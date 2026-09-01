"""
kpi_service.py — Cálculo de KPIs y datos de gráficas para el Dashboard.

Funciones expuestas:
    get_kpis(conn, date_from=None, date_to=None) -> dict
    get_charts_data(conn, date_from=None, date_to=None) -> dict
    get_top_paises(conn, date_from=None, date_to=None) -> list

Requisitos cubiertos: 2.1, 2.3, 2.4, 2.5, 2.6, 2.7
"""

from __future__ import annotations

import logging
from datetime import date
from typing import Optional

import duckdb

from backend.database import execute_query

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Helpers internos
# ---------------------------------------------------------------------------


def _build_date_filter(
    date_from: Optional[date],
    date_to: Optional[date],
    region: Optional[str] = None,
    origen: Optional[str] = None,
) -> tuple[str, list]:
    """
    Construye la cláusula WHERE para filtros de fecha, región y origen.
    """
    conditions = []
    params = []

    if date_from is not None:
        conditions.append("order_date >= ?")
        params.append(date_from)
    if date_to is not None:
        conditions.append("order_date <= ?")
        params.append(date_to)
    if region:
        conditions.append("region = ?")
        params.append(region)
    if origen and origen in ("historico", "portal"):
        conditions.append("origen = ?")
        params.append(origen)

    where_clause = ("WHERE " + " AND ".join(conditions)) if conditions else ""
    return where_clause, params


# ---------------------------------------------------------------------------
# Función pública: get_kpis
# ---------------------------------------------------------------------------


def get_kpis(
    conn: duckdb.DuckDBPyConnection,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    region: Optional[str] = None,
    origen: Optional[str] = None,
) -> dict:
    """
    Calcula los KPIs globales sobre la tabla ``ventas``.
    Acepta filtro opcional por rango de fechas y región.
    """
    where_clause, params = _build_date_filter(date_from, date_to, region, origen)

    sql = f"""
        SELECT
            COALESCE(SUM(total_revenue), 0) AS total_revenue,
            COALESCE(SUM(total_cost),    0) AS total_cost,
            COALESCE(SUM(total_profit),  0) AS total_profit,
            COALESCE(SUM(units_sold),    0) AS units_sold
        FROM ventas
        {where_clause}
    """

    logger.debug(
        "get_kpis — date_from=%s, date_to=%s",
        date_from,
        date_to,
    )

    row = execute_query(conn, sql, params or None, fetch="one")

    # row puede ser None si la tabla está vacía y COALESCE no aplica
    if row is None:
        return {
            "total_revenue": 0.0,
            "total_cost": 0.0,
            "total_profit": 0.0,
            "units_sold": 0,
        }

    total_revenue, total_cost, total_profit, units_sold = row
    return {
        "total_revenue": float(total_revenue),
        "total_cost": float(total_cost),
        "total_profit": float(total_profit),
        "units_sold": int(units_sold),
    }


# ---------------------------------------------------------------------------
# Función pública: get_charts_data
# ---------------------------------------------------------------------------


def get_charts_data(
    conn: duckdb.DuckDBPyConnection,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    region: Optional[str] = None,
    origen: Optional[str] = None,
) -> dict:
    """
    Calcula los datos de las tres gráficas de barras del Dashboard.
    Acepta filtro opcional por rango de fechas y región.
    """
    where_clause, params = _build_date_filter(date_from, date_to, region, origen)

    logger.debug(
        "get_charts_data — date_from=%s, date_to=%s",
        date_from,
        date_to,
    )

    # --- Gráfica 1: por región (Requisito 2.3) ---
    sql_region = f"""
        SELECT
            region                      AS label,
            COALESCE(SUM(total_revenue), 0) AS total_revenue
        FROM ventas
        {where_clause}
        GROUP BY region
        ORDER BY total_revenue DESC
    """
    rows_region = execute_query(conn, sql_region, params or None, fetch="all")

    # --- Gráfica 2: por canal de venta (Requisito 2.4) ---
    sql_canal = f"""
        SELECT
            sales_channel               AS label,
            COALESCE(SUM(total_revenue), 0) AS total_revenue
        FROM ventas
        {where_clause}
        GROUP BY sales_channel
        ORDER BY total_revenue DESC
    """
    rows_canal = execute_query(conn, sql_canal, params or None, fetch="all")

    # --- Gráfica 3: por tipo de producto (Requisito 2.5) ---
    sql_item = f"""
        SELECT
            item_type                   AS label,
            COALESCE(SUM(total_revenue), 0) AS total_revenue
        FROM ventas
        {where_clause}
        GROUP BY item_type
        ORDER BY total_revenue DESC
    """
    rows_item = execute_query(conn, sql_item, params or None, fetch="all")

    # --- Gráfica: ventas por catálogo (categoría). Requisito panel de ventas ---
    sql_cat = f"""
        SELECT
            dimension_categoria          AS label,
            COALESCE(SUM(total_revenue), 0) AS total_revenue
        FROM ventas
        {where_clause}
        GROUP BY dimension_categoria
        ORDER BY total_revenue DESC
    """
    rows_cat = execute_query(conn, sql_cat, params or None, fetch="all")

    def _to_list(rows) -> list[dict]:
        if not rows:
            return []
        return [
            {"label": row[0], "total_revenue": float(row[1])}
            for row in rows
        ]

    # Revenue + Profit por producto
    sql_rp = f"""
        SELECT item_type AS label,
               COALESCE(SUM(total_revenue), 0),
               COALESCE(SUM(total_profit), 0)
        FROM ventas {where_clause}
        GROUP BY item_type ORDER BY 2 DESC
    """
    rows_rp = execute_query(conn, sql_rp, params or None, fetch="all")

    # Evolución mensual
    sql_mes = f"""
        SELECT strftime(CAST(order_date AS DATE), '%Y-%m') AS label,
               COALESCE(SUM(total_revenue), 0)
        FROM ventas {where_clause}
        GROUP BY 1 ORDER BY 1
    """
    rows_mes = execute_query(conn, sql_mes, params or None, fetch="all")

    # Top 10 países por revenue
    sql_top10 = f"""
        SELECT country AS label, COALESCE(SUM(total_revenue), 0)
        FROM ventas {where_clause}
        GROUP BY country ORDER BY 2 DESC LIMIT 10
    """
    rows_top10 = execute_query(conn, sql_top10, params or None, fetch="all")

    sql_origen = f"""
        SELECT COALESCE(origen, 'historico') AS label, COALESCE(SUM(total_revenue), 0)
        FROM ventas {where_clause}
        GROUP BY 1 ORDER BY 2 DESC
    """
    rows_origen = execute_query(conn, sql_origen, params or None, fetch="all")

    def _profit_list(rows) -> list[dict]:
        if not rows:
            return []
        return [
            {"label": r[0], "total_revenue": float(r[1]), "total_profit": float(r[2])}
            for r in rows
        ]

    return {
        "por_region": _to_list(rows_region),
        "por_canal": _to_list(rows_canal),
        "por_item_type": _to_list(rows_item),
        "por_categoria": _to_list(rows_cat),
        "producto_revenue_profit": _profit_list(rows_rp),
        "ventas_por_mes": _to_list(rows_mes),
        "top10_paises_revenue": _to_list(rows_top10),
        "por_origen": _to_list(rows_origen),
    }


# ---------------------------------------------------------------------------
# Función pública: get_top_paises
# ---------------------------------------------------------------------------


def get_top_paises(
    conn: duckdb.DuckDBPyConnection,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    region: Optional[str] = None,
    origen: Optional[str] = None,
) -> list[dict]:
    """
    Devuelve el top 5 de países por ``total_profit``.
    Acepta filtro opcional por rango de fechas y región.
    """
    where_clause, params = _build_date_filter(date_from, date_to, region, origen)

    logger.debug(
        "get_top_paises — date_from=%s, date_to=%s",
        date_from,
        date_to,
    )

    sql = f"""
        SELECT
            country,
            region,
            COALESCE(SUM(total_profit),  0) AS total_profit,
            COALESCE(SUM(total_revenue), 0) AS total_revenue
        FROM ventas
        {where_clause}
        GROUP BY country, region
        ORDER BY total_profit DESC, total_revenue DESC
        LIMIT 5
    """

    rows = execute_query(conn, sql, params or None, fetch="all")

    if not rows:
        return []

    result = []
    for row in rows:
        country, region, total_profit, total_revenue = row
        total_profit_f  = float(total_profit)
        total_revenue_f = float(total_revenue)
        margen_pct = (
            round((total_profit_f / total_revenue_f) * 100, 2)
            if total_revenue_f > 0 else None
        )
        result.append({
            "country":       country,
            "region":        region,
            "total_profit":  total_profit_f,
            "total_revenue": total_revenue_f,
            "margen_pct":    margen_pct,
        })
    return result
