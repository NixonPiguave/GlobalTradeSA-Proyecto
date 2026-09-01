# Comparativa de tiempos — Informe SQL vs ETL (GlobalTrade S.A.)

Volumen: **1,000,013 filas** en `fact_ventas`
(fecha de medición: 2026-08-08 21:09).

| Ruta | Mediana (s) | Mínimo (s) | Muestras |
|------|-------------:|-----------:|----------|
| SQL directo sobre fact_ventas | 0.0025 | 0.0021 | [0.0095, 0.0025, 0.0021] |
| KPI persistido (lectura `anal_kpis`) | 0.0004 | 0.0004 | [0.0009, 0.0004, 0.0004] |
| ETL completo (3 etapas) | 1.9378 | 1.9378 | [1.9378] |

## lectura del cuadro

- Leer a **KPIs persistido** es casi instantáneo (fracciones de segundo):
  la agregación ya fue calculada por el ETL y no se recorre el histórico.
- Ejecutar el **informe SQLITE** sobre ~1,000,013 filas agrega en cada
  consulta (adecuado para uso puntual).
- El **ETL completo** ejecuta extracción + transformación + carga (~2-3 s):
  es el proceso que mantiene fact_ventas y las tablas analíticas al día.

## últimas ejecuciones registradas en etl_control

| Etapa | Inicio | Tiempo (s) | Filas | Estado | Detalle |
|-------|--------|-----------:|------:|--------|---------|
| carga | 1786241391.044769 | 0.24 | 9 | OK | estrategia=incremental |
| transformacion | 1786241390.529589 | 0.25 | 100011 | OK |  |
| extraccion | 1786241389.4902775 | 0.912 | 100023 | OK |  |
