"""
generador_service.py — Generación masiva vectorizada en fact_ventas (NumPy + PyArrow + bulk INSERT).
"""

from __future__ import annotations

import logging
import time
from typing import Any

import duckdb
import numpy as np
import pyarrow as pa

from backend.database import execute_query, notify_db_changed

logger = logging.getLogger(__name__)

_START = np.datetime64("2020-01-01", "D")
_END = np.datetime64("2026-12-31", "D")
_DAY_RANGE = int((_END - _START) / np.timedelta64(1, "D")) + 1
_INSERT_SQL = """
    INSERT INTO fact_ventas (
        id_venta, order_id, id_region, id_country, id_item_type, id_channel, id_priority,
        order_date, ship_date, units_sold, unit_price, unit_cost,
        total_revenue, total_cost, total_profit, origen
    )
    SELECT
        id_venta, order_id, id_region, id_country, id_item_type, id_channel, id_priority,
        order_date, ship_date, units_sold, unit_price, unit_cost,
        total_revenue, total_cost, total_profit, 'sintetico'
    FROM _gen_bulk
"""
_BATCH_SIZE = 50_000


def _load_masters(conn: duckdb.DuckDBPyConnection) -> dict[str, np.ndarray]:
    countries = execute_query(
        conn, "SELECT id_country, id_region FROM dim_country", fetch="all"
    ) or []
    items = execute_query(
        conn,
        "SELECT id_item_type, unit_price, unit_cost FROM dim_item_type",
        fetch="all",
    ) or []
    channels = execute_query(conn, "SELECT id_channel FROM dim_sales_channel", fetch="all") or []
    priorities = execute_query(conn, "SELECT id_priority FROM dim_order_priority", fetch="all") or []
    return {
        "countries": np.array(countries, dtype=np.int64),
        "items": np.array(items, dtype=np.float64),
        "channels": np.array([r[0] for r in channels], dtype=np.int64),
        "priorities": np.array([r[0] for r in priorities], dtype=np.int64),
    }


def _build_arrow_batch(
    masters: dict[str, np.ndarray],
    max_id: int,
    max_order: int,
    n: int,
    rng: np.random.Generator,
) -> pa.Table:
    ci = rng.integers(0, len(masters["countries"]), n)
    ii = rng.integers(0, len(masters["items"]), n)
    ch_i = rng.integers(0, len(masters["channels"]), n)
    pr_i = rng.integers(0, len(masters["priorities"]), n)

    countries = masters["countries"][ci]
    items = masters["items"][ii]

    units = rng.integers(1, 501, size=n, dtype=np.int32)
    unit_price = items[:, 1]
    unit_cost = items[:, 2]
    total_revenue = np.round(unit_price * units, 2)
    total_cost = np.round(unit_cost * units, 2)
    total_profit = np.round(total_revenue - total_cost, 2)

    day_offsets = rng.integers(0, _DAY_RANGE, size=n, dtype=np.int32)
    order_dates = (_START + day_offsets.astype("timedelta64[D]")).astype("datetime64[D]")
    ship_dates = (
        order_dates + rng.integers(1, 31, size=n, dtype=np.int32).astype("timedelta64[D]")
    )

    return pa.table({
        "id_venta": pa.array(np.arange(max_id + 1, max_id + 1 + n, dtype=np.int64)),
        "order_id": pa.array(np.arange(max_order + 1, max_order + 1 + n, dtype=np.int64)),
        "id_region": pa.array(countries[:, 1], type=pa.int64()),
        "id_country": pa.array(countries[:, 0], type=pa.int64()),
        "id_item_type": pa.array(items[:, 0], type=pa.int64()),
        "id_channel": pa.array(masters["channels"][ch_i], type=pa.int64()),
        "id_priority": pa.array(masters["priorities"][pr_i], type=pa.int64()),
        "order_date": pa.array(order_dates),
        "ship_date": pa.array(ship_dates),
        "units_sold": pa.array(units, type=pa.int32()),
        "unit_price": pa.array(unit_price, type=pa.float64()),
        "unit_cost": pa.array(unit_cost, type=pa.float64()),
        "total_revenue": pa.array(total_revenue, type=pa.float64()),
        "total_cost": pa.array(total_cost, type=pa.float64()),
        "total_profit": pa.array(total_profit, type=pa.float64()),
    })


def generar_ventas(conn: duckdb.DuckDBPyConnection, cantidad: int = 100_000) -> dict[str, Any]:
    t0 = time.perf_counter()

    masters = _load_masters(conn)
    if masters["countries"].size == 0 or masters["items"].size == 0:
        raise ValueError("Las tablas maestras están vacías. Ejecute scripts/cargar_duckdb.py primero.")

    row = execute_query(
        conn,
        "SELECT "
        "COALESCE(MAX(CASE WHEN order_id >= 50000000000000 AND order_id < 60000000000000 "
        "THEN order_id END), 50000000000000), "
        "COALESCE(MAX(id_venta), 0) FROM fact_ventas",
        fetch="one",
    )
    max_order, max_id = int(row[0]), int(row[1])

    max_order, max_id = int(row[0]), int(row[1])

    rng = np.random.default_rng()
    restante = cantidad
    insertadas = 0

    while restante > 0:
        n = min(_BATCH_SIZE, restante)
        batch = _build_arrow_batch(masters, max_id, max_order, n, rng)
        conn.execute("BEGIN TRANSACTION")
        try:
            conn.register("_gen_bulk", batch)
            try:
                conn.execute(_INSERT_SQL)
            finally:
                conn.unregister("_gen_bulk")
            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise

        max_id += n
        max_order += n
        insertadas += n
        restante -= n
        logger.info("Generadas %d / %d ventas sintéticas…", insertadas, cantidad)

    elapsed = time.perf_counter() - t0
    rps = round(insertadas / elapsed, 3) if elapsed > 0 else 0.0

    notify_db_changed(conn)
    total_ventas = int(conn.execute("SELECT COUNT(*) FROM fact_ventas").fetchone()[0])
    logger.info("Generadas %d ventas en %.3f s (%.0f reg/s)", insertadas, elapsed, rps)

    return {
        "registros": insertadas,
        "inserted": insertadas,
        "total_ventas": total_ventas,
        "tiempo_segundos": round(elapsed, 3),
        "registros_por_segundo": rps,
    }
