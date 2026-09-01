---
description: "Task list — Admin operativo (spec 004)"
---

# Tasks: Admin operativo — catálogo, inventario y pedidos

**Status**: All tasks completed (Implemented)

**Prerequisites**: [`001`](../001-sistema-operativo-completo/spec.md) auth + DDL

**Original mapping**: T027–T042, T053–T058, T077

---

## Fase 1: Catálogo administrable (US-A1)

- [x] T401 [P] [US-A1] Modelos Pydantic catálogo — `models/catalogo.py`
- [x] T402 [US-A1] Servicio categorías — `categoria_service.py`
- [x] T403 [US-A1] Servicio productos + SKU — `producto_service.py`
- [x] T404 [US-A1] Listas de precios — `precio_service.py`
- [x] T405 [US-A1] Imágenes locales Pillow — `imagen_service.py`, `shared/storage/uploads/`
- [x] T406 [P] [US-A1] Routers catálogo/maestras — `routers/catalogo.py`
- [x] T407 [US-A1] Servir `/media` — `main.py`
- [x] T408 [P] [US-A1] UI admin catálogo — `erp.js`, vistas catálogo
- [x] T409 [US-A1] Portal lee catálogo admin — `portal/.../producto_service.py`, `catalogo.py`

**Checkpoint**: Producto con imagen en portal.

---

## Fase 2: Inventario y compras (US-A2)

- [x] T410 [P] [US-A2] Modelos inventario — `models/inventario.py`
- [x] T411 [US-A2] Proveedores — `proveedor_service.py`
- [x] T412 [US-A2] OC y recepciones — `compras_service.py`
- [x] T413 [US-A2] Inventario stock/movimientos/alertas — `inventario_service.py`
- [x] T414 [P] [US-A2] Test inventario — `tests/test_inventario_service.py`
- [x] T415 [P] [US-A2] Routers compras/inventario
- [x] T416 [P] [US-A2] UI proveedores/compras/inventario — `erp.js`

**Checkpoint**: Recepción incrementa stock.

---

## Fase 3: Pedidos, clientes y logística (US-A3, US-A4)

- [x] T417 [US-A3] Pedidos admin — `pedido_admin_service.py`
- [x] T418 [US-A3] Clientes y CxC — `cliente_service.py`
- [x] T419 [P] [US-A3] Routers pedidos/clientes
- [x] T420 [P] [US-A3] UI pedidos y clientes
- [x] T421 [US-A3] UX panel ERP base — `app.css`, layout
- [x] T422 [P] [US-A4] Logística transportistas/tracking — `logistica_service.py`

**Checkpoint**: Admin opera ciclo compra-venta con **003**.

---

## Dependencias

- Paralelo con **003** tras **001**.
- Notificaciones stock y recepciones UI refinadas en **002**.
