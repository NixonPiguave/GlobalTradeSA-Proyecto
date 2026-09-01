"""
models/catalogo.py — Esquemas Pydantic del catálogo administrable.
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class CategoriaCreate(BaseModel):
    nombre: str = Field(min_length=2, max_length=80)
    descripcion: Optional[str] = Field(default=None, max_length=300)
    imagen_path: Optional[str] = None


class CategoriaUpdate(BaseModel):
    nombre: Optional[str] = Field(default=None, min_length=2, max_length=80)
    descripcion: Optional[str] = Field(default=None, max_length=300)
    imagen_path: Optional[str] = None
    activo: Optional[bool] = None
    descuento_pct: Optional[float] = Field(default=None, ge=0, le=90)
    descuento_aplica_a: Optional[str] = Field(default=None, pattern="^(mayorista|retail|ambos)$")
    descuento_hasta: Optional[str] = None
    descuento_motivo: Optional[str] = Field(default=None, max_length=200)
    avisar_clientes: bool = True


class ProductoCreate(BaseModel):
    nombre_producto: str = Field(min_length=2, max_length=160)
    descripcion: Optional[str] = Field(default=None, max_length=1000)
    id_item_type: int = Field(gt=0)
    id_marca: Optional[int] = Field(default=None, gt=0)
    id_linea: Optional[int] = Field(default=None, gt=0)
    sku: Optional[str] = Field(default=None, max_length=40)
    precio_unitario: float = Field(gt=0, le=1_000_000)
    precio_mayorista: float = Field(gt=0, le=1_000_000)
    descuento_pct: float = Field(default=0, ge=0, le=100)
    precio_rebajado: Optional[float] = Field(default=None, gt=0, le=1_000_000)
    descuento_aplica_a: str = Field(default="mayorista", pattern="^(mayorista|retail|ambos)$")
    fecha_rebaja_hasta: Optional[str] = None
    descuento_motivo: Optional[str] = Field(default=None, max_length=200)
    avisar_clientes: bool = True
    imagen_url: Optional[str] = None
    stock_inicial: float = Field(default=0, ge=0, description="Ignorado: el stock siempre inicia en 0")
    stock_minimo: float = Field(default=10, ge=0, le=1_000_000, description="Umbral «poco stock» en portal B2B")


class ProductoUpdate(BaseModel):
    nombre_producto: Optional[str] = Field(default=None, min_length=2, max_length=160)
    descripcion: Optional[str] = Field(default=None, max_length=1000)
    id_item_type: Optional[int] = Field(default=None, gt=0)
    id_marca: Optional[int] = Field(default=None, gt=0)
    id_linea: Optional[int] = Field(default=None, gt=0)
    sku: Optional[str] = Field(default=None, max_length=40)
    precio_unitario: Optional[float] = Field(default=None, gt=0, le=1_000_000)
    precio_mayorista: Optional[float] = Field(default=None, gt=0, le=1_000_000)
    descuento_pct: Optional[float] = Field(default=None, ge=0, le=100)
    precio_rebajado: Optional[float] = Field(default=None, gt=0, le=1_000_000)
    descuento_aplica_a: Optional[str] = Field(default=None, pattern="^(mayorista|retail|ambos)$")
    fecha_rebaja_hasta: Optional[str] = None
    descuento_motivo: Optional[str] = Field(default=None, max_length=200)
    avisar_clientes: bool = True
    imagen_url: Optional[str] = None
    activo: Optional[bool] = None
    stock_minimo: Optional[float] = Field(default=None, ge=0, le=1_000_000)


class PrecioDetalle(BaseModel):
    id_lista: int = Field(gt=0)
    id_producto: int = Field(gt=0)
    precio: float = Field(gt=0, le=1_000_000)
    cantidad_minima: int = Field(default=1, ge=1)


class CatalogoCreate(BaseModel):
    nombre: str = Field(min_length=2, max_length=120)
    descripcion: Optional[str] = Field(default=None, max_length=500)
    id_item_type: Optional[int] = Field(default=None, gt=0)
    activo: bool = True


class CatalogoUpdate(BaseModel):
    nombre: Optional[str] = Field(default=None, min_length=2, max_length=120)
    descripcion: Optional[str] = Field(default=None, max_length=500)
    id_item_type: Optional[int] = Field(default=None, gt=0)
    activo: Optional[bool] = None
    descuento_pct: Optional[float] = Field(default=None, ge=0, le=90)
    descuento_hasta: Optional[str] = None
    descuento_motivo: Optional[str] = Field(default=None, max_length=200)
    avisar_clientes: bool = True


class CatalogoProductoAdd(BaseModel):
    id_producto: int = Field(gt=0)
    cantidad_base: int = Field(default=10, ge=1, le=100_000)
    precio_unitario: Optional[float] = Field(default=None, gt=0, le=1_000_000)


class CatalogoProductoUpdate(BaseModel):
    cantidad_base: Optional[int] = Field(default=None, ge=1, le=100_000)
    precio_unitario: Optional[float] = Field(default=None, gt=0, le=1_000_000)


class MarcaCreate(BaseModel):
    nombre: str = Field(min_length=2, max_length=80)


class MarcaUpdate(BaseModel):
    nombre: Optional[str] = Field(default=None, min_length=2, max_length=80)
    activo: Optional[bool] = None


class LineaCreate(BaseModel):
    nombre: str = Field(min_length=2, max_length=80)
    id_marca: Optional[int] = Field(default=None, gt=0)
    descripcion: Optional[str] = Field(default=None, max_length=200)


class LineaUpdate(BaseModel):
    nombre: Optional[str] = Field(default=None, min_length=2, max_length=80)
    id_marca: Optional[int] = Field(default=None, gt=0)
    descripcion: Optional[str] = Field(default=None, max_length=200)
    activo: Optional[bool] = None
