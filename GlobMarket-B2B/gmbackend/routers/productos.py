from __future__ import annotations

from typing import Optional

import duckdb
from fastapi import APIRouter, Depends, HTTPException, Query, status

from gmbackend.database import get_db
from gmbackend.models.schemas import CategoriaResponse, ProductoResponse, ProductosListResponse
from gmbackend.services.producto_service import listar_categorias, listar_productos, obtener_producto

router = APIRouter(prefix="/api/productos", tags=["productos"])


@router.get("/categorias", response_model=list[CategoriaResponse], summary="Listar categorías (12)")
def categorias(conn: duckdb.DuckDBPyConnection = Depends(get_db)) -> list[dict]:
    return listar_categorias(conn)


@router.get("", response_model=ProductosListResponse, summary="Listar productos con filtros")
def productos(
    conn: duckdb.DuckDBPyConnection = Depends(get_db),
    id_item_type: Optional[int] = Query(default=None, description="Filtrar por categoría (id_item_type)"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=12, ge=1, le=48),
) -> dict:
    return listar_productos(conn, id_item_type=id_item_type, page=page, page_size=page_size)


@router.get("/{id_producto}", response_model=ProductoResponse, summary="Detalle de un producto")
def producto_detalle(
    id_producto: int,
    conn: duckdb.DuckDBPyConnection = Depends(get_db),
) -> dict:
    prod = obtener_producto(conn, id_producto=id_producto)
    if not prod:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Producto no encontrado.")
    return prod

