"""
services/estado_pedido.py — Máquina de estados del pedido.

borrador → pendiente_pago → pagado → preparando → enviado → entregado
`cancelado` alcanzable desde pendiente_pago, pagado y preparando.
"""

from __future__ import annotations

from typing import Any, Optional

import duckdb

ESTADOS = [
    "borrador",
    "pendiente_pago",
    "pagado",
    "preparando",
    "enviado",
    "entregado",
    "cancelado",
]

TRANSICIONES: dict[str, set[str]] = {
    "borrador": {"pendiente_pago", "cancelado"},
    "pendiente_pago": {"pagado", "cancelado"},
    "pagado": {"preparando", "cancelado"},
    "preparando": {"enviado", "cancelado"},
    "enviado": {"entregado"},
    "entregado": set(),
    "cancelado": set(),
}


def transicion_valida(actual: str, nuevo: str) -> bool:
    return nuevo in TRANSICIONES.get(actual, set())


def cambiar_estado(
    conn: duckdb.DuckDBPyConnection,
    *,
    id_pedido: int,
    nuevo_estado: str,
    id_usuario: Optional[int] = None,
) -> dict[str, Any]:
    """Aplica una transición válida y registra el historial. No abre transacción propia."""
    if nuevo_estado not in ESTADOS:
        raise ValueError(f"Estado desconocido: {nuevo_estado}.")

    row = conn.execute("SELECT estado FROM pedidos WHERE id_pedido = ?", [id_pedido]).fetchone()
    if not row:
        raise ValueError(f"Pedido {id_pedido} no existe.")
    actual = row[0]

    if not transicion_valida(actual, nuevo_estado):
        raise ValueError(f"Transición inválida: {actual} → {nuevo_estado}.")

    conn.execute("UPDATE pedidos SET estado = ? WHERE id_pedido = ?", [nuevo_estado, id_pedido])
    conn.execute(
        """
        INSERT INTO pedido_estados_historial (id_historial, id_pedido, estado_anterior, estado_nuevo, id_usuario)
        VALUES ((SELECT COALESCE(MAX(id_historial), 0) + 1 FROM pedido_estados_historial), ?, ?, ?, ?)
        """,
        [id_pedido, actual, nuevo_estado, id_usuario],
    )
    return {"id_pedido": id_pedido, "estado_anterior": actual, "estado": nuevo_estado}


_CADENA_OPERATIVA = ("pagado", "preparando", "enviado", "entregado")


def avanzar_pedido_hasta(
    conn: duckdb.DuckDBPyConnection,
    id_pedido: int,
    destino: str,
    *,
    id_usuario: Optional[int] = None,
) -> None:
    """Avanza el pedido por la cadena operativa hasta el estado destino (sin saltos inválidos)."""
    if destino not in _CADENA_OPERATIVA:
        return
    while True:
        row = conn.execute("SELECT estado FROM pedidos WHERE id_pedido = ?", [id_pedido]).fetchone()
        if not row:
            return
        actual = row[0]
        if actual == destino:
            return
        if actual in ("cancelado", "borrador", "pendiente_pago"):
            return
        if actual not in _CADENA_OPERATIVA:
            return
        idx_actual = _CADENA_OPERATIVA.index(actual)
        idx_dest = _CADENA_OPERATIVA.index(destino)
        if idx_actual >= idx_dest:
            return
        siguiente = _CADENA_OPERATIVA[idx_actual + 1]
        cambiar_estado(conn, id_pedido=id_pedido, nuevo_estado=siguiente, id_usuario=id_usuario)


def historial_pedido(conn: duckdb.DuckDBPyConnection, id_pedido: int) -> list[dict[str, Any]]:
    from shared.database.connection import table_exists

    if not table_exists(conn, "pedido_estados_historial"):
        return []
    rows = conn.execute(
        """
        SELECT h.id_historial, h.estado_anterior, h.estado_nuevo, h.fecha, u.email
        FROM pedido_estados_historial h
        LEFT JOIN usuarios u ON u.id_usuario = h.id_usuario
        WHERE h.id_pedido = ?
        ORDER BY h.id_historial
        """,
        [id_pedido],
    ).fetchall()
    return [
        {
            "id_historial": int(r[0]),
            "estado_anterior": r[1],
            "estado_nuevo": r[2],
            "fecha": str(r[3]) if r[3] is not None else None,
            "usuario": r[4],
        }
        for r in rows
    ]
