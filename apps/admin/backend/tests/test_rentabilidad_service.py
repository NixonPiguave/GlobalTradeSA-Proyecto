"""Tests rentabilidad por SKU (portal) vs item_type (histórico)."""

from __future__ import annotations

import duckdb
import pytest

from backend.services.rentabilidad_service import get_rentabilidad_producto


@pytest.fixture()
def conn():
    c = duckdb.connect(":memory:")
    c.execute(
        """
        CREATE TABLE dim_region (id_region INTEGER PRIMARY KEY, region VARCHAR);
        CREATE TABLE dim_country (id_country INTEGER PRIMARY KEY, country VARCHAR, id_region INTEGER);
        CREATE TABLE dim_item_type (
          id_item_type INTEGER PRIMARY KEY, item_type VARCHAR,
          unit_price DECIMAL(10,2), unit_cost DECIMAL(10,2)
        );
        CREATE TABLE dim_sales_channel (id_channel INTEGER PRIMARY KEY, sales_channel VARCHAR);
        CREATE TABLE dim_order_priority (id_priority INTEGER PRIMARY KEY, order_priority VARCHAR);
        CREATE TABLE dim_producto (
          id_producto BIGINT PRIMARY KEY, nombre_producto VARCHAR, id_item_type BIGINT
        );
        CREATE TABLE fact_ventas (
          id_venta INTEGER PRIMARY KEY, order_id BIGINT UNIQUE,
          id_region INTEGER, id_country INTEGER, id_item_type INTEGER,
          id_channel INTEGER, id_priority INTEGER,
          order_date DATE, ship_date DATE,
          units_sold INTEGER, unit_price DECIMAL(10,2), unit_cost DECIMAL(10,2),
          total_revenue DECIMAL(12,2), total_cost DECIMAL(12,2), total_profit DECIMAL(12,2),
          id_producto BIGINT, origen VARCHAR
        );
        INSERT INTO dim_region VALUES (1, 'North');
        INSERT INTO dim_country VALUES (1, 'USA', 1);
        INSERT INTO dim_item_type VALUES (1, 'Meat', 10, 5);
        INSERT INTO dim_sales_channel VALUES (1, 'Online');
        INSERT INTO dim_order_priority VALUES (1, 'Normal');
        INSERT INTO dim_producto VALUES (99, 'Frozen Beef Strips — 10kg', 1);
        INSERT INTO fact_ventas VALUES
          (1, 100, 1,1,1,1,1, '2020-01-01','2020-01-08', 100, 10, 5, 1000, 500, 500, NULL, 'historico'),
          (2, 10000000001, 1,1,1,1,1, CURRENT_DATE, CURRENT_DATE, 2, 76, 62, 152, 124, 28, 99, 'portal');
        CREATE VIEW ventas AS
        SELECT
          dr.region, dc.country, dit.item_type, dsc.sales_channel, dop.order_priority,
          fv.order_date, fv.order_id, fv.ship_date, fv.units_sold,
          fv.unit_price, fv.unit_cost, fv.total_revenue, fv.total_cost, fv.total_profit,
          fv.id_venta, fv.id_producto, fv.origen,
          dp.nombre_producto,
          COALESCE(dp.nombre_producto, dit.item_type) AS dimension_producto
        FROM fact_ventas fv
        JOIN dim_region dr ON dr.id_region = fv.id_region
        JOIN dim_country dc ON dc.id_country = fv.id_country
        JOIN dim_item_type dit ON dit.id_item_type = fv.id_item_type
        JOIN dim_sales_channel dsc ON dsc.id_channel = fv.id_channel
        JOIN dim_order_priority dop ON dop.id_priority = fv.id_priority
        LEFT JOIN dim_producto dp ON dp.id_producto = fv.id_producto
        """
    )
    yield c
    c.close()


def test_rentabilidad_producto_solo_sku_portal(conn):
    rows = get_rentabilidad_producto(conn)
    by_dim = {r["dimension"]: r for r in rows}
    assert "Meat" not in by_dim
    assert "Frozen Beef Strips — 10kg" in by_dim
    assert by_dim["Frozen Beef Strips — 10kg"]["total_revenue"] == 152.0
    assert len(rows) == 1
