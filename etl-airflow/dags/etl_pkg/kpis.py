"""kpis.py — Tablas analíticas de los informes compuestos y de la sección de
KPIs del dashboard. Cada ejecución del ETL las reconstruye desde fact_ventas
(operación ligera: se agregan ~1 M de filas en segundos).

Tablas creadas (CREATE OR REPLACE, deterministas):
  anal_kpis               catálogo de KPI con su valor actual (dashboard)
  anal_ventas_diarias     por fecha y origen (histórico / portal)
  anal_ventas_region      por región
  anal_ventas_pais        por país
  anal_ventas_categoria   por categoría (item_type)
  anal_ventas_canal       por canal
  anal_ventas_prioridad   por prioridad de pedido
  anal_ventas_producto    top SKU (une dim_producto)
  anal_pedidos_por_estado pedidos B2B por estado
"""
from __future__ import annotations

DEFINICIONES = [
    (
        "anal_ventas_region",
        """
        SELECT r.id_region, r.region,
               COUNT(*) AS pedidos,
               SUM(f.units_sold) AS unidades,
               SUM(f.total_revenue) AS ingresos,
               SUM(f.total_profit) AS profit
        FROM fact_ventas f
        JOIN dim_region r ON r.id_region = f.id_region
        GROUP BY r.id_region, r.region
        """,
    ),
    (
        "anal_ventas_pais",
        """
        SELECT c.id_country, c.country, r.region,
               COUNT(*) AS pedidos,
               SUM(f.units_sold) AS unidades,
               SUM(f.total_revenue) AS ingresos,
               SUM(f.total_profit) AS profit
        FROM fact_ventas f
        JOIN dim_country c ON c.id_country = f.id_country
        JOIN dim_region r ON r.id_region = c.id_region
        GROUP BY c.id_country, c.country, r.region
        """,
    ),
    (
        "anal_ventas_categoria",
        """
        SELECT it.id_item_type, it.item_type AS categoria,
               COUNT(*) AS pedidos,
               SUM(f.units_sold) AS unidades,
               SUM(f.total_revenue) AS ingresos,
               SUM(f.total_profit) AS profit
        FROM fact_ventas f
        JOIN dim_item_type it ON it.id_item_type = f.id_item_type
        GROUP BY it.id_item_type, it.item_type
        """,
    ),
    (
        "anal_ventas_canal",
        """
        SELECT ch.id_channel, ch.sales_channel AS canal,
               COUNT(*) AS pedidos,
               SUM(f.units_sold) AS unidades,
               SUM(f.total_revenue) AS ingresos,
               SUM(f.total_profit) AS profit
        FROM fact_ventas f
        JOIN dim_sales_channel ch ON ch.id_channel = f.id_channel
        GROUP BY ch.id_channel, ch.sales_channel
        """,
    ),
    (
        "anal_ventas_prioridad",
        """
        SELECT p.id_priority, p.order_priority AS prioridad,
               COUNT(*) AS pedidos,
               SUM(f.units_sold) AS unidades,
               SUM(f.total_revenue) AS ingresos,
               SUM(f.total_profit) AS profit
        FROM fact_ventas f
        JOIN dim_order_priority p ON p.id_priority = f.id_priority
        GROUP BY p.id_priority, p.order_priority
        """,
    ),
    (
        "anal_ventas_producto",
        """
        SELECT f.id_producto, dp.nombre_producto AS producto,
               it.item_type AS categoria,
               COUNT(*) AS pedidos,
               SUM(f.units_sold) AS unidades,
               SUM(f.total_revenue) AS ingresos,
               SUM(f.total_cost) AS costo,
               SUM(f.total_profit) AS profit
        FROM fact_ventas f
        LEFT JOIN dim_producto dp ON dp.id_producto = f.id_producto
        LEFT JOIN dim_item_type it ON it.id_item_type = dp.id_item_type
        GROUP BY f.id_producto, dp.nombre_producto, it.item_type
        ORDER BY ingresos DESC
        """,
    ),
    (
        "anal_pedidos_por_estado",
        """
        SELECT estado, COUNT(*) AS pedidos,
               SUM(total_pedido) AS valor_total
        FROM pedidos
        GROUP BY estado
        """,
    ),
]

KPIS = [
    ("ingresos_totales", "SUM(total_revenue)", "USD"),
    ("profit_total", "SUM(total_profit)", "USD"),
    ("margen_pct", "ROUND(100.0 * SUM(total_profit) / NULLIF(SUM(total_revenue), 0), 2)", "%"),
    ("unidades_vendidas", "SUM(units_sold)", "u"),
    ("pedidos_atendidos", "COUNT(*)", "u"),
]


def refrescar_tablas(conn, *, estrategia="incremental"):
    """(Re)construye todas las tablas analíticas. Devuelve el total creado."""
    conn.execute(
        """
        CREATE OR REPLACE TABLE anal_ventas_diarias AS
        SELECT order_date, origen,
               COUNT(*) AS pedidos,
               SUM(units_sold) AS unidades,
               SUM(total_revenue) AS ingresos,
               SUM(total_profit) AS profit
        FROM fact_ventas
        GROUP BY order_date, origen
        """
    )
    for nombre, sql in DEFINICIONES:
        conn.execute(f"CREATE OR REPLACE TABLE {nombre} AS {sql}")

    selects = []
    for kpi, expr, unidad in KPIS:
        selects.append(
            f"SELECT '{kpi}' AS kpi, CAST({expr} AS DOUBLE) AS valor, '{unidad}' AS unidad FROM fact_ventas"
        )
    conn.execute(
        "CREATE OR REPLACE TABLE anal_kpis AS "
        + " UNION ALL ".join(selects)
    )
    return len(DEFINICIONES) + 2