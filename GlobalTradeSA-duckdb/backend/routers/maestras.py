"""
maestras.py — CRUD para dimensiones del modelo estrella DuckDB.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

import duckdb
from fastapi import APIRouter, HTTPException, Query

from backend.database import get_connection, execute_query, notify_db_changed
from backend.models.validators import (
    validate_pagination_maestras,
    validate_sort_by_maestra,
    validate_sort_order,
    MAESTRAS_COLUMNS,
)

logger = logging.getLogger(__name__)

router = APIRouter()

_TABLE_MAP: dict[str, str] = {
    "regiones": "dim_region",
    "paises": "dim_country",
    "tipos-producto": "dim_item_type",
    "canales": "dim_sales_channel",
    "prioridades": "dim_order_priority",
}

_PK_COLUMN: dict[str, str] = {
    "regiones": "id_region",
    "paises": "id_country",
    "tipos-producto": "id_item_type",
    "canales": "id_channel",
    "prioridades": "id_priority",
}

_REQUIRED_FIELDS: dict[str, list[str]] = {
    "regiones": ["region"],
    "paises": ["country", "id_region"],
    "tipos-producto": ["item_type", "unit_price", "unit_cost"],
    "canales": ["sales_channel"],
    "prioridades": ["order_priority"],
}

_TEXT_COLUMNS: dict[str, list[str]] = {
    "regiones": ["region"],
    "paises": ["country"],
    "tipos-producto": ["item_type"],
    "canales": ["sales_channel"],
    "prioridades": ["order_priority"],
}

VALID_TABLES: frozenset[str] = frozenset(_TABLE_MAP.keys())


def _physical_table(tabla: str) -> str:
    return _TABLE_MAP[tabla]


def _validate_tabla(tabla: str) -> None:
    if tabla not in VALID_TABLES:
        raise HTTPException(
            status_code=400,
            detail={
                "code": 400,
                "message": f"Tabla '{tabla}' no es válida.",
                "detail": f"Tablas válidas: {sorted(VALID_TABLES)}.",
            },
        )


def _validate_required_fields(tabla: str, body: dict[str, Any]) -> None:
    required = _REQUIRED_FIELDS[tabla]
    missing = [f for f in required if f not in body or body[f] is None]
    if missing:
        raise HTTPException(
            status_code=422,
            detail={
                "code": 422,
                "message": "Faltan campos obligatorios.",
                "detail": [{"field": f, "reason": "Campo obligatorio ausente."} for f in missing],
            },
        )


def _row_to_dict(row: tuple, columns: list[str]) -> dict[str, Any]:
    return {col: val for col, val in zip(columns, row)}


def _get_column_names(conn, physical: str) -> list[str]:
    sql = """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_name = ?
          AND table_schema = 'main'
        ORDER BY ordinal_position
    """
    rows = execute_query(conn, sql, (physical,), fetch="all")
    return [r[0] for r in rows]


def _next_id(conn, physical: str, pk_col: str) -> int:
    row = execute_query(conn, f"SELECT COALESCE(MAX({pk_col}), 0) + 1 FROM {physical}", fetch="one")
    return int(row[0])


@router.get("/filtros", summary="Todas las dimensiones para filtros (una sola petición)")
def get_filtros() -> dict[str, list[dict[str, Any]]]:
    """Evita 5 GET paralelos desde el frontend (límite de conexiones del navegador)."""
    with get_connection() as conn:
        regiones = execute_query(
            conn, "SELECT id_region, region FROM dim_region ORDER BY region", fetch="all"
        ) or []
        paises = execute_query(
            conn,
            "SELECT id_country, country, id_region FROM dim_country ORDER BY country",
            fetch="all",
        ) or []
        tipos = execute_query(
            conn,
            "SELECT id_item_type, item_type, unit_price, unit_cost FROM dim_item_type ORDER BY item_type",
            fetch="all",
        ) or []
        canales = execute_query(
            conn,
            "SELECT id_channel, sales_channel FROM dim_sales_channel ORDER BY sales_channel",
            fetch="all",
        ) or []
        prioridades = execute_query(
            conn,
            "SELECT id_priority, order_priority FROM dim_order_priority ORDER BY order_priority",
            fetch="all",
        ) or []

    return {
        "regiones": [{"id_region": r[0], "region": r[1]} for r in regiones],
        "paises": [{"id_country": p[0], "country": p[1], "id_region": p[2]} for p in paises],
        "tipos": [
            {"id_item_type": t[0], "item_type": t[1], "unit_price": t[2], "unit_cost": t[3]}
            for t in tipos
        ],
        "canales": [{"id_channel": c[0], "sales_channel": c[1]} for c in canales],
        "prioridades": [{"id_priority": p[0], "order_priority": p[1]} for p in prioridades],
    }


@router.get("/{tabla}/")
@router.get("/{tabla}", include_in_schema=False)
def list_records(
    tabla: str,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=500),
    search: Optional[str] = Query(default=None),
    id_region: Optional[int] = Query(default=None, description="Filtrar países por región"),
    sort_by: Optional[str] = Query(default=None),
    sort_order: str = Query(default="asc"),
) -> dict:
    _validate_tabla(tabla)
    validate_pagination_maestras(page, page_size)
    sort_order_validated = validate_sort_order(sort_order)
    pk_col = _PK_COLUMN[tabla]
    sort_col = validate_sort_by_maestra(sort_by, tabla) if sort_by else pk_col
    physical = _physical_table(tabla)
    offset = (page - 1) * page_size

    with get_connection() as conn:
        col_names = _get_column_names(conn, physical)
        where_clause = ""
        params: list[Any] = []
        text_cols = _TEXT_COLUMNS.get(tabla, [])
        if tabla == "paises" and id_region is not None:
            conditions = ["id_region = ?"]
            params.append(id_region)
            if search and text_cols:
                conditions.extend([f"{col} ILIKE ?" for col in text_cols])
                params.extend([f"%{search}%"] * len(text_cols))
            where_clause = "WHERE " + " AND ".join(conditions)
        elif search and text_cols:
            conditions = [f"{col} ILIKE ?" for col in text_cols]
            where_clause = "WHERE " + " OR ".join(conditions)
            params.extend([f"%{search}%"] * len(text_cols))

        count_sql = f"SELECT COUNT(*) FROM {physical} {where_clause}"
        count_row = execute_query(conn, count_sql, params if params else None, fetch="one")
        total = count_row[0] if count_row else 0

        data_sql = (
            f"SELECT * FROM {physical} {where_clause} "
            f"ORDER BY {sort_col} {sort_order_validated.upper()} "
            f"LIMIT ? OFFSET ?"
        )
        rows = execute_query(conn, data_sql, params + [page_size, offset], fetch="all")
        data = [_row_to_dict(row, col_names) for row in rows] if rows else []

    return {
        "data": data,
        "page": page,
        "page_size": page_size,
        "total": total,
        "total_pages": max(1, -(-total // page_size)) if total else 1,
    }


@router.get("/{tabla}/{id}/")
@router.get("/{tabla}/{id}", include_in_schema=False)
def get_record(tabla: str, id: int) -> dict:
    _validate_tabla(tabla)
    physical = _physical_table(tabla)
    pk_col = _PK_COLUMN[tabla]
    sql = f"SELECT * FROM {physical} WHERE {pk_col} = ?"

    with get_connection() as conn:
        col_names = _get_column_names(conn, physical)
        row = execute_query(conn, sql, (id,), fetch="one")

    if row is None:
        raise HTTPException(status_code=404, detail={"code": 404, "message": f"Registro {id} no encontrado."})

    return _row_to_dict(row, col_names)


@router.post("/{tabla}/", status_code=201)
@router.post("/{tabla}", status_code=201, include_in_schema=False)
def create_record(tabla: str, body: dict[str, Any]) -> dict:
    _validate_tabla(tabla)
    _validate_required_fields(tabla, body)
    physical = _physical_table(tabla)
    pk_col = _PK_COLUMN[tabla]
    insert_data = {k: v for k, v in body.items() if k != pk_col}
    if not insert_data:
        raise HTTPException(status_code=422, detail={"code": 422, "message": "Sin campos para insertar."})

    columns = list(insert_data.keys())
    values = list(insert_data.values())
    placeholders = ", ".join(["?"] * len(columns))
    col_list = ", ".join(columns)

    with get_connection() as conn:
        col_names = _get_column_names(conn, physical)
        new_id = _next_id(conn, physical, pk_col)
        sql = f"INSERT INTO {physical} ({pk_col}, {col_list}) VALUES (?, {placeholders}) RETURNING *"
        try:
            row = execute_query(conn, sql, [new_id] + values, fetch="one")
        except duckdb.ConstraintException as exc:
            raise HTTPException(status_code=409, detail={"code": 409, "message": str(exc)}) from exc
        if row is None:
            raise HTTPException(status_code=500, detail={"code": 500, "message": "No se pudo crear el registro."})
        notify_db_changed(conn)
        return _row_to_dict(row, col_names)


@router.put("/{tabla}/{id}/")
def update_record(tabla: str, id: int, body: dict[str, Any]) -> dict:
    _validate_tabla(tabla)
    _validate_required_fields(tabla, body)
    physical = _physical_table(tabla)
    pk_col = _PK_COLUMN[tabla]
    update_data = {k: v for k, v in body.items() if k != pk_col}
    if not update_data:
        raise HTTPException(status_code=422, detail={"code": 422, "message": "Sin campos para actualizar."})

    def _values_equal(current: Any, new: Any) -> bool:
        if current is None and new is None:
            return True
        if isinstance(current, (int, float)) or isinstance(new, (int, float)):
            try:
                return float(current) == float(new)
            except (TypeError, ValueError):
                pass
        return str(current).strip() == str(new).strip()

    select_sql = f"SELECT * FROM {physical} WHERE {pk_col} = ?"

    with get_connection() as conn:
        col_names = _get_column_names(conn, physical)
        current_row = execute_query(conn, f"SELECT * FROM {physical} WHERE {pk_col} = ?", (id,), fetch="one")
        if current_row is None:
            raise HTTPException(status_code=404, detail={"code": 404, "message": f"Registro {id} no encontrado."})
        current = _row_to_dict(current_row, col_names)
        changed_data = {
            k: v for k, v in update_data.items()
            if k in current and not _values_equal(current[k], v)
        }
        if not changed_data:
            return current

        merged = {**current, **changed_data}
        non_pk_cols = [c for c in col_names if c != pk_col]
        row_values = [merged[c] for c in non_pk_cols]

        # DuckDB suele fallar con UPDATE en columnas con FK/UNIQUE; reemplazo DELETE+INSERT.
        delete_sql = f"DELETE FROM {physical} WHERE {pk_col} = ?"
        insert_cols = ", ".join([pk_col] + non_pk_cols)
        insert_ph = ", ".join(["?"] * (1 + len(non_pk_cols)))
        insert_sql = f"INSERT INTO {physical} ({insert_cols}) VALUES ({insert_ph})"

        try:
            execute_query(conn, delete_sql, (id,), fetch="none")
            execute_query(conn, insert_sql, [id] + row_values, fetch="none")
            row = execute_query(conn, select_sql, (id,), fetch="one")
        except duckdb.ConstraintException:
            set_clauses = ", ".join([f"{col} = ?" for col in changed_data.keys()])
            values = list(changed_data.values()) + [id]
            update_sql = f"UPDATE {physical} SET {set_clauses} WHERE {pk_col} = ?"
            try:
                execute_query(conn, update_sql, values, fetch="none")
                row = execute_query(conn, select_sql, (id,), fetch="one")
            except duckdb.ConstraintException as exc2:
                raise HTTPException(
                    status_code=409,
                    detail={
                        "code": 409,
                        "message": "No se puede modificar: el registro está en uso en ventas u otras tablas.",
                        "detail": str(exc2),
                    },
                ) from exc2
        notify_db_changed(conn)

    if row is None:
        raise HTTPException(status_code=404, detail={"code": 404, "message": f"Registro {id} no encontrado."})
    return _row_to_dict(row, col_names)


@router.delete("/{tabla}/{id}/", status_code=200)
def delete_record(tabla: str, id: int) -> dict:
    _validate_tabla(tabla)
    physical = _physical_table(tabla)
    pk_col = _PK_COLUMN[tabla]
    check_sql = f"SELECT 1 FROM {physical} WHERE {pk_col} = ?"
    delete_sql = f"DELETE FROM {physical} WHERE {pk_col} = ?"

    with get_connection() as conn:
        exists = execute_query(conn, check_sql, (id,), fetch="one")
        if exists is None:
            raise HTTPException(status_code=404, detail={"code": 404, "message": f"Registro {id} no encontrado."})
        try:
            execute_query(conn, delete_sql, (id,), fetch="none")
        except duckdb.ConstraintException as exc:
            raise HTTPException(
                status_code=409,
                detail={"code": 409, "message": "No se puede eliminar: hay registros dependientes.", "detail": str(exc)},
            ) from exc

        notify_db_changed(conn)

    return {"message": "Registro eliminado correctamente"}
