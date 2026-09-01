# Feature Specification: Portal B2B — Volver a pedir

**Feature Directory**: `007-volver-a-pedir`

**Created**: 2026-08-29

**Status**: Implemented

**Depends on**: [`003-portal-b2b-carrito-checkout`](../003-portal-b2b-carrito-checkout/spec.md) (carrito persistente, mis pedidos, checkout y pago simulado)

**Input**: Nueva feature 007-volver-a-pedir: En el portal B2B, en mis pedidos, botón «Volver a pedir» en pedidos pagados, preparados, enviados o entregados. Al hacer clic, cargar al carrito las mismas líneas (Producto + cantidad), respetando stock, redirigir al carrito. Si está el producto inactivo o sin stock, omitir y avisar. No cambiar el checkout ni pago simulado. Solo en el portal de ventas.

## Clarifications

### Session 2026-08-29

- Q: ¿Redirigir al carrito cuando ninguna línea se agrega (0 agregados)? → A: No. Permanecer en Mis pedidos con toast/resumen de omisiones; el carrito no recibe líneas nuevas.
- Q: ¿Idempotencia backend vs protección ante doble clic (NFR-704)? → A: Protección en UI (botón deshabilitado durante el POST). Dos POST separados intencionales suman cantidades, igual que agregar desde catálogo.

## Project Fit

**Affected Product Area**: GlobMarket-B2B marketplace (`apps/portal`)

**Current State**: El portal B2B (spec 003, implementada) permite consultar el historial de pedidos en «Mis pedidos», ver detalle con líneas de producto y cantidades, y gestionar un carrito persistente con validación de stock y productos activos. No existe acción de recompra desde un pedido anterior.

**Target State**: Un comprador B2B puede repetir un pedido ya confirmado con un solo clic: las líneas elegibles se cargan en su carrito actual y continúa el flujo habitual de compra sin modificar checkout ni pago simulado.

**Out Of Scope**:

- Cambios en checkout, pago simulado o máquina de estados del pedido.
- Funcionalidad equivalente en el panel admin/ERP.
- Reordenar pedidos cancelados o pendientes de pago.
- Congelar precios históricos del pedido original (se aplican precios vigentes al agregar al carrito).
- Creación automática de pedido; solo precarga del carrito.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Repetir un pedido entregado (Priority: P1)

Como empresa compradora autenticada, abro el detalle de un pedido en estado entregado y pulso «Volver a pedir» para volver a comprar los mismos productos sin buscarlos uno a uno en el catálogo.

**Why this priority**: Es el caso de uso principal de recompra recurrente B2B y el flujo más común tras una compra satisfactoria.

**Independent Test**: Login en portal → Mis pedidos → abrir pedido entregado → «Volver a pedir» → carrito muestra las líneas agregadas → usuario puede continuar a checkout sin cambios en ese flujo.

**Acceptance Scenarios**:

1. **Given** un pedido propio en estado `entregado` con al menos una línea cuyo producto está activo y con stock en la zona del cliente, **When** pulso «Volver a pedir», **Then** esas líneas quedan en mi carrito activo con las mismas cantidades solicitadas (salvo límites de stock) y soy redirigido a la pantalla del carrito.
2. **Given** un pedido entregado cuyas líneas tienen productos activos con stock, **When** completo «Volver a pedir» y reviso el carrito, **Then** veo los productos con precios vigentes calculados según las reglas habituales del carrito (no los precios históricos del pedido).

---

### User Story 2 - Botón visible solo en estados elegibles (Priority: P1)

Como comprador, solo veo «Volver a pedir» cuando tiene sentido repetir la compra, no en pedidos aún abiertos o cancelados.

**Why this priority**: Evita recompras sobre pedidos no confirmados o anulados y reduce confusión operativa.

**Independent Test**: Revisar detalle de pedidos en distintos estados y confirmar presencia/ausencia del botón según reglas.

**Acceptance Scenarios**:

1. **Given** un pedido en estado `pagado`, `preparando`, `enviado` o `entregado`, **When** abro su detalle en Mis pedidos, **Then** veo el botón «Volver a pedir».
2. **Given** un pedido en estado `pendiente_pago`, `borrador` o `cancelado`, **When** abro su detalle, **Then** no veo el botón «Volver a pedir».

---

### User Story 3 - Omitir productos no disponibles y avisar (Priority: P1)

Como comprador, si algunos productos del pedido original ya no están disponibles, quiero que el sistema agregue lo que sí puede y me explique qué se omitió.

**Why this priority**: La recompra parcial es frecuente en B2B; el usuario debe entender por qué no se replicó el pedido completo.

**Independent Test**: Preparar pedido con mezcla de productos activos/inactivos y con/sin stock → ejecutar «Volver a pedir» → verificar carrito y mensajes.

**Acceptance Scenarios**:

1. **Given** un pedido elegible donde una línea referencia un producto inactivo, **When** pulso «Volver a pedir», **Then** esa línea no se agrega al carrito y recibo un aviso que indica el producto omitido y el motivo (no disponible).
2. **Given** un pedido elegible donde una línea referencia un producto activo pero sin stock en la zona del cliente, **When** pulso «Volver a pedir», **Then** esa línea no se agrega y recibo un aviso de producto omitido por falta de stock.
3. **Given** un pedido elegible con varias líneas y solo algunas disponibles, **When** pulso «Volver a pedir», **Then** se agregan las líneas disponibles, se omiten las no disponibles con aviso explícito, y soy redirigido al carrito.
4. **Given** un pedido elegible donde ninguna línea puede agregarse, **When** pulso «Volver a pedir», **Then** no se modifica el carrito con nuevas líneas, recibo un aviso de que no se pudo agregar ningún producto, permanezco en Mis pedidos (sin redirección al carrito) y recibo el resumen sin errores confusos.

---

### User Story 4 - Respeto de stock y carrito existente (Priority: P2)

Como comprador con productos ya en el carrito, quiero que «Volver a pedir» respete el stock disponible y las reglas actuales del carrito al sumar cantidades.

**Why this priority**: Evita sobreventa y mantiene coherencia con el comportamiento existente del carrito (spec 003).

**Independent Test**: Tener ítems previos en carrito → volver a pedir un pedido que comparte productos → verificar cantidades finales y mensajes de stock.

**Acceptance Scenarios**:

1. **Given** que ya tengo un producto en el carrito y el pedido original incluye el mismo producto, **When** pulso «Volver a pedir», **Then** las cantidades se combinan siguiendo las mismas reglas que al agregar desde catálogo, sin superar el stock disponible en mi zona.
2. **Given** que la cantidad solicitada supera el stock disponible pero hay stock parcial, **When** pulso «Volver a pedir», **Then** se agrega hasta el máximo disponible y se informa que la cantidad fue ajustada por stock.
3. **Given** que tengo un pedido `pendiente_pago` bloqueando modificaciones del carrito (regla existente de spec 003), **When** intento «Volver a pedir», **Then** la acción no agrega líneas y recibo un mensaje claro indicando que debo completar o cancelar el pedido pendiente antes de modificar el carrito.

### Edge Cases

- Pedido de otro cliente: el sistema no debe permitir recompra; solo pedidos propios del usuario autenticado.
- Producto eliminado del catálogo: tratar como no disponible, omitir y avisar.
- Pedido con una sola línea omitida por stock (cero agregados): permanecer en Mis pedidos, mostrar toast con resumen de omisiones; no redirigir al carrito.
- Doble clic rápido en «Volver a pedir»: deshabilitar el botón durante la petición en curso para evitar duplicación anómala en la misma acción; no se exige idempotencia backend entre POSTs separados.
- Línea con cantidad histórica que ya no cumple MOQ mayorista: el carrito puede quedar bajo MOQ; el checkout existente seguirá validando MOQ sin cambios en esta feature.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-701**: El portal MUST mostrar un botón «Volver a pedir» en el detalle de pedidos propios en estados `pagado`, `preparando`, `enviado` y `entregado`.
- **FR-702**: El portal MUST ocultar «Volver a pedir» en pedidos en estados `pendiente_pago`, `borrador` y `cancelado`.
- **FR-703**: Al activar «Volver a pedir», el sistema MUST leer las líneas del pedido (producto + cantidad) y intentar agregarlas al carrito activo del cliente autenticado.
- **FR-704**: El sistema MUST omitir líneas cuyo producto esté inactivo o sin stock en la zona de entrega del cliente, registrando el motivo para feedback al usuario.
- **FR-705**: El sistema MUST respetar el stock disponible al combinar cantidades con ítems ya presentes en el carrito, incluyendo ajuste a stock parcial cuando aplique.
- **FR-706**: Tras procesar la recompra, el sistema MUST redirigir al usuario a la experiencia del carrito (drawer global del portal) cuando al menos una línea se agregó correctamente.
- **FR-707**: Cuando ninguna línea pueda agregarse, el sistema MUST informar al usuario con un resumen claro en Mis pedidos, MUST NOT agregar líneas al carrito y MUST NOT redirigir al carrito.
- **FR-708**: El sistema MUST presentar un resumen de éxito parcial u omisiones (productos omitidos, cantidades ajustadas) mediante feedback visible (toast o equivalente) antes o al llegar al carrito.
- **FR-709**: La feature MUST reutilizar las reglas de negocio del carrito existente (producto activo, stock por zona, bloqueo por pedido pendiente de pago, precios vigentes) sin alterar checkout ni pago simulado.
- **FR-710**: Solo el titular autenticado del pedido MUST poder ejecutar «Volver a pedir» sobre ese pedido.
- **FR-711**: El resultado MUST ser verificable desde la UI de Mis pedidos y el carrito, y mediante una operación de backend expuesta para recompra (endpoint dedicado o acción documentada sobre recursos existentes).

### Non-Functional Requirements

- **NFR-701**: El portal en `:8001` MUST seguir arrancando y funcionando tras el cambio.
- **NFR-702**: Los mensajes de error MUST ser comprensibles para el comprador y MUST NOT exponer datos de otros clientes ni detalles internos del sistema.
- **NFR-703**: La acción «Volver a pedir» SHOULD completarse en un tiempo percibido como inmediato para pedidos típicos (≤ 20 líneas) en entorno local.
- **NFR-704**: La UI MUST deshabilitar «Volver a pedir» mientras el POST está en curso, evitando duplicación anómala por doble clic en la misma acción. Reintentos POST separados intencionales pueden sumar cantidades (comportamiento equivalente al catálogo).

### Business Rules

- **BR-701**: Estados elegibles para recompra: `pagado`, `preparando`, `enviado`, `entregado` (equivalente operativo a «pagados, preparados, enviados o entregados» del pedido del usuario).
- **BR-702**: Producto inactivo o con stock cero en la zona del cliente → omitir línea y avisar; no fallar silenciosamente.
- **BR-703**: Stock insuficiente para la cantidad original pero stock parcial disponible → agregar hasta el máximo disponible y avisar del ajuste.
- **BR-704**: Precios al recomprar se calculan con reglas vigentes del carrito, no se reutilizan precios congelados del pedido histórico.
- **BR-705**: Checkout, MOQ mayorista y pago simulado permanecen sin cambios; esta feature solo precarga el carrito.

### Key Entities *(include if feature involves data)*

- **Pedido**: Compra histórica del cliente; aporta estado, identificador y líneas a replicar.
- **Línea de pedido**: Par producto + cantidad solicitada en la compra original.
- **Carrito activo**: Contenedor de compra en curso del cliente; destino de las líneas replicadas.
- **Producto**: Debe estar activo y con stock en la red de bodegas del cliente para ser incluido.
- **Resumen de recompra**: Resultado agregado de la operación (líneas agregadas, omitidas, cantidades ajustadas) para feedback al usuario.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-701**: Un comprador puede repetir un pedido elegible y ver las líneas disponibles en su carrito en menos de 30 segundos desde Mis pedidos en entorno local.
- **SC-702**: En pruebas con pedidos en estados elegibles, el botón «Volver a pedir» aparece en el 100% de los casos; en estados no elegibles, aparece en 0% de los casos.
- **SC-703**: Cuando existen productos inactivos o sin stock, el usuario recibe aviso explícito por cada omisión en el 100% de los escenarios de prueba definidos.
- **SC-704**: El flujo de checkout y pago simulado existente (spec 003) sigue completándose sin regresiones tras usar «Volver a pedir».
- **SC-705**: Ningún usuario puede recomprar pedidos de otra empresa en escenarios de prueba de autorización.

## Validation Plan

- **Browser/UI**: `mis-pedidos.html` — botón visible/oculto por estado; clic redirige a carrito; toasts/resumen de omisiones; carrito refleja líneas agregadas.
- **API/Backend**: Operación de recompra sobre pedido propio; respuesta con detalle de agregados/omitidos/ajustados; rechazo de pedido ajeno o estado no elegible.
- **Data**: Verificar en carrito activo del cliente las filas `carrito_items` correspondientes tras recompra; stock no negativo en bodegas de la zona.
- **Docker/Runtime**: Portal accesible en `http://localhost:8001`; login, Mis pedidos y carrito operativos.

## Assumptions

- «Preparados» del pedido del usuario corresponde al estado `preparando` ya usado en el portal.
- Los precios al recomprar se recalculan con la lógica actual del carrito (mayorista/unitario, descuentos vigentes).
- Si hay stock parcial, se prefiere agregar la cantidad máxima disponible en lugar de omitir toda la línea.
- La recompra se implementa exclusivamente en `apps/portal`; el admin no requiere botón equivalente.
- Se reutiliza el carrito y servicios de spec 003; no se crea un segundo flujo de carrito.
- El bloqueo existente cuando hay pedido `pendiente_pago` sigue aplicando antes de modificar el carrito.
- «Pantalla del carrito» en este portal = drawer global del carrito (spec 003), no una página dedicada ni checkout.

## Spec Kit Workflow

1. `/speckit-specify` — esta spec.
2. `/speckit-plan` — diseño técnico acotado a portal (router/service/UI).
3. `/speckit-tasks` — tareas implementables.
4. `/speckit-implement` — cambios en `apps/portal/`.
5. Verificación — `:8001`, flujo Mis pedidos → Volver a pedir → carrito → checkout sin regresión.

**Contratos base**: [`003-portal-b2b-carrito-checkout`](../003-portal-b2b-carrito-checkout/spec.md), [`001/contracts/portal-api.md`](../001-sistema-operativo-completo/contracts/portal-api.md)
