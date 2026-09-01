"""
listas_precio_service.py — Tarifas B2B por lista de precios.

Cada cliente pertenece a un grupo con una lista asignada. La lista define
el precio por producto. El umbral mayorista (MOQ) lo controla MOQ_MAYORISTA
en configuración del sistema (no la lista).
"""

from __future__ import annotations

from typing import Any, Optional

import duckdb

from shared.database.connection import table_exists


def _lista_por_nombre(conn: duckdb.DuckDBPyConnection, nombre: str) -> Optional[int]:
    if not table_exists(conn, "listas_precios"):
        return None
    row = conn.execute(
        "SELECT id_lista FROM listas_precios WHERE lower(nombre) = lower(?) LIMIT 1",
        [nombre],
    ).fetchone()
    return int(row[0]) if row else None


def id_lista_cliente(
    conn: duckdb.DuckDBPyConnection, id_cliente: Optional[int]
) -> Optional[int]:
    """Lista de precios del cliente (grupo B2B) o lista por defecto si no hay sesión."""
    if not table_exists(conn, "listas_precios"):
        return None
    if id_cliente is None:
        return _lista_por_nombre(conn, "Público")
    if table_exists(conn, "cliente_grupo") and table_exists(conn, "grupos_cliente"):
        row = conn.execute(
            """
            SELECT g.id_lista
            FROM cliente_grupo cg
            JOIN grupos_cliente g ON g.id_grupo = cg.id_grupo
            WHERE cg.id_cliente = ? AND g.id_lista IS NOT NULL
            LIMIT 1
            """,
            [int(id_cliente)],
        ).fetchone()
        if row and row[0] is not None:
            return int(row[0])
    return _lista_por_nombre(conn, "Público")


def info_lista_cliente(
    conn: duckdb.DuckDBPyConnection, id_cliente: Optional[int]
) -> dict[str, Any]:
    id_lista = id_lista_cliente(conn, id_cliente)
    if not id_lista:
        return {"id_lista": None, "nombre": None, "grupo": None}
    row = conn.execute(
        """
        SELECT lp.nombre, g.nombre
        FROM listas_precios lp
        LEFT JOIN grupos_cliente g ON g.id_lista = lp.id_lista
        LEFT JOIN cliente_grupo cg ON cg.id_grupo = g.id_grupo AND cg.id_cliente = ?
        WHERE lp.id_lista = ?
        LIMIT 1
        """,
        [int(id_cliente or 0), id_lista],
    ).fetchone()
    return {
        "id_lista": id_lista,
        "nombre": row[0] if row else None,
        "grupo": row[1] if row else None,
    }


def tarifa_producto(
    conn: duckdb.DuckDBPyConnection,
    id_lista: int,
    id_producto: int,
) -> Optional[dict[str, Any]]:
    if not table_exists(conn, "lista_precio_detalle"):
        return None
    row = conn.execute(
        """
        SELECT CAST(d.precio AS DOUBLE), lp.nombre
        FROM lista_precio_detalle d
        JOIN listas_precios lp ON lp.id_lista = d.id_lista
        WHERE d.id_lista = ? AND d.id_producto = ?
        """,
        [int(id_lista), int(id_producto)],
    ).fetchone()
    if not row:
        return None
    return {
        "precio": float(row[0]),
        "lista": row[1],
    }


def aplicar_tarifa(
    conn: duckdb.DuckDBPyConnection,
    *,
    id_cliente: Optional[int],
    id_producto: int,
    precio_mayorista: float,
    moq_default: int,
) -> tuple[float, int, Optional[str]]:
    """Devuelve (precio_mayorista_efectivo, moq, nombre_lista).

    La lista solo sustituye el precio mayorista del catálogo. El MOQ siempre
    proviene de moq_default (configuración MOQ_MAYORISTA).
    """
    moq = max(1, int(moq_default or 10))
    id_lista = id_lista_cliente(conn, id_cliente)
    if not id_lista:
        return precio_mayorista, moq, None
    tarifa = tarifa_producto(conn, id_lista, id_producto)
    if not tarifa:
        return precio_mayorista, moq, None
    return tarifa["precio"], moq, tarifa["lista"]
