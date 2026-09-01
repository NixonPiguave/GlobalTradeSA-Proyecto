# Feature Specification: Reestructuración profesional GlobalTradeSA

**Feature Directory**: `002-reestructuracion-profesional`

**Created**: 2026-08-01

**Status**: Implemented

**Closed**: 2026-08-28

**Depends on**: [`001-sistema-operativo-completo`](../001-sistema-operativo-completo/spec.md) (fundación) y specs de módulo [`003`](../003-portal-b2b-carrito-checkout/spec.md)–[`006`](../006-analytics-contabilidad-integracion/spec.md) (núcleo operativo cerrado)

**Input**: Evolucionar el sistema operativo ya implementado hacia una experiencia profesional de ERP: navegación por dominio, gobierno de acceso configurable, arquitectura híbrida DuckDB + ClickHouse + Airflow, centro de informes con gráficos, notificaciones operativas y roles demo (vendedor, almacén, gerente).

## Spec Kit Workflow

Esta feature se desarrolló con el mismo flujo Spec Kit que 001:

1. `/speckit-specify` — alcance de reestructuración UX + analytics + gobierno.
2. `/speckit-plan` / diseño — contratos analytics, ClickHouse, DAGs Airflow.
3. `/speckit-tasks` / implementación incremental en Cursor.
4. Verificación — `docker-compose.full.yml`, APIs analytics, UI admin por rol, portal checkout.

No se usó OpenSpec/opsx; Spec Kit (`.specify/` + `specs/`) es el único flujo activo.

## Project Fit

**Affected Product Area**: Admin ERP (`apps/admin`), portal B2B (`apps/portal`), `shared/`, `etl-airflow/`, ClickHouse, Docker full stack.

**Baseline (tras 001)**: ERP y portal operativos sobre DuckDB unificado; menú aún por niveles genéricos; reportes básicos; sin ClickHouse/Airflow ni matriz de roles editable en UI.

**Estado actual (implementado)**:

- Navegación superior por dominio: Dirección, Comercial, Operaciones, Informes, Sistema.
- Permisos por módulo (`mod.*`); menú y rutas filtrados por rol; página de inicio = primera permitida.
- Gobierno: Usuarios y roles (matriz de permisos agrupada; rol `gerente` + usuario demo).
- Analytics: DuckDB operativo + ClickHouse analítico (publish + fallback).
- Airflow: DAGs ETL / rebuild / publish CH / IA / reportes.
- Centro de informes: simples/compuestos, Chart.js, PDF/CSV, resumen IA opcional.
- Notificaciones en campana (stock bajo, pedidos) con deduplicación.
- Ventas históricas: filtros organizados y comboboxes buscables (región/país).
- Recepciones: acción «Recibir mercancía» desde la pestaña Recepciones.

**Out Of Scope**: Pasarelas reales, Kubernetes productivo, ML entrenado en producción, multi-empresa, OpenSpec legacy.

## User Scenarios & Testing

### US-A — Navegar el ERP por dominio y rol (P1) — Implemented

Como usuario staff, veo solo los módulos de mi rol y entro en una sección permitida (no en un dashboard vacío).

**Independent Test**: Login `vendedor@globmarket.com` → menú sin Inventario/Compras; Centro de informes y Ventas cargan contenido.

**Acceptance**:

1. Ítems sin permiso no aparecen en el dropdown.
2. URL `?page=` no autorizada redirige a la primera página permitida.
3. Con `mod.dashboard`, el panel ejecutivo carga KPIs (filtros maestros no exigen `mod.catalogo`).

---

### US-B — Gobierno de usuarios y roles (P1) — Implemented

Como admin, creo roles, asigno módulos y creo usuarios staff.

**Independent Test**: Sistema → Usuarios y roles → crear/editar permisos → login con el nuevo rol.

**Acceptance**:

1. Catálogo de 13 permisos alineado al menú (Dirección, Comercial, Informes, Operaciones, Sistema).
2. Rol `gerente` con `mod.dashboard`, `mod.reportes`, `mod.ventas`.
3. Usuario `gerente@globmarket.com` / `12345678` operativo.
4. Admin protegido (acceso total implícito).

---

### US-C — Analítica híbrida DuckDB + ClickHouse (P1) — Implemented

Como analista, consulto rankings y sincronizo marts a ClickHouse con fallback a DuckDB.

**Independent Test**: `POST /api/dashboard/sync-clickhouse` → `GET /api/analytics/ranking-proveedores`.

**Acceptance**:

1. Sync publica marts cuando CH está disponible.
2. Si CH falla o está vacío, la API responde desde DuckDB.
3. UI Inteligencia de datos / dashboard muestra gráficos.

---

### US-D — Pipelines Airflow (P2) — Implemented

Como operador, ejecuto DAGs de ETL, rebuild, publish CH y reportes.

**Independent Test**: `docker compose -f docker-compose.full.yml up -d` → Airflow UI → DAGs visibles.

**Acceptance**:

1. Contenedores apps + ClickHouse + Airflow + Postgres Airflow.
2. DAGs `etl_01`…`etl_04` (pipeline, rebuild, CH/IA, reportes).

---

### US-E — Centro de informes profesional (P1) — Implemented

Como gerente/vendedor con `mod.reportes`, genero informes con filtros, gráficos y export PDF/CSV.

**Independent Test**: Informes → elegir reporte → Generar → PDF/CSV.

**Acceptance**:

1. Catálogo de informes simples y compuestos.
2. Vista con KPIs/tablas/gráficos cuando aplica.
3. Export no depende de botones PDF rotos en pantallas operativas (comprobantes sí).

---

### US-F — Operaciones diarias pulidas (P2) — Implemented

Como almacén/compras, recibo mercancía y recibo avisos de stock.

**Independent Test**: Compras → Recepciones → Recibir mercancía; campana sin duplicados masivos.

**Acceptance**:

1. Botón recibir desde Recepciones (OC aprobadas/parciales).
2. Notificaciones de stock deduplicadas (ventana reciente + compactación).
3. Toolbar vacío no tapa el encabezado de la tabla.

## Requirements

### Functional

- **FR-201**: Menú superior por dominio con `data-perm` por página.
- **FR-202**: `GET /api/auth/me` incluye `permisos[]`; frontend oculta nav y bloquea `loadPageData`.
- **FR-203**: CRUD gobierno (`/api/gobierno/*`) con `mod.gobierno`.
- **FR-204**: Catálogo canónico de permisos en `shared/database/permisos_catalogo.py` (sync al arranque).
- **FR-205**: Analytics API + sync ClickHouse + fallback DuckDB.
- **FR-206**: Compose full con ClickHouse + Airflow.
- **FR-207**: Centro de informes con catálogo, vista, export.
- **FR-208**: Notificaciones staff con dedupe.
- **FR-209**: Filtros de ventas históricas usables (search-select región/país).
- **FR-210**: Recepciones con acción explícita de recibir.

### Non-Functional

- **NFR-201**: Arranque reproducible con `docker-compose.full.yml` o unified + CH opcional.
- **NFR-202**: Sin prometer capacidades no verificables.
- **NFR-203**: Spec Kit como fuente de verdad del cambio.

## Success Criteria

- **SC-201**: Vendedor ve solo módulos permitidos y puede usar informes/ventas.
- **SC-202**: Gerente entra a panel + informes + rentabilidad.
- **SC-203**: Sync CH y rankings verificables por API.
- **SC-204**: Airflow reachable en el stack full.
- **SC-205**: Informe PDF/CSV generado desde Centro de informes.

## Verification (reproducible)

1. `docker compose -f docker-compose.full.yml up --build -d`
2. Admin `:8000` — menú por dominio, dashboard ≤6 KPIs, Inteligencia de datos
3. `POST /api/dashboard/sync-clickhouse`
4. `GET /api/analytics/ranking-proveedores` (o con fallback)
5. Portal `:8001` — mayorista autenticado, checkout con validación de tarjeta simulada
6. Gobierno — roles/permisos; login `gerente@globmarket.com`
7. Informes — generar + exportar
8. Recepciones — Recibir mercancía

## API contracts (nuevos / reforzados)

- `GET /api/analytics/estado`
- `GET /api/analytics/{vista}`
- `POST /api/dashboard/sync-clickhouse`
- `POST /api/configuracion/test-ia` (opcional, requiere `IA_API_KEY`)
- `GET|POST|PUT|DELETE /api/gobierno/*`
- `GET /api/notificaciones`
- `GET /api/maestras/filtros` — accesible con permisos de lectura operativa (no solo `mod.catalogo`)

## Demo accounts (staff)

| Rol | Email | Contraseña | Permisos típicos |
|-----|-------|------------|------------------|
| Admin | `admin@globmarket.com` | `12345678` | Todos |
| Vendedor | `vendedor@globmarket.com` | `12345678` | dashboard, ventas, clientes, reportes |
| Almacén | `almacen@globmarket.com` | `12345678` | inventario, compras, operaciones, logística, catálogo, reportes |
| Gerente | `gerente@globmarket.com` | `12345678` | dashboard, reportes, ventas |

## Assumptions

- Specs 001 y 003–006 cerradas; 002 no reimplementa el núcleo, lo profesionaliza (nav, gobierno, CH/Airflow, informes UX).
- Artefactos: [`plan.md`](plan.md), [`tasks.md`](tasks.md) (T201–T230).
- DuckDB sigue siendo el sistema de registro; ClickHouse es capa analítica.
- Spec Kit documenta e impulsa el trabajo; el código es la prueba de verdad.
