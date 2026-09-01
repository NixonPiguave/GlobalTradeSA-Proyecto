"""
routers/comprobantes.py — Descarga de comprobantes PDF (panel admin).
"""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response

from backend.database import get_connection
from backend.middleware.authz import require_staff
from shared.pdf import comprobante_service

router = APIRouter()


@router.get("", summary="Metadatos de comprobante")
def metadatos(
    tipo: str = Query(...),
    entidad_id: int = Query(...),
    _: dict = Depends(require_staff),
) -> dict[str, Any]:
    with get_connection() as conn:
        meta = comprobante_service.obtener_comprobante_meta(conn, tipo=tipo, entidad_id=entidad_id)
    if not meta:
        raise HTTPException(status_code=404, detail="Comprobante no generado aún.")
    return meta


@router.get("/{tipo}/{entidad_id}/pdf", summary="Descargar comprobante PDF")
def descargar_pdf(
    tipo: str,
    entidad_id: int,
    usuario: dict = Depends(require_staff),
) -> Response:
    with get_connection() as conn:
        try:
            data, filename = comprobante_service.leer_pdf_bytes(
                conn, tipo=tipo, entidad_id=entidad_id, id_usuario=usuario["id_usuario"]
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
