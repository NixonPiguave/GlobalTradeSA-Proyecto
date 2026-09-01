# Datos compartidos

Archivos de ventas usados por el panel admin y el portal B2B.

| Archivo | Descripción |
|---------|-------------|
| `ventas.parquet` | Dataset principal para carga histórica en DuckDB |
| `ventas.csv` | Fuente o respaldo en CSV |

Tras la reorganización (Parte 1), configurar `PARQUET_PATH` y `DUCKDB_PATH` en `.env` en la raíz del monorepo (`db/globtrade.duckdb`).
