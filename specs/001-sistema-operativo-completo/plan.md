# Implementation Plan: Fundación del sistema GlobalTradeSA

**Feature Directory**: `001-sistema-operativo-completo` | **Date**: 2026-07-04 | **Spec**: [spec.md](spec.md)

**Status**: Implemented (fundación cerrada; specs 002–006 continúan el roadmap)

**Input**: Feature specification from `/specs/001-sistema-operativo-completo/spec.md`

**Note**: Esta spec cubre **Parte 1** del proyecto original. El diseño transversal (modelo de datos, contratos API) permanece aquí como referencia del monorepo. La implementación funcional se reparte en [`003`](../003-portal-b2b-carrito-checkout/spec.md)–[`006`](../006-analytics-contabilidad-integracion/spec.md) y la profesionalización en [`002`](../002-reestructuracion-profesional/spec.md).

## Summary

Reorganizar el monorepo en `apps/`, `shared/` e `infrastructure/`; crear el DDL DuckDB unificado (~82 tablas en 13 módulos); cargar el histórico parquet; sembrar datos demo; levantar runtime unificado (`:8000` admin, `:8001` portal) con auth admin JWT/RBAC base. Checkpoint: ambos puertos responden, BD inicializada, login admin operativo.

## Technical Context

**Language/Version**: Python 3.11+; HTML/CSS/JS estático.

**Primary Dependencies**: FastAPI, Uvicorn, DuckDB, passlib/bcrypt, python-jose (JWT).

**Storage**: `db/globtrade.duckdb`; histórico `data/ventas.parquet` (hasta 100k filas).

**Testing**: smoke pytest; verificación quickstart.md.

**Constraints**: Single-writer DuckDB; no romper portal login/catálogo existente.

## Constitution Check

- Ejecutable sobre documento: checkpoint Docker + puertos. **PASA**
- Dos productos, una visión: runtime unificado. **PASA**
- DuckDB protegido: single-writer, DDL idempotente. **PASA**
- Funcionalidad verificable: quickstart + consultas. **PASA**

## Project Structure

Artefactos de esta feature:

```text
specs/001-sistema-operativo-completo/
├── spec.md              # Alcance fundación (este documento)
├── plan.md
├── tasks.md             # T001–T026, T081–T084
├── data-model.md        # Modelo completo del sistema (transversal)
├── research.md
├── quickstart.md        # Verificación global (actualizada por specs hijas)
├── contracts/           # Contratos API completos (referencia)
└── checklists/
```

Código objetivo:

```text
apps/admin/backend/     # FastAPI admin (:8000)
apps/portal/gmbackend/  # FastAPI portal (:8001)
shared/database/        # init_sistema.py, connection.py
infrastructure/docker/  # Dockerfile.unified, entrypoint.sh
run.py
db/globtrade.duckdb
```

## Modelo de datos (referencia transversal)

Detalle en [data-model.md](data-model.md). Los módulos M01–M13 se crean en esta fase; el uso operativo se implementa en specs 003–006.

## Roadmap de specs dependientes

| Orden | Spec | Depende de |
|-------|------|------------|
| 1 | 001 (esta) | — |
| 2 | 003 Portal B2B | 001 |
| 3 | 004 Admin operativo | 001 |
| 4 | 005 Comprobantes/reportes | 003, 004 |
| 5 | 006 Analytics/contabilidad | 003, 004 |
| 6 | 002 Reestructuración | 001–006 |

## Estrategia de ejecución

1. Fases 1–2 de `tasks.md` (T001–T021): estructura + DDL + seeds.
2. Fase 3 (T022–T026): auth admin base.
3. Checkpoint Parte 1 antes de iniciar specs 003/004 en paralelo.
4. Cierre documental (T081–T084) puede hacerse al final del roadmap completo.

## Complexity Tracking

Sin violaciones. El modelo grande se mitiga con DDL único y specs modulares downstream.
