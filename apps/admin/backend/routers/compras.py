"""
routers/compras.py — Proveedores, órdenes de compra y recepciones.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response

from backend.database import get_connection, notify_db_changed
from backend.middleware.authz import require_staff
from backend.models.inventario import OrdenCompraCreate, ProveedorCreate, ProveedorUpdate, RecepcionCreate
from backend.services import compras_service, proveedor_service
from backend.services.auditoria_service import registrar_auditoria
from shared.pdf import comprobante_service

router = APIRouter()


class EstadoOC(str, Enum):
    borrador = "borrador"
    aprobada = "aprobada"
    parcialmente_recibida = "parcialmente_recibida"
    recibida = "recibida"
    cancelada = "cancelada"


# --- Proveedores ---

@router.get("/proveedores", summary="Listar proveedores")
def listar_proveedores(
    incluir_inactivos: bool = False,
    q: Optional[str] = None,
    _: dict = Depends(require_staff),
) -> list[dict[str, Any]]:
    with get_connection() as conn:
        return proveedor_service.listar_proveedores(
            conn, incluir_inactivos=incluir_inactivos, q=q
        )


@router.post("/proveedores", status_code=201, summary="Crear proveedor")
def crear_proveedor(body: ProveedorCreate, usuario: dict = Depends(require_staff)) -> dict[str, Any]:
    with get_connection() as conn:
        try:
            prov = proveedor_service.crear_proveedor(
                conn, razon_social=body.razon_social, ruc=body.ruc, id_country=body.id_country
            )
        except ValueError as e:
            raise HTTPException(status_code=409, detail=str(e))
        registrar_auditoria(
            conn, id_usuario=usuario["id_usuario"], entidad="proveedor",
            entidad_id=prov["id_proveedor"], accion="crear", valor_nuevo=prov,
        )
        notify_db_changed(conn)
    return prov


@router.put("/proveedores/{id_proveedor}", summary="Actualizar proveedor")
def actualizar_proveedor(
    id_proveedor: int, body: ProveedorUpdate, usuario: dict = Depends(require_staff)
) -> dict[str, Any]:
    with get_connection() as conn:
        try:
            prov = proveedor_service.actualizar_proveedor(conn, id_proveedor, body.model_dump(exclude_unset=True))
        except ValueError as e:
            raise HTTPException(status_code=409, detail=str(e))
        if not prov:
            raise HTTPException(status_code=404, detail="Proveedor no encontrado.")
        registrar_auditoria(
            conn, id_usuario=usuario["id_usuario"], entidad="proveedor",
            entidad_id=id_proveedor, accion="actualizar", valor_nuevo=prov,
        )
        notify_db_changed(conn)
    return prov


@router.delete("/proveedores/{id_proveedor}", summary="Eliminar proveedor (solo sin órdenes)")
def eliminar_proveedor(
    id_proveedor: int, usuario: dict = Depends(require_staff)
) -> dict[str, Any]:
    with get_connection() as conn:
        try:
            proveedor_service.eliminar_proveedor(conn, id_proveedor)
        except KeyError:
            raise HTTPException(status_code=404, detail="Proveedor no encontrado.")
        except ValueError as e:
            raise HTTPException(status_code=409, detail=str(e))
        registrar_auditoria(
            conn, id_usuario=usuario["id_usuario"], entidad="proveedor",
            entidad_id=id_proveedor, accion="eliminar",
        )
        notify_db_changed(conn)
    return {"ok": True}


# --- Órdenes de compra ---

@router.get("/costo-sugerido", summary="Costo unitario sugerido para una OC")
def costo_sugerido(
    id_producto: int,
    id_proveedor: Optional[int] = None,
    _: dict = Depends(require_staff),
) -> dict[str, Any]:
    with get_connection() as conn:
        try:
            return compras_service.costo_sugerido_compra(
                conn, id_producto=id_producto, id_proveedor=id_proveedor
            )
        except ValueError as e:
            raise HTTPException(status_code=422, detail=str(e))


@router.get("/ordenes", summary="Listar órdenes de compra")
def listar_ordenes(estado: Optional[EstadoOC] = None, _: dict = Depends(require_staff)) -> list[dict[str, Any]]:
    with get_connection() as conn:
        return compras_service.listar_ordenes(conn, estado=estado.value if estado else None)


@router.get("/ordenes/{id_oc}", summary="Detalle de orden de compra")
def obtener_orden(id_oc: int, _: dict = Depends(require_staff)) -> dict[str, Any]:
    with get_connection() as conn:
        orden = compras_service.obtener_orden(conn, id_oc)
    if not orden:
        raise HTTPException(status_code=404, detail="Orden de compra no encontrada.")
    return orden


@router.get("/ordenes/{id_oc}/pdf", summary="Descargar PDF de orden de compra")
def pdf_orden(id_oc: int, usuario: dict = Depends(require_staff)) -> Response:
    with get_connection() as conn:
        try:
            data, filename = comprobante_service.leer_pdf_bytes(
                conn, tipo="orden_compra", entidad_id=id_oc, id_usuario=usuario["id_usuario"]
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


@router.post("/ordenes", status_code=201, summary="Crear orden de compra")
def crear_orden(body: OrdenCompraCreate, usuario: dict = Depends(require_staff)) -> dict[str, Any]:
    with get_connection() as conn:
        try:
            orden = compras_service.crear_orden_compra(
                conn,
                id_proveedor=body.id_proveedor,
                items=[i.model_dump() for i in body.items],
                metodo_pago=body.metodo_pago or "caja",
            )
        except ValueError as e:
            raise HTTPException(status_code=422, detail=str(e))
        registrar_auditoria(
            conn, id_usuario=usuario["id_usuario"], entidad="orden_compra",
            entidad_id=orden["id_oc"], accion="crear", valor_nuevo={"numero": orden["numero"], "total": orden["total"]},
        )
        notify_db_changed(conn)
    return orden


@router.post("/ordenes/{id_oc}/estado", summary="Cambiar estado de orden (aprobar/cancelar)")
def cambiar_estado(id_oc: int, estado: EstadoOC, usuario: dict = Depends(require_staff)) -> dict[str, Any]:
    with get_connection() as conn:
        try:
            orden = compras_service.cambiar_estado_oc(conn, id_oc, estado.value)
        except ValueError as e:
            raise HTTPException(status_code=422, detail=str(e))
        registrar_auditoria(
            conn, id_usuario=usuario["id_usuario"], entidad="orden_compra",
            entidad_id=id_oc, accion=f"estado:{estado.value}",
        )
        notify_db_changed(conn)
    return orden


@router.post("/ordenes/{id_oc}/recibir", summary="Recibir orden de compra (completa o parcial)")
def recibir_orden(id_oc: int, body: RecepcionCreate, usuario: dict = Depends(require_staff)) -> dict[str, Any]:
    with get_connection() as conn:
        try:
            resultado = compras_service.recibir_orden(
                conn, id_oc=id_oc, id_almacen=body.id_almacen, id_usuario=usuario["id_usuario"],
                recibos=[i.model_dump() for i in (body.recibos or [])] or None,
            )
        except ValueError as e:
            raise HTTPException(status_code=422, detail=str(e))
        registrar_auditoria(
            conn, id_usuario=usuario["id_usuario"], entidad="orden_compra",
            entidad_id=id_oc, accion="recibir", valor_nuevo={"id_recepcion": resultado["id_recepcion"]},
        )
        notify_db_changed(conn)
    return resultado


@router.get("/recepciones", summary="Historial de recepciones de compra")
def listar_recepciones(
    id_oc: Optional[int] = None,
    id_producto: Optional[int] = None,
    limit: int = 100,
    _: dict = Depends(require_staff),
) -> list[dict[str, Any]]:
    with get_connection() as conn:
        return compras_service.listar_recepciones(
            conn, id_oc=id_oc, id_producto=id_producto, limit=limit
        )


@router.get("/cuentas-por-pagar", summary="Deuda a proveedores (recibido vs pagado)")
def cuentas_por_pagar(
    id_proveedor: Optional[int] = None, _: dict = Depends(require_staff)
) -> dict[str, Any]:
    with get_connection() as conn:
        return compras_service.cuentas_por_pagar(conn, id_proveedor=id_proveedor)
