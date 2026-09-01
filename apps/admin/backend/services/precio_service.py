"""
services/precio_service.py — Listas de precios y detalle por producto.
"""

from __future__ import annotations

from typing import Any

import duckdb


def listar_listas(conn: duckdb.DuckDBPyConnection) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT lp.id_lista, lp.nombre, lp.id_moneda, m.codigo, lp.activo,
               (SELECT COUNT(*) FROM lista_precio_detalle d WHERE d.id_lista = lp.id_lista) AS n_precios
        FROM listas_precios lp
        LEFT JOIN monedas m ON m.id_moneda = lp.id_moneda
        ORDER BY lp.id_lista
        """
    ).fetchall()
    return [
        {
            "id_lista": int(r[0]),
            "nombre": r[1],
            "id_moneda": int(r[2]) if r[2] is not None else None,
            "moneda": r[3],
            "activo": bool(r[4]),
            "n_precios": int(r[5]),
        }
        for r in rows
    ]


def listar_precios_lista(
    conn: duckdb.DuckDBPyConnection,
    id_lista: int,
    *,
    q: str | None = None,
) -> list[dict[str, Any]]:
    params: list[Any] = [id_lista]
    where = "WHERE d.id_lista = ?"
    if q:
        where += " AND (lower(p.nombre_producto) LIKE ? OR lower(COALESCE(p.sku, '')) LIKE ?)"
        like = f"%{q.lower()}%"
        params.extend([like, like])
    rows = conn.execute(
        f"""
        SELECT d.id_detalle, d.id_producto, p.nombre_producto, COALESCE(p.sku, ''),
               CAST(d.precio AS DOUBLE), d.cantidad_minima
        FROM lista_precio_detalle d
        JOIN dim_producto p ON p.id_producto = d.id_producto
        {where}
        ORDER BY p.nombre_producto
        """,
        params,
    ).fetchall()
    return [
        {
            "id_detalle": int(r[0]),
            "id_producto": int(r[1]),
            "producto": r[2],
            "sku": r[3] or None,
            "precio": float(r[4]),
            "cantidad_minima": int(r[5]),
        }
        for r in rows
    ]


def listar_precios_producto(conn: duckdb.DuckDBPyConnection, id_producto: int) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT d.id_detalle, d.id_lista, lp.nombre, d.id_producto, CAST(d.precio AS DOUBLE), d.cantidad_minima
        FROM lista_precio_detalle d
        JOIN listas_precios lp ON lp.id_lista = d.id_lista
        WHERE d.id_producto = ?
        ORDER BY d.id_lista
        """,
        [id_producto],
    ).fetchall()
    return [
        {
            "id_detalle": int(r[0]),
            "id_lista": int(r[1]),
            "lista": r[2],
            "id_producto": int(r[3]),
            "precio": float(r[4]),
            "cantidad_minima": int(r[5]),
        }
        for r in rows
    ]


def fijar_precio(
    conn: duckdb.DuckDBPyConnection,
    *,
    id_lista: int,
    id_producto: int,
    precio: float,
    cantidad_minima: int = 1,
) -> dict[str, Any]:
    lista = conn.execute("SELECT 1 FROM listas_precios WHERE id_lista = ?", [id_lista]).fetchone()
    if not lista:
        raise ValueError(f"No existe la lista de precios {id_lista}.")
    producto = conn.execute("SELECT 1 FROM dim_producto WHERE id_producto = ?", [id_producto]).fetchone()
    if not producto:
        raise ValueError(f"No existe el producto {id_producto}.")

    existente = conn.execute(
        "SELECT id_detalle FROM lista_precio_detalle WHERE id_lista = ? AND id_producto = ?",
        [id_lista, id_producto],
    ).fetchone()
    if existente:
        conn.execute(
            "UPDATE lista_precio_detalle SET precio = ?, cantidad_minima = ? WHERE id_detalle = ?",
            [precio, cantidad_minima, int(existente[0])],
        )
        id_detalle = int(existente[0])
    else:
        conn.execute(
            """
            INSERT INTO lista_precio_detalle (id_detalle, id_lista, id_producto, precio, cantidad_minima)
            VALUES ((SELECT COALESCE(MAX(id_detalle), 0) + 1 FROM lista_precio_detalle), ?, ?, ?, ?)
            RETURNING id_detalle
            """,
            [id_lista, id_producto, precio, cantidad_minima],
        )
        id_detalle = int(conn.fetchone()[0])

    return {
        "id_detalle": id_detalle,
        "id_lista": id_lista,
        "id_producto": id_producto,
        "precio": precio,
        "cantidad_minima": cantidad_minima,
    }


def eliminar_precio(conn: duckdb.DuckDBPyConnection, id_detalle: int) -> bool:
    existe = conn.execute(
        "SELECT 1 FROM lista_precio_detalle WHERE id_detalle = ?", [id_detalle]
    ).fetchone()
    if not existe:
        return False
    conn.execute("DELETE FROM lista_precio_detalle WHERE id_detalle = ?", [id_detalle])
    return True
