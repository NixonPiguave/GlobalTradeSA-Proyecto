# Research: Portal B2B — Volver a pedir

**Feature**: `007-volver-a-pedir` | **Date**: 2026-08-29

## R1 — Ubicación del endpoint

**Decision**: `POST /api/pedidos/{id_pedido}/volver-a-pedir` en `routers/pedidos.py`.

**Rationale**: El recurso accionado es un pedido existente; el patrón ya existe con `POST /{id_pedido}/cancelar`. Mantiene auth y `_ids()` centralizados.

**Alternatives considered**:

| Alternativa | Descartada porque |
|-------------|-------------------|
| `POST /api/carrito/reorden` con body `{ id_pedido }` | Menos RESTful; mezcla responsabilidades del carrito con lectura de pedidos históricos |
| Loop de `POST /api/carrito/items` desde el frontend | N+1 requests; difícil resumir omisiones; expone lógica de negocio al cliente |
| Extender `GET /api/pedidos/{id}` con acción | GET no debe mutar carrito |

---

## R2 — Reutilización vs. extensión de `agregar_item`

**Decision**: Nueva función interna `agregar_linea_reorden()` en `carrito_service.py`; **no** modificar la firma pública de `agregar_item()` usada por catálogo.

**Rationale**: `agregar_item` lanza excepción en inactivo/sin stock/stock insuficiente. La recompra requiere comportamiento tolerante (omitir o ajustar) y retorno estructurado por línea. Separar evita regresiones en flujo de catálogo.

**Alternatives considered**:

| Alternativa | Descartada porque |
|-------------|-------------------|
| Parámetro `modo="estricto|tolerante"` en `agregar_item` | Aumenta complejidad y riesgo en path crítico de checkout |
| Duplicar SQL de carrito en `pedido_service` | Viola DRY y diverge reglas de precio/stock |

---

## R3 — Stock parcial

**Decision**: Si `cantidad_solicitada + cantidad_en_carrito > stock_disponible` pero `stock_disponible > cantidad_en_carrito`, agregar `stock_disponible - cantidad_en_carrito` unidades y marcar línea como `ajustado`.

**Rationale**: Alineado con supuesto BR-703 de la spec y maximiza valor B2B sin sobreventa.

**Alternatives considered**:

| Alternativa | Descartada porque |
|-------------|-------------------|
| Omitir línea completa si no alcanza stock total | Peor UX; la spec prefiere agregar máximo disponible |
| Fallar toda la operación | Contradice recompra parcial |

---

## R4 — Redirección al carrito (sin página dedicada)

**Decision**: Tras éxito, redirect a `/pages/catalogo.html?carrito=1`; `carrito.js` detecta param y abre el drawer global. Resumen de toasts vía `sessionStorage` key `gm-reorden-resumen`.

**Rationale**: El portal no tiene `carrito.html`; el drawer en `carrito.js` es la UX canónica del carrito (spec 003). No invade checkout.

**Alternatives considered**:

| Alternativa | Descartada porque |
|-------------|-------------------|
| Redirect a `checkout.html` paso 1 | Spec prohíbe cambios en checkout; además salta pasos de entrega |
| Abrir drawer sin navegar | No cumple literalmente «redirigir»; pierde refresh de badge en header |
| Nueva página `carrito.html` | Scope innecesario |

---

## R5 — Idempotencia y doble clic

**Decision**: Deshabilitar botón + flag `data-loading` en UI durante la petición. Backend no garantiza idempotencia entre dos POST separados (segundo clic volvería a sumar cantidades, coherente con agregar desde catálogo dos veces).

**Rationale**: NFR-704 pide evitar duplicación *anómala* en la misma acción (doble clic accidental), no impedir recompras deliberadas repetidas.

**Alternatives considered**:

| Alternativa | Descartada porque |
|-------------|-------------------|
| Token idempotencia por pedido | Over-engineering para demo/local |
| Debounce 5s en backend | Ocultaría intención legítima de recomprar de nuevo |

---

## R6 — Precios al recomprar

**Decision**: Recalcular con `_precio_para()` y descuentos vigentes al insertar/actualizar `carrito_items`; ignorar `precio_unitario` histórico de `pedido_detalle`.

**Rationale**: BR-704 de la spec; coherente con carrito normal.

**Alternatives considered**:

| Alternativa | Descartada porque |
|-------------|-------------------|
| Copiar precio congelado del pedido | Fuera de alcance explícito |

---

## R7 — Producto eliminado del catálogo

**Decision**: Si `JOIN dim_producto` no encuentra fila o producto inactivo → `omitido` con motivo `no_disponible`.

**Rationale**: Edge case de la spec; mismo tratamiento que inactivo.

---

## R8 — Sin cambios DDL

**Decision**: No crear tablas ni columnas nuevas; resultado de recompra es efímero en respuesta HTTP + estado del carrito.

**Rationale**: DuckDB protegido; feature es orquestación de datos existentes.

**Alternatives considered**:

| Alternativa | Descartada porque |
|-------------|-------------------|
| Tabla `reorden_log` | Auditoría no solicitada; aumenta scope |
