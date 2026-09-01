"""
routers/logistica.py — Transportistas, zonas y tracking (admin).
"""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from backend.database import get_connection, notify_db_changed
from backend.middleware.authz import require_perm, require_staff
from backend.services import logistica_service

router = APIRouter()


class TransportistaIn(BaseModel):
    nombre: str
    id_region: Optional[int] = None
    macro_zona: Optional[str] = None


class AlmacenIn(BaseModel):
    nombre: str
    direccion: Optional[str] = None
    id_region: Optional[int] = None


class TrackingIn(BaseModel):
    estado: str
    descripcion: Optional[str] = None


class ActivoIn(BaseModel):
    activo: bool


class EnvioPedidoIn(BaseModel):
    id_transportista: int
    id_zona: Optional[int] = None


class ZonaIn(BaseModel):
    nombre: str
    costo_base: float = 0.0
    macro_zona: Optional[str] = None


class TarifaIn(BaseModel):
    id_zona: int
    peso_max: float
    costo: float


@router.get("/transportistas", summary="Listar transportistas")
def transportistas(
    macro_zona: Optional[str] = None, _: dict = Depends(require_staff)
) -> list[dict[str, Any]]:
    with get_connection() as conn:
        return logistica_service.listar_transportistas(
            conn, activos_only=False, macro_zona=macro_zona
        )


@router.post("/transportistas", status_code=201, summary="Crear transportista")
def crear_transportista(body: TransportistaIn, _: dict = Depends(require_staff)) -> dict[str, Any]:
    with get_connection() as conn:
        try:
            return logistica_service.crear_transportista(
                conn, nombre=body.nombre, id_region=body.id_region, macro_zona=body.macro_zona
            )
        except ValueError as e:
            raise HTTPException(status_code=409, detail=str(e))


@router.put("/transportistas/{id_transportista}", summary="Actualizar transportista")
def actualizar_transportista(
    id_transportista: int, body: TransportistaIn, _: dict = Depends(require_staff)
) -> dict[str, Any]:
    with get_connection() as conn:
        try:
            t = logistica_service.actualizar_transportista(
                conn,
                id_transportista,
                nombre=body.nombre,
                id_region=body.id_region,
                macro_zona=body.macro_zona,
            )
        except ValueError as e:
            raise HTTPException(status_code=409, detail=str(e))
        if not t:
            raise HTTPException(status_code=404, detail="Transportista no encontrado.")
        notify_db_changed(conn)
        return t


@router.delete("/transportistas/{id_transportista}", summary="Eliminar transportista (solo sin envíos)")
def eliminar_transportista(id_transportista: int, _: dict = Depends(require_staff)) -> dict[str, Any]:
    with get_connection() as conn:
        try:
            logistica_service.eliminar_transportista(conn, id_transportista)
        except KeyError:
            raise HTTPException(status_code=404, detail="Transportista no encontrado.")
        except ValueError as e:
            raise HTTPException(status_code=409, detail=str(e))
        notify_db_changed(conn)
    return {"ok": True}


@router.post("/transportistas/{id_transportista}/activo", summary="Activar/desactivar transportista")
def activo_transportista(
    id_transportista: int, body: ActivoIn, _: dict = Depends(require_staff)
) -> dict[str, Any]:
    with get_connection() as conn:
        t = logistica_service.set_activo_transportista(
            conn, id_transportista, activo=body.activo
        )
        if not t:
            raise HTTPException(status_code=404, detail="Transportista no encontrado")
        notify_db_changed(conn)
        return t


@router.get("/zonas", summary="Zonas y tarifas de envío")
def zonas(_: dict = Depends(require_staff)) -> list[dict[str, Any]]:
    with get_connection() as conn:
        return logistica_service.listar_zonas_tarifas(conn)


@router.post("/zonas", status_code=201, summary="Crear zona de envío")
def crear_zona(body: ZonaIn, usuario: dict = Depends(require_staff)) -> dict[str, Any]:
    with get_connection() as conn:
        try:
            zona = logistica_service.crear_zona(
                conn, nombre=body.nombre, costo_base=body.costo_base, macro_zona=body.macro_zona
            )
        except ValueError as e:
            raise HTTPException(status_code=409, detail=str(e))
        notify_db_changed(conn)
    return zona


@router.put("/zonas/{id_zona}", summary="Actualizar zona de envío")
def actualizar_zona(id_zona: int, body: ZonaIn, usuario: dict = Depends(require_staff)) -> dict[str, Any]:
    with get_connection() as conn:
        try:
            zona = logistica_service.actualizar_zona(
                conn,
                id_zona=id_zona,
                nombre=body.nombre,
                costo_base=body.costo_base,
                macro_zona=body.macro_zona,
            )
        except ValueError as e:
            raise HTTPException(status_code=404 if "no existe" in str(e) else 409, detail=str(e))
        notify_db_changed(conn)
    return zona


@router.delete("/zonas/{id_zona}", summary="Eliminar zona de envío")
def eliminar_zona(id_zona: int, usuario: dict = Depends(require_staff)) -> dict[str, Any]:
    with get_connection() as conn:
        try:
            logistica_service.eliminar_zona(conn, id_zona=id_zona)
        except ValueError as e:
            raise HTTPException(status_code=409, detail=str(e))
        notify_db_changed(conn)
    return {"ok": True}


@router.post("/tarifas", status_code=201, summary="Crear tarifa de envío")
def crear_tarifa(body: TarifaIn, usuario: dict = Depends(require_staff)) -> dict[str, Any]:
    with get_connection() as conn:
        try:
            tarifa = logistica_service.crear_tarifa(
                conn, id_zona=body.id_zona, peso_max=body.peso_max, costo=body.costo
            )
        except ValueError as e:
            raise HTTPException(status_code=409, detail=str(e))
        notify_db_changed(conn)
    return tarifa


@router.put("/tarifas/{id_tarifa}", summary="Actualizar tarifa de envío")
def actualizar_tarifa(id_tarifa: int, body: TarifaIn, usuario: dict = Depends(require_staff)) -> dict[str, Any]:
    with get_connection() as conn:
        try:
            logistica_service.actualizar_tarifa(
                conn, id_tarifa=id_tarifa, peso_max=body.peso_max, costo=body.costo
            )
        except ValueError as e:
            raise HTTPException(status_code=409, detail=str(e))
        notify_db_changed(conn)
    return {"ok": True}


@router.delete("/tarifas/{id_tarifa}", summary="Eliminar tarifa de envío")
def eliminar_tarifa(id_tarifa: int, usuario: dict = Depends(require_staff)) -> dict[str, Any]:
    with get_connection() as conn:
        try:
            logistica_service.eliminar_tarifa(conn, id_tarifa=id_tarifa)
        except ValueError as e:
            raise HTTPException(status_code=409, detail=str(e))
        notify_db_changed(conn)
    return {"ok": True}


@router.get("/almacenes", summary="Listar almacenes (bodegas por región)")
def almacenes(_: dict = Depends(require_staff)) -> list[dict[str, Any]]:
    with get_connection() as conn:
        return logistica_service.listar_almacenes(conn, activos_only=False)


@router.post("/almacenes", status_code=201, summary="Crear almacén")
def crear_almacen(body: AlmacenIn, _: dict = Depends(require_staff)) -> dict[str, Any]:
    with get_connection() as conn:
        try:
            return logistica_service.crear_almacen(
                conn, nombre=body.nombre, direccion=body.direccion, id_region=body.id_region
            )
        except ValueError as e:
            raise HTTPException(status_code=409, detail=str(e))


@router.put("/almacenes/{id_almacen}", summary="Actualizar almacén")
def actualizar_almacen(
    id_almacen: int, body: AlmacenIn, _: dict = Depends(require_staff)
) -> dict[str, Any]:
    with get_connection() as conn:
        try:
            a = logistica_service.actualizar_almacen(
                conn, id_almacen, nombre=body.nombre, direccion=body.direccion, id_region=body.id_region
            )
        except ValueError as e:
            raise HTTPException(status_code=409, detail=str(e))
        if not a:
            raise HTTPException(status_code=404, detail="Almacén no encontrado.")
        notify_db_changed(conn)
        return a


@router.delete("/almacenes/{id_almacen}", summary="Eliminar almacén (solo sin stock)")
def eliminar_almacen(id_almacen: int, _: dict = Depends(require_staff)) -> dict[str, Any]:
    with get_connection() as conn:
        try:
            logistica_service.eliminar_almacen(conn, id_almacen)
        except KeyError:
            raise HTTPException(status_code=404, detail="Almacén no encontrado.")
        except ValueError as e:
            raise HTTPException(status_code=409, detail=str(e))
        notify_db_changed(conn)
    return {"ok": True}


@router.post("/almacenes/{id_almacen}/activo", summary="Activar/desactivar almacén")
def activo_almacen(id_almacen: int, body: ActivoIn, _: dict = Depends(require_staff)) -> dict[str, Any]:
    with get_connection() as conn:
        a = logistica_service.set_activo_almacen(conn, id_almacen, activo=body.activo)
        if not a:
            raise HTTPException(status_code=404, detail="Almacén no encontrado")
        notify_db_changed(conn)
        return a


@router.get("/almacenes/{id_almacen}/stock", summary="Inventario de un almacén")
def stock_almacen(id_almacen: int, _: dict = Depends(require_staff)) -> dict[str, Any]:
    with get_connection() as conn:
        alm = logistica_service.listar_almacenes(conn, activos_only=False, id_almacen=id_almacen)
        if not alm:
            raise HTTPException(status_code=404, detail="Almacén no encontrado")
        items = logistica_service.stock_por_almacen(conn, id_almacen)
    return {"almacen": alm[0], "items": items}


@router.get("/pedidos", summary="Pedidos con estado de envío")
def pedidos_envio(_: dict = Depends(require_perm("mod.logistica", "mod.operaciones"))) -> list[dict[str, Any]]:
    with get_connection() as conn:
        return logistica_service.listar_pedidos_envio(conn)


@router.get("/pedidos/{id_pedido}/opciones-envio", summary="Transportistas/zonas válidos según país del cliente")
def opciones_envio(
    id_pedido: int, _: dict = Depends(require_perm("mod.logistica", "mod.operaciones"))
) -> dict[str, Any]:
    with get_connection() as conn:
        try:
            return logistica_service.opciones_envio_pedido(conn, id_pedido)
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e))


@router.post("/pedidos/{id_pedido}/envio", status_code=201, summary="Asignar transportista y despachar pedido")
def crear_envio_pedido(
    id_pedido: int, body: EnvioPedidoIn, usuario: dict = Depends(require_perm("mod.logistica", "mod.operaciones"))
) -> dict[str, Any]:
    with get_connection() as conn:
        row = conn.execute("SELECT estado FROM pedidos WHERE id_pedido = ?", [id_pedido]).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Pedido no encontrado.")
        if row[0] not in ("pagado", "preparando"):
            raise HTTPException(
                status_code=400,
                detail=f"El pedido en estado «{row[0]}» no admite despacho.",
            )
        conn.execute("BEGIN TRANSACTION")
        try:
            envio = logistica_service.asignar_transportista_y_despachar(
                conn,
                id_pedido=id_pedido,
                id_transportista=body.id_transportista,
                id_zona=body.id_zona,
                id_usuario=usuario["id_usuario"],
            )
            conn.execute("COMMIT")
        except ValueError as e:
            conn.execute("ROLLBACK")
            raise HTTPException(status_code=409, detail=str(e))
        notify_db_changed(conn)
        return envio


@router.get("/pedidos/{id_pedido}/envio", summary="Envío y tracking de un pedido")
def envio_pedido(
    id_pedido: int, _: dict = Depends(require_perm("mod.logistica", "mod.operaciones"))
) -> dict[str, Any]:
    with get_connection() as conn:
        envio = logistica_service.obtener_envio_pedido(conn, id_pedido)
    if not envio:
        raise HTTPException(status_code=404, detail="Sin envío registrado para este pedido.")
    return envio


@router.post("/envios/{id_envio}/evento", summary="Registrar evento de tracking")
def evento_tracking(
    id_envio: int, body: TrackingIn, usuario: dict = Depends(require_perm("mod.logistica", "mod.operaciones"))
) -> dict[str, Any]:
    with get_connection() as conn:
        try:
            conn.execute("BEGIN TRANSACTION")
            resultado = logistica_service.registrar_evento_tracking(
                conn,
                id_envio=id_envio,
                estado=body.estado,
                descripcion=body.descripcion,
                id_usuario=usuario["id_usuario"],
            )
            conn.execute("COMMIT")
            notify_db_changed(conn)
            return resultado
        except ValueError as e:
            conn.execute("ROLLBACK")
            raise HTTPException(status_code=422, detail=str(e))
