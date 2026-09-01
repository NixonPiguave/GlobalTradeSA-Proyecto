from __future__ import annotations

import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from gmbackend.config import get_settings
from gmbackend.routers.auth import router as auth_router
from gmbackend.routers.productos import router as productos_router


logger = logging.getLogger("globmarket")


BASE_DIR = Path(__file__).resolve().parent.parent  # GlobMarket-B2B/
FRONTEND_DIR = BASE_DIR / "frontend"


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

    # Routers
    app.include_router(auth_router)
    app.include_router(productos_router)

    # Frontend (público) como archivos estáticos
    if FRONTEND_DIR.exists():
        app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")
        logger.info("Frontend montado desde: %s", FRONTEND_DIR)

    return app


app = create_app()

