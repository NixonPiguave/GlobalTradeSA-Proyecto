"""
Tests de integración pedido → fact_ventas (idempotencia y order_id único).

Ejecutar desde la raíz del repo:
    $env:PYTHONPATH=".;apps/admin;apps/portal"
    pytest apps/admin/backend/tests/test_integracion_ventas.py -q
"""

from __future__ import annotations

import duckdb
import pytest

from shared.services.integracion_ventas_service import (
    integrar_pedido,
    order_id_linea,
    reintegrar_pedidos_pendientes,
)


@pytest.fixture()
def conn():
    c = duckdb.connect(":memory:")
    for seq in (
        "seq_pedidos", "seq_pedido_detalle", "seq_dim_producto", "seq_dim_cliente",
    ):
        c.execute(f"CREATE SEQUENCE {seq} START 1")
    c.execute(
        """
        CREATE TABLE dim_region (id_region INTEGER PRIMARY KEY, region VARCHAR);
        CREATE TABLE dim_country (id_country INTEGER PRIMARY KEY, country VARCHAR, id_region INTEGER);
        CREATE TABLE dim_item_type (id_item_type INTEGER PRIMARY KEY, item_type VARCHAR, unit_price DECIMAL(10,2), unit_cost DECIMAL(10,2));
        CREATE TABLE dim_sales_channel (id_channel INTEGER PRIMARY KEY, sales_channel VARCHAR);
        CREATE TABLE dim_order_priority (id_priority INTEGER PRIMARY KEY, order_priority VARCHAR);
        CREATE TABLE dim_cliente (
          id_cliente BIGINT PRIMARY KEY DEFAULT nextval('seq_dim_cliente'),
          nombre_empresa VARCHAR, pais VARCHAR
        );
        CREATE TABLE dim_producto (
          id_producto BIGINT PRIMARY KEY DEFAULT nextval('seq_dim_producto'),
          nombre_producto VARCHAR, id_item_type BIGINT, precio_unitario DECIMAL(10,2)
        );
        CREATE TABLE pedidos (
          id_pedido BIGINT PRIMARY KEY DEFAULT nextval('seq_pedidos'),
          id_cliente BIGINT, id_country BIGINT, id_channel BIGINT, id_priority BIGINT,
          fecha_pedido TIMESTAMP DEFAULT current_timestamp, estado VARCHAR,
          subtotal DECIMAL(12,2), total DECIMAL(12,2), numero VARCHAR
        );
        CREATE TABLE pedido_detalle (
          id_detalle BIGINT PRIMARY KEY DEFAULT nextval('seq_pedido_detalle'),
          id_pedido BIGINT, id_producto BIGINT, cantidad INTEGER,
          precio_unitario DECIMAL(10,2), subtotal DECIMAL(12,2), costo_unitario DECIMAL(10,2)
        );
        CREATE TABLE fact_ventas (
          id_venta INTEGER PRIMARY KEY,
          order_id BIGINT NOT NULL UNIQUE,
          id_region INTEGER NOT NULL, id_country INTEGER NOT NULL,
          id_item_type INTEGER NOT NULL, id_channel INTEGER NOT NULL, id_priority INTEGER NOT NULL,
          order_date DATE NOT NULL, ship_date DATE NOT NULL,
          units_sold INTEGER NOT NULL, unit_price DECIMAL(10,2) NOT NULL,
          unit_cost DECIMAL(10,2) NOT NULL, total_revenue DECIMAL(12,2) NOT NULL,
          total_cost DECIMAL(12,2) NOT NULL, total_profit DECIMAL(12,2) NOT NULL,
          id_producto BIGINT, origen VARCHAR DEFAULT 'historico'
        );
        """
    )
    c.execute("INSERT INTO dim_region VALUES (1, 'Norte')")
    c.execute("INSERT INTO dim_country VALUES (1, 'Peru', 1)")
    c.execute("INSERT INTO dim_sales_channel VALUES (1, 'Online')")
    c.execute("INSERT INTO dim_order_priority VALUES (1, 'M')")
    c.execute("INSERT INTO dim_item_type VALUES (1, 'Snacks', 10, 6)")
    c.execute("INSERT INTO dim_cliente (nombre_empresa, pais) VALUES ('ACME', 'Peru')")
    c.execute("INSERT INTO dim_producto (nombre_producto, id_item_type, precio_unitario) VALUES ('Prod A', 1, 10)")
    c.execute(
        """
        INSERT INTO pedidos (id_cliente, id_country, id_channel, id_priority, estado, subtotal, total, numero)
        VALUES (1, 1, 1, 1, 'pagado', 80, 80, 'PED-000001')
        """
    )
    c.execute(
        """
        INSERT INTO pedido_detalle (id_pedido, id_producto, cantidad, precio_unitario, subtotal, costo_unitario)
        VALUES (1, 1, 5, 8, 40, 6), (1, 1, 5, 8, 40, 6)
        """
    )
    yield c
    c.close()


def test_integrar_pedido_inserta_lineas_con_origen_portal(conn):
    r = integrar_pedido(conn, id_pedido=1)
    assert r["insertadas"] == 2
    assert r["omitidas"] == 0

    filas = conn.execute(
        "SELECT order_id, id_producto, origen, units_sold FROM fact_ventas ORDER BY order_id"
    ).fetchall()
    assert len(filas) == 2
    assert all(f[1] == 1 for f in filas)
    assert all(f[2] == "portal" for f in filas)
    assert filas[0][0] == order_id_linea(1, 1)
    assert filas[1][0] == order_id_linea(1, 2)


def test_integrar_pedido_idempotente(conn):
    integrar_pedido(conn, id_pedido=1)
    r2 = integrar_pedido(conn, id_pedido=1)
    assert r2["insertadas"] == 0
    assert r2["omitidas"] == 2
    n = conn.execute("SELECT COUNT(*) FROM fact_ventas").fetchone()[0]
    assert n == 2


def test_reintegrar_no_duplica(conn):
    integrar_pedido(conn, id_pedido=1)
    bulk = reintegrar_pedidos_pendientes(conn)
    assert bulk["insertadas"] == 0
    assert conn.execute("SELECT COUNT(*) FROM fact_ventas").fetchone()[0] == 2


def test_order_id_no_colisiona_historico(conn):
    conn.execute(
        """
        INSERT INTO fact_ventas (
          id_venta, order_id, id_region, id_country, id_item_type, id_channel, id_priority,
          order_date, ship_date, units_sold, unit_price, unit_cost,
          total_revenue, total_cost, total_profit, id_producto, origen
        ) VALUES (1, 99999, 1, 1, 1, 1, 1, '2020-01-01', '2020-01-08', 1, 10, 6, 10, 6, 4, NULL, 'historico')
        """
    )
    integrar_pedido(conn, id_pedido=1)
    assert conn.execute("SELECT COUNT(*) FROM fact_ventas").fetchone()[0] == 3
