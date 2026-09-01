"""
routers/pedidos.py — Checkout, pago simulado y "Mis pedidos" del portal B2B.
"""

from __future__ import annotations

from typing import Any

import duckdb
from fastapi import APIRouter, Depends, HTTPException

from gmbackend.database import get_db
from gmbackend.models.ventas import CheckoutRequest, PagoSimuladoRequest
from gmbackend.routers.auth import get_current_user
from gmbackend.services import pedido_service
from shared.api.db_errors import codigo_http_bd, detalle_respuesta_bd

router = APIRouter(prefix="/api/pedidos", tags=["pedidos"])


def _ids(current: dict) -> tuple[int, int]:
    cliente = current.get("cliente")
    if not cliente:
        raise HTTPException(status_code=403, detail="La cuenta no tiene ficha de cliente B2B.")
    return int(cliente["id_cliente"]), int(current["usuario"]["id_usuario"])


@router.post("/checkout", status_code=201, summary="Confirmar checkout (carrito → pedido pendiente de pago)")
def checkout(
    body: CheckoutRequest,
    current: dict = Depends(get_current_user),
    conn: duckdb.DuckDBPyConnection = Depends(get_db),
) -> dict[str, Any]:
    id_cliente, id_usuario = _ids(current)
    try:
        return pedido_service.crear_pedido_desde_carrito(
            conn,
            id_cliente=id_cliente,
            id_usuario=id_usuario,
            direccion_entrega=body.direccion_entrega,
            ciudad=body.ciudad,
            pais=body.pais,
            notas=body.notas,
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except duckdb.Error as e:
        raise HTTPException(
            status_code=codigo_http_bd(e),
            detail={"message": detalle_respuesta_bd(e)["message"]},
        ) from e


@router.post("/pagar", summary="Pago simulado (idempotente)")
def pagar(
    body: PagoSimuladoRequest,
    current: dict = Depends(get_current_user),
    conn: duckdb.DuckDBPyConnection = Depends(get_db),
) -> dict[str, Any]:
    id_cliente, id_usuario = _ids(current)
    try:
        return pedido_service.pagar_pedido_simulado(
            conn,
            id_pedido=body.id_pedido,
            id_cliente=id_cliente,
            id_usuario=id_usuario,
            metodo=body.metodo,
            referencia=body.referencia,
            ultimos_digitos=body.ultimos_digitos,
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except duckdb.Error as e:
        raise HTTPException(
            status_code=codigo_http_bd(e),
            detail={"message": detalle_respuesta_bd(e)["message"]},
        ) from e


@router.get("", summary="Mis pedidos")
def mis_pedidos(
    current: dict = Depends(get_current_user),
    conn: duckdb.DuckDBPyConnection = Depends(get_db),
) -> list[dict[str, Any]]:
    id_cliente, _ = _ids(current)
    return pedido_service.listar_pedidos_cliente(conn, id_cliente)


@router.post("/{id_pedido}/cancelar", summary="Cancelar mi pedido (solo pendiente de pago o pagado)")
def cancelar_mi_pedido(
    id_pedido: int,
    current: dict = Depends(get_current_user),
    conn: duckdb.DuckDBPyConnection = Depends(get_db),
) -> dict[str, Any]:
    id_cliente, id_usuario = _ids(current)
    try:
        return pedido_service.cancelar_pedido_cliente(
            conn,
            id_pedido=id_pedido,
            id_cliente=id_cliente,
            id_usuario=id_usuario,
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


@router.post("/{id_pedido}/volver-a-pedir", summary="Volver a pedir (replicar líneas al carrito)")
def volver_a_pedir_endpoint(
    id_pedido: int,
    current: dict = Depends(get_current_user),
    conn: duckdb.DuckDBPyConnection = Depends(get_db),
) -> dict[str, Any]:
    id_cliente, _ = _ids(current)
    try:
        return pedido_service.volver_a_pedir(conn, id_pedido=id_pedido, id_cliente=id_cliente)
    except pedido_service.ReordenSinAgregadosError as e:
        raise HTTPException(
            status_code=422,
            detail={"message": str(e), "resumen": e.resumen},
        ) from e
    except ValueError as e:
        msg = str(e)
        if "no encontrado" in msg.lower():
            raise HTTPException(status_code=404, detail=msg) from e
        raise HTTPException(status_code=422, detail=msg) from e
    except duckdb.Error as e:
        raise HTTPException(
            status_code=codigo_http_bd(e),
            detail={"message": detalle_respuesta_bd(e)["message"]},
        ) from e


@router.get("/{id_pedido}", summary="Detalle de mi pedido")
def detalle_pedido(
    id_pedido: int,
    current: dict = Depends(get_current_user),
    conn: duckdb.DuckDBPyConnection = Depends(get_db),
) -> dict[str, Any]:
    id_cliente, _ = _ids(current)
    pedido = pedido_service.obtener_pedido(conn, id_pedido)
    if not pedido or pedido["id_cliente"] != id_cliente:
        raise HTTPException(status_code=404, detail="Pedido no encontrado.")
    return pedido
