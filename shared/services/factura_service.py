"""
factura_service.py — Creación de facturas de venta desde pedidos pagados.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

import duckdb

from shared.pdf.comprobante_service import siguiente_numero


def _iva_pct(conn: duckdb.DuckDBPyConnection) -> float:
    row = conn.execute("SELECT valor FROM configuracion_sistema WHERE clave = 'IVA_PCT'").fetchone()
    try:
        return float(row[0]) if row else 18.0
    except (TypeError, ValueError):
        return 18.0


def obtener_factura_por_pedido(conn: duckdb.DuckDBPyConnection, id_pedido: int) -> Optional[dict[str, Any]]:
    r = conn.execute(
        """
        SELECT id_factura, numero, id_pedido, id_cliente, fecha, estado,
               CAST(subtotal AS DOUBLE), CAST(impuesto_monto AS DOUBLE), CAST(total AS DOUBLE)
        FROM facturas_venta WHERE id_pedido = ?
        """,
        [id_pedido],
    ).fetchone()
    if not r:
        return None
    return {
        "id_factura": int(r[0]), "numero": r[1], "id_pedido": int(r[2]), "id_cliente": int(r[3]),
        "fecha": str(r[4]) if r[4] else None, "estado": r[5],
        "subtotal": float(r[6]), "impuesto": float(r[7]), "total": float(r[8]),
    }


def _insertar_detalle_desde_pedido(
    conn: duckdb.DuckDBPyConnection, *, id_factura: int, id_pedido: int
) -> int:
    """Copia líneas de pedido_detalle a factura_venta_detalle. Devuelve cantidad insertada."""
    lineas = conn.execute(
        """
        SELECT id_producto, cantidad, CAST(precio_unitario AS DOUBLE), CAST(subtotal AS DOUBLE)
        FROM pedido_detalle WHERE id_pedido = ?
        """,
        [id_pedido],
    ).fetchall()
    if not lineas:
        return 0
    next_id = int(
        conn.execute("SELECT COALESCE(MAX(id_detalle), 0) + 1 FROM factura_venta_detalle").fetchone()[0]
    )
    for ln in lineas:
        conn.execute(
            """
            INSERT INTO factura_venta_detalle (id_detalle, id_factura, id_producto, cantidad, precio_unitario, subtotal)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            [next_id, id_factura, int(ln[0]), int(ln[1]), float(ln[2]), float(ln[3])],
        )
        next_id += 1
    return len(lineas)


def asegurar_detalle_factura(conn: duckdb.DuckDBPyConnection, id_factura: int) -> None:
    """Rellena factura_venta_detalle si la cabecera existe sin líneas (datos legacy)."""
    n = int(
        conn.execute(
            "SELECT COUNT(*) FROM factura_venta_detalle WHERE id_factura = ?", [id_factura]
        ).fetchone()[0]
    )
    if n > 0:
        return
    row = conn.execute(
        "SELECT id_pedido FROM facturas_venta WHERE id_factura = ?", [id_factura]
    ).fetchone()
    if row:
        _insertar_detalle_desde_pedido(conn, id_factura=id_factura, id_pedido=int(row[0]))


def crear_factura_desde_pedido(
    conn: duckdb.DuckDBPyConnection, *, id_pedido: int
) -> dict[str, Any]:
    """Crea factura + detalle desde un pedido pagado. Idempotente por id_pedido."""
    existente = obtener_factura_por_pedido(conn, id_pedido)
    if existente:
        asegurar_detalle_factura(conn, int(existente["id_factura"]))
        return existente

    pedido = conn.execute(
        """
        SELECT id_cliente, estado, CAST(COALESCE(subtotal,0) AS DOUBLE),
               CAST(COALESCE(impuesto_monto,0) AS DOUBLE), CAST(COALESCE(total,0) AS DOUBLE), numero
        FROM pedidos WHERE id_pedido = ?
        """,
        [id_pedido],
    ).fetchone()
    if not pedido:
        raise ValueError(f"Pedido {id_pedido} no existe.")
    if pedido[1] not in ("pagado", "preparando", "enviado", "entregado"):
        raise ValueError(f"El pedido debe estar pagado para facturar (estado: {pedido[1]}).")

    id_cliente = int(pedido[0])
    subtotal, impuesto, total = float(pedido[2]), float(pedido[3]), float(pedido[4])
    if subtotal == 0:
        iva = _iva_pct(conn)
        subtotal = round(total / (1 + iva / 100), 2) if total else 0
        impuesto = round(total - subtotal, 2)

    # Numeración unificada con la serie de comprobantes (misma que usan los PDF).
    _, numero = siguiente_numero(conn, "factura")
    n = int(conn.execute("SELECT COALESCE(MAX(id_factura), 0) + 1 FROM facturas_venta").fetchone()[0])

    conn.execute(
        """
        INSERT INTO facturas_venta (id_factura, numero, id_pedido, id_cliente, fecha, subtotal, impuesto_monto, total, estado)
        VALUES (?, ?, ?, ?, current_timestamp, ?, ?, ?, 'emitida')
        """,
        [n, numero, id_pedido, id_cliente, subtotal, impuesto, total],
    )

    _insertar_detalle_desde_pedido(conn, id_factura=n, id_pedido=id_pedido)

    conn.execute(
        "UPDATE pagos SET id_factura = ? WHERE id_pedido = ? AND id_factura IS NULL",
        [n, id_pedido],
    )
    return obtener_factura_por_pedido(conn, id_pedido)
