from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, EmailStr, Field, StringConstraints, field_validator
from typing_extensions import Annotated

from gmbackend.models.validators import validar_telefono_e164


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

Contrasena = Annotated[str, StringConstraints(min_length=8, max_length=72)]


class RegistroRequest(BaseModel):
    nombre_empresa: Annotated[str, StringConstraints(min_length=2, max_length=120)]
    email: EmailStr
    password: Contrasena
    pais: Annotated[str, StringConstraints(min_length=2, max_length=80)]
    telefono: Optional[str] = None
    direccion: Optional[Annotated[str, StringConstraints(min_length=5, max_length=200)]] = None

    @field_validator("telefono")
    @classmethod
    def _validar_tel_registro(cls, v: Optional[str]) -> Optional[str]:
        return validar_telefono_e164(v)


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
    rol: Literal["cliente", "admin", "vendedor", "almacen"]
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


class PerfilUpdateRequest(BaseModel):
    pais: Annotated[str, StringConstraints(min_length=2, max_length=80)]
    telefono: Optional[str] = None
    direccion: Optional[Annotated[str, StringConstraints(min_length=5, max_length=200)]] = None

    @field_validator("telefono")
    @classmethod
    def _validar_tel_perfil(cls, v: Optional[str]) -> Optional[str]:
        return validar_telefono_e164(v)


# ---------------------------------------------------------------------------
# Productos
# ---------------------------------------------------------------------------

class CategoriaResponse(BaseModel):
    id_item_type: int
    item_type: str


class ProductoResponse(BaseModel):
    id_producto: int
    sku: Optional[str] = None
    nombre_producto: str
    descripcion: Optional[str] = None
    id_item_type: int
    categoria: str
    precio_unitario: float = Field(ge=0)
    precio_mayorista: Optional[float] = Field(default=None, ge=0)
    ahorro_pct: float = Field(default=0.0, ge=0)
    imagen_url: Optional[str] = None
    activo: bool
    stock_disponible: Optional[float] = None
    stock_minimo: Optional[float] = None
    estado_stock: Optional[str] = None
    moq: Optional[int] = None
    marca: Optional[str] = None
    linea: Optional[str] = None
    descuento_pct: float = Field(default=0.0, ge=0)
    descuento_aplica_a: Optional[str] = None
    descuento_origen: Optional[str] = None
    descuento_etiqueta: Optional[str] = None
    precio_rebajado: Optional[float] = None
    precio_login_hint: Optional[bool] = None
    zona_entrega: Optional[str] = None
    zona_label: Optional[str] = None
    bodega_asignada: Optional[str] = None
    zona_resuelta: Optional[bool] = None
    lista_precio: Optional[str] = None


class ProductosListResponse(BaseModel):
    items: list[ProductoResponse]
    page: int
    page_size: int
    total_items: int
    total_pages: int
    zona_entrega: Optional[str] = None
    zona_label: Optional[str] = None
    bodega_asignada: Optional[str] = None
    zona_resuelta: Optional[bool] = None

