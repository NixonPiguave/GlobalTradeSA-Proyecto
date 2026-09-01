"""DAG etl_03 — Publicación DuckDB → ClickHouse."""
from __future__ import annotations

import os

from airflow.decorators import dag, task
from airflow.utils.dates import days_ago


@dag(
    dag_id="etl_03_clickhouse_publish",
    default_args={"owner": "gobierno-datos", "retries": 1},
    description="Publica marts analíticos de DuckDB hacia ClickHouse",
    schedule="30 2 * * *",
    start_date=days_ago(1),
    catchup=False,
    max_active_runs=1,
    tags=["etl", "clickhouse", "globtrade"],
)
def etl_clickhouse_publish():
    @task(task_id="publish_clickhouse")
    def task_publish():
        from etl_pkg.conexion import conectar, sync_clickhouse_via_api
        from etl_pkg import clickhouse_publish

        if os.environ.get("GLOBALTRADE_ETL_VIA_API", "").strip().lower() in {"1", "true", "yes"}:
            return sync_clickhouse_via_api()
        conn = conectar()
        try:
            return clickhouse_publish.publicar_desde_duckdb(conn)
        finally:
            conn.close()

    task_publish()


etl_03_clickhouse_publish_dag = etl_clickhouse_publish()
