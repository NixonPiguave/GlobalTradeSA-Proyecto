"""etl_03_ia_dag.py — DAG opcional de alertas con métodos de inteligencia
artificial. DESACTIVADO por defecto.

Según la directriz del proyecto, la IA se aplica únicamente cuando es
imprescindible. El nivel estratégico actual se resuelve con reglas SQL
deterministas (stg_anomalias del ETL). Este DAG documenta dónde podría
usarse IA (detección de anomalías de ventas y predicción de tendencia) y
queda como flag apagado: para activarlo, en Airflow cree la variable
ETL_IA_HABILITADA = '1' y reactive el DAG.
"""
from __future__ import annotations

from airflow.decorators import dag, task
from airflow.models import Variable
from airflow.utils.dates import days_ago

from etl_pkg.conexion import conectar


@dag(
    dag_id="etl_03_ia_alertas_dag",
    default_args={"owner": "gobierno-datos", "retries": 0},
    description="IA opcional: anomalías/pronóstico (solo si ETL_IA_HABILITADA=1)",
    schedule=None,
    start_date=days_ago(1),
    catchup=False,
    max_active_runs=1,
    is_paused_upon_creation=True,
    tags=["etl", "ia", "opcional"],
)
def etl_ia_alertas() -> None:
    @task(task_id="alertas_ia")
    def task_alertas():
        if Variable.get("ETL_IA_HABILITADA", default_var="0") != "1":
            return {
                "estado": "omitido",
                "motivo": "IA deshabilitada: las alertas deterministas del ETL cubren el objetivo.",
            }
        conn = conectar()
        try:
            conn.execute(
                """
                CREATE OR REPLACE TABLE anal_alertas_ia AS
                WITH base AS (
                    SELECT order_date,
                           SUM(total_revenue)  AS ingresos
                    FROM fact_ventas
                    GROUP BY order_date
                ),
                stats AS (
                    SELECT AVG(ingresos) AS media, STDDEV(ingresos) AS desv
                    FROM base
                )
                SELECT b.order_date, b.ingresos,
                       (b.ingresos - s.media) / NULLIF(s.desv, 0) AS z_score
                FROM base b, stats s
                WHERE ABS((b.ingresos - s.media) / NULLIF(s.desv, 0)) > 3
                """
            )
            n = conn.execute("SELECT COUNT(*) FROM anal_alertas_ia").fetchone()[0]
            return {"IA": "habilitada", "anomalias_diarias": int(n)}
        finally:
            conn.close()

    task_alertas()


etl_ia_alertas_dag = etl_ia_alertas()