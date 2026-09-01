# Feature Specification: Analytics, contabilidad e integración ventas

**Feature Directory**: `006-analytics-contabilidad-integracion`

**Created**: 2026-07-28

**Status**: Implemented

**Closed**: 2026-08-15

**Depends on**: [`003-portal-b2b-carrito-checkout`](../003-portal-b2b-carrito-checkout/spec.md), [`001-sistema-operativo-completo`](../001-sistema-operativo-completo/spec.md) (fact_ventas DDL)

**Input**: Integración idempotente de pedidos portal a `fact_ventas`, dashboard con origen histórico vs portal, contabilidad mínima automática (asientos venta/cobro) y resumen financiero.

## Spec Kit Workflow

Servicios en `shared/services/` + routers admin dashboard/contabilidad. ClickHouse/Airflow se especifican en **002** (capa analítica extendida).

## User Scenarios

### US-N1 — Integración analítica (P1) — Implemented

Pedidos confirmados alimentan `fact_ventas` sin duplicar.

**Independent Test**: Pedido portal → fila `origen='portal'`; reintegrar no duplica.

---

### US-N2 — Dashboard operativo (P2) — Implemented

Admin ve KPIs mezclando histórico parquet y ventas portal.

**Independent Test**: Filtro origen en dashboard.

---

### US-N3 — Contabilidad mínima (P2) — Implemented

Asientos automáticos al vender/cobrar; resumen en Finanzas.

**Independent Test**: Pedido pagado → asientos CxC/ingresos/costo/inventario/caja.

## Requirements

- **FR-601**: Integración idempotente — `integracion_ventas_service.py`
- **FR-602**: Hook al confirmar/pagar pedido + endpoint reintegración
- **FR-603**: Dashboard KPIs + filtro origen — `kpi_service.py`, `app.js`
- **FR-604**: Asientos automáticos — `contabilidad_service.py`
- **FR-605**: Router + UI Finanzas — `routers/contabilidad.py`
- **FR-606**: ETL pipeline base — `etl_pipeline_service.py`, `routers/etl.py`

## Success Criteria

- **SC-601**: Venta portal visible en dashboard sin duplicados.
- **SC-602**: Resumen financiero refleja ingresos/margen.
- **SC-603**: Histórico 100k intacto (`id_producto` nullable).

## Validation

- Consulta DuckDB `fact_ventas` post-pedido.
- `pytest` integración ventas (si existe).
- Sección Finanzas admin.

Tareas: [`tasks.md`](tasks.md)
