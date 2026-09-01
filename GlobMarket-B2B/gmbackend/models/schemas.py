from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, EmailStr, Field, HttpUrl, StringConstraints
from typing_extensions import Annotated


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

Contrasena = Annotated[str, StringConstraints(min_length=8, max_length=72)]


class RegistroRequest(BaseModel):
    nombre_empresa: Annotated[str, StringConstraints(min_length=2, max_length=120)]
    email: EmailStr
    password: Contrasena
    pais: Annotated[str, StringConstraints(min_length=2, max_length=80)]
    telefono: Optional[Annotated[str, StringConstraints(min_length=6, max_length=30)]] = None
    direccion: Optional[Annotated[str, StringConstraints(min_length=5, max_length=200)]] = None


class LoginRequest(BaseModel):
    email: EmailStr
    password: Contrasena


class TokenResponse(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in_minutes: int


class UsuarioResponse(BaseModel):
    id_usuario: int
    email: EmailStr
    rol: Literal["cliente", "admin"]
    activo: bool
    fecha_registro: datetime


class ClienteResponse(BaseModel):
    id_cliente: int
    id_usuario: int
    nombre_empresa: str
    pais: str
    telefono: Optional[str] = None
    direccion: Optional[str] = None


class MeResponse(BaseModel):
    usuario: UsuarioResponse
    cliente: Optional[ClienteResponse] = None


# ---------------------------------------------------------------------------
# Productos
# ---------------------------------------------------------------------------

class CategoriaResponse(BaseModel):
    id_item_type: int
    item_type: str


class ProductoResponse(BaseModel):
    id_producto: int
    nombre_producto: str
    descripcion: Optional[str] = None
    id_item_type: int
    categoria: str
    precio_unitario: float = Field(ge=0)
    precio_mayorista: float = Field(ge=0)
    imagen_url: Optional[HttpUrl] = None
    activo: bool


class ProductosListResponse(BaseModel):
    items: list[ProductoResponse]
    page: int
    page_size: int
    total_items: int
    total_pages: int

