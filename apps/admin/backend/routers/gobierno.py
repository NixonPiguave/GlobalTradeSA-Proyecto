"""
routers/gobierno.py — Gestión de usuarios, roles y permisos del panel.

Todo el módulo exige el permiso `mod.gobierno` (el rol admin lo tiene implícito).
"""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, EmailStr, Field

from backend.database import get_connection
from backend.middleware.authz import require_perm
from backend.services.gobierno_service import (
    actualizar_rol,
    actualizar_usuario_staff,
    asignar_permisos_rol,
    crear_rol,
    crear_usuario_staff,
    desactivar_usuario_staff,
    eliminar_rol,
    listar_permisos,
    listar_roles_detalle,
    listar_usuarios_staff,
)

router = APIRouter(dependencies=[Depends(require_perm("mod.gobierno"))])


class UsuarioCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=6, max_length=128)
    rol: str
    nombre: str = ""
    id_region: Optional[int] = None


class UsuarioUpdate(BaseModel):
    email: Optional[EmailStr] = None
    rol: Optional[str] = None
    nombre: Optional[str] = None
    password: Optional[str] = Field(default=None, min_length=6, max_length=128)
    activo: Optional[bool] = None
    id_region: Optional[int] = None


class RolCreate(BaseModel):
    nombre: str = Field(min_length=2, max_length=40)
    descripcion: str = ""


class RolUpdate(BaseModel):
    nombre: Optional[str] = Field(default=None, min_length=2, max_length=40)
    descripcion: Optional[str] = None


class RolPermisos(BaseModel):
    permisos: list[str] = []


def _error(exc: ValueError) -> HTTPException:
    return HTTPException(status_code=400, detail=str(exc))


@router.get("/usuarios", summary="Listado de usuarios del panel")
def listar_usuarios(
    q: str = "",
    rol: str = "",
    activo: Optional[bool] = None,
    limit: int = Query(default=100, le=500),
    incluir_clientes: bool = False,
    usuario: dict = Depends(require_perm("mod.gobierno")),
) -> list[dict[str, Any]]:
    with get_connection() as conn:
        return listar_usuarios_staff(
            conn, q=q, rol=rol, activo=activo, limit=limit, incluir_clientes=incluir_clientes
        )


@router.post("/usuarios", status_code=201, summary="Crear usuario del panel")
def crear_usuario(
    body: UsuarioCreate,
    usuario: dict = Depends(require_perm("mod.gobierno")),
) -> dict[str, Any]:
    try:
        with get_connection() as conn:
            return crear_usuario_staff(
                conn,
                email=str(body.email),
                password=body.password,
                rol=body.rol,
                nombre=body.nombre,
                id_region=body.id_region,
                id_usuario_actor=usuario["id_usuario"],
            )
    except ValueError as exc:
        raise _error(exc)


@router.put("/usuarios/{id_usuario}", summary="Editar usuario del panel")
def editar_usuario(
    id_usuario: int,
    body: UsuarioUpdate,
    usuario: dict = Depends(require_perm("mod.gobierno")),
) -> dict[str, Any]:
    try:
        with get_connection() as conn:
            return actualizar_usuario_staff(
                conn,
                id_usuario=id_usuario,
                email=str(body.email) if body.email else None,
                rol=body.rol,
                nombre=body.nombre,
                password=body.password,
                activo=body.activo,
                id_region=body.id_region,
                id_usuario_actor=usuario["id_usuario"],
            )
    except ValueError as exc:
        raise _error(exc)


@router.delete("/usuarios/{id_usuario}", summary="Desactivar usuario del panel")
def eliminar_usuario(
    id_usuario: int,
    usuario: dict = Depends(require_perm("mod.gobierno")),
) -> dict[str, Any]:
    try:
        with get_connection() as conn:
            return desactivar_usuario_staff(
                conn, id_usuario=id_usuario, id_usuario_actor=usuario["id_usuario"]
            )
    except ValueError as exc:
        raise _error(exc)


@router.get("/permisos", summary="Catálogo de permisos por módulo")
def permisos() -> list[dict[str, Any]]:
    with get_connection() as conn:
        return listar_permisos(conn)


@router.get("/roles", summary="Roles con sus permisos asignados")
def roles() -> list[dict[str, Any]]:
    with get_connection() as conn:
        return listar_roles_detalle(conn)


@router.post("/roles", status_code=201, summary="Crear rol personalizado")
def crear_rol_endpoint(
    body: RolCreate,
    usuario: dict = Depends(require_perm("mod.gobierno")),
) -> dict[str, Any]:
    try:
        with get_connection() as conn:
            return crear_rol(
                conn,
                nombre=body.nombre,
                descripcion=body.descripcion,
                id_usuario_actor=usuario["id_usuario"],
            )
    except ValueError as exc:
        raise _error(exc)


@router.put("/roles/{id_rol}", summary="Actualizar rol")
def editar_rol_endpoint(
    id_rol: int,
    body: RolUpdate,
    usuario: dict = Depends(require_perm("mod.gobierno")),
) -> dict[str, Any]:
    try:
        with get_connection() as conn:
            return actualizar_rol(
                conn,
                id_rol=id_rol,
                nombre=body.nombre,
                descripcion=body.descripcion,
                id_usuario_actor=usuario["id_usuario"],
            )
    except ValueError as exc:
        raise _error(exc)


@router.delete("/roles/{id_rol}", summary="Eliminar rol (si no tiene usuarios)")
def eliminar_rol_endpoint(
    id_rol: int,
    usuario: dict = Depends(require_perm("mod.gobierno")),
) -> dict[str, Any]:
    try:
        with get_connection() as conn:
            return eliminar_rol(
                conn, id_rol=id_rol, id_usuario_actor=usuario["id_usuario"]
            )
    except ValueError as exc:
        raise _error(exc)


@router.put("/roles/{id_rol}/permisos", summary="Asignar permisos a un rol")
def asignar_permisos_endpoint(
    id_rol: int,
    body: RolPermisos,
    usuario: dict = Depends(require_perm("mod.gobierno")),
) -> dict[str, Any]:
    try:
        with get_connection() as conn:
            return asignar_permisos_rol(
                conn,
                id_rol=id_rol,
                codigos=body.permisos,
                id_usuario_actor=usuario["id_usuario"],
            )
    except ValueError as exc:
        raise _error(exc)