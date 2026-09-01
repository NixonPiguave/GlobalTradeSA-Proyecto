"""
routers/marketing.py — Contenido público del landing (banners, promociones).
"""

from __future__ import annotations

from typing import Any

import duckdb
from fastapi import APIRouter, Depends

from gmbackend.database import get_db
from gmbackend.services import marketing_service
from shared.services.config_service import obtener_config

router = APIRouter(prefix="/api/marketing", tags=["marketing"])


@router.get("/home", summary="Banners y promociones del landing")
def home(conn: duckdb.DuckDBPyConnection = Depends(get_db)) -> dict[str, Any]:
    return marketing_service.datos_home(conn)


@router.get("/branding", summary="Logo y nombre públicos del portal")
def branding(conn: duckdb.DuckDBPyConnection = Depends(get_db)) -> dict[str, Any]:
    logo = (obtener_config(conn, "EMPRESA_LOGO", "") or "").strip()
    nombre = (obtener_config(conn, "EMPRESA_NOMBRE", "GlobMarket B2B") or "GlobMarket B2B").strip()
    return {
        "nombre": nombre,
        "logo_url": f"/media/{logo}" if logo else None,
        "marca_corta": "GM",
    }
