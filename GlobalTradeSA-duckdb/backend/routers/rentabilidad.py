"""
routers/rentabilidad.py — Endpoints de análisis de rentabilidad.

Rutas (montadas bajo /api/rentabilidad):
    GET /api/rentabilidad/region/   — Agrupado por región
    GET /api/rentabilidad/canal/    — Agrupado por canal de venta
    GET /api/rentabilidad/producto/ — Agrupado por tipo de producto
    GET /api/rentabilidad           — Ruta unificada con ?dimension=region|canal|producto

Requisitos cubiertos: 6.1, 6.2, 6.3, 6.4, 6.5, 6.7, 6.9
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from backend.database import get_connection
from backend.models.validators import validate_date_range
from backend.services.rentabilidad_service import (
    get_rentabilidad_region,
    get_rentabilidad_canal,
    get_rentabilidad_producto,
)

logger = logging.getLogger(__name__)

router = APIRouter()

_DIMENSION_MAP = {
    "region":   get_rentabilidad_region,
    "canal":    get_rentabilidad_canal,
    "producto": get_rentabilidad_producto,
}


def _paginate(data: list, page: int, page_size: int) -> dict:
    """Aplica paginación en memoria sobre una lista ya calculada."""
    total = len(data)
    start = (page - 1) * page_size
    end = start + page_size
    return {
        "data": data[start:end],
        "page": page,
        "page_size": page_size,
        "total": total,
        "total_pages": max(1, -(-total // page_size)),  # ceil division
    }


# ---------------------------------------------------------------------------
# Ruta unificada — usada por el frontend: /api/rentabilidad?dimension=region
# ---------------------------------------------------------------------------

@router.get("", summary="Rentabilidad por dimensión (unificada)")
@router.get("/", include_in_schema=False)
def rentabilidad_unificada(
    dimension: str           = Query(default="region", description="region | canal | producto"),
    page:      int           = Query(default=1,  ge=1),
    page_size: int           = Query(default=20, ge=1, le=200),
    date_from: Optional[str] = Query(default=None, description="Fecha inicio YYYY-MM-DD"),
    date_to:   Optional[str] = Query(default=None, description="Fecha fin YYYY-MM-DD"),
) -> dict:
    """
    Ruta unificada que despacha a la función correcta según el parámetro
    `dimension` (region, canal o producto). Usada por el frontend SPA.
    """
    fn = _DIMENSION_MAP.get(dimension.lower())
    if fn is None:
        raise HTTPException(
            status_code=400,
            detail={
                "code": 400,
                "message": f"Dimensión '{dimension}' no válida. Use: region, canal o producto.",
            },
        )
    parsed_from, parsed_to = validate_date_range(date_from, date_to)
    with get_connection() as conn:
        data = fn(conn, date_from=parsed_from, date_to=parsed_to)
    return _paginate(data, page, page_size)


# ---------------------------------------------------------------------------
# Rutas individuales por dimensión (compatibilidad con el diseño original)
# ---------------------------------------------------------------------------

@router.get("/region/", summary="Rentabilidad por región")
def rentabilidad_region(
    date_from: Optional[str] = Query(default=None, description="Fecha inicio YYYY-MM-DD"),
    date_to:   Optional[str] = Query(default=None, description="Fecha fin YYYY-MM-DD"),
) -> dict:
    """Rentabilidad agrupada por región, ordenada por total_profit DESC. Requisito 6.4"""
    parsed_from, parsed_to = validate_date_range(date_from, date_to)
    with get_connection() as conn:
        data = get_rentabilidad_region(conn, date_from=parsed_from, date_to=parsed_to)
    return {"data": data}


@router.get("/canal/", summary="Rentabilidad por canal de venta")
def rentabilidad_canal(
    date_from: Optional[str] = Query(default=None, description="Fecha inicio YYYY-MM-DD"),
    date_to:   Optional[str] = Query(default=None, description="Fecha fin YYYY-MM-DD"),
) -> dict:
    """Rentabilidad agrupada por sales_channel, ordenada por total_profit DESC. Requisito 6.4"""
    parsed_from, parsed_to = validate_date_range(date_from, date_to)
    with get_connection() as conn:
        data = get_rentabilidad_canal(conn, date_from=parsed_from, date_to=parsed_to)
    return {"data": data}


@router.get("/producto/", summary="Rentabilidad por tipo de producto")
def rentabilidad_producto(
    date_from: Optional[str] = Query(default=None, description="Fecha inicio YYYY-MM-DD"),
    date_to:   Optional[str] = Query(default=None, description="Fecha fin YYYY-MM-DD"),
) -> dict:
    """Rentabilidad agrupada por item_type con units_sold, ordenada por total_profit DESC. Requisito 6.4"""
    parsed_from, parsed_to = validate_date_range(date_from, date_to)
    with get_connection() as conn:
        data = get_rentabilidad_producto(conn, date_from=parsed_from, date_to=parsed_to)
    return {"data": data}
