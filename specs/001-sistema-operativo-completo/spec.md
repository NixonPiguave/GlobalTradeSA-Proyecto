# Feature Specification: Fundación del sistema GlobalTradeSA

**Feature Directory**: `001-sistema-operativo-completo`

**Created**: 2026-07-04

**Status**: Implemented

**Closed**: 2026-08-10

**Input**: Establecer la base ejecutable del monorepo: estructura profesional (`apps/`, `shared/`, `infrastructure/`), DuckDB unificado con DDL idempotente, carga del histórico analítico, seeds demo, runtime unificado en `:8000`/`:8001` y autenticación admin con roles base.

## Spec Kit Workflow

Primera feature del roadmap Spec Kit. Las capacidades de negocio (portal, admin operativo, PDF/reportes, analytics) se especificaron e implementaron en specs hijas:

| Spec | Alcance |
|------|---------|
| [`003-portal-b2b-carrito-checkout`](../003-portal-b2b-carrito-checkout/spec.md) | Carrito, checkout, mis pedidos, marketing portal |
| [`004-admin-operativo-catalogo-inventario`](../004-admin-operativo-catalogo-inventario/spec.md) | Catálogo, inventario, compras, pedidos, clientes, logística |
| [`005-comprobantes-reportes-pdf`](../005-comprobantes-reportes-pdf/spec.md) | Comprobantes PDF y centro de informes base |
| [`006-analytics-contabilidad-integracion`](../006-analytics-contabilidad-integracion/spec.md) | `fact_ventas`, contabilidad mínima, dashboard |
| [`002-reestructuracion-profesional`](../002-reestructuracion-profesional/spec.md) | Nav por dominio, gobierno, ClickHouse, Airflow, UX profesional |

Flujo: `/speckit-constitution` → `/speckit-specify` (esta spec) → `/speckit-plan` → `/speckit-tasks` → `/speckit-implement` → verificación Docker + DuckDB.

## Project Fit

**Affected Product Area**: Monorepo completo — capa de datos, runtime, auth base admin.

**Baseline (antes de 001)**: Dos apps FastAPI legacy (`GlobalTradeSA-duckdb/`, `GlobMarket-B2B/`) con frontends estáticos; catálogo portal sin carrito operativo; admin con dashboard histórico.

**Estado actual (implementado)**: Repositorio reorganizado; DuckDB con ~80+ tablas; histórico parquet cargado; seeds idempotentes; `run.py` y Docker unificado; login admin JWT + RBAC base; smoke tests.

**Out Of Scope en esta spec**: Carrito/checkout, CRUD operativo de catálogo, PDF, reportes avanzados, ClickHouse, gobierno UI — ver specs 002–006.

## User Scenarios & Testing

### US-F1 — Monorepo y runtime unificado (P1) — Implemented

Como desarrollador, levanto admin y portal en un solo proceso/contenedor sin conflictos de DuckDB.

**Independent Test**: `python run.py` o Docker unified → `:8000` y `:8001` responden health.

**Acceptance**:

1. Estructura `apps/admin`, `apps/portal`, `shared/`, `infrastructure/`.
2. Legacy eliminado o aislado; imports actualizados.
3. Un solo escritor DuckDB (single-writer).

---

### US-F2 — Modelo de datos y seeds (P1) — Implemented

Como sistema, inicializo tablas, dimensiones analíticas e histórico sin duplicar datos en reinit.

**Independent Test**: Borrar/reinit → `init_sistema.py` idempotente; `fact_ventas` con hasta 100k filas históricas.

**Acceptance**:

1. DDL M01–M13 en `shared/database/init_sistema.py`.
2. `fact_ventas` con `id_producto` nullable y `origen`.
3. Seeds: roles, admin, monedas, plan de cuentas, almacén, métodos de pago, catálogo demo.

---

### US-F3 — Autenticación admin base (P2) — Implemented

Como administrador, inicio sesión con JWT; clientes portal no acceden a APIs admin.

**Independent Test**: Login admin → panel; token portal → 403 en `/api/catalogo` admin.

**Acceptance**:

1. bcrypt + JWT en admin.
2. Middleware `authz.py` por rol/permiso.
3. Auditoría en operaciones críticas (helper base).

## Requirements

### Functional

- **FR-001**: Migrar apps a `apps/`; runtime unificado `run.py`.
- **FR-002**: DDL idempotente ~80+ tablas; carga parquet histórico.
- **FR-003**: Seeds idempotentes (roles, admin, maestras, demo).
- **FR-004**: Auth admin JWT + RBAC + login UI.
- **FR-005**: Docker unified con init al arrancar.
- **FR-006**: Preservar login portal y catálogo existente.

### Non-Functional

- **NFR-001**: Reproducible Windows + Docker; puertos `:8000`/`:8001`.
- **NFR-002**: DuckDB single-writer; sin contraseñas en claro.
- **NFR-003**: Artefactos transversales en esta carpeta: `data-model.md`, `contracts/`, `quickstart.md`.

## Success Criteria

- **SC-001**: Compose/run levanta ambos puertos con tablas creadas.
- **SC-002**: Histórico parquet visible en dashboard (post specs 006/002).
- **SC-003**: Admin login operativo; cliente no ejecuta APIs staff.

## Validation Plan

- Docker unified o `python run.py`.
- Consulta DuckDB: conteo tablas, `fact_ventas`, usuario admin.
- `pytest apps/admin/backend/tests/test_smoke.py`.

## Assumptions

- Specs 003–006 dependen del checkpoint de esta spec (Parte 1 cerrada).
- `data-model.md` y `contracts/` describen el sistema completo; cada spec hija referencia las secciones que implementa.

## Implementation Evidence

| Fase | Contenido | Tareas |
|------|-----------|--------|
| Setup | Monorepo, Docker, run.py | T001–T008 |
| Datos | DDL, parquet, seeds | T009–T021 |
| Auth | JWT, authz, login admin | T022–T026 |
| Docs | README, quickstart, smoke | T081–T084 |

Detalle: [`tasks.md`](tasks.md).
