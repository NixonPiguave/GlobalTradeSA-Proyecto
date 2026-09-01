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

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from backend.config import get_settings
from backend.database import init_db, close_db, create_indexes, get_connection, release_thread_connection, warmup_worker
from backend.services.pocketbase_sync_service import try_startup_sync
from backend.logger import configure_root_logger, get_logger
from backend.middleware.error_handler import add_error_handlers
from backend.middleware.query_timer import QueryTimerMiddleware

# Routers
from backend.routers import dashboard, etl, ventas, rentabilidad, maestras, generador

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Directorio raíz del proyecto (un nivel arriba de backend/)
# ---------------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent.parent
FRONTEND_DIR = BASE_DIR / "frontend"


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

# ---------------------------------------------------------------------------
# Routers — todos bajo el prefijo /api
# ---------------------------------------------------------------------------

app.include_router(dashboard.router,    prefix="/api/dashboard",    tags=["Dashboard"])
app.include_router(etl.router,          prefix="/api/etl",          tags=["ETL"])
app.include_router(ventas.router,       prefix="/api/ventas",       tags=["Ventas"])
app.include_router(rentabilidad.router, prefix="/api/rentabilidad", tags=["Rentabilidad"])
# El router de maestras define /{tabla}/ y /{tabla}/{id}/ — se monta bajo
# /api/maestras para que las rutas finales sean /api/maestras/regiones/, etc.
app.include_router(maestras.router,     prefix="/api/maestras",     tags=["Tablas Maestras"])
app.include_router(generador.router,    prefix="/api/generador",    tags=["Generador de Ventas"])

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
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")
    logger.info("Frontend SPA montado desde: %s", FRONTEND_DIR)
else:
    logger.warning(
        "Directorio frontend no encontrado en %s — los archivos estáticos no se servirán.",
        FRONTEND_DIR,
    )
