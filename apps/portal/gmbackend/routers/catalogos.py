"""
routers/catalogos.py — Catálogos/paquetes configurables del portal B2B.
"""

from __future__ import annotations

from typing import Any, Optional

import duckdb
from fastapi import APIRouter, Depends, HTTPException

from gmbackend.database import get_db
from gmbackend.routers.auth import get_current_user_optional
from gmbackend.services import catalogo_service

router = APIRouter(prefix="/api/catalogos", tags=["catalogos"])


def _id_cliente(current: Optional[dict]) -> Optional[int]:
    if not current:
        return None
    cliente = current.get("cliente")
    if not cliente:
        return None
    try:
        return int(cliente["id_cliente"])
    except (KeyError, TypeError, ValueError):
        return None


@router.get("", summary="Listar catálogos/paquetes comprables")
def listar_catalogos(
    conn: duckdb.DuckDBPyConnection = Depends(get_db),
    current: Optional[dict] = Depends(get_current_user_optional),
) -> list[dict[str, Any]]:
    return catalogo_service.listar_catalogos(conn, id_cliente=_id_cliente(current))


@router.get("/{id_catalogo}", summary="Detalle de catálogo con productos configurables")
def detalle_catalogo(
    id_catalogo: int,
    conn: duckdb.DuckDBPyConnection = Depends(get_db),
    current: Optional[dict] = Depends(get_current_user_optional),
) -> dict[str, Any]:
    catalogo = catalogo_service.obtener_catalogo(
        conn, id_catalogo, id_cliente=_id_cliente(current)
    )
    if not catalogo:
        raise HTTPException(status_code=404, detail="Catálogo no encontrado.")
    return catalogo