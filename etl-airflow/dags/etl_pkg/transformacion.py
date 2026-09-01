"""transformacion.py — Etapa TRANSFORMACIÓN (limpieza, tipado, canonización).

Reglas (documentadas en README.md):
  * Fechas: 'MM/DD/YYYY' -> DATE (formato DuckDB strptime).
  * Monetarios y unidades a tipos numéricos correctos.
  * Deduplicación de pedidos por order_id (solo ventas únicas).
  * Detección de anomalías deterministas (precios negativos / costos nulos).

El resultado queda en `stg_*algo*` listo para la etapa CARGA.
"""
from __future__ import annotations

import time
from datetime import datetime

from etl_pkg.conexion import conectar
from etl_pkg.util import garantizar_etl_control


def _registrar(conn, etapa, inicio, fin, filas, detalle=""):
    conn.execute(
        """
        INSERT INTO etl_control (id, etapa, inicio, fin, tiempo_s, filas, estado, detalle)
        VALUES (
          (SELECT COALESCE(MAX(id), 0) + 1 FROM etl_control),
          ?, ?, ?, ?, ?, 'OK', ?
        )
        """,
        [etapa, inicio, fin, round(fin - inicio, 3), filas, detalle],
    )


def _tabla_existe(conn, tabla):
    return conn.execute(
        "SELECT 1 FROM information_schema.tables WHERE table_name = ?",
        [tabla],
    ).fetchone() is not None


def ejecutar(conn=None, *, cerrar: bool | None = None):
    propia = conn is None
    if propia:
        conn = conectar()
    debe_cerrar = propia if cerrar is None else cerrar
    try:
        garantizar_etl_control(conn)
        inicio = time.time()
        resumen = {}

        resumen["ventas_objetivo"] = _transformar_ventas(conn)
        resumen["pedidos_objetivo"] = _transformar_pedidos(conn)
        resumen["anomalias"] = _detectar_anomalias(conn)

        fin = time.time()
        _registrar(conn, "transformacion", inicio, fin, sum(resumen.values()))
        return resumen
    finally:
        if debe_cerrar:
            conn.close()


def _transformar_ventas(conn):
    if not _tabla_existe(conn, "stg_ventas"):
        return 0
    conn.execute(
        """
        CREATE OR REPLACE TABLE stg_ventas_objetivo AS
        SELECT
            region, country, item_type, sales_channel, order_priority,
            strptime(order_date::VARCHAR, '%m/%d/%Y')::DATE AS order_date,
            strptime(ship_date::VARCHAR, '%m/%d/%Y')::DATE AS ship_date,
            CAST(order_id AS BIGINT) AS order_id,
            CAST(units_sold AS INTEGER) AS units_sold,
            CAST(unit_price AS DECIMAL(10,2)) AS unit_price,
            CAST(unit_cost AS DECIMAL(10,2)) AS unit_cost,
            CAST(total_revenue AS DECIMAL(12,2)) AS total_revenue,
            CAST(total_cost AS DECIMAL(12,2)) AS total_cost,
            CAST(total_profit AS DECIMAL(12,2)) AS total_profit
        FROM stg_ventas
        WHERE order_id IS NOT NULL
        QUALIFY row_number() OVER (PARTITION BY order_id ORDER BY order_id) = 1
        """
    )
    return int(conn.execute("SELECT COUNT(*) FROM stg_ventas_objetivo").fetchone()[0])


def _transformar_pedidos(conn):
    if not _tabla_existe(conn, "stg_pedidos"):
        return 0
    conn.execute("CREATE OR REPLACE TABLE stg_pedidos_objetivo AS SELECT * FROM stg_pedidos")
    return int(conn.execute("SELECT COUNT(*) FROM stg_pedidos_objetivo").fetchone()[0])


def _detectar_anomalias(conn):
    """Alertas deterministas (sin IA): la capa de IA es opcional y va en
    etl_ia_dag (desactivado por defecto, ver README)."""
    if not _tabla_existe(conn, "stg_ventas_objetivo"):
        return 0
    conn.execute(
        """
        CREATE OR REPLACE TABLE stg_anomalias AS
        SELECT order_id, total_revenue, total_cost, total_profit,
               'ingreso_negativo_o_costos_descuadrados' AS motivo
        FROM stg_ventas_objetivo
        WHERE total_revenue < 0 OR total_cost < 0
              OR (total_cost = 0 AND total_revenue > 0)
        """
    )
    return int(conn.execute("SELECT COUNT(*) FROM stg_anomalias").fetchone()[0])