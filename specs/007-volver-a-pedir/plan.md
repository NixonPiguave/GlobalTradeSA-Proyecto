# Implementation Plan: Portal B2B — Volver a pedir

**Feature Directory**: `007-volver-a-pedir` | **Date**: 2026-08-29 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/007-volver-a-pedir/spec.md`

**Depends on**: [`003-portal-b2b-carrito-checkout`](../003-portal-b2b-carrito-checkout/spec.md)

## Summary

Permitir recompra B2B desde **Mis pedidos**: botón «Volver a pedir» en pedidos confirmados (`pagado`, `preparando`, `enviado`, `entregado`) que replica líneas al carrito activo respetando stock y disponibilidad, con feedback de omisiones/ajustes y redirección al carrito (drawer global). Sin cambios en checkout ni pago simulado.

**Enfoque técnico**: nuevo endpoint `POST /api/pedidos/{id}/volver-a-pedir`, función de servicio `pedido_service.volver_a_pedir()` que orquesta líneas desde `pedido_detalle` y delega inserción tolerante en `carrito_service.agregar_linea_reorden()` (soporta omitir inactivos/sin stock y ajustar cantidad parcial). UI en `mis-pedidos.html` + apertura automática del drawer vía query param en catálogo.

## Technical Context

**Language/Version**: Python 3.x (FastAPI backend); HTML/CSS/JS estático en portal.

**Primary Dependencies**: FastAPI, DuckDB, servicios existentes `carrito_service`, `pedido_service`, `estado_pedido`, `red_bodegas`.

**Storage**: DuckDB — **lectura** de `pedidos`, `pedido_detalle`, `dim_producto`; **escritura** de `carritos`, `carrito_items`. Sin migraciones DDL.

**Testing/Verification**: pytest en `apps/portal/gmbackend/tests/` (nuevo `test_volver_a_pedir.py`); flujo navegador en `:8001`; consulta DuckDB opcional sobre `carrito_items`.

**Target Platform**: Windows + Docker Desktop; portal en `http://localhost:8001`.

**Project Type**: Monorepo; alcance exclusivo `apps/portal/`.

**Performance Goals**: Procesar ≤ 20 líneas en una transacción única; respuesta percibida inmediata en local.

**Constraints**:

- No modificar `checkout.html`, flujo de pago simulado ni máquina de estados.
- No tocar `apps/admin`.
- Un solo writer DuckDB (proceso portal existente).
- Reutilizar `_bloquear_si_pedido_pendiente` del carrito.
- JWT obligatorio; solo pedidos del `id_cliente` autenticado.

**Scale/Scope**: Feature acotada (~4 archivos backend, 2 frontend, 1 test).

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principio | Evaluación |
|-----------|--------------|
| **Executable over document** | Endpoint + UI + pytest + quickstart reproducible. **PASA** |
| **Two products** | Solo `apps/portal`; admin intacto. **PASA** |
| **DuckDB protected** | Una transacción por recompra; sin segundo writer; sin DDL. **PASA** |
| **Verifiable** | Criterios mapeados a browser, API, datos. **PASA** |
| **Security B2B** | Ownership check `id_cliente`; estados elegibles; errores genéricos 404 para pedido ajeno. **PASA** |
| **Reproducible runtime** | Sin cambios de puertos/Docker. **PASA** |

**Post-design re-check**: Sin violaciones. No requiere Complexity Tracking.

## Project Structure

### Feature Artifacts

```text
specs/007-volver-a-pedir/
├── spec.md
├── plan.md              ← este archivo
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   └── reorden-api.md
└── tasks.md             ← generado por /speckit-tasks
```

### Source Code Touchpoints

```text
apps/portal/
├── gmbackend/
│   ├── routers/pedidos.py          # POST /{id_pedido}/volver-a-pedir
│   ├── services/pedido_service.py  # volver_a_pedir()
│   ├── services/carrito_service.py # agregar_linea_reorden() + constantes
│   └── tests/test_volver_a_pedir.py
└── web/
    ├── pages/mis-pedidos.html      # botón + handler
    └── js/carrito.js               # auto-abrir drawer (?carrito=1)
```

**Structure Decision**: Cambios mínimos en capas ya existentes de spec 003. No se crean routers ni tablas nuevas.

## Phase 0: Research

Ver [research.md](research.md). Sin NEEDS CLARIFICATION pendientes.

**Decisiones clave**:

1. Endpoint dedicado en router de pedidos (simétrico a `cancelar`).
2. Lógica de omisión/ajuste en servicio de carrito, no en UI.
3. «Pantalla del carrito» = drawer global con redirect a catálogo + `?carrito=1`.
4. Precios vigentes vía `_precio_para` existente.

## Phase 1: Design

| Artefacto | Contenido |
|-----------|-----------|
| [data-model.md](data-model.md) | Entidades, tablas DuckDB, reglas de estado |
| [contracts/reorden-api.md](contracts/reorden-api.md) | Request/response del endpoint |
| [quickstart.md](quickstart.md) | Validación browser + pytest + datos |

## Implementation Phases (for /speckit-tasks)

### Fase A — Backend (P1)

1. Constante `ESTADOS_REORDEN = {"pagado", "preparando", "enviado", "entregado"}` en `pedido_service` o módulo compartido.
2. `carrito_service.agregar_linea_reorden(conn, id_cliente, id_producto, cantidad_solicitada) -> dict` retorna:
   - `estado`: `"agregado"` | `"omitido"` | `"ajustado"`
   - `id_producto`, `nombre_producto`, `cantidad_solicitada`, `cantidad_agregada`, `motivo?`
3. `pedido_service.volver_a_pedir(conn, id_pedido, id_cliente) -> dict`:
   - Valida ownership y estado elegible (422 si no elegible).
   - Llama `_bloquear_si_pedido_pendiente` una vez al inicio.
   - Itera `pedido_detalle`; acumula `agregados`, `omitidos`, `ajustados`.
   - Transacción única BEGIN/COMMIT envolviendo todas las líneas.
   - Retorna `{ id_pedido, resumen, carrito }` donde `carrito = ver_carrito(...)`.
4. Router `POST /api/pedidos/{id_pedido}/volver-a-pedir` con auth JWT.

### Fase B — Frontend (P1)

1. En `mis-pedidos.html`, renderizar botón «Volver a pedir» cuando `p.estado` ∈ estados elegibles.
2. Handler: deshabilitar botón durante request → `POST` → toasts según `omitidos`/`ajustados` → si `agregados.length > 0`, guardar resumen en `sessionStorage` y `location.href = '/pages/catalogo.html?carrito=1'`.
3. Si cero agregados: toast error/warning, permanecer en Mis pedidos.
4. En `carrito.js`: al cargar, si `?carrito=1`, abrir drawer y consumir toast de `sessionStorage`.

### Fase C — Tests (P2)

1. pytest: pedido entregado → líneas en carrito.
2. pytest: producto inactivo omitido.
3. pytest: stock parcial → ajustado.
4. pytest: estado `pendiente_pago` → 422 sin botón backend.
5. pytest: pedido ajeno → 404.

## Complexity Tracking

N/A — ninguna violación de constitución.

## Verification

Ver [quickstart.md](quickstart.md) y escenarios en [spec.md](spec.md).
