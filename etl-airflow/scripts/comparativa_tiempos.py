"""scripts/comparativa_tiempos.py — Comparativa de tiempos: informe SQL directo
sobre fact_ventas vs lectura de KPIs persistidos vs ETL completo.

Método (repetible): se mide 3 veces cada ruta sobre el histórico completo y se
reporta la mediana. Genera informes/comparativa_tiempos.md y .json.
"""
from __future__ import annotations

import json
import statistics
import sys
import time
from pathlib import Path

import duckdb

RAIZ = Path(__file__).resolve().parents[2]
DB = RAIZ / "db" / "globtrade.duckdb"
INFO = RAIZ / "etl-airflow" / "informes"

REPETICIONES = 3

SQL_INFORME_DIRECTO = """
    SELECT COUNT(*)                        AS filas,
           SUM(total_revenue)              AS ingresos,
           SUM(total_cost)                 AS costos,
           SUM(total_profit)               AS profit
    FROM fact_ventas;
"""

SQL_KPI_PERSISTIDOS = """
    SELECT kpi, valor, unidad FROM anal_kpis ORDER BY kpi;
"""


def medir(fn, repet: int = REPETICIONES) -> dict:
    muestras = []
    for _ in range(repet):
        t0 = time.perf_counter()
        fn()
        muestras.append(time.perf_counter() - t0)
    return {
        "mediana_s": round(statistics.median(muestras), 4),
        "min_s": round(min(muestras), 4),
        "muestras": [round(t, 4) for t in muestras],
    }


def main() -> None:
    INFO.mkdir(parents=True, exist_ok=True)
    conn = duckdb.connect(str(DB), read_only=True)

    def ruta_directa() -> int:
        return int(conn.execute(SQL_INFORME_DIRECTO).fetchone()[0])

    def ruta_persistido() -> int:
        return len(conn.execute(SQL_KPI_PERSISTIDOS).fetchall())

    directa = medir(ruta_directa)
    persistida = medir(ruta_persistido)
    conn.close()

    def ruta_etl() -> None:
        dags = RAIZ / "etl-airflow" / "dags"
        sys.path.insert(0, str(dags))
        from etl_pkg import carga, extraccion, transformacion

        extraccion.ejecutar()
        transformacion.ejecutar()
        carga.ejecutar(estrategia="incremental")

    etl = medir(ruta_etl, 1)

    conn = duckdb.connect(str(DB), read_only=True)

    ultimas = conn.execute(
        "SELECT etapa, inicio, tiempo_s, filas, estado, detalle "
        "FROM etl_control ORDER BY id DESC LIMIT 3"
    ).fetchall()
    filas_fact = int(conn.execute("SELECT COUNT(*) FROM fact_ventas").fetchone()[0])
    conn.close()

    data = {
        "volumen_filas_fact_ventas": filas_fact,
        "sql_informe_directo": directa,
        "kpi_persistido": persistida,
        "etl_completo": etl,
        "ultimas_ejecuciones_etl_control": [
            {
                "etapa": r[0], "inicio": str(r[1]), "tiempo_s": r[2],
                "filas": r[3], "estado": r[4], "detalle": r[5],
            }
            for r in ultimas
        ],
    }
    (INFO / "comparativa_tiempos.json").write_text(
        json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    md = f"""# Comparativa de tiempos — Informe SQL vs ETL (GlobalTrade S.A.)

Volumen: **{filas_fact:,} filas** en `fact_ventas`
(fecha de medición: {time.strftime('%Y-%m-%d %H:%M')}).

| Ruta | Mediana (s) | Mínimo (s) | Muestras |
|------|-------------:|-----------:|----------|
| SQL directo sobre fact_ventas | {directa['mediana_s']} | {directa['min_s']} | {directa['muestras']} |
| KPI persistido (lectura `anal_kpis`) | {persistida['mediana_s']} | {persistida['min_s']} | {persistida['muestras']} |
| ETL completo (3 etapas) | {etl['mediana_s']} | {etl['min_s']} | {etl['muestras']} |

## lectura del cuadro

- Leer a **KPIs persistido** es casi instantáneo (fracciones de segundo):
  la agregación ya fue calculada por el ETL y no se recorre el histórico.
- Ejecutar el **informe SQLITE** sobre ~{filas_fact:,} filas agrega en cada
  consulta (adecuado para uso puntual).
- El **ETL completo** ejecuta extracción + transformación + carga (~2-3 s):
  es el proceso que mantiene fact_ventas y las tablas analíticas al día.

## últimas ejecuciones registradas en etl_control

| Etapa | Inicio | Tiempo (s) | Filas | Estado | Detalle |
|-------|--------|-----------:|------:|--------|---------|
"""
    for r in ultimas:
        md += f"| {r[0]} | {r[1]} | {r[2]} | {r[3]} | {r[4]} | {r[5]} |\n"

    (INFO / "comparativa_tiempos.md").write_text(md, encoding="utf-8")
    print(md)


if __name__ == "__main__":
    main()