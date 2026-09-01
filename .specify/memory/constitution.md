# GlobalTradeSA Constitution

## Core Principles

### I. Sistema Ejecutable Sobre Documento

Todo cambio debe mejorar o preservar el comportamiento real del sistema. Las especificaciones, planes y tareas de Spec Kit existen para guiar la implementacion de GlobalTradeSA, no para producir documentacion aislada. Una funcionalidad solo se considera terminada cuando puede ejecutarse, probarse o verificarse en la aplicacion.

### II. Dos Productos, Una Vision Empresarial

El monorepo expone dos superficies en un runtime unificado: el panel ERP/analitico en `apps/admin` (`:8000`) y el marketplace B2B en `apps/portal` (`:8001`). Los cambios deben respetar esa separacion, evitando mezclar responsabilidades entre analytics/ETL/reportes y experiencia B2B/catalogo/autenticacion salvo que la integracion este especificada explicitamente. Las carpetas legacy `GlobalTradeSA-duckdb/` y `GlobMarket-B2B/` no son el punto de entrada activo.

### III. Datos Consistentes Y DuckDB Protegido

DuckDB es el nucleo de datos del proyecto. Cualquier cambio que lea, escriba o inicialice la base debe declarar que tablas usa, que proceso escribe, y como evita bloqueos o corrupcion. No se debe asumir escritura concurrente sobre el mismo archivo DuckDB desde varios contenedores o procesos sin una estrategia implementada y verificada.

### IV. Funcionalidad Verificable

Cada requisito funcional debe tener una forma clara de validacion: endpoint, pantalla, flujo de usuario, consulta de base de datos, prueba automatizada o evidencia reproducible. Los requisitos no funcionales deben expresarse con condiciones observables, por ejemplo tiempos de respuesta, reglas de seguridad, disponibilidad local o consistencia de datos.

### V. Seguridad Basica Y Experiencia B2B

El marketplace debe proteger autenticacion, datos de empresas compradoras y sesiones de usuario. No se deben almacenar contrasenas en texto plano ni exponer detalles sensibles en errores. Los flujos B2B deben mantener una experiencia clara para registro, login, catalogo, detalle de producto, carrito, pedidos y checkout (pago simulado). El panel admin debe filtrar navegacion y APIs por permisos de modulo (`mod.*`).

### VI. Despliegue Local Reproducible

El proyecto debe poder levantarse de forma confiable en Windows con Docker Desktop y PowerShell. Los cambios que afecten arranque, puertos, variables de entorno, volumenes, entrypoints o dependencias deben mantener funcionando los servicios locales esperados en `http://localhost:8000` y `http://localhost:8001`, o explicar el nuevo comportamiento en la spec.

## Project Boundaries

### Implementado Actualmente (roadmap Spec Kit)

| Spec | Status | Alcance |
|------|--------|---------|
| `001-sistema-operativo-completo` | Implemented | Fundacion: monorepo, DuckDB DDL/seeds, runtime, auth admin base |
| `003-portal-b2b-carrito-checkout` | Implemented | Portal: carrito, checkout, mis pedidos, perfil, wishlist, marketing |
| `004-admin-operativo-catalogo-inventario` | Implemented | Admin: catalogo, inventario, compras, pedidos, clientes, logistica |
| `005-comprobantes-reportes-pdf` | Implemented | PDF comprobantes + reportes exportables |
| `006-analytics-contabilidad-integracion` | Implemented | fact_ventas, dashboard KPIs, contabilidad minima, ETL base |
| `002-reestructuracion-profesional` | Implemented | Nav por dominio, gobierno, ClickHouse, Airflow, informes UX, notificaciones |

Orden logico de desarrollo: **001 → 003/004 (paralelo) → 005 → 006 → 002**.

### En Implementacion

Ninguna feature Spec Kit abierta. El trabajo nuevo debe crear o extender specs bajo `specs/` (007+) antes de implementar.

### Fuera De Alcance

Pasarelas de pago reales (el pago es simulado), integraciones con partners externos, CDN de imagenes en la nube, Kubernetes productivo, ML entrenado como producto, contabilidad avanzada (cierre de periodos, balances formales, libros mayores), multi-empresa y nomina. OpenSpec/opsx no forma parte del flujo activo.

### Fuera De Suposicion

No se debe presentar como implementado lo que aun no existe en codigo. Cada capacidad se considera terminada solo cuando puede ejecutarse y verificarse (navegador, endpoint, consulta DuckDB/ClickHouse, comprobante descargable o arranque Docker).

## Technical Constraints

- Backend principal en Python/FastAPI; mantener convenciones existentes de routers, services, configuracion y acceso a datos.
- Frontend actual basado en HTML, CSS y JavaScript estatico; no introducir frameworks nuevos sin justificacion en el plan.
- DuckDB debe inicializarse de forma idempotente cuando aplique.
- Las variables sensibles o de entorno deben vivir en `.env` o ejemplos seguros; no insertar secretos reales en el repositorio.
- Los cambios de Docker deben considerar Windows, rutas del monorepo, volumenes persistentes y puertos `8000`/`8001`.
- Mantener compatibilidad con el flujo academico del proyecto, pero priorizando que el software funcione.

## Spec Kit Workflow

- Usar `/speckit-constitution` solo cuando cambien reglas base del proyecto.
- Usar `/speckit-specify` para definir funcionalidades nuevas o cambios importantes antes de implementarlos.
- Usar `/speckit-clarify` cuando existan dudas sobre alcance, actores, datos, reglas de negocio o criterios de aceptacion.
- Usar `/speckit-plan` para cambios que toquen arquitectura, base de datos, Docker, autenticacion o varios modulos.
- Usar `/speckit-tasks` para convertir la spec y el plan en trabajo implementable.
- Usar `/speckit-implement` solo despues de tener tareas claras.
- Usar `/speckit-analyze` y `/speckit-checklist` para revisar coherencia y completitud antes de dar por cerrado un cambio.

## Quality Gates

Antes de cerrar una funcionalidad, se debe verificar como minimo:

- El servicio afectado arranca localmente.
- El flujo principal funciona desde navegador, endpoint o comando reproducible.
- Los cambios de datos son consistentes e idempotentes.
- No se rompen los puertos, rutas, login, catalogo o dashboard existentes.
- La spec no promete funcionalidades que el codigo no implementa.

## Governance

Esta constitucion guia el uso de Spec Kit en este repositorio. Si entra en conflicto con una instruccion puntual del usuario o del equipo, se debe actualizar la spec o la constitucion antes de implementar. Las decisiones tecnicas deben favorecer un sistema ejecutable, simple y verificable sobre cambios decorativos o puramente documentales.

**Version**: 1.3.0 | **Ratified**: 2026-06-30 | **Last Amended**: 2026-08-29
