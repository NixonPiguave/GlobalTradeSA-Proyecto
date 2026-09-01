"""
routers/auditoria.py — Consulta del log de auditoría operativa.
"""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, Query

from backend.database import get_connection
from backend.middleware.authz import require_staff
from backend.services import auditoria_service

router = APIRouter()


@router.get("/filtros", summary="Catálogo de entidades/acciones para filtros")
def filtros(_: dict = Depends(require_staff)) -> dict[str, Any]:
    with get_connection() as conn:
        return auditoria_service.catalogo_filtros(conn)


@router.get("", summary="Listar eventos de auditoría")
def listar(
    entidad: Optional[str] = Query(None),
    accion: Optional[str] = Query(None),
    email: Optional[str] = Query(None),
    entidad_id: Optional[int] = Query(None),
    desde: Optional[str] = Query(None),
    hasta: Optional[str] = Query(None),
    q: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=500),
    page: int = Query(1, ge=1),
    _: dict = Depends(require_staff),
) -> dict[str, Any]:
    offset = (page - 1) * limit
    with get_connection() as conn:
        return auditoria_service.listar_auditoria(
            conn,
            entidad=entidad,
            accion=accion,
            email=email,
            entidad_id=entidad_id,
            desde=desde,
            hasta=hasta,
            q=q,
            limit=limit,
            offset=offset,
        )
