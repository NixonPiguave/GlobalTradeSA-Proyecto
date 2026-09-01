# Feature Specification: Portal B2B — carrito y checkout

**Feature Directory**: `003-portal-b2b-carrito-checkout`

**Created**: 2026-07-15

**Status**: Implemented

**Closed**: 2026-08-05

**Depends on**: [`001-sistema-operativo-completo`](../001-sistema-operativo-completo/spec.md) (fundación + DDL ventas/portal)

**Input**: Flujo completo de compra B2B en el portal: registro/login JWT, catálogo público, carrito persistente, checkout en 3 pasos, pago simulado, mis pedidos, perfil y marketing (banners/promociones).

## Spec Kit Workflow

1. `/speckit-specify` — esta spec (US portal).
2. `/speckit-tasks` — T301–T312.
3. `/speckit-implement` — `apps/portal/`.
4. Verificación — `:8001`, pytest pedidos, checkout E2E.

**Contratos**: [`001/contracts/portal-api.md`](../001-sistema-operativo-completo/contracts/portal-api.md)

## User Scenarios

### US-P1 — Carrito y checkout (P1) — Implemented

Como empresa compradora, agrego productos, valido MOQ y confirmo pago simulado.

**Independent Test**: Login → carrito → checkout → pedido en Mis pedidos; stock descontado.

**Acceptance**:

1. Carrito persistente con precios congelados mayoristas.
2. MOQ bloquea checkout con mensaje claro.
3. Pago simulado crea pedido + pago aprobado; carrito vacío.
4. Timeline de estados en Mis pedidos.

---

### US-P2 — Perfil y cuenta (P2) — Implemented

Como cliente B2B, gestiono datos de empresa y direcciones.

**Independent Test**: Perfil → editar → reflejado en checkout.

---

### US-P3 — Catálogos y wishlist (P2) — Implemented

Como comprador, navego catálogos/paquetes y guardo favoritos.

**Independent Test**: `catalogos.html`, `favoritos.html`, APIs wishlist.

---

### US-P4 — Marketing portal (P3) — Implemented

Como visitante, veo banners y promociones en landing.

**Independent Test**: Banners activos en home portal.

## Requirements

- **FR-301**: Carrito CRUD con precios congelados — `carrito_service.py`
- **FR-302**: Checkout 3 pasos + validación stock/MOQ — `pedido_service.py`
- **FR-303**: Máquina estados pedido + historial — `estado_pedido.py`
- **FR-304**: Mis pedidos + detalle timeline — UI + routers
- **FR-305**: Perfil empresa/direcciones — `cuenta_service.py`
- **FR-306**: Catálogos/paquetes — `catalogo_service.py`, `catalogos.js`
- **FR-307**: Wishlist — `wishlist_service.py`
- **FR-308**: Marketing banners — `marketing_service.py`

## Success Criteria

- **SC-301**: Compra completa en &lt; 5 min local.
- **SC-302**: Stock nunca negativo tras confirmar pedido.
- **SC-303**: Cliente no accede APIs admin.

## Validation

- Navegador: carrito, checkout, mis-pedidos, perfil, favoritos.
- `pytest apps/portal/gmbackend/tests/test_pedido_service.py`
- `pytest apps/portal/gmbackend/tests/test_checkout_e2e_http.py`

## Assumptions

- Pago siempre simulado.
- Integración analítica y PDF en specs **005** y **006**.

Tareas: [`tasks.md`](tasks.md)
