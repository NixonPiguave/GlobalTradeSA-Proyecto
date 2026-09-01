#!/usr/bin/env python3
"""
Carga el modelo estrella en DuckDB desde data/ventas.parquet.
"""

from __future__ import annotations

import sys
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parent.parent
PARQUET_PATH = ROOT / "data" / "ventas.parquet"
DB_PATH = ROOT / "db" / "globtrade.duckdb"


def main() -> None:
    if not PARQUET_PATH.exists():
        print(f"Error: no se encontró {PARQUET_PATH}")
        sys.exit(1)

    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    if DB_PATH.exists():
        DB_PATH.unlink()

    con = duckdb.connect(str(DB_PATH))
    parquet = PARQUET_PATH.as_posix()

    con.execute(f"CREATE TABLE staging AS SELECT * FROM read_parquet('{parquet}')")
    con.execute("""
        ALTER TABLE staging
        ALTER COLUMN order_date TYPE DATE
        USING strptime(order_date::VARCHAR, '%m/%d/%Y')::DATE
    """)
    con.execute("""
        ALTER TABLE staging
        ALTER COLUMN ship_date TYPE DATE
        USING strptime(ship_date::VARCHAR, '%m/%d/%Y')::DATE
    """)

    con.execute("""
        CREATE TABLE dim_region (
            id_region INTEGER PRIMARY KEY,
            region VARCHAR NOT NULL UNIQUE
        )
    """)
    con.execute("""
        INSERT INTO dim_region (id_region, region)
        SELECT row_number() OVER (ORDER BY region), region
        FROM (SELECT DISTINCT region FROM staging WHERE region IS NOT NULL)
    """)

    con.execute("""
        CREATE TABLE dim_country (
            id_country INTEGER PRIMARY KEY,
            country VARCHAR NOT NULL,
            id_region INTEGER NOT NULL REFERENCES dim_region(id_region),
            UNIQUE(country, id_region)
        )
    """)
    con.execute("""
        INSERT INTO dim_country (id_country, country, id_region)
        SELECT
            row_number() OVER (ORDER BY s.country, r.id_region),
            s.country,
            r.id_region
        FROM (
            SELECT DISTINCT country, region FROM staging
            WHERE country IS NOT NULL AND region IS NOT NULL
        ) s
        JOIN dim_region r ON r.region = s.region
    """)

    con.execute("""
        CREATE TABLE dim_item_type (
            id_item_type INTEGER PRIMARY KEY,
            item_type VARCHAR NOT NULL UNIQUE,
            unit_price DECIMAL(10, 2) NOT NULL,
            unit_cost DECIMAL(10, 2) NOT NULL
        )
    """)
    con.execute("""
        INSERT INTO dim_item_type (id_item_type, item_type, unit_price, unit_cost)
        SELECT
            row_number() OVER (ORDER BY item_type),
            item_type,
            CAST(AVG(unit_price) AS DECIMAL(10,2)),
            CAST(AVG(unit_cost) AS DECIMAL(10,2))
        FROM staging
        WHERE item_type IS NOT NULL
        GROUP BY item_type
    """)

    con.execute("""
        CREATE TABLE dim_sales_channel (
            id_channel INTEGER PRIMARY KEY,
            sales_channel VARCHAR NOT NULL UNIQUE
        )
    """)
    con.execute("""
        INSERT INTO dim_sales_channel (id_channel, sales_channel)
        SELECT row_number() OVER (ORDER BY sales_channel), sales_channel
        FROM (SELECT DISTINCT sales_channel FROM staging WHERE sales_channel IS NOT NULL)
    """)

    con.execute("""
        CREATE TABLE dim_order_priority (
            id_priority INTEGER PRIMARY KEY,
            order_priority VARCHAR NOT NULL UNIQUE
        )
    """)
    con.execute("""
        INSERT INTO dim_order_priority (id_priority, order_priority)
        SELECT row_number() OVER (ORDER BY order_priority), order_priority
        FROM (SELECT DISTINCT order_priority FROM staging WHERE order_priority IS NOT NULL)
    """)

    con.execute("""
        CREATE TABLE fact_ventas (
            id_venta INTEGER PRIMARY KEY,
            order_id BIGINT NOT NULL UNIQUE,
            id_region INTEGER NOT NULL REFERENCES dim_region(id_region),
            id_country INTEGER NOT NULL REFERENCES dim_country(id_country),
            id_item_type INTEGER NOT NULL REFERENCES dim_item_type(id_item_type),
            id_channel INTEGER NOT NULL REFERENCES dim_sales_channel(id_channel),
            id_priority INTEGER NOT NULL REFERENCES dim_order_priority(id_priority),
            order_date DATE NOT NULL,
            ship_date DATE NOT NULL,
            units_sold INTEGER NOT NULL,
            unit_price DECIMAL(10, 2) NOT NULL,
            unit_cost DECIMAL(10, 2) NOT NULL,
            total_revenue DECIMAL(12, 2) NOT NULL,
            total_cost DECIMAL(12, 2) NOT NULL,
            total_profit DECIMAL(12, 2) NOT NULL
        )
    """)
    con.execute("""
        INSERT INTO fact_ventas (
            id_venta, order_id, id_region, id_country, id_item_type, id_channel, id_priority,
            order_date, ship_date, units_sold, unit_price, unit_cost,
            total_revenue, total_cost, total_profit
        )
        SELECT
            row_number() OVER (ORDER BY s.order_id),
            CAST(s.order_id AS BIGINT),
            r.id_region,
            c.id_country,
            it.id_item_type,
            ch.id_channel,
            p.id_priority,
            s.order_date,
            s.ship_date,
            CAST(s.units_sold AS INTEGER),
            CAST(s.unit_price AS DECIMAL(10,2)),
            CAST(s.unit_cost AS DECIMAL(10,2)),
            CAST(s.total_revenue AS DECIMAL(12,2)),
            CAST(s.total_cost AS DECIMAL(12,2)),
            CAST(s.total_profit AS DECIMAL(12,2))
        FROM staging s
        JOIN dim_region r ON r.region = s.region
        JOIN dim_country c ON c.country = s.country AND c.id_region = r.id_region
        JOIN dim_item_type it ON it.item_type = s.item_type
        JOIN dim_sales_channel ch ON ch.sales_channel = s.sales_channel
        JOIN dim_order_priority p ON p.order_priority = s.order_priority
    """)

    con.execute("""
        CREATE OR REPLACE VIEW ventas AS
        SELECT
            dr.region,
            dc.country,
            dit.item_type,
            dsc.sales_channel,
            dop.order_priority,
            fv.order_date,
            fv.order_id,
            fv.ship_date,
            fv.units_sold,
            fv.unit_price,
            fv.unit_cost,
            fv.total_revenue,
            fv.total_cost,
            fv.total_profit,
            fv.id_venta
        FROM fact_ventas fv
        JOIN dim_region dr ON dr.id_region = fv.id_region
        JOIN dim_country dc ON dc.id_country = fv.id_country
        JOIN dim_item_type dit ON dit.id_item_type = fv.id_item_type
        JOIN dim_sales_channel dsc ON dsc.id_channel = fv.id_channel
        JOIN dim_order_priority dop ON dop.id_priority = fv.id_priority
    """)

    con.execute("DROP TABLE staging")

    tables = [
        "dim_region",
        "dim_country",
        "dim_item_type",
        "dim_sales_channel",
        "dim_order_priority",
        "fact_ventas",
        "ventas",
    ]
    print("\n=== Conteo de registros ===")
    for table in tables:
        count = con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        print(f"  {table}: {count:,}")

    con.close()
    print(f"\nBase de datos creada en: {DB_PATH}")


if __name__ == "__main__":
    main()
