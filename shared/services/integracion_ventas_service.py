"""
integracion_ventas_service.py — Pedidos pagados → fact_ventas (idempotente por order_id).

Cada línea de pedido genera un order_id único:
  10_000_000_000 + id_pedido * 1000 + id_detalle
para no colisionar con order_id del parquet histórico (rango ~10⁹–10¹⁰).
"""

from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Any, Optional

import duckdb

from shared.database.connection import table_exists

logger = logging.getLogger(__name__)

ORDER_ID_BASE = 91_000_000_000_000  # 91e12 — evita colisión con parquet (~10e9) y generador sintético (50e12, y las históricas ~90e12)
ESTADOS_INTEGRABLES = ("pagado", "preparando", "enviado", "entregado")


def order_id_linea(id_pedido: int, id_detalle: int) -> int:
    return ORDER_ID_BASE + id_pedido * 1000 + int(id_detalle)


def _siguiente_id_venta(conn: duckdb.DuckDBPyConnection) -> int:
    row = conn.execute("SELECT COALESCE(MAX(id_venta), 0) + 1 FROM fact_ventas").fetchone()
    return int(row[0])


def integrar_pedido(
    conn: duckdb.DuckDBPyConnection,
    *,
    id_pedido: int,
) -> dict[str, Any]:
    """Integra las líneas de un pedido pagado a fact_ventas. Idempotente por order_id."""
    if not table_exists(conn, "fact_ventas"):
        return {"id_pedido": id_pedido, "insertadas": 0, "omitidas": 0, "motivo": "sin_fact_ventas"}

    pedido = conn.execute(
        """
        SELECT p.estado, p.fecha_pedido, p.id_country, p.id_channel, p.id_priority
        FROM pedidos p WHERE p.id_pedido = ?
        """,
        [id_pedido],
    ).fetchone()
    if not pedido:
        raise ValueError(f"Pedido {id_pedido} no encontrado.")
    if pedido[0] not in ESTADOS_INTEGRABLES:
        raise ValueError(f"Pedido {id_pedido} no integrable (estado: {pedido[0]}).")

    fecha_pedido = pedido[1]
    if hasattr(fecha_pedido, "date"):
        order_date = fecha_pedido.date()
    elif fecha_pedido:
        order_date = date.fromisoformat(str(fecha_pedido)[:10])
    else:
        order_date = date.today()
    ship_date = order_date + timedelta(days=7)

    id_country = int(pedido[2])
    id_channel = int(pedido[3])
    id_priority = int(pedido[4])
    id_region_row = conn.execute(
        "SELECT id_region FROM dim_country WHERE id_country = ?", [id_country]
    ).fetchone()
    id_region = int(id_region_row[0]) if id_region_row else 1

    lineas = conn.execute(
        """
        SELECT d.id_detalle, d.id_producto, d.cantidad,
               CAST(d.precio_unitario AS DOUBLE), CAST(d.subtotal AS DOUBLE),
               CAST(COALESCE(d.costo_unitario, 0) AS DOUBLE), p.id_item_type
        FROM pedido_detalle d
        JOIN dim_producto p ON p.id_producto = d.id_producto
        WHERE d.id_pedido = ?
        ORDER BY d.id_detalle
        """,
        [id_pedido],
    ).fetchall()

    insertadas = 0
    omitidas = 0
    for ln in lineas:
        id_detalle, id_producto = int(ln[0]), int(ln[1])
        cantidad = int(ln[2])
        precio_u, subtotal, costo_u = float(ln[3]), float(ln[4]), float(ln[5])
        id_item_type = int(ln[6])
        oid = order_id_linea(id_pedido, id_detalle)

        # Idempotencia: si el order_id ya existe (portal o histórico), la línea
        # ya está integrada y se omite.
        existe = conn.execute(
            "SELECT 1 FROM fact_ventas WHERE order_id = ?", [oid]
        ).fetchone()
        if existe:
            omitidas += 1
            continue

        # Costo real de adquisición (última compra del producto) si existe.
        # El costo del detalle proviene del tipo ETL (alineado al precio histórico,
        # no al precio B2B), por eso la jerarquía aplica siempre.
        compra = None
        if table_exists(conn, "fact_compras"):
            compra = conn.execute(
                "SELECT costo FROM fact_compras WHERE id_producto = ? ORDER BY fecha DESC LIMIT 1",
                [id_producto],
            ).fetchone()
        if compra and compra[0] and float(compra[0]) > 0:
            costo_u = float(compra[0])
        else:
            # Sin compra registrada: conserva el margen relativo del tipo ETL
            # (unit_cost/unit_price) aplicado al precio B2B, evitando costos
            # del dataset histórico que no corresponden a precios del portal.
            tipo = conn.execute(
                "SELECT unit_cost, unit_price FROM dim_item_type WHERE id_item_type = ?",
                [id_item_type],
            ).fetchone()
            if tipo and tipo[1] and float(tipo[1]) > 0 and tipo[0] and float(tipo[0]) > 0:
                costo_u = round(precio_u * (float(tipo[0]) / float(tipo[1])), 4)
            elif costo_u > 0:
                costo_u = costo_u  # fallback: costo del detalle (ETL del tipo)
            else:
                costo_u = 0.0

        total_cost = round(cantidad * costo_u, 2)
        total_profit = round(subtotal - total_cost, 2)
        id_venta = _siguiente_id_venta(conn)

        conn.execute(
            """
            INSERT INTO fact_ventas (
              id_venta, order_id, id_region, id_country, id_item_type, id_channel, id_priority,
              order_date, ship_date, units_sold, unit_price, unit_cost,
              total_revenue, total_cost, total_profit, id_producto, origen
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'portal')
            """,
            [
                id_venta, oid, id_region, id_country, id_item_type, id_channel, id_priority,
                order_date, ship_date, cantidad, precio_u, costo_u,
                subtotal, total_cost, total_profit, id_producto,
            ],
        )
        insertadas += 1

    logger.info("Integración pedido %s: +%s líneas, %s omitidas", id_pedido, insertadas, omitidas)
    return {"id_pedido": id_pedido, "insertadas": insertadas, "omitidas": omitidas}


def reintegrar_pedidos_pendientes(conn: duckdb.DuckDBPyConnection) -> dict[str, Any]:
    """Reintegra todos los pedidos pagados que aún no están completamente en fact_ventas."""
    if not table_exists(conn, "pedidos") or not table_exists(conn, "fact_ventas"):
        return {"procesados": 0, "insertadas": 0, "omitidas": 0, "detalle": []}

    ids = conn.execute(
        f"""
        SELECT id_pedido FROM pedidos
        WHERE estado IN ({','.join('?' * len(ESTADOS_INTEGRABLES))})
        ORDER BY id_pedido
        """,
        list(ESTADOS_INTEGRABLES),
    ).fetchall()

    total_ins, total_omit, detalle = 0, 0, []
    for (id_pedido,) in ids:
        try:
            r = integrar_pedido(conn, id_pedido=int(id_pedido))
            total_ins += r["insertadas"]
            total_omit += r["omitidas"]
            if r["insertadas"] > 0:
                detalle.append(r)
        except ValueError as exc:
            logger.warning("Pedido %s omitido en reintegración: %s", id_pedido, exc)
        except duckdb.Error as exc:
            logger.warning("Pedido %s falló en reintegración (se reintentará): %s", id_pedido, exc)

    return {
        "procesados": len(ids),
        "insertadas": total_ins,
        "omitidas": total_omit,
        "detalle": detalle,
    }
