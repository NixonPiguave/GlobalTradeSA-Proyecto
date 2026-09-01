---
description: "Task list — Portal B2B carrito y checkout (spec 003)"
---

# Tasks: Portal B2B — carrito y checkout

**Status**: All tasks completed (Implemented)

**Prerequisites**: [`001`](../001-sistema-operativo-completo/spec.md) checkpoint Parte 1

**Original mapping**: T043–T052, T078 (roadmap 001)

---

## Fase 1: Modelos y servicios core (US-P1)

- [x] T301 [P] [US-P1] Modelos Pydantic carrito/pedido — `apps/portal/gmbackend/models/ventas.py`
- [x] T302 [US-P1] Servicio carrito persistente — `services/carrito_service.py`
- [x] T303 [US-P1] Servicio checkout (stock, MOQ) — integrado en `pedido_service.py`
- [x] T304 [US-P1] Pedidos + pago simulado transaccional — `services/pedido_service.py`
- [x] T305 [US-P1] Máquina estados + historial — `services/estado_pedido.py`
- [x] T306 [P] [US-P1] Test pedido — `tests/test_pedido_service.py`

**Checkpoint**: API carrito/checkout operativa.

---

## Fase 2: Routers y UI portal (US-P1)

- [x] T307 [P] [US-P1] Routers carrito, pedidos, auth — `routers/carrito.py`, `pedidos.py`
- [x] T308 [US-P1] UI carrito drawer + checkout 3 pasos — `checkout.html`, `carrito.js`
- [x] T309 [P] [US-P1] Mis pedidos + timeline — `mis-pedidos.html`
- [x] T310 [P] [US-P2] Perfil empresa — `perfil.html`, `routers/cuenta.py`

**Checkpoint**: Flujo compra E2E en navegador.

---

## Fase 3: Catálogo extendido y marketing (US-P3, US-P4)

- [x] T311 [P] [US-P3] Catálogos/paquetes — `catalogos.js`, `routers/catalogos.py`, `catalogo_paquete.html`
- [x] T312 [P] [US-P3] Wishlist/favoritos — `wishlist_service.py`, `favoritos.html`
- [x] T313 [P] [US-P4] Marketing banners portal — `marketing_service.py`, landing UI
- [x] T314 [P] UX responsive portal — `apps/portal/web/css/`

**Checkpoint**: Portal B2B completo para demo.

---

## Dependencias

- Requiere catálogo admin (**004**) para productos visibles; puede desarrollarse en paralelo con seed demo de **001**.
- PDF comprobantes: **005**; integración `fact_ventas`: **006**.
