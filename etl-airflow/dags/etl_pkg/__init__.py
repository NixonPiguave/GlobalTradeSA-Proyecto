"""etl_pkg — Paquete de extracción / transformación / carga (ELT) para GlobalTrade S.A.

Diseñado para ser ejecutado tanto por Apache Airflow (DAGs en ../dags/) como
manualmente con scripts/ejecutar_etl.py. Toda la lógica es idempotente: si una
etapa falla, se puede reintentar sin duplicar datos (estrategia incremental).
"""