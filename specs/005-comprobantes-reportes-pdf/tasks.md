---
description: "Task list — Comprobantes y reportes (spec 005)"
---

# Tasks: Comprobantes y reportes PDF

**Status**: All tasks completed (Implemented)

**Prerequisites**: [`003`](../003-portal-b2b-carrito-checkout/spec.md), [`004`](../004-admin-operativo-catalogo-inventario/spec.md)

**Original mapping**: T059–T068

---

## Fase 1: Comprobantes PDF (US-R1)

- [x] T501 [US-R1] Generador PDF — `shared/pdf/generator.py`
- [x] T502 [P] [US-R1] Plantillas HTML pedido/factura/pago/OC/cotización/NC — `shared/templates/comprobantes/`
- [x] T503 [US-R1] Servicio comprobantes + series — `shared/pdf/comprobante_service.py`
- [x] T504 [US-R1] Facturación — `shared/services/factura_service.py`
- [x] T505 [P] [US-R1] Endpoints comprobantes admin/portal
- [x] T506 [P] [US-R1] Botones descarga en UI pedidos

**Checkpoint**: 3 PDF tras checkout.

---

## Fase 2: Reportes exportables (US-R2)

- [x] T507 [US-R2] Servicio reportes consultas + PDF/CSV — `reporte_service.py`
- [x] T508 [P] [US-R2] Plantillas HTML reportes
- [x] T509 [P] [US-R2] Router reportes — `routers/reportes.py`
- [x] T510 [P] [US-R2] Export en listados panel (base; **002** añade centro informes)

**Checkpoint**: Al menos un reporte PDF y CSV verificables.

---

## Dependencias

- Requiere pedidos confirmados (**003**).
- Centro informes avanzado (gráficos) en **002**.
