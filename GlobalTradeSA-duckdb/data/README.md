# Datos compartidos

Archivos de ventas usados por el panel admin y GlobMarket B2B.

| Archivo | Descripción |
|---------|-------------|
| `ventas.parquet` | Dataset principal para carga en DuckDB y consumo analítico |
| `ventas.csv` | Fuente o respaldo en CSV |

**No mover** estos archivos sin actualizar `PARQUET_PATH` en `GlobalTradeSA-duckdb/.env` y las rutas del sistema B2B.
