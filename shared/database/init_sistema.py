#!/usr/bin/env python3
"""
Inicialización idempotente del sistema GlobalTradeSA.
- Modelo estrella (histórico parquet hasta 100k filas)
- Tablas operativas ERP (M01–M13)
- Semillas base y catálogo B2B
"""

from __future__ import annotations

import sys
from pathlib import Path

import duckdb
from passlib.context import CryptContext

from shared.database.connection import column_exists, connect, repo_root, resolve_duckdb_path, table_exists
from shared.database.seeds.catalogo_demo import reparar_imagenes_desde_storage, seed_catalogo_demo, seed_marcas

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
PARQUET_LIMIT = 100_000
DEMO_PASSWORD = "12345678"


def _hash_password(password: str) -> str:
    return pwd_context.hash(password)


def _exec_many(conn, sql: str) -> None:
    for stmt in sql.split(";\n"):
        s = stmt.strip()
        if s:
            conn.execute(s)


def _ensure_sequences(conn) -> None:
    sequences = [
        "seq_usuarios", "seq_dim_cliente", "seq_dim_producto", "seq_pedidos", "seq_pedido_detalle",
        "seq_roles", "seq_permisos", "seq_categorias", "seq_marcas", "seq_productos", "seq_listas_precios",
        "seq_clientes", "seq_carritos", "seq_comprobantes", "seq_asientos", "seq_proveedores",
        "seq_almacenes", "seq_movimientos", "seq_pagos", "seq_facturas",
        "seq_ordenes_compra", "seq_recepciones", "seq_cotizaciones", "seq_grupos_cliente",
        "seq_proveedor_contactos", "seq_cliente_contactos", "seq_lotes", "seq_transferencias",
    ]
    for name in sequences:
        conn.execute(f"CREATE SEQUENCE IF NOT EXISTS {name} START 1")


def _load_star_schema_if_empty(conn, parquet_path: Path) -> None:
    if table_exists(conn, "fact_ventas"):
        count = conn.execute("SELECT COUNT(*) FROM fact_ventas").fetchone()[0]
        if count > 0:
            print(f"[init] fact_ventas ya tiene {count} filas — omitiendo carga parquet.")
            return

    if not parquet_path.exists():
        print(f"[init] AVISO: no existe {parquet_path}; se omiten ventas históricas.")
        return

    parquet = parquet_path.as_posix()
    conn.execute("DROP TABLE IF EXISTS staging")
    conn.execute(
        f"""
        CREATE TABLE staging AS
        SELECT * FROM read_parquet('{parquet}')
        LIMIT {PARQUET_LIMIT}
        """
    )
    conn.execute(
        """
        ALTER TABLE staging
        ALTER COLUMN order_date TYPE DATE
        USING strptime(order_date::VARCHAR, '%m/%d/%Y')::DATE
        """
    )
    conn.execute(
        """
        ALTER TABLE staging
        ALTER COLUMN ship_date TYPE DATE
        USING strptime(ship_date::VARCHAR, '%m/%d/%Y')::DATE
        """
    )

    if not table_exists(conn, "dim_region"):
        conn.execute("CREATE TABLE dim_region (id_region INTEGER PRIMARY KEY, region VARCHAR NOT NULL UNIQUE)")
    if not table_exists(conn, "dim_country"):
        conn.execute(
            """
            CREATE TABLE dim_country (
              id_country INTEGER PRIMARY KEY,
              country VARCHAR NOT NULL,
              id_region INTEGER NOT NULL,
              UNIQUE(country, id_region)
            )
            """
        )
    if not table_exists(conn, "dim_item_type"):
        conn.execute(
            """
            CREATE TABLE dim_item_type (
              id_item_type INTEGER PRIMARY KEY,
              item_type VARCHAR NOT NULL UNIQUE,
              unit_price DECIMAL(10,2) NOT NULL,
              unit_cost DECIMAL(10,2) NOT NULL
            )
            """
        )
    if not table_exists(conn, "dim_sales_channel"):
        conn.execute("CREATE TABLE dim_sales_channel (id_channel INTEGER PRIMARY KEY, sales_channel VARCHAR NOT NULL UNIQUE)")
    if not table_exists(conn, "dim_order_priority"):
        conn.execute("CREATE TABLE dim_order_priority (id_priority INTEGER PRIMARY KEY, order_priority VARCHAR NOT NULL UNIQUE)")

    conn.execute("DELETE FROM dim_region")
    conn.execute(
        """
        INSERT INTO dim_region (id_region, region)
        SELECT row_number() OVER (ORDER BY region), region
        FROM (SELECT DISTINCT region FROM staging WHERE region IS NOT NULL)
        """
    )
    conn.execute("DELETE FROM dim_country")
    conn.execute(
        """
        INSERT INTO dim_country (id_country, country, id_region)
        SELECT row_number() OVER (ORDER BY s.country, r.id_region), s.country, r.id_region
        FROM (SELECT DISTINCT country, region FROM staging WHERE country IS NOT NULL) s
        JOIN dim_region r ON r.region = s.region
        """
    )
    conn.execute("DELETE FROM dim_item_type")
    conn.execute(
        """
        INSERT INTO dim_item_type (id_item_type, item_type, unit_price, unit_cost)
        SELECT row_number() OVER (ORDER BY item_type), item_type,
               CAST(AVG(unit_price) AS DECIMAL(10,2)), CAST(AVG(unit_cost) AS DECIMAL(10,2))
        FROM staging WHERE item_type IS NOT NULL GROUP BY item_type
        """
    )
    conn.execute("DELETE FROM dim_sales_channel")
    conn.execute(
        """
        INSERT INTO dim_sales_channel (id_channel, sales_channel)
        SELECT row_number() OVER (ORDER BY sales_channel), sales_channel
        FROM (SELECT DISTINCT sales_channel FROM staging WHERE sales_channel IS NOT NULL)
        """
    )
    conn.execute("DELETE FROM dim_order_priority")
    conn.execute(
        """
        INSERT INTO dim_order_priority (id_priority, order_priority)
        SELECT row_number() OVER (ORDER BY order_priority), order_priority
        FROM (SELECT DISTINCT order_priority FROM staging WHERE order_priority IS NOT NULL)
        """
    )

    if not table_exists(conn, "fact_ventas"):
        conn.execute(
            """
            CREATE TABLE fact_ventas (
              id_venta INTEGER PRIMARY KEY,
              order_id BIGINT NOT NULL UNIQUE,
              id_region INTEGER NOT NULL,
              id_country INTEGER NOT NULL,
              id_item_type INTEGER NOT NULL,
              id_channel INTEGER NOT NULL,
              id_priority INTEGER NOT NULL,
              order_date DATE NOT NULL,
              ship_date DATE NOT NULL,
              units_sold INTEGER NOT NULL,
              unit_price DECIMAL(10,2) NOT NULL,
              unit_cost DECIMAL(10,2) NOT NULL,
              total_revenue DECIMAL(12,2) NOT NULL,
              total_cost DECIMAL(12,2) NOT NULL,
              total_profit DECIMAL(12,2) NOT NULL,
              id_producto BIGINT,
              origen VARCHAR DEFAULT 'historico'
            )
            """
        )
    else:
        conn.execute("DELETE FROM fact_ventas")

    conn.execute(
        """
        INSERT INTO fact_ventas (
          id_venta, order_id, id_region, id_country, id_item_type, id_channel, id_priority,
          order_date, ship_date, units_sold, unit_price, unit_cost,
          total_revenue, total_cost, total_profit, id_producto, origen
        )
        SELECT
          row_number() OVER (ORDER BY s.order_id),
          CAST(s.order_id AS BIGINT),
          r.id_region, c.id_country, it.id_item_type, ch.id_channel, p.id_priority,
          s.order_date, s.ship_date,
          CAST(s.units_sold AS INTEGER),
          CAST(s.unit_price AS DECIMAL(10,2)), CAST(s.unit_cost AS DECIMAL(10,2)),
          CAST(s.total_revenue AS DECIMAL(12,2)), CAST(s.total_cost AS DECIMAL(12,2)),
          CAST(s.total_profit AS DECIMAL(12,2)),
          NULL, 'historico'
        FROM staging s
        JOIN dim_region r ON r.region = s.region
        JOIN dim_country c ON c.country = s.country AND c.id_region = r.id_region
        JOIN dim_item_type it ON it.item_type = s.item_type
        JOIN dim_sales_channel ch ON ch.sales_channel = s.sales_channel
        JOIN dim_order_priority p ON p.order_priority = s.order_priority
        """
    )
    conn.execute("DROP TABLE IF EXISTS staging")
    print(f"[init] Cargadas hasta {PARQUET_LIMIT} filas históricas en fact_ventas.")


def _extend_fact_ventas(conn) -> None:
    if table_exists(conn, "fact_ventas"):
        if not column_exists(conn, "fact_ventas", "id_producto"):
            conn.execute("ALTER TABLE fact_ventas ADD COLUMN id_producto BIGINT")
        if not column_exists(conn, "fact_ventas", "origen"):
            conn.execute("ALTER TABLE fact_ventas ADD COLUMN origen VARCHAR DEFAULT 'historico'")
            conn.execute("UPDATE fact_ventas SET origen = 'historico' WHERE origen IS NULL")


def _extend_pedidos(conn) -> None:
    """Columnas adicionales del ciclo de venta completo sobre la tabla legacy."""
    if not table_exists(conn, "pedidos"):
        return
    extras = [
        ("numero", "VARCHAR"),
        ("id_direccion_entrega", "BIGINT"),
        ("subtotal", "DECIMAL(12,2)"),
        ("impuesto_monto", "DECIMAL(12,2)"),
        ("total", "DECIMAL(12,2)"),
        ("descuento_pct", "DECIMAL(5,2)"),
        ("descuento_monto", "DECIMAL(12,2)"),
        ("id_promocion", "BIGINT"),
    ]
    for col, tipo in extras:
        if not column_exists(conn, "pedidos", col):
            conn.execute(f"ALTER TABLE pedidos ADD COLUMN {col} {tipo}")
    if table_exists(conn, "pedido_detalle") and not column_exists(conn, "pedido_detalle", "costo_unitario"):
        conn.execute("ALTER TABLE pedido_detalle ADD COLUMN costo_unitario DECIMAL(10,2)")


def _extend_compras(conn) -> None:
    """Migración idempotente: método de pago en OC, motivo de diferencia en
    recepciones, asientos ligados a órdenes de compra y cuentas de proveedores."""
    extras_oc = [("metodo_pago", "VARCHAR DEFAULT 'caja'")]
    for col, tipo in extras_oc:
        if table_exists(conn, "ordenes_compra") and not column_exists(conn, "ordenes_compra", col):
            conn.execute(f"ALTER TABLE ordenes_compra ADD COLUMN {col} {tipo}")
    if table_exists(conn, "recepcion_compra_detalle") and not column_exists(conn, "recepcion_compra_detalle", "observacion"):
        conn.execute("ALTER TABLE recepcion_compra_detalle ADD COLUMN observacion VARCHAR")
    if table_exists(conn, "asientos_contables") and not column_exists(conn, "asientos_contables", "id_oc"):
        conn.execute("ALTER TABLE asientos_contables ADD COLUMN id_oc BIGINT")

    if table_exists(conn, "plan_cuentas"):
        for cid, codigo, nombre, tipo in [
            (6, "2002", "Cuentas por pagar a proveedores", "pasivo"),
            (7, "3001", "Pagos externos (financiamiento)", "pasivo"),
        ]:
            conn.execute(
                """
                INSERT INTO plan_cuentas (id_cuenta, codigo, nombre, tipo)
                SELECT ?, ?, ?, ?
                WHERE NOT EXISTS (SELECT 1 FROM plan_cuentas WHERE codigo = ?)
                """,
                [cid, codigo, nombre, tipo, codigo],
            )

    _backfill_recepciones_estado(conn)


def _backfill_recepciones_estado(conn) -> None:
    """Corrige el estado de recepciones históricas: 'completa' solo cuando lo
    recibido acumulado cubre el total pedido de la OC; si no, 'parcial'."""
    if not (
        table_exists(conn, "recepciones_compra")
        and column_exists(conn, "recepciones_compra", "estado")
        and table_exists(conn, "recepcion_compra_detalle")
        and table_exists(conn, "orden_compra_detalle")
    ):
        return
    filas = conn.execute(
        """
        WITH por_rec AS (
            SELECT rc.id_recepcion, rc.id_oc, CAST(SUM(rcd.cantidad_recibida) AS DOUBLE) AS recibido
            FROM recepciones_compra rc
            JOIN recepcion_compra_detalle rcd ON rcd.id_recepcion = rc.id_recepcion
            GROUP BY rc.id_recepcion, rc.id_oc
        ),
        acum AS (
            SELECT id_recepcion, id_oc,
                   SUM(recibido) OVER (PARTITION BY id_oc ORDER BY id_recepcion) AS rec_acum
            FROM por_rec
        ),
        ped AS (
            SELECT id_oc, SUM(cantidad) AS total
            FROM orden_compra_detalle
            GROUP BY id_oc
        )
        SELECT a.id_recepcion,
               CASE WHEN a.rec_acum + 1e-9 >= COALESCE(p.total, 0) THEN 'completa' ELSE 'parcial' END
        FROM acum a
        LEFT JOIN ped p ON p.id_oc = a.id_oc
        """
    )
    for id_rec, estado_real in filas.fetchall():
        conn.execute(
            "UPDATE recepciones_compra SET estado = ? WHERE id_recepcion = ?",
            [estado_real, int(id_rec)],
        )


def _create_views(conn) -> None:
    conn.execute(
        """
        CREATE OR REPLACE VIEW ventas AS
        SELECT
          dr.region, dc.country, dit.item_type, dsc.sales_channel, dop.order_priority,
          fv.order_date, fv.order_id, fv.ship_date, fv.units_sold,
          fv.unit_price, fv.unit_cost, fv.total_revenue, fv.total_cost, fv.total_profit,
          fv.id_venta, fv.id_producto, fv.origen,
          dp.nombre_producto,
          COALESCE(dp.nombre_producto, dit.item_type) AS dimension_producto,
          COALESCE(cat.nombre, dit.item_type) AS dimension_categoria
        FROM fact_ventas fv
        JOIN dim_region dr ON dr.id_region = fv.id_region
        JOIN dim_country dc ON dc.id_country = fv.id_country
        JOIN dim_item_type dit ON dit.id_item_type = fv.id_item_type
        JOIN dim_sales_channel dsc ON dsc.id_channel = fv.id_channel
        JOIN dim_order_priority dop ON dop.id_priority = fv.id_priority
        LEFT JOIN dim_producto dp ON dp.id_producto = fv.id_producto
        LEFT JOIN categorias cat ON cat.id_item_type = fv.id_item_type
        """
    )
    if table_exists(conn, "stock_almacen") and table_exists(conn, "productos"):
        conn.execute(
            """
            CREATE OR REPLACE VIEW vista_stock_valorizado AS
            SELECT sa.id_producto, sa.id_almacen, sa.cantidad_disponible,
                   COALESCE(p.costo_estandar, 0) AS costo,
                   sa.cantidad_disponible * COALESCE(p.costo_estandar, 0) AS valor
            FROM stock_almacen sa
            LEFT JOIN productos p ON p.id_producto = sa.id_producto
            """
        )
    if table_exists(conn, "fact_ventas"):
        conn.execute(
            """
            CREATE OR REPLACE VIEW vista_rentabilidad_producto AS
            SELECT id_producto,
                   SUM(total_revenue) AS ingresos,
                   SUM(total_cost) AS costos,
                   SUM(total_profit) AS margen
            FROM fact_ventas
            WHERE id_producto IS NOT NULL
            GROUP BY id_producto
            """
        )


def _extend_usuarios(conn) -> None:
    """Columna nombre para el panel (gobierno de acceso) y orden fijo en listados."""
    conn.execute(
        "ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS nombre VARCHAR DEFAULT ''"
    )


def _extend_maestras_region(conn) -> None:
    """Asocia almacenes, transportistas y usuarios del panel a una región geoespacial."""
    if table_exists(conn, "almacenes"):
        conn.execute("ALTER TABLE almacenes ADD COLUMN IF NOT EXISTS id_region BIGINT")
    if table_exists(conn, "transportistas"):
        conn.execute(
            "ALTER TABLE transportistas ADD COLUMN IF NOT EXISTS id_region BIGINT"
        )
    if table_exists(conn, "usuarios"):
        conn.execute("ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS id_region BIGINT")


USUARIOS_STAFF_DEMO = [
    ("admin@globmarket.com", DEMO_PASSWORD, "admin", "Administrador GlobalTrade"),
    ("vendedor@globmarket.com", DEMO_PASSWORD, "vendedor", "Carla Mendoza (Ventas)"),
    ("almacen@globmarket.com", DEMO_PASSWORD, "almacen", "Jorge Ramírez (Almacén)"),
    ("gerente@globmarket.com", DEMO_PASSWORD, "gerente", "Gerente Informes"),
]


def _seed_usuarios_staff(conn) -> None:
    """Crea (de forma idempotente) un usuario de panel por rol: admin, vendedor, almacén."""
    for email, password, rol, nombre in USUARIOS_STAFF_DEMO:
        conn.execute(
            """
            UPDATE usuarios SET nombre = ?
            WHERE email = ? AND COALESCE(nombre, '') = ''
            """,
            [nombre, email],
        )
        conn.execute(
            """
            INSERT INTO usuarios (email, password_hash, rol, activo, nombre)
            SELECT ?, ?, ?, true, ?
            WHERE NOT EXISTS (SELECT 1 FROM usuarios WHERE email = ?)
            """,
            [email, _hash_password(password), rol, nombre, email],
        )
        conn.execute(
            "UPDATE usuarios SET password_hash = ? WHERE email = ?",
            [_hash_password(DEMO_PASSWORD), email],
        )


def _create_legacy_b2b_tables(conn) -> None:
    _exec_many(
        conn,
        """
        CREATE TABLE IF NOT EXISTS usuarios (
          id_usuario BIGINT PRIMARY KEY DEFAULT nextval('seq_usuarios'),
          email VARCHAR UNIQUE NOT NULL,
          password_hash VARCHAR NOT NULL,
          rol VARCHAR DEFAULT 'cliente',
          activo BOOLEAN DEFAULT true,
          fecha_registro TIMESTAMP DEFAULT current_timestamp
        );

        CREATE TABLE IF NOT EXISTS dim_cliente (
          id_cliente BIGINT PRIMARY KEY DEFAULT nextval('seq_dim_cliente'),
          id_usuario BIGINT,
          nombre_empresa VARCHAR NOT NULL,
          pais VARCHAR NOT NULL,
          telefono VARCHAR,
          direccion VARCHAR
        );

        CREATE TABLE IF NOT EXISTS dim_producto (
          id_producto BIGINT PRIMARY KEY DEFAULT nextval('seq_dim_producto'),
          nombre_producto VARCHAR NOT NULL,
          descripcion VARCHAR,
          id_item_type BIGINT NOT NULL,
          precio_unitario DECIMAL(10,2),
          precio_mayorista DECIMAL(10,2),
          imagen_url VARCHAR,
          activo BOOLEAN DEFAULT true
        );

        CREATE TABLE IF NOT EXISTS pedidos (
          id_pedido BIGINT PRIMARY KEY DEFAULT nextval('seq_pedidos'),
          id_cliente BIGINT NOT NULL,
          id_country BIGINT NOT NULL,
          id_channel BIGINT NOT NULL,
          id_priority BIGINT NOT NULL,
          fecha_pedido TIMESTAMP DEFAULT current_timestamp,
          estado VARCHAR DEFAULT 'pendiente_pago',
          total_pedido DECIMAL(12,2),
          notas VARCHAR
        );

        CREATE TABLE IF NOT EXISTS pedido_detalle (
          id_detalle BIGINT PRIMARY KEY DEFAULT nextval('seq_pedido_detalle'),
          id_pedido BIGINT NOT NULL,
          id_producto BIGINT NOT NULL,
          cantidad BIGINT NOT NULL,
          precio_unitario DECIMAL(10,2),
          subtotal DECIMAL(12,2)
        )
        """,
    )


def _create_extended_tables(conn) -> None:
    """Tablas adicionales M03–M12 no incluidas en el bloque ERP base."""
    ddl = """
    CREATE TABLE IF NOT EXISTS producto_variantes (
      id_variante BIGINT PRIMARY KEY, id_producto BIGINT, nombre VARCHAR,
      sku_variante VARCHAR, factor DECIMAL(10,4) DEFAULT 1
    );
    CREATE TABLE IF NOT EXISTS atributos_definicion (
      id_atributo BIGINT PRIMARY KEY, nombre VARCHAR, tipo VARCHAR
    );
    CREATE TABLE IF NOT EXISTS producto_atributos (
      id_producto BIGINT, id_atributo BIGINT, valor VARCHAR
    );
    CREATE TABLE IF NOT EXISTS proveedor_contactos (
      id_contacto BIGINT PRIMARY KEY DEFAULT nextval('seq_proveedor_contactos'),
      id_proveedor BIGINT, nombre VARCHAR, email VARCHAR, telefono VARCHAR
    );
    CREATE TABLE IF NOT EXISTS ordenes_compra (
      id_oc BIGINT PRIMARY KEY DEFAULT nextval('seq_ordenes_compra'),
      numero VARCHAR, id_proveedor BIGINT, fecha TIMESTAMP, estado VARCHAR, total DECIMAL(12,2),
      metodo_pago VARCHAR DEFAULT 'caja'
    );
    CREATE TABLE IF NOT EXISTS orden_compra_detalle (
      id_detalle BIGINT PRIMARY KEY, id_oc BIGINT, id_producto BIGINT,
      cantidad DECIMAL(12,4), costo_unitario DECIMAL(10,2), subtotal DECIMAL(12,2)
    );
    CREATE TABLE IF NOT EXISTS recepciones_compra (
      id_recepcion BIGINT PRIMARY KEY DEFAULT nextval('seq_recepciones'),
      id_oc BIGINT, fecha TIMESTAMP, id_almacen BIGINT, estado VARCHAR
    );
    CREATE TABLE IF NOT EXISTS recepcion_compra_detalle (
      id_detalle BIGINT PRIMARY KEY, id_recepcion BIGINT, id_producto BIGINT,
      cantidad_recibida DECIMAL(12,4), id_lote BIGINT, observacion VARCHAR
    );
    CREATE TABLE IF NOT EXISTS devoluciones_proveedor (
      id_devolucion BIGINT PRIMARY KEY, id_oc BIGINT, fecha TIMESTAMP, motivo VARCHAR, total DECIMAL(12,2)
    );
    CREATE TABLE IF NOT EXISTS ubicaciones_almacen (
      id_ubicacion BIGINT PRIMARY KEY, id_almacen BIGINT, codigo VARCHAR
    );
    CREATE TABLE IF NOT EXISTS lotes_inventario (
      id_lote BIGINT PRIMARY KEY DEFAULT nextval('seq_lotes'),
      id_producto BIGINT, codigo_lote VARCHAR, fecha_vencimiento DATE, cantidad DECIMAL(12,4)
    );
    CREATE TABLE IF NOT EXISTS movimiento_inventario_detalle (
      id_detalle BIGINT PRIMARY KEY, id_movimiento BIGINT, id_producto BIGINT,
      id_almacen BIGINT, id_lote BIGINT, cantidad DECIMAL(12,4)
    );
    CREATE TABLE IF NOT EXISTS reservas_stock (
      id_reserva BIGINT PRIMARY KEY, id_pedido BIGINT, id_producto BIGINT,
      id_almacen BIGINT, cantidad DECIMAL(12,4), estado VARCHAR DEFAULT 'activa'
    );
    CREATE TABLE IF NOT EXISTS transferencias_almacen (
      id_transferencia BIGINT PRIMARY KEY DEFAULT nextval('seq_transferencias'),
      id_almacen_origen BIGINT, id_almacen_destino BIGINT, fecha TIMESTAMP, estado VARCHAR
    );
    CREATE TABLE IF NOT EXISTS alertas_stock (
      id_alerta BIGINT PRIMARY KEY, id_producto BIGINT, id_almacen BIGINT,
      umbral_minimo DECIMAL(12,4), activa BOOLEAN DEFAULT true
    );
    CREATE TABLE IF NOT EXISTS cliente_contactos (
      id_contacto BIGINT PRIMARY KEY DEFAULT nextval('seq_cliente_contactos'),
      id_cliente BIGINT, nombre VARCHAR, cargo VARCHAR, email VARCHAR, telefono VARCHAR
    );
    CREATE TABLE IF NOT EXISTS grupos_cliente (
      id_grupo BIGINT PRIMARY KEY DEFAULT nextval('seq_grupos_cliente'),
      nombre VARCHAR, id_lista BIGINT
    );
    CREATE TABLE IF NOT EXISTS cliente_grupo (id_cliente BIGINT, id_grupo BIGINT);
    CREATE TABLE IF NOT EXISTS condiciones_credito (
      id_condicion BIGINT PRIMARY KEY, id_cliente BIGINT,
      dias_pago INTEGER, limite_credito DECIMAL(12,2), bloqueado BOOLEAN DEFAULT false
    );
    CREATE TABLE IF NOT EXISTS cuenta_corriente_cliente (
      id_cliente BIGINT PRIMARY KEY, saldo DECIMAL(12,2) DEFAULT 0
    );
    CREATE TABLE IF NOT EXISTS movimientos_cxc (
      id_movimiento BIGINT PRIMARY KEY, id_cliente BIGINT, tipo VARCHAR,
      id_factura BIGINT, id_pago BIGINT, monto DECIMAL(12,2), fecha TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS cotizaciones (
      id_cotizacion BIGINT PRIMARY KEY DEFAULT nextval('seq_cotizaciones'),
      numero VARCHAR, id_cliente BIGINT, fecha TIMESTAMP, estado VARCHAR,
      total DECIMAL(12,2), validez DATE
    );
    CREATE TABLE IF NOT EXISTS cotizacion_detalle (
      id_detalle BIGINT PRIMARY KEY, id_cotizacion BIGINT, id_producto BIGINT,
      cantidad INTEGER, precio DECIMAL(10,2), subtotal DECIMAL(12,2)
    );
    CREATE TABLE IF NOT EXISTS envio_detalle (
      id_detalle BIGINT PRIMARY KEY, id_envio BIGINT, id_producto BIGINT,
      cantidad INTEGER, id_lote BIGINT
    );
    CREATE TABLE IF NOT EXISTS guias_remision (
      id_guia BIGINT PRIMARY KEY, numero VARCHAR, id_envio BIGINT, fecha TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS devoluciones_cliente (
      id_devolucion BIGINT PRIMARY KEY, id_pedido BIGINT, fecha TIMESTAMP,
      motivo VARCHAR, total DECIMAL(12,2), estado VARCHAR
    );
    CREATE TABLE IF NOT EXISTS cuentas_bancarias (
      id_cuenta BIGINT PRIMARY KEY, nombre VARCHAR, saldo DECIMAL(12,2) DEFAULT 0
    );
    CREATE TABLE IF NOT EXISTS movimientos_tesoreria (
      id_movimiento BIGINT PRIMARY KEY, id_cuenta BIGINT, tipo VARCHAR,
      monto DECIMAL(12,2), id_pago BIGINT, fecha TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS conciliaciones_pago (
      id_conciliacion BIGINT PRIMARY KEY, id_pago BIGINT,
      monto_esperado DECIMAL(12,2), monto_recibido DECIMAL(12,2), estado VARCHAR
    );
    CREATE TABLE IF NOT EXISTS fact_compras (
      id_compra BIGINT PRIMARY KEY, id_oc BIGINT, id_producto BIGINT,
      cantidad DECIMAL(12,4), costo DECIMAL(12,2), fecha TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS dim_tiempo (
      fecha DATE PRIMARY KEY, anio INTEGER, mes INTEGER, trimestre INTEGER, dia_semana INTEGER
    );
    CREATE TABLE IF NOT EXISTS tarifas_envio (
      id_tarifa BIGINT PRIMARY KEY, id_zona BIGINT, peso_max DECIMAL(10,2), costo DECIMAL(10,2)
    );
    CREATE TABLE IF NOT EXISTS rutas_envio (
      id_ruta BIGINT PRIMARY KEY, nombre VARCHAR, id_zona BIGINT
    );
    CREATE TABLE IF NOT EXISTS promocion_productos (id_promocion BIGINT, id_producto BIGINT)
    """
    _exec_many(conn, ddl)


def _create_erp_tables(conn) -> None:
    ddl = """
    CREATE TABLE IF NOT EXISTS roles (
      id_rol BIGINT PRIMARY KEY DEFAULT nextval('seq_roles'),
      nombre VARCHAR UNIQUE NOT NULL,
      descripcion VARCHAR
    );
    CREATE TABLE IF NOT EXISTS permisos (
      id_permiso BIGINT PRIMARY KEY DEFAULT nextval('seq_permisos'),
      codigo VARCHAR UNIQUE NOT NULL,
      descripcion VARCHAR
    );
    CREATE TABLE IF NOT EXISTS rol_permiso (id_rol BIGINT, id_permiso BIGINT);
    CREATE TABLE IF NOT EXISTS usuario_rol (id_usuario BIGINT, id_rol BIGINT);
    CREATE TABLE IF NOT EXISTS auditoria_log (
      id_log BIGINT PRIMARY KEY,
      id_usuario BIGINT, entidad VARCHAR, entidad_id BIGINT,
      accion VARCHAR, valor_anterior VARCHAR, valor_nuevo VARCHAR,
      fecha TIMESTAMP DEFAULT current_timestamp
    );
    CREATE TABLE IF NOT EXISTS configuracion_sistema (
      clave VARCHAR PRIMARY KEY, valor VARCHAR, descripcion VARCHAR
    );
    CREATE TABLE IF NOT EXISTS monedas (
      id_moneda BIGINT PRIMARY KEY, codigo VARCHAR UNIQUE, simbolo VARCHAR, nombre VARCHAR
    );
    CREATE TABLE IF NOT EXISTS tipos_cambio (
      id_tc BIGINT PRIMARY KEY, id_moneda BIGINT, fecha DATE, tasa DECIMAL(12,6)
    );
    CREATE TABLE IF NOT EXISTS zonas_envio (
      id_zona BIGINT PRIMARY KEY, nombre VARCHAR, costo_base DECIMAL(10,2)
    );
    CREATE TABLE IF NOT EXISTS calendario_operativo (
      fecha DATE PRIMARY KEY, es_habil BOOLEAN, descripcion VARCHAR
    );
    CREATE TABLE IF NOT EXISTS categorias (
      id_categoria BIGINT PRIMARY KEY DEFAULT nextval('seq_categorias'),
      nombre VARCHAR NOT NULL, slug VARCHAR UNIQUE, descripcion VARCHAR,
      id_categoria_padre BIGINT, imagen_path VARCHAR, activo BOOLEAN DEFAULT true,
      id_item_type BIGINT
    );
    CREATE TABLE IF NOT EXISTS marcas (
      id_marca BIGINT PRIMARY KEY DEFAULT nextval('seq_marcas'),
      nombre VARCHAR UNIQUE, activo BOOLEAN DEFAULT true
    );
    CREATE TABLE IF NOT EXISTS unidades_medida (
      id_unidad BIGINT PRIMARY KEY, nombre VARCHAR, factor_conversion DECIMAL(10,4) DEFAULT 1
    );
    CREATE TABLE IF NOT EXISTS productos (
      id_producto BIGINT PRIMARY KEY DEFAULT nextval('seq_productos'),
      sku VARCHAR UNIQUE, nombre VARCHAR NOT NULL, descripcion VARCHAR,
      id_categoria BIGINT, id_marca BIGINT, id_unidad BIGINT,
      costo_estandar DECIMAL(10,2), activo BOOLEAN DEFAULT true
    );
    CREATE TABLE IF NOT EXISTS producto_categorias (id_producto BIGINT, id_categoria BIGINT);
    CREATE TABLE IF NOT EXISTS producto_imagenes (
      id_imagen BIGINT PRIMARY KEY, id_producto BIGINT, imagen_path VARCHAR,
      es_principal BOOLEAN DEFAULT false, orden INTEGER DEFAULT 0
    );
    CREATE TABLE IF NOT EXISTS listas_precios (
      id_lista BIGINT PRIMARY KEY DEFAULT nextval('seq_listas_precios'),
      nombre VARCHAR NOT NULL, id_moneda BIGINT, activo BOOLEAN DEFAULT true
    );
    CREATE TABLE IF NOT EXISTS lista_precio_detalle (
      id_detalle BIGINT PRIMARY KEY, id_lista BIGINT, id_producto BIGINT,
      precio DECIMAL(10,2), cantidad_minima INTEGER DEFAULT 1
    );
    CREATE TABLE IF NOT EXISTS proveedores (
      id_proveedor BIGINT PRIMARY KEY DEFAULT nextval('seq_proveedores'),
      razon_social VARCHAR, ruc VARCHAR, id_country BIGINT, activo BOOLEAN DEFAULT true
    );
    CREATE TABLE IF NOT EXISTS almacenes (
      id_almacen BIGINT PRIMARY KEY DEFAULT nextval('seq_almacenes'),
      nombre VARCHAR, direccion VARCHAR, id_region BIGINT, activo BOOLEAN DEFAULT true
    );
    CREATE TABLE IF NOT EXISTS stock_almacen (
      id_stock BIGINT PRIMARY KEY, id_producto BIGINT, id_almacen BIGINT,
      cantidad_disponible DECIMAL(12,4) DEFAULT 0, cantidad_reservada DECIMAL(12,4) DEFAULT 0
    );
    CREATE TABLE IF NOT EXISTS movimientos_inventario (
      id_movimiento BIGINT PRIMARY KEY DEFAULT nextval('seq_movimientos'),
      tipo VARCHAR, fecha TIMESTAMP DEFAULT current_timestamp, referencia VARCHAR, id_usuario BIGINT
    );
    CREATE TABLE IF NOT EXISTS clientes (
      id_cliente BIGINT PRIMARY KEY DEFAULT nextval('seq_clientes'),
      id_usuario BIGINT, nombre_empresa VARCHAR, ruc VARCHAR, id_country BIGINT, activo BOOLEAN DEFAULT true
    );
    CREATE TABLE IF NOT EXISTS cliente_direcciones (
      id_direccion BIGINT PRIMARY KEY, id_cliente BIGINT, tipo VARCHAR,
      direccion VARCHAR, ciudad VARCHAR, id_country BIGINT, predeterminada BOOLEAN DEFAULT false
    );
    CREATE TABLE IF NOT EXISTS carritos (
      id_carrito BIGINT PRIMARY KEY DEFAULT nextval('seq_carritos'),
      id_cliente BIGINT, estado VARCHAR DEFAULT 'activo',
      fecha TIMESTAMP DEFAULT current_timestamp
    );
    CREATE TABLE IF NOT EXISTS carrito_items (
      id_item BIGINT PRIMARY KEY, id_carrito BIGINT, id_producto BIGINT,
      cantidad INTEGER, precio_congelado DECIMAL(10,2), subtotal DECIMAL(12,2)
    );
    CREATE TABLE IF NOT EXISTS pedido_estados_historial (
      id_historial BIGINT PRIMARY KEY, id_pedido BIGINT,
      estado_anterior VARCHAR, estado_nuevo VARCHAR, id_usuario BIGINT,
      fecha TIMESTAMP DEFAULT current_timestamp
    );
    CREATE TABLE IF NOT EXISTS facturas_venta (
      id_factura BIGINT PRIMARY KEY DEFAULT nextval('seq_facturas'),
      numero VARCHAR, id_pedido BIGINT, id_cliente BIGINT, fecha TIMESTAMP,
      subtotal DECIMAL(12,2), impuesto_monto DECIMAL(12,2), total DECIMAL(12,2), estado VARCHAR
    );
    CREATE TABLE IF NOT EXISTS factura_venta_detalle (
      id_detalle BIGINT PRIMARY KEY, id_factura BIGINT, id_producto BIGINT,
      cantidad INTEGER, precio_unitario DECIMAL(10,2), subtotal DECIMAL(12,2)
    );
    CREATE TABLE IF NOT EXISTS metodos_pago (
      id_metodo BIGINT PRIMARY KEY, nombre VARCHAR UNIQUE, activo BOOLEAN DEFAULT true
    );
    CREATE TABLE IF NOT EXISTS pagos (
      id_pago BIGINT PRIMARY KEY DEFAULT nextval('seq_pagos'),
      numero VARCHAR, id_pedido BIGINT, id_factura BIGINT, id_metodo BIGINT,
      monto DECIMAL(12,2), estado VARCHAR, referencia VARCHAR, fecha TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS plan_cuentas (
      id_cuenta BIGINT PRIMARY KEY, codigo VARCHAR UNIQUE, nombre VARCHAR, tipo VARCHAR
    );
    CREATE TABLE IF NOT EXISTS asientos_contables (
      id_asiento BIGINT PRIMARY KEY DEFAULT nextval('seq_asientos'),
      numero VARCHAR, fecha TIMESTAMP, descripcion VARCHAR,
      id_pedido BIGINT, id_factura BIGINT, id_oc BIGINT, total DECIMAL(12,2)
    );
    CREATE TABLE IF NOT EXISTS asiento_lineas (
      id_linea BIGINT PRIMARY KEY, id_asiento BIGINT, id_cuenta BIGINT,
      debe DECIMAL(12,2) DEFAULT 0, haber DECIMAL(12,2) DEFAULT 0
    );
    CREATE TABLE IF NOT EXISTS comprobantes (
      id_comprobante BIGINT PRIMARY KEY DEFAULT nextval('seq_comprobantes'),
      tipo VARCHAR, serie VARCHAR, numero VARCHAR,
      entidad_tipo VARCHAR, entidad_id BIGINT, pdf_path VARCHAR,
      fecha_generacion TIMESTAMP DEFAULT current_timestamp, id_usuario BIGINT
    );
    CREATE TABLE IF NOT EXISTS comprobante_series (
      id_serie BIGINT PRIMARY KEY, tipo VARCHAR, serie VARCHAR, anio INTEGER, ultimo_numero INTEGER DEFAULT 0
    );
    CREATE TABLE IF NOT EXISTS transportistas (
      id_transportista BIGINT PRIMARY KEY, nombre VARCHAR, id_region BIGINT, activo BOOLEAN DEFAULT true
    );
    CREATE TABLE IF NOT EXISTS tracking_eventos (
      id_evento BIGINT PRIMARY KEY, id_envio BIGINT, estado VARCHAR,
      fecha TIMESTAMP, descripcion VARCHAR
    );
    CREATE TABLE IF NOT EXISTS envios (
      id_envio BIGINT PRIMARY KEY, id_pedido BIGINT, id_transportista BIGINT,
      fecha_despacho TIMESTAMP, estado VARCHAR, id_zona BIGINT
    );
    CREATE TABLE IF NOT EXISTS banners_portal (
      id_banner BIGINT PRIMARY KEY, titulo VARCHAR, imagen_path VARCHAR,
      enlace VARCHAR, activo BOOLEAN DEFAULT true, orden INTEGER DEFAULT 0
    );
    CREATE TABLE IF NOT EXISTS promociones (
      id_promocion BIGINT PRIMARY KEY, nombre VARCHAR, descuento_pct DECIMAL(5,2),
      fecha_inicio DATE, fecha_fin DATE, activa BOOLEAN DEFAULT true
    );
    CREATE TABLE IF NOT EXISTS wishlist_items (
      id_item BIGINT PRIMARY KEY, id_cliente BIGINT, id_producto BIGINT, fecha TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS etl_jobs (
      id_job BIGINT PRIMARY KEY, tipo VARCHAR, estado VARCHAR,
      fecha_inicio TIMESTAMP, fecha_fin TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS etl_job_logs (
      id_log BIGINT PRIMARY KEY, id_job BIGINT, mensaje VARCHAR, fecha TIMESTAMP
    )
    """
    _exec_many(conn, ddl)
    _create_extended_tables(conn)

    conn.execute(
        """
        CREATE OR REPLACE VIEW vista_resumen_financiero AS
        SELECT
          CAST(SUM(CASE WHEN pc.tipo = 'ingreso' THEN al.haber - al.debe ELSE 0 END) AS DECIMAL(12,2)) AS ingresos,
          CAST(SUM(CASE WHEN pc.tipo = 'costo' THEN al.debe - al.haber ELSE 0 END) AS DECIMAL(12,2)) AS costos,
          CAST(
            SUM(CASE WHEN pc.tipo = 'ingreso' THEN al.haber - al.debe ELSE 0 END)
            - SUM(CASE WHEN pc.tipo = 'costo' THEN al.debe - al.haber ELSE 0 END)
          AS DECIMAL(12,2)) AS margen
        FROM asiento_lineas al
        JOIN plan_cuentas pc ON pc.id_cuenta = al.id_cuenta
        """
    )


def _seed_base(conn) -> None:
    conn.execute(
        """
        INSERT INTO roles (nombre, descripcion)
        SELECT 'admin', 'Administrador del sistema'
        WHERE NOT EXISTS (SELECT 1 FROM roles WHERE nombre = 'admin')
        """
    )
    conn.execute(
        """
        INSERT INTO roles (nombre, descripcion)
        SELECT 'cliente', 'Cliente B2B'
        WHERE NOT EXISTS (SELECT 1 FROM roles WHERE nombre = 'cliente')
        """
    )
    conn.execute(
        """
        INSERT INTO monedas (id_moneda, codigo, simbolo, nombre)
        SELECT 1, 'USD', '$', 'Dólar estadounidense'
        WHERE NOT EXISTS (SELECT 1 FROM monedas WHERE codigo = 'USD')
        """
    )
    conn.execute(
        """
        INSERT INTO metodos_pago (id_metodo, nombre, activo)
        SELECT 1, 'simulado', true
        WHERE NOT EXISTS (SELECT 1 FROM metodos_pago WHERE nombre = 'simulado')
        """
    )
    for mid, nombre in ((2, "tarjeta"), (3, "transferencia"), (4, "credito_interno")):
        conn.execute(
            """
            INSERT INTO metodos_pago (id_metodo, nombre, activo)
            SELECT ?, ?, true
            WHERE NOT EXISTS (SELECT 1 FROM metodos_pago WHERE lower(nombre) = lower(?))
            """,
            [mid, nombre, nombre],
        )
    conn.execute(
        """
        INSERT INTO almacenes (nombre, direccion, activo)
        SELECT 'Almacén Central', 'Principal', true
        WHERE NOT EXISTS (SELECT 1 FROM almacenes WHERE nombre = 'Almacén Central')
        """
    )
    # Países de la región South America (id_region = 8) que faltan en dim_country.
    paises_sudamerica = [
        "Argentina", "Bolivia", "Brazil", "Chile", "Colombia",
        "Guyana", "Paraguay", "Peru", "Suriname", "Uruguay", "Venezuela",
    ]
    for nombre_pais in paises_sudamerica:
        conn.execute(
            """
            INSERT INTO dim_country (id_country, country, id_region)
            SELECT COALESCE((SELECT MAX(id_country) FROM dim_country), 0) + 1, ?, 8
            WHERE NOT EXISTS (SELECT 1 FROM dim_country WHERE country = ? AND id_region = 8)
            """,
            [nombre_pais, nombre_pais],
        )
    # Una bodega por región. La existencia se verifica por región y no por
    # nombre: las bodegas se renombran/traducen en migraciones posteriores y
    # comparar por nombre volvía a insertar duplicados en cada arranque.
    for id_cod, nombre_reg in conn.execute(
        "SELECT id_region, region FROM dim_region ORDER BY id_region"
    ).fetchall():
        conn.execute(
            """
            INSERT INTO almacenes (nombre, direccion, id_region, activo)
            SELECT ?, 'Principal', ?, true
            WHERE NOT EXISTS (
              SELECT 1 FROM almacenes
              WHERE id_region = ? AND lower(nombre) NOT LIKE 'hub %'
            )
            """,
            [f"Bodega {nombre_reg}", int(id_cod), int(id_cod)],
        )
    cuentas = [
        (1, "1101", "Caja", "activo"),
        (2, "1201", "Cuentas por cobrar", "activo"),
        (3, "4101", "Ingresos por ventas", "ingreso"),
        (4, "5101", "Costo de ventas", "costo"),
        (5, "1301", "Inventario", "activo"),
        (6, "2002", "Cuentas por pagar a proveedores", "pasivo"),
        (7, "3001", "Pagos externos (financiamiento)", "pasivo"),
        (8, "2101", "IVA débito fiscal", "pasivo"),
        (9, "2102", "IVA crédito fiscal", "activo"),
        (10, "4102", "Ventas netas", "ingreso"),
    ]
    for cid, codigo, nombre, tipo in cuentas:
        conn.execute(
            """
            INSERT INTO plan_cuentas (id_cuenta, codigo, nombre, tipo)
            SELECT ?, ?, ?, ?
            WHERE NOT EXISTS (SELECT 1 FROM plan_cuentas WHERE codigo = ?)
            """,
            [cid, codigo, nombre, tipo, codigo],
        )
    conn.execute(
        """
        INSERT INTO listas_precios (nombre, id_moneda, activo)
        SELECT 'Público', 1, true
        WHERE NOT EXISTS (SELECT 1 FROM listas_precios WHERE nombre = 'Público')
        """
    )
    conn.execute(
        """
        INSERT INTO listas_precios (nombre, id_moneda, activo)
        SELECT 'Mayorista', 1, true
        WHERE NOT EXISTS (SELECT 1 FROM listas_precios WHERE nombre = 'Mayorista')
        """
    )
    conn.execute(
        """
        INSERT INTO configuracion_sistema (clave, valor, descripcion)
        SELECT 'IVA_PCT', '18', 'Porcentaje de IVA'
        WHERE NOT EXISTS (SELECT 1 FROM configuracion_sistema WHERE clave = 'IVA_PCT')
        """
    )
    for clave, valor, desc in [
        ("MOQ_MAYORISTA", "10", "Cantidad mínima para precio mayorista"),
        ("EMPRESA_NOMBRE", "GLOBTRADE S.A.", "Nombre en comprobantes y reportes"),
        ("EMPRESA_TAGLINE", "Comercio internacional · Distribución B2B", "Subtítulo en documentos PDF"),
        ("EMPRESA_LOGO", "", "Logo en comprobantes PDF (ruta uploads/empresa/…)"),
    ]:
        conn.execute(
            """
            INSERT INTO configuracion_sistema (clave, valor, descripcion)
            SELECT ?, ?, ?
            WHERE NOT EXISTS (SELECT 1 FROM configuracion_sistema WHERE clave = ?)
            """,
            [clave, valor, desc, clave],
        )
    conn.execute(
        """
        INSERT INTO usuarios (email, password_hash, rol, activo)
        SELECT ?, ?, 'admin', true
        WHERE NOT EXISTS (SELECT 1 FROM usuarios WHERE email = ?)
        """,
        ["admin@globmarket.com", _hash_password(DEMO_PASSWORD), "admin@globmarket.com"],
    )
    for email, pwd, rol in [
        ("compras@walmart.com", DEMO_PASSWORD, "cliente"),
        ("procurement@carrefour.com", DEMO_PASSWORD, "cliente"),
        ("sourcing@costco.com", DEMO_PASSWORD, "cliente"),
    ]:
        conn.execute(
            """
            INSERT INTO usuarios (email, password_hash, rol, activo)
            SELECT ?, ?, ?, true
            WHERE NOT EXISTS (SELECT 1 FROM usuarios WHERE email = ?)
            """,
            [email, _hash_password(pwd), rol, email],
        )
        conn.execute(
            "UPDATE usuarios SET password_hash = ? WHERE email = ?",
            [_hash_password(DEMO_PASSWORD), email],
        )


def _seed_categorias_from_item_types(conn) -> None:
    """Solo crea categorías faltantes; no reactiva las desactivadas a propósito."""
    conn.execute(
        """
        INSERT INTO categorias (nombre, slug, descripcion, activo, id_item_type)
        SELECT item_type, lower(replace(item_type, ' ', '-')), item_type, true, id_item_type
        FROM dim_item_type dit
        WHERE NOT EXISTS (
          SELECT 1 FROM categorias c WHERE c.id_item_type = dit.id_item_type
        )
        """
    )
    # Si ya existe desactivada, no la toca (el portal filtra activo=true).



def _seed_dim_clientes(conn) -> None:
    seeds = [
        ("compras@walmart.com", "Walmart Inc.", "United States", "+1 479-273-4000", "702 SW 8th St"),
        ("procurement@carrefour.com", "Carrefour S.A.", "France", "+33 1 64 50 50 50", "93 Avenue de Paris"),
        ("sourcing@costco.com", "Costco Wholesale", "United States", "+1 425-313-8100", "999 Lake Dr, Issaquah, WA"),
    ]
    for email, nombre, pais, tel, dir_ in seeds:
        row = conn.execute("SELECT id_usuario FROM usuarios WHERE email = ?", [email]).fetchone()
        if not row:
            continue
        uid = int(row[0])
        conn.execute(
            """
            INSERT INTO dim_cliente (id_usuario, nombre_empresa, pais, telefono, direccion)
            SELECT ?, ?, ?, ?, ?
            WHERE NOT EXISTS (SELECT 1 FROM dim_cliente WHERE id_usuario = ?)
            """,
            [uid, nombre, pais, tel, dir_, uid],
        )


def _seed_productos_demo(conn) -> None:
    seed_marcas(conn)
    seed_catalogo_demo(conn)
    reparar_imagenes_desde_storage(conn, repo_root() / "shared" / "storage")


def _seed_stock_inicial(conn) -> None:
    """Da stock inicial (500 u.) a productos demo sin fila en stock_almacen."""
    conn.execute(
        """
        INSERT INTO stock_almacen (id_stock, id_producto, id_almacen, cantidad_disponible, cantidad_reservada)
        SELECT (SELECT COALESCE(MAX(id_stock), 0) FROM stock_almacen) + row_number() OVER (),
               p.id_producto, 1, 500, 0
        FROM dim_producto p
        WHERE p.activo = true
          AND NOT EXISTS (
            SELECT 1 FROM stock_almacen sa
            WHERE sa.id_producto = p.id_producto AND sa.id_almacen = 1
          )
        """
    )


def _seed_roles_staff(conn) -> None:
    sincronizar_roles_staff(conn)


from shared.database.permisos_catalogo import (
    PERMISOS_CATALOGO,
    ROLES_PERMISOS_DEFAULT,
    ROLES_STAFF_DEFAULT,
    sincronizar_permisos_catalogo,
    sincronizar_roles_permisos_default,
    sincronizar_roles_staff,
)


def _seed_permisos(conn) -> None:
    """Permisos de módulo + asignación por defecto a cada rol (rol_permiso)."""
    sincronizar_permisos_catalogo(conn)
    for rol, codigos in ROLES_PERMISOS_DEFAULT.items():
        if rol == "admin":
            continue
        for codigo in codigos:
            conn.execute(
                """
                INSERT INTO rol_permiso (id_rol, id_permiso)
                SELECT r.id_rol, p.id_permiso
                FROM roles r, permisos p
                WHERE r.nombre = ? AND p.codigo = ?
                  AND NOT EXISTS (
                    SELECT 1 FROM rol_permiso rp
                    WHERE rp.id_rol = r.id_rol AND rp.id_permiso = p.id_permiso
                  )
                """,
                [rol, codigo],
            )


def _seed_logistica_marketing(conn) -> None:
    # Seed canónico lo aplica migrate_reestructuracion._seed_logistica_macro_zonas
    if table_exists(conn, "banners_portal"):
        conn.execute(
            """
            INSERT INTO banners_portal (id_banner, titulo, imagen_path, enlace, activo, orden)
            SELECT 1, 'Catálogo FMCG', 'uploads/banners/fmcg.jpg', '/pages/catalogo.html', true, 1
            WHERE NOT EXISTS (SELECT 1 FROM banners_portal WHERE id_banner = 1)
            """
        )
        conn.execute(
            """
            INSERT INTO banners_portal (id_banner, titulo, imagen_path, enlace, activo, orden)
            SELECT 2, 'Envíos por regiones', NULL, '/pages/registro.html', true, 2
            WHERE NOT EXISTS (SELECT 1 FROM banners_portal WHERE id_banner = 2)
            """
        )
    if table_exists(conn, "promociones"):
        conn.execute(
            """
            INSERT INTO promociones (id_promocion, nombre, descuento_pct, fecha_inicio, fecha_fin, activa)
            SELECT 1, 'Bienvenida B2B', 5.00, current_date, current_date + INTERVAL 90 DAY, true
            WHERE NOT EXISTS (SELECT 1 FROM promociones WHERE id_promocion = 1)
            """
        )


def _create_catalogos_tables(conn: duckdb.DuckDBPyConnection) -> None:
    """Tablas de catálogos/paquetes configurables (compra por catálogo)."""
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS catalogos (
            id_catalogo INTEGER PRIMARY KEY,
            nombre VARCHAR NOT NULL,
            descripcion VARCHAR,
            id_item_type BIGINT NOT NULL,
            imagen_path VARCHAR,
            activo BOOLEAN DEFAULT true
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS catalogo_detalle (
            id_catalogo BIGINT NOT NULL,
            id_producto BIGINT NOT NULL,
            cantidad_base INTEGER DEFAULT 10,
            precio_unitario DOUBLE,
            PRIMARY KEY (id_catalogo, id_producto)
        )
        """
    )


def _seed_catalogos(conn: duckdb.DuckDBPyConnection) -> None:
    """Crea un catálogo/paquete por tipo de producto con 10 uds. de cada producto activo."""
    if not table_exists(conn, "catalogos"):
        return
    tipos = conn.execute(
        """
        SELECT DISTINCT it.id_item_type, it.item_type
        FROM dim_item_type it
        JOIN dim_producto p ON p.id_item_type = it.id_item_type AND COALESCE(p.activo, true) = true
        """
    ).fetchall()
    for id_item_type, item_type in tipos:
        conn.execute(
            """
            INSERT INTO catalogos (id_catalogo, nombre, descripcion, id_item_type, activo)
            SELECT COALESCE((SELECT MAX(id_catalogo) FROM catalogos), 0) + 1, ?, ?, ?, true
            WHERE NOT EXISTS (SELECT 1 FROM catalogos WHERE id_item_type = ?)
            """,
            [
                str(item_type),
                f"Paquete {item_type}: 10 unidades de cada producto. Configura las cantidades a tu medida.",
                int(id_item_type),
                int(id_item_type),
            ],
        )
        id_catalogo = conn.execute(
            "SELECT id_catalogo FROM catalogos WHERE id_item_type = ? LIMIT 1", [int(id_item_type)]
        ).fetchone()[0]
        conn.execute(
            """
            INSERT INTO catalogo_detalle (id_catalogo, id_producto, cantidad_base, precio_unitario)
            SELECT ?, p.id_producto, 10, CAST(p.precio_mayorista AS DOUBLE)
            FROM dim_producto p
            WHERE p.id_item_type = ? AND COALESCE(p.activo, true) = true
              AND NOT EXISTS (
                  SELECT 1 FROM catalogo_detalle d
                  WHERE d.id_catalogo = ? AND d.id_producto = p.id_producto
              )
            """,
            [int(id_catalogo), int(id_item_type), int(id_catalogo)],
        )


def _create_estrategia_tables(conn) -> None:
    """Tablas del módulo estratégico: objetivos (cuadro de mando) y riesgos."""
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS objetivos_estrategicos (
          id_objetivo BIGINT PRIMARY KEY,
          nombre VARCHAR NOT NULL,
          descripcion VARCHAR,
          tipo_metrica VARCHAR NOT NULL,
          meta_numerica DOUBLE NOT NULL,
          periodo VARCHAR,
          orden INTEGER DEFAULT 0,
          activo BOOLEAN DEFAULT true
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS riesgos_estrategicos (
          id_riesgo BIGINT PRIMARY KEY,
          nombre VARCHAR NOT NULL,
          descripcion VARCHAR,
          probabilidad INTEGER NOT NULL,
          impacto INTEGER NOT NULL,
          mitigacion VARCHAR,
          id_objetivo BIGINT,
          estado VARCHAR DEFAULT 'activo'
        )
        """
    )


def _seed_estrategia(conn) -> None:
    """Objetivos y riesgos estratégicos de ejemplo (idempotente y tolerante a
    arranques concurrentes: si otro worker ya insertó, se omite)."""
    objetivos = [
        ("Superar los 210 mil millones de dólares en ingresos", "ingresos", 210_000_000_000.0,
         "Crecimiento de ingresos consolidado del grupo", "2026", 1),
        ("Alcanzar un margen bruto del 30%", "margen_pct", 30.0,
         "Eficiencia en costos de adquisición y precios B2B", "2026", 2),
        ("Generar 65 mil millones de dólares de profit", "profit", 65_000_000_000.0,
         "Rentabilidad acumulada del período", "2026", 3),
        ("Vender 850 millones de unidades", "unidades", 850_000_000.0,
         "Volumen comercializado por los canales mayoristas", "2026", 4),
        ("Atender 190 países", "paises", 190.0,
         "Ampliación de cobertura geográfica de la distribución", "2026", 5),
        ("Sumar el décimo cliente mayorista", "clientes", 10.0,
         "Cartera de clientes B2B de alto volumen", "2026", 6),
    ]
    for nombre, tipo, meta, descripcion, periodo, orden in objetivos:
        try:
            conn.execute(
                """
                INSERT INTO objetivos_estrategicos
                  (id_objetivo, nombre, descripcion, tipo_metrica, meta_numerica, periodo, orden, activo)
                SELECT ?, ?, ?, ?, ?, ?, ?, true
                WHERE NOT EXISTS (SELECT 1 FROM objetivos_estrategicos WHERE nombre = ?)
                """,
                [orden, nombre, descripcion, tipo, meta, periodo, orden, nombre],
            )
        except duckdb.ConstraintException:
            pass
    riesgos = [
        ("Concentración geográfica de ingresos", "Si los mercados principales se concentran en pocos países, una crisis regional golpea el portafolio.", 3, 4,
         "Diversificar la red de distribución hacia mercados emergentes con menor correlación.", None),
        ("Dependencia de clientes mayoristas clave", "Walmart, Costco y Carrefour concentran un alto volumen de pedidos B2B.", 4, 3,
         "Ampliar la cartera a medianas cadenas y marketplaces regionales.", None),
        ("Volatilidad del costo de adquisición", "Cambios en los costos de compra erosionan el margen bruto (objetivo 30%).", 3, 3,
         "Negociar contratos de suministro a largo plazo y diversificar proveedores.", 2),
        ("Desabastecimiento de categorías top", "Interrupciones logísticas en categorías de alto ingreso frenan el crecimiento.", 2, 4,
         "Stock de seguridad por almacén y alertas tempranas de umbral mínimo.", 4),
        ("Riesgo cambiario en mercados internacionales", "Las ventas en 186 países exponen el portafolio a fluctuaciones cambiarias.", 2, 2,
         "Coberturas cambiarias y precios en USD para contratos B2B.", None),
    ]
    for i, (nombre, descripcion, prob, imp, mitigacion, id_objetivo) in enumerate(riesgos, start=1):
        try:
            conn.execute(
                """
                INSERT INTO riesgos_estrategicos
                  (id_riesgo, nombre, descripcion, probabilidad, impacto, mitigacion, id_objetivo, estado)
                SELECT ?, ?, ?, ?, ?, ?, ?, 'activo'
                WHERE NOT EXISTS (SELECT 1 FROM riesgos_estrategicos WHERE nombre = ?)
                """,
                [i, nombre, descripcion, prob, imp, mitigacion, id_objetivo, nombre],
            )
        except duckdb.ConstraintException:
            pass


def run_init(parquet_path: Path | None = None, duckdb_path: Path | None = None) -> None:
    root = repo_root()
    db_path = duckdb_path or resolve_duckdb_path()
    pq = parquet_path or (root / "data" / "ventas.parquet")

    conn = duckdb.connect(str(db_path))
    try:
        _ensure_sequences(conn)
        _load_star_schema_if_empty(conn, pq)
        _extend_fact_ventas(conn)
        _create_legacy_b2b_tables(conn)
        _extend_usuarios(conn)
        _extend_pedidos(conn)
        _create_erp_tables(conn)
        _extend_maestras_region(conn)
        _create_views(conn)
        _create_catalogos_tables(conn)
        _seed_base(conn)
        _seed_roles_staff(conn)
        _seed_permisos(conn)
        _seed_usuarios_staff(conn)
        _seed_categorias_from_item_types(conn)
        _seed_dim_clientes(conn)
        _seed_productos_demo(conn)
        _seed_stock_inicial(conn)
        _seed_catalogos(conn)
        _seed_logistica_marketing(conn)
        _create_estrategia_tables(conn)
        _seed_estrategia(conn)
        from shared.database.migrate_reestructuracion import aplicar_migraciones_reestructuracion

        aplicar_migraciones_reestructuracion(conn)

        from shared.database.seed_listas_precios import seed_listas_precios

        try:
            msg = seed_listas_precios(conn)
            print(f"[init] listas_precios: {msg}")
        except Exception as exc:
            print(f"[init] listas_precios omitido: {exc}")

        tables = conn.execute(
            "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = 'main' AND table_type = 'BASE TABLE'"
        ).fetchone()[0]
        ventas = conn.execute("SELECT COUNT(*) FROM fact_ventas").fetchone()[0]
        print(f"[init] OK — {tables} tablas, {ventas} filas en fact_ventas, DB: {db_path}")
    finally:
        conn.close()


def main() -> None:
    try:
        run_init()
    except Exception as exc:
        print(f"[init] ERROR: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
