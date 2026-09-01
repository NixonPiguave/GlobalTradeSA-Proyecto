"""
rentabilidad_service.py — Análisis de rentabilidad agrupado por dimensión.

Funciones expuestas:
    get_rentabilidad_region(conn, date_from=None, date_to=None)  -> list[dict]
    get_rentabilidad_canal(conn, date_from=None, date_to=None)   -> list[dict]
    get_rentabilidad_producto(conn, date_from=None, date_to=None) -> list[dict]
    get_rentabilidad_categoria(conn, date_from=None, date_to=None) -> list[dict]

Requisitos cubiertos: 6.1, 6.2, 6.3, 6.4, 6.5, 6.7, 6.9
"""

from __future__ import annotations

import logging
from datetime import date
from typing import Optional

import duckdb

from backend.database import execute_query
from shared.database.connection import column_exists

logger = logging.getLogger(__name__)

_CATEGORIAS_EXCLUIDAS = ("peperoni", "pepperoni")


def _filtro_fechas_fact(alias: str, date_from: Optional[date], date_to: Optional[date]) -> tuple[str, list]:
    """Filtro de fechas para tablas fact_ventas (alias opcional, ej. fv.)."""
    prefix = f"{alias}." if alias else ""
    if date_from is not None and date_to is not None:
        return f"AND {prefix}order_date >= ? AND {prefix}order_date <= ?", [date_from, date_to]
    if date_from is not None:
        return f"AND {prefix}order_date >= ?", [date_from]
    if date_to is not None:
        return f"AND {prefix}order_date <= ?", [date_to]
    return "", []


def _es_categoria_valida(nombre: str) -> bool:
    n = (nombre or "").strip().lower()
    if not n or n in _CATEGORIAS_EXCLUIDAS:
        return False
    return True

# ---------------------------------------------------------------------------
# Helpers internos
# ---------------------------------------------------------------------------


def _append_where(where_clause: str, extra: str) -> str:
    if where_clause:
        return f"{where_clause} AND {extra}"
    return f"WHERE {extra}"


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
    Rentabilidad por SKU del catálogo B2B: todos los productos activos con sus
    ventas del portal (fact_ventas con id_producto). Los sin ventas aparecen en 0.
    """
    date_sql, date_params = _filtro_fechas_fact("fv", date_from, date_to)
    activo_sql = (
        "AND COALESCE(dp.activo, true) = true"
        if column_exists(conn, "dim_producto", "activo")
        else ""
    )

    sql = f"""
        SELECT
            dp.nombre_producto,
            COALESCE(SUM(fv.total_revenue), 0) AS total_revenue,
            COALESCE(SUM(fv.total_cost),    0) AS total_cost,
            COALESCE(SUM(fv.total_profit),  0) AS total_profit,
            COALESCE(SUM(fv.units_sold),    0) AS units_sold
        FROM dim_producto dp
        LEFT JOIN fact_ventas fv
          ON fv.id_producto = dp.id_producto
          {date_sql}
        WHERE lower(COALESCE(dp.nombre_producto, '')) NOT IN ('peperoni', 'pepperoni')
          {activo_sql}
        GROUP BY dp.id_producto, dp.nombre_producto
        ORDER BY total_profit DESC, dp.nombre_producto
    """

    logger.debug(
        "get_rentabilidad_producto — date_from=%s, date_to=%s",
        date_from,
        date_to,
    )

    rows = execute_query(conn, sql, date_params or None, fetch="all")

    if not rows:
        return []

    return [
        _build_row(row[0], row[1:], include_units_sold=True)
        for row in rows
    ]


def get_rentabilidad_categoria(
    conn: duckdb.DuckDBPyConnection,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
) -> list[dict]:
    """
    Rentabilidad agrupada por categoría de catálogo (categorias.nombre).
    Las ventas del portal se acumulan en la categoría del producto (ej. Congelados Premium).
    El histórico parquet usa el tipo de producto / categoría vinculada.
    """
    where_clause, params = _build_date_filter(date_from, date_to)

    sql = f"""
        SELECT
            dimension_categoria,
            COALESCE(SUM(total_revenue), 0) AS total_revenue,
            COALESCE(SUM(total_cost),    0) AS total_cost,
            COALESCE(SUM(total_profit),  0) AS total_profit,
            COALESCE(SUM(units_sold),    0) AS units_sold
        FROM ventas v
        {where_clause}
        {"AND" if where_clause else "WHERE"} lower(dimension_categoria) NOT IN ('peperoni', 'pepperoni')
        GROUP BY dimension_categoria
        HAVING ABS(COALESCE(SUM(total_revenue), 0)) >= 0.01
            OR ABS(COALESCE(SUM(total_profit), 0)) >= 0.01
        ORDER BY total_profit DESC
    """

    rows = execute_query(conn, sql, params or None, fetch="all")
    if not rows:
        return []
    out = []
    for row in rows:
        if not _es_categoria_valida(row[0]):
            continue
        cat_row = execute_query(
            conn,
            """
            SELECT activo FROM categorias
            WHERE lower(nombre) = lower(?)
            LIMIT 1
            """,
            (row[0],),
            fetch="one",
        )
        if cat_row is not None and not bool(cat_row[0]):
            continue
        out.append(_build_row(row[0], row[1:], include_units_sold=True))
    return out
