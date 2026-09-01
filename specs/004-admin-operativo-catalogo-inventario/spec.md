# Feature Specification: Admin operativo — catálogo, inventario y pedidos

**Feature Directory**: `004-admin-operativo-catalogo-inventario`

**Created**: 2026-07-15

**Status**: Implemented

**Closed**: 2026-08-08

**Depends on**: [`001-sistema-operativo-completo`](../001-sistema-operativo-completo/spec.md)

**Input**: CRUD de catálogo desde admin, inventario/compras/recepciones, administración de pedidos y clientes (CxC), logística y UX base del panel ERP.

## Spec Kit Workflow

Implementación en `apps/admin/` sobre auth de **001**. Contratos: [`001/contracts/admin-api.md`](../001-sistema-operativo-completo/contracts/admin-api.md).

## User Scenarios

### US-A1 — Catálogo administrable (P1) — Implemented

Admin crea categorías/productos con imágenes; visibles en portal.

**Independent Test**: Crear producto → aparece en `:8001`.

---

### US-A2 — Inventario y compras (P1) — Implemented

Proveedores, OC, recepciones, stock por almacén, alertas stock bajo.

**Independent Test**: OC → recepción → stock sube; pedido portal → stock baja.

---

### US-A3 — Pedidos y clientes (P2) — Implemented

Admin gestiona estados de pedido y ficha cliente/CxC.

**Independent Test**: Cambio estado válido → historial; CxC coherente.

---

### US-A4 — Logística (P3) — Implemented

Transportistas, tarifas, tracking de envíos.

**Independent Test**: Asignar envío a pedido en tránsito.

## Requirements

- **FR-401**: CRUD categorías/productos/listas precios + imágenes `/media`
- **FR-402**: Proveedores, OC, recepciones — `compras_service.py`
- **FR-403**: Stock, movimientos, lotes, alertas — `inventario_service.py`
- **FR-404**: Pedidos admin + facturación trigger — `pedido_admin_service.py`
- **FR-405**: Clientes + CxC — `cliente_service.py`
- **FR-406**: Logística — `logistica_service.py`
- **FR-407**: Layout ERP base — `app.css`, sidebar/breadcrumbs

## Success Criteria

- **SC-401**: Producto admin → portal en una sesión.
- **SC-402**: Stock nunca negativo (test inventario).
- **SC-403**: Transiciones pedido inválidas rechazadas.

## Validation

- Navegador: catálogo, inventario, compras, pedidos, clientes.
- `pytest apps/admin/backend/tests/test_inventario_service.py`
- `pytest apps/admin/backend/tests/test_categoria_service.py`

Tareas: [`tasks.md`](tasks.md)
