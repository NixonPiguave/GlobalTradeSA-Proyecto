"""Router notificaciones ERP."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from backend.database import get_connection
from backend.middleware.authz import require_staff
from shared.services import notificacion_service as ns

logger = logging.getLogger(__name__)

router = APIRouter(tags=["notificaciones"])


@router.get("")
def listar(limit: int = 30, usuario: dict = Depends(require_staff)) -> dict[str, Any]:
    with get_connection() as conn:
        # Refresca avisos operativos (stock bajo) sin duplicar recientes
        try:
            ns.sincronizar_alertas_stock(conn)
        except Exception as exc:
            logger.warning("No se pudo sincronizar alertas de stock: %s", exc)
        try:
            ns.compactar_duplicados(conn, id_usuario=int(usuario["id_usuario"]))
        except Exception as exc:
            logger.warning("No se pudo compactar duplicados: %s", exc)
        items = ns.listar(conn, id_usuario=int(usuario["id_usuario"]), limit=limit)
        return {"items": items, "no_leidas": ns.no_leidas(conn, id_usuario=int(usuario["id_usuario"]))}


@router.post("/leer-todas")
def leer_todas(usuario: dict = Depends(require_staff)) -> dict[str, Any]:
    with get_connection() as conn:
        n = ns.marcar_todas(conn, id_usuario=int(usuario["id_usuario"]))
        return {"ok": True, "marcadas": n}


@router.post("/limpiar")
def limpiar_bandeja(usuario: dict = Depends(require_staff)) -> dict[str, Any]:
    with get_connection() as conn:
        n = ns.limpiar(conn, id_usuario=int(usuario["id_usuario"]))
        return {"ok": True, "eliminadas": n}


@router.post("/{id_notif}/leida")
def marcar(id_notif: int, usuario: dict = Depends(require_staff)) -> dict[str, Any]:
    with get_connection() as conn:
        ok = ns.marcar_leida(conn, id_usuario=int(usuario["id_usuario"]), id_notif=id_notif)
        if not ok:
            raise HTTPException(status_code=404, detail="Notificación no encontrada.")
        return {"ok": True}


@router.delete("/{id_notif}")
def eliminar(id_notif: int, usuario: dict = Depends(require_staff)) -> dict[str, Any]:
    with get_connection() as conn:
        ns.eliminar(conn, id_usuario=int(usuario["id_usuario"]), id_notif=id_notif)
        return {"ok": True}
