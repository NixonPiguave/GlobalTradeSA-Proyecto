"""Router cuenta B2B — perfil ampliado, direcciones, contactos, seguridad."""

from __future__ import annotations

from typing import Optional

import duckdb
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr, StringConstraints, field_validator
from typing_extensions import Annotated

from gmbackend.models.validators import validar_telefono_e164

from gmbackend.database import get_db
from gmbackend.models.schemas import MeResponse, PerfilUpdateRequest
from gmbackend.routers.auth import get_current_user
from gmbackend.services import cuenta_service
from gmbackend.services.auth_service import actualizar_perfil_cliente

router = APIRouter(prefix="/api/cuenta", tags=["cuenta-b2b"])


class PasswordChangeRequest(BaseModel):
    password_actual: Annotated[str, StringConstraints(min_length=8, max_length=72)]
    password_nueva: Annotated[str, StringConstraints(min_length=8, max_length=72)]


class DireccionCreate(BaseModel):
    alias: Annotated[str, StringConstraints(min_length=1, max_length=80)] = "Dirección"
    direccion: Annotated[str, StringConstraints(min_length=5, max_length=300)]
    ciudad: Optional[Annotated[str, StringConstraints(max_length=100)]] = None
    pais: Annotated[str, StringConstraints(min_length=2, max_length=80)]
    tipo: Annotated[str, StringConstraints(pattern="^(envio|facturacion|ambos)$")] = "envio"
    es_principal: bool = False


class DireccionUpdate(BaseModel):
    alias: Optional[Annotated[str, StringConstraints(min_length=1, max_length=80)]] = None
    direccion: Optional[Annotated[str, StringConstraints(min_length=5, max_length=300)]] = None
    ciudad: Optional[Annotated[str, StringConstraints(max_length=100)]] = None
    pais: Optional[Annotated[str, StringConstraints(min_length=2, max_length=80)]] = None
    tipo: Optional[Annotated[str, StringConstraints(pattern="^(envio|facturacion|ambos)$")]] = None
    es_principal: Optional[bool] = None


class ContactoCreate(BaseModel):
    nombre: Annotated[str, StringConstraints(min_length=2, max_length=120)]
    cargo: Optional[Annotated[str, StringConstraints(max_length=80)]] = None
    email: Optional[EmailStr] = None
    telefono: Optional[str] = None

    @field_validator("telefono")
    @classmethod
    def _validar_tel_contacto(cls, v: Optional[str]) -> Optional[str]:
        return validar_telefono_e164(v)


class ContactoUpdate(BaseModel):
    nombre: Optional[Annotated[str, StringConstraints(min_length=2, max_length=120)]] = None
    cargo: Optional[Annotated[str, StringConstraints(max_length=80)]] = None
    email: Optional[EmailStr] = None
    telefono: Optional[str] = None

    @field_validator("telefono")
    @classmethod
    def _validar_tel_contacto_upd(cls, v: Optional[str]) -> Optional[str]:
        return validar_telefono_e164(v)


class PreferenciasUpdate(BaseModel):
    notif_pedidos: Optional[bool] = None
    notif_promociones: Optional[bool] = None
    notif_stock: Optional[bool] = None
    moneda_preferida: Optional[Annotated[str, StringConstraints(pattern="^(USD|EUR|PEN|MXN)$")]] = None


def _uid(current: dict) -> int:
    return int(current["usuario"]["id_usuario"])


@router.get("/resumen", summary="Resumen completo de la cuenta B2B")
def resumen(current: dict = Depends(get_current_user), conn: duckdb.DuckDBPyConnection = Depends(get_db)) -> dict:
    try:
        return cuenta_service.resumen_cuenta(conn, _uid(current))
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.put("/perfil", response_model=MeResponse, summary="Actualizar ficha empresa")
def actualizar_perfil(
    body: PerfilUpdateRequest,
    current: dict = Depends(get_current_user),
    conn: duckdb.DuckDBPyConnection = Depends(get_db),
) -> dict:
    try:
        return actualizar_perfil_cliente(
            conn,
            id_usuario=_uid(current),
            pais=str(body.pais),
            telefono=body.telefono,
            direccion=body.direccion,
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


@router.post("/password", summary="Cambiar contraseña")
def password(
    body: PasswordChangeRequest,
    current: dict = Depends(get_current_user),
    conn: duckdb.DuckDBPyConnection = Depends(get_db),
) -> dict[str, str]:
    try:
        cuenta_service.cambiar_password(
            conn,
            id_usuario=_uid(current),
            password_actual=body.password_actual,
            password_nueva=body.password_nueva,
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    return {"mensaje": "Contraseña actualizada."}


@router.get("/direcciones")
def get_direcciones(current: dict = Depends(get_current_user), conn: duckdb.DuckDBPyConnection = Depends(get_db)):
    return {"items": cuenta_service.listar_direcciones(conn, _uid(current))}


@router.post("/direcciones", status_code=201)
def post_direccion(
    body: DireccionCreate,
    current: dict = Depends(get_current_user),
    conn: duckdb.DuckDBPyConnection = Depends(get_db),
):
    try:
        return cuenta_service.crear_direccion(
            conn,
            id_usuario=_uid(current),
            alias=body.alias,
            direccion=body.direccion,
            ciudad=body.ciudad,
            pais=body.pais,
            tipo=body.tipo,
            es_principal=body.es_principal,
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


@router.put("/direcciones/{id_direccion}")
def put_direccion(
    id_direccion: int,
    body: DireccionUpdate,
    current: dict = Depends(get_current_user),
    conn: duckdb.DuckDBPyConnection = Depends(get_db),
):
    try:
        return cuenta_service.actualizar_direccion(
            conn,
            id_usuario=_uid(current),
            id_direccion=id_direccion,
            **body.model_dump(exclude_unset=True),
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


@router.delete("/direcciones/{id_direccion}")
def del_direccion(
    id_direccion: int,
    current: dict = Depends(get_current_user),
    conn: duckdb.DuckDBPyConnection = Depends(get_db),
):
    try:
        cuenta_service.eliminar_direccion(conn, id_usuario=_uid(current), id_direccion=id_direccion)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return {"ok": True}


@router.get("/contactos")
def get_contactos(current: dict = Depends(get_current_user), conn: duckdb.DuckDBPyConnection = Depends(get_db)):
    return {"items": cuenta_service.listar_contactos(conn, _uid(current))}


@router.post("/contactos", status_code=201)
def post_contacto(
    body: ContactoCreate,
    current: dict = Depends(get_current_user),
    conn: duckdb.DuckDBPyConnection = Depends(get_db),
):
    try:
        return cuenta_service.crear_contacto(
            conn,
            id_usuario=_uid(current),
            nombre=body.nombre,
            cargo=body.cargo,
            email=str(body.email) if body.email else None,
            telefono=body.telefono,
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


@router.put("/contactos/{id_contacto}")
def put_contacto(
    id_contacto: int,
    body: ContactoUpdate,
    current: dict = Depends(get_current_user),
    conn: duckdb.DuckDBPyConnection = Depends(get_db),
):
    data = body.model_dump(exclude_unset=True)
    if "email" in data and data["email"] is not None:
        data["email"] = str(data["email"])
    try:
        return cuenta_service.actualizar_contacto(
            conn,
            id_usuario=_uid(current),
            id_contacto=id_contacto,
            **data,
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


@router.delete("/contactos/{id_contacto}")
def del_contacto(
    id_contacto: int,
    current: dict = Depends(get_current_user),
    conn: duckdb.DuckDBPyConnection = Depends(get_db),
):
    try:
        cuenta_service.eliminar_contacto(conn, id_usuario=_uid(current), id_contacto=id_contacto)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return {"ok": True}


@router.get("/preferencias")
def get_prefs(current: dict = Depends(get_current_user), conn: duckdb.DuckDBPyConnection = Depends(get_db)):
    return cuenta_service.obtener_preferencias(conn, _uid(current))


@router.get("/envio-estimado")
def envio_estimado(
    pais: Optional[str] = None,
    current: dict = Depends(get_current_user),
    conn: duckdb.DuckDBPyConnection = Depends(get_db),
):
    """Zona logística / transportistas según país de entrega (perfil o query)."""
    try:
        return cuenta_service.estimar_envio_cliente(conn, id_usuario=_uid(current), pais=pais)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


@router.put("/preferencias")
def put_prefs(
    body: PreferenciasUpdate,
    current: dict = Depends(get_current_user),
    conn: duckdb.DuckDBPyConnection = Depends(get_db),
):
    try:
        return cuenta_service.guardar_preferencias(
            conn,
            id_usuario=_uid(current),
            preferencias=body.model_dump(exclude_unset=True),
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


@router.get("/notificaciones")
def get_notifs(current: dict = Depends(get_current_user), conn: duckdb.DuckDBPyConnection = Depends(get_db)):
    from shared.services import notificacion_service as ns
    uid = _uid(current)
    prefs = cuenta_service.obtener_preferencias(conn, uid)
    items = ns.listar(conn, id_usuario=uid, limit=30)
    # Filtrar por preferencias del cliente
    filtrados = []
    for it in items:
        tipo = (it.get("tipo") or "").lower()
        if tipo == "pedido" and not prefs.get("notif_pedidos", True):
            continue
        if tipo in ("promo", "promocion", "marketing") and not prefs.get("notif_promociones", True):
            continue
        if tipo == "stock" and not prefs.get("notif_stock", False):
            continue
        filtrados.append(it)
    return {"items": filtrados, "no_leidas": sum(1 for i in filtrados if not i.get("leida"))}


@router.post("/notificaciones/leer-todas")
def leer_notifs(current: dict = Depends(get_current_user), conn: duckdb.DuckDBPyConnection = Depends(get_db)):
    from shared.services import notificacion_service as ns
    n = ns.marcar_todas(conn, id_usuario=_uid(current))
    return {"ok": True, "marcadas": n}


@router.post("/notificaciones/{id_notif}/leida")
def leer_notif(
    id_notif: int,
    current: dict = Depends(get_current_user),
    conn: duckdb.DuckDBPyConnection = Depends(get_db),
):
    from shared.services import notificacion_service as ns
    ok = ns.marcar_leida(conn, id_usuario=_uid(current), id_notif=id_notif)
    if not ok:
        raise HTTPException(status_code=404, detail="Notificación no encontrada.")
    return {"ok": True}
