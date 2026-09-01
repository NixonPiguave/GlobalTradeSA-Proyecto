"""etl_02_rebuild_dag.py — DAG de REBUILD COMPLETO (manual).

Borrar todo y recargar desde cero. Se ejecuta SOLO manualmente (sin
programación) y es recomendado únicamente para migraciones de esquema;
para el día a día se usa la estrategia incremental (etl_01_pipeline_dag).
"""
from __future__ import annotations

import os

from airflow.decorators import dag, task
from airflow.utils.dates import days_ago


@dag(
    dag_id="etl_02_rebuild_dag",
    default_args={"owner": "gobierno-datos", "retries": 0},
    description="ELT GlobalTrade: RUTA REBUILD — borra fact_ventas y recarga todo (bajo demanda)",
    schedule=None,
    start_date=days_ago(1),
    catchup=False,
    max_active_runs=1,
    tags=["etl", "globtrade", "rebuild"],
)
def etl_rebuild() -> None:
    @task(task_id="pipeline_rebuild")
    def task_pipeline_rebuild():
        from etl_pkg.conexion import conectar, ejecutar_via_api
        from etl_pkg import carga, extraccion, transformacion

        estrategia = "rebuild"
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

    task_pipeline_rebuild()


etl_rebuild_dag = etl_rebuild()
