---
description: "Task list — Analytics y contabilidad (spec 006)"
---

# Tasks: Analytics, contabilidad e integración ventas

**Status**: All tasks completed (Implemented)

**Prerequisites**: [`003`](../003-portal-b2b-carrito-checkout/spec.md) (pedidos operativos)

**Original mapping**: T069–T076

---

## Fase 1: Integración fact_ventas (US-N1)

- [x] T601 [US-N1] Servicio integración idempotente — `shared/services/integracion_ventas_service.py`
- [x] T602 [P] [US-N1] Test idempotencia integración ventas
- [x] T603 [US-N1] Hook confirmar/pagar + endpoint reintegración — `routers/dashboard.py`
- [x] T604 [US-N1] Dashboard filtro origen histórico/portal — `apps/admin/web/js/app.js`

**Checkpoint**: Pedido → `fact_ventas` una sola vez.

---

## Fase 2: Contabilidad mínima (US-N3)

- [x] T605 [US-N3] Asientos automáticos venta/costo/cobro — `shared/services/contabilidad_service.py`
- [x] T606 [US-N3] Enganche en flujo pago pedido
- [x] T607 [P] [US-N3] Router contabilidad — `routers/contabilidad.py`
- [x] T608 [P] [US-N3] UI resumen Finanzas — admin web

**Checkpoint**: Asientos visibles tras checkout.

---

## Fase 3: ETL y KPIs base (US-N2)

- [x] T609 [US-N2] Servicio KPIs dashboard — `kpi_service.py`
- [x] T610 [P] [US-N2] Router ETL operativo DuckDB — `routers/etl.py`, `etl_service.py`
- [x] T611 [P] [US-N2] Pipeline ETL shared — `shared/services/etl_pipeline_service.py`

**Checkpoint**: Dashboard KPIs operativos (CH/Airflow en **002**).

---

## Dependencias

- **002** añade ClickHouse publish, Airflow y centro informes avanzado sobre esta base.
