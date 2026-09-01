"""Pipeline ETL completo en una sola sesión DuckDB (seguro con la app en marcha)."""
from __future__ import annotations

import sys
import time
from pathlib import Path
from typing import Any

import duckdb


def _import_etl_pkg():
    dags = Path(__file__).resolve().parents[2] / "etl-airflow" / "dags"
    dags_str = str(dags)
    if dags_str not in sys.path:
        sys.path.insert(0, dags_str)
    from etl_pkg import carga, extraccion, transformacion

    return extraccion, transformacion, carga


def ejecutar_pipeline(
    conn: duckdb.DuckDBPyConnection | Any,
    *,
    estrategia: str = "incremental",
) -> dict[str, Any]:
    """Extracción → transformación → carga en la misma conexión, sin cerrarla."""
    extraccion, transformacion, carga = _import_etl_pkg()
    inicio = time.time()

    resumen: dict[str, Any] = {
        "estrategia": estrategia,
        "extraccion": extraccion.ejecutar(conn, cerrar=False),
        "transformacion": transformacion.ejecutar(conn, cerrar=False),
        "carga": carga.ejecutar(conn, estrategia=estrategia, cerrar=False),
    }
    resumen["total_s"] = round(time.time() - inicio, 3)
    return resumen
