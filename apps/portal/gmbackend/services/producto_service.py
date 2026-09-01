from __future__ import annotations

import logging
import math
from typing import Any, Optional

import duckdb

from shared.database.connection import table_exists
from shared.services import listas_precio_service, precios_b2b, red_bodegas
from shared.services.config_service import obtener_config_int

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


def _imagen_publica(imagen_url: str | None) -> str | None:
    """Convierte rutas relativas de uploads a URL servida por /media."""
    if not imagen_url:
        return None
    if imagen_url.startswith(("http://", "https://", "/")):
        return imagen_url
    return f"/media/{imagen_url}"


def listar_categorias(conn: duckdb.DuckDBPyConnection) -> list[dict[str, Any]]:
    """Solo categorías administradas y activas (no huérfanos de dim_item_type)."""
    if table_exists(conn, "categorias"):
        conn.execute(
            """
            SELECT COALESCE(c.id_item_type, c.id_categoria) AS id_item_type,
                   COALESCE(it.item_type, c.nombre) AS item_type
            FROM categorias c
            LEFT JOIN dim_item_type it ON it.id_item_type = c.id_item_type
            WHERE COALESCE(c.activo, true) = true
              AND c.id_item_type IS NOT NULL
            ORDER BY COALESCE(it.item_type, c.nombre)
            """
        )
    else:
        conn.execute(
            """
            SELECT it.id_item_type, it.item_type
            FROM dim_item_type it
            ORDER BY it.item_type
            """
        )
    rows = conn.fetchall()
    return [{"id_item_type": int(r[0]), "item_type": _categoria_es(r[1])} for r in rows]


def contexto_red(
    conn: duckdb.DuckDBPyConnection, *, id_cliente: Optional[int] = None
) -> dict[str, Any]:
    """Zona de entrega del cliente y bodegas que la abastecen.

    Sin sesión o con país no mapeado devuelve la red completa: el catálogo
    sigue visible como vitrina, pero `zona_resuelta` queda en False.
    """
    return red_bodegas.red_de_cliente(conn, id_cliente=id_cliente)


def _almacenes(red: Optional[dict[str, Any]]) -> list[int]:
    return list((red or {}).get("almacenes") or [])


def _info_zona(red: Optional[dict[str, Any]]) -> dict[str, Any]:
    red = red or {}
    return {
        "zona_entrega": red.get("macro_zona"),
        "zona_label": red.get("macro_label"),
        "bodega_asignada": red.get("bodega_principal"),
        "zona_resuelta": bool(red.get("zona_resuelta")),
    }


def _stock_neto(
    conn: duckdb.DuckDBPyConnection,
    id_producto: int,
    almacenes: Optional[list[int]] = None,
) -> float:
    if not table_exists(conn, "stock_almacen"):
        return 0.0
    return red_bodegas.stock_zona(conn, id_producto, almacenes)


def _tiene_dto_categoria(conn: duckdb.DuckDBPyConnection) -> bool:
    try:
        return bool(
            conn.execute(
                """
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'categorias' AND column_name = 'descuento_pct'
                """
            ).fetchone()
        )
    except Exception:
        return False


def _stock_minimo(conn: duckdb.DuckDBPyConnection, id_producto: int) -> float:
    row = None
    try:
        row = conn.execute(
            "SELECT CAST(COALESCE(stock_minimo, 10) AS DOUBLE) FROM dim_producto WHERE id_producto = ?",
            [id_producto],
        ).fetchone()
    except Exception:
        row = None
    if row and row[0] is not None:
        return float(row[0])
    if table_exists(conn, "alertas_stock"):
        al = conn.execute(
            """
            SELECT CAST(umbral_minimo AS DOUBLE) FROM alertas_stock
            WHERE id_producto = ? AND activa = true ORDER BY id_alerta LIMIT 1
            """,
            [id_producto],
        ).fetchone()
        if al and al[0] is not None:
            return float(al[0])
    return 10.0


def _estado_stock(disponible: float, minimo: float) -> str:
    if disponible <= 0:
        return "sin_stock"
    if disponible <= minimo:
        return "poco_stock"
    return "ok"


def obtener_producto(
    conn: duckdb.DuckDBPyConnection,
    *,
    id_producto: int,
    id_cliente: Optional[int] = None,
    red: Optional[dict[str, Any]] = None,
) -> dict[str, Any] | None:
    red = red if red is not None else contexto_red(conn, id_cliente=id_cliente)
    almacenes = _almacenes(red)

    stock_sql = ""
    if table_exists(conn, "stock_almacen"):
        stock_sql = f", {red_bodegas.sql_stock_zona(almacenes, 'p.id_producto')} AS stock_disponible"

    dto_cat_sql = (
        """,
          CAST(COALESCE(c.descuento_pct, 0) AS DOUBLE) AS dto_categoria,
          COALESCE(c.descuento_aplica_a, 'mayorista') AS dto_cat_aplica,
          c.descuento_hasta AS dto_cat_hasta,
          c.descuento_motivo AS dto_cat_motivo,
          c.nombre AS dto_cat_nombre"""
        if _tiene_dto_categoria(conn)
        else """,
          CAST(0 AS DOUBLE) AS dto_categoria,
          'mayorista' AS dto_cat_aplica,
          CAST(NULL AS DATE) AS dto_cat_hasta,
          CAST(NULL AS VARCHAR) AS dto_cat_motivo,
          c.nombre AS dto_cat_nombre"""
    )

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
          p.activo,
          CAST(COALESCE(p.descuento_pct, 0) AS DOUBLE) AS descuento_pct,
          CAST(p.precio_rebajado AS DOUBLE) AS precio_rebajado,
          COALESCE(p.descuento_aplica_a, 'mayorista') AS descuento_aplica_a,
          p.fecha_rebaja_hasta
          {dto_cat_sql}
          {stock_sql}
        FROM dim_producto p
        JOIN dim_item_type it ON it.id_item_type = p.id_item_type
        LEFT JOIN categorias c ON c.id_item_type = p.id_item_type
        WHERE p.id_producto = ? AND p.activo = true
          AND c.id_item_type IS NOT NULL AND COALESCE(c.activo, false) = true
        """,
        [id_producto],
    )
    r = conn.fetchone()
    if not r:
        return None

    precio_unitario = float(r[5] or 0)
    precio_mayorista = float(r[6] or 0)
    moq = obtener_config_int(conn, "MOQ_MAYORISTA", 10)
    precio_mayorista, moq, lista_tarifa = listas_precio_service.aplicar_tarifa(
        conn,
        id_cliente=id_cliente,
        id_producto=id_producto,
        precio_mayorista=precio_mayorista,
        moq_default=moq,
    )
    dto = precios_b2b.mejor_descuento(
        pct_producto=r[9],
        aplica_producto=r[11],
        rebaja_hasta=r[12],
        pct_categoria=r[13],
        aplica_categoria=r[14],
        categoria_hasta=r[15],
        categoria_nombre=r[17],
        categoria_motivo=r[16],
    )
    precio_rebajado_manual = float(r[10]) if r[10] is not None else None
    precio_rebajado = None
    if dto["pct"] > 0 or (precio_rebajado_manual and dto["origen"] == "producto"):
        efectivo = precios_b2b.precio_mayorista_efectivo(
            precio_mayorista,
            pct=dto["pct"],
            aplica_a=dto["aplica_a"],
            precio_rebajado=precio_rebajado_manual,
            origen=dto["origen"],
        )
        if efectivo < precio_mayorista:
            precio_rebajado = efectivo

    stock = max(0.0, float(r[18])) if len(r) > 18 and r[18] is not None else 0.0
    minimo = _stock_minimo(conn, id_producto)
    ahorro_pct = 0.0
    if precio_unitario > 0 and precio_mayorista > 0:
        ahorro_pct = round((1 - precio_mayorista / precio_unitario) * 100, 1)

    return {
        "id_producto": int(r[0]),
        "sku": f"GM-{int(r[0]):06d}",
        "nombre_producto": r[1],
        "descripcion": r[2],
        "id_item_type": int(r[3]),
        "categoria": _categoria_es(r[4]),
        "precio_unitario": precio_unitario,
        "precio_mayorista": precio_mayorista,
        "descuento_pct": dto["pct"],
        "descuento_origen": dto["origen"],
        "descuento_etiqueta": dto["etiqueta"],
        "precio_rebajado": precio_rebajado,
        "descuento_aplica_a": dto["aplica_a"],
        "ahorro_pct": ahorro_pct,
        "imagen_url": _imagen_publica(r[7]),
        "activo": bool(r[8]),
        "stock_disponible": stock,
        "stock_minimo": minimo,
        "estado_stock": _estado_stock(stock, minimo),
        "moq": moq,
        "lista_precio": lista_tarifa,
        **_info_zona(red),
    }


def listar_marcas(conn: duckdb.DuckDBPyConnection) -> list[dict[str, Any]]:
    conn.execute("SELECT id_marca, nombre FROM marcas WHERE activo = true ORDER BY nombre")
    return [{"id_marca": int(r[0]), "nombre": r[1]} for r in conn.fetchall()]


def listar_lineas(conn: duckdb.DuckDBPyConnection, *, id_marca: Optional[int] = None) -> list[dict[str, Any]]:
    where = "WHERE activo = true"
    params: list[Any] = []
    if id_marca is not None:
        where += " AND id_marca = ?"
        params.append(id_marca)
    conn.execute(f"SELECT id_linea, nombre, id_marca FROM lineas_producto {where} ORDER BY nombre", params)
    return [{"id_linea": int(r[0]), "nombre": r[1], "id_marca": int(r[2]) if r[2] is not None else None} for r in conn.fetchall()]


def listar_productos(
    conn: duckdb.DuckDBPyConnection,
    *,
    id_item_type: Optional[int],
    page: int,
    page_size: int,
    q: Optional[str] = None,
    id_marca: Optional[int] = None,
    id_linea: Optional[int] = None,
    precio_min: Optional[float] = None,
    precio_max: Optional[float] = None,
    orden: Optional[str] = None,
    autenticado: bool = False,
    id_cliente: Optional[int] = None,
    red: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    red = red if red is not None else contexto_red(conn, id_cliente=id_cliente)
    almacenes = _almacenes(red)
    if page < 1:
        page = 1
    if page_size < 1:
        page_size = 12
    if page_size > 48:
        page_size = 48

    where = "WHERE p.activo = true AND c.id_item_type IS NOT NULL AND COALESCE(c.activo, false) = true"
    params: list[Any] = []
    if id_item_type is not None:
        where += " AND p.id_item_type = ?"
        params.append(id_item_type)
    if q:
        term = f"%{q.strip().lower()}%"
        where += " AND (LOWER(p.nombre_producto) LIKE ? OR LOWER(COALESCE(p.descripcion, '')) LIKE ?)"
        params.extend([term, term])
    if id_marca is not None:
        where += " AND p.id_marca = ?"
        params.append(id_marca)
    if id_linea is not None:
        where += " AND p.id_linea = ?"
        params.append(id_linea)
    if precio_min is not None:
        where += " AND COALESCE(p.precio_rebajado, p.precio_mayorista, p.precio_unitario) >= ?"
        params.append(precio_min)
    if precio_max is not None:
        where += " AND COALESCE(p.precio_rebajado, p.precio_mayorista, p.precio_unitario) <= ?"
        params.append(precio_max)

    order_sql = "ORDER BY it.item_type, p.nombre_producto"
    if orden == "precio_asc":
        order_sql = "ORDER BY COALESCE(p.precio_rebajado, p.precio_mayorista, p.precio_unitario) ASC"
    elif orden == "precio_desc":
        order_sql = "ORDER BY COALESCE(p.precio_rebajado, p.precio_mayorista, p.precio_unitario) DESC"
    elif orden == "nombre":
        order_sql = "ORDER BY p.nombre_producto"

    conn.execute(
        f"""
        SELECT COUNT(*)
        FROM dim_producto p
        LEFT JOIN categorias c ON c.id_item_type = p.id_item_type
        {where}
        """,
        params,
    )
    total_items = int(conn.fetchone()[0])
    # NOTE: JOIN categorias must be INNER-equivalent via WHERE c.id_item_type IS NOT NULL
    # Count query already uses LEFT JOIN + filter above.
    total_pages = max(1, int(math.ceil(total_items / page_size))) if total_items else 1
    if page > total_pages:
        page = total_pages

    offset = (page - 1) * page_size

    dto_cat_sql = (
        """,
          CAST(COALESCE(c.descuento_pct, 0) AS DOUBLE) AS dto_categoria,
          COALESCE(c.descuento_aplica_a, 'mayorista') AS dto_cat_aplica,
          c.descuento_hasta AS dto_cat_hasta,
          c.descuento_motivo AS dto_cat_motivo,
          c.nombre AS dto_cat_nombre"""
        if _tiene_dto_categoria(conn)
        else """,
          CAST(0 AS DOUBLE) AS dto_categoria,
          'mayorista' AS dto_cat_aplica,
          CAST(NULL AS DATE) AS dto_cat_hasta,
          CAST(NULL AS VARCHAR) AS dto_cat_motivo,
          c.nombre AS dto_cat_nombre"""
    )

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
          p.activo,
          m.nombre AS marca,
          l.nombre AS linea,
          CAST(COALESCE(p.descuento_pct, 0) AS DOUBLE) AS descuento_pct,
          CAST(p.precio_rebajado AS DOUBLE) AS precio_rebajado,
          COALESCE(p.sku, 'GM-' || LPAD(CAST(p.id_producto AS VARCHAR), 6, '0')) AS sku,
          COALESCE(p.descuento_aplica_a, 'mayorista') AS descuento_aplica_a,
          CAST({red_bodegas.sql_stock_zona(almacenes, 'p.id_producto')} AS DOUBLE) AS stock_disponible,
          CAST(COALESCE(p.stock_minimo, COALESCE((
            SELECT al.umbral_minimo FROM alertas_stock al
            WHERE al.id_producto = p.id_producto AND al.activa = true LIMIT 1
          ), 10)) AS DOUBLE) AS stock_minimo,
          p.fecha_rebaja_hasta
          {dto_cat_sql}
        FROM dim_producto p
        JOIN dim_item_type it ON it.id_item_type = p.id_item_type
        LEFT JOIN categorias c ON c.id_item_type = p.id_item_type
        LEFT JOIN marcas m ON m.id_marca = p.id_marca
        LEFT JOIN lineas_producto l ON l.id_linea = p.id_linea
        {where}
        {order_sql}
        LIMIT ? OFFSET ?
        """,
        [*params, page_size, offset],
    )

    rows = conn.fetchall()
    moq_default = obtener_config_int(conn, "MOQ_MAYORISTA", 10)
    id_lista = listas_precio_service.id_lista_cliente(conn, id_cliente)
    zona = _info_zona(red)
    items = []
    for r in rows:
        stock = max(0.0, float(r[15] or 0))
        minimo = float(r[16] if r[16] is not None else 10)
        precio_mayorista = float(r[6] or 0)
        moq = moq_default
        lista_tarifa = None
        if id_lista:
            precio_mayorista, moq, lista_tarifa = listas_precio_service.aplicar_tarifa(
                conn,
                id_cliente=id_cliente,
                id_producto=int(r[0]),
                precio_mayorista=precio_mayorista,
                moq_default=moq_default,
            )
        dto = precios_b2b.mejor_descuento(
            pct_producto=r[11],
            aplica_producto=r[14],
            rebaja_hasta=r[17],
            pct_categoria=r[18],
            aplica_categoria=r[19],
            categoria_hasta=r[20],
            categoria_nombre=r[22],
            categoria_motivo=r[21],
        )
        rebajado_manual = float(r[12]) if r[12] is not None else None
        precio_rebajado = None
        if dto["pct"] > 0 or (rebajado_manual and dto["origen"] == "producto"):
            efectivo = precios_b2b.precio_mayorista_efectivo(
                precio_mayorista,
                pct=dto["pct"],
                aplica_a=dto["aplica_a"],
                precio_rebajado=rebajado_manual,
                origen=dto["origen"],
            )
            if efectivo < precio_mayorista:
                precio_rebajado = efectivo

        item = {
            "id_producto": int(r[0]),
            "nombre_producto": r[1],
            "descripcion": r[2],
            "id_item_type": int(r[3]),
            "categoria": _categoria_es(r[4]),
            "precio_unitario": float(r[5]),
            "imagen_url": _imagen_publica(r[7]),
            "activo": bool(r[8]),
            "marca": r[9],
            "linea": r[10],
            "descuento_pct": dto["pct"],
            "descuento_origen": dto["origen"],
            "descuento_etiqueta": dto["etiqueta"],
            "precio_rebajado": precio_rebajado,
            "sku": r[13],
            "descuento_aplica_a": dto["aplica_a"],
            "stock_disponible": stock,
            "stock_minimo": minimo,
            "estado_stock": _estado_stock(stock, minimo),
            "moq": moq,
            "lista_precio": lista_tarifa,
        }
        if autenticado:
            item["precio_mayorista"] = precio_mayorista
        else:
            item["precio_mayorista"] = None
            item["precio_rebajado"] = None
            item["descuento_pct"] = 0
            item["descuento_origen"] = None
            item["descuento_etiqueta"] = None
            item["precio_login_hint"] = True
            item["precio_etiqueta"] = "Precio público — inicia sesión para ver precio mayorista"
        items.append(item)

    return {
        "items": items,
        "page": page,
        "page_size": page_size,
        "total_items": total_items,
        "total_pages": total_pages,
        **zona,
    }

