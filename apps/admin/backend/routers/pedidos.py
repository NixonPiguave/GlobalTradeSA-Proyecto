"""
routers/pedidos.py — Administración de pedidos del panel.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from backend.database import get_connection, notify_db_changed
from backend.middleware.authz import require_staff
from backend.services import pedido_admin_service
from backend.services.auditoria_service import registrar_auditoria

router = APIRouter()


class EstadoPedido(str, Enum):
    borrador = "borrador"
    pendiente_pago = "pendiente_pago"
    pagado = "pagado"
    preparando = "preparando"
    enviado = "enviado"
    entregado = "entregado"
    cancelado = "cancelado"


class CambioEstado(BaseModel):
    estado: EstadoPedido
    id_transportista: Optional[int] = None


@router.get("", summary="Listar pedidos (admin)")
def listar_pedidos(
    estado: Optional[EstadoPedido] = None,
    q: Optional[str] = None,
    page: int = 1,
    page_size: int = 20,
    _: dict = Depends(require_staff),
) -> dict[str, Any]:
    with get_connection() as conn:
        return pedido_admin_service.listar_pedidos(conn, estado=estado.value if estado else None, q=q, page=page, page_size=page_size)


@router.get("/{id_pedido}", summary="Detalle de pedido (admin)")
def detalle_pedido(id_pedido: int, _: dict = Depends(require_staff)) -> dict[str, Any]:
    with get_connection() as conn:
        pedido = pedido_admin_service.obtener_pedido_admin(conn, id_pedido)
    if not pedido:
        raise HTTPException(status_code=404, detail="Pedido no encontrado.")
    return pedido


@router.post("/{id_pedido}/estado", summary="Cambiar estado del pedido")
def cambiar_estado(
    id_pedido: int, body: CambioEstado, usuario: dict = Depends(require_staff)
) -> dict[str, Any]:
    with get_connection() as conn:
        if body.estado == EstadoPedido.enviado:
            from backend.services import logistica_service
            envio = logistica_service.obtener_envio_pedido(conn, id_pedido)
            if not envio and not body.id_transportista:
                raise HTTPException(
                    status_code=422,
                    detail="Indica un transportista para marcar el pedido como enviado.",
                )
        try:
            resultado = pedido_admin_service.cambiar_estado_admin(
                conn,
                id_pedido=id_pedido,
                nuevo_estado=body.estado.value,
                id_usuario=usuario["id_usuario"],
                id_transportista=body.id_transportista,
            )
        except ValueError as e:
            raise HTTPException(status_code=422, detail=str(e))
        registrar_auditoria(
            conn, id_usuario=usuario["id_usuario"], entidad="pedido",
            entidad_id=id_pedido, accion=f"estado:{body.estado.value}",
            valor_anterior=resultado.get("estado_anterior"), valor_nuevo=body.estado.value,
        )
        notify_db_changed(conn)
        pedido = pedido_admin_service.obtener_pedido_admin(conn, id_pedido)
    return pedido or {}
