"""
services/compras_service.py — Órdenes de compra y recepciones.

Estados de OC: borrador → aprobada → recibida (o cancelada desde borrador/aprobada).
La recepción incrementa stock del almacén destino vía inventario_service.
"""

from __future__ import annotations

from typing import Any, Optional

import duckdb

from backend.services.inventario_service import modificar_stock
from shared.database.connection import column_exists, table_exists
from shared.database.ids import siguiente_id
from shared.services import contabilidad_service
from shared.services.red_bodegas import geo_de_proveedor

METODOS_PAGO_OC = {"caja", "externo", "credito"}

ESTADOS_OC = {"borrador", "aprobada", "parcialmente_recibida", "recibida", "cancelada"}
_TRANSICIONES_OC = {
    "borrador": {"aprobada", "cancelada"},
    "aprobada": {"parcialmente_recibida", "recibida", "cancelada"},
    "parcialmente_recibida": {"parcialmente_recibida", "recibida", "cancelada"},
    "recibida": set(),
    "cancelada": set(),
}


def _tiene_col(conn: duckdb.DuckDBPyConnection, tabla: str, columna: str) -> bool:
    return column_exists(conn, tabla, columna)


def _siguiente_id_oc(conn: duckdb.DuckDBPyConnection) -> int:
    return siguiente_id(conn, "ordenes_compra")


def _numero_oc(conn: duckdb.DuckDBPyConnection, id_oc: Optional[int] = None) -> str:
    n = id_oc if id_oc is not None else _siguiente_id_oc(conn)
    return f"OC-{n:06d}"


def costo_sugerido_compra(
    conn: duckdb.DuckDBPyConnection,
    *,
    id_producto: int,
    id_proveedor: Optional[int] = None,
) -> dict[str, Any]:
    """Sugiere costo unitario: última OC al proveedor o costo del tipo de producto."""
    prod = conn.execute(
        "SELECT 1 FROM dim_producto WHERE id_producto = ?", [id_producto]
    ).fetchone()
    if not prod:
        raise ValueError(f"Producto {id_producto} no existe.")

    if id_proveedor is not None:
        prov = conn.execute(
            "SELECT 1 FROM proveedores WHERE id_proveedor = ? AND activo = true", [id_proveedor]
        ).fetchone()
        if not prov:
            raise ValueError(f"Proveedor {id_proveedor} no existe o está inactivo.")
        ultima = conn.execute(
            """
            SELECT CAST(d.costo_unitario AS DOUBLE)
            FROM orden_compra_detalle d
            JOIN ordenes_compra oc ON oc.id_oc = d.id_oc
            WHERE d.id_producto = ? AND oc.id_proveedor = ?
            ORDER BY oc.fecha DESC, d.id_detalle DESC
            LIMIT 1
            """,
            [id_producto, id_proveedor],
        ).fetchone()
        if ultima and ultima[0] is not None and float(ultima[0]) > 0:
            costo = float(ultima[0])
            return {
                "costo_unitario": costo,
                "origen": "ultima_compra_proveedor",
                "origen_label": "Última compra a este proveedor",
            }

    row = conn.execute(
        """
        SELECT CAST(COALESCE(p.precio_mayorista, p.precio_unitario, 0) AS DOUBLE),
               CAST(p.precio_unitario AS DOUBLE),
               CAST(p.precio_mayorista AS DOUBLE)
        FROM dim_producto p
        WHERE p.id_producto = ?
        """,
        [id_producto],
    ).fetchone()
    if not row:
        costo = 0.0
    else:
        costo = float(row[0] or 0)
    origen_label = (
        "Precio mayorista del producto en catálogo"
        if row and row[2] is not None and float(row[2]) > 0
        else "Precio de lista del producto en catálogo"
    )
    return {
        "costo_unitario": costo,
        "origen": "precio_producto",
        "origen_label": origen_label,
    }


def crear_orden_compra(
    conn: duckdb.DuckDBPyConnection,
    *,
    id_proveedor: int,
    items: list[dict[str, Any]],
    metodo_pago: str = "caja",
) -> dict[str, Any]:
    if metodo_pago not in METODOS_PAGO_OC:
        raise ValueError(
            f"Método de pago inválido: {metodo_pago}. Valores: {', '.join(sorted(METODOS_PAGO_OC))}."
        )
    proveedor = conn.execute(
        "SELECT 1 FROM proveedores WHERE id_proveedor = ? AND activo = true", [id_proveedor]
    ).fetchone()
    if not proveedor:
        raise ValueError(f"Proveedor {id_proveedor} no existe o está inactivo.")
    if not items:
        raise ValueError("La orden de compra necesita al menos un producto.")

    for item in items:
        prod = conn.execute(
            "SELECT 1 FROM dim_producto WHERE id_producto = ?", [item["id_producto"]]
        ).fetchone()
        if not prod:
            raise ValueError(f"Producto {item['id_producto']} no existe.")

    conn.execute("BEGIN TRANSACTION")
    try:
        total = sum(float(i["cantidad"]) * float(i["costo_unitario"]) for i in items)
        id_oc = _siguiente_id_oc(conn)
        numero = _numero_oc(conn, id_oc)
        if _tiene_col(conn, "ordenes_compra", "metodo_pago"):
            conn.execute(
                """
                INSERT INTO ordenes_compra (id_oc, numero, id_proveedor, fecha, estado, total, metodo_pago)
                VALUES (?, ?, ?, current_timestamp, 'borrador', ?, ?)
                """,
                [id_oc, numero, id_proveedor, total, metodo_pago],
            )
        else:
            conn.execute(
                """
                INSERT INTO ordenes_compra (id_oc, numero, id_proveedor, fecha, estado, total)
                VALUES (?, ?, ?, current_timestamp, 'borrador', ?)
                """,
                [id_oc, numero, id_proveedor, total],
            )
        for item in items:
            subtotal = float(item["cantidad"]) * float(item["costo_unitario"])
            conn.execute(
                """
                INSERT INTO orden_compra_detalle (id_detalle, id_oc, id_producto, cantidad, costo_unitario, subtotal)
                VALUES ((SELECT COALESCE(MAX(id_detalle), 0) + 1 FROM orden_compra_detalle), ?, ?, ?, ?, ?)
                """,
                [id_oc, item["id_producto"], item["cantidad"], item["costo_unitario"], subtotal],
            )
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise
    orden = obtener_orden(conn, id_oc)
    try:
        from shared.services import notificacion_service as ns
        ns.notificar_staff_con_permiso(
            conn,
            permiso="mod.compras",
            titulo=f"Nueva OC {orden.get('numero') or id_oc}",
            cuerpo=f"Proveedor: {orden.get('proveedor') or '—'} · Total {float(orden.get('total') or 0):,.2f} · {orden.get('estado')}",
            link="/?page=compras",
            tipo="compra",
        )
    except Exception:
        pass
    return orden


def obtener_orden(conn: duckdb.DuckDBPyConnection, id_oc: int) -> Optional[dict[str, Any]]:
    col_metodo = "oc.metodo_pago" if _tiene_col(conn, "ordenes_compra", "metodo_pago") else "NULL"
    r = conn.execute(
        f"""
        SELECT oc.id_oc, oc.numero, oc.id_proveedor, pr.razon_social, oc.fecha, oc.estado, CAST(oc.total AS DOUBLE), {col_metodo}
        FROM ordenes_compra oc
        JOIN proveedores pr ON pr.id_proveedor = oc.id_proveedor
        WHERE oc.id_oc = ?
        """,
        [id_oc],
    ).fetchone()
    if not r:
        return None
    detalles = conn.execute(
        """
        SELECT d.id_detalle, d.id_producto, p.nombre_producto,
               CAST(d.cantidad AS DOUBLE), CAST(d.costo_unitario AS DOUBLE), CAST(d.subtotal AS DOUBLE)
        FROM orden_compra_detalle d
        JOIN dim_producto p ON p.id_producto = d.id_producto
        WHERE d.id_oc = ?
        ORDER BY d.id_detalle
        """,
        [id_oc],
    ).fetchall()
    recibido_lotes = {}
    if table_exists(conn, "recepcion_compra_detalle") and table_exists(conn, "recepciones_compra"):
        rows = conn.execute(
            """
            SELECT rcd.id_producto, SUM(CAST(rcd.cantidad_recibida AS DOUBLE))
            FROM recepcion_compra_detalle rcd
            JOIN recepciones_compra rc ON rc.id_recepcion = rcd.id_recepcion
            WHERE rc.id_oc = ?
            GROUP BY rcd.id_producto
            """,
            [id_oc],
        ).fetchall()
        for lote in rows:
            recibido_lotes[int(lote[0])] = float(lote[1] or 0)
    geo = geo_de_proveedor(conn, int(r[2]))
    return {
        "id_oc": int(r[0]),
        "numero": r[1],
        "id_proveedor": int(r[2]),
        "proveedor": r[3],
        "fecha": str(r[4]) if r[4] is not None else None,
        "estado": r[5],
        "total": float(r[6]) if r[6] is not None else 0.0,
        "metodo_pago": r[7] or "caja",
        "proveedor_pais": geo.get("pais"),
        "proveedor_macro_zona": geo.get("macro_zona"),
        "proveedor_macro_label": geo.get("macro_label"),
        "bodega_recepcion_sugerida": geo.get("bodega_sugerida"),
        "id_almacen_sugerido": geo.get("id_almacen_sugerido"),
        "items": [
            {
                "id_detalle": int(d[0]),
                "id_producto": int(d[1]),
                "producto": d[2],
                "cantidad": float(d[3]),
                "costo_unitario": float(d[4]),
                "subtotal": float(d[5]),
                "recibido": recibido_lotes.get(int(d[1]), 0.0),
                "pendiente": float(d[3]) - recibido_lotes.get(int(d[1]), 0.0),
            }
            for d in detalles
        ],
    }


def listar_ordenes(conn: duckdb.DuckDBPyConnection, *, estado: Optional[str] = None) -> list[dict[str, Any]]:
    where = ""
    params: list[Any] = []
    if estado:
        where = "WHERE oc.estado = ?"
        params.append(estado)
    col_metodo = "oc.metodo_pago" if _tiene_col(conn, "ordenes_compra", "metodo_pago") else "NULL"
    rows = conn.execute(
        f"""
        SELECT oc.id_oc, oc.numero, pr.razon_social, oc.fecha, oc.estado, CAST(oc.total AS DOUBLE),
               (SELECT COUNT(*) FROM orden_compra_detalle d WHERE d.id_oc = oc.id_oc), {col_metodo}
        FROM ordenes_compra oc
        JOIN proveedores pr ON pr.id_proveedor = oc.id_proveedor
        {where}
        ORDER BY oc.id_oc DESC
        """,
        params,
    ).fetchall()
    return [
        {
            "id_oc": int(r[0]),
            "numero": r[1],
            "proveedor": r[2],
            "fecha": str(r[3]) if r[3] is not None else None,
            "estado": r[4],
            "total": float(r[5]) if r[5] is not None else 0.0,
            "n_items": int(r[6]),
            "metodo_pago": r[7] or "caja",
        }
        for r in rows
    ]


def cambiar_estado_oc(conn: duckdb.DuckDBPyConnection, id_oc: int, nuevo_estado: str) -> dict[str, Any]:
    if nuevo_estado not in ESTADOS_OC:
        raise ValueError(f"Estado inválido: {nuevo_estado}.")
    orden = obtener_orden(conn, id_oc)
    if not orden:
        raise ValueError(f"Orden de compra {id_oc} no existe.")
    if nuevo_estado not in _TRANSICIONES_OC[orden["estado"]]:
        raise ValueError(f"Transición inválida: {orden['estado']} → {nuevo_estado}.")
    if nuevo_estado == "recibida":
        raise ValueError("Usa el endpoint de recepción para marcar la orden como recibida.")
    conn.execute("UPDATE ordenes_compra SET estado = ? WHERE id_oc = ?", [nuevo_estado, id_oc])
    orden = obtener_orden(conn, id_oc)
    try:
        from shared.services import notificacion_service as ns
        if nuevo_estado == "aprobada":
            ns.notificar_staff_con_permiso(
                conn,
                permiso="mod.compras",
                titulo=f"OC {orden.get('numero') or id_oc} aprobada",
                cuerpo=f"Proveedor: {orden.get('proveedor') or '—'} · Total {orden.get('total', 0):,.2f}",
                link="/?page=compras",
                tipo="compra",
            )
        elif nuevo_estado == "cancelada":
            ns.notificar_staff_con_permiso(
                conn,
                permiso="mod.compras",
                titulo=f"OC {orden.get('numero') or id_oc} cancelada",
                cuerpo=f"Proveedor: {orden.get('proveedor') or '—'}",
                link="/?page=compras",
                tipo="compra",
            )
    except Exception:
        pass
    return orden


def recibir_orden(
    conn: duckdb.DuckDBPyConnection,
    *,
    id_oc: int,
    id_almacen: int,
    id_usuario: Optional[int],
    recibos: Optional[list[dict[str, Any]]] = None,
) -> dict[str, Any]:
    """Registra la recepción de una OC aprobada o parcialmente recibida.

    - Sin ``recibos``: recibe todo el pendiente (recepción completa).
    - Con ``recibos``: recibe ``cantidad`` por ``id_detalle`` (recepción
      parcial). Cada ítem puede indicar ``observacion`` (merma/daño/diferencia).
    Incrementa stock, registra fact_compras y los asientos contables según el
    método de pago de la OC (caja / externo / credito).
    """
    orden = obtener_orden(conn, id_oc)
    if not orden:
        raise ValueError(f"Orden de compra {id_oc} no existe.")
    if orden["estado"] not in ("aprobada", "parcialmente_recibida"):
        raise ValueError(
            f"Solo se puede recibir una OC aprobada o parcialmente recibida (estado actual: {orden['estado']})."
        )

    detalles = {d["id_detalle"]: d for d in orden["items"]}
    recibo_map: dict[int, dict[str, Any]] = {}
    if recibos:
        for rec in recibos:
            id_det = int(rec["id_detalle"])
            det = detalles.get(id_det)
            if not det:
                raise ValueError(f"Detalle {id_det} no pertenece a la OC {id_oc}.")
            cant = float(rec.get("cantidad") or 0)
            if cant < 0 or cant > det["pendiente"] + 1e-9:
                raise ValueError(
                    f"Cantidad inválida para «{det['producto']}»: disponible por recibir {det['pendiente']}."
                )
            if cant > 0:
                recibo_map[id_det] = {
                    "id_detalle": id_det,
                    "id_producto": det["id_producto"],
                    "producto": det["producto"],
                    "cantidad": cant,
                    "costo_unitario": det["costo_unitario"],
                    "observacion": (rec.get("observacion") or "").strip() or None,
                }
    else:
        for det in detalles.values():
            if det["pendiente"] > 0:
                recibo_map[det["id_detalle"]] = {
                    "id_detalle": det["id_detalle"],
                    "id_producto": det["id_producto"],
                    "producto": det["producto"],
                    "cantidad": det["pendiente"],
                    "costo_unitario": det["costo_unitario"],
                    "observacion": None,
                }

    if not recibo_map:
        raise ValueError("No hay cantidades por recibir en esta orden.")

    pendiente_total = sum(det["pendiente"] for det in detalles.values())
    a_recibir = sum(rec["cantidad"] for rec in recibo_map.values())
    estado_recepcion = "completa" if a_recibir >= pendiente_total - 1e-9 else "parcial"

    conn.execute("BEGIN TRANSACTION")
    try:
        id_recepcion = siguiente_id(conn, "recepciones_compra")
        conn.execute(
            """
            INSERT INTO recepciones_compra (id_recepcion, id_oc, fecha, id_almacen, estado)
            VALUES (?, ?, current_timestamp, ?, ?)
            """,
            [id_recepcion, id_oc, id_almacen, estado_recepcion],
        )
        total_recibido = 0.0
        for rec in recibo_map.values():
            subtotal = rec["cantidad"] * rec["costo_unitario"]
            total_recibido += subtotal
            if _tiene_col(conn, "recepcion_compra_detalle", "observacion"):
                conn.execute(
                    """
                    INSERT INTO recepcion_compra_detalle (id_detalle, id_recepcion, id_producto, cantidad_recibida, id_lote, observacion)
                    VALUES ((SELECT COALESCE(MAX(id_detalle), 0) + 1 FROM recepcion_compra_detalle), ?, ?, ?, NULL, ?)
                    """,
                    [id_recepcion, rec["id_producto"], rec["cantidad"], rec["observacion"]],
                )
            else:
                conn.execute(
                    """
                    INSERT INTO recepcion_compra_detalle (id_detalle, id_recepcion, id_producto, cantidad_recibida, id_lote)
                    VALUES ((SELECT COALESCE(MAX(id_detalle), 0) + 1 FROM recepcion_compra_detalle), ?, ?, ?, NULL)
                    """,
                    [id_recepcion, rec["id_producto"], rec["cantidad"]],
                )
            modificar_stock(
                conn,
                id_producto=rec["id_producto"],
                cantidad=rec["cantidad"],
                tipo="entrada",
                referencia=f"Recepción {orden['numero']}",
                id_usuario=id_usuario,
                id_almacen=id_almacen,
            )
            conn.execute(
                """
                INSERT INTO fact_compras (id_compra, id_oc, id_producto, cantidad, costo, fecha)
                VALUES ((SELECT COALESCE(MAX(id_compra), 0) + 1 FROM fact_compras), ?, ?, ?, ?, current_timestamp)
                """,
                [id_oc, rec["id_producto"], rec["cantidad"], subtotal],
            )

        # Nuevo estado de la OC
        orden_act = obtener_orden(conn, id_oc)
        pendientes = [i["pendiente"] for i in orden_act["items"]]
        nuevo_estado = "recibida" if all(p <= 1e-9 for p in pendientes) else "parcialmente_recibida"
        conn.execute("UPDATE ordenes_compra SET estado = ? WHERE id_oc = ?", [nuevo_estado, id_oc])

        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise

    # Asientos contables fuera de la transacción de la recepción (cada asiento
    # abre su propia transacción). No deben romper la recepción.
    try:
        contabilidad_service.generar_asientos_recepcion_compra(
            conn,
            id_oc=id_oc,
            numero_oc=orden["numero"],
            id_recepcion=id_recepcion,
            total=total_recibido,
            metodo_pago=orden.get("metodo_pago") or "caja",
        )
    except Exception as exc:
        import logging
        logging.getLogger(__name__).warning(
            "Asientos de recepción OC %s: %s", id_oc, exc
        )

    return {"id_recepcion": id_recepcion, "orden": obtener_orden(conn, id_oc)}


def listar_recepciones(
    conn: duckdb.DuckDBPyConnection,
    *,
    id_oc: Optional[int] = None,
    id_producto: Optional[int] = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    where = ["1 = 1"]
    params: list[Any] = []
    if id_oc:
        where.append("r.id_oc = ?")
        params.append(id_oc)
    if id_producto:
        where.append("d.id_producto = ?")
        params.append(id_producto)
    cond = " AND ".join(where)
    rows = conn.execute(
        f"""
        SELECT r.id_recepcion, r.id_oc, oc.numero, pr.razon_social, r.fecha, r.estado,
               d.id_producto, p.nombre_producto, CAST(d.cantidad_recibida AS DOUBLE),
               d.observacion, a.nombre, a.macro_zona
        FROM recepciones_compra r
        JOIN ordenes_compra oc ON oc.id_oc = r.id_oc
        JOIN proveedores pr ON pr.id_proveedor = oc.id_proveedor
        JOIN recepcion_compra_detalle d ON d.id_recepcion = r.id_recepcion
        LEFT JOIN dim_producto p ON p.id_producto = d.id_producto
        LEFT JOIN almacenes a ON a.id_almacen = r.id_almacen
        WHERE {cond}
        ORDER BY r.id_recepcion DESC
        LIMIT ?
        """,
        params + [limit],
    ).fetchall()
    agrupadas: dict[int, dict[str, Any]] = {}
    for r in rows:
        id_rec = int(r[0])
        reg = agrupadas.get(id_rec)
        if reg is None:
            reg = {
                "id_recepcion": id_rec,
                "id_oc": int(r[1]),
                "numero_oc": r[2],
                "proveedor": r[3],
                "fecha": str(r[4]) if r[4] else None,
                "estado": r[5],
                "bodega": r[10] or "—",
                "macro_zona": r[11],
                "n_items": 0,
                "total": 0.0,
                "items": [],
            }
            agrupadas[id_rec] = reg
        reg["n_items"] += 1
        monto_item = float(r[8] or 0)
        costo_u = 0.0
        row_u = conn.execute(
            "SELECT CAST(costo_unitario AS DOUBLE) FROM orden_compra_detalle WHERE id_oc = ? AND id_producto = ? LIMIT 1",
            [int(r[1]), int(r[6])],
        ).fetchone()
        if row_u:
            costo_u = float(row_u[0])
        reg["total"] += monto_item * costo_u
        reg["items"].append({
            "id_producto": int(r[6]),
            "producto": r[7] or "—",
            "cantidad": monto_item,
            "observacion": r[9] if r[9] else None,
        })
    resultado = list(agrupadas.values())
    resultado.sort(key=lambda x: x["id_recepcion"], reverse=True)
    return resultado


def cuentas_por_pagar(
    conn: duckdb.DuckDBPyConnection,
    *,
    id_proveedor: Optional[int] = None,
) -> dict[str, Any]:
    """Resumen de deuda a proveedores: comprado, recibido, pagado y pendiente."""
    if not table_exists(conn, "fact_compras"):
        return {"total_pendiente": 0.0, "proveedores": []}
    cond = ""
    params: list[Any] = []
    if id_proveedor:
        cond = "WHERE oc.id_proveedor = ?"
        params.append(id_proveedor)
    rows = conn.execute(
        f"""
        SELECT oc.id_proveedor, pr.razon_social,
               CAST(COALESCE(SUM(fc.costo), 0) AS DOUBLE) AS comprado,
               CAST(COALESCE(SUM(fc.cantidad * d.costo_unitario), 0) AS DOUBLE) AS recibido
        FROM fact_compras fc
        JOIN ordenes_compra oc ON oc.id_oc = fc.id_oc
        JOIN proveedores pr ON pr.id_proveedor = oc.id_proveedor
        JOIN orden_compra_detalle d ON d.id_oc = oc.id_oc AND d.id_producto = fc.id_producto
        {cond}
        GROUP BY oc.id_proveedor, pr.razon_social
        ORDER BY pr.razon_social
        """,
        params,
    ).fetchall()
    proveedores = []
    for r in rows:
        recibido_val = float(r[3] or 0)
        comprado_val = float(r[2] or 0)
        pagado = 0.0
        if table_exists(conn, "asientos_contables"):
            pago_row = conn.execute(
                """
                SELECT CAST(COALESCE(SUM(a.total), 0) AS DOUBLE)
                FROM asientos_contables a
                JOIN ordenes_compra x ON x.id_oc = a.id_oc
                WHERE a.descripcion LIKE 'pago_oc:%' AND x.id_proveedor = ?
                """,
                [int(r[0])],
            ).fetchone()
            pagado = float(pago_row[0] or 0)
        pendiente = max(recibido_val - pagado, 0.0)
        proveedores.append({
            "id_proveedor": int(r[0]),
            "razon_social": r[1],
            "comprado": comprado_val,
            "recibido": recibido_val,
            "pagado": pagado,
            "pendiente": round(pendiente, 2),
        })
    total_pendiente = round(sum(p["pendiente"] for p in proveedores), 2)
    return {"total_pendiente": total_pendiente, "proveedores": proveedores}
