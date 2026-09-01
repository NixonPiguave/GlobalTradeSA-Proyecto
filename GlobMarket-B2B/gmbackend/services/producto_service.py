from __future__ import annotations

import logging
import math
from typing import Any, Optional

import duckdb

logger = logging.getLogger(__name__)

MAPA_CATEGORIAS_ES: dict[str, str] = {
    "Baby Food": "Alimentos para bebé",
    "Beverages": "Bebidas",
    "Cereal": "Cereales",
    "Clothes": "Ropa",
    "Cosmetics": "Cosméticos",
    "Fruits": "Frutas",
    "Household": "Hogar",
    "Meat": "Carnes",
    "Office Supplies": "Suministros de oficina",
    "Personal Care": "Cuidado personal",
    "Snacks": "Snacks",
    "Vegetables": "Verduras",
}


def _categoria_es(nombre_en: str) -> str:
    return MAPA_CATEGORIAS_ES.get(nombre_en, nombre_en)


def listar_categorias(conn: duckdb.DuckDBPyConnection) -> list[dict[str, Any]]:
    conn.execute(
        """
        SELECT id_item_type, item_type
        FROM dim_item_type
        ORDER BY item_type
        """
    )
    rows = conn.fetchall()
    return [{"id_item_type": int(r[0]), "item_type": _categoria_es(r[1])} for r in rows]


def obtener_producto(conn: duckdb.DuckDBPyConnection, *, id_producto: int) -> dict[str, Any] | None:
    conn.execute(
        """
        SELECT
          p.id_producto,
          p.nombre_producto,
          p.descripcion,
          p.id_item_type,
          it.item_type AS categoria,
          CAST(p.precio_unitario AS DOUBLE) AS precio_unitario,
          CAST(p.precio_mayorista AS DOUBLE) AS precio_mayorista,
          p.imagen_url,
          p.activo
        FROM dim_producto p
        JOIN dim_item_type it ON it.id_item_type = p.id_item_type
        WHERE p.id_producto = ? AND p.activo = true
        """,
        [id_producto],
    )
    r = conn.fetchone()
    if not r:
        return None
    return {
        "id_producto": int(r[0]),
        "nombre_producto": r[1],
        "descripcion": r[2],
        "id_item_type": int(r[3]),
        "categoria": _categoria_es(r[4]),
        "precio_unitario": float(r[5]),
        "precio_mayorista": float(r[6]),
        "imagen_url": r[7],
        "activo": bool(r[8]),
    }


def listar_productos(
    conn: duckdb.DuckDBPyConnection,
    *,
    id_item_type: Optional[int],
    page: int,
    page_size: int,
) -> dict[str, Any]:
    if page < 1:
        page = 1
    if page_size < 1:
        page_size = 12
    if page_size > 48:
        page_size = 48

    where = "WHERE p.activo = true"
    params: list[Any] = []
    if id_item_type is not None:
        where += " AND p.id_item_type = ?"
        params.append(id_item_type)

    conn.execute(
        f"""
        SELECT COUNT(*)
        FROM dim_producto p
        {where}
        """,
        params,
    )
    total_items = int(conn.fetchone()[0])
    total_pages = max(1, int(math.ceil(total_items / page_size))) if total_items else 1
    if page > total_pages:
        page = total_pages

    offset = (page - 1) * page_size

    conn.execute(
        f"""
        SELECT
          p.id_producto,
          p.nombre_producto,
          p.descripcion,
          p.id_item_type,
          it.item_type AS categoria,
          CAST(p.precio_unitario AS DOUBLE) AS precio_unitario,
          CAST(p.precio_mayorista AS DOUBLE) AS precio_mayorista,
          p.imagen_url,
          p.activo
        FROM dim_producto p
        JOIN dim_item_type it ON it.id_item_type = p.id_item_type
        {where}
        ORDER BY it.item_type, p.nombre_producto
        LIMIT ? OFFSET ?
        """,
        [*params, page_size, offset],
    )

    rows = conn.fetchall()
    items = [
        {
            "id_producto": int(r[0]),
            "nombre_producto": r[1],
            "descripcion": r[2],
            "id_item_type": int(r[3]),
            "categoria": _categoria_es(r[4]),
            "precio_unitario": float(r[5]),
            "precio_mayorista": float(r[6]),
            "imagen_url": r[7],
            "activo": bool(r[8]),
        }
        for r in rows
    ]

    return {
        "items": items,
        "page": page,
        "page_size": page_size,
        "total_items": total_items,
        "total_pages": total_pages,
    }

