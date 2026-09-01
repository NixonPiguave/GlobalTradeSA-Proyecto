# GlobalTradeSA Project Context

## Product Summary

GlobalTradeSA is a local monorepo with two related products under `apps/`:

- `apps/admin`: ERP + analytics panel (catalog, inventory, purchasing, orders, finance, logistics, reports, strategy, access governance).
- `apps/portal`: B2B marketplace (registration, JWT login, catalog, cart, checkout with simulated payment, order history, PDFs, wishlist/packages).

Legacy folders `GlobalTradeSA-duckdb/` and `GlobMarket-B2B/` are reference only; active code lives in `apps/`.

## Spec Kit (only active specification workflow)

All product work is driven by Spec Kit in Cursor:

1. `/speckit-constitution` — project rules (`.specify/memory/constitution.md`).
2. `/speckit-specify` — feature specs under `specs/`.
3. `/speckit-clarify` — resolve underspecified rules.
4. `/speckit-plan` — technical design (`plan.md`, data model, contracts).
5. `/speckit-tasks` — ordered `tasks.md`.
6. `/speckit-implement` — code against tasks.
7. `/speckit-analyze` / `/speckit-checklist` / `/speckit-converge` — close the loop.

**Active features (all Implemented):**

| Spec | Focus | Key artifacts |
|------|--------|----------------|
| `001-sistema-operativo-completo` | Foundation: monorepo, DuckDB, runtime, auth base | `data-model.md`, `contracts/`, `quickstart.md` |
| `003-portal-b2b-carrito-checkout` | Portal cart, checkout, orders, profile, wishlist | `spec.md`, `tasks.md` |
| `004-admin-operativo-catalogo-inventario` | Admin catalog, inventory, POs, orders, clients | `spec.md`, `tasks.md` |
| `005-comprobantes-reportes-pdf` | PDF vouchers and exportable reports | `spec.md`, `tasks.md` |
| `006-analytics-contabilidad-integracion` | `fact_ventas`, KPIs, auto journal entries | `spec.md`, `tasks.md` |
| `002-reestructuracion-profesional` | Domain nav, governance, ClickHouse, Airflow, reports UX | `spec.md`, `plan.md`, `tasks.md` |

**Development order**: 001 → 003 + 004 (parallel) → 005 → 006 → 002.

OpenSpec / `opsx` is **not** used.

## Current Runtime

- Full stack (recommended demo): `docker compose -f docker-compose.full.yml up --build -d`  
  → apps + ClickHouse + Airflow (+ Airflow Postgres).
- Unified apps only: `docker-compose.unified.yml` / `infrastructure/compose/docker-compose.yml`.
- Admin: `http://localhost:8000`
- Portal: `http://localhost:8001`
- Database: `db/globtrade.duckdb` via `shared/database/init_sistema.py` (idempotent).
- Local launcher: `python run.py` (shared DuckDB writer).

## Main Technical Stack

- Backend: Python, FastAPI.
- Operational data: DuckDB (system of record).
- Analytics: ClickHouse (published marts; DuckDB fallback).
- ETL orchestration: Apache Airflow (`etl-airflow/`).
- Frontend: static HTML/CSS/JS (Chart.js where needed).
- Auth: JWT (admin staff + portal clients).
- PDF: ReportLab / WeasyPrint via `shared/pdf/`.
- Local: Windows, PowerShell, Docker Desktop.

## Important Architecture Decisions

- DuckDB is single-writer across processes; unified runtime or one apps container.
- Portal package is `gmbackend` (not `backend`) to avoid Python import collisions.
- Module permissions (`mod.*`) gate admin routers and top-nav items.
- `/api/maestras/filtros` is readable by operational roles; CRUD maestras still requires `mod.catalogo`.
- ClickHouse is optional at runtime: APIs must fall back to DuckDB.

## Implemented Capabilities (by spec)

### 001 — Foundation

- Monorepo `apps/`, `shared/`, `infrastructure/`.
- DuckDB ~80+ tables, parquet historic, idempotent seeds.
- Unified runtime `:8000`/`:8001`; admin JWT auth base.

### 003 — Portal

- Cart, 3-step checkout, simulated payment, order state machine.
- Mis pedidos, profile, catalog packages, wishlist, marketing banners.

### 004 — Admin operations

- Catalog CRUD, price lists, images; inventory, suppliers, POs, receptions.
- Admin orders/clients (CxC), logistics, ERP layout base.

### 005 — Documents

- PDF vouchers (order/invoice/payment/PO); report PDF/CSV.

### 006 — Analytics & finance

- Idempotent portal orders → `fact_ventas`; dashboard KPIs by origin.
- Auto journal entries; finance summary; ETL base.

### 002 — Professionalization

- Top nav by domain; role-aware menu; governance UI; demo role `gerente`.
- ClickHouse publish + analytics endpoints + Airflow DAGs.
- Report center with charts; notifications dedupe; operational UX polish.

## Demo Staff Accounts

| Role | Email | Password |
|------|-------|----------|
| admin | `admin@globmarket.com` | `12345678` |
| vendedor | `vendedor@globmarket.com` | `12345678` |
| almacen | `almacen@globmarket.com` | `12345678` |
| gerente | `gerente@globmarket.com` | `12345678` |

Portal B2B demos: `compras@walmart.com`, etc. / `12345678`.

## Do Not Assume

- Real payment gateways, production Kubernetes, trained ML as a product feature, multi-company tenancy.
- Do not present planned-only work as done; verify via browser, API, DuckDB, or test.

## Target Structure

- `apps/admin`, `apps/portal`
- `shared/database`, `shared/pdf`, `shared/services`, `shared/storage`, `shared/templates`
- `etl-airflow/`, `infrastructure/`, `specs/`, `.specify/`
