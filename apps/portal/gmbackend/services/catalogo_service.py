"""
services/catalogo_service.py — Catálogos/paquetes configurables del portal B2B.

El precio de referencia del paquete usa el mejor descuento aplicable a cada
producto (propio o de su categoría) y, encima, el descuento del paquete. El
stock mostrado es el de la macro-zona del cliente: un paquete puede aparecer
completo en Américas y con líneas agotadas en APAC.
"""

from __future__ import annotations

from typing import Any, Optional

import duckdb

from shared.services import precios_b2b, red_bodegas

from .producto_service import _imagen_publica


def _almacenes(conn: duckdb.DuckDBPyConnection, id_cliente: Optional[int]) -> list[int]:
    red = red_bodegas.red_de_cliente(conn, id_cliente=id_cliente)
    return list(red.get("almacenes") or [])


def _precio_linea(
    conn: duckdb.DuckDBPyConnection,
    *,
    precio_base: float,
    id_item_type: Optional[int],
    descuento_producto: float,
    aplica_producto: Any,
    rebaja_hasta: Any,
    precio_rebajado: Optional[float],
    descuento_paquete: float,
) -> float:
    dto = precios_b2b.resolver_descuento(
        conn,
        id_item_type=id_item_type,
        descuento_producto=descuento_producto,
        aplica_producto=aplica_producto,
        rebaja_hasta=rebaja_hasta,
    )
    con_dto = precios_b2b.precio_mayorista_efectivo(
        precio_base,
        pct=dto["pct"],
        aplica_a=dto["aplica_a"],
        precio_rebajado=precio_rebajado,
        origen=dto["origen"],
    )
    return precios_b2b.precio_con_descuento(con_dto, descuento_paquete)


def listar_catalogos(
    conn: duckdb.DuckDBPyConnection, *, id_cliente: Optional[int] = None
) -> list[dict[str, Any]]:
    almacenes = _almacenes(conn, id_cliente)
    stock_sql = red_bodegas.sql_stock_zona(almacenes, "d.id_producto")

    rows = conn.execute(
        f"""
        SELECT c.id_catalogo, c.nombre, c.descripcion, c.id_item_type,
               it.item_type,
               (SELECT COUNT(*)
                  FROM catalogo_detalle d JOIN dim_producto p ON p.id_producto = d.id_producto
                 WHERE d.id_catalogo = c.id_catalogo AND COALESCE(p.activo, true) = true) AS n_productos,
               (SELECT p2.imagen_url
                  FROM catalogo_detalle d2 JOIN dim_producto p2 ON p2.id_producto = d2.id_producto
                 WHERE d2.id_catalogo = c.id_catalogo AND COALESCE(p2.activo, true) = true
                       AND COALESCE(p2.imagen_url, '') <> ''
                 ORDER BY p2.nombre_producto LIMIT 1) AS imagen_url,
               (SELECT LIST(imagen_url)
                  FROM (SELECT p2.imagen_url AS imagen_url
                          FROM catalogo_detalle d2 JOIN dim_producto p2 ON p2.id_producto = d2.id_producto
                         WHERE d2.id_catalogo = c.id_catalogo AND COALESCE(p2.activo, true) = true
                               AND COALESCE(p2.imagen_url, '') <> ''
                         ORDER BY p2.nombre_producto LIMIT 4)) AS imagenes,
               ROUND(CAST(COALESCE(SUM(d.cantidad_base * COALESCE(d.precio_unitario, p.precio_mayorista, 0)), 0) AS DOUBLE), 2) AS precio_total,
               CAST(COALESCE(c.descuento_pct, 0) AS DOUBLE) AS descuento_pct,
               c.descuento_hasta, c.descuento_motivo,
               (SELECT COUNT(*)
                  FROM catalogo_detalle d3 JOIN dim_producto p3 ON p3.id_producto = d3.id_producto
                 WHERE d3.id_catalogo = c.id_catalogo AND COALESCE(p3.activo, true) = true
                       AND {red_bodegas.sql_stock_zona(almacenes, 'd3.id_producto')} <= 0) AS n_agotados
        FROM catalogos c
        LEFT JOIN dim_item_type it ON it.id_item_type = c.id_item_type
        LEFT JOIN catalogo_detalle d ON d.id_catalogo = c.id_catalogo
        LEFT JOIN dim_producto p ON p.id_producto = d.id_producto
        WHERE COALESCE(c.activo, true) = true
        GROUP BY c.id_catalogo, c.nombre, c.descripcion, c.id_item_type, it.item_type,
                 c.descuento_pct, c.descuento_hasta, c.descuento_motivo
        ORDER BY c.nombre
        """,
    ).fetchall()

    salida = []
    for r in rows:
        id_catalogo = int(r[0])
        base = float(r[8])
        dto = precios_b2b.descuento_paquete(conn, id_catalogo)
        salida.append(
            {
                "id_catalogo": id_catalogo,
                "nombre": r[1],
                "descripcion": r[2],
                "id_item_type": int(r[3]) if r[3] is not None else None,
                "categoria": r[4],
                "n_productos": int(r[5]),
                "imagen_url": _imagen_publica(r[6]),
                "imagenes": [_imagen_publica(x) for x in (r[7] or [])],
                "precio_total_base": base,
                "descuento_pct": dto["pct"],
                "descuento_motivo": dto["motivo"],
                "descuento_hasta": str(r[10]) if r[10] else None,
                "precio_total_final": precios_b2b.precio_con_descuento(base, dto["pct"]),
                "n_agotados": int(r[12] or 0),
            }
        )
    return salida


def obtener_catalogo(
    conn: duckdb.DuckDBPyConnection, id_catalogo: int, *, id_cliente: Optional[int] = None
) -> Optional[dict[str, Any]]:
    red = red_bodegas.red_de_cliente(conn, id_cliente=id_cliente)
    almacenes = list(red.get("almacenes") or [])

    cat = conn.execute(
        """
        SELECT c.id_catalogo, c.nombre, c.descripcion, c.id_item_type, it.item_type,
               ROUND(CAST(COALESCE(SUM(d.cantidad_base * COALESCE(d.precio_unitario, p.precio_mayorista, 0)), 0) AS DOUBLE), 2)
        FROM catalogos c
        LEFT JOIN dim_item_type it ON it.id_item_type = c.id_item_type
        LEFT JOIN catalogo_detalle d ON d.id_catalogo = c.id_catalogo
        LEFT JOIN dim_producto p ON p.id_producto = d.id_producto
        WHERE c.id_catalogo = ? AND COALESCE(c.activo, true) = true
        GROUP BY c.id_catalogo, c.nombre, c.descripcion, c.id_item_type, it.item_type
        """,
        [id_catalogo],
    ).fetchone()
    if not cat:
        return None

    dto_paquete = precios_b2b.descuento_paquete(conn, id_catalogo)

    productos = conn.execute(
        f"""
        SELECT d.id_producto, p.nombre_producto, d.cantidad_base,
               p.imagen_url,
               ROUND(CAST(COALESCE(d.precio_unitario, p.precio_mayorista, 0) AS DOUBLE), 2) AS precio_mayorista,
               ROUND(CAST(COALESCE(p.precio_unitario, 0) AS DOUBLE), 2) AS precio_retail,
               CAST({red_bodegas.sql_stock_zona(almacenes, 'd.id_producto')} AS DOUBLE) AS stock_disponible,
               COALESCE(p.activo, true) AS activo,
               p.id_item_type,
               CAST(COALESCE(p.descuento_pct, 0) AS DOUBLE),
               COALESCE(p.descuento_aplica_a, 'mayorista'),
               p.fecha_rebaja_hasta,
               CAST(p.precio_rebajado AS DOUBLE)
        FROM catalogo_detalle d
        JOIN dim_producto p ON p.id_producto = d.id_producto
        WHERE d.id_catalogo = ?
        ORDER BY p.nombre_producto
        """,
        [id_catalogo],
    ).fetchall()

    detalles = []
    total_final = 0.0
    for pr in productos:
        precio_base = float(pr[4])
        precio_final = _precio_linea(
            conn,
            precio_base=precio_base,
            id_item_type=int(pr[8]) if pr[8] is not None else None,
            descuento_producto=float(pr[9] or 0),
            aplica_producto=pr[10],
            rebaja_hasta=pr[11],
            precio_rebajado=float(pr[12]) if pr[12] is not None else None,
            descuento_paquete=dto_paquete["pct"],
        )
        cantidad_base = int(pr[2])
        stock = max(0.0, float(pr[6]))
        total_final += precio_final * cantidad_base
        detalles.append(
            {
                "id_producto": int(pr[0]),
                "nombre_producto": pr[1],
                "cantidad_base": cantidad_base,
                "imagen_url": _imagen_publica(pr[3]),
                "precio_mayorista": precio_base,
                "precio_final": precio_final,
                "precio_retail": float(pr[5]),
                "stock_disponible": stock,
                "agotado": stock <= 0,
                "activo": bool(pr[7]),
            }
        )

    return {
        "id_catalogo": int(cat[0]),
        "nombre": cat[1],
        "descripcion": cat[2],
        "id_item_type": int(cat[3]) if cat[3] is not None else None,
        "categoria": cat[4],
        "precio_total_base": float(cat[5]),
        "precio_total_final": round(total_final, 2),
        "descuento_pct": dto_paquete["pct"],
        "descuento_motivo": dto_paquete["motivo"],
        "descuento_hasta": str(dto_paquete["hasta"]) if dto_paquete["hasta"] else None,
        "zona_entrega": red.get("macro_zona"),
        "zona_label": red.get("macro_label"),
        "bodega_asignada": red.get("bodega_principal"),
        "productos": detalles,
    }
