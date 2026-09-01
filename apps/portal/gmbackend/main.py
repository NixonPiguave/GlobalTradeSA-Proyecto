from __future__ import annotations

import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from gmbackend.config import get_settings
from gmbackend.middleware.error_handler import add_error_handlers
from gmbackend.routers.auth import router as auth_router
from gmbackend.routers.carrito import router as carrito_router
from gmbackend.routers.catalogo import router as catalogo_router
from gmbackend.routers.catalogos import router as catalogos_router
from gmbackend.routers.comprobantes import router as comprobantes_router
from gmbackend.routers.cuenta import router as cuenta_router
from gmbackend.routers.marketing import router as marketing_router
from gmbackend.routers.pedidos import router as pedidos_router
from gmbackend.routers.productos import router as productos_router
from gmbackend.routers.wishlist import router as wishlist_router


logger = logging.getLogger("globmarket")


BASE_DIR = Path(__file__).resolve().parent.parent
FRONTEND_DIR = BASE_DIR / "web"


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title="GlobMarket B2B API",
        version="0.1.0",
        description="Portal mayorista internacional (B2B) de GlobTrade S.A.",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS or ["http://127.0.0.1:8001", "http://localhost:8001"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    add_error_handlers(app)

    # Routers
    app.include_router(auth_router)
    app.include_router(cuenta_router)
    app.include_router(catalogo_router)
    app.include_router(catalogos_router)
    app.include_router(productos_router)
    app.include_router(carrito_router)
    app.include_router(pedidos_router)
    app.include_router(comprobantes_router)
    app.include_router(marketing_router)
    app.include_router(wishlist_router)

    # Imágenes subidas desde el panel admin (rutas relativas uploads/...)
    media_dir = BASE_DIR.parent.parent / "shared" / "storage"
    if media_dir.exists():
        app.mount("/media", StaticFiles(directory=str(media_dir)), name="media")

    # Frontend (público) como archivos estáticos
    if FRONTEND_DIR.exists():
        app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")
        logger.info("Frontend montado desde: %s", FRONTEND_DIR)

    return app


app = create_app()

