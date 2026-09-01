# Implementation Plan: [FEATURE]

**Feature Directory**: `[###-feature-name]` | **Date**: [DATE] | **Spec**: [link]

**Input**: Feature specification from `/specs/[###-feature-name]/spec.md`

**Note**: This template is filled in by `/speckit-plan`. Keep implementation decisions aligned with `.specify/memory/constitution.md` and `.specify/memory/project-context.md`.

## Summary

[Extract from feature spec: user/business need, affected product area and technical approach.]

## Technical Context

**Language/Version**: Python 3.x for backend; HTML/CSS/JavaScript for current frontend unless otherwise justified.

**Primary Dependencies**: FastAPI, Uvicorn, DuckDB and existing project libraries.

**Storage**: DuckDB. Specify affected tables and whether the feature reads, writes or migrates data.

**Testing/Verification**: Use the most appropriate available checks: pytest when present, endpoint/browser verification, DuckDB query checks, Docker startup checks and regression checks for existing flows.

**Target Platform**: Windows local development with PowerShell and Docker Desktop; Linux container runtime through Docker images.

**Project Type**: Monorepo with two web applications and optional unified runtime.

**Performance Goals**: Preserve responsive local UX for catalog, auth and dashboard flows; define specific targets when a feature changes query-heavy or user-facing paths.

**Constraints**:

- Do not break `http://localhost:8000` for analytics/admin or `http://localhost:8001` for B2B.
- Do not introduce a second writer process against the same DuckDB file.
- Do not store plaintext passwords or leak sensitive login details.
- Do not introduce a frontend framework or new database unless the spec explicitly requires and justifies it.

**Scale/Scope**: Local academic/demo environment with a DuckDB dataset and B2B product catalog; future production-scale integrations require separate specs.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- **Executable over document**: The plan must include a runnable validation path.
- **Two products, one vision**: The plan must identify whether it affects analytics/admin, B2B, unified runtime or integration.
- **DuckDB protected**: The plan must explain read/write behavior and lock/concurrency implications.
- **Functionality verifiable**: Requirements must map to browser, endpoint, data or Docker checks.
- **Security and B2B UX**: Auth/session/company data risks must be addressed when relevant.
- **Reproducible runtime**: Docker, ports and environment changes must be explicit.

## Project Structure

### Feature Artifacts

```text
specs/[###-feature]/
├── spec.md
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
└── tasks.md
```

### Source Code Touchpoints

```text
GlobalTradeSA-duckdb/
├── backend/
│   ├── routers/
│   ├── services/
│   ├── database.py
│   └── main.py
└── frontend/
    ├── index.html
    ├── js/
    └── css/

GlobMarket-B2B/
├── gmbackend/
│   ├── routers/
│   ├── services/
│   ├── database.py
│   └── main.py
└── frontend/
    ├── pages/
    ├── js/
    └── css/

docker/
├── unified-entrypoint.sh
└── entrypoints or support scripts

docker-compose.unified.yml
Dockerfile.unified
run.py
```

**Structure Decision**: [State which real directories/files are in scope and why.]

## Phase 0: Research

Resolve unknowns before design:

- Data ownership and affected DuckDB tables.
- Existing routes/services/pages that already implement related behavior.
- Runtime mode required: isolated compose, unified compose or local dev.
- Security or validation rules for affected users/data.

## Phase 1: Design

Produce or update:

- `data-model.md` for entities, states, validation and DuckDB table impact.
- `contracts/` for API routes, request/response shapes or UI/data contracts when relevant.
- `quickstart.md` with exact validation steps for browser, API, data and Docker/runtime checks.

## Complexity Tracking

Use only if the plan violates a constitution gate and needs justification.

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| [Violation] | [Reason] | [Alternative] |
