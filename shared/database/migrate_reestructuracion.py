"""
Migraciones idempotentes para la reestructuración GlobalTradeSA.
Se ejecutan en cada arranque vía init_sistema / main lifespan.
"""
from __future__ import annotations


def _column_exists(conn, table: str, column: str) -> bool:
    rows = conn.execute(
        """
        SELECT 1 FROM information_schema.columns
        WHERE table_name = ? AND column_name = ?
        """,
        [table, column],
    ).fetchall()
    return bool(rows)


def _table_exists(conn, table: str) -> bool:
    rows = conn.execute(
        "SELECT 1 FROM information_schema.tables WHERE table_name = ?",
        [table],
    ).fetchall()
    return bool(rows)


def aplicar_migraciones_reestructuracion(conn) -> None:
    """DDL incremental: líneas, marcas en dim_producto, descuentos, config, wishlist."""

    conn.execute(
        """
        CREATE SEQUENCE IF NOT EXISTS seq_lineas START 1;
        CREATE TABLE IF NOT EXISTS lineas_producto (
          id_linea BIGINT PRIMARY KEY DEFAULT nextval('seq_lineas'),
          nombre VARCHAR NOT NULL,
          id_marca BIGINT,
          activo BOOLEAN DEFAULT true,
          descripcion VARCHAR
        )
        """
    )

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS descuentos_producto (
          id_descuento BIGINT PRIMARY KEY,
          id_producto BIGINT,
          id_item_type BIGINT,
          id_cliente BIGINT,
          descuento_pct DECIMAL(5,2) NOT NULL,
          fecha_inicio DATE,
          fecha_fin DATE,
          activo BOOLEAN DEFAULT true,
          motivo VARCHAR
        )
        """
    )

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS cliente_direcciones_extra (
          id_direccion BIGINT PRIMARY KEY,
          id_cliente BIGINT NOT NULL,
          alias VARCHAR,
          direccion VARCHAR NOT NULL,
          ciudad VARCHAR,
          pais VARCHAR,
          es_principal BOOLEAN DEFAULT false,
          activo BOOLEAN DEFAULT true,
          tipo VARCHAR DEFAULT 'envio'
        )
        """
    )
    if not _column_exists(conn, "cliente_direcciones_extra", "tipo"):
        conn.execute("ALTER TABLE cliente_direcciones_extra ADD COLUMN tipo VARCHAR DEFAULT 'envio'")

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS cliente_preferencias (
          id_cliente BIGINT PRIMARY KEY,
          preferencias_json VARCHAR
        )
        """
    )
    if not _column_exists(conn, "dim_producto", "stock_minimo"):
        conn.execute("ALTER TABLE dim_producto ADD COLUMN stock_minimo DECIMAL(12,4) DEFAULT 10")

    # Soft-fix residual: categorías recreadas por seed tras borrado duro (caso peperoni, etc.)
    # No reactivar; si el admin las necesita, las activa manualmente.
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS notificaciones (
          id_notif BIGINT PRIMARY KEY,
          id_usuario BIGINT NOT NULL,
          titulo VARCHAR NOT NULL,
          cuerpo VARCHAR,
          tipo VARCHAR DEFAULT 'info',
          link VARCHAR,
          leida BOOLEAN DEFAULT false,
          fecha TIMESTAMP DEFAULT current_timestamp
        )
        """
    )

    for codigo, nombre, tipo in [
        ("2101", "IVA débito fiscal", "pasivo"),
        ("2102", "IVA crédito fiscal", "activo"),
        ("4102", "Ventas netas", "ingreso"),
    ]:
        conn.execute(
            """
            INSERT INTO plan_cuentas (id_cuenta, codigo, nombre, tipo)
            SELECT (SELECT COALESCE(MAX(id_cuenta), 0) + 1 FROM plan_cuentas), ?, ?, ?
            WHERE NOT EXISTS (SELECT 1 FROM plan_cuentas WHERE codigo = ?)
            """,
            [codigo, nombre, tipo, codigo],
        )

    # Categorías residuales recreadas por seed tras borrado duro (ej. peperoni)
    try:
        conn.execute(
            """
            UPDATE categorias SET activo = false
            WHERE activo = true AND (
              lower(nombre) LIKE '%peperoni%' OR lower(COALESCE(slug,'')) LIKE '%peperoni%'
              OR lower(nombre) LIKE '%pepperoni%' OR lower(COALESCE(slug,'')) LIKE '%pepperoni%'
            )
            """
        )
    except Exception:
        pass

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS wishlist (
          id_wishlist BIGINT PRIMARY KEY,
          id_usuario BIGINT NOT NULL,
          id_producto BIGINT NOT NULL,
          fecha TIMESTAMP DEFAULT current_timestamp,
          UNIQUE(id_usuario, id_producto)
        )
        """
    )

    cols_dim = [
        ("id_marca", "BIGINT"),
        ("id_linea", "BIGINT"),
        ("sku", "VARCHAR"),
        ("descuento_pct", "DECIMAL(5,2) DEFAULT 0"),
        ("precio_rebajado", "DECIMAL(10,2)"),
        ("fecha_rebaja_hasta", "DATE"),
        ("descuento_aplica_a", "VARCHAR DEFAULT 'mayorista'"),
    ]
    for col, typ in cols_dim:
        if not _column_exists(conn, "dim_producto", col):
            conn.execute(f"ALTER TABLE dim_producto ADD COLUMN {col} {typ}")

    if not _column_exists(conn, "pagos", "ref_transaccion"):
        conn.execute("ALTER TABLE pagos ADD COLUMN ref_transaccion VARCHAR")
    if not _column_exists(conn, "pagos", "ultimos_digitos"):
        conn.execute("ALTER TABLE pagos ADD COLUMN ultimos_digitos VARCHAR(4)")
    if not _column_exists(conn, "pagos", "estado_simulacion"):
        conn.execute("ALTER TABLE pagos ADD COLUMN estado_simulacion VARCHAR DEFAULT 'aprobado'")

    if not _column_exists(conn, "pedidos", "costo_envio"):
        conn.execute("ALTER TABLE pedidos ADD COLUMN costo_envio DECIMAL(10,2) DEFAULT 0")
    if not _column_exists(conn, "pedidos", "contabilidad_pendiente"):
        conn.execute("ALTER TABLE pedidos ADD COLUMN contabilidad_pendiente BOOLEAN DEFAULT false")

    # Vista unificada productos ERP sobre dim_producto
    conn.execute(
        """
        CREATE OR REPLACE VIEW vista_productos_unificados AS
        SELECT
          dp.id_producto,
          COALESCE(dp.sku, 'GM-' || LPAD(CAST(dp.id_producto AS VARCHAR), 6, '0')) AS sku,
          dp.nombre_producto AS nombre,
          dp.descripcion,
          dp.id_item_type AS id_categoria,
          dp.id_marca,
          dp.id_linea,
          dp.precio_unitario,
          dp.precio_mayorista,
          dp.precio_rebajado,
          dp.descuento_pct,
          dp.imagen_url,
          dp.activo,
          m.nombre AS marca,
          l.nombre AS linea
        FROM dim_producto dp
        LEFT JOIN marcas m ON m.id_marca = dp.id_marca
        LEFT JOIN lineas_producto l ON l.id_linea = dp.id_linea
        """
    )

    config_defaults = [
        ("PAGO_SIM_TASA_EXITO", "95", "Porcentaje de éxito en pago simulado (0-100)"),
        ("PAGO_SIM_METODOS", "tarjeta,transferencia,credito_interno", "Métodos de pago simulados habilitados"),
        ("UMBRAL_STOCK_BAJO", "10", "Umbral global de stock bajo"),
        ("DIAS_CREDITO_DEFAULT", "30", "Días de crédito por defecto B2B"),
        ("SERIE_FACTURA", "FAC", "Prefijo serie facturas"),
        ("SERIE_PEDIDO", "PED", "Prefijo serie pedidos"),
        ("SERIE_COMPROBANTE", "PAG", "Prefijo comprobantes de pago"),
        ("ENVIO_GRATIS_MINIMO", "500", "Monto mínimo para envío gratis (USD)"),
        ("CLICKHOUSE_SYNC_AUTO", "true", "Sincronizar ClickHouse tras ETL"),
        (
            "FULFILLMENT_CROSS_ZONA",
            "0",
            "1 = permitir servir un pedido desde otra macro-zona cuando la del cliente no tiene stock",
        ),
        (
            "STOCK_OBJETIVO_HUB",
            "600",
            "Unidades objetivo por producto en cada hub regional al rebalancear",
        ),
        (
            "STOCK_OBJETIVO_SATELITE",
            "150",
            "Unidades objetivo por producto en cada bodega satélite al rebalancear",
        ),
    ]
    for clave, valor, desc in config_defaults:
        conn.execute(
            """
            INSERT INTO configuracion_sistema (clave, valor, descripcion)
            SELECT ?, ?, ?
            WHERE NOT EXISTS (SELECT 1 FROM configuracion_sistema WHERE clave = ?)
            """,
            [clave, valor, desc, clave],
        )

    if _table_exists(conn, "metodos_pago"):
        for nombre in ("tarjeta", "transferencia", "credito_interno", "simulado"):
            conn.execute(
                """
                INSERT INTO metodos_pago (id_metodo, nombre, activo)
                SELECT (SELECT COALESCE(MAX(id_metodo), 0) + 1 FROM metodos_pago), ?, true
                WHERE NOT EXISTS (SELECT 1 FROM metodos_pago WHERE lower(nombre) = lower(?))
                """,
                [nombre, nombre],
            )

    # Seed marcas / líneas y asignar a productos demo sin línea
    conn.execute(
        """
        INSERT INTO marcas (id_marca, nombre, activo)
        SELECT (SELECT COALESCE(MAX(id_marca), 0) + 1 FROM marcas), 'GlobTrade Select', true
        WHERE NOT EXISTS (SELECT 1 FROM marcas WHERE nombre = 'GlobTrade Select')
        """
    )
    conn.execute(
        """
        INSERT INTO marcas (id_marca, nombre, activo)
        SELECT (SELECT COALESCE(MAX(id_marca), 0) + 1 FROM marcas), 'Pacific Trade', true
        WHERE NOT EXISTS (SELECT 1 FROM marcas WHERE nombre = 'Pacific Trade')
        """
    )
    conn.execute(
        """
        INSERT INTO lineas_producto (id_linea, nombre, id_marca, activo, descripcion)
        SELECT (SELECT COALESCE(MAX(id_linea), 0) + 1 FROM lineas_producto), 'Línea Premium',
               (SELECT id_marca FROM marcas WHERE nombre = 'GlobTrade Select' LIMIT 1), true, 'Productos premium B2B'
        WHERE NOT EXISTS (SELECT 1 FROM lineas_producto WHERE nombre = 'Línea Premium')
        """
    )
    conn.execute(
        """
        INSERT INTO lineas_producto (id_linea, nombre, id_marca, activo, descripcion)
        SELECT (SELECT COALESCE(MAX(id_linea), 0) + 1 FROM lineas_producto), 'Línea Estándar',
               (SELECT id_marca FROM marcas WHERE nombre = 'Pacific Trade' LIMIT 1), true, 'Catálogo estándar'
        WHERE NOT EXISTS (SELECT 1 FROM lineas_producto WHERE nombre = 'Línea Estándar')
        """
    )
    conn.execute(
        """
        UPDATE dim_producto SET
          id_marca = COALESCE(id_marca, (SELECT id_marca FROM marcas WHERE nombre = 'GlobTrade Select' LIMIT 1)),
          id_linea = COALESCE(id_linea, (SELECT id_linea FROM lineas_producto WHERE nombre = 'Línea Premium' LIMIT 1)),
          sku = COALESCE(sku, 'GM-' || LPAD(CAST(id_producto AS VARCHAR), 6, '0'))
        WHERE id_marca IS NULL OR id_linea IS NULL OR sku IS NULL
        """
    )

    conn.execute(
        """
        INSERT INTO plan_cuentas (id_cuenta, codigo, nombre, tipo)
        SELECT (SELECT COALESCE(MAX(id_cuenta), 0) + 1 FROM plan_cuentas), '2101', 'IVA débito fiscal', 'pasivo'
        WHERE NOT EXISTS (SELECT 1 FROM plan_cuentas WHERE codigo = '2101')
        """
    )
    conn.execute(
        """
        INSERT INTO plan_cuentas (id_cuenta, codigo, nombre, tipo)
        SELECT (SELECT COALESCE(MAX(id_cuenta), 0) + 1 FROM plan_cuentas), '2102', 'IVA crédito fiscal', 'activo'
        WHERE NOT EXISTS (SELECT 1 FROM plan_cuentas WHERE codigo = '2102')
        """
    )
    conn.execute(
        """
        INSERT INTO plan_cuentas (id_cuenta, codigo, nombre, tipo)
        SELECT (SELECT COALESCE(MAX(id_cuenta), 0) + 1 FROM plan_cuentas), '4102', 'Ventas netas', 'ingreso'
        WHERE NOT EXISTS (SELECT 1 FROM plan_cuentas WHERE codigo = '4102')
        """
    )

    _seed_logistica_macro_zonas(conn)
    _migrar_descuentos_jerarquicos(conn)
    _migrar_favoritos_paquetes(conn)
    _migrar_red_bodegas(conn)
    _distribuir_stock_red(conn)
    _seed_proveedores_regionales(conn)
    _seed_lineas_por_marca(conn)
    _migrar_maestras_mejoras(conn)

    # categorias con id_item_type sin fila en dim_item_type (p. ej. Tecnologia)
    conn.execute(
        """
        INSERT INTO dim_item_type (id_item_type, item_type, unit_price, unit_cost)
        SELECT c.id_item_type, c.nombre, 0, 0
        FROM categorias c
        LEFT JOIN dim_item_type d ON d.id_item_type = c.id_item_type
        WHERE c.id_item_type IS NOT NULL AND d.id_item_type IS NULL
        """
    )


def asegurar_lineas_marca(conn, id_marca: int, nombre_marca: str) -> None:
    """Garantiza al menos 2 líneas activas por marca."""
    if not _table_exists(conn, "lineas_producto"):
        return
    count = conn.execute(
        """
        SELECT COUNT(*) FROM lineas_producto
        WHERE id_marca = ? AND COALESCE(activo, true) = true
        """,
        [id_marca],
    ).fetchone()[0]
    if int(count or 0) >= 2:
        return
    plantillas = [
        ("Línea Premium", "Productos premium y mayor margen"),
        ("Línea Estándar", "Catálogo estándar de la marca"),
    ]
    for nombre_base, desc in plantillas:
        if int(count or 0) >= 2:
            break
        existe = conn.execute(
            """
            SELECT 1 FROM lineas_producto
            WHERE id_marca = ?
              AND (
                lower(nombre) = lower(?)
                OR lower(nombre) = lower(?)
                OR lower(nombre) LIKE lower(?)
              )
            LIMIT 1
            """,
            [id_marca, nombre_base, f"{nombre_base} — {nombre_marca}", f"{nombre_base}%"],
        ).fetchone()
        if existe:
            continue
        nombre = f"{nombre_base} — {nombre_marca}"
        dup = conn.execute(
            "SELECT 1 FROM lineas_producto WHERE lower(nombre) = lower(?)", [nombre]
        ).fetchone()
        if dup:
            nombre = f"{nombre_base} — {nombre_marca} ({id_marca})"
        nid = conn.execute("SELECT COALESCE(MAX(id_linea), 0) + 1 FROM lineas_producto").fetchone()[0]
        conn.execute(
            """
            INSERT INTO lineas_producto (id_linea, nombre, id_marca, activo, descripcion)
            VALUES (?, ?, ?, true, ?)
            """,
            [int(nid), nombre, id_marca, desc],
        )
        count = int(count or 0) + 1


def _seed_lineas_por_marca(conn) -> None:
    if not _table_exists(conn, "marcas") or not _table_exists(conn, "lineas_producto"):
        return
    rows = conn.execute(
        "SELECT id_marca, nombre FROM marcas WHERE COALESCE(activo, true) = true ORDER BY id_marca"
    ).fetchall()
    for id_marca, nombre in rows:
        asegurar_lineas_marca(conn, int(id_marca), str(nombre))


def _migrar_maestras_mejoras(conn) -> None:
    """Descripción en prioridades y países clave para la red comercial."""
    if _table_exists(conn, "dim_order_priority") and not _column_exists(conn, "dim_order_priority", "descripcion"):
        conn.execute("ALTER TABLE dim_order_priority ADD COLUMN descripcion VARCHAR")

    desc_por_codigo = {
        "C": "Crítica — máxima urgencia, atención inmediata",
        "H": "Alta — prioridad elevada",
        "M": "Media — plazo estándar",
        "L": "Baja — puede demorarse sin impacto grave",
    }
    if _table_exists(conn, "dim_order_priority"):
        for cod, desc in desc_por_codigo.items():
            conn.execute(
                """
                UPDATE dim_order_priority
                SET descripcion = ?
                WHERE UPPER(order_priority) = ? AND (descripcion IS NULL OR trim(descripcion) = '')
                """,
                [desc, cod],
            )

    # RUC duplicados en datos viejos: asignar RUC provisional único.
    if _table_exists(conn, "proveedores"):
        dups = conn.execute(
            """
            SELECT ruc FROM proveedores
            WHERE ruc IS NOT NULL AND trim(ruc) <> ''
            GROUP BY ruc HAVING COUNT(*) > 1
            """
        ).fetchall()
        for (ruc,) in dups:
            filas = conn.execute(
                """
                SELECT id_proveedor, razon_social FROM proveedores
                WHERE ruc = ? ORDER BY id_proveedor
                """,
                [ruc],
            ).fetchall()
            for id_prov, nombre in filas[1:]:
                nuevo = f"{ruc}-D{id_prov}"[:13]
                conn.execute(
                    "UPDATE proveedores SET ruc = ? WHERE id_proveedor = ?",
                    [nuevo, int(id_prov)],
                )

    # Países útiles para proveedores / clientes B2B por macro-zona (si faltan).
    if not _table_exists(conn, "dim_country"):
        return
    extras = [
        ("Ecuador", 8),
        ("Qatar", 5),
        ("Netherlands", 4),
        ("Hong Kong", 1),
        ("New Zealand", 2),
    ]
    for nombre, id_region in extras:
        conn.execute(
            """
            INSERT INTO dim_country (id_country, country, id_region)
            SELECT COALESCE((SELECT MAX(id_country) FROM dim_country), 0) + 1, ?, ?
            WHERE NOT EXISTS (
              SELECT 1 FROM dim_country WHERE lower(country) = lower(?)
            )
            """,
            [nombre, id_region, nombre],
        )

    # Corrige países sudamericanos mal asignados a otras regiones.
    conn.execute(
        """
        UPDATE dim_country SET id_region = 8
        WHERE lower(country) IN ('ecuador', 'peru', 'colombia', 'brazil', 'chile', 'argentina')
          AND id_region IS DISTINCT FROM 8
        """
    )


def _seed_proveedores_regionales(conn) -> None:
    """Proveedores por macro-zona para abastecer la red de bodegas regional."""
    if not _table_exists(conn, "proveedores"):
        return

    conn.execute(
        """
        UPDATE proveedores SET id_country = 194
        WHERE lower(razon_social) LIKE '%acme%'
          AND (id_country IS NULL OR id_country NOT IN (
            SELECT id_country FROM dim_country WHERE id_region IN (3, 6, 8)
          ))
        """
    )
    conn.execute(
        """
        UPDATE proveedores SET id_country = 191
        WHERE lower(razon_social) LIKE '%importador global%'
          AND (id_country IS NULL OR id_country = 1)
        """
    )

    catalogo = [
        ("Andes Supply SAC", "20123456789", 194),
        ("Atlântico Distribuidora Ltda", "12345678001", 189),
        ("Europa Handels GmbH", "12345678901", 57),
        ("Gulf Trade FZE", "98765432101", 176),
        ("Pacific Rim Supplies Pte", "20198765432", 146),
        ("Nippon Parts KK", "40123456789", 77),
    ]
    for razon, ruc, id_country in catalogo:
        conn.execute(
            """
            INSERT INTO proveedores (razon_social, ruc, id_country, activo)
            SELECT ?, ?, ?, true
            WHERE NOT EXISTS (
              SELECT 1 FROM proveedores WHERE lower(razon_social) = lower(?)
            )
            """,
            [razon, ruc, id_country, razon],
        )


def _migrar_descuentos_jerarquicos(conn) -> None:
    """Descuentos a nivel de categoría y de paquete, además del de producto."""
    cols_categoria = [
        ("descuento_pct", "DECIMAL(5,2) DEFAULT 0"),
        ("descuento_aplica_a", "VARCHAR DEFAULT 'mayorista'"),
        ("descuento_hasta", "DATE"),
        ("descuento_motivo", "VARCHAR"),
        ("descuento_publicado", "TIMESTAMP"),
    ]
    if _table_exists(conn, "categorias"):
        for col, typ in cols_categoria:
            if not _column_exists(conn, "categorias", col):
                conn.execute(f"ALTER TABLE categorias ADD COLUMN {col} {typ}")

    cols_catalogo = [
        ("descuento_pct", "DECIMAL(5,2) DEFAULT 0"),
        ("descuento_hasta", "DATE"),
        ("descuento_motivo", "VARCHAR"),
        ("descuento_publicado", "TIMESTAMP"),
    ]
    if _table_exists(conn, "catalogos"):
        for col, typ in cols_catalogo:
            if not _column_exists(conn, "catalogos", col):
                conn.execute(f"ALTER TABLE catalogos ADD COLUMN {col} {typ}")

    if _table_exists(conn, "dim_producto") and not _column_exists(conn, "dim_producto", "descuento_motivo"):
        conn.execute("ALTER TABLE dim_producto ADD COLUMN descuento_motivo VARCHAR")


def _migrar_favoritos_paquetes(conn) -> None:
    """Favoritos de paquetes, en paralelo a la wishlist de productos."""
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS wishlist_catalogos (
          id_wishlist BIGINT PRIMARY KEY,
          id_usuario BIGINT NOT NULL,
          id_catalogo BIGINT NOT NULL,
          fecha TIMESTAMP DEFAULT current_timestamp,
          UNIQUE(id_usuario, id_catalogo)
        )
        """
    )


# Región analítica (dataset histórico, en inglés) → macro-zona operativa y etiqueta ES
_REGION_MACRO = {1: "apac", 2: "apac", 3: "americas", 4: "emea", 5: "emea", 6: "americas", 7: "emea", 8: "americas"}
_REGION_ES = {
    1: "Asia",
    2: "Oceanía",
    3: "Centroamérica",
    4: "Europa",
    5: "Medio Oriente y Norte de África",
    6: "Norteamérica",
    7: "África Subsahariana",
    8: "Sudamérica",
}
# Hub por macro-zona: (nombre de bodega existente, código, id_region del hub)
_HUBS = {
    "americas": ("Almacén Central", "AMS-HUB", 8),
    "emea": ("Hub EMEA", "EMEA-HUB", 4),
    "apac": ("Hub APAC", "APAC-HUB", 1),
}


def _migrar_red_bodegas(conn) -> None:
    """Convierte el listado plano de almacenes en una red con hubs y satélites.

    Un hub por macro-zona concentra el inventario y las bodegas regionales
    actúan como satélites. `prioridad` define el orden de despacho dentro de
    la zona (menor = se sirve primero).
    """
    if not _table_exists(conn, "almacenes"):
        return

    for col, typ in [
        ("macro_zona", "VARCHAR"),
        ("es_hub", "BOOLEAN DEFAULT false"),
        ("prioridad", "INTEGER DEFAULT 50"),
        ("codigo", "VARCHAR"),
    ]:
        if not _column_exists(conn, "almacenes", col):
            conn.execute(f"ALTER TABLE almacenes ADD COLUMN {col} {typ}")

    # "Hub Américas" era redundante con el Almacén Central: fusionar su stock
    # en el central y retirarlo de la red para no duplicar el hub de la zona.
    dup = conn.execute(
        "SELECT id_almacen FROM almacenes WHERE lower(nombre) = 'hub américas' OR lower(nombre) = 'hub americas'"
    ).fetchone()
    if dup:
        id_dup = int(dup[0])
        if id_dup != 1:
            _fusionar_bodega(conn, origen=id_dup, destino=1)

    # Región y zona del Almacén Central (hub Américas)
    conn.execute(
        """
        UPDATE almacenes
        SET id_region = COALESCE(id_region, 8), macro_zona = 'americas',
            es_hub = true, prioridad = 0, codigo = 'AMS-HUB', activo = true
        WHERE lower(nombre) IN ('almacén central', 'almacen central')
        """
    )

    for macro, (nombre, codigo, id_region) in _HUBS.items():
        if macro == "americas":
            continue
        fila = conn.execute(
            "SELECT id_almacen FROM almacenes WHERE lower(nombre) = lower(?)", [nombre]
        ).fetchone()
        if fila:
            conn.execute(
                """
                UPDATE almacenes
                SET id_region = ?, macro_zona = ?, es_hub = true, prioridad = 0, codigo = ?, activo = true
                WHERE id_almacen = ?
                """,
                [id_region, macro, codigo, int(fila[0])],
            )

    # Antes de codificar la red, consolidar copias que dejaron seeds anteriores
    _purgar_bodegas_duplicadas(conn)

    # Bodegas satélite: zona derivada de su región analítica, nombre en español
    satelites = conn.execute(
        """
        SELECT id_almacen, id_region, nombre
        FROM almacenes
        WHERE COALESCE(es_hub, false) = false AND id_region IS NOT NULL
        ORDER BY id_almacen
        """
    ).fetchall()
    contador: dict[str, int] = {}
    for id_almacen, id_region, nombre in satelites:
        macro = _REGION_MACRO.get(int(id_region))
        if not macro:
            continue
        contador[macro] = contador.get(macro, 0) + 1
        prefijo = {"americas": "AMS", "emea": "EMEA", "apac": "APAC"}[macro]
        codigo = f"{prefijo}-{contador[macro]:02d}"
        region_es = _REGION_ES.get(int(id_region))
        # El nombre solo se normaliza si viene del seed (nombre de la región, en
        # inglés o español). Una bodega bautizada por el ERP conserva su nombre.
        actual = (nombre or "").strip()
        genericos = _nombres_seed_bodega(conn, int(id_region))
        nombre_nuevo = (
            f"Bodega {region_es}"
            if region_es and (actual.lower() in genericos or not actual)
            else actual
        )
        conn.execute(
            """
            UPDATE almacenes
            SET macro_zona = ?, es_hub = false, prioridad = 10, codigo = ?, nombre = ?
            WHERE id_almacen = ?
            """,
            [macro, codigo, nombre_nuevo, int(id_almacen)],
        )

    # Cualquier bodega sin región queda en Américas para no dejarla huérfana
    conn.execute(
        """
        UPDATE almacenes
        SET macro_zona = 'americas', id_region = COALESCE(id_region, 8), prioridad = COALESCE(prioridad, 50)
        WHERE macro_zona IS NULL
        """
    )


def _nombres_seed_bodega(conn, id_region: int) -> set[str]:
    """Nombres que el seed pudo dar a la bodega de una región (inglés y español)."""
    fila = conn.execute("SELECT region FROM dim_region WHERE id_region = ?", [id_region]).fetchone()
    region_en = (fila[0] if fila else None) or ""
    region_es = _REGION_ES.get(int(id_region), "")
    nombres = set()
    for base in (region_en, region_es):
        if base:
            nombres.add(f"bodega {base}".lower())
            nombres.add(base.lower())
    return nombres


def _purgar_bodegas_duplicadas(conn) -> None:
    """Consolida las bodegas satélite repetidas dentro de una misma región.

    El seed base crea una bodega por región y las migraciones las renombran al
    español, así que cada arranque podía insertar otra copia. Se conserva la
    bodega más antigua de la región; las copias generadas por el seed (nombre
    regional y dirección 'Principal') ceden su stock a la conservada y se
    eliminan. Las bodegas con nombre propio, creadas desde el ERP, se respetan.
    """
    if not _table_exists(conn, "almacenes"):
        return

    regiones = conn.execute(
        """
        SELECT id_region FROM almacenes
        WHERE id_region IS NOT NULL AND COALESCE(es_hub, false) = false
        GROUP BY id_region HAVING COUNT(*) > 1
        """
    ).fetchall()

    for (id_region,) in regiones:
        id_region = int(id_region)
        bodegas = conn.execute(
            """
            SELECT id_almacen, nombre, direccion
            FROM almacenes
            WHERE id_region = ? AND COALESCE(es_hub, false) = false
            ORDER BY id_almacen
            """,
            [id_region],
        ).fetchall()
        if len(bodegas) < 2:
            continue

        conservada = int(bodegas[0][0])
        nombres_seed = _nombres_seed_bodega(conn, id_region)
        for id_almacen, nombre, direccion in bodegas[1:]:
            id_almacen = int(id_almacen)
            es_del_seed = (nombre or "").strip().lower() in nombres_seed and (
                (direccion or "").strip().lower() in ("principal", "")
            )
            if not es_del_seed:
                continue
            _fusionar_bodega(conn, origen=id_almacen, destino=conservada)


def _fusionar_bodega(conn, *, origen: int, destino: int) -> None:
    """Traslada stock e historial de una bodega a otra y la elimina."""
    if _table_exists(conn, "stock_almacen"):
        conn.execute(
            """
            UPDATE stock_almacen SET cantidad_disponible = cantidad_disponible + COALESCE((
              SELECT SUM(o.cantidad_disponible) FROM stock_almacen o
              WHERE o.id_producto = stock_almacen.id_producto AND o.id_almacen = ?
            ), 0)
            WHERE id_almacen = ?
            """,
            [origen, destino],
        )
        # Productos que solo existían en la bodega origen: se reasignan.
        conn.execute(
            """
            UPDATE stock_almacen SET id_almacen = ?
            WHERE id_almacen = ?
              AND id_producto NOT IN (SELECT id_producto FROM stock_almacen WHERE id_almacen = ?)
            """,
            [destino, origen, destino],
        )
        conn.execute("DELETE FROM stock_almacen WHERE id_almacen = ?", [origen])
    if _table_exists(conn, "movimiento_inventario_detalle"):
        conn.execute(
            "UPDATE movimiento_inventario_detalle SET id_almacen = ? WHERE id_almacen = ?",
            [destino, origen],
        )
    if _table_exists(conn, "transferencias_almacen"):
        conn.execute(
            "UPDATE transferencias_almacen SET id_almacen_origen = ? WHERE id_almacen_origen = ?",
            [destino, origen],
        )
        conn.execute(
            "UPDATE transferencias_almacen SET id_almacen_destino = ? WHERE id_almacen_destino = ?",
            [destino, origen],
        )
        conn.execute(
            "DELETE FROM transferencias_almacen WHERE id_almacen_origen = id_almacen_destino"
        )
    conn.execute("DELETE FROM almacenes WHERE id_almacen = ?", [origen])


def _pesos_demanda_por_zona(conn) -> dict[str, float]:
    """Participación de demanda histórica por macro-zona (fallback razonable)."""
    base = {"americas": 0.40, "emea": 0.35, "apac": 0.25}
    if not _table_exists(conn, "fact_ventas"):
        return base
    try:
        rows = conn.execute(
            "SELECT id_region, SUM(units_sold) FROM fact_ventas GROUP BY id_region"
        ).fetchall()
    except Exception:
        return base
    acum = {"americas": 0.0, "emea": 0.0, "apac": 0.0}
    for id_region, units in rows:
        macro = _REGION_MACRO.get(int(id_region)) if id_region is not None else None
        if macro:
            acum[macro] += float(units or 0)
    total = sum(acum.values())
    if total <= 0:
        return base
    pesos = {k: v / total for k, v in acum.items()}
    # Piso del 15% por zona: ninguna región queda sin surtido operativo
    for k in pesos:
        pesos[k] = max(pesos[k], 0.15)
    suma = sum(pesos.values())
    return {k: v / suma for k, v in pesos.items()}


def _distribuir_stock_red(conn) -> None:
    """Surte las bodegas de cada macro-zona a partir del inventario existente.

    Idempotente: solo actúa sobre productos cuyo stock está concentrado en una
    sola zona (situación del seed original, que cargaba todo en el central).
    El reparto entre zonas sigue la demanda histórica; dentro de la zona, el
    hub retiene el 60% y los satélites comparten el resto.
    """
    if not (_table_exists(conn, "almacenes") and _table_exists(conn, "stock_almacen")):
        return

    bodegas = conn.execute(
        """
        SELECT id_almacen, macro_zona, COALESCE(es_hub, false)
        FROM almacenes
        WHERE COALESCE(activo, true) = true AND macro_zona IS NOT NULL
        ORDER BY COALESCE(prioridad, 50), id_almacen
        """
    ).fetchall()
    if not bodegas:
        return

    hubs: dict[str, int] = {}
    satelites: dict[str, list[int]] = {"americas": [], "emea": [], "apac": []}
    for id_almacen, macro, es_hub in bodegas:
        macro = str(macro)
        if macro not in satelites:
            continue
        if bool(es_hub) and macro not in hubs:
            hubs[macro] = int(id_almacen)
        else:
            satelites[macro].append(int(id_almacen))
    if not hubs:
        return

    pesos = _pesos_demanda_por_zona(conn)

    productos = conn.execute(
        """
        SELECT p.id_producto,
               CAST(COALESCE(SUM(sa.cantidad_disponible), 0) AS DOUBLE) AS total,
               COUNT(DISTINCT a.macro_zona) FILTER (WHERE sa.cantidad_disponible > 0) AS zonas
        FROM dim_producto p
        LEFT JOIN stock_almacen sa ON sa.id_producto = p.id_producto
        LEFT JOIN almacenes a ON a.id_almacen = sa.id_almacen
        WHERE p.activo = true
        GROUP BY p.id_producto
        """
    ).fetchall()

    for id_producto, total, zonas in productos:
        id_producto = int(id_producto)
        total = float(total or 0)
        if int(zonas or 0) > 1:
            continue  # ya está repartido en más de una zona
        if total <= 0:
            continue

        conn.execute("DELETE FROM stock_almacen WHERE id_producto = ?", [id_producto])
        for macro, hub in hubs.items():
            cupo_zona = total * pesos.get(macro, 0.0)
            if cupo_zona <= 0:
                continue
            sat = satelites.get(macro, [])
            cupo_hub = cupo_zona if not sat else cupo_zona * 0.60
            _upsert_stock(conn, id_producto, hub, round(cupo_hub))
            if sat:
                por_satelite = (cupo_zona - cupo_hub) / len(sat)
                for id_almacen in sat:
                    _upsert_stock(conn, id_producto, id_almacen, round(por_satelite))


def _upsert_stock(conn, id_producto: int, id_almacen: int, cantidad: float) -> None:
    cantidad = max(0.0, float(cantidad))
    fila = conn.execute(
        "SELECT id_stock FROM stock_almacen WHERE id_producto = ? AND id_almacen = ?",
        [int(id_producto), int(id_almacen)],
    ).fetchone()
    if fila:
        conn.execute(
            "UPDATE stock_almacen SET cantidad_disponible = ? WHERE id_stock = ?",
            [cantidad, int(fila[0])],
        )
        return
    conn.execute(
        """
        INSERT INTO stock_almacen (id_stock, id_producto, id_almacen, cantidad_disponible, cantidad_reservada)
        VALUES ((SELECT COALESCE(MAX(id_stock), 0) + 1 FROM stock_almacen), ?, ?, ?, 0)
        """,
        [int(id_producto), int(id_almacen), cantidad],
    )


def _seed_logistica_macro_zonas(conn) -> None:
    """3 transportistas por macro-zona + tarifas + hubs de bodega."""
    if not _table_exists(conn, "transportistas"):
        return

    if _table_exists(conn, "transportistas") and not _column_exists(conn, "transportistas", "macro_zona"):
        conn.execute("ALTER TABLE transportistas ADD COLUMN macro_zona VARCHAR")
    if _table_exists(conn, "zonas_envio") and not _column_exists(conn, "zonas_envio", "macro_zona"):
        conn.execute("ALTER TABLE zonas_envio ADD COLUMN macro_zona VARCHAR")
    if _table_exists(conn, "almacenes") and not _column_exists(conn, "almacenes", "id_region"):
        conn.execute("ALTER TABLE almacenes ADD COLUMN id_region BIGINT")

    carriers = [
        (1, "GT Américas Logistics", 8, "americas"),
        (2, "GT EMEA Freight", 4, "emea"),
        (3, "GT APAC Express", 1, "apac"),
    ]
    for tid, nombre, id_region, macro in carriers:
        exists = conn.execute(
            "SELECT id_transportista FROM transportistas WHERE id_transportista = ?", [tid]
        ).fetchone()
        if exists:
            conn.execute(
                """
                UPDATE transportistas
                SET nombre = ?, id_region = ?, macro_zona = ?, activo = true
                WHERE id_transportista = ?
                """,
                [nombre, id_region, macro, tid],
            )
        else:
            conn.execute(
                """
                INSERT INTO transportistas (id_transportista, nombre, id_region, macro_zona, activo)
                VALUES (?, ?, ?, ?, true)
                """,
                [tid, nombre, id_region, macro],
            )
    # Desactivar transportistas legacy sin macro (no los 3 GT)
    conn.execute(
        """
        UPDATE transportistas
        SET activo = false
        WHERE id_transportista NOT IN (1, 2, 3)
          AND (macro_zona IS NULL OR trim(macro_zona) = '')
        """
    )

    if not _table_exists(conn, "zonas_envio"):
        return

    # Limpiar zonas basura / locales obsoletas no usadas
    for nombre_basura in ("Tecnologia", "Provincias Perú"):
        row = conn.execute(
            "SELECT id_zona FROM zonas_envio WHERE lower(nombre) = lower(?)", [nombre_basura]
        ).fetchone()
        if not row:
            continue
        idz = int(row[0])
        usado = 0
        if _table_exists(conn, "envios"):
            usado = int(
                conn.execute("SELECT COUNT(*) FROM envios WHERE id_zona = ?", [idz]).fetchone()[0]
            )
        if usado == 0:
            if _table_exists(conn, "tarifas_envio"):
                conn.execute("DELETE FROM tarifas_envio WHERE id_zona = ?", [idz])
            conn.execute("DELETE FROM zonas_envio WHERE id_zona = ?", [idz])

    # Zona local legacy → Américas (si sigue existiendo)
    conn.execute(
        """
        UPDATE zonas_envio SET macro_zona = 'americas'
        WHERE lower(nombre) LIKE '%lima%' AND (macro_zona IS NULL OR trim(macro_zona) = '')
        """
    )

    zonas = [
        ("Américas — Estándar", 35.0, "americas", [(5, 35.0), (20, 55.0), (50, 85.0)]),
        ("EMEA — Estándar", 55.0, "emea", [(5, 55.0), (20, 85.0), (50, 130.0)]),
        ("APAC — Estándar", 60.0, "apac", [(5, 60.0), (20, 95.0), (50, 145.0)]),
    ]
    for nombre, costo_base, macro, tarifas in zonas:
        row = conn.execute(
            "SELECT id_zona FROM zonas_envio WHERE lower(nombre) = lower(?)", [nombre]
        ).fetchone()
        if row:
            id_zona = int(row[0])
            conn.execute(
                "UPDATE zonas_envio SET costo_base = ?, macro_zona = ? WHERE id_zona = ?",
                [costo_base, macro, id_zona],
            )
        else:
            conn.execute(
                """
                INSERT INTO zonas_envio (id_zona, nombre, costo_base, macro_zona)
                VALUES ((SELECT COALESCE(MAX(id_zona), 0) + 1 FROM zonas_envio), ?, ?, ?)
                """,
                [nombre, costo_base, macro],
            )
            id_zona = int(
                conn.execute(
                    "SELECT id_zona FROM zonas_envio WHERE nombre = ? ORDER BY id_zona DESC LIMIT 1",
                    [nombre],
                ).fetchone()[0]
            )
        if not _table_exists(conn, "tarifas_envio"):
            continue
        for peso_max, costo in tarifas:
            dup = conn.execute(
                "SELECT 1 FROM tarifas_envio WHERE id_zona = ? AND peso_max = ?",
                [id_zona, peso_max],
            ).fetchone()
            if not dup:
                conn.execute(
                    """
                    INSERT INTO tarifas_envio (id_tarifa, id_zona, peso_max, costo)
                    VALUES ((SELECT COALESCE(MAX(id_tarifa), 0) + 1 FROM tarifas_envio), ?, ?, ?)
                    """,
                    [id_zona, peso_max, costo],
                )

    if not _table_exists(conn, "almacenes"):
        return
    # El hub de Américas es el "Almacén Central" que ya existe desde el seed
    # base; crear otro con nombre distinto duplicaba el hub de la zona.
    hubs = [
        ("Hub EMEA", "Rotterdam — Países Bajos", 4),
        ("Hub APAC", "Singapore — Singapur", 1),
    ]
    for nombre, direccion, id_region in hubs:
        exists = conn.execute(
            "SELECT id_almacen FROM almacenes WHERE lower(nombre) = lower(?)", [nombre]
        ).fetchone()
        if exists:
            conn.execute(
                "UPDATE almacenes SET direccion = ?, id_region = ?, activo = true WHERE id_almacen = ?",
                [direccion, id_region, int(exists[0])],
            )
        else:
            conn.execute(
                """
                INSERT INTO almacenes (nombre, direccion, id_region, activo)
                VALUES (?, ?, ?, true)
                """,
                [nombre, direccion, id_region],
            )
    # Asegurar almacén central con región Américas
    conn.execute(
        """
        UPDATE almacenes
        SET id_region = COALESCE(id_region, 8), activo = true
        WHERE lower(nombre) = 'almacén central' OR lower(nombre) = 'almacen central'
        """
    )
