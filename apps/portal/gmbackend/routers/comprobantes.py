"""
routers/comprobantes.py — Descarga de comprobantes PDF del portal (solo propios).
"""

from __future__ import annotations

from typing import Any

import duckdb
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response

from gmbackend.database import get_db
from gmbackend.routers.auth import get_current_user
from shared.pdf import comprobante_service

router = APIRouter(prefix="/api/comprobantes", tags=["comprobantes"])


def _id_cliente(current: dict) -> int:
    cliente = current.get("cliente")
    if not cliente:
        raise HTTPException(status_code=403, detail="La cuenta no tiene ficha de cliente B2B.")
    return int(cliente["id_cliente"])


@router.get("", summary="Metadatos de mi comprobante")
def metadatos(
    tipo: str = Query(...),
    entidad_id: int = Query(...),
    current: dict = Depends(get_current_user),
    conn: duckdb.DuckDBPyConnection = Depends(get_db),
) -> dict[str, Any]:
    id_cliente = _id_cliente(current)
    if not comprobante_service.verificar_acceso_cliente(conn, tipo=tipo, entidad_id=entidad_id, id_cliente=id_cliente):
        raise HTTPException(status_code=403, detail="No tienes acceso a este comprobante.")
    meta = comprobante_service.obtener_comprobante_meta(conn, tipo=tipo, entidad_id=entidad_id)
    if not meta:
        raise HTTPException(status_code=404, detail="Comprobante no generado aún.")
    return meta


@router.get("/{tipo}/{entidad_id}/pdf", summary="Descargar mi comprobante PDF")
def descargar_pdf(
    tipo: str,
    entidad_id: int,
    current: dict = Depends(get_current_user),
    conn: duckdb.DuckDBPyConnection = Depends(get_db),
) -> Response:
    id_cliente = _id_cliente(current)
    if not comprobante_service.verificar_acceso_cliente(conn, tipo=tipo, entidad_id=entidad_id, id_cliente=id_cliente):
        raise HTTPException(status_code=403, detail="No tienes acceso a este comprobante.")
    try:
        data, filename = comprobante_service.leer_pdf_bytes(
            conn,
            tipo=tipo,
            entidad_id=entidad_id,
            id_usuario=int(current["usuario"]["id_usuario"]),
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return Response(
        content=data,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
