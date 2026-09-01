from __future__ import annotations

import logging
from typing import Annotated

import duckdb
from fastapi import APIRouter, Depends, Header, HTTPException, status

from gmbackend.config import Settings, get_settings
from gmbackend.database import get_db
from gmbackend.models.schemas import LoginRequest, MeResponse, RegistroRequest, TokenResponse
from gmbackend.services.auth_service import (
    autenticar_usuario,
    crear_access_token,
    decodificar_token,
    obtener_usuario_y_cliente,
    registrar_cliente,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _bearer_token(authorization: str) -> str:
    raw = authorization.strip()
    if not raw.lower().startswith("bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token Bearer requerido.")
    token = raw[7:].strip()
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token vacío.")
    return token


def get_current_user(
    conn: duckdb.DuckDBPyConnection = Depends(get_db),
    settings: Settings = Depends(get_settings),
    authorization: Annotated[str | None, Header()] = None,
) -> dict:
    if not authorization:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Falta header Authorization.")

    token = _bearer_token(authorization)
    try:
        payload = decodificar_token(settings, token)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token inválido o expirado.")

    sub = payload.get("sub")
    if not sub:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token inválido (sub ausente).")

    try:
        id_usuario = int(sub)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token inválido (sub no numérico).")

    data = obtener_usuario_y_cliente(conn, id_usuario=id_usuario)
    if not data or not data.get("usuario"):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Usuario no encontrado.")

    if not data["usuario"]["activo"]:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Usuario inactivo.")

    return data


@router.post(
    "/registro",
    response_model=MeResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Registrar nueva empresa (cliente B2B)",
)
def registro(
    body: RegistroRequest,
    conn: duckdb.DuckDBPyConnection = Depends(get_db),
) -> dict:
    try:
        return registrar_cliente(
            conn,
            email=str(body.email).lower(),
            password=body.password,
            nombre_empresa=body.nombre_empresa,
            pais=body.pais,
            telefono=body.telefono,
            direccion=body.direccion,
        )
    except Exception as e:
        msg = str(e).lower()
        if "unique" in msg and "email" in msg:
            raise HTTPException(status_code=409, detail="Ya existe un usuario con ese email.")
        raise HTTPException(status_code=400, detail="No se pudo registrar el cliente. Verifica los datos.")


@router.post("/login", response_model=TokenResponse, summary="Login con JWT")
def login(
    body: LoginRequest,
    conn: duckdb.DuckDBPyConnection = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict:
    usuario = autenticar_usuario(conn, email=str(body.email).lower(), password=body.password)
    if not usuario:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Credenciales inválidas.")

    token = crear_access_token(
        settings=settings,
        id_usuario=usuario["id_usuario"],
        rol=usuario["rol"],
        expires_minutes=settings.JWT_EXPIRE_MINUTES,
    )

    logger.info("Login exitoso: %s (rol=%s)", usuario["email"], usuario["rol"])
    return {"access_token": token, "expires_in_minutes": settings.JWT_EXPIRE_MINUTES}


@router.get("/me", response_model=MeResponse, summary="Datos del usuario actual")
def me(
    current: dict = Depends(get_current_user),
) -> dict:
    return current

