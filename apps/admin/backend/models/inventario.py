"""
models/inventario.py — Esquemas Pydantic de compras e inventario.
"""

from __future__ import annotations

import re
from typing import Optional

from pydantic import BaseModel, Field, model_validator, field_validator

_RUC_RE = re.compile(r"^\d{8,13}$")


def _norm_ruc(v: Optional[str]) -> Optional[str]:
    if v is None:
        return None
    s = str(v).strip().replace(" ", "").replace("-", "")
    if not s:
        return None
    if not _RUC_RE.match(s):
        raise ValueError("RUC inválido: use solo dígitos (8 a 13 caracteres).")
    return s


class ProveedorCreate(BaseModel):
    razon_social: str = Field(min_length=2, max_length=160)
    ruc: Optional[str] = Field(default=None, max_length=13)
    id_country: Optional[int] = None

    @field_validator("razon_social")
    @classmethod
    def _razon(cls, v: str) -> str:
        s = " ".join(str(v or "").split())
        if len(s) < 2 or len(s) > 160:
            raise ValueError("Razón social: entre 2 y 160 caracteres.")
        return s

    @field_validator("ruc")
    @classmethod
    def _ruc(cls, v: Optional[str]) -> Optional[str]:
        return _norm_ruc(v)


class ProveedorUpdate(BaseModel):
    razon_social: Optional[str] = Field(default=None, min_length=2, max_length=160)
    ruc: Optional[str] = Field(default=None, max_length=13)
    id_country: Optional[int] = None
    activo: Optional[bool] = None

    @field_validator("razon_social")
    @classmethod
    def _razon(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        s = " ".join(str(v).split())
        if len(s) < 2 or len(s) > 160:
            raise ValueError("Razón social: entre 2 y 160 caracteres.")
        return s

    @field_validator("ruc")
    @classmethod
    def _ruc(cls, v: Optional[str]) -> Optional[str]:
        return _norm_ruc(v)


class OCDetalleItem(BaseModel):
    id_producto: int = Field(gt=0)
    cantidad: float = Field(gt=0)
    costo_unitario: float = Field(gt=0)


class OrdenCompraCreate(BaseModel):
    id_proveedor: int = Field(gt=0)
    items: list[OCDetalleItem] = Field(min_length=1)
    metodo_pago: Optional[str] = Field(default="caja", pattern="^(caja|externo|credito)$")


class RecepcionItemCreate(BaseModel):
    id_detalle: int = Field(gt=0)
    cantidad: float = Field(ge=0)
    observacion: Optional[str] = Field(default=None, max_length=200)


class RecepcionCreate(BaseModel):
    id_almacen: int = Field(default=1, gt=0)
    recibos: Optional[list[RecepcionItemCreate]] = None


class AjusteStock(BaseModel):
    id_producto: int = Field(gt=0)
    id_almacen: int = Field(default=1, gt=0)
    cantidad: float = Field(description="Cantidad del ajuste (negativa = salida, positiva = entrada)")
    motivo: str = Field(min_length=3, max_length=200)

    @model_validator(mode="after")
    def cantidad_distinta_cero(self) -> "AjusteStock":
        if self.cantidad == 0:
            raise ValueError("La cantidad del ajuste debe ser distinta de cero.")
        return self


class AlertaStockCreate(BaseModel):
    id_producto: int = Field(gt=0)
    id_almacen: int = Field(default=1, gt=0)
    umbral_minimo: float = Field(ge=0)


class TransferenciaStock(BaseModel):
    id_producto: int = Field(gt=0)
    id_almacen_origen: int = Field(gt=0)
    id_almacen_destino: int = Field(gt=0)
    cantidad: float = Field(gt=0, le=1_000_000)

    @model_validator(mode="after")
    def origen_distinto_destino(self) -> "TransferenciaStock":
        if self.id_almacen_origen == self.id_almacen_destino:
            raise ValueError("El almacén de origen y destino deben ser distintos.")
        return self
