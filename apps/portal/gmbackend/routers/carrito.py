"""
routers/carrito.py — Carrito del portal B2B (requiere sesión de cliente).
"""

from __future__ import annotations

from typing import Any

import duckdb
from fastapi import APIRouter, Depends, HTTPException

from gmbackend.database import get_db
from gmbackend.models.ventas import CarritoItemAdd, CarritoItemUpdate, PaqueteAgregar
from gmbackend.routers.auth import get_current_user
from gmbackend.services import carrito_service

router = APIRouter(prefix="/api/carrito", tags=["carrito"])


def _id_cliente(current: dict) -> int:
    cliente = current.get("cliente")
    if not cliente:
        raise HTTPException(status_code=403, detail="La cuenta no tiene ficha de cliente B2B.")
    return int(cliente["id_cliente"])


@router.get("", summary="Ver carrito activo")
def ver_carrito(
    current: dict = Depends(get_current_user),
    conn: duckdb.DuckDBPyConnection = Depends(get_db),
) -> dict[str, Any]:
    return carrito_service.ver_carrito(conn, _id_cliente(current))


@router.post("/items", summary="Agregar producto al carrito")
def agregar_item(
    body: CarritoItemAdd,
    current: dict = Depends(get_current_user),
    conn: duckdb.DuckDBPyConnection = Depends(get_db),
) -> dict[str, Any]:
    try:
        return carrito_service.agregar_item(
            conn,
            id_cliente=_id_cliente(current),
            id_producto=body.id_producto,
            cantidad=body.cantidad,
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


@router.put("/items/{id_item}", summary="Actualizar cantidad (0 elimina)")
def actualizar_item(
    id_item: int,
    body: CarritoItemUpdate,
    current: dict = Depends(get_current_user),
    conn: duckdb.DuckDBPyConnection = Depends(get_db),
) -> dict[str, Any]:
    try:
        return carrito_service.actualizar_item(
            conn,
            id_cliente=_id_cliente(current),
            id_item=id_item,
            cantidad=body.cantidad,
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


@router.post("/paquete", summary="Agregar catálogo configurado al carrito")
def agregar_paquete(
    body: PaqueteAgregar,
    current: dict = Depends(get_current_user),
    conn: duckdb.DuckDBPyConnection = Depends(get_db),
) -> dict[str, Any]:
    try:
        return carrito_service.agregar_paquete(
            conn,
            id_cliente=_id_cliente(current),
            id_catalogo=body.id_catalogo,
            items=[{"id_producto": i.id_producto, "cantidad": i.cantidad} for i in body.items],
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


@router.delete("", summary="Vaciar carrito")
def vaciar(
    current: dict = Depends(get_current_user),
    conn: duckdb.DuckDBPyConnection = Depends(get_db),
) -> dict[str, Any]:
    return carrito_service.vaciar_carrito(conn, _id_cliente(current))
