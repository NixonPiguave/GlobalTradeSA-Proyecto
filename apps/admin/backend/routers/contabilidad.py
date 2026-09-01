"""
routers/contabilidad.py — Asientos contables y resumen financiero (admin).
"""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from backend.database import get_connection
from backend.middleware.authz import require_staff
from backend.services import contabilidad_service

router = APIRouter()


@router.get("/asientos", summary="Listar asientos contables")
def listar_asientos(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    _: dict = Depends(require_staff),
) -> dict[str, Any]:
    with get_connection() as conn:
        return contabilidad_service.listar_asientos(conn, page=page, page_size=page_size)


@router.get("/resumen", summary="Resumen financiero por cuenta")
def resumen(_: dict = Depends(require_staff)) -> dict[str, Any]:
    with get_connection() as conn:
        return contabilidad_service.resumen_financiero(conn)


@router.post("/sincronizar", summary="Generar asientos faltantes de pedidos pagados")
def sincronizar_asientos(_: dict = Depends(require_staff)) -> dict[str, Any]:
    with get_connection() as conn:
        return contabilidad_service.sincronizar_asientos_pedidos_pagados(conn)


@router.post("/regularizar-caja", summary="Ajustar saldo de Caja (1101) a un objetivo")
def regularizar_caja(
    saldo_objetivo: float = Query(0.0, description="Saldo deseado de caja (default 0)"),
    nota: str = Query("", max_length=200),
    _: dict = Depends(require_staff),
) -> dict[str, Any]:
    with get_connection() as conn:
        try:
            return contabilidad_service.regularizar_caja(
                conn, saldo_objetivo=saldo_objetivo, nota=nota,
            )
        except ValueError as e:
            raise HTTPException(status_code=422, detail=str(e)) from e


@router.post("/regularizar-inventario", summary="Ajustar saldo de Inventario (1301) al stock físico")
def regularizar_inventario(
    saldo_objetivo: Optional[float] = Query(None, description="Saldo deseado; por defecto valor en bodega"),
    nota: str = Query("", max_length=200),
    _: dict = Depends(require_staff),
) -> dict[str, Any]:
    with get_connection() as conn:
        try:
            return contabilidad_service.regularizar_inventario(
                conn, saldo_objetivo=saldo_objetivo, nota=nota,
            )
        except ValueError as e:
            raise HTTPException(status_code=422, detail=str(e)) from e


@router.post("/reparar-saldos", summary="Corregir saldos negativos y desajustes contables")
def reparar_saldos(_: dict = Depends(require_staff)) -> dict[str, Any]:
    with get_connection() as conn:
        return contabilidad_service.reparar_saldos_negativos(conn)


@router.post("/pedidos/{id_pedido}/asientos", summary="Generar asientos de un pedido pagado")
def generar_asientos_pedido(
    id_pedido: int,
    _: dict = Depends(require_staff),
) -> dict[str, Any]:
    with get_connection() as conn:
        try:
            return contabilidad_service.generar_asientos_pedido_pagado(conn, id_pedido=id_pedido)
        except ValueError as e:
            raise HTTPException(status_code=422, detail=str(e))
