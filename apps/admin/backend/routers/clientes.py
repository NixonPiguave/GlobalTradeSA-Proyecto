"""
routers/clientes.py — Administración de clientes B2B y CxC.
"""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from backend.database import get_connection, notify_db_changed
from backend.middleware.authz import require_staff
from backend.services import cliente_service
from backend.services.auditoria_service import registrar_auditoria

router = APIRouter()


class CambioActivo(BaseModel):
    activo: bool


class ClienteUpdate(BaseModel):
    nombre_empresa: str = Field(min_length=2, max_length=200)
    pais: str = Field(min_length=2, max_length=100)
    telefono: Optional[str] = Field(default=None, max_length=50)
    direccion: Optional[str] = Field(default=None, max_length=500)


class AsignarGrupo(BaseModel):
    id_grupo: Optional[int] = Field(
        default=None,
        description="Grupo comercial. Null = sin grupo (lista Público por defecto).",
    )


@router.get("/grupos", summary="Grupos comerciales y su lista de precios")
def listar_grupos(_: dict = Depends(require_staff)) -> list[dict[str, Any]]:
    with get_connection() as conn:
        return cliente_service.listar_grupos_cliente(conn)


@router.get("", summary="Listar clientes B2B")
def listar_clientes(q: Optional[str] = None, _: dict = Depends(require_staff)) -> list[dict[str, Any]]:
    with get_connection() as conn:
        return cliente_service.listar_clientes(conn, q=q)


@router.get("/{id_cliente}", summary="Ficha de cliente con historial y CxC")
def obtener_cliente(id_cliente: int, _: dict = Depends(require_staff)) -> dict[str, Any]:
    with get_connection() as conn:
        cliente = cliente_service.obtener_cliente(conn, id_cliente)
    if not cliente:
        raise HTTPException(status_code=404, detail="Cliente no encontrado.")
    return cliente


@router.put("/{id_cliente}", summary="Actualizar datos de empresa del cliente")
def actualizar_cliente(
    id_cliente: int, body: ClienteUpdate, usuario: dict = Depends(require_staff)
) -> dict[str, Any]:
    with get_connection() as conn:
        try:
            cliente = cliente_service.actualizar_cliente(
                conn,
                id_cliente,
                nombre_empresa=body.nombre_empresa.strip(),
                pais=body.pais.strip(),
                telefono=body.telefono.strip() if body.telefono else None,
                direccion=body.direccion.strip() if body.direccion else None,
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc))
        if not cliente:
            raise HTTPException(status_code=404, detail="Cliente no encontrado.")
        registrar_auditoria(
            conn,
            id_usuario=usuario["id_usuario"],
            entidad="cliente",
            entidad_id=id_cliente,
            accion="actualizar",
            valor_nuevo={
                "nombre_empresa": body.nombre_empresa,
                "pais": body.pais,
                "telefono": body.telefono,
                "direccion": body.direccion,
            },
        )
        notify_db_changed(conn)
    return cliente


@router.put("/{id_cliente}/grupo", summary="Asignar grupo comercial / lista de precios")
def asignar_grupo(
    id_cliente: int, body: AsignarGrupo, usuario: dict = Depends(require_staff)
) -> dict[str, Any]:
    with get_connection() as conn:
        try:
            cliente = cliente_service.asignar_grupo_cliente(
                conn, id_cliente, id_grupo=body.id_grupo
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc))
        if not cliente:
            raise HTTPException(status_code=404, detail="Cliente no encontrado.")
        registrar_auditoria(
            conn,
            id_usuario=usuario["id_usuario"],
            entidad="cliente",
            entidad_id=id_cliente,
            accion="asignar_grupo",
            valor_nuevo={"id_grupo": body.id_grupo, "lista_precio": cliente.get("lista_precio")},
        )
        notify_db_changed(conn)
    return cliente


@router.post("/{id_cliente}/activo", summary="Activar/desactivar acceso del cliente")
def cambiar_activo(
    id_cliente: int, body: CambioActivo, usuario: dict = Depends(require_staff)
) -> dict[str, Any]:
    with get_connection() as conn:
        if not cliente_service.activar_desactivar_cliente(conn, id_cliente, body.activo):
            raise HTTPException(status_code=404, detail="Cliente no encontrado o sin usuario asociado.")
        registrar_auditoria(
            conn, id_usuario=usuario["id_usuario"], entidad="cliente",
            entidad_id=id_cliente, accion="activar" if body.activo else "desactivar",
        )
        notify_db_changed(conn)
    return {"ok": True, "activo": body.activo}
