"""wishlist_service.py — Favoritos B2B del cliente autenticado (productos y paquetes)."""
from __future__ import annotations

from typing import Any, Optional

import duckdb

from shared.services import precios_b2b, red_bodegas


def _ensure_table(conn: duckdb.DuckDBPyConnection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS wishlist (
          id_wishlist BIGINT PRIMARY KEY,
          id_usuario BIGINT NOT NULL,
          id_producto BIGINT NOT NULL,
          fecha TIMESTAMP DEFAULT current_timestamp,
          UNIQUE(id_usuario, id_producto)
        )
        """
    )


def _ensure_table_catalogos(conn: duckdb.DuckDBPyConnection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS wishlist_catalogos (
          id_wishlist BIGINT PRIMARY KEY,
          id_usuario BIGINT NOT NULL,
          id_catalogo BIGINT NOT NULL,
          fecha TIMESTAMP DEFAULT current_timestamp,
          UNIQUE(id_usuario, id_catalogo)
        )
        """
    )


def listar(conn: duckdb.DuckDBPyConnection, *, id_usuario: int, autenticado: bool = True) -> list[dict[str, Any]]:
    _ensure_table(conn)
    rows = conn.execute(
        """
        SELECT p.id_producto, p.nombre_producto, p.descripcion, p.id_item_type,
               it.item_type, p.precio_unitario, p.precio_mayorista, p.imagen_url,
               COALESCE(p.activo, true), p.sku, COALESCE(p.descuento_pct, 0),
               p.precio_rebajado, m.nombre, l.nombre, w.fecha
        FROM wishlist w
        JOIN dim_producto p ON p.id_producto = w.id_producto
        LEFT JOIN dim_item_type it ON it.id_item_type = p.id_item_type
        LEFT JOIN marcas m ON m.id_marca = p.id_marca
        LEFT JOIN lineas_producto l ON l.id_linea = p.id_linea
        WHERE w.id_usuario = ? AND COALESCE(p.activo, true) = true
        ORDER BY w.fecha DESC
        """,
        [id_usuario],
    ).fetchall()
    out = []
    for r in rows:
        item = {
            "id_producto": int(r[0]),
            "nombre_producto": r[1],
            "descripcion": r[2],
            "id_item_type": int(r[3]) if r[3] is not None else None,
            "categoria": r[4],
            "precio_unitario": float(r[5] or 0),
            "precio_mayorista": float(r[6]) if r[6] is not None else None,
            "imagen_url": f"/media/{r[7]}" if r[7] and not str(r[7]).startswith("/") else r[7],
            "activo": bool(r[8]) if r[8] is not None else True,
            "sku": r[9],
            "descuento_pct": float(r[10] or 0),
            "precio_rebajado": float(r[11]) if r[11] is not None else None,
            "marca": r[12],
            "linea": r[13],
            "fecha_wishlist": str(r[14])[:19] if r[14] else None,
        }
        if not autenticado:
            item["precio_mayorista"] = None
        out.append(item)
    return out


def agregar(conn: duckdb.DuckDBPyConnection, *, id_usuario: int, id_producto: int) -> dict[str, Any]:
    _ensure_table(conn)
    existe = conn.execute(
        "SELECT 1 FROM dim_producto WHERE id_producto = ? AND COALESCE(activo, true) = true",
        [id_producto],
    ).fetchone()
    if not existe:
        raise ValueError("Producto no encontrado.")
    conn.execute(
        """
        INSERT INTO wishlist (id_wishlist, id_usuario, id_producto)
        SELECT COALESCE((SELECT MAX(id_wishlist) FROM wishlist), 0) + 1, ?, ?
        WHERE NOT EXISTS (
          SELECT 1 FROM wishlist WHERE id_usuario = ? AND id_producto = ?
        )
        """,
        [id_usuario, id_producto, id_usuario, id_producto],
    )
    return {"ok": True, "id_producto": id_producto}


def quitar(conn: duckdb.DuckDBPyConnection, *, id_usuario: int, id_producto: int) -> dict[str, Any]:
    _ensure_table(conn)
    conn.execute(
        "DELETE FROM wishlist WHERE id_usuario = ? AND id_producto = ?",
        [id_usuario, id_producto],
    )
    return {"ok": True, "id_producto": id_producto}


# --------------------------------------------------------------------------
# Favoritos de paquetes
# --------------------------------------------------------------------------

def listar_paquetes(
    conn: duckdb.DuckDBPyConnection, *, id_usuario: int, id_cliente: Optional[int] = None
) -> list[dict[str, Any]]:
    _ensure_table_catalogos(conn)
    red = red_bodegas.red_de_cliente(conn, id_cliente=id_cliente)
    almacenes = list(red.get("almacenes") or [])
    rows = conn.execute(
        f"""
        SELECT c.id_catalogo, c.nombre, c.descripcion, c.id_item_type, it.item_type,
               (SELECT COUNT(*)
                  FROM catalogo_detalle d JOIN dim_producto p ON p.id_producto = d.id_producto
                 WHERE d.id_catalogo = c.id_catalogo AND COALESCE(p.activo, true) = true) AS n_productos,
               (SELECT p2.imagen_url
                  FROM catalogo_detalle d2 JOIN dim_producto p2 ON p2.id_producto = d2.id_producto
                 WHERE d2.id_catalogo = c.id_catalogo AND COALESCE(p2.imagen_url, '') <> ''
                 ORDER BY p2.nombre_producto LIMIT 1) AS imagen_url,
               ROUND(CAST(COALESCE((
                 SELECT SUM(d3.cantidad_base * COALESCE(d3.precio_unitario, p3.precio_mayorista, 0))
                 FROM catalogo_detalle d3 JOIN dim_producto p3 ON p3.id_producto = d3.id_producto
                 WHERE d3.id_catalogo = c.id_catalogo
               ), 0) AS DOUBLE), 2) AS precio_total_base,
               w.fecha,
               (SELECT COUNT(*)
                  FROM catalogo_detalle d4 JOIN dim_producto p4 ON p4.id_producto = d4.id_producto
                 WHERE d4.id_catalogo = c.id_catalogo AND COALESCE(p4.activo, true) = true
                       AND {red_bodegas.sql_stock_zona(almacenes, 'd4.id_producto')} <= 0) AS n_agotados
        FROM wishlist_catalogos w
        JOIN catalogos c ON c.id_catalogo = w.id_catalogo
        LEFT JOIN dim_item_type it ON it.id_item_type = c.id_item_type
        WHERE w.id_usuario = ? AND COALESCE(c.activo, true) = true
        ORDER BY w.fecha DESC
        """,
        [id_usuario],
    ).fetchall()

    salida = []
    for r in rows:
        id_catalogo = int(r[0])
        base = float(r[7] or 0)
        dto = precios_b2b.descuento_paquete(conn, id_catalogo)
        salida.append(
            {
                "id_catalogo": id_catalogo,
                "nombre": r[1],
                "descripcion": r[2],
                "id_item_type": int(r[3]) if r[3] is not None else None,
                "categoria": r[4],
                "n_productos": int(r[5] or 0),
                "imagen_url": f"/media/{r[6]}" if r[6] and not str(r[6]).startswith(("/", "http")) else r[6],
                "precio_total_base": base,
                "descuento_pct": dto["pct"],
                "descuento_motivo": dto["motivo"],
                "precio_total_final": precios_b2b.precio_con_descuento(base, dto["pct"]),
                "fecha_wishlist": str(r[8])[:19] if r[8] else None,
                "n_agotados": int(r[9] or 0),
                "zona_label": red.get("macro_label"),
            }
        )
    return salida


def agregar_paquete(
    conn: duckdb.DuckDBPyConnection, *, id_usuario: int, id_catalogo: int
) -> dict[str, Any]:
    _ensure_table_catalogos(conn)
    existe = conn.execute(
        "SELECT 1 FROM catalogos WHERE id_catalogo = ? AND COALESCE(activo, true) = true",
        [id_catalogo],
    ).fetchone()
    if not existe:
        raise ValueError("Paquete no encontrado.")
    conn.execute(
        """
        INSERT INTO wishlist_catalogos (id_wishlist, id_usuario, id_catalogo)
        SELECT COALESCE((SELECT MAX(id_wishlist) FROM wishlist_catalogos), 0) + 1, ?, ?
        WHERE NOT EXISTS (
          SELECT 1 FROM wishlist_catalogos WHERE id_usuario = ? AND id_catalogo = ?
        )
        """,
        [id_usuario, id_catalogo, id_usuario, id_catalogo],
    )
    return {"ok": True, "id_catalogo": id_catalogo}


def quitar_paquete(
    conn: duckdb.DuckDBPyConnection, *, id_usuario: int, id_catalogo: int
) -> dict[str, Any]:
    _ensure_table_catalogos(conn)
    conn.execute(
        "DELETE FROM wishlist_catalogos WHERE id_usuario = ? AND id_catalogo = ?",
        [id_usuario, id_catalogo],
    )
    return {"ok": True, "id_catalogo": id_catalogo}


def ids_paquetes(conn: duckdb.DuckDBPyConnection, *, id_usuario: int) -> list[int]:
    _ensure_table_catalogos(conn)
    return [
        int(r[0])
        for r in conn.execute(
            "SELECT id_catalogo FROM wishlist_catalogos WHERE id_usuario = ?", [id_usuario]
        ).fetchall()
    ]
