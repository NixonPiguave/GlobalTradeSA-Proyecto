# etl-airflow — Orquestación ETL de GlobalTrade S.A.

Orquestador del proceso de integración de datos: **extracción → transformación → carga → analítica**
(Apache Airflow + DuckDB). Es el requisito OE5/OO10 y alimenta los dashboards y reportes del ERP.

## Lista de DAGs (config.json)

| DAG | Día de ejecución | Estrategia | Descripción |
|-----|------------------|------------|-------------|
| `etl_pipeline_dag` | Diario 02:00 (`0 2 * * *`) | incremental | ELT completo: parquet/portal/compras → `fact_ventas` → tablas `anal_*` |
| `etl_rebuild_dag`   | Manual (sin cron) | rebuild | Recarga total (solo migraciones de esquema) |
| `etl_ia_alertas_dag`| Manual (pausado) | ia | IA opcional (z-score sobre ingresos diarios); requiere Variable `ETL_IA_HABILITADA=1` |
| `etl_04_reportes_dag` | Diario 02:30 (`30 2 * * *`) | reportes programados | Genera el paquete de reportes ejecutivos (PDF/CSV) en `shared/storage/reportes/` y lo expone en el panel (Reportes → Reportes programados). Reutiliza `reporte_service` del panel; retención 30 días |

> La lista formal queda registrada en `dags/config.json` y cada DAG en `dags/etl_XX_*.py`.

## Estrategia de carga (decisión documentada)

- **`incremental` (por defecto):** inserta únicamente los `order_id` que aún no existen en `fact_ventas`;
  es idempotente — repetir la corrida no duplica registros. Se usa en el DAG programado.
- **`rebuild`:** `DELETE` + recarga completa; se reserva para migraciones y se ejecuta a mano.
- **IA:** el nivel estratégico actual se resuelve con reglas SQL deterministas (`stg_anomalias`).
  La IA (z-score de ventas) está implementada como DAG opcional y apagado por defecto,
  respetando el criterio *IA solo donde es imprescindible*.

## Cómo ejecutar

### Stack completo recomendado (raíz del repo)

Airflow + ClickHouse + apps viven en **`docker-compose.full.yml`**:

```bash
docker compose -f docker-compose.full.yml up --build -d
```

Airflow UI: http://localhost:8080 · Admin: http://localhost:8000 · Portal: http://localhost:8001

> Este `etl-airflow/docker-compose.yml` es **legacy** (duplica webserver/scheduler).
> Prefiere el stack `full` para evitar contenedores detenidos y choques de puerto 8080.

### Local (sin Airflow)

```bash
python etl-airflow/scripts/ejecutar_etl.py --estrategia incremental   # o rebuild
```

### Orquestado con Airflow (Docker)

```bash
cd etl-airflow
docker compose up -d --build
# UI: http://localhost:8080   (usuario: globtrade_admin / 12345678)
```

- `webserver` (`:8080`) y `scheduler` comparten `AIRFLOW_HOME` y montan `../proyecto`
  con `DUCKDB_PATH=/proyecto/db/globtrade.duckdb` (la misma base del ERP).
- La programación puede cambiarse desde la UI (DAGs → Schedule) o editando `etl_01_pipeline_dag.py`.
- Ver una corrida: `docker exec globtrade-airflow-scheduler airflow dags trigger etl_pipeline_dag`.

## Evidencia de rendimiento

`informes/comparativa_tiempos.md` — medición sobre 1,000,013 registros en `fact_ventas`:

| Ruta | Mediana (s) |
|------|------------:|
| SQL directo sobre fact_ventas | 0.0025 |
| KPIs persistidos (`anal_kpis`)  | 0.0004 |
| ETL completo (3 etapas)        | 1.94 |

La bitácora de cada ejecución queda en `etl_control` (etapa, duración, filas, estado) y se expone
en el dashboard como "Información adicional — sincronización ETL" (`GET /api/dashboard/etl-estado`).