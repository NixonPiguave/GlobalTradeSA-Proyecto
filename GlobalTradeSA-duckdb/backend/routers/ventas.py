"""
routers/ventas.py — CRUD y consultas sobre fact_ventas (vista ventas).
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Optional

from fastapi import APIRouter, Body, HTTPException, Query
from fastapi.responses import Response

from backend.database import get_connection, execute_query
from backend.models.validators import (
    validate_pagination_ventas,
    validate_sort_by_ventas,
    validate_sort_order,
    validate_date_range,
    validate_date_format,
)
from backend.services.ventas_service import (
    query_ventas,
    export_ventas_csv,
    truncate_fact_ventas,
    get_venta_by_id,
    create_venta,
    update_venta,
    delete_venta,
)

logger = logging.getLogger(__name__)

router = APIRouter()

_REQUIRED_VENTA_FIELDS = (
    "order_id", "region", "country", "item_type", "sales_channel", "order_priority",
    "order_date", "ship_date", "units_sold",
)


def _resolve_dates(
    order_date_from: Optional[str],
    order_date_to: Optional[str],
    fecha_inicio: Optional[str],
    fecha_fin: Optional[str],
) -> tuple[Optional[str], Optional[str]]:
    date_from = order_date_from or fecha_inicio
    date_to = order_date_to or fecha_fin
    return date_from, date_to


def _parse_venta_body(body: dict[str, Any], *, require_prices: bool) -> dict[str, Any]:
    missing = [f for f in _REQUIRED_VENTA_FIELDS if f not in body or body[f] is None or body[f] == ""]
    if missing:
        raise HTTPException(
            status_code=422,
            detail={"message": "Faltan campos obligatorios.", "fields": missing},
        )
    order_date = validate_date_format(str(body["order_date"]), "order_date")
    ship_date = validate_date_format(str(body["ship_date"]), "ship_date")
    if ship_date < order_date:
        raise HTTPException(status_code=400, detail="ship_date no puede ser anterior a order_date.")

    parsed: dict[str, Any] = {
        "order_id": body["order_id"],
        "region": str(body["region"]).strip(),
        "country": str(body["country"]).strip(),
        "item_type": str(body["item_type"]).strip(),
        "sales_channel": str(body["sales_channel"]).strip(),
        "order_priority": str(body["order_priority"]).strip(),
        "order_date": order_date.isoformat(),
        "ship_date": ship_date.isoformat(),
        "units_sold": body["units_sold"],
    }
    for price_field in ("unit_price", "unit_cost"):
        val = body.get(price_field)
        if val is None or val == "":
            if require_prices:
                raise HTTPException(
                    status_code=422,
                    detail={"message": "Faltan campos obligatorios.", "fields": [price_field]},
                )
        else:
            parsed[price_field] = val
    return parsed


@router.get("/paises", summary="Lista de países únicos en ventas")
@router.get("/paises/", include_in_schema=False)
def list_paises_ventas() -> list[str]:
    with get_connection() as conn:
        rows = execute_query(
            conn,
            "SELECT DISTINCT country FROM ventas WHERE country IS NOT NULL ORDER BY country",
            fetch="all",
        )
    return [r[0] for r in rows] if rows else []


@router.get("/export", summary="Exportar ventas como CSV")
@router.get("/export/", include_in_schema=False)
def export_ventas(
    region: Optional[str] = Query(default=None),
    country: Optional[str] = Query(default=None),
    item_type: Optional[str] = Query(default=None),
    sales_channel: Optional[str] = Query(default=None),
    order_priority: Optional[str] = Query(default=None),
    order_date_from: Optional[str] = Query(default=None),
    order_date_to: Optional[str] = Query(default=None),
    fecha_inicio: Optional[str] = Query(default=None),
    fecha_fin: Optional[str] = Query(default=None),
    q: Optional[str] = Query(default=None, max_length=120),
    sort_by: str = Query(default="order_id"),
    sort_order: str = Query(default="asc"),
) -> Response:
    safe_sort_by = validate_sort_by_ventas(sort_by)
    safe_sort_order = validate_sort_order(sort_order)
    raw_from, raw_to = _resolve_dates(order_date_from, order_date_to, fecha_inicio, fecha_fin)
    parsed_from, parsed_to = validate_date_range(raw_from, raw_to)
    filters = {
        "region": region, "country": country, "item_type": item_type,
        "sales_channel": sales_channel, "order_priority": order_priority,
        "order_date_from": parsed_from, "order_date_to": parsed_to,
        "q": q,
    }
    with get_connection() as conn:
        csv_content = export_ventas_csv(conn, filters, safe_sort_by, safe_sort_order)
    return Response(
        content=csv_content,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=ventas_export.csv"},
    )


def _truncate_sync() -> dict:
    with get_connection() as conn:
        return truncate_fact_ventas(conn)


@router.delete("/truncate", summary="Borrar todos los registros de fact_ventas")
async def truncate_ventas() -> dict:
    return await asyncio.to_thread(_truncate_sync)


@router.get("/{id_venta}", summary="Obtener una venta por id_venta")
def get_venta(id_venta: int) -> dict:
    with get_connection() as conn:
        return get_venta_by_id(conn, id_venta)


@router.post("", status_code=201, summary="Crear venta en fact_ventas")
@router.post("/", status_code=201, include_in_schema=False)
def post_venta(body: dict[str, Any] = Body(...)) -> dict:
    data = _parse_venta_body(body, require_prices=False)
    with get_connection() as conn:
        return create_venta(conn, data)


@router.put("/{id_venta}", summary="Actualizar venta")
def put_venta(id_venta: int, body: dict[str, Any] = Body(...)) -> dict:
    data = _parse_venta_body(body, require_prices=False)
    with get_connection() as conn:
        return update_venta(conn, id_venta, data)


@router.delete("/{id_venta}", summary="Eliminar una venta")
def remove_venta(id_venta: int) -> dict:
    with get_connection() as conn:
        return delete_venta(conn, id_venta)


@router.get("", summary="Consulta paginada de ventas")
@router.get("/", include_in_schema=False)
def list_ventas(
    region: Optional[str] = Query(default=None),
    country: Optional[str] = Query(default=None),
    item_type: Optional[str] = Query(default=None),
    sales_channel: Optional[str] = Query(default=None),
    order_priority: Optional[str] = Query(default=None),
    order_date_from: Optional[str] = Query(default=None),
    order_date_to: Optional[str] = Query(default=None),
    fecha_inicio: Optional[str] = Query(default=None),
    fecha_fin: Optional[str] = Query(default=None),
    q: Optional[str] = Query(default=None, max_length=120),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=100, ge=1, le=500),
    sort_by: str = Query(default="order_id"),
    sort_order: str = Query(default="asc"),
) -> dict:
    validate_pagination_ventas(page, page_size)
    safe_sort_by = validate_sort_by_ventas(sort_by)
    safe_sort_order = validate_sort_order(sort_order)
    raw_from, raw_to = _resolve_dates(order_date_from, order_date_to, fecha_inicio, fecha_fin)
    parsed_from, parsed_to = validate_date_range(raw_from, raw_to)
    filters = {
        "region": region, "country": country, "item_type": item_type,
        "sales_channel": sales_channel, "order_priority": order_priority,
        "order_date_from": parsed_from, "order_date_to": parsed_to,
        "q": q,
    }
    with get_connection() as conn:
        return query_ventas(conn, filters, page, page_size, safe_sort_by, safe_sort_order)
