"""
routers/dashboard.py — Endpoints del Dashboard de GLOBTRADE S.A.

Rutas (montadas bajo /api/dashboard):
    GET /api/dashboard/kpis        — KPIs globales con filtro de fecha y región
    GET /api/dashboard/charts      — Datos para las 3 gráficas de barras
    GET /api/dashboard/top-paises  — Top 5 países por total_profit

Parámetros aceptados:
    date_from / fecha_inicio  — fecha inicio YYYY-MM-DD
    date_to   / fecha_fin     — fecha fin YYYY-MM-DD
    region                    — filtro por región (ventas.region)

Requisitos cubiertos: 2.1, 2.3, 2.4, 2.5, 2.6, 2.7, 2.9
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Query

from backend.database import get_connection
from backend.models.validators import validate_date_range
from backend.services.kpi_service import get_kpis, get_charts_data, get_top_paises

logger = logging.getLogger(__name__)

router = APIRouter()


def _resolve_dates(
    date_from: Optional[str],
    date_to: Optional[str],
    fecha_inicio: Optional[str],
    fecha_fin: Optional[str],
) -> tuple[Optional[str], Optional[str]]:
    """Acepta tanto date_from/date_to como los alias fecha_inicio/fecha_fin del frontend."""
    return (date_from or fecha_inicio), (date_to or fecha_fin)


@router.get("/kpis", summary="KPIs globales")
def dashboard_kpis(
    date_from:    Optional[str] = Query(default=None, description="Fecha inicio YYYY-MM-DD"),
    date_to:      Optional[str] = Query(default=None, description="Fecha fin YYYY-MM-DD"),
    fecha_inicio: Optional[str] = Query(default=None, description="Alias de date_from"),
    fecha_fin:    Optional[str] = Query(default=None, description="Alias de date_to"),
    region:       Optional[str] = Query(default=None, description="Filtrar por región"),
) -> dict:
    """
    Devuelve total_revenue, total_cost, total_profit y units_sold.
    Acepta filtro opcional por rango de fechas y región.
    Requisito 2.1, 2.6
    """
    raw_from, raw_to = _resolve_dates(date_from, date_to, fecha_inicio, fecha_fin)
    parsed_from, parsed_to = validate_date_range(raw_from, raw_to)
    with get_connection() as conn:
        result = get_kpis(conn, date_from=parsed_from, date_to=parsed_to, region=region)
    result["date_from"] = raw_from
    result["date_to"] = raw_to
    return result


@router.get("/charts", summary="Datos para gráficas de barras")
def dashboard_charts(
    date_from:    Optional[str] = Query(default=None, description="Fecha inicio YYYY-MM-DD"),
    date_to:      Optional[str] = Query(default=None, description="Fecha fin YYYY-MM-DD"),
    fecha_inicio: Optional[str] = Query(default=None, description="Alias de date_from"),
    fecha_fin:    Optional[str] = Query(default=None, description="Alias de date_to"),
    region:       Optional[str] = Query(default=None, description="Filtrar por región"),
) -> dict:
    """
    Devuelve datos agrupados por región, canal de venta y tipo de producto.
    Requisito 2.3, 2.4, 2.5, 2.6
    """
    raw_from, raw_to = _resolve_dates(date_from, date_to, fecha_inicio, fecha_fin)
    parsed_from, parsed_to = validate_date_range(raw_from, raw_to)
    with get_connection() as conn:
        return get_charts_data(conn, date_from=parsed_from, date_to=parsed_to, region=region)


@router.get("/top-paises", summary="Top 5 países por total_profit")
def dashboard_top_paises(
    date_from:    Optional[str] = Query(default=None, description="Fecha inicio YYYY-MM-DD"),
    date_to:      Optional[str] = Query(default=None, description="Fecha fin YYYY-MM-DD"),
    fecha_inicio: Optional[str] = Query(default=None, description="Alias de date_from"),
    fecha_fin:    Optional[str] = Query(default=None, description="Alias de date_to"),
    region:       Optional[str] = Query(default=None, description="Filtrar por región"),
) -> list:
    """
    Devuelve los 5 países con mayor total_profit como lista directa.
    Requisito 2.7
    """
    raw_from, raw_to = _resolve_dates(date_from, date_to, fecha_inicio, fecha_fin)
    parsed_from, parsed_to = validate_date_range(raw_from, raw_to)
    with get_connection() as conn:
        return get_top_paises(conn, date_from=parsed_from, date_to=parsed_to, region=region)
