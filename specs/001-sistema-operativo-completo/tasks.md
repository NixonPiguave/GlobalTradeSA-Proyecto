---
description: "Task list — Fundación del sistema GlobalTradeSA (spec 001)"
---

# Tasks: Fundación del sistema GlobalTradeSA

**Status**: All tasks completed (Implemented)

**Input**: `/specs/001-sistema-operativo-completo/` (spec.md, plan.md, data-model.md)

**Prerequisites**: `.specify/memory/constitution.md`

**Downstream specs** (implementan el núcleo de negocio sobre esta fundación):

- [`003-portal-b2b-carrito-checkout`](../003-portal-b2b-carrito-checkout/tasks.md)
- [`004-admin-operativo-catalogo-inventario`](../004-admin-operativo-catalogo-inventario/tasks.md)
- [`005-comprobantes-reportes-pdf`](../005-comprobantes-reportes-pdf/tasks.md)
- [`006-analytics-contabilidad-integracion`](../006-analytics-contabilidad-integracion/tasks.md)
- [`002-reestructuracion-profesional`](../002-reestructuracion-profesional/tasks.md)

## Formato: `[ID] [P?] [US-F#] Descripción con ruta`

---

## Fase 1: Setup / Reorganización

**Propósito**: Estructura profesional del repositorio.

- [x] T001 Crear estructura objetivo: `apps/admin`, `apps/portal`, `shared/`, `infrastructure/`, `docs/`
- [x] T002 Migrar admin legacy → `apps/admin/` actualizando imports
- [x] T003 Migrar portal legacy → `apps/portal/` actualizando imports
- [x] T004 [P] Eliminar legacy obsoleto (`.kiro/`, backends muertos, specs baseline)
- [x] T005 [P] Unificar Docker/READMEs duplicados
- [x] T006 Mover Docker a `infrastructure/docker/Dockerfile.unified` y entrypoint
- [x] T007 Actualizar `run.py` → `:8000` + `:8001` en un proceso
- [x] T008 [P] Actualizar `.env.example`, configs y `DUCKDB_PATH`

**Checkpoint**: Estructura monorepo lista; imports resuelven.

---

## Fase 2: Modelo de datos y runtime

**⚠️ CRÍTICO**: Bloquea specs 003–006.

- [x] T009 `shared/database/connection.py` — helpers DuckDB single-writer
- [x] T010 DDL M01–M02 (seguridad, maestras) en `init_sistema.py`
- [x] T011 DDL M03 (catálogo/PIM)
- [x] T012 DDL M04–M05 (compras, inventario)
- [x] T013 DDL M06–M07 (CRM, ventas)
- [x] T014 DDL M08–M09 (tesorería, contabilidad)
- [x] T015 DDL M10–M13 (logística, analytics, portal, comprobantes)
- [x] T016 Extender `fact_ventas` (`id_producto`, `origen`); vista `ventas`
- [x] T017 Carga histórico `data/ventas.parquet` (100k, idempotente)
- [x] T018 [P] Seeds: roles, admin, monedas, plan cuentas, listas precios, almacén, métodos pago
- [x] T019 [P] Seeds catálogo demo (marcas, categorías, productos)
- [x] T020 Entrypoint Docker ejecuta `init_sistema.py` al arrancar
- [x] T021 Verificar checkpoint Parte 1 (`quickstart.md`)

**Checkpoint Parte 1**: `:8000`/`:8001` + DuckDB con tablas e histórico.

---

## Fase 3: Auth admin base (US-F3)

- [x] T022 [US-F3] Auth admin JWT + bcrypt — `apps/admin/backend/services/auth_service.py`
- [x] T023 [US-F3] Middleware autorización — `middleware/authz.py`
- [x] T024 [P] [US-F3] Router auth/roles
- [x] T025 [US-F3] Servicio auditoría base — `auditoria_service.py`
- [x] T026 [P] [US-F3] Login admin UI — `pages/login.html`, guards JS

**Checkpoint**: Panel admin protegido; base para specs 004/002.

---

## Fase 4: Documentación y smoke (cierre 001)

- [x] T081 README raíz + `docs/quickstart.md` (arranque unificado)
- [x] T082 Referencia modelo de datos (`data-model.md` → docs)
- [x] T083 Smoke test — `apps/admin/backend/tests/test_smoke.py`
- [x] T084 Validación documentada en quickstart (checkpoint fundación)

---

## Dependencias

- **001** debe cerrar checkpoint Parte 1 antes de **003** o **004**.
- **005** requiere pedidos operativos (**003** + **004**).
- **006** requiere ventas confirmadas (**003**).
- **002** cierra el roadmap UX/analytics sobre **001–006**.

## Notas

Las tareas T027–T080 del roadmap original se movieron a specs 003–006 (ver tasks.md de cada una).
