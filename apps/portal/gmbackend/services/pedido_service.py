"""
services/pedido_service.py — Checkout, pedidos y pago simulado.

Flujo transaccional al confirmar:
  carrito activo → pedido (pendiente_pago) → pago simulado aprobado →
  descuento de stock atómico → estado pagado → carrito convertido.

Idempotencia de pago: un pedido con pago aprobado no se vuelve a procesar.
El stock nunca queda negativo (falla el checkout con ValueError).
"""

from __future__ import annotations

from typing import Any, Optional

import duckdb

from shared.database.connection import table_exists, column_exists
from shared.database.ids import siguiente_id
from shared.services import red_bodegas
from shared.services.promocion_service import calcular_totales_venta

from gmbackend.services.estado_pedido import cambiar_estado, historial_pedido
from gmbackend.services.carrito_service import (
    _bloquear_si_pedido_pendiente,
    _carrito_o_crear,
    agregar_linea_reorden,
    obtener_carrito_activo,
    ver_carrito,
)
from gmbackend.services.producto_service import _imagen_publica

METODOS_PAGO_DIFERIDOS = frozenset({"transferencia", "credito_interno"})

ESTADOS_REORDEN = frozenset({"pagado", "preparando", "enviado", "entregado"})


class ReordenSinAgregadosError(ValueError):
    """Ninguna línea del pedido pudo agregarse al carrito."""

    def __init__(self, resumen: dict[str, Any]):
        self.resumen = resumen
        super().__init__("No se pudo agregar ningún producto al carrito.")


def _metodos_pago_habilitados(conn: duckdb.DuckDBPyConnection) -> set[str]:
    from shared.services.config_service import obtener_config

    raw = obtener_config(conn, "PAGO_SIM_METODOS", "tarjeta,transferencia,credito_interno")
    return {m.strip().lower() for m in raw.split(",") if m.strip()}


def _id_metodo_pago(conn: duckdb.DuckDBPyConnection, metodo: str) -> int:
    row = conn.execute(
        "SELECT id_metodo FROM metodos_pago WHERE lower(nombre) = lower(?) AND activo = true",
        [metodo],
    ).fetchone()
    if not row:
        raise ValueError(f"Método de pago no disponible: {metodo}")
    return int(row[0])

IVA_PCT_DEFAULT = 18.0
ALMACEN_CENTRAL = 1


def _envio_cliente(conn: duckdb.DuckDBPyConnection, id_pedido: int) -> Optional[dict[str, Any]]:
    if not table_exists(conn, "envios"):
        return None
    try:
        r = conn.execute(
            """
            SELECT e.id_envio, e.estado, t.nombre
            FROM envios e LEFT JOIN transportistas t ON t.id_transportista = e.id_transportista
            WHERE e.id_pedido = ? ORDER BY e.id_envio DESC LIMIT 1
            """,
            [id_pedido],
        ).fetchone()
    except duckdb.Error:
        return None
    if not r:
        return None
    eventos = []
    if table_exists(conn, "tracking_eventos"):
        eventos = [
            {"estado": ev[0], "fecha": str(ev[1]) if ev[1] else None, "descripcion": ev[2]}
            for ev in conn.execute(
                "SELECT estado, fecha, descripcion FROM tracking_eventos WHERE id_envio = ? ORDER BY fecha",
                [int(r[0])],
            ).fetchall()
        ]
    return {"id_envio": int(r[0]), "estado": r[1], "transportista": r[2], "eventos": eventos}


def _iva_pct(conn: duckdb.DuckDBPyConnection) -> float:
    row = conn.execute(
        "SELECT valor FROM configuracion_sistema WHERE clave = 'IVA_PCT'"
    ).fetchone()
    try:
        return float(row[0]) if row else IVA_PCT_DEFAULT
    except (TypeError, ValueError):
        return IVA_PCT_DEFAULT


def _numero_pedido(conn: duckdb.DuckDBPyConnection) -> str:
    n = int(conn.execute("SELECT COALESCE(MAX(id_pedido), 0) + 1 FROM pedidos").fetchone()[0])
    return f"PED-{n:06d}"


def _dim_int(
    conn: duckdb.DuckDBPyConnection,
    sql: str,
    params: list[Any] | None,
    *,
    err: str,
) -> int:
    row = conn.execute(sql, params or []).fetchone()
    if row and row[0] is not None:
        return int(row[0])
    raise ValueError(err)


def _dim_defaults(conn: duckdb.DuckDBPyConnection, id_cliente: int) -> tuple[int, int, int]:
    """(id_country, id_channel, id_priority) para el pedido."""
    pais = conn.execute(
        """
        SELECT dc2.id_country
        FROM dim_cliente dc
        JOIN dim_country dc2 ON lower(dc2.country) = lower(dc.pais)
        WHERE dc.id_cliente = ?
        LIMIT 1
        """,
        [id_cliente],
    ).fetchone()
    if pais and pais[0] is not None:
        id_country = int(pais[0])
    else:
        id_country = _dim_int(
            conn,
            "SELECT MIN(id_country) FROM dim_country",
            None,
            err="No hay países configurados en el catálogo maestro.",
        )
    canal = conn.execute(
        "SELECT id_channel FROM dim_sales_channel WHERE lower(sales_channel) = 'online' LIMIT 1"
    ).fetchone()
    if canal and canal[0] is not None:
        id_channel = int(canal[0])
    else:
        id_channel = _dim_int(
            conn,
            "SELECT MIN(id_channel) FROM dim_sales_channel",
            None,
            err="No hay canales de venta configurados.",
        )
    id_priority = _dim_int(
        conn,
        "SELECT MIN(id_priority) FROM dim_order_priority",
        None,
        err="No hay prioridades de pedido configuradas.",
    )
    return id_country, id_channel, id_priority


def _almacenes_cliente(conn: duckdb.DuckDBPyConnection, id_cliente: int) -> list[int]:
    """Bodegas que abastecen la macro-zona del cliente, en orden de despacho."""
    red = red_bodegas.red_de_cliente(conn, id_cliente=id_cliente)
    return list(red.get("almacenes") or [ALMACEN_CENTRAL])


def _almacenes_pedido(conn: duckdb.DuckDBPyConnection, id_pedido: int) -> list[int]:
    row = conn.execute("SELECT id_cliente FROM pedidos WHERE id_pedido = ?", [id_pedido]).fetchone()
    if not row:
        return [ALMACEN_CENTRAL]
    return _almacenes_cliente(conn, int(row[0]))


def _validar_stock_carrito(
    conn: duckdb.DuckDBPyConnection, items: list[dict[str, Any]], almacenes: list[int]
) -> None:
    red_bodegas.validar_stock_zona(conn, items, almacenes)


def _descontar_stock(
    conn: duckdb.DuckDBPyConnection,
    items: list[dict[str, Any]],
    referencia: str,
    id_usuario: Optional[int],
    almacenes: list[int],
) -> None:
    """Descuenta stock de las bodegas de la zona, en orden de preferencia."""
    red_bodegas.descontar_stock_zona(
        conn, items, almacenes, referencia=referencia, id_usuario=id_usuario
    )


def _reponer_stock(
    conn: duckdb.DuckDBPyConnection,
    items: list[dict[str, Any]],
    referencia: str,
    id_usuario: Optional[int],
    almacenes: list[int],
) -> None:
    """Devuelve el stock de un pedido cancelado al hub de su zona."""
    red_bodegas.reponer_stock_zona(
        conn, items, almacenes, referencia=referencia, id_usuario=id_usuario
    )


def _pedido_pendiente_cliente(conn: duckdb.DuckDBPyConnection, id_cliente: int) -> Optional[int]:
    row = conn.execute(
        """
        SELECT id_pedido FROM pedidos
        WHERE id_cliente = ? AND estado = 'pendiente_pago'
        ORDER BY id_pedido DESC LIMIT 1
        """,
        [id_cliente],
    ).fetchone()
    return int(row[0]) if row else None


def _pais_valido(conn: duckdb.DuckDBPyConnection, pais: Optional[str]) -> str:
    pais_n = (pais or "").strip()
    if not pais_n:
        raise ValueError("Selecciona un país de entrega válido.")
    row = conn.execute(
        "SELECT 1 FROM dim_country WHERE country IS NOT NULL AND lower(country) = lower(?)",
        [pais_n],
    ).fetchone()
    if not row:
        raise ValueError("El país no es válido. Selecciona un país de la lista.")
    return pais_n


def _costo_envio_pais(conn: duckdb.DuckDBPyConnection, pais: str) -> float:
    """Tarifa base de la macro-zona del país de entrega (0 si no hay zonas configuradas)."""
    from shared.services.logistica_envio import estimar_envio_por_pais

    info = estimar_envio_por_pais(conn, pais=pais)
    costo = info.get("costo_estimado")
    if costo is None:
        return 0.0
    return round(float(costo), 2)


def _insertar_lineas_pedido(
    conn: duckdb.DuckDBPyConnection,
    *,
    id_pedido: int,
    items: list[dict[str, Any]],
) -> None:
    conn.execute("DELETE FROM pedido_detalle WHERE id_pedido = ?", [id_pedido])
    tiene_costo = column_exists(conn, "pedido_detalle", "costo_unitario")
    for item in items:
        id_detalle = siguiente_id(conn, "pedido_detalle")
        costo = conn.execute(
            """
            SELECT CAST(COALESCE(it.unit_cost, 0) AS DOUBLE)
            FROM dim_producto p JOIN dim_item_type it ON it.id_item_type = p.id_item_type
            WHERE p.id_producto = ?
            """,
            [item["id_producto"]],
        ).fetchone()
        costo_unitario = float(costo[0]) if costo else 0.0
        if tiene_costo:
            conn.execute(
                """
                INSERT INTO pedido_detalle (id_detalle, id_pedido, id_producto, cantidad, precio_unitario, subtotal, costo_unitario)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                [id_detalle, id_pedido, item["id_producto"], item["cantidad"], item["precio"], item["subtotal"], costo_unitario],
            )
        else:
            conn.execute(
                """
                INSERT INTO pedido_detalle (id_detalle, id_pedido, id_producto, cantidad, precio_unitario, subtotal)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                [id_detalle, id_pedido, item["id_producto"], item["cantidad"], item["precio"], item["subtotal"]],
            )


def crear_pedido_desde_carrito(
    conn: duckdb.DuckDBPyConnection,
    *,
    id_cliente: int,
    id_usuario: int,
    direccion_entrega: str,
    ciudad: Optional[str],
    notas: Optional[str],
    pais: Optional[str] = None,
) -> dict[str, Any]:
    """Convierte el carrito activo en un pedido `pendiente_pago` (checkout paso final).

    Si ya existe un pedido pendiente del cliente, lo actualiza (idempotente).
    """
    carrito = ver_carrito(conn, id_cliente)
    if not carrito["items"]:
        raise ValueError("El carrito está vacío.")

    pais_n = _pais_valido(conn, pais)
    conn.execute(
        "UPDATE dim_cliente SET pais = ? WHERE id_cliente = ?",
        [pais_n, id_cliente],
    )

    _validar_stock_carrito(conn, carrito["items"], _almacenes_cliente(conn, id_cliente))

    subtotal_items = round(sum(i["subtotal"] for i in carrito["items"]), 2)
    totales = calcular_totales_venta(conn, subtotal_items=subtotal_items)
    subtotal = totales["subtotal"]
    impuesto = totales["impuesto"]
    costo_envio = _costo_envio_pais(conn, pais_n)
    total = round(totales["total"] + costo_envio, 2)
    descuento_pct = totales["descuento_pct"]
    descuento_monto = totales["descuento_monto"]
    id_promocion = totales["id_promocion"]

    id_country, id_channel, id_priority = _dim_defaults(conn, id_cliente)
    direccion_full = direccion_entrega if not ciudad else f"{direccion_entrega}, {ciudad}"
    notas_full = (notas or "") + f" | Entrega: {direccion_full}"
    pending = _pedido_pendiente_cliente(conn, id_cliente)

    conn.execute("BEGIN TRANSACTION")
    try:
        if pending:
            id_pedido = pending
            sets = [
                "total_pedido = ?", "notas = ?", "subtotal = ?", "impuesto_monto = ?", "total = ?",
                "id_country = ?", "id_channel = ?", "id_priority = ?",
            ]
            params: list[Any] = [total, notas_full, subtotal, impuesto, total, id_country, id_channel, id_priority]
            if column_exists(conn, "pedidos", "descuento_pct"):
                sets += ["descuento_pct = ?", "descuento_monto = ?", "id_promocion = ?"]
                params += [descuento_pct, descuento_monto, id_promocion]
            if column_exists(conn, "pedidos", "costo_envio"):
                sets.append("costo_envio = ?")
                params.append(costo_envio)
            conn.execute(
                f"UPDATE pedidos SET {', '.join(sets)} WHERE id_pedido = ? AND id_cliente = ? AND estado = 'pendiente_pago'",
                [*params, id_pedido, id_cliente],
            )
            _insertar_lineas_pedido(conn, id_pedido=id_pedido, items=carrito["items"])
        else:
            numero = _numero_pedido(conn)
            insert_cols = [
                "id_cliente", "id_country", "id_channel", "id_priority", "estado",
                "total_pedido", "notas", "numero", "subtotal", "impuesto_monto", "total",
            ]
            insert_vals = [
                id_cliente, id_country, id_channel, id_priority, "pendiente_pago",
                total, notas_full, numero, subtotal, impuesto, total,
            ]
            if column_exists(conn, "pedidos", "descuento_pct"):
                insert_cols += ["descuento_pct", "descuento_monto", "id_promocion"]
                insert_vals += [descuento_pct, descuento_monto, id_promocion]
            if column_exists(conn, "pedidos", "costo_envio"):
                insert_cols.append("costo_envio")
                insert_vals.append(costo_envio)
            id_pedido = siguiente_id(conn, "pedidos")
            insert_cols = ["id_pedido"] + insert_cols
            insert_vals = [id_pedido] + insert_vals
            placeholders = ", ".join(["?"] * len(insert_vals))
            conn.execute(
                f"""
                INSERT INTO pedidos ({", ".join(insert_cols)})
                VALUES ({placeholders})
                """,
                insert_vals,
            )
            _insertar_lineas_pedido(conn, id_pedido=id_pedido, items=carrito["items"])
            conn.execute(
                """
                INSERT INTO pedido_estados_historial (id_historial, id_pedido, estado_anterior, estado_nuevo, id_usuario)
                VALUES ((SELECT COALESCE(MAX(id_historial), 0) + 1 FROM pedido_estados_historial), ?, NULL, 'pendiente_pago', ?)
                """,
                [id_pedido, id_usuario],
            )
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise
    return obtener_pedido(conn, id_pedido)


def pagar_pedido_simulado(
    conn: duckdb.DuckDBPyConnection,
    *,
    id_pedido: int,
    id_cliente: int,
    id_usuario: int,
    metodo: str = "simulado",
    referencia: Optional[str] = None,
    ultimos_digitos: Optional[str] = None,
    forzar_rechazo: bool = False,
) -> dict[str, Any]:
    """Pago simulado idempotente: aprueba, descuenta stock y convierte el carrito."""
    import random

    from shared.services.config_service import obtener_config_float

    metodo = (metodo or "tarjeta").strip().lower()
    if metodo not in _metodos_pago_habilitados(conn):
        raise ValueError(f"Método de pago no habilitado: {metodo}")

    pedido = obtener_pedido(conn, id_pedido)
    if not pedido or pedido["id_cliente"] != id_cliente:
        raise ValueError("Pedido no encontrado.")

    pago_previo = conn.execute(
        "SELECT id_pago FROM pagos WHERE id_pedido = ? AND estado = 'aprobado'", [id_pedido]
    ).fetchone()
    if pago_previo:
        return {"pedido": pedido, "pago": {"id_pago": int(pago_previo[0]), "estado": "aprobado", "idempotente": True}, "aprobado": True}

    pendiente_prev = conn.execute(
        "SELECT id_pago, numero FROM pagos WHERE id_pedido = ? AND estado = 'pendiente_validacion'",
        [id_pedido],
    ).fetchone()
    if pendiente_prev:
        return {
            "pedido": pedido,
            "pago": {"id_pago": int(pendiente_prev[0]), "numero": pendiente_prev[1], "estado": "pendiente_validacion"},
            "aprobado": False,
            "pendiente_validacion": True,
        }

    if pedido["estado"] != "pendiente_pago":
        raise ValueError(f"El pedido no está pendiente de pago (estado: {pedido['estado']}).")

    id_metodo = _id_metodo_pago(conn, metodo)
    ref_base = referencia or f"{metodo.upper()}-{id_pedido:06d}"

    if metodo in METODOS_PAGO_DIFERIDOS:
        n_pago = int(conn.execute("SELECT COALESCE(MAX(id_pago), 0) + 1 FROM pagos").fetchone()[0])
        numero_pago = f"PAG-{n_pago:06d}"
        conn.execute(
            """
            INSERT INTO pagos (id_pago, numero, id_pedido, id_factura, id_metodo, monto, estado, referencia, fecha)
            VALUES (?, ?, ?, NULL, ?, ?, 'pendiente_validacion', ?, current_timestamp)
            """,
            [n_pago, numero_pago, id_pedido, id_metodo, pedido["total"], ref_base],
        )
        motivo = (
            "Transferencia registrada. Validaremos el abono en 24–48 h hábiles."
            if metodo == "transferencia"
            else "Solicitud de crédito interno registrada. Pendiente de validación comercial."
        )
        return {
            "pedido": pedido,
            "pago": {
                "id_pago": n_pago,
                "numero": numero_pago,
                "estado": "pendiente_validacion",
                "referencia": ref_base,
                "motivo": motivo,
            },
            "aprobado": False,
            "pendiente_validacion": True,
        }

    tasa = obtener_config_float(conn, "PAGO_SIM_TASA_EXITO", 95.0)
    if forzar_rechazo or random.randint(1, 100) > int(tasa):
        ref = referencia or f"REJ-{id_pedido:06d}"
        n_pago = int(conn.execute("SELECT COALESCE(MAX(id_pago), 0) + 1 FROM pagos").fetchone()[0])
        conn.execute(
            """
            INSERT INTO pagos (numero, id_pedido, id_factura, id_metodo, monto, estado, referencia, fecha)
            VALUES (?, ?, NULL, ?, ?, 'rechazado', ?, current_timestamp)
            """,
            [f"PAG-{n_pago:06d}", id_pedido, id_metodo, pedido["total"], ref],
        )
        return {
            "pedido": pedido,
            "pago": {"estado": "rechazado", "referencia": ref, "motivo": "Pago simulado rechazado por el emisor"},
            "aprobado": False,
        }

    conn.execute("BEGIN TRANSACTION")
    try:
        _descontar_stock(
            conn,
            pedido["items"],
            f"Pedido {pedido['numero']}",
            id_usuario,
            _almacenes_cliente(conn, id_cliente),
        )

        n_pago = int(conn.execute("SELECT COALESCE(MAX(id_pago), 0) + 1 FROM pagos").fetchone()[0])
        ref_tx = referencia or f"TXN-{n_pago:06d}-{id_pedido}"
        id_pago = n_pago
        cols = "id_pago, numero, id_pedido, id_factura, id_metodo, monto, estado, referencia, fecha"
        vals = "?, ?, ?, NULL, ?, ?, 'aprobado', ?, current_timestamp"
        params: list[Any] = [id_pago, f"PAG-{n_pago:06d}", id_pedido, id_metodo, pedido["total"], ref_tx]
        if column_exists(conn, "pagos", "ref_transaccion"):
            cols += ", ref_transaccion, ultimos_digitos, estado_simulacion"
            vals += ", ?, ?, 'aprobado'"
            params.extend([ref_tx, (ultimos_digitos or "")[:4] or None])
        conn.execute(
            f"""
            INSERT INTO pagos ({cols})
            VALUES ({vals})
            """,
            params,
        )

        cambiar_estado(conn, id_pedido=id_pedido, nuevo_estado="pagado", id_usuario=id_usuario)

        id_carrito = obtener_carrito_activo(conn, id_cliente)
        if id_carrito is not None:
            conn.execute("UPDATE carritos SET estado = 'convertido' WHERE id_carrito = ?", [id_carrito])

        # Factura + integración a fact_ventas dentro de la transacción: si fallan,
        # se revierte TODO el pago (stock, pago, estado). Nunca queda un pedido
        # pagado sin factura ni sin filas en fact_ventas.
        _facturar_e_integrar(conn, id_pedido=id_pedido)

        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise

    # Fuera de la transacción: asientos contables (con backfill existente) y PDFs
    # (regenerables). Su fallo no bloquea el pago.
    _post_pago_complementos(conn, id_pedido=id_pedido, id_pago=id_pago, id_usuario=id_usuario)

    pedido_final = obtener_pedido(conn, id_pedido)
    try:
        from shared.services import notificacion_service as ns
        ns.notificar_pedido_portal_staff(
            conn,
            id_cliente=id_cliente,
            numero=pedido_final["numero"],
            total=float(pedido_final["total"]),
            estado="pagado",
        )
        ns.crear(
            conn,
            id_usuario=int(id_usuario),
            titulo=f"Pedido {pedido_final['numero']} confirmado",
            cuerpo=f"Pago aprobado por ${float(pedido_final['total']):,.2f}.",
            tipo="pedido",
            link="/pages/mis-pedidos.html",
        )
    except Exception:
        pass

    return {
        "pedido": pedido_final,
        "pago": {"id_pago": id_pago, "numero": f"PAG-{n_pago:06d}", "estado": "aprobado", "monto": pedido["total"], "referencia": ref_tx},
        "aprobado": True,
    }


def cancelar_pedido_cliente(
    conn: duckdb.DuckDBPyConnection,
    *,
    id_pedido: int,
    id_cliente: int,
    id_usuario: int,
) -> dict[str, Any]:
    """Cancela un pedido por parte del cliente.

    Regla de negocio: solo se permite cancelar mientras el pedido esté en
    `pendiente_pago` (aún no pagado) o `pagado` (recién pagado, antes de que
    empiece la preparación). Si ya fue pagado, se repone el stock y se actualiza
    el historial. No se permite cancelar pedidos en preparación/enviados.
    """
    pedido = obtener_pedido(conn, id_pedido)
    if not pedido or pedido["id_cliente"] != id_cliente:
        raise ValueError("Pedido no encontrado.")

    estado = pedido["estado"]
    if estado not in ("pendiente_pago", "pagado"):
        raise ValueError(
            "No es posible cancelar este pedido: solo se cancela mientras está "
            "pendiente de pago o recién pagado."
        )

    conn.execute("BEGIN TRANSACTION")
    try:
        cambio_estado = cambiar_estado(
            conn, id_pedido=id_pedido, nuevo_estado="cancelado", id_usuario=id_usuario
        )

        if estado == "pagado":
            _reponer_stock(
                conn,
                pedido["items"],
                f"Cancelación del pedido {pedido['numero']}",
                id_usuario,
                _almacenes_pedido(conn, id_pedido),
            )
            conn.execute(
                "UPDATE pagos SET estado = 'reversado' WHERE id_pedido = ? AND estado = 'aprobado'",
                [id_pedido],
            )
            _revertir_documentos_pagado(conn, id_pedido=id_pedido)

        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise

    return {"pedido": obtener_pedido(conn, id_pedido), "cambio": cambio_estado}


def _revertir_documentos_pagado(
    conn: duckdb.DuckDBPyConnection,
    *,
    id_pedido: int,
) -> None:
    """Revierte factura, filas de fact_ventas y asientos de un pedido pagado cancelado."""
    from shared.services.integracion_ventas_service import order_id_linea

    if table_exists(conn, "facturas_venta"):
        conn.execute(
            "UPDATE facturas_venta SET estado = 'anulada' WHERE id_pedido = ? AND estado = 'emitida'",
            [id_pedido],
        )
    if table_exists(conn, "fact_ventas"):
        oid_ini = order_id_linea(id_pedido, 0)
        conn.execute(
            "DELETE FROM fact_ventas WHERE order_id >= ? AND order_id < ?",
            [oid_ini, oid_ini + 1000],
        )
    if table_exists(conn, "asientos_contables"):
        conn.execute(
            "DELETE FROM asiento_lineas WHERE id_asiento IN (SELECT id_asiento FROM asientos_contables WHERE id_pedido = ?)",
            [id_pedido],
        )
        conn.execute("DELETE FROM asientos_contables WHERE id_pedido = ?", [id_pedido])


def _facturar_e_integrar(
    conn: duckdb.DuckDBPyConnection,
    *,
    id_pedido: int,
) -> None:
    """Factura + integración a fact_ventas, dentro de la transacción del pago.

    Las excepciones se propagan para que el pago se revierta por completo.
    """
    from shared.services.factura_service import crear_factura_desde_pedido
    from shared.services.integracion_ventas_service import integrar_pedido

    if table_exists(conn, "facturas_venta"):
        crear_factura_desde_pedido(conn, id_pedido=id_pedido)
    if table_exists(conn, "fact_ventas"):
        integrar_pedido(conn, id_pedido=id_pedido)


def _post_pago_complementos(
    conn: duckdb.DuckDBPyConnection,
    *,
    id_pedido: int,
    id_pago: int,
    id_usuario: int,
) -> None:
    """Tras el commit del pago: asientos contables y PDFs (best-effort, regenerables)."""
    import logging

    from shared.services.factura_service import obtener_factura_por_pedido

    log = logging.getLogger(__name__)

    if table_exists(conn, "asientos_contables"):
        try:
            from shared.services.contabilidad_service import generar_asientos_pedido_pagado

            generar_asientos_pedido_pagado(conn, id_pedido=id_pedido, id_pago=id_pago)
        except Exception as exc:
            log.warning("Asientos contables omitidos para pedido %s: %s", id_pedido, exc)

    if table_exists(conn, "comprobantes"):
        try:
            from shared.pdf import comprobante_service

            factura = obtener_factura_por_pedido(conn, id_pedido)
            comprobante_service.generar_pdf(conn, tipo="pedido", entidad_id=id_pedido, id_usuario=id_usuario)
            if factura:
                comprobante_service.generar_pdf(
                    conn, tipo="factura", entidad_id=int(factura["id_factura"]), id_usuario=id_usuario
                )
            comprobante_service.generar_pdf(conn, tipo="comprobante_pago", entidad_id=id_pago, id_usuario=id_usuario)
        except Exception as exc:
            log.warning("PDFs post-pago omitidos para pedido %s: %s", id_pedido, exc)


def obtener_pedido(conn: duckdb.DuckDBPyConnection, id_pedido: int) -> Optional[dict[str, Any]]:
    promo_join = ""
    promo_cols = ""
    if column_exists(conn, "pedidos", "descuento_pct"):
        promo_cols += ", CAST(COALESCE(p.descuento_pct, 0) AS DOUBLE)"
    if column_exists(conn, "pedidos", "descuento_monto"):
        promo_cols += ", CAST(COALESCE(p.descuento_monto, 0) AS DOUBLE)"
    if column_exists(conn, "pedidos", "id_promocion"):
        promo_cols += ", p.id_promocion"
        if table_exists(conn, "promociones"):
            promo_join = "LEFT JOIN promociones pr ON pr.id_promocion = p.id_promocion"
            promo_cols += ", pr.nombre"
        else:
            promo_cols += ", CAST(NULL AS VARCHAR)"
    envio_col = ""
    if column_exists(conn, "pedidos", "costo_envio"):
        envio_col = ", CAST(COALESCE(p.costo_envio, 0) AS DOUBLE)"
    r = conn.execute(
        f"""
        SELECT p.id_pedido, p.numero, p.id_cliente, c.nombre_empresa, p.fecha_pedido, p.estado,
               CAST(COALESCE(p.subtotal, 0) AS DOUBLE), CAST(COALESCE(p.impuesto_monto, 0) AS DOUBLE),
               CAST(COALESCE(p.total, p.total_pedido, 0) AS DOUBLE), p.notas
               {promo_cols}{envio_col}
        FROM pedidos p
        JOIN dim_cliente c ON c.id_cliente = p.id_cliente
        {promo_join}
        WHERE p.id_pedido = ?
        """,
        [id_pedido],
    ).fetchone()
    if not r:
        return None
    pagos = conn.execute(
        "SELECT id_pago, numero, CAST(monto AS DOUBLE), estado FROM pagos WHERE id_pedido = ? ORDER BY id_pago",
        [id_pedido],
    ).fetchall()
    factura_row = None
    if table_exists(conn, "facturas_venta"):
        factura_row = conn.execute(
            "SELECT id_factura, numero FROM facturas_venta WHERE id_pedido = ?", [id_pedido]
        ).fetchone()
    items = conn.execute(
        """
        SELECT d.id_detalle, d.id_producto, pr.nombre_producto, pr.imagen_url,
               d.cantidad, CAST(d.precio_unitario AS DOUBLE), CAST(d.subtotal AS DOUBLE)
        FROM pedido_detalle d
        JOIN dim_producto pr ON pr.id_producto = d.id_producto
        WHERE d.id_pedido = ?
        ORDER BY d.id_detalle
        """,
        [id_pedido],
    ).fetchall()
    idx = 10
    descuento_pct = 0.0
    descuento_monto = 0.0
    id_promocion = None
    promocion_nombre = None
    if column_exists(conn, "pedidos", "descuento_pct"):
        descuento_pct = float(r[idx])
        idx += 1
    if column_exists(conn, "pedidos", "descuento_monto"):
        descuento_monto = float(r[idx])
        idx += 1
    if column_exists(conn, "pedidos", "id_promocion"):
        id_promocion = int(r[idx]) if r[idx] is not None else None
        idx += 1
        # Siempre hay columna de nombre (JOIN o CAST NULL) cuando id_promocion está en el SELECT.
        if len(r) > idx:
            promocion_nombre = r[idx]
            idx += 1
    costo_envio = float(r[idx]) if envio_col and len(r) > idx and r[idx] is not None else 0.0
    return {
        "id_pedido": int(r[0]),
        "numero": r[1],
        "id_cliente": int(r[2]),
        "empresa": r[3],
        "fecha": str(r[4]) if r[4] is not None else None,
        "estado": r[5],
        "subtotal": float(r[6]),
        "impuesto": float(r[7]),
        "total": float(r[8]),
        "notas": r[9],
        "costo_envio": costo_envio,
        "descuento_pct": descuento_pct,
        "descuento_monto": descuento_monto,
        "id_promocion": id_promocion,
        "promocion_nombre": promocion_nombre,
        "items": [
            {
                "id_detalle": int(i[0]) if i[0] is not None else None,
                "id_producto": int(i[1]),
                "nombre_producto": i[2],
                "imagen_url": _imagen_publica(i[3]),
                "cantidad": int(i[4]),
                "precio_unitario": float(i[5]),
                "subtotal": float(i[6]),
            }
            for i in items
        ],
        "historial": historial_pedido(conn, id_pedido),
        "pagos": [
            {"id_pago": int(p[0]), "numero": p[1], "monto": float(p[2]), "estado": p[3]}
            for p in pagos
        ],
        "factura": (
            {"id_factura": int(factura_row[0]), "numero": factura_row[1]} if factura_row else None
        ),
        "envio": _envio_cliente(conn, id_pedido) if table_exists(conn, "envios") else None,
    }


def _linea_reorden_a_resumen(linea: dict[str, Any]) -> dict[str, Any]:
    base = {
        "id_producto": linea["id_producto"],
        "nombre_producto": linea.get("nombre_producto"),
        "cantidad_solicitada": linea["cantidad_solicitada"],
        "cantidad_agregada": linea.get("cantidad_agregada", 0),
    }
    if linea.get("motivo"):
        base["motivo"] = linea["motivo"]
    return base


def volver_a_pedir(
    conn: duckdb.DuckDBPyConnection,
    *,
    id_pedido: int,
    id_cliente: int,
) -> dict[str, Any]:
    """Replica líneas de un pedido elegible al carrito activo del cliente."""
    row = conn.execute(
        "SELECT id_pedido, numero, id_cliente, estado FROM pedidos WHERE id_pedido = ?",
        [id_pedido],
    ).fetchone()
    if not row or int(row[2]) != id_cliente:
        raise ValueError("Pedido no encontrado.")

    estado = str(row[3])
    if estado not in ESTADOS_REORDEN:
        raise ValueError(f"Este pedido no permite volver a pedir (estado: {estado}).")

    _bloquear_si_pedido_pendiente(conn, id_cliente)

    lineas = conn.execute(
        """
        SELECT id_producto, CAST(cantidad AS INTEGER)
        FROM pedido_detalle
        WHERE id_pedido = ?
        ORDER BY id_detalle
        """,
        [id_pedido],
    ).fetchall()

    agregados: list[dict[str, Any]] = []
    omitidos: list[dict[str, Any]] = []
    ajustados: list[dict[str, Any]] = []

    conn.execute("BEGIN TRANSACTION")
    try:
        id_carrito = _carrito_o_crear(conn, id_cliente)
        for id_producto, cantidad in lineas:
            resultado = agregar_linea_reorden(
                conn,
                id_carrito=id_carrito,
                id_cliente=id_cliente,
                id_producto=int(id_producto),
                cantidad_solicitada=int(cantidad),
            )
            item = _linea_reorden_a_resumen(resultado)
            if resultado["estado"] == "agregado":
                agregados.append(item)
            elif resultado["estado"] == "ajustado":
                ajustados.append(item)
            else:
                omitidos.append(item)

        n_agregados = len(agregados) + len(ajustados)
        resumen = {
            "agregados": agregados,
            "omitidos": omitidos,
            "ajustados": ajustados,
            "n_agregados": n_agregados,
        }
        if n_agregados == 0:
            conn.execute("ROLLBACK")
            raise ReordenSinAgregadosError(resumen)
        conn.execute("COMMIT")
    except ReordenSinAgregadosError:
        raise
    except Exception:
        conn.execute("ROLLBACK")
        raise

    return {
        "id_pedido": int(row[0]),
        "numero": row[1],
        "resumen": resumen,
        "carrito": ver_carrito(conn, id_cliente),
        "redirigir_carrito": True,
    }


def listar_pedidos_cliente(conn: duckdb.DuckDBPyConnection, id_cliente: int) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT p.id_pedido, p.numero, p.fecha_pedido, p.estado,
               CAST(COALESCE(p.total, p.total_pedido, 0) AS DOUBLE),
               (SELECT COUNT(*) FROM pedido_detalle d WHERE d.id_pedido = p.id_pedido)
        FROM pedidos p
        WHERE p.id_cliente = ?
        ORDER BY p.id_pedido DESC
        """,
        [id_cliente],
    ).fetchall()
    return [
        {
            "id_pedido": int(r[0]),
            "numero": r[1],
            "fecha": str(r[2]) if r[2] is not None else None,
            "estado": r[3],
            "total": float(r[4]),
            "n_items": int(r[5]),
        }
        for r in rows
    ]
