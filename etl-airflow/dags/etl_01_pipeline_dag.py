"""etl_pipeline_dag.py — DAG principal: ELT GlobalTrade S.A.

Una sola tarea usa la misma sesión DuckDB (local) o delega al admin vía API
cuando globaltrade-apps ya tiene abierto el archivo (Docker).
"""
from __future__ import annotations

import os

from airflow.decorators import dag, task
from airflow.models import Variable
from airflow.utils.dates import days_ago


@dag(
    dag_id="etl_01_pipeline_dag",
    default_args={"owner": "gobierno-datos", "retries": 1, "retry_delay": 30},
    description="ELT GlobalTrade: extrae parquet+portal, transforma y carga fact_ventas + tablas analiticas",
    schedule="0 2 * * *",
    start_date=days_ago(1),
    catchup=False,
    max_active_runs=1,
    tags=["etl", "globtrade"],
)
def etl_pipeline() -> None:
    @task(task_id="pipeline_incremental")
    def task_pipeline():
        from etl_pkg.conexion import conectar, ejecutar_via_api
        from etl_pkg import carga, extraccion, transformacion

        estrategia = Variable.get("ETL_ESTRATEGIA", default_var="incremental")
        if os.environ.get("GLOBALTRADE_ETL_VIA_API", "").strip().lower() in {"1", "true", "yes"}:
            return ejecutar_via_api(estrategia=estrategia)

        conn = conectar()
        try:
            return {
                "estrategia": estrategia,
                "extraccion": extraccion.ejecutar(conn, cerrar=False),
                "transformacion": transformacion.ejecutar(conn, cerrar=False),
                "carga": carga.ejecutar(conn, estrategia=estrategia, cerrar=False),
            }
        finally:
            conn.close()

    task_pipeline()


etl_pipeline_dag = etl_pipeline()
