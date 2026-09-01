"""
ventas_service.py — Consultas paginadas, exportación y truncate de fact_ventas.
"""

from __future__ import annotations

import csv
import io
import logging
import time
from typing import Any, Optional

import duckdb
from fastapi import HTTPException

from backend.database import execute_query, notify_db_changed

logger = logging.getLogger(__name__)

_VENTAS_SORT_WHITELIST: frozenset[str] = frozenset(
    {
        "region", "country", "item_type", "sales_channel", "order_priority",
        "order_date", "order_id", "ship_date", "units_sold", "unit_price",
        "unit_cost", "total_revenue", "total_cost", "total_profit", "id_venta",
    }
)

_CSV_COLUMNS: list[str] = [
    "region", "country", "item_type", "sales_channel", "order_priority",
    "order_date", "order_id", "ship_date", "units_sold", "unit_price",
    "unit_cost", "total_revenue", "total_cost", "total_profit",
]

_SELECT_COLUMNS: str = ", ".join(_CSV_COLUMNS)
_LIST_COLUMNS: list[str] = ["id_venta", *_CSV_COLUMNS]
_LIST_SELECT: str = ", ".join(_LIST_COLUMNS)


def _validate_sort_column(sort_by: str) -> str:
    normalized = sort_by.strip().lower()
    if normalized not in _VENTAS_SORT_WHITELIST:
        raise HTTPException(status_code=400, detail=f"Columna '{sort_by}' no válida.")
    return normalized


def _validate_sort_order(sort_order: str) -> str:
    normalized = sort_order.strip().lower()
    if normalized not in {"asc", "desc"}:
        raise HTTPException(status_code=400, detail="sort_order debe ser 'asc' o 'desc'.")
    return normalized


def _build_where_clause(filters: dict) -> tuple[str, list[Any]]:
    conditions: list[str] = []
    params: list[Any] = []

    for filter_key, column_name in [
        ("region", "region"),
        ("country", "country"),
        ("item_type", "item_type"),
        ("sales_channel", "sales_channel"),
        ("order_priority", "order_priority"),
    ]:
        value = filters.get(filter_key)
        if value is not None and value != "":
            conditions.append(f"{column_name} = ?")
            params.append(value)

    if filters.get("order_date_from") is not None:
        conditions.append("order_date >= ?")
        params.append(filters["order_date_from"])
    if filters.get("order_date_to") is not None:
        conditions.append("order_date <= ?")
        params.append(filters["order_date_to"])

    # Busqueda libre por texto: order_id, pais, region o tipo de producto.
    q = filters.get("q")
    if q is not None and str(q).strip() != "":
        like = f"%{str(q).strip().lower()}%"
        conditions.append(
            "(CAST(order_id AS VARCHAR) LIKE ? OR lower(country) LIKE ? "
            "OR lower(region) LIKE ? OR lower(item_type) LIKE ?)"
        )
        params.extend([like, like, like, like])

    where_clause = ("WHERE " + " AND ".join(conditions)) if conditions else ""
    return where_clause, params


def _rows_to_dicts(rows: list[tuple], columns: list[str] | None = None) -> list[dict]:
    cols = columns or _CSV_COLUMNS
    return [dict(zip(cols, row)) for row in rows]


def _row_to_dict(row: tuple, columns: list[str]) -> dict:
    return dict(zip(columns, row))


def _calc_totals(units: int, unit_price: float, unit_cost: float) -> tuple[float, float, float]:
    revenue = round(float(unit_price) * units, 2)
    cost = round(float(unit_cost) * units, 2)
    profit = round(revenue - cost, 2)
    return revenue, cost, profit


def _resolve_dimension_ids(
    conn: duckdb.DuckDBPyConnection,
    region: str,
    country: str,
    item_type: str,
    sales_channel: str,
    order_priority: str,
) -> dict[str, int]:
    row = execute_query(
        conn,
        """
        SELECT r.id_region, c.id_country, it.id_item_type, ch.id_channel, p.id_priority
        FROM dim_region r
        JOIN dim_country c ON c.country = ? AND c.id_region = r.id_region
        JOIN dim_item_type it ON it.item_type = ?
        JOIN dim_sales_channel ch ON ch.sales_channel = ?
        JOIN dim_order_priority p ON p.order_priority = ?
        WHERE r.region = ?
        """,
        (country, item_type, sales_channel, order_priority, region),
        fetch="one",
    )
    if row is None:
        raise HTTPException(
            status_code=400,
            detail="No se encontró la combinación región/país/producto/canal/prioridad en las dimensiones.",
        )
    return {
        "id_region": int(row[0]),
        "id_country": int(row[1]),
        "id_item_type": int(row[2]),
        "id_channel": int(row[3]),
        "id_priority": int(row[4]),
    }


def get_venta_by_id(conn: duckdb.DuckDBPyConnection, id_venta: int) -> dict:
    row = execute_query(
        conn,
        f"SELECT {_LIST_SELECT} FROM ventas WHERE id_venta = ?",
        (id_venta,),
        fetch="one",
    )
    if row is None:
        raise HTTPException(status_code=404, detail=f"Venta id_venta={id_venta} no encontrada.")
    return _row_to_dict(row, _LIST_COLUMNS)


def create_venta(conn: duckdb.DuckDBPyConnection, data: dict) -> dict:
    raw_order_id = data.get("order_id")
    if raw_order_id in (None, ""):
        max_oid = execute_query(
            conn, "SELECT COALESCE(MAX(order_id), 0) FROM fact_ventas", fetch="one"
        )[0]
        order_id = int(max_oid) + 1
    else:
        order_id = int(raw_order_id)
    exists = execute_query(
        conn, "SELECT 1 FROM fact_ventas WHERE order_id = ?", (order_id,), fetch="one"
    )
    if exists:
        raise HTTPException(status_code=409, detail=f"order_id {order_id} ya existe.")

    ids = _resolve_dimension_ids(
        conn,
        str(data["region"]).strip(),
        str(data["country"]).strip(),
        str(data["item_type"]).strip(),
        str(data["sales_channel"]).strip(),
        str(data["order_priority"]).strip(),
    )

    units = int(data["units_sold"])
    item_row = execute_query(
        conn,
        "SELECT unit_price, unit_cost FROM dim_item_type WHERE id_item_type = ?",
        (ids["id_item_type"],),
        fetch="one",
    )
    unit_price = float(data.get("unit_price") or item_row[0])
    unit_cost = float(data.get("unit_cost") or item_row[1])
    total_revenue, total_cost, total_profit = _calc_totals(units, unit_price, unit_cost)

    max_id = execute_query(conn, "SELECT COALESCE(MAX(id_venta), 0) FROM fact_ventas", fetch="one")[0]
    new_id = int(max_id) + 1

    execute_query(
        conn,
        """
        INSERT INTO fact_ventas (
            id_venta, order_id, id_region, id_country, id_item_type, id_channel, id_priority,
            order_date, ship_date, units_sold, unit_price, unit_cost,
            total_revenue, total_cost, total_profit
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            new_id, order_id, ids["id_region"], ids["id_country"], ids["id_item_type"],
            ids["id_channel"], ids["id_priority"],
            data["order_date"], data["ship_date"], units,
            unit_price, unit_cost, total_revenue, total_cost, total_profit,
        ),
        fetch="none",
    )
    notify_db_changed(conn)
    return get_venta_by_id(conn, new_id)


def update_venta(conn: duckdb.DuckDBPyConnection, id_venta: int, data: dict) -> dict:
    current = execute_query(
        conn, "SELECT order_id FROM fact_ventas WHERE id_venta = ?", (id_venta,), fetch="one"
    )
    if current is None:
        raise HTTPException(status_code=404, detail=f"Venta id_venta={id_venta} no encontrada.")

    raw_order_id = data.get("order_id")
    if raw_order_id in (None, ""):
        order_id = int(current[0])
    else:
        order_id = int(raw_order_id)
        if order_id != int(current[0]):
            dup = execute_query(
                conn, "SELECT 1 FROM fact_ventas WHERE order_id = ? AND id_venta <> ?",
                (order_id, id_venta), fetch="one",
            )
            if dup:
                raise HTTPException(status_code=409, detail=f"order_id {order_id} ya existe.")

    ids = _resolve_dimension_ids(
        conn,
        str(data["region"]).strip(),
        str(data["country"]).strip(),
        str(data["item_type"]).strip(),
        str(data["sales_channel"]).strip(),
        str(data["order_priority"]).strip(),
    )

    units = int(data["units_sold"])
    item_row = execute_query(
        conn,
        "SELECT unit_price, unit_cost FROM dim_item_type WHERE id_item_type = ?",
        (ids["id_item_type"],),
        fetch="one",
    )
    if item_row is None:
        raise HTTPException(status_code=400, detail="Tipo de producto no encontrado en maestras.")
    unit_price = float(data.get("unit_price") or item_row[0])
    unit_cost = float(data.get("unit_cost") or item_row[1])
    total_revenue, total_cost, total_profit = _calc_totals(units, unit_price, unit_cost)

    # DuckDB falla con UPDATE en columnas UNIQUE/indexadas (order_id, FKs, order_date+índice).
    # Reemplazo atómico: DELETE + INSERT conservando id_venta.
    execute_query(conn, "DELETE FROM fact_ventas WHERE id_venta = ?", (id_venta,), fetch="none")
    execute_query(
        conn,
        """
        INSERT INTO fact_ventas (
            id_venta, order_id, id_region, id_country, id_item_type, id_channel, id_priority,
            order_date, ship_date, units_sold, unit_price, unit_cost,
            total_revenue, total_cost, total_profit
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            id_venta, order_id, ids["id_region"], ids["id_country"], ids["id_item_type"],
            ids["id_channel"], ids["id_priority"],
            data["order_date"], data["ship_date"], units,
            unit_price, unit_cost, total_revenue, total_cost, total_profit,
        ),
        fetch="none",
    )
    notify_db_changed(conn)
    return get_venta_by_id(conn, id_venta)


def delete_venta(conn: duckdb.DuckDBPyConnection, id_venta: int) -> dict:
    row = execute_query(
        conn, "SELECT order_id FROM fact_ventas WHERE id_venta = ?", (id_venta,), fetch="one"
    )
    if row is None:
        raise HTTPException(status_code=404, detail=f"Venta id_venta={id_venta} no encontrada.")
    execute_query(conn, "DELETE FROM fact_ventas WHERE id_venta = ?", (id_venta,), fetch="none")
    notify_db_changed(conn)
    return {"message": "Venta eliminada correctamente", "id_venta": id_venta, "order_id": int(row[0])}


def query_ventas(
    conn: duckdb.DuckDBPyConnection,
    filters: dict,
    page: int,
    page_size: int,
    sort_by: str = "order_id",
    sort_order: str = "asc",
) -> dict:
    safe_sort_by = _validate_sort_column(sort_by)
    safe_sort_order = _validate_sort_order(sort_order)
    where_clause, params = _build_where_clause(filters)

    count_sql = f"SELECT COUNT(*) FROM ventas {where_clause}"
    count_row = execute_query(conn, count_sql, params or None, fetch="one")
    total: int = count_row[0] if count_row else 0

    if total == 0:
        return {"data": [], "page": 1, "page_size": page_size, "total": 0}

    offset = (page - 1) * page_size
    data_sql = (
        f"SELECT {_LIST_SELECT} FROM ventas {where_clause} "
        f"ORDER BY {safe_sort_by} {safe_sort_order} LIMIT ? OFFSET ?"
    )
    rows = execute_query(conn, data_sql, list(params) + [page_size, offset], fetch="all")

    return {
        "data": _rows_to_dicts(rows, _LIST_COLUMNS) if rows else [],
        "page": page,
        "page_size": page_size,
        "total": total,
    }


def export_ventas_csv(
    conn: duckdb.DuckDBPyConnection,
    filters: dict,
    sort_by: str = "order_id",
    sort_order: str = "asc",
) -> str:
    safe_sort_by = _validate_sort_column(sort_by)
    safe_sort_order = _validate_sort_order(sort_order)
    where_clause, params = _build_where_clause(filters)

    export_sql = (
        f"SELECT {_SELECT_COLUMNS} FROM ventas {where_clause} "
        f"ORDER BY {safe_sort_by} {safe_sort_order}"
    )
    rows = execute_query(conn, export_sql, params or None, timeout_seconds=15, fetch="all")

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(_CSV_COLUMNS)
    if rows:
        writer.writerows(rows)
    return output.getvalue()


def truncate_fact_ventas(conn: duckdb.DuckDBPyConnection) -> dict[str, Any]:
    """Elimina todos los registros de fact_ventas (TRUNCATE rápido en DuckDB)."""
    t0 = time.perf_counter()
    count_row = execute_query(conn, "SELECT COUNT(*) FROM fact_ventas", fetch="one")
    deleted = int(count_row[0]) if count_row else 0
    execute_query(conn, "TRUNCATE TABLE fact_ventas", fetch="none")
    notify_db_changed(conn)
    elapsed = time.perf_counter() - t0
    logger.info("Truncate fact_ventas: %d registros en %.3f s", deleted, elapsed)
    return {"eliminados": deleted, "tiempo_segundos": round(elapsed, 3)}
