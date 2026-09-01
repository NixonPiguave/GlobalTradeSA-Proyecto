"""
generador.py — Endpoint para generar ventas sintéticas.
"""

from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, HTTPException, Query

from backend.database import get_connection, release_thread_connection
from backend.services.generador_service import generar_ventas

logger = logging.getLogger(__name__)

router = APIRouter()


def _generar_sync(cantidad: int) -> dict:
    try:
        with get_connection() as conn:
            return generar_ventas(conn, cantidad)
    finally:
        release_thread_connection()


@router.post("/generar", summary="Generar ventas sintéticas")
async def generar(
    cantidad: int = Query(default=100_000, ge=1, le=1_000_000, description="Registros a generar"),
) -> dict:
    try:
        return await asyncio.to_thread(_generar_sync, cantidad)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
