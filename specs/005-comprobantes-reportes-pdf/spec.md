# Feature Specification: Comprobantes y reportes PDF

**Feature Directory**: `005-comprobantes-reportes-pdf`

**Created**: 2026-07-25

**Status**: Implemented

**Closed**: 2026-08-12

**Depends on**: [`003-portal-b2b-carrito-checkout`](../003-portal-b2b-carrito-checkout/spec.md), [`004-admin-operativo-catalogo-inventario`](../004-admin-operativo-catalogo-inventario/spec.md)

**Input**: Generación de comprobantes PDF (pedido, factura, pago, OC, cotización, NC) y reportes exportables PDF/CSV desde el panel.

## Spec Kit Workflow

Capa `shared/pdf/` + routers comprobantes/reportes. Contratos: [`001/contracts/comprobantes-reportes-api.md`](../001-sistema-operativo-completo/contracts/comprobantes-reportes-api.md).

## User Scenarios

### US-R1 — Comprobantes PDF (P1) — Implemented

Cliente y admin descargan PDF de pedido, factura y pago tras venta.

**Independent Test**: Pedido pagado → 3 PDF descargables.

**Acceptance**:

1. Numeración por series atómica.
2. WeasyPrint + fallback ReportLab.
3. Fallo PDF no rompe el pedido.

---

### US-R2 — Reportes exportables (P2) — Implemented

Admin genera reportes ventas, inventario, pedidos, CxC, rentabilidad en PDF/CSV.

**Independent Test**: Centro/listados → export coherente con filtros.

## Requirements

- **FR-501**: Generador HTML→PDF — `shared/pdf/generator.py`
- **FR-502**: Plantillas comprobantes — `shared/templates/comprobantes/`
- **FR-503**: Servicio series/numeración — `comprobante_service.py`
- **FR-504**: Facturación + impuesto — `factura_service.py`
- **FR-505**: Endpoints PDF admin/portal autorizados por propietario
- **FR-506**: Reportes PDF/CSV — `reporte_service.py`
- **FR-507**: Plantillas reportes — `shared/templates/comprobantes/reportes/`

## Success Criteria

- **SC-501**: PDF pedido con líneas y totales correctos.
- **SC-502**: Reporte ventas = filtros fecha/región.
- **SC-503**: Inventario valorizado = qty × costo.

## Validation

- Descarga PDF desde portal mis-pedidos y admin pedidos.
- Generar reporte desde panel / centro informes (**002** extiende UX).

Tareas: [`tasks.md`](tasks.md)
