---
description: "Task list — Portal B2B Volver a pedir (spec 007)"
---

# Tasks: Portal B2B — Volver a pedir

**Input**: Design documents from `/specs/007-volver-a-pedir/`

**Prerequisites**: [`003-portal-b2b-carrito-checkout`](../003-portal-b2b-carrito-checkout/spec.md) (Implemented), [`plan.md`](plan.md), [`contracts/reorden-api.md`](contracts/reorden-api.md)

**Tests**: Incluidos en fase Polish (plan.md y quickstart.md los requieren como verificación; no TDD estricto).

**Organization**: Tareas agrupadas por user story para implementación y prueba incremental.

**Changelog (post-analyze 2026-08-29)**: Fusionadas T707+T711; eliminada T712 (cubierta por T705); ampliada suite pytest en T716.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Paralelizable (archivos distintos, sin dependencias pendientes)
- **[Story]**: US1–US4 según [`spec.md`](spec.md)

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Confirmar contexto y baseline antes de tocar código.

- [x] T701 Revisar artefactos de diseño en `specs/007-volver-a-pedir/` (`spec.md`, `plan.md`, `data-model.md`, `contracts/reorden-api.md`)
- [x] T702 Verificar baseline spec 003: portal en `:8001`, `GET /api/pedidos` y `GET /api/carrito` operativos en `apps/portal/gmbackend/`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Backend de recompra — **bloquea todas las user stories de UI**.

**⚠️ CRITICAL**: Ninguna tarea de US1–US4 puede completarse sin esta fase.

- [x] T703 Definir `ESTADOS_REORDEN` (`pagado`, `preparando`, `enviado`, `entregado`) en `apps/portal/gmbackend/services/pedido_service.py`
- [x] T704 Implementar `agregar_linea_reorden()` con lógica agregado/omitido/ajustado (activo, stock, merge carrito, stock parcial) en `apps/portal/gmbackend/services/carrito_service.py`
- [x] T705 Implementar `volver_a_pedir()` (validación ownership/estado elegible → 422, `_bloquear_si_pedido_pendiente`, transacción única, `resumen` + `ver_carrito`) en `apps/portal/gmbackend/services/pedido_service.py`
- [x] T706 Exponer `POST /api/pedidos/{id_pedido}/volver-a-pedir` con auth JWT y códigos 200/404/422 según contrato en `apps/portal/gmbackend/routers/pedidos.py`

**Checkpoint**: Endpoint de recompra responde JSON con `resumen` y `carrito` vía curl/Postman.

---

## Phase 3: User Story 1 — Repetir un pedido entregado (Priority: P1) 🎯 MVP

**Goal**: Un clic en pedido elegible carga líneas al carrito y redirige al drawer del carrito.

**Independent Test**: Login → Mis pedidos → pedido `entregado` → «Volver a pedir» → drawer con líneas → checkout sin regresión.

### Implementation for User Story 1

- [x] T707 [US1] [US2] Renderizar botón «Volver a pedir» con matriz de visibilidad (mostrar en `pagado`/`preparando`/`enviado`/`entregado`; ocultar en `pendiente_pago`/`borrador`/`cancelado`) en `apps/portal/web/pages/mis-pedidos.html`
- [x] T708 [US1] Implementar handler POST con guard anti-doble-clic (`disabled`/`data-loading`) en `apps/portal/web/pages/mis-pedidos.html`
- [x] T709 [P] [US1] Redirigir a `/pages/catalogo.html?carrito=1` cuando `resumen.n_agregados > 0` en `apps/portal/web/pages/mis-pedidos.html`
- [x] T710 [P] [US1] Auto-abrir drawer del carrito si `?carrito=1` y refrescar badge en `apps/portal/web/js/carrito.js`

**Checkpoint**: Flujo feliz E2E navegable (escenario 1 de `quickstart.md`).

---

## Phase 4: User Story 2 — Botón visible solo en estados elegibles (Priority: P1)

**Goal**: El botón no aparece en `pendiente_pago`, `borrador` ni `cancelado`.

**Independent Test**: Abrir detalles en distintos estados; botón solo en `pagado`/`preparando`/`enviado`/`entregado`.

> **Nota**: Implementación cubierta por **T707**. Validación backend de estado no elegible cubierta por **T705** y **T716**.

**Checkpoint**: Escenario 2 de `quickstart.md` pasa.

---

## Phase 5: User Story 3 — Omitir productos no disponibles y avisar (Priority: P1)

**Goal**: Productos inactivos o sin stock se omiten con aviso; recompra parcial redirige; cero agregados no redirige.

**Independent Test**: Pedido con mezcla activo/inactivo/sin stock → toasts por omisión; carrito solo con líneas válidas.

### Implementation for User Story 3

- [x] T711 [US3] Persistir `resumen` en `sessionStorage` (`gm-reorden-resumen`) antes del redirect en `apps/portal/web/pages/mis-pedidos.html`
- [x] T712 [US3] Mostrar toasts de productos omitidos (`no_disponible`, `sin_stock`) al cargar catálogo o en Mis pedidos en `apps/portal/web/pages/mis-pedidos.html` y `apps/portal/web/js/carrito.js`
- [x] T713 [US3] Manejar respuesta 422 sin agregados (toast error, permanecer en Mis pedidos, sin redirect) en `apps/portal/web/pages/mis-pedidos.html`

**Checkpoint**: Escenarios 3 y recompra parcial de `quickstart.md` pasan.

---

## Phase 6: User Story 4 — Respeto de stock y carrito existente (Priority: P2)

**Goal**: Cantidades se combinan con carrito previo sin superar stock; stock parcial ajusta y avisa; bloqueo por `pendiente_pago` claro.

**Independent Test**: Carrito con producto previo + recompra del mismo → cantidades mergeadas; stock parcial → toast de ajuste.

### Implementation for User Story 4

- [x] T714 [US4] Mostrar toasts de líneas `ajustados` (`stock_parcial`) desde `sessionStorage` en `apps/portal/web/js/carrito.js`
- [x] T715 [US4] Mostrar mensaje claro cuando `_bloquear_si_pedido_pendiente` impide recompra en `apps/portal/web/pages/mis-pedidos.html`

**Checkpoint**: Escenarios 4 y bloqueo pendiente_pago de `spec.md` edge cases pasan.

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: Verificación automatizada, contrato y cierre de feature.

- [x] T716 [P] Crear suite pytest en `apps/portal/gmbackend/tests/test_volver_a_pedir.py` con casos: recompra feliz; producto inactivo omitido; stock parcial ajustado; merge con carrito existente (cantidad ≤ stock); precios vigentes ≠ históricos del pedido; estado no elegible → 422; pedido ajeno → 404; bloqueo `pendiente_pago` → 422; stock no negativo post-recompra
- [x] T717 [P] Documentar endpoint en `specs/001-sistema-operativo-completo/contracts/portal-api.md` (sección Mis pedidos)
- [x] T718 Ejecutar checklist completo de `specs/007-volver-a-pedir/quickstart.md` (browser + API + pytest + consulta stock)

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: Sin dependencias — iniciar de inmediato
- **Foundational (Phase 2)**: Depende de Setup — **bloquea US1–US4**
- **User Stories (Phase 3–6)**: Dependen de Foundational
  - US1 es MVP y debe completarse primero para demo mínima
  - US2 cubierta por T707 + T705/T716 (sin tareas propias)
  - US3/US4 dependen de backend T704–T705 y UI base US1
- **Polish (Phase 7)**: Depende de US1–US4 deseadas

### User Story Dependencies

| Story | Depende de | Independiente cuando |
|-------|------------|----------------------|
| **US1** | Phase 2 | Backend + botón + redirect + drawer |
| **US2** | Phase 2, T707 | Matriz estados en UI + pytest T716 |
| **US3** | Phase 2, US1 handler | Toasts omitidos verificables con datos seed |
| **US4** | Phase 2, US1 | Merge/ajuste verificable con carrito pre-cargado |

### Within Each User Story

- Foundational backend antes de UI
- Handler US1 (T708) antes de toasts US3/US4
- `carrito.js` drawer (T710) antes de toasts en drawer (T714)

### Parallel Opportunities

```text
Tras Phase 2:
  T709 [US1] mis-pedidos.html  ||  T710 [US1] carrito.js

Polish:
  T716 test_volver_a_pedir.py  ||  T717 portal-api.md
```

---

## Parallel Example: User Story 1

```bash
# Tras T708, en paralelo:
Task T709: Redirect y sessionStorage en apps/portal/web/pages/mis-pedidos.html
Task T710: Auto-open drawer en apps/portal/web/js/carrito.js
```

---

## Implementation Strategy

### MVP First (User Story 1)

1. Phase 1: Setup (T701–T702)
2. Phase 2: Foundational (T703–T706) — **crítico**
3. Phase 3: US1 (T707–T710)
4. **STOP and VALIDATE**: Escenario 1 quickstart + checkout sin regresión
5. Demo si listo

### Incremental Delivery

1. Setup + Foundational → API recompra lista
2. US1 + US2 (T707) → recompra feliz + botón correcto (MVP)
3. US3 → omisiones y feedback
4. US4 → stock parcial y bloqueos
5. Polish → pytest ampliado + quickstart + contrato

### Parallel Team Strategy

- Dev A: Foundational backend (T703–T706)
- Tras checkpoint: Dev B UI Mis pedidos (T707–T713), Dev C carrito.js + tests (T710, T714, T716)

---

## Notes

- No modificar `apps/portal/web/pages/checkout.html` ni flujo pago simulado
- No tocar `apps/admin/`
- Sin migraciones DuckDB
- Numeración T701+ alinea con FR-701+ de la spec
- Commit sugerido tras cada checkpoint de fase
