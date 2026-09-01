"""
Tests de recompra «Volver a pedir» (spec 007).

Ejecutar desde la raíz del repo:
    $env:PYTHONPATH=".;apps/admin;apps/portal"
    pytest apps/portal/gmbackend/tests/test_volver_a_pedir.py -q
"""

from __future__ import annotations

import duckdb
import pytest

from gmbackend.services import carrito_service, pedido_service
from gmbackend.services.pedido_service import ReordenSinAgregadosError


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
          subtotal DECIMAL(12,2), impuesto_monto DECIMAL(12,2), total DECIMAL(12,2)
        );
        CREATE TABLE pedido_detalle (
          id_detalle BIGINT PRIMARY KEY DEFAULT nextval('seq_pedido_detalle'),
          id_pedido BIGINT, id_producto BIGINT, cantidad BIGINT,
          precio_unitario DECIMAL(10,2), subtotal DECIMAL(12,2), costo_unitario DECIMAL(10,2)
        );
        CREATE TABLE configuracion_sistema (clave VARCHAR PRIMARY KEY, valor VARCHAR, descripcion VARCHAR);
        INSERT INTO configuracion_sistema VALUES ('MOQ_MAYORISTA', '10', ''), ('IVA_PCT', '18', '');
        """
    )
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
    c.execute(
        "INSERT INTO dim_producto (nombre_producto, id_item_type, precio_unitario, precio_mayorista, activo) VALUES ('Prod B', 1, 12, 9, true)"
    )
    c.execute("INSERT INTO stock_almacen VALUES (1, 1, 1, 100, 0)")
    c.execute("INSERT INTO stock_almacen VALUES (2, 2, 1, 50, 0)")
    yield c
    c.close()


def _crear_pedido_entregado(conn, *, id_cliente: int = 1, cantidad: int = 5) -> int:
    """Pedido entregado con una línea de Prod A (sin pasar por checkout completo)."""
    carrito_service.vaciar_carrito(conn, id_cliente)
    row = conn.execute("SELECT COALESCE(MAX(id_pedido), 0) + 1 FROM pedidos").fetchone()
    id_pedido = int(row[0])
    subtotal = round(cantidad * 10.0, 2)
    total = round(subtotal * 1.18, 2)
    conn.execute(
        """
        INSERT INTO pedidos (
          id_pedido, id_cliente, id_country, id_channel, id_priority, estado, numero,
          subtotal, impuesto_monto, total, total_pedido
        ) VALUES (?, ?, 1, 1, 1, 'entregado', ?, ?, ?, ?, ?)
        """,
        [id_pedido, id_cliente, f"PED-T{id_pedido}", subtotal, round(subtotal * 0.18, 2), total, total],
    )
    conn.execute(
        """
        INSERT INTO pedido_detalle (id_pedido, id_producto, cantidad, precio_unitario, subtotal, costo_unitario)
        VALUES (?, 1, ?, 10, ?, 6)
        """,
        [id_pedido, cantidad, subtotal],
    )
    return id_pedido


def test_volver_a_pedir_feliz(conn):
    id_pedido = _crear_pedido_entregado(conn, cantidad=5)
    resultado = pedido_service.volver_a_pedir(conn, id_pedido=id_pedido, id_cliente=1)
    assert resultado["resumen"]["n_agregados"] == 1
    carrito = carrito_service.ver_carrito(conn, 1)
    assert carrito["n_items"] == 1
    assert carrito["items"][0]["cantidad"] == 5


def test_volver_a_pedir_producto_inactivo_omitido(conn):
    id_pedido = _crear_pedido_entregado(conn)
    conn.execute(
        """
        INSERT INTO pedido_detalle (id_pedido, id_producto, cantidad, precio_unitario, subtotal, costo_unitario)
        VALUES (?, 2, 3, 12, 36, 6)
        """,
        [id_pedido],
    )
    conn.execute("UPDATE dim_producto SET activo = false WHERE id_producto = 2")
    resultado = pedido_service.volver_a_pedir(conn, id_pedido=id_pedido, id_cliente=1)
    assert resultado["resumen"]["n_agregados"] == 1
    assert any(o["id_producto"] == 2 and o["motivo"] == "no_disponible" for o in resultado["resumen"]["omitidos"])


def test_volver_a_pedir_stock_parcial_ajustado(conn):
    id_pedido = _crear_pedido_entregado(conn, cantidad=10)
    conn.execute("UPDATE stock_almacen SET cantidad_disponible = 7 WHERE id_producto = 1")
    resultado = pedido_service.volver_a_pedir(conn, id_pedido=id_pedido, id_cliente=1)
    assert resultado["resumen"]["ajustados"]
    assert resultado["resumen"]["ajustados"][0]["cantidad_agregada"] == 7
    carrito = carrito_service.ver_carrito(conn, 1)
    assert carrito["items"][0]["cantidad"] == 7


def test_volver_a_pedir_merge_carrito_existente(conn):
    id_pedido = _crear_pedido_entregado(conn, cantidad=5)
    carrito_service.agregar_item(conn, id_cliente=1, id_producto=1, cantidad=3)
    resultado = pedido_service.volver_a_pedir(conn, id_pedido=id_pedido, id_cliente=1)
    assert resultado["resumen"]["n_agregados"] == 1
    carrito = carrito_service.ver_carrito(conn, 1)
    assert carrito["items"][0]["cantidad"] == 8


def test_volver_a_pedir_precios_vigentes_no_historicos(conn):
    id_pedido = _crear_pedido_entregado(conn, cantidad=5)
    conn.execute("UPDATE pedido_detalle SET precio_unitario = 99 WHERE id_pedido = ?", [id_pedido])
    conn.execute("UPDATE dim_producto SET precio_unitario = 11, precio_mayorista = 9 WHERE id_producto = 1")
    resultado = pedido_service.volver_a_pedir(conn, id_pedido=id_pedido, id_cliente=1)
    precio_carrito = resultado["carrito"]["items"][0]["precio"]
    assert precio_carrito != 99.0
    assert precio_carrito == 11.0


def test_volver_a_pedir_estado_no_elegible(conn):
    id_pedido = _crear_pedido_entregado(conn)
    conn.execute("UPDATE pedidos SET estado = 'pendiente_pago' WHERE id_pedido = ?", [id_pedido])
    with pytest.raises(ValueError, match="no permite volver a pedir"):
        pedido_service.volver_a_pedir(conn, id_pedido=id_pedido, id_cliente=1)


def test_volver_a_pedir_pedido_ajeno(conn):
    id_pedido = _crear_pedido_entregado(conn)
    conn.execute("INSERT INTO usuarios (email, password_hash) VALUES ('otro@x.com', 'h')")
    conn.execute("INSERT INTO dim_cliente (id_usuario, nombre_empresa, pais) VALUES (2, 'Otra', 'Peru')")
    with pytest.raises(ValueError, match="Pedido no encontrado"):
        pedido_service.volver_a_pedir(conn, id_pedido=id_pedido, id_cliente=2)


def test_volver_a_pedir_bloqueo_pendiente_pago(conn):
    id_entregado = _crear_pedido_entregado(conn)
    conn.execute(
        """
        INSERT INTO pedidos (
          id_pedido, id_cliente, id_country, id_channel, id_priority, estado, numero,
          subtotal, impuesto_monto, total, total_pedido
        ) VALUES (99, 1, 1, 1, 1, 'pendiente_pago', 'PED-PEND', 20, 3.6, 23.6, 23.6)
        """
    )
    with pytest.raises(ValueError, match="pendiente de pago"):
        pedido_service.volver_a_pedir(conn, id_pedido=id_entregado, id_cliente=1)


def test_volver_a_pedir_cero_agregados(conn):
    id_pedido = _crear_pedido_entregado(conn)
    conn.execute("UPDATE dim_producto SET activo = false WHERE id_producto = 1")
    with pytest.raises(ReordenSinAgregadosError) as exc:
        pedido_service.volver_a_pedir(conn, id_pedido=id_pedido, id_cliente=1)
    assert exc.value.resumen["n_agregados"] == 0
    carrito = carrito_service.ver_carrito(conn, 1)
    assert carrito["n_items"] == 0


def test_volver_a_pedir_stock_no_negativo(conn):
    id_pedido = _crear_pedido_entregado(conn, cantidad=5)
    conn.execute("UPDATE stock_almacen SET cantidad_disponible = 5 WHERE id_producto = 1")
    pedido_service.volver_a_pedir(conn, id_pedido=id_pedido, id_cliente=1)
    stock = conn.execute(
        "SELECT cantidad_disponible FROM stock_almacen WHERE id_producto = 1"
    ).fetchone()[0]
    assert float(stock) >= 0
