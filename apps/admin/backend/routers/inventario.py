"""
routers/inventario.py — Stock, movimientos, ajustes y alertas.
"""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from backend.database import get_connection, notify_db_changed
from backend.middleware.authz import require_staff
from backend.models.inventario import AjusteStock, AlertaStockCreate, TransferenciaStock
from backend.services import inventario_service
from backend.services.auditoria_service import registrar_auditoria

router = APIRouter()


@router.get("/stock", summary="Stock por producto en la red de bodegas")
def listar_stock(
    solo_bajo: bool = False,
    q: Optional[str] = None,
    id_almacen: Optional[int] = None,
    macro_zona: Optional[str] = None,
    _: dict = Depends(require_staff),
) -> list[dict[str, Any]]:
    with get_connection() as conn:
        return inventario_service.listar_stock(
            conn, solo_bajo=solo_bajo, q=q, id_almacen=id_almacen, macro_zona=macro_zona
        )


@router.get("/red", summary="Panorama de la red de bodegas por macro-zona")
def panorama_red(_: dict = Depends(require_staff)) -> dict[str, Any]:
    with get_connection() as conn:
        return inventario_service.panorama_red(conn)


@router.get("/stock/{id_producto}/bodegas", summary="Desglose de un producto por bodega")
def stock_por_bodega(id_producto: int, _: dict = Depends(require_staff)) -> dict[str, Any]:
    with get_connection() as conn:
        return inventario_service.stock_producto_por_bodega(conn, id_producto)


@router.post("/transferencias", summary="Transferir stock entre bodegas")
def transferir(body: TransferenciaStock, usuario: dict = Depends(require_staff)) -> dict[str, Any]:
    with get_connection() as conn:
        try:
            resultado = inventario_service.transferir_stock(
                conn,
                id_producto=body.id_producto,
                id_almacen_origen=body.id_almacen_origen,
                id_almacen_destino=body.id_almacen_destino,
                cantidad=body.cantidad,
                id_usuario=usuario["id_usuario"],
            )
        except ValueError as e:
            raise HTTPException(status_code=422, detail=str(e))
        registrar_auditoria(
            conn, id_usuario=usuario["id_usuario"], entidad="stock",
            entidad_id=body.id_producto, accion="transferencia", valor_nuevo=resultado,
        )
        notify_db_changed(conn)
    return resultado


@router.post("/red/reabastecer", summary="Surtir las bodegas que no cubren su objetivo")
def reabastecer(
    solo_vacias: bool = True, usuario: dict = Depends(require_staff)
) -> dict[str, Any]:
    with get_connection() as conn:
        try:
            resultado = inventario_service.reabastecer_red(
                conn, id_usuario=usuario["id_usuario"], solo_vacias=solo_vacias
            )
        except ValueError as e:
            raise HTTPException(status_code=422, detail=str(e))
        registrar_auditoria(
            conn, id_usuario=usuario["id_usuario"], entidad="stock",
            entidad_id=0, accion="reabastecer_red", valor_nuevo=resultado,
        )
        notify_db_changed(conn)
    return resultado


@router.get("/movimientos", summary="Movimientos de inventario (kardex) con filtro de producto")
def listar_movimientos(
    limit: int = Query(default=100, ge=1, le=500),
    id_producto: Optional[int] = None,
    _: dict = Depends(require_staff),
) -> list[dict[str, Any]]:
    with get_connection() as conn:
        return inventario_service.listar_movimientos(conn, limit=limit, id_producto=id_producto)


@router.post("/ajustes", summary="Ajuste manual de stock (+/-)")
def ajustar_stock(body: AjusteStock, usuario: dict = Depends(require_staff)) -> dict[str, Any]:
    with get_connection() as conn:
        try:
            resultado = inventario_service.ajustar_stock(
                conn,
                id_producto=body.id_producto,
                cantidad=body.cantidad,
                motivo=body.motivo,
                id_usuario=usuario["id_usuario"],
                id_almacen=body.id_almacen,
            )
        except ValueError as e:
            raise HTTPException(status_code=422, detail=str(e))
        registrar_auditoria(
            conn, id_usuario=usuario["id_usuario"], entidad="stock",
            entidad_id=body.id_producto, accion="ajuste",
            valor_nuevo={"cantidad": body.cantidad, "motivo": body.motivo},
        )
        notify_db_changed(conn)
    return resultado


@router.post("/alertas", summary="Fijar umbral de alerta de stock")
def fijar_alerta(body: AlertaStockCreate, usuario: dict = Depends(require_staff)) -> dict[str, Any]:
    with get_connection() as conn:
        alerta = inventario_service.fijar_alerta(
            conn,
            id_producto=body.id_producto,
            umbral_minimo=body.umbral_minimo,
            id_almacen=body.id_almacen,
        )
        registrar_auditoria(
            conn, id_usuario=usuario["id_usuario"], entidad="alerta_stock",
            entidad_id=alerta["id_alerta"], accion="fijar", valor_nuevo=alerta,
        )
        notify_db_changed(conn)
    return alerta


@router.get("/alertas", summary="Alertas de stock bajo activas")
def alertas_activas(_: dict = Depends(require_staff)) -> list[dict[str, Any]]:
    with get_connection() as conn:
        return inventario_service.alertas_activas(conn)
