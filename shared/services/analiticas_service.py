"""Reconstrucción de tablas analíticas del dashboard (anal_*, vista ventas)."""
from __future__ import annotations

import sys
import time
from pathlib import Path

import duckdb

from shared.database.init_sistema import _create_views


def _etl_kpis_module():
    dags = Path(__file__).resolve().parents[2] / "etl-airflow" / "dags"
    dags_str = str(dags)
    if dags_str not in sys.path:
        sys.path.insert(0, dags_str)
    from etl_pkg import kpis
    from etl_pkg.util import garantizar_etl_control

    return kpis, garantizar_etl_control


def refrescar_analiticas_dashboard(conn: duckdb.DuckDBPyConnection) -> dict:
    """Vista ventas + tablas anal_* + registro en etl_control."""
    filas_fact = int(conn.execute("SELECT COUNT(*) FROM fact_ventas").fetchone()[0])
    if filas_fact <= 0:
        raise ValueError("fact_ventas está vacía. Ejecuta el ETL o scripts/regenerar_fact_ventas.py.")

    _create_views(conn)
    kpis, garantizar_etl_control = _etl_kpis_module()
    garantizar_etl_control(conn)

    inicio = time.time()
    tablas = kpis.refrescar_tablas(conn, estrategia="incremental")
    fin = time.time()

    conn.execute(
        """
        INSERT INTO etl_control (id, etapa, inicio, fin, tiempo_s, filas, estado, detalle)
        VALUES (
          (SELECT COALESCE(MAX(id), 0) + 1 FROM etl_control),
          'carga', ?, ?, ?, ?, 'OK', 'refrescar_analiticas_dashboard'
        )
        """,
        [inicio, fin, round(fin - inicio, 3), tablas],
    )

    kpis_rows = conn.execute("SELECT kpi, valor, unidad FROM anal_kpis ORDER BY kpi").fetchall()
    try:
        conn.execute("CHECKPOINT")
    except duckdb.Error:
        pass

    return {
        "filas_fact_ventas": filas_fact,
        "tablas_analiticas": tablas,
        "kpis": [{"kpi": r[0], "valor": float(r[1] or 0), "unidad": r[2]} for r in kpis_rows],
    }
