"""
services/pedido_admin_service.py — Gestión de pedidos desde el panel.
Comparte la máquina de estados del portal (misma BD).
"""

from __future__ import annotations

from typing import Any, Optional

import duckdb

from shared.database.connection import table_exists, column_exists

# La máquina de estados vive en el paquete del portal; ambas apps corren en el
# mismo proceso (run.py añade apps/portal al sys.path).
from gmbackend.services.estado_pedido import TRANSICIONES, cambiar_estado, historial_pedido


def listar_pedidos(
    conn: duckdb.DuckDBPyConnection,
    *,
    estado: Optional[str] = None,
    q: Optional[str] = None,
    page: int = 1,
    page_size: int = 20,
) -> dict[str, Any]:
    page = max(1, page)
    page_size = max(1, min(page_size, 100))
    where: list[str] = []
    params: list[Any] = []
    if estado:
        where.append("p.estado = ?")
        params.append(estado)
    if q:
        where.append("(lower(c.nombre_empresa) LIKE ? OR lower(COALESCE(p.numero, '')) LIKE ?)")
        params.extend([f"%{q.lower()}%", f"%{q.lower()}%"])
    where_sql = ("WHERE " + " AND ".join(where)) if where else ""

    total = int(
        conn.execute(
            f"""
            SELECT COUNT(*) FROM pedidos p
            JOIN dim_cliente c ON c.id_cliente = p.id_cliente
            {where_sql}
            """,
            params,
        ).fetchone()[0]
    )
    rows = conn.execute(
        f"""
        SELECT p.id_pedido, p.numero, c.nombre_empresa, p.fecha_pedido, p.estado,
               CAST(COALESCE(p.total, p.total_pedido, 0) AS DOUBLE),
               (SELECT COUNT(*) FROM pedido_detalle d WHERE d.id_pedido = p.id_pedido)
        FROM pedidos p
        JOIN dim_cliente c ON c.id_cliente = p.id_cliente
        {where_sql}
        ORDER BY p.id_pedido DESC
        LIMIT ? OFFSET ?
        """,
        [*params, page_size, (page - 1) * page_size],
    ).fetchall()
    return {
        "items": [
            {
                "id_pedido": int(r[0]),
                "numero": r[1],
                "empresa": r[2],
                "fecha": str(r[3]) if r[3] is not None else None,
                "estado": r[4],
                "total": float(r[5]),
                "n_items": int(r[6]),
            }
            for r in rows
        ],
        "page": page,
        "page_size": page_size,
        "total_items": total,
        "total_pages": max(1, -(-total // page_size)),
    }


def obtener_pedido_admin(conn: duckdb.DuckDBPyConnection, id_pedido: int) -> Optional[dict[str, Any]]:
    envio_col = ""
    if column_exists(conn, "pedidos", "costo_envio"):
        envio_col = ", CAST(COALESCE(p.costo_envio, 0) AS DOUBLE)"
    r = conn.execute(
        f"""
        SELECT p.id_pedido, p.numero, p.id_cliente, c.nombre_empresa, c.pais,
               p.fecha_pedido, p.estado, CAST(COALESCE(p.subtotal, 0) AS DOUBLE),
               CAST(COALESCE(p.impuesto_monto, 0) AS DOUBLE),
               CAST(COALESCE(p.total, p.total_pedido, 0) AS DOUBLE), p.notas{envio_col}
        FROM pedidos p
        JOIN dim_cliente c ON c.id_cliente = p.id_cliente
        WHERE p.id_pedido = ?
        """,
        [id_pedido],
    ).fetchone()
    if not r:
        return None

    items = conn.execute(
        """
        SELECT d.id_detalle, d.id_producto, pr.nombre_producto, d.cantidad,
               CAST(d.precio_unitario AS DOUBLE), CAST(d.subtotal AS DOUBLE)
        FROM pedido_detalle d
        JOIN dim_producto pr ON pr.id_producto = d.id_producto
        WHERE d.id_pedido = ?
        ORDER BY d.id_detalle
        """,
        [id_pedido],
    ).fetchall()
    pagos = conn.execute(
        """
        SELECT id_pago, numero, CAST(monto AS DOUBLE), estado, referencia, fecha
        FROM pagos WHERE id_pedido = ? ORDER BY id_pago
        """,
        [id_pedido],
    ).fetchall()
    estado = r[6]
    factura_row = None
    if table_exists(conn, "facturas_venta"):
        factura_row = conn.execute(
            "SELECT id_factura, numero FROM facturas_venta WHERE id_pedido = ?", [id_pedido]
        ).fetchone()
    return {
        "id_pedido": int(r[0]),
        "numero": r[1],
        "id_cliente": int(r[2]),
        "empresa": r[3],
        "pais": r[4],
        "fecha": str(r[5]) if r[5] is not None else None,
        "estado": estado,
        "subtotal": float(r[7]),
        "impuesto": float(r[8]),
        "total": float(r[9]),
        "notas": r[10],
        "costo_envio": float(r[11]) if envio_col else 0.0,
        "items": [
            {
                "id_detalle": int(i[0]),
                "id_producto": int(i[1]),
                "producto": i[2],
                "cantidad": int(i[3]),
                "precio_unitario": float(i[4]),
                "subtotal": float(i[5]),
            }
            for i in items
        ],
        "pagos": [
            {
                "id_pago": int(p[0]),
                "numero": p[1],
                "monto": float(p[2]),
                "estado": p[3],
                "referencia": p[4],
                "fecha": str(p[5]) if p[5] is not None else None,
            }
            for p in pagos
        ],
        "historial": historial_pedido(conn, id_pedido),
        "transiciones_posibles": sorted(TRANSICIONES.get(estado, set())),
        "factura": (
            {"id_factura": int(factura_row[0]), "numero": factura_row[1]} if factura_row else None
        ),
        "envio": _envio_resumen(conn, id_pedido),
    }


def _envio_resumen(conn: duckdb.DuckDBPyConnection, id_pedido: int) -> Optional[dict[str, Any]]:
    try:
        from backend.services.logistica_service import obtener_envio_pedido
        return obtener_envio_pedido(conn, id_pedido)
    except Exception:
        return None


def cambiar_estado_admin(
    conn: duckdb.DuckDBPyConnection,
    *,
    id_pedido: int,
    nuevo_estado: str,
    id_usuario: int,
    id_transportista: Optional[int] = None,
) -> dict[str, Any]:
    conn.execute("BEGIN TRANSACTION")
    try:
        if nuevo_estado == "pagado":
            _verificar_pago_aprobado(conn, id_pedido=id_pedido)
        resultado = cambiar_estado(conn, id_pedido=id_pedido, nuevo_estado=nuevo_estado, id_usuario=id_usuario)
        if nuevo_estado == "pagado":
            _facturar_e_integrar_admin(conn, id_pedido=id_pedido)
        elif nuevo_estado == "enviado":
            from backend.services.logistica_service import on_pedido_enviado
            on_pedido_enviado(conn, id_pedido=id_pedido, id_transportista=id_transportista)
        elif nuevo_estado == "entregado":
            from backend.services.logistica_service import on_pedido_entregado
            on_pedido_entregado(conn, id_pedido=id_pedido)
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise
    if nuevo_estado == "pagado":
        _contabilidad_pedido_pagado(conn, id_pedido=id_pedido)
    try:
        from shared.services import notificacion_service as ns
        numero = resultado.get("numero") or id_pedido
        try:
            row_n = conn.execute("SELECT numero FROM pedidos WHERE id_pedido = ?", [id_pedido]).fetchone()
            if row_n and row_n[0]:
                numero = row_n[0]
        except Exception:
            pass
        ns.notificar_staff_con_permiso(
            conn,
            permiso="mod.operaciones",
            titulo=f"Pedido {numero} → {nuevo_estado}",
            cuerpo=f"El pedido cambió de estado a «{nuevo_estado}».",
            link=f"/?page=pedidos",
            tipo="pedido",
        )
        # Aviso al cliente del portal (si tiene usuario)
        cli = conn.execute(
            """
            SELECT u.id_usuario FROM pedidos p
            JOIN dim_cliente dc ON dc.id_cliente = p.id_cliente
            JOIN usuarios u ON u.id_usuario = dc.id_usuario
            WHERE p.id_pedido = ?
            """,
            [id_pedido],
        ).fetchone()
        if cli:
            ns.crear(
                conn,
                id_usuario=int(cli[0]),
                titulo=f"Tu pedido {numero}",
                cuerpo=f"Estado actualizado: {nuevo_estado}",
                tipo="pedido",
                link="/pages/mis-pedidos.html",
            )
    except Exception:
        pass
    return resultado


def _verificar_pago_aprobado(conn: duckdb.DuckDBPyConnection, *, id_pedido: int) -> None:
    """Un pedido solo puede marcarse 'pagado' si existe un pago aprobado real."""
    row = conn.execute(
        "SELECT 1 FROM pagos WHERE id_pedido = ? AND estado = 'aprobado' LIMIT 1",
        [id_pedido],
    ).fetchone()
    if not row:
        raise ValueError(
            "No es posible marcar el pedido como 'pagado' sin un pago aprobado. "
            "El pago debe registrarse por el flujo del portal del cliente."
        )


def _facturar_e_integrar_admin(conn: duckdb.DuckDBPyConnection, *, id_pedido: int) -> None:
    """Factura + integración a fact_ventas al marcar pagado desde el admin
    (dentro de la transacción; revierte todo si falla)."""
    from shared.services.factura_service import crear_factura_desde_pedido
    from shared.services.integracion_ventas_service import integrar_pedido

    if table_exists(conn, "facturas_venta"):
        crear_factura_desde_pedido(conn, id_pedido=id_pedido)
    if table_exists(conn, "fact_ventas"):
        integrar_pedido(conn, id_pedido=id_pedido)


def _contabilidad_pedido_pagado(conn: duckdb.DuckDBPyConnection, *, id_pedido: int) -> None:
    """Genera asientos si el pedido quedó pagado (p. ej. cambio manual desde admin)."""
    import logging

    from shared.services.contabilidad_service import generar_asientos_pedido_pagado

    log = logging.getLogger(__name__)
    if not table_exists(conn, "asientos_contables"):
        return
    id_pago = None
    if table_exists(conn, "pagos"):
        row = conn.execute(
            "SELECT id_pago FROM pagos WHERE id_pedido = ? AND estado = 'aprobado' ORDER BY id_pago DESC LIMIT 1",
            [id_pedido],
        ).fetchone()
        id_pago = int(row[0]) if row else None
    try:
        generar_asientos_pedido_pagado(conn, id_pedido=id_pedido, id_pago=id_pago)
    except Exception as exc:
        log.warning("Asientos contables omitidos para pedido %s: %s", id_pedido, exc)
