"""
routers/auth.py — Login del panel admin, sesión actual, roles y auditoría.
"""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr, Field

from backend.database import get_connection
from backend.middleware.authz import get_current_staff, require_admin
from backend.services.auditoria_service import listar_auditoria, registrar_auditoria
from backend.services.auth_service import autenticar_staff, crear_access_token, listar_roles

router = APIRouter()


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    email: str
    rol: str


@router.post("/login", response_model=LoginResponse, summary="Login del panel administrativo")
def login(body: LoginRequest) -> dict[str, Any]:
    with get_connection() as conn:
        usuario = autenticar_staff(conn, email=str(body.email).lower(), password=body.password)
        if not usuario:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Credenciales inválidas o usuario sin acceso al panel.",
            )
        registrar_auditoria(
            conn,
            id_usuario=usuario["id_usuario"],
            entidad="sesion",
            entidad_id=usuario["id_usuario"],
            accion="login",
            valor_nuevo={"email": usuario["email"], "rol": usuario["rol"]},
        )
    token = crear_access_token(id_usuario=usuario["id_usuario"], rol=usuario["rol"])
    return {
        "access_token": token,
        "token_type": "bearer",
        "email": usuario["email"],
        "rol": usuario["rol"],
    }


@router.get("/me", summary="Usuario staff actual")
def me(usuario: dict = Depends(get_current_staff)) -> dict[str, Any]:
    return usuario


@router.get("/roles", summary="Roles del sistema")
def roles(_: dict = Depends(require_admin)) -> list[dict[str, Any]]:
    with get_connection() as conn:
        return listar_roles(conn)


@router.get("/auditoria", summary="Registro de auditoría")
def auditoria(
    entidad: Optional[str] = None,
    limit: int = 100,
    _: dict = Depends(require_admin),
) -> list[dict[str, Any]]:
    with get_connection() as conn:
        return listar_auditoria(conn, entidad=entidad, limit=limit)
