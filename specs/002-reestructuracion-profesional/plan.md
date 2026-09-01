# Implementation Plan: Reestructuración profesional GlobalTradeSA

**Feature Directory**: `002-reestructuracion-profesional` | **Date**: 2026-08-01 | **Spec**: [spec.md](spec.md)

**Status**: Implemented

**Depends on**: [`001`](../001-sistema-operativo-completo/spec.md), [`003`](../003-portal-b2b-carrito-checkout/spec.md)–[`006`](../006-analytics-contabilidad-integracion/spec.md)

## Summary

Profesionalizar el ERP ya operativo: navegación superior por dominio, permisos `mod.*` en menú y rutas, UI de gobierno (usuarios/roles), analytics híbrido DuckDB + ClickHouse con Airflow, centro de informes con gráficos Chart.js, notificaciones deduplicadas y pulido operativo (filtros ventas históricas, recepciones, toolbar).

No reimplementa carrito, inventario ni PDF — los refina en UX, acceso y capa analítica.

## Technical Context

**Stack añadido**: ClickHouse (`infrastructure/clickhouse/`), Airflow (`etl-airflow/`), Chart.js, `docker-compose.full.yml`.

**Patrones**: Fallback DuckDB si CH no disponible; sync publish vía `POST /api/dashboard/sync-clickhouse`; permisos en localStorage tras login.

## Constitution Check

- Dos productos: cambios principalmente admin + shared analytics. **PASA**
- Verificable: roles demo, APIs analytics, compose full. **PASA**
- No prometer ML productivo: IA summary opcional con API key. **PASA**

## Fases de implementación

1. **Nav y permisos frontend** — `nav.js`, `data-perm`, `aplicarNavPermisos()`, landing por rol.
2. **Gobierno backend/UI** — `gobierno_service.py`, `permisos_catalogo.py`, matriz agrupada.
3. **Analytics híbrido** — `clickhouse_service.py`, `analytics_service.py`, routers analytics/dashboard.
4. **Airflow + compose full** — DAGs etl_01–04, `docker-compose.full.yml`.
5. **Centro de informes** — `reportes.js`, informes compuestos, export PDF/CSV.
6. **Operaciones pulidas** — notificaciones dedupe, ventas filtros search-select, recepciones UI.

## Verificación

Ver [spec.md § Verification](spec.md#verification-reproducible) y [`tasks.md`](tasks.md).

## Complexity Tracking

ClickHouse/Airflow son capa analítica opcional en runtime unified; APIs deben funcionar sin CH. Sin violaciones.
