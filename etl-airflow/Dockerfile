FROM apache/airflow:2.10.5

USER root
RUN apt-get update && apt-get install -y --no-install-recommends curl wget && rm -rf /var/lib/apt/lists/*

USER airflow
RUN pip install --no-cache-dir \
    "duckdb>=1.1.0" \
    "reportlab>=4.0" \
    "pandas>=2.2.0" \
    "pyarrow>=17.0.0" \
    "python-dotenv>=1.0.0" \
    "requests>=2.32.0" \
    "pydantic>=2.7.0" \
    "jinja2>=3.1.0"

ENV AIRFLOW_HOME=/opt/airflow \
    AIRFLOW__CORE__LOAD_EXAMPLES=false \
    AIRFLOW__CORE__DAGS_ARE_PAUSED_AT_CREATION=false \
    AIRFLOW__CORE__DAGS_FOLDER=/opt/airflow/dags

WORKDIR /opt/airflow