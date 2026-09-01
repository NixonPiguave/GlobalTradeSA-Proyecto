"""
models/ventas.py — Esquemas Pydantic del flujo carrito → checkout → pedido (portal).
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class CarritoItemAdd(BaseModel):
    id_producto: int = Field(gt=0)
    cantidad: int = Field(gt=0, le=100_000)


class CarritoItemUpdate(BaseModel):
    cantidad: int = Field(ge=0, le=100_000)  # 0 elimina el item


class CheckoutRequest(BaseModel):
    direccion_entrega: str = Field(min_length=5, max_length=300)
    ciudad: Optional[str] = Field(default=None, max_length=100)
    pais: str = Field(min_length=2, max_length=80)
    notas: Optional[str] = Field(default=None, max_length=500)


class PagoSimuladoRequest(BaseModel):
    id_pedido: int = Field(gt=0)
    metodo: str = Field(default="tarjeta", max_length=40)
    referencia: Optional[str] = Field(default=None, max_length=80)
    ultimos_digitos: Optional[str] = Field(default=None, max_length=4)


class PaqueteItemAdd(BaseModel):
    id_producto: int = Field(gt=0)
    cantidad: int = Field(ge=0, le=100_000)  # 0 significa "no lleva ese producto"


class PaqueteAgregar(BaseModel):
    id_catalogo: int = Field(gt=0)
    items: list[PaqueteItemAdd] = Field(min_length=1, max_length=200)
