from __future__ import annotations

from typing import Optional

import duckdb
from fastapi import APIRouter, Depends, HTTPException, Query, status

from gmbackend.database import get_db
from gmbackend.models.schemas import CategoriaResponse, ProductoResponse, ProductosListResponse
from gmbackend.routers.auth import get_current_user_optional
from gmbackend.services.producto_service import listar_categorias, listar_lineas, listar_marcas, listar_productos, obtener_producto

router = APIRouter(prefix="/api/productos", tags=["productos"])


def _id_cliente(current: Optional[dict]) -> Optional[int]:
    """id_cliente de la sesión, si la cuenta tiene ficha B2B.

    Determina la macro-zona de entrega y con ella el stock que se muestra.
    """
    if not current:
        return None
    cliente = current.get("cliente")
    if not cliente:
        return None
    try:
        return int(cliente["id_cliente"])
    except (KeyError, TypeError, ValueError):
        return None


@router.get("/categorias", response_model=list[CategoriaResponse], summary="Listar categorías (12)")
def categorias(conn: duckdb.DuckDBPyConnection = Depends(get_db)) -> list[dict]:
    return listar_categorias(conn)


@router.get("/marcas", summary="Listar marcas activas")
def marcas(conn: duckdb.DuckDBPyConnection = Depends(get_db)) -> list[dict]:
    return listar_marcas(conn)


@router.get("/lineas", summary="Listar líneas de producto")
def lineas(
    conn: duckdb.DuckDBPyConnection = Depends(get_db),
    id_marca: Optional[int] = Query(default=None),
) -> list[dict]:
    return listar_lineas(conn, id_marca=id_marca)


@router.get("", response_model=ProductosListResponse, summary="Listar productos con filtros")
def productos(
    conn: duckdb.DuckDBPyConnection = Depends(get_db),
    id_item_type: Optional[int] = Query(default=None, description="Filtrar por categoría (id_item_type)"),
    id_marca: Optional[int] = Query(default=None),
    id_linea: Optional[int] = Query(default=None),
    precio_min: Optional[float] = Query(default=None, ge=0),
    precio_max: Optional[float] = Query(default=None, ge=0),
    orden: Optional[str] = Query(default=None, description="precio_asc|precio_desc|nombre"),
    q: Optional[str] = Query(default=None, description="Buscar por nombre o descripción"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=12, ge=1, le=48),
    current: Optional[dict] = Depends(get_current_user_optional),
) -> dict:
    return listar_productos(
        conn,
        id_item_type=id_item_type,
        id_marca=id_marca,
        id_linea=id_linea,
        precio_min=precio_min,
        precio_max=precio_max,
        orden=orden,
        page=page,
        page_size=page_size,
        q=q,
        autenticado=current is not None,
        id_cliente=_id_cliente(current),
    )


@router.get("/{id_producto}", response_model=ProductoResponse, summary="Detalle de un producto")
def producto_detalle(
    id_producto: int,
    conn: duckdb.DuckDBPyConnection = Depends(get_db),
    current: Optional[dict] = Depends(get_current_user_optional),
) -> dict:
    prod = obtener_producto(conn, id_producto=id_producto, id_cliente=_id_cliente(current))
    if not prod:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Producto no encontrado.")
    return prod

