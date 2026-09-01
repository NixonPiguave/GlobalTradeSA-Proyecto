---
description: "Task list — Reestructuración profesional (spec 002)"
---

# Tasks: Reestructuración profesional GlobalTradeSA

**Status**: All tasks completed (Implemented)

**Input**: [spec.md](spec.md), [plan.md](plan.md)

**Prerequisites**: Specs [`001`](../001-sistema-operativo-completo/spec.md)–[`006`](../006-analytics-contabilidad-integracion/spec.md) cerradas (núcleo operativo)

---

## Fase 1: Navegación por dominio y permisos (US-A)

- [x] T201 [US-A] Top nav por dominio (Dirección, Comercial, Operaciones, Informes, Sistema) — `apps/admin/web/js/nav.js`
- [x] T202 [US-A] Atributos `data-perm` en ítems de menú — `index.html`, `nav.js`
- [x] T203 [US-A] `GET /api/auth/me` incluye `permisos[]` — `auth_service.py`
- [x] T204 [US-A] `aplicarNavPermisos()` + ocultar `[hidden]` en dropdown — `app.js`, `app.css`
- [x] T205 [US-A] Redirigir `?page=` no autorizada a primera página permitida — `views.js`
- [x] T206 [US-A] `/api/maestras/filtros` accesible con permisos operativos — `routers/maestras.py`

**Checkpoint**: Login vendedor → menú sin Inventario/Compras; dashboard carga KPIs.

---

## Fase 2: Gobierno de usuarios y roles (US-B)

- [x] T207 [US-B] Catálogo canónico 13 permisos — `shared/database/permisos_catalogo.py`
- [x] T208 [US-B] Sync permisos al arranque — `init_sistema.py` / scripts sync
- [x] T209 [US-B] API gobierno CRUD — `routers/gobierno.py`, `gobierno_service.py`
- [x] T210 [US-B] UI matriz permisos agrupada — `gobierno.js`, CSS tema pastel
- [x] T211 [US-B] Rol y usuario demo `gerente` — seed + `gerente@globmarket.com`
- [x] T212 [US-B] Cuentas demo vendedor/almacen documentadas en spec

**Checkpoint**: Crear rol → login → menú coherente con permisos.

---

## Fase 3: Analytics híbrido DuckDB + ClickHouse (US-C)

- [x] T213 [US-C] Cliente ClickHouse + publish marts — `shared/services/clickhouse_service.py`, `clickhouse_publish.py`
- [x] T214 [US-C] Router analytics + fallback DuckDB — `routers/analytics.py`, `analytics_service.py`
- [x] T215 [US-C] `POST /api/dashboard/sync-clickhouse` — `routers/dashboard.py`
- [x] T216 [US-C] UI Inteligencia de datos / rankings — `app.js`, `charts.js`
- [x] T217 [US-C] Logging fallback CH→DuckDB en reportes — `reporte_clickhouse_service.py`

**Checkpoint**: Sync + `GET /api/analytics/ranking-proveedores` responde.

---

## Fase 4: Pipelines Airflow (US-D)

- [x] T218 [US-D] `docker-compose.full.yml` (apps + CH + Airflow + Postgres)
- [x] T219 [US-D] DAGs `etl_01` pipeline, `etl_02` rebuild, `etl_03` CH/IA, `etl_04` reportes — `etl-airflow/dags/`
- [x] T220 [US-D] Paquete `etl_pkg/` (extracción, transformación, carga, publish)

**Checkpoint**: Airflow UI muestra DAGs; stack full arranca.

---

## Fase 5: Centro de informes profesional (US-E)

- [x] T221 [US-E] Catálogo informes simples/compuestos — `reportes.js`, `reporte_service.py`
- [x] T222 [US-E] Vistas con KPIs, tablas y Chart.js
- [x] T223 [US-E] Export PDF/CSV desde centro (no botones rotos en pantallas operativas)
- [x] T224 [US-E] Resumen IA opcional — `ia_service.py`, `POST /api/configuracion/test-ia`

**Checkpoint**: Gerente genera informe y exporta PDF.

---

## Fase 6: Operaciones diarias pulidas (US-F)

- [x] T225 [US-F] Notificaciones campana + dedupe 12h — `notificacion_service.py`, `routers/notificaciones.py`
- [x] T226 [US-F] Filtros ventas históricas search-select región/país — `app.js`, `app.css`
- [x] T227 [US-F] Botón «Recibir mercancía» en Recepciones — `erp.js`
- [x] T228 [US-F] Toolbar vacío no tapa tabla — `views.js`
- [x] T229 [P] [US-F] Módulo estrategia — `estrategia.js`, `estrategia_service.py`
- [x] T230 [P] [US-F] UX responsive y accesibilidad básica admin/portal

**Checkpoint**: Recepción + campana sin duplicados masivos; vendedor opera ventas/informes.

---

## Dependencias

- Fases 1–2 pueden iniciar tras **001** + **004** (RBAC base).
- Fase 3–4 requieren **006** (marts/dashboard base).
- Fase 5 extiende **005** (reportes base).
- Fase 6 es polish independiente al final.

## Notas

Esta spec cierra el roadmap Spec Kit 001→006→002. Trabajo nuevo debe abrir spec **007+** antes de implementar.
