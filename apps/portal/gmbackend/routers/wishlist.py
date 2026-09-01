"""routers/wishlist.py — Favoritos del portal B2B."""
from __future__ import annotations

from typing import Any

import duckdb
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from gmbackend.database import get_db
from gmbackend.routers.auth import get_current_user
from gmbackend.services import wishlist_service

router = APIRouter(prefix="/api/wishlist", tags=["wishlist"])


class WishlistAdd(BaseModel):
    id_producto: int = Field(gt=0)


class WishlistPaqueteAdd(BaseModel):
    id_catalogo: int = Field(gt=0)


def _id_usuario(current: dict) -> int:
    return int(current["usuario"]["id_usuario"])


def _id_cliente(current: dict) -> int | None:
    cliente = current.get("cliente")
    if not cliente:
        return None
    try:
        return int(cliente["id_cliente"])
    except (KeyError, TypeError, ValueError):
        return None


@router.get("", summary="Listar favoritos")
def listar(
    current: dict = Depends(get_current_user),
    conn: duckdb.DuckDBPyConnection = Depends(get_db),
) -> list[dict[str, Any]]:
    return wishlist_service.listar(conn, id_usuario=_id_usuario(current), autenticado=True)


@router.get("/catalogos", summary="Listar paquetes favoritos")
def listar_paquetes(
    current: dict = Depends(get_current_user),
    conn: duckdb.DuckDBPyConnection = Depends(get_db),
) -> list[dict[str, Any]]:
    return wishlist_service.listar_paquetes(
        conn, id_usuario=_id_usuario(current), id_cliente=_id_cliente(current)
    )


@router.get("/catalogos/ids", summary="IDs de paquetes favoritos")
def ids_paquetes(
    current: dict = Depends(get_current_user),
    conn: duckdb.DuckDBPyConnection = Depends(get_db),
) -> list[int]:
    return wishlist_service.ids_paquetes(conn, id_usuario=_id_usuario(current))


@router.post("/catalogos", status_code=201, summary="Agregar paquete a favoritos")
def agregar_paquete(
    body: WishlistPaqueteAdd,
    current: dict = Depends(get_current_user),
    conn: duckdb.DuckDBPyConnection = Depends(get_db),
) -> dict[str, Any]:
    try:
        return wishlist_service.agregar_paquete(
            conn, id_usuario=_id_usuario(current), id_catalogo=body.id_catalogo
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


@router.delete("/catalogos/{id_catalogo}", summary="Quitar paquete de favoritos")
def quitar_paquete(
    id_catalogo: int,
    current: dict = Depends(get_current_user),
    conn: duckdb.DuckDBPyConnection = Depends(get_db),
) -> dict[str, Any]:
    return wishlist_service.quitar_paquete(
        conn, id_usuario=_id_usuario(current), id_catalogo=id_catalogo
    )


@router.post("", status_code=201, summary="Agregar a favoritos")
def agregar(
    body: WishlistAdd,
    current: dict = Depends(get_current_user),
    conn: duckdb.DuckDBPyConnection = Depends(get_db),
) -> dict[str, Any]:
    try:
        return wishlist_service.agregar(conn, id_usuario=_id_usuario(current), id_producto=body.id_producto)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


@router.delete("/{id_producto}", summary="Quitar de favoritos")
def quitar(
    id_producto: int,
    current: dict = Depends(get_current_user),
    conn: duckdb.DuckDBPyConnection = Depends(get_db),
) -> dict[str, Any]:
    return wishlist_service.quitar(conn, id_usuario=_id_usuario(current), id_producto=id_producto)
