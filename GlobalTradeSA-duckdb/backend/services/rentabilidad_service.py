"""
rentabilidad_service.py — Análisis de rentabilidad agrupado por dimensión.

Funciones expuestas:
    get_rentabilidad_region(conn, date_from=None, date_to=None)  -> list[dict]
    get_rentabilidad_canal(conn, date_from=None, date_to=None)   -> list[dict]
    get_rentabilidad_producto(conn, date_from=None, date_to=None) -> list[dict]

Requisitos cubiertos: 6.1, 6.2, 6.3, 6.4, 6.5, 6.7, 6.9
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
) -> tuple[str, list]:
    """
    Construye la cláusula WHERE para el filtro de fechas y la lista de
    parámetros correspondiente.

    Returns:
        (where_clause, params)
        - where_clause: cadena SQL vacía o con condición(es) de fecha
        - params: lista de valores para los marcadores de posición
    """
    if date_from is not None and date_to is not None:
        return "WHERE order_date >= ? AND order_date <= ?", [date_from, date_to]
    if date_from is not None:
        return "WHERE order_date >= ?", [date_from]
    if date_to is not None:
        return "WHERE order_date <= ?", [date_to]
    return "", []


def _calcular_margen_pct(total_profit: float, total_revenue: float) -> Optional[float]:
    """
    Calcula el margen porcentual con redondeo a 2 decimales.

    Requisito 6.1 — margen_pct = round((total_profit / total_revenue) * 100, 2)
    Requisito 6.7 — null cuando total_revenue = 0

    Args:
        total_profit: Ganancia total de la dimensión.
        total_revenue: Ingresos totales de la dimensión.

    Returns:
        float redondeado a 2 decimales, o None si total_revenue == 0.
    """
    if total_revenue == 0:
        return None
    return round((float(total_profit) / float(total_revenue)) * 100, 2)


def _clasificar_margen(margen_pct: Optional[float]) -> Optional[str]:
    """
    Clasifica el margen porcentual en "alto", "medio" o "bajo".

    Requisito 6.2 — "alto" si margen_pct > 30
    Requisito 6.3 — "medio" si 10 <= margen_pct <= 30
    Requisito 6.9 — "bajo" si margen_pct < 10
    Requisito 6.7 — null si margen_pct es None (total_revenue = 0)

    Args:
        margen_pct: Margen calculado por _calcular_margen_pct(), o None.

    Returns:
        "alto", "medio", "bajo" o None.
    """
    if margen_pct is None:
        return None
    if margen_pct > 30:
        return "alto"
    if margen_pct < 10:
        return "bajo"
    return "medio"


def _build_row(dimension_value: str, row: tuple, include_units_sold: bool = False) -> dict:
    """
    Construye el diccionario de respuesta para una fila de rentabilidad.

    Args:
        dimension_value: Valor de la columna de agrupación (región, canal, item_type).
        row: Tupla de la BD con (total_revenue, total_cost, total_profit[, units_sold]).
        include_units_sold: Si True, incluye el campo units_sold en el resultado.

    Returns:
        dict con dimension, total_revenue, total_cost, total_profit,
        margen_pct, clasificacion_margen y opcionalmente units_sold.
    """
    if include_units_sold:
        total_revenue, total_cost, total_profit, units_sold = row
    else:
        total_revenue, total_cost, total_profit = row
        units_sold = None

    total_revenue_f = float(total_revenue)
    total_cost_f = float(total_cost)
    total_profit_f = float(total_profit)

    margen_pct = _calcular_margen_pct(total_profit_f, total_revenue_f)
    clasificacion = _clasificar_margen(margen_pct)

    result = {
        "dimension": dimension_value,
        "total_revenue": total_revenue_f,
        "total_cost": total_cost_f,
        "total_profit": total_profit_f,
        "margen_pct": margen_pct,
        "clasificacion_margen": clasificacion,
    }

    if include_units_sold:
        result["units_sold"] = int(units_sold) if units_sold is not None else 0

    return result


# ---------------------------------------------------------------------------
# Función pública: get_rentabilidad_region
# ---------------------------------------------------------------------------


def get_rentabilidad_region(
    conn: duckdb.DuckDBPyConnection,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
) -> list[dict]:
    """
    Calcula la rentabilidad agrupada por región.

    Requisito 6.4 — ordenado de mayor a menor total_profit.
    Requisito 6.5 — filtro opcional por rango de fechas (order_date).

    Args:
        conn: Conexión activa obtenida con get_connection().
        date_from: Fecha de inicio del filtro (inclusive). None = sin límite inferior.
        date_to:   Fecha de fin del filtro (inclusive). None = sin límite superior.

    Returns:
        list[dict] con claves:
            dimension (str), total_revenue (float), total_cost (float),
            total_profit (float), margen_pct (float|None),
            clasificacion_margen (str|None)
        Ordenado de mayor a menor total_profit.
    """
    where_clause, params = _build_date_filter(date_from, date_to)

    sql = f"""
        SELECT
            region,
            COALESCE(SUM(total_revenue), 0) AS total_revenue,
            COALESCE(SUM(total_cost),    0) AS total_cost,
            COALESCE(SUM(total_profit),  0) AS total_profit
        FROM ventas
        {where_clause}
        GROUP BY region
        ORDER BY total_profit DESC
    """

    logger.debug(
        "get_rentabilidad_region — date_from=%s, date_to=%s",
        date_from,
        date_to,
    )

    rows = execute_query(conn, sql, params or None, fetch="all")

    if not rows:
        return []

    return [
        _build_row(row[0], row[1:], include_units_sold=False)
        for row in rows
    ]


# ---------------------------------------------------------------------------
# Función pública: get_rentabilidad_canal
# ---------------------------------------------------------------------------


def get_rentabilidad_canal(
    conn: duckdb.DuckDBPyConnection,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
) -> list[dict]:
    """
    Calcula la rentabilidad agrupada por canal de venta (sales_channel).

    Requisito 6.4 — ordenado de mayor a menor total_profit.
    Requisito 6.5 — filtro opcional por rango de fechas (order_date).

    Args:
        conn: Conexión activa obtenida con get_connection().
        date_from: Fecha de inicio del filtro (inclusive). None = sin límite inferior.
        date_to:   Fecha de fin del filtro (inclusive). None = sin límite superior.

    Returns:
        list[dict] con claves:
            dimension (str), total_revenue (float), total_cost (float),
            total_profit (float), margen_pct (float|None),
            clasificacion_margen (str|None)
        Ordenado de mayor a menor total_profit.
    """
    where_clause, params = _build_date_filter(date_from, date_to)

    sql = f"""
        SELECT
            sales_channel,
            COALESCE(SUM(total_revenue), 0) AS total_revenue,
            COALESCE(SUM(total_cost),    0) AS total_cost,
            COALESCE(SUM(total_profit),  0) AS total_profit
        FROM ventas
        {where_clause}
        GROUP BY sales_channel
        ORDER BY total_profit DESC
    """

    logger.debug(
        "get_rentabilidad_canal — date_from=%s, date_to=%s",
        date_from,
        date_to,
    )

    rows = execute_query(conn, sql, params or None, fetch="all")

    if not rows:
        return []

    return [
        _build_row(row[0], row[1:], include_units_sold=False)
        for row in rows
    ]


# ---------------------------------------------------------------------------
# Función pública: get_rentabilidad_producto
# ---------------------------------------------------------------------------


def get_rentabilidad_producto(
    conn: duckdb.DuckDBPyConnection,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
) -> list[dict]:
    """
    Calcula la rentabilidad agrupada por tipo de producto (item_type).

    Incluye ``units_sold`` además de los campos estándar de rentabilidad.

    Requisito 6.4 — ordenado de mayor a menor total_profit.
    Requisito 6.5 — filtro opcional por rango de fechas (order_date).

    Args:
        conn: Conexión activa obtenida con get_connection().
        date_from: Fecha de inicio del filtro (inclusive). None = sin límite inferior.
        date_to:   Fecha de fin del filtro (inclusive). None = sin límite superior.

    Returns:
        list[dict] con claves:
            dimension (str), total_revenue (float), total_cost (float),
            total_profit (float), margen_pct (float|None),
            clasificacion_margen (str|None), units_sold (int)
        Ordenado de mayor a menor total_profit.
    """
    where_clause, params = _build_date_filter(date_from, date_to)

    sql = f"""
        SELECT
            item_type,
            COALESCE(SUM(total_revenue), 0) AS total_revenue,
            COALESCE(SUM(total_cost),    0) AS total_cost,
            COALESCE(SUM(total_profit),  0) AS total_profit,
            COALESCE(SUM(units_sold),    0) AS units_sold
        FROM ventas
        {where_clause}
        GROUP BY item_type
        ORDER BY total_profit DESC
    """

    logger.debug(
        "get_rentabilidad_producto — date_from=%s, date_to=%s",
        date_from,
        date_to,
    )

    rows = execute_query(conn, sql, params or None, fetch="all")

    if not rows:
        return []

    return [
        _build_row(row[0], row[1:], include_units_sold=True)
        for row in rows
    ]
