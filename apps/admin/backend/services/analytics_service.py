"""
analytics_service.py — Consultas analíticas con ClickHouse y fallback DuckDB.
"""
from __future__ import annotations

from datetime import date
from typing import Any, Optional

import duckdb

from shared.services.clickhouse_service import clickhouse_disponible, ejecutar_query, estado_almacen


def _filtro_fechas(desde: Optional[str], hasta: Optional[str]) -> tuple[str, list[Any]]:
    conds: list[str] = []
    params: list[Any] = []
    if desde:
        conds.append("order_date >= ?")
        params.append(desde)
    if hasta:
        conds.append("order_date <= ?")
        params.append(hasta)
    return (" AND ".join(conds), params)


def ranking_proveedores_duckdb(conn, *, desde: Optional[str] = None, hasta: Optional[str] = None, limite: int = 15) -> dict:
    where = ["1=1"]
    params: list[Any] = []
    if desde:
        where.append("oc.fecha >= ?")
        params.append(desde)
    if hasta:
        where.append("oc.fecha <= ?")
        params.append(hasta)
    rows = conn.execute(
        f"""
        SELECT pr.razon_social AS proveedor,
               COALESCE(c.country, '—') AS pais,
               CAST(SUM(COALESCE(oc.total, 0)) AS DOUBLE) AS total_comprado,
               COUNT(DISTINCT oc.id_oc) AS num_oc
        FROM ordenes_compra oc
        JOIN proveedores pr ON pr.id_proveedor = oc.id_proveedor
        LEFT JOIN dim_country c ON c.id_country = pr.id_country
        WHERE {' AND '.join(where)}
        GROUP BY pr.razon_social, c.country
        ORDER BY total_comprado DESC
        LIMIT ?
        """,
        [*params, limite],
    ).fetchall()
    items = [
        {"proveedor": r[0], "pais": r[1], "total_comprado": float(r[2]), "num_oc": int(r[3])}
        for r in rows
    ]
    return {"vista": "ranking-proveedores", "motor": "DuckDB", "items": items}


def ranking_clientes_duckdb(conn, *, limite: int = 15) -> dict:
    rows = conn.execute(
        """
        SELECT dc.nombre_empresa AS cliente,
               dc.pais,
               CAST(SUM(COALESCE(p.total, p.total_pedido, 0)) AS DOUBLE) AS total_comprado,
               CAST(SUM(CASE WHEN p.estado IN ('pagado','preparando','enviado','entregado')
                    THEN COALESCE(p.total, p.total_pedido, 0) ELSE 0 END) AS DOUBLE) AS total_pagado
        FROM dim_cliente dc
        LEFT JOIN pedidos p ON p.id_cliente = dc.id_cliente
        GROUP BY dc.nombre_empresa, dc.pais
        HAVING total_comprado > 0
        ORDER BY total_comprado DESC
        LIMIT ?
        """,
        [limite],
    ).fetchall()
    items = [
        {
            "cliente": r[0],
            "pais": r[1],
            "total_comprado": float(r[2]),
            "total_pagado": float(r[3]),
            "cxc": round(float(r[2]) - float(r[3]), 2),
        }
        for r in rows
    ]
    return {"vista": "ranking-clientes", "motor": "DuckDB", "items": items}


def ventas_por_pais_duckdb(conn, *, desde: Optional[str] = None, hasta: Optional[str] = None, limite: int = 20) -> dict:
    where = ["1=1"]
    params: list[Any] = []
    if desde:
        where.append("v.order_date >= ?")
        params.append(desde)
    if hasta:
        where.append("v.order_date <= ?")
        params.append(hasta)
    rows = conn.execute(
        f"""
        SELECT v.country, v.region,
               CAST(SUM(v.total_revenue) AS DOUBLE) AS total_revenue,
               CAST(SUM(v.units_sold) AS BIGINT) AS units_sold,
               COUNT(DISTINCT v.order_id) AS num_pedidos
        FROM ventas v
        WHERE {' AND '.join(where)}
        GROUP BY v.country, v.region
        ORDER BY total_revenue DESC
        LIMIT ?
        """,
        [*params, limite],
    ).fetchall()
    items = [
        {
            "country": r[0],
            "region": r[1],
            "total_revenue": float(r[2]),
            "units_sold": int(r[3]),
            "num_pedidos": int(r[4]),
        }
        for r in rows
    ]
    return {"vista": "ventas-por-pais", "motor": "DuckDB", "items": items}


def ventas_por_linea_duckdb(conn, *, desde: Optional[str] = None, hasta: Optional[str] = None, limite: int = 20) -> dict:
    where = ["1=1"]
    params: list[Any] = []
    if desde:
        where.append("fv.order_date >= ?")
        params.append(desde)
    if hasta:
        where.append("fv.order_date <= ?")
        params.append(hasta)
    rows = conn.execute(
        f"""
        SELECT COALESCE(l.nombre, it.item_type, 'Sin línea') AS linea,
               CAST(SUM(fv.total_revenue) AS DOUBLE) AS total_revenue,
               CAST(SUM(fv.units_sold) AS BIGINT) AS units_sold
        FROM fact_ventas fv
        JOIN dim_item_type it ON it.id_item_type = fv.id_item_type
        LEFT JOIN dim_producto dp ON dp.id_producto = fv.id_producto
        LEFT JOIN lineas_producto l ON l.id_linea = dp.id_linea
        WHERE {' AND '.join(where)}
        GROUP BY 1
        ORDER BY total_revenue DESC
        LIMIT ?
        """,
        [*params, limite],
    ).fetchall()
    items = [{"linea": r[0], "total_revenue": float(r[1]), "units_sold": int(r[2])} for r in rows]
    return {"vista": "ventas-por-linea", "motor": "DuckDB", "items": items}


def _ch_ranking_proveedores(limite: int) -> dict:
    rows = ejecutar_query(
        f"""
        SELECT proveedor, pais, sum(total_compra) AS total_comprado, sum(num_oc) AS num_oc
        FROM dwh_proveedores GROUP BY proveedor, pais
        ORDER BY total_comprado DESC LIMIT {limite}
        """
    )
    return {"vista": "ranking-proveedores", "motor": "ClickHouse", "items": rows}


def _ch_ranking_clientes(limite: int) -> dict:
    rows = ejecutar_query(
        f"""
        SELECT nombre_cliente AS cliente, pais, total_comprado, total_pagado, cxc
        FROM dwh_clientes ORDER BY total_comprado DESC LIMIT {limite}
        """
    )
    return {"vista": "ranking-clientes", "motor": "ClickHouse", "items": rows}


def _ch_ventas_pais(desde: Optional[str], hasta: Optional[str], limite: int) -> dict:
    cond = "1=1"
    if desde:
        cond += f" AND order_date >= toDate('{desde}')"
    if hasta:
        cond += f" AND order_date <= toDate('{hasta}')"
    rows = ejecutar_query(
        f"""
        SELECT country, region, sum(total_revenue) AS total_revenue,
               sum(units_sold) AS units_sold, count() AS num_pedidos
        FROM dwh_geografia WHERE {cond}
        GROUP BY country, region ORDER BY total_revenue DESC LIMIT {limite}
        """
    )
    return {"vista": "ventas-por-pais", "motor": "ClickHouse", "items": rows}


def _ch_ventas_linea(desde: Optional[str], hasta: Optional[str], limite: int) -> dict:
    cond = "1=1"
    if desde:
        cond += f" AND order_date >= toDate('{desde}')"
    if hasta:
        cond += f" AND order_date <= toDate('{hasta}')"
    rows = ejecutar_query(
        f"""
        SELECT linea, sum(total_revenue) AS total_revenue, sum(units_sold) AS units_sold
        FROM dwh_ventas WHERE {cond}
        GROUP BY linea ORDER BY total_revenue DESC LIMIT {limite}
        """
    )
    return {"vista": "ventas-por-linea", "motor": "ClickHouse", "items": rows}


VISTAS = {
    "ranking-proveedores",
    "ranking-clientes",
    "ventas-por-pais",
    "ventas-por-linea",
    "margen-por-categoria",
    "pedidos-por-estado",
}


def _ch_pedidos_estado(limite: int = 15) -> dict[str, Any]:
    rows = ejecutar_query(
        """
        SELECT estado, cantidad, monto_total
        FROM dwh_pedidos_estado
        ORDER BY cantidad DESC
        LIMIT {limite}
        """.format(limite=int(limite))
    )
    return {
        "vista": "pedidos-por-estado",
        "motor": "ClickHouse",
        "items": [
            {"estado": r.get("estado"), "cantidad": int(r.get("cantidad") or 0), "monto": float(r.get("monto_total") or 0)}
            for r in rows
        ],
    }


def _ch_margen_categoria(desde: Optional[str], hasta: Optional[str], limite: int) -> dict[str, Any]:
    cond = "1=1"
    if desde:
        cond += f" AND order_date >= toDate('{desde}')"
    if hasta:
        cond += f" AND order_date <= toDate('{hasta}')"
    rows = ejecutar_query(
        f"""
        SELECT item_type AS categoria,
               sum(total_revenue) AS ingresos,
               sum(total_profit) AS profit,
               if(sum(total_revenue) > 0, round(sum(total_profit)/sum(total_revenue)*100, 2), 0) AS margen_pct
        FROM dwh_ventas
        WHERE {cond}
        GROUP BY item_type
        ORDER BY ingresos DESC
        LIMIT {int(limite)}
        """
    )
    return {
        "vista": "margen-por-categoria",
        "motor": "ClickHouse",
        "items": [
            {
                "categoria": r.get("categoria"),
                "ingresos": float(r.get("ingresos") or 0),
                "profit": float(r.get("profit") or 0),
                "margen_pct": float(r.get("margen_pct") or 0),
            }
            for r in rows
        ],
    }


def consultar_vista(
    conn: duckdb.DuckDBPyConnection,
    vista: str,
    *,
    desde: Optional[str] = None,
    hasta: Optional[str] = None,
    limite: int = 15,
) -> dict[str, Any]:
    if vista not in VISTAS:
        raise ValueError(f"Vista analítica desconocida: {vista}")

    if clickhouse_disponible():
        try:
            if vista == "ranking-proveedores":
                return _ch_ranking_proveedores(limite)
            if vista == "ranking-clientes":
                return _ch_ranking_clientes(limite)
            if vista == "ventas-por-pais":
                return _ch_ventas_pais(desde, hasta, limite)
            if vista == "ventas-por-linea":
                return _ch_ventas_linea(desde, hasta, limite)
            if vista == "pedidos-por-estado":
                return _ch_pedidos_estado(limite)
            if vista == "margen-por-categoria":
                return _ch_margen_categoria(desde, hasta, limite)
        except Exception:
            pass

    if vista == "ranking-proveedores":
        return ranking_proveedores_duckdb(conn, desde=desde, hasta=hasta, limite=limite)
    if vista == "ranking-clientes":
        return ranking_clientes_duckdb(conn, limite=limite)
    if vista == "ventas-por-pais":
        return ventas_por_pais_duckdb(conn, desde=desde, hasta=hasta, limite=limite)
    if vista == "ventas-por-linea":
        return ventas_por_linea_duckdb(conn, desde=desde, hasta=hasta, limite=limite)
    if vista == "pedidos-por-estado":
        rows = conn.execute(
            """
            SELECT estado, COUNT(*) AS n, CAST(SUM(COALESCE(total, total_pedido, 0)) AS DOUBLE) AS monto
            FROM pedidos GROUP BY estado ORDER BY n DESC
            """
        ).fetchall()
        return {
            "vista": vista,
            "motor": "DuckDB",
            "items": [{"estado": r[0], "cantidad": int(r[1]), "monto": float(r[2])} for r in rows],
        }
    if vista == "margen-por-categoria":
        rows = conn.execute(
            """
            SELECT item_type AS categoria,
                   CAST(SUM(total_revenue) AS DOUBLE) AS ingresos,
                   CAST(SUM(total_profit) AS DOUBLE) AS profit,
                   CASE WHEN SUM(total_revenue) > 0
                        THEN ROUND(SUM(total_profit)/SUM(total_revenue)*100, 2) ELSE 0 END AS margen_pct
            FROM ventas GROUP BY item_type ORDER BY ingresos DESC LIMIT ?
            """,
            [limite],
        ).fetchall()
        return {
            "vista": vista,
            "motor": "DuckDB",
            "items": [
                {"categoria": r[0], "ingresos": float(r[1]), "profit": float(r[2]), "margen_pct": float(r[3])}
                for r in rows
            ],
        }
    raise ValueError(vista)


def almacen_estado() -> dict[str, Any]:
    return estado_almacen()
