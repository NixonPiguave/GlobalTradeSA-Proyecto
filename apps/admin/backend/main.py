"""
backend/main.py — Punto de entrada de la aplicación FastAPI de GLOBTRADE S.A.

Responsabilidades:
  - Crear la instancia FastAPI con lifespan (arranque / apagado).
  - Leer configuración desde variables de entorno (config.py).
  - Inicializar DuckDB embebido y crear índices.
  - Registrar todos los routers bajo el prefijo /api.
  - Registrar middleware (QueryTimerMiddleware, CORS, ErrorHandlers).
  - Servir el frontend SPA (frontend/) como archivos estáticos en /.

Requisitos cubiertos: 1.1, 1.2, 1.3, 1.4, 1.8, 7.6, 8.4
"""

from __future__ import annotations

import asyncio
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from backend.config import get_settings
from backend.database import init_db, close_db, create_indexes, get_connection, release_thread_connection, warmup_worker
from backend.services.pocketbase_sync_service import try_startup_sync
from backend.logger import configure_root_logger, get_logger
from backend.middleware.error_handler import add_error_handlers
from backend.middleware.query_timer import QueryTimerMiddleware

# Routers
from backend.routers import analytics, auth, auditoria, catalogo, clientes, compras, comprobantes, configuracion, contabilidad, dashboard, estrategia, etl, generador, gobierno, inventario, logistica, maestras, marketing, notificaciones, pedidos, rentabilidad, reportes, ventas
from backend.middleware.authz import require_perm

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Directorio raíz del proyecto (un nivel arriba de backend/)
# ---------------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent.parent
FRONTEND_DIR = BASE_DIR / "web"


# ---------------------------------------------------------------------------
# Lifespan — arranque y apagado controlados
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Gestiona el ciclo de vida de la aplicación:
      - Arranque: configura logging, lee settings, inicializa DuckDB e índices.
      - Apagado: cierra la conexión DuckDB del hilo.
    """
    # Configurar root logger para capturar logs de uvicorn y librerías externas
    configure_root_logger()
    logger.info("Iniciando GLOBTRADE S.A. API...")

    # Leer y validar variables de entorno (SystemExit si faltan)
    settings = get_settings()
    logger.info(
        "Configuración cargada — duckdb=%s",
        settings.duckdb_absolute_path,
    )

    init_db(str(settings.duckdb_absolute_path))

    from shared.database.init_sistema import _extend_compras, _extend_pedidos, _create_views
    from shared.database.migrate_reestructuracion import aplicar_migraciones_reestructuracion

    with get_connection() as conn:
        _extend_pedidos(conn)
        _extend_compras(conn)
        aplicar_migraciones_reestructuracion(conn)
        _create_views(conn)
        from shared.database.init_sistema import _hash_password
        from shared.database.permisos_catalogo import sincronizar_gobierno_demo

        try:
            sincronizar_gobierno_demo(conn, password_hash_fn=_hash_password)
        except Exception as exc:
            logger.warning("Sync permisos/rol gerente omitido: %s", exc)

    create_indexes()

    with get_connection() as conn:
        try_startup_sync(
            conn,
            settings.parquet_absolute_path,
            enabled=settings.POCKETBASE_SYNC_ON_STARTUP,
            base_url=settings.POCKETBASE_URL or None,
            email=settings.POCKETBASE_EMAIL or None,
            password=settings.POCKETBASE_PASSWORD or None,
        )
    release_thread_connection()

    await asyncio.to_thread(warmup_worker)

    logger.info("GLOBTRADE S.A. API lista para recibir solicitudes.")

    yield  # La aplicación está en ejecución

    logger.info("Apagando GLOBTRADE S.A. API...")
    close_db()
    logger.info("Conexión DuckDB cerrada. Hasta luego.")


# ---------------------------------------------------------------------------
# Instancia FastAPI
# ---------------------------------------------------------------------------

app = FastAPI(
    title="GLOBTRADE S.A. — API REST",
    description=(
        "Plataforma de análisis de ventas internacionales: KPIs, rentabilidad, "
        "carga ETL de CSV y gestión de tablas maestras."
    ),
    version="1.0.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
    lifespan=lifespan,
)

# ---------------------------------------------------------------------------
# Middleware — orden de registro: el último en registrarse es el primero en ejecutarse
# ---------------------------------------------------------------------------

# CORS — permite peticiones desde el frontend servido en el mismo origen
# y desde herramientas de desarrollo locales
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],          # En producción restringir al dominio real
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Query-Time-Ms"],
)

# Medir tiempo acumulado de consultas SQL por request
app.add_middleware(QueryTimerMiddleware)


@app.middleware("http")
async def no_cache_frontend(request, call_next):
    """Evita que el navegador sirva JS/CSS viejos tras actualizar la UI."""
    response = await call_next(request)
    path = request.url.path
    if path == "/" or path.endswith((".js", ".css", ".html")):
        response.headers["Cache-Control"] = "no-store, max-age=0"
    return response

# Manejadores globales de excepciones (HTTPException, ValidationError, catch-all)
add_error_handlers(app)

# Rutas públicas (sin dependencias de permisos) — deben registrarse antes del router de configuración
@app.get("/api/configuracion/branding", tags=["Configuración"], summary="Logo público del panel (sin auth)")
def branding_publico() -> dict:
    from shared.services.config_service import obtener_config

    with get_connection() as conn:
        logo = (obtener_config(conn, "EMPRESA_LOGO", "") or "").strip()
        nombre = (obtener_config(conn, "EMPRESA_NOMBRE", "GLOBTRADE S.A.") or "GLOBTRADE S.A.").strip()
    return {
        "nombre": nombre,
        "logo_url": f"/media/{logo}" if logo else None,
        "marca_corta": "GT",
    }

# ---------------------------------------------------------------------------
# Routers — todos bajo el prefijo /api
# ---------------------------------------------------------------------------

app.include_router(analytics.router,    prefix="/api/analytics",    tags=["Analytics"],    dependencies=[Depends(require_perm("mod.reportes", "mod.dashboard"))])
app.include_router(dashboard.internal_router, prefix="/api/dashboard", tags=["Dashboard"])
app.include_router(dashboard.router,    prefix="/api/dashboard",    tags=["Dashboard"],    dependencies=[Depends(require_perm("mod.dashboard"))])
app.include_router(etl.internal_router, prefix="/api/etl", tags=["ETL"])
app.include_router(etl.router,          prefix="/api/etl",          tags=["ETL"],          dependencies=[Depends(require_perm("mod.reportes"))])
app.include_router(ventas.router,       prefix="/api/ventas",       tags=["Ventas"],       dependencies=[Depends(require_perm("mod.ventas"))])
app.include_router(rentabilidad.router, prefix="/api/rentabilidad", tags=["Rentabilidad"], dependencies=[Depends(require_perm("mod.ventas"))])
# El router de maestras define /{tabla}/ y /{tabla}/{id}/ — se monta bajo
# /api/maestras para que las rutas finales sean /api/maestras/regiones/, etc.
app.include_router(maestras.router,     prefix="/api/maestras",     tags=["Tablas Maestras"])
app.include_router(generador.router,    prefix="/api/generador",    tags=["Generador de Ventas"], dependencies=[Depends(require_perm("mod.reportes"))])
app.include_router(auth.router,         prefix="/api/auth",         tags=["Autenticación"])
app.include_router(catalogo.router,     prefix="/api/catalogo",     tags=["Catálogo"],    dependencies=[Depends(require_perm("mod.catalogo"))])
app.include_router(compras.router,      prefix="/api/compras",      tags=["Compras"],     dependencies=[Depends(require_perm("mod.compras"))])
app.include_router(inventario.router,   prefix="/api/inventario",   tags=["Inventario"],  dependencies=[Depends(require_perm("mod.inventario"))])
app.include_router(pedidos.router,      prefix="/api/pedidos",      tags=["Pedidos"],     dependencies=[Depends(require_perm("mod.operaciones"))])
app.include_router(clientes.router,     prefix="/api/clientes",     tags=["Clientes"],    dependencies=[Depends(require_perm("mod.clientes"))])
app.include_router(comprobantes.router, prefix="/api/comprobantes", tags=["Comprobantes"], dependencies=[Depends(require_perm("mod.finanzas", "mod.compras", "mod.ventas", "mod.reportes"))])
app.include_router(reportes.router,     prefix="/api/reportes",     tags=["Reportes"],    dependencies=[Depends(require_perm("mod.reportes"))])
app.include_router(contabilidad.router, prefix="/api/contabilidad", tags=["Contabilidad"], dependencies=[Depends(require_perm("mod.finanzas"))])
app.include_router(logistica.router,     prefix="/api/logistica",     tags=["Logística"],   dependencies=[Depends(require_perm("mod.logistica"))])
app.include_router(marketing.router,     prefix="/api/marketing",     tags=["Marketing"],   dependencies=[Depends(require_perm("mod.marketing"))])
app.include_router(configuracion.router, prefix="/api/configuracion", tags=["Configuración"], dependencies=[Depends(require_perm("mod.gobierno"))])
app.include_router(auditoria.router,     prefix="/api/auditoria",     tags=["Auditoría"],   dependencies=[Depends(require_perm("mod.gobierno"))])
app.include_router(gobierno.router,     prefix="/api/gobierno",     tags=["Gobierno de Acceso"])
app.include_router(notificaciones.router, prefix="/api/notificaciones", tags=["Notificaciones"])
app.include_router(estrategia.router,   prefix="/api/estrategia",   tags=["Estrategia"])

# ---------------------------------------------------------------------------
# Health-check rápido (no requiere BD)
# ---------------------------------------------------------------------------

@app.get("/api/health", tags=["Sistema"], summary="Estado del servidor")
def health_check() -> dict:
    """Devuelve HTTP 200 si el servidor está en ejecución."""
    return {"status": "ok", "service": "globtrade-api", "version": "1.0.0"}


# ---------------------------------------------------------------------------
# Archivos estáticos del frontend SPA
# Debe montarse DESPUÉS de los routers de la API para que /api/* tenga
# prioridad sobre la carpeta estática.
# ---------------------------------------------------------------------------

if FRONTEND_DIR.exists():
    # Imágenes y archivos subidos (compartidos con el portal)
    MEDIA_DIR = BASE_DIR.parent.parent / "shared" / "storage"
    MEDIA_DIR.mkdir(parents=True, exist_ok=True)
    app.mount("/media", StaticFiles(directory=str(MEDIA_DIR)), name="media")

    app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")
    logger.info("Frontend SPA montado desde: %s", FRONTEND_DIR)
else:
    logger.warning(
        "Directorio frontend no encontrado en %s — los archivos estáticos no se servirán.",
        FRONTEND_DIR,
    )
