"""Diagnóstico: ¿el webserver y el scheduler ven la misma base interna de Airflow?"""
import os
import sqlite3

path = "/opt/airflow/airflow.db"
print(f"host: {os.uname().nodename if hasattr(os, 'uname') else '?'} | {path} existe: {os.path.exists(path)}")
if os.path.exists(path):
    conn = sqlite3.connect(path)
    rows = conn.execute("SELECT dag_id, is_paused FROM dag ORDER BY dag_id").fetchall()
    print(f"DAGs registrados en esta BD interna: {len(rows)}")
    for dag_id, paused in rows:
        print(f"  - {dag_id} (paused={paused})")
    conn.close()
else:
    print("NO hay airflow.db en este contenedor")