"""
Tests del flujo de pedido: checkout, pago simulado idempotente y descuento de stock.

Ejecutar desde la raíz del repo:
    $env:PYTHONPATH=".;apps/admin;apps/portal"
    pytest apps/portal/gmbackend/tests/test_pedido_service.py -q
"""

from __future__ import annotations

import duckdb
import pytest

from gmbackend.services import carrito_service, pedido_service
from gmbackend.services.estado_pedido import cambiar_estado


@pytest.fixture()
def conn():
    c = duckdb.connect(":memory:")
    for seq in (
        "seq_usuarios", "seq_dim_cliente", "seq_dim_producto", "seq_pedidos",
        "seq_pedido_detalle", "seq_carritos", "seq_movimientos", "seq_pagos",
    ):
        c.execute(f"CREATE SEQUENCE {seq} START 1")
    c.execute(
        """
        CREATE TABLE usuarios (
          id_usuario BIGINT PRIMARY KEY DEFAULT nextval('seq_usuarios'),
          email VARCHAR, password_hash VARCHAR, rol VARCHAR DEFAULT 'cliente', activo BOOLEAN DEFAULT true,
          fecha_registro TIMESTAMP DEFAULT current_timestamp
        );
        CREATE TABLE dim_cliente (
          id_cliente BIGINT PRIMARY KEY DEFAULT nextval('seq_dim_cliente'),
          id_usuario BIGINT, nombre_empresa VARCHAR, pais VARCHAR, telefono VARCHAR, direccion VARCHAR
        );
        CREATE TABLE dim_item_type (id_item_type INTEGER PRIMARY KEY, item_type VARCHAR, unit_price DECIMAL(10,2), unit_cost DECIMAL(10,2));
        CREATE TABLE dim_producto (
          id_producto BIGINT PRIMARY KEY DEFAULT nextval('seq_dim_producto'),
          nombre_producto VARCHAR, descripcion VARCHAR, id_item_type BIGINT,
          precio_unitario DECIMAL(10,2), precio_mayorista DECIMAL(10,2), imagen_url VARCHAR, activo BOOLEAN DEFAULT true,
          descuento_pct DECIMAL(5,2) DEFAULT 0, precio_rebajado DECIMAL(10,2),
          descuento_aplica_a VARCHAR DEFAULT 'mayorista', fecha_rebaja_hasta DATE, sku VARCHAR
        );
        CREATE TABLE dim_region (id_region INTEGER PRIMARY KEY, region VARCHAR);
        CREATE TABLE dim_country (id_country INTEGER PRIMARY KEY, country VARCHAR, id_region INTEGER);
        CREATE TABLE dim_sales_channel (id_channel INTEGER PRIMARY KEY, sales_channel VARCHAR);
        CREATE TABLE dim_order_priority (id_priority INTEGER PRIMARY KEY, order_priority VARCHAR);
        CREATE TABLE stock_almacen (
          id_stock BIGINT PRIMARY KEY, id_producto BIGINT, id_almacen BIGINT,
          cantidad_disponible DECIMAL(12,4) DEFAULT 0, cantidad_reservada DECIMAL(12,4) DEFAULT 0
        );
        CREATE TABLE movimientos_inventario (
          id_movimiento BIGINT PRIMARY KEY DEFAULT nextval('seq_movimientos'),
          tipo VARCHAR, fecha TIMESTAMP DEFAULT current_timestamp, referencia VARCHAR, id_usuario BIGINT
        );
        CREATE TABLE movimiento_inventario_detalle (
          id_detalle BIGINT PRIMARY KEY, id_movimiento BIGINT, id_producto BIGINT,
          id_almacen BIGINT, id_lote BIGINT, cantidad DECIMAL(12,4)
        );
        CREATE TABLE carritos (
          id_carrito BIGINT PRIMARY KEY DEFAULT nextval('seq_carritos'),
          id_cliente BIGINT, estado VARCHAR DEFAULT 'activo', fecha TIMESTAMP DEFAULT current_timestamp
        );
        CREATE TABLE carrito_items (
          id_item BIGINT PRIMARY KEY, id_carrito BIGINT, id_producto BIGINT,
          cantidad INTEGER, precio_congelado DECIMAL(10,2), subtotal DECIMAL(12,2)
        );
        CREATE TABLE pedidos (
          id_pedido BIGINT PRIMARY KEY DEFAULT nextval('seq_pedidos'),
          id_cliente BIGINT, id_country BIGINT, id_channel BIGINT, id_priority BIGINT,
          fecha_pedido TIMESTAMP DEFAULT current_timestamp, estado VARCHAR DEFAULT 'pendiente',
          total_pedido DECIMAL(12,2), notas VARCHAR,
          numero VARCHAR, id_direccion_entrega BIGINT,
          subtotal DECIMAL(12,2), impuesto_monto DECIMAL(12,2), total DECIMAL(12,2),
          descuento_pct DECIMAL(5,2), descuento_monto DECIMAL(12,2), id_promocion BIGINT,
          costo_envio DECIMAL(12,2) DEFAULT 0
        );
        CREATE TABLE zonas_envio (
          id_zona INTEGER PRIMARY KEY, nombre VARCHAR, costo_base DECIMAL(10,2), macro_zona VARCHAR
        );
        CREATE TABLE promociones (
          id_promocion BIGINT PRIMARY KEY, nombre VARCHAR, descuento_pct DECIMAL(5,2),
          fecha_inicio DATE, fecha_fin DATE, activa BOOLEAN DEFAULT true
        );
        CREATE TABLE pedido_detalle (
          id_detalle BIGINT PRIMARY KEY DEFAULT nextval('seq_pedido_detalle'),
          id_pedido BIGINT, id_producto BIGINT, cantidad BIGINT,
          precio_unitario DECIMAL(10,2), subtotal DECIMAL(12,2), costo_unitario DECIMAL(10,2)
        );
        CREATE TABLE pedido_estados_historial (
          id_historial BIGINT PRIMARY KEY, id_pedido BIGINT,
          estado_anterior VARCHAR, estado_nuevo VARCHAR, id_usuario BIGINT,
          fecha TIMESTAMP DEFAULT current_timestamp
        );
        CREATE TABLE metodos_pago (id_metodo BIGINT PRIMARY KEY, nombre VARCHAR, activo BOOLEAN DEFAULT true);
        INSERT INTO metodos_pago VALUES (1, 'simulado', true), (2, 'tarjeta', true), (3, 'transferencia', true), (4, 'credito_interno', true);
        CREATE TABLE pagos (
          id_pago BIGINT PRIMARY KEY DEFAULT nextval('seq_pagos'),
          numero VARCHAR, id_pedido BIGINT, id_factura BIGINT, id_metodo BIGINT,
          monto DECIMAL(12,2), estado VARCHAR, referencia VARCHAR, fecha TIMESTAMP
        );
        CREATE TABLE configuracion_sistema (clave VARCHAR PRIMARY KEY, valor VARCHAR, descripcion VARCHAR);
        INSERT INTO configuracion_sistema VALUES
          ('PAGO_SIM_METODOS', 'tarjeta,transferencia,credito_interno,simulado', ''),
          ('IVA_PCT', '18', ''), ('PAGO_SIM_TASA_EXITO', '95', '');
        """
    )
    # Seeds mínimos
    c.execute("INSERT INTO dim_region VALUES (1, 'Norte')")
    c.execute("INSERT INTO dim_country VALUES (1, 'Peru', 1)")
    c.execute("INSERT INTO dim_sales_channel VALUES (1, 'Online')")
    c.execute("INSERT INTO dim_order_priority VALUES (1, 'M')")
    c.execute("INSERT INTO dim_item_type VALUES (1, 'Snacks', 10, 6)")
    c.execute("INSERT INTO usuarios (email, password_hash) VALUES ('c@x.com', 'h')")
    c.execute("INSERT INTO dim_cliente (id_usuario, nombre_empresa, pais) VALUES (1, 'ACME', 'Peru')")
    c.execute(
        "INSERT INTO dim_producto (nombre_producto, id_item_type, precio_unitario, precio_mayorista) VALUES ('Prod A', 1, 10, 8)"
    )
    c.execute("INSERT INTO stock_almacen VALUES (1, 1, 1, 100, 0)")
    yield c
    c.close()


def _checkout_pagado(conn) -> dict:
    carrito_service.agregar_item(conn, id_cliente=1, id_producto=1, cantidad=5)
    pedido = pedido_service.crear_pedido_desde_carrito(
        conn, id_cliente=1, id_usuario=1, direccion_entrega="Av. Central 123", ciudad="Lima",
        notas=None, pais="Peru",
    )
    resultado = pedido_service.pagar_pedido_simulado(
        conn, id_pedido=pedido["id_pedido"], id_cliente=1, id_usuario=1
    )
    return resultado


def test_obtener_pedido_sin_tabla_promociones(conn):
    """Con columnas de promo en pedidos pero sin tabla promociones (migración parcial)."""
    conn.execute("DROP TABLE IF EXISTS promociones")
    carrito_service.agregar_item(conn, id_cliente=1, id_producto=1, cantidad=2)
    pedido = pedido_service.crear_pedido_desde_carrito(
        conn, id_cliente=1, id_usuario=1, direccion_entrega="Av. Central 123", ciudad="Lima",
        notas=None, pais="Peru",
    )
    det = pedido_service.obtener_pedido(conn, pedido["id_pedido"])
    assert det is not None
    assert det["id_pedido"] == pedido["id_pedido"]
    assert det["costo_envio"] == 0.0


def test_checkout_crea_pedido_pendiente(conn):
    carrito_service.agregar_item(conn, id_cliente=1, id_producto=1, cantidad=5)
    pedido = pedido_service.crear_pedido_desde_carrito(
        conn, id_cliente=1, id_usuario=1, direccion_entrega="Av. Central 123", ciudad=None, notas=None, pais="Peru",
    )
    assert pedido["estado"] == "pendiente_pago"
    assert pedido["subtotal"] == 50.0
    assert pedido["impuesto"] == 9.0
    assert pedido["total"] == 59.0
    assert pedido["items"]
    assert all(i.get("id_detalle") is not None for i in pedido["items"])
    # El checkout no descuenta stock todavía
    stock = conn.execute("SELECT cantidad_disponible FROM stock_almacen WHERE id_producto = 1").fetchone()[0]
    assert float(stock) == 100


def test_pago_descuenta_stock_y_marca_pagado(conn):
    resultado = _checkout_pagado(conn)
    assert resultado["pedido"]["estado"] == "pagado"
    assert resultado["pago"]["estado"] == "aprobado"
    stock = conn.execute("SELECT cantidad_disponible FROM stock_almacen WHERE id_producto = 1").fetchone()[0]
    assert float(stock) == 95


def test_pago_idempotente(conn):
    resultado = _checkout_pagado(conn)
    id_pedido = resultado["pedido"]["id_pedido"]
    # Reintento de pago: no duplica ni vuelve a descontar stock
    reintento = pedido_service.pagar_pedido_simulado(conn, id_pedido=id_pedido, id_cliente=1, id_usuario=1)
    assert reintento["pago"].get("idempotente") is True
    stock = conn.execute("SELECT cantidad_disponible FROM stock_almacen WHERE id_producto = 1").fetchone()[0]
    assert float(stock) == 95
    n_pagos = conn.execute("SELECT COUNT(*) FROM pagos WHERE id_pedido = ?", [id_pedido]).fetchone()[0]
    assert int(n_pagos) == 1


def test_checkout_falla_sin_stock(conn):
    conn.execute("UPDATE stock_almacen SET cantidad_disponible = 3 WHERE id_producto = 1")
    with pytest.raises(ValueError, match="Stock insuficiente"):
        carrito_service.agregar_item(conn, id_cliente=1, id_producto=1, cantidad=5)


def test_maquina_estados_valida(conn):
    resultado = _checkout_pagado(conn)
    id_pedido = resultado["pedido"]["id_pedido"]
    cambiar_estado(conn, id_pedido=id_pedido, nuevo_estado="preparando", id_usuario=1)
    cambiar_estado(conn, id_pedido=id_pedido, nuevo_estado="enviado", id_usuario=1)
    cambiar_estado(conn, id_pedido=id_pedido, nuevo_estado="entregado", id_usuario=1)
    with pytest.raises(ValueError, match="Transición inválida"):
        cambiar_estado(conn, id_pedido=id_pedido, nuevo_estado="pagado", id_usuario=1)


def test_transicion_invalida_desde_pendiente(conn):
    carrito_service.agregar_item(conn, id_cliente=1, id_producto=1, cantidad=2)
    pedido = pedido_service.crear_pedido_desde_carrito(
        conn, id_cliente=1, id_usuario=1, direccion_entrega="Calle Falsa 123", ciudad=None, notas=None, pais="Peru",
    )
    with pytest.raises(ValueError, match="Transición inválida"):
        cambiar_estado(conn, id_pedido=pedido["id_pedido"], nuevo_estado="enviado", id_usuario=1)


def test_pago_transferencia_pendiente_validacion(conn):
    carrito_service.agregar_item(conn, id_cliente=1, id_producto=1, cantidad=2)
    pedido = pedido_service.crear_pedido_desde_carrito(
        conn, id_cliente=1, id_usuario=1, direccion_entrega="Av. Central 123", ciudad=None, notas=None, pais="Peru",
    )
    res = pedido_service.pagar_pedido_simulado(
        conn, id_pedido=pedido["id_pedido"], id_cliente=1, id_usuario=1, metodo="transferencia",
    )
    assert res["pendiente_validacion"] is True
    assert res["pago"]["estado"] == "pendiente_validacion"
    assert res["pedido"]["estado"] == "pendiente_pago"
    stock = conn.execute("SELECT cantidad_disponible FROM stock_almacen WHERE id_producto = 1").fetchone()[0]
    assert float(stock) == 100


def test_checkout_idempotente_actualiza_pendiente(conn):
    carrito_service.agregar_item(conn, id_cliente=1, id_producto=1, cantidad=5)
    p1 = pedido_service.crear_pedido_desde_carrito(
        conn, id_cliente=1, id_usuario=1, direccion_entrega="Av. Central 123", ciudad="Lima",
        notas=None, pais="Peru",
    )
    p2 = pedido_service.crear_pedido_desde_carrito(
        conn, id_cliente=1, id_usuario=1, direccion_entrega="Av. Nueva 456", ciudad="Lima",
        notas="OC-1", pais="Peru",
    )
    assert p1["id_pedido"] == p2["id_pedido"]
    assert p2["subtotal"] == 50.0
    n_pedidos = conn.execute("SELECT COUNT(*) FROM pedidos WHERE id_cliente = 1").fetchone()[0]
    assert int(n_pedidos) == 1


def test_checkout_rechaza_pais_invalido(conn):
    carrito_service.agregar_item(conn, id_cliente=1, id_producto=1, cantidad=2)
    with pytest.raises(ValueError, match="país"):
        pedido_service.crear_pedido_desde_carrito(
            conn, id_cliente=1, id_usuario=1, direccion_entrega="Av. X 1", ciudad=None, notas=None, pais="Atlantis",
        )


def test_checkout_incluye_costo_envio(conn):
    conn.execute("INSERT INTO zonas_envio VALUES (1, 'APAC Std', 30.0, 'apac')")
    carrito_service.agregar_item(conn, id_cliente=1, id_producto=1, cantidad=2)
    pedido = pedido_service.crear_pedido_desde_carrito(
        conn, id_cliente=1, id_usuario=1, direccion_entrega="Av. X 1", ciudad=None, notas=None, pais="Peru",
    )
    assert pedido["costo_envio"] == 30.0
    assert pedido["subtotal"] == 20.0
    assert pedido["total"] == round(20.0 * 1.18 + 30.0, 2)


def test_precio_mayorista_desde_minimo(conn):
    carrito_service.agregar_item(conn, id_cliente=1, id_producto=1, cantidad=10)
    carrito = carrito_service.ver_carrito(conn, 1)
    assert carrito["items"][0]["precio"] == 8.0  # precio mayorista
