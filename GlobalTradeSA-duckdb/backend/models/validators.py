"""
validators.py — Validadores reutilizables para parámetros de la API.
"""

from __future__ import annotations

import re
from datetime import date, datetime
from typing import Optional

from fastapi import HTTPException

PAGE_SIZE_MIN = 1
PAGE_SIZE_MAX_MAESTRAS = 500  # suficiente para poblar selects de filtros
PAGE_SIZE_MAX_VENTAS = 500
PAGE_DEFAULT_MAESTRAS = 50
PAGE_DEFAULT_VENTAS = 100

VENTAS_COLUMNS: frozenset[str] = frozenset(
    {
        "region",
        "country",
        "item_type",
        "sales_channel",
        "order_priority",
        "order_date",
        "order_id",
        "ship_date",
        "units_sold",
        "unit_price",
        "unit_cost",
        "total_revenue",
        "total_cost",
        "total_profit",
        "id_venta",
    }
)

MAESTRAS_COLUMNS: dict[str, frozenset[str]] = {
    "regiones": frozenset({"id_region", "region"}),
    "paises": frozenset({"id_country", "country", "id_region"}),
    "tipos-producto": frozenset({"id_item_type", "item_type", "unit_price", "unit_cost"}),
    "canales": frozenset({"id_channel", "sales_channel"}),
    "prioridades": frozenset({"id_priority", "order_priority"}),
}

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def validate_date_format(value: str, field_name: str = "fecha") -> date:
    if not _DATE_RE.match(value):
        raise HTTPException(
            status_code=400,
            detail=(
                f"El parámetro '{field_name}' tiene un formato inválido: '{value}'. "
                "Se esperaba el formato YYYY-MM-DD."
            ),
        )
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=(
                f"El parámetro '{field_name}' contiene una fecha inexistente: '{value}'."
            ),
        )


def validate_date_range(
    date_from: Optional[str],
    date_to: Optional[str],
    from_field: str = "date_from",
    to_field: str = "date_to",
) -> tuple[Optional[date], Optional[date]]:
    parsed_from: Optional[date] = None
    parsed_to: Optional[date] = None

    if date_from is not None:
        parsed_from = validate_date_format(date_from, from_field)

    if date_to is not None:
        parsed_to = validate_date_format(date_to, to_field)

    if parsed_from is not None and parsed_to is not None:
        if parsed_from > parsed_to:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"El rango de fechas es inválido: '{from_field}' ({date_from}) "
                    f"es posterior a '{to_field}' ({date_to})."
                ),
            )

    return parsed_from, parsed_to


def validate_pagination_maestras(page: int, page_size: int) -> None:
    _validate_page(page)
    if not (PAGE_SIZE_MIN <= page_size <= PAGE_SIZE_MAX_MAESTRAS):
        raise HTTPException(
            status_code=400,
            detail=(
                f"El parámetro 'page_size' debe estar entre {PAGE_SIZE_MIN} y "
                f"{PAGE_SIZE_MAX_MAESTRAS}. Valor recibido: {page_size}."
            ),
        )


def validate_pagination_ventas(page: int, page_size: int) -> None:
    _validate_page(page)
    if not (PAGE_SIZE_MIN <= page_size <= PAGE_SIZE_MAX_VENTAS):
        raise HTTPException(
            status_code=400,
            detail=(
                f"El parámetro 'page_size' debe estar entre {PAGE_SIZE_MIN} y "
                f"{PAGE_SIZE_MAX_VENTAS}. Valor recibido: {page_size}."
            ),
        )


def _validate_page(page: int) -> None:
    if page < 1:
        raise HTTPException(
            status_code=400,
            detail=f"El parámetro 'page' debe ser >= 1. Valor recibido: {page}.",
        )


def validate_sort_by_ventas(sort_by: str) -> str:
    normalized = sort_by.strip().lower()
    if normalized not in VENTAS_COLUMNS:
        raise HTTPException(
            status_code=400,
            detail=(
                f"La columna '{sort_by}' no es válida. "
                f"Columnas válidas: {sorted(VENTAS_COLUMNS)}."
            ),
        )
    return normalized


def validate_sort_by_maestra(sort_by: str, tabla: str) -> str:
    if tabla not in MAESTRAS_COLUMNS:
        raise HTTPException(
            status_code=400,
            detail=(
                f"La tabla '{tabla}' no es válida. "
                f"Tablas válidas: {sorted(MAESTRAS_COLUMNS.keys())}."
            ),
        )
    normalized = sort_by.strip().lower()
    valid_cols = MAESTRAS_COLUMNS[tabla]
    if normalized not in valid_cols:
        raise HTTPException(
            status_code=400,
            detail=(
                f"La columna '{sort_by}' no existe en '{tabla}'. "
                f"Columnas válidas: {sorted(valid_cols)}."
            ),
        )
    return normalized


def validate_sort_order(sort_order: str) -> str:
    normalized = sort_order.strip().lower()
    if normalized not in {"asc", "desc"}:
        raise HTTPException(
            status_code=400,
            detail=f"sort_order debe ser 'asc' o 'desc'. Valor recibido: '{sort_order}'.",
        )
    return normalized
