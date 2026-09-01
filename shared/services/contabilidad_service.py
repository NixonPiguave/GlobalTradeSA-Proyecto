"""
contabilidad_service.py — Asientos automáticos al pagar pedidos (venta, costo, cobro).
"""

from __future__ import annotations

import logging
from typing import Any, Optional

import duckdb

from shared.database.connection import column_exists, table_exists
from shared.services.integracion_ventas_service import order_id_linea

logger = logging.getLogger(__name__)

CUENTAS = {
    "caja": "1101",
    "cxc": "1201",
    "cxp": "2002",
    "pagos_externos": "3001",
    "ingresos": "4101",
    "ingresos_netos": "4102",
    "iva_debito": "2101",
    "iva_credito": "2102",
    "costo": "5101",
    "inventario": "1301",
}


def _cuenta_id_opcional(conn: duckdb.DuckDBPyConnection, codigo: str) -> Optional[int]:
    try:
        return _cuenta_id(conn, codigo)
    except ValueError:
        return None


def _desglose_iva(conn: duckdb.DuckDBPyConnection, total: float, impuesto: float) -> tuple[float, float]:
    if impuesto > 0:
        return round(total - impuesto, 2), round(impuesto, 2)
    from shared.services.config_service import obtener_config_float

    iva_pct = obtener_config_float(conn, "IVA_PCT", 18.0)
    if iva_pct <= 0:
        return round(total, 2), 0.0
    neto = round(total / (1 + iva_pct / 100), 2)
    return neto, round(total - neto, 2)


def _cuenta_id(conn: duckdb.DuckDBPyConnection, codigo: str) -> int:
    row = conn.execute("SELECT id_cuenta FROM plan_cuentas WHERE codigo = ?", [codigo]).fetchone()
    if not row:
        raise ValueError(f"Cuenta contable {codigo} no configurada.")
    return int(row[0])


def _asiento_existe(conn: duckdb.DuckDBPyConnection, *, id_pedido: int, tipo: str) -> bool:
    r = conn.execute(
        "SELECT 1 FROM asientos_contables WHERE id_pedido = ? AND descripcion LIKE ?",
        [id_pedido, f"{tipo}:%"],
    ).fetchone()
    return bool(r)


def _crear_asiento(
    conn: duckdb.DuckDBPyConnection,
    *,
    id_pedido: Optional[int],
    id_factura: Optional[int],
    descripcion: str,
    lineas: list[tuple[int, float, float]],
    id_oc: Optional[int] = None,
) -> int:
    n = int(conn.execute("SELECT COALESCE(MAX(id_asiento), 0) + 1 FROM asientos_contables").fetchone()[0])
    numero = f"AST-{n:06d}"
    total = max(sum(d for _, d, _ in lineas), sum(h for _, _, h in lineas))
    conn.execute("BEGIN TRANSACTION")
    try:
        if id_oc is not None and column_exists(conn, "asientos_contables", "id_oc"):
            conn.execute(
                """
                INSERT INTO asientos_contables (id_asiento, numero, fecha, descripcion, id_pedido, id_factura, id_oc, total)
                VALUES (?, ?, current_timestamp, ?, ?, ?, ?, ?)
                """,
                [n, numero, descripcion, id_pedido, id_factura, id_oc, total],
            )
        else:
            conn.execute(
                """
                INSERT INTO asientos_contables (id_asiento, numero, fecha, descripcion, id_pedido, id_factura, total)
                VALUES (?, ?, current_timestamp, ?, ?, ?, ?)
                """,
                [n, numero, descripcion, id_pedido, id_factura, total],
            )
        for id_cuenta, debe, haber in lineas:
            id_linea = int(
                conn.execute("SELECT COALESCE(MAX(id_linea), 0) + 1 FROM asiento_lineas").fetchone()[0]
            )
            conn.execute(
                """
                INSERT INTO asiento_lineas (id_linea, id_asiento, id_cuenta, debe, haber)
                VALUES (?, ?, ?, ?, ?)
                """,
                [id_linea, n, id_cuenta, debe, haber],
            )
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise
    return n


def _asiento_id(conn: duckdb.DuckDBPyConnection, *, id_pedido: int, tipo: str) -> Optional[int]:
    r = conn.execute(
        "SELECT id_asiento FROM asientos_contables WHERE id_pedido = ? AND descripcion LIKE ?",
        [id_pedido, f"{tipo}:%"],
    ).fetchone()
    return int(r[0]) if r else None


def _total_cuenta_asiento(
    conn: duckdb.DuckDBPyConnection, *, id_asiento: int, codigo_cuenta: str
) -> tuple[float, float]:
    row = conn.execute(
        """
        SELECT CAST(COALESCE(SUM(al.debe), 0) AS DOUBLE),
               CAST(COALESCE(SUM(al.haber), 0) AS DOUBLE)
        FROM asiento_lineas al
        JOIN plan_cuentas pc ON pc.id_cuenta = al.id_cuenta
        WHERE al.id_asiento = ? AND pc.codigo = ?
        """,
        [id_asiento, codigo_cuenta],
    ).fetchone()
    return float(row[0]), float(row[1]) if row else (0.0, 0.0)


def _reparar_asiento_venta_cxc(
    conn: duckdb.DuckDBPyConnection,
    *,
    id_pedido: int,
    id_factura: Optional[int],
    total: float,
    c_cxc: int,
    c_ing: int,
) -> bool:
    """Completa débito CxC y/o crédito ingresos si el asiento de venta quedó incompleto."""
    id_a = _asiento_id(conn, id_pedido=id_pedido, tipo="venta")
    if id_a is None:
        return False
    debe_cxc, _ = _total_cuenta_asiento(conn, id_asiento=id_a, codigo_cuenta=CUENTAS["cxc"])
    _, haber_ing = _total_cuenta_asiento(conn, id_asiento=id_a, codigo_cuenta=CUENTAS["ingresos"])
    esperado = max(haber_ing, debe_cxc, total)
    reparado = False
    faltante_cxc = round(esperado - debe_cxc, 2)
    if faltante_cxc > 0.01:
        id_linea = int(conn.execute("SELECT COALESCE(MAX(id_linea), 0) + 1 FROM asiento_lineas").fetchone()[0])
        conn.execute(
            """
            INSERT INTO asiento_lineas (id_linea, id_asiento, id_cuenta, debe, haber)
            VALUES (?, ?, ?, ?, 0)
            """,
            [id_linea, id_a, c_cxc, faltante_cxc],
        )
        reparado = True
    faltante_ing = round(esperado - haber_ing, 2)
    if faltante_ing > 0.01:
        id_linea = int(conn.execute("SELECT COALESCE(MAX(id_linea), 0) + 1 FROM asiento_lineas").fetchone()[0])
        conn.execute(
            """
            INSERT INTO asiento_lineas (id_linea, id_asiento, id_cuenta, debe, haber)
            VALUES (?, ?, ?, 0, ?)
            """,
            [id_linea, id_a, c_ing, faltante_ing],
        )
        reparado = True
    if reparado:
        logger.info("Reparado asiento venta pedido %s (CxC +%.2f, ingresos +%.2f)", id_pedido, faltante_cxc, faltante_ing)
    return reparado


def _reparar_asiento_cobro_cxc(
    conn: duckdb.DuckDBPyConnection,
    *,
    id_pedido: int,
    id_factura: Optional[int],
    total: float,
    c_cxc: int,
    c_caja: int,
    id_pago: Optional[int],
) -> bool:
    """Completa el abono en CxC si el asiento de cobro quedó incompleto."""
    id_a = _asiento_id(conn, id_pedido=id_pedido, tipo="cobro")
    if id_a is None:
        return False
    _, haber_cxc = _total_cuenta_asiento(conn, id_asiento=id_a, codigo_cuenta=CUENTAS["cxc"])
    debe_caja, _ = _total_cuenta_asiento(conn, id_asiento=id_a, codigo_cuenta=CUENTAS["caja"])
    esperado = debe_caja if debe_caja > 0 else total
    faltante = round(esperado - haber_cxc, 2)
    if faltante <= 0.01:
        return False
    id_linea = int(conn.execute("SELECT COALESCE(MAX(id_linea), 0) + 1 FROM asiento_lineas").fetchone()[0])
    conn.execute(
        """
        INSERT INTO asiento_lineas (id_linea, id_asiento, id_cuenta, debe, haber)
        VALUES (?, ?, ?, 0, ?)
        """,
        [id_linea, id_a, c_cxc, faltante],
    )
    logger.info("Reparado abono CxC %.2f en cobro pedido %s", faltante, id_pedido)
    return True


def generar_asientos_pedido_pagado(
    conn: duckdb.DuckDBPyConnection,
    *,
    id_pedido: int,
    id_pago: Optional[int] = None,
) -> dict[str, Any]:
    if not table_exists(conn, "asientos_contables") or not table_exists(conn, "plan_cuentas"):
        return {"id_pedido": id_pedido, "asientos": [], "motivo": "sin_tablas_contables"}

    pedido = conn.execute(
        """
        SELECT estado, CAST(COALESCE(subtotal, 0) AS DOUBLE), CAST(COALESCE(impuesto_monto, 0) AS DOUBLE),
               CAST(COALESCE(total, total_pedido, 0) AS DOUBLE)
        FROM pedidos WHERE id_pedido = ?
        """,
        [id_pedido],
    ).fetchone()
    if not pedido or pedido[0] not in ("pagado", "preparando", "enviado", "entregado"):
        raise ValueError(f"Pedido {id_pedido} no está pagado.")

    total = float(pedido[3]) or float(pedido[1]) + float(pedido[2])

    costo_total = 0.0
    if table_exists(conn, "fact_ventas"):
        base = order_id_linea(id_pedido, 0)
        c_row = conn.execute(
            """
            SELECT CAST(SUM(COALESCE(total_cost, 0)) AS DOUBLE)
            FROM fact_ventas
            WHERE order_id >= ? AND order_id <= ? AND origen = 'portal'
            """,
            [base, base + 999],
        ).fetchone()
        if c_row and c_row[0]:
            costo_total = float(c_row[0])
    if costo_total <= 0:
        costo_row = conn.execute(
            """
            SELECT CAST(SUM(COALESCE(d.costo_unitario, 0) * d.cantidad) AS DOUBLE)
            FROM pedido_detalle d WHERE d.id_pedido = ?
            """,
            [id_pedido],
        ).fetchone()
        costo_total = float(costo_row[0]) if costo_row and costo_row[0] else 0.0

    id_factura = None
    if table_exists(conn, "facturas_venta"):
        fr = conn.execute("SELECT id_factura FROM facturas_venta WHERE id_pedido = ?", [id_pedido]).fetchone()
        id_factura = int(fr[0]) if fr else None

    c_cxc = _cuenta_id(conn, CUENTAS["cxc"])
    c_ing = _cuenta_id(conn, CUENTAS["ingresos"])
    c_costo = _cuenta_id(conn, CUENTAS["costo"])
    c_inv = _cuenta_id(conn, CUENTAS["inventario"])
    c_caja = _cuenta_id(conn, CUENTAS["caja"])

    creados: list[dict[str, Any]] = []

    if _reparar_asiento_venta_cxc(
        conn, id_pedido=id_pedido, id_factura=id_factura, total=total, c_cxc=c_cxc, c_ing=c_ing
    ):
        creados.append({"tipo": "venta_reparada", "id_pedido": id_pedido})

    if _reparar_asiento_cobro_cxc(
        conn,
        id_pedido=id_pedido,
        id_factura=id_factura,
        total=total,
        c_cxc=c_cxc,
        c_caja=c_caja,
        id_pago=id_pago,
    ):
        creados.append({"tipo": "cobro_reparado", "id_pedido": id_pedido})

    if not _asiento_existe(conn, id_pedido=id_pedido, tipo="venta"):
        impuesto = float(pedido[2] or 0)
        neto, iva = _desglose_iva(conn, total, impuesto)
        c_ing_neto = _cuenta_id_opcional(conn, CUENTAS["ingresos_netos"]) or c_ing
        c_iva = _cuenta_id_opcional(conn, CUENTAS["iva_debito"])
        lineas_venta: list[tuple[int, float, float]] = [(c_cxc, total, 0), (c_ing_neto, 0, neto)]
        if c_iva and iva > 0:
            lineas_venta.append((c_iva, 0, iva))
        elif iva > 0:
            lineas_venta = [(c_cxc, total, 0), (c_ing, 0, total)]
        else:
            lineas_venta = [(c_cxc, total, 0), (c_ing_neto, 0, neto)]
        id_a = _crear_asiento(
            conn, id_pedido=id_pedido, id_factura=id_factura,
            descripcion=f"venta:Pedido {id_pedido}",
            lineas=lineas_venta,
        )
        creados.append({"tipo": "venta", "id_asiento": id_a})
        if column_exists(conn, "pedidos", "contabilidad_pendiente"):
            conn.execute("UPDATE pedidos SET contabilidad_pendiente = false WHERE id_pedido = ?", [id_pedido])

    if costo_total > 0 and not _asiento_existe(conn, id_pedido=id_pedido, tipo="costo"):
        id_a = _crear_asiento(
            conn, id_pedido=id_pedido, id_factura=id_factura,
            descripcion=f"costo:Pedido {id_pedido}",
            lineas=[(c_costo, costo_total, 0), (c_inv, 0, costo_total)],
        )
        creados.append({"tipo": "costo", "id_asiento": id_a})

    if not _asiento_existe(conn, id_pedido=id_pedido, tipo="cobro"):
        id_a = _crear_asiento(
            conn, id_pedido=id_pedido, id_factura=id_factura,
            descripcion=f"cobro:Pedido {id_pedido}" + (f" pago {id_pago}" if id_pago else ""),
            lineas=[(c_caja, total, 0), (c_cxc, 0, total)],
        )
        creados.append({"tipo": "cobro", "id_asiento": id_a})

    return {"id_pedido": id_pedido, "asientos": creados, "omitidos": 3 - len(creados)}


METODOS_PAGO_OC = {"caja", "externo", "credito"}


def _encontrar_asiento_descripcion(
    conn: duckdb.DuckDBPyConnection, descripcion: str
) -> Optional[int]:
    r = conn.execute(
        "SELECT id_asiento FROM asientos_contables WHERE descripcion = ?",
        [descripcion],
    ).fetchone()
    return int(r[0]) if r else None


def generar_asientos_recepcion_compra(
    conn: duckdb.DuckDBPyConnection,
    *,
    id_oc: int,
    numero_oc: str,
    id_recepcion: int,
    total: float,
    metodo_pago: str,
) -> dict[str, Any]:
    """Registra la compra (Inventario → Cuentas por pagar) y, según el método de
    pago de la OC, el pago correspondiente (Caja o Pagos externos).

    - caja:   descuenta la caja (1101) por el total recibido.
    - externo: la financiación sale de fondos externos (3001); caja intacta.
    - credito: queda como Cuenta por pagar (2002) abierta.
    La dedupe se hace por descripción (una por recepción): idempotente.
    """
    if not table_exists(conn, "asientos_contables") or not table_exists(conn, "plan_cuentas"):
        return {"id_oc": id_oc, "creados": [], "motivo": "sin_tablas_contables"}
    total = round(float(total or 0), 2)
    if total <= 0:
        return {"id_oc": id_oc, "creados": [], "motivo": "total_cero"}

    c_inv = _cuenta_id(conn, CUENTAS["inventario"])
    c_cxp = _cuenta_id(conn, CUENTAS["cxp"])
    c_caja = _cuenta_id(conn, CUENTAS["caja"])
    c_ext = _cuenta_id(conn, CUENTAS["pagos_externos"])
    creados: list[dict[str, Any]] = []

    desc_compra = f"compra:R{id_recepcion} OC {numero_oc}"
    if _encontrar_asiento_descripcion(conn, desc_compra) is None:
        id_a = _crear_asiento(
            conn, id_pedido=0, id_factura=None, id_oc=id_oc,
            descripcion=desc_compra,
            lineas=[(c_inv, total, 0), (c_cxp, 0, total)],
        )
        creados.append({"tipo": "compra", "id_asiento": id_a})

    if metodo_pago != "credito":
        desc_pago = f"pago_oc:R{id_recepcion} OC {numero_oc}"
        if _encontrar_asiento_descripcion(conn, desc_pago) is None:
            if metodo_pago == "caja":
                lineas = [(c_cxp, total, 0), (c_caja, 0, total)]
            else:  # externo
                lineas = [(c_cxp, total, 0), (c_ext, 0, total)]
            id_a = _crear_asiento(
                conn, id_pedido=0, id_factura=None, id_oc=id_oc,
                descripcion=desc_pago,
                lineas=lineas,
            )
            creados.append({"tipo": f"pago_{metodo_pago}", "id_asiento": id_a})

    return {"id_oc": id_oc, "creados": creados}


def sincronizar_asientos_pedidos_pagados(conn: duckdb.DuckDBPyConnection) -> dict[str, Any]:
    """Genera asientos faltantes para pedidos ya pagados (backfill idempotente)."""
    if not table_exists(conn, "asientos_contables") or not table_exists(conn, "plan_cuentas"):
        return {"procesados": 0, "creados": 0, "detalle": [], "motivo": "sin_tablas_contables"}

    rows = conn.execute(
        """
        SELECT id_pedido FROM pedidos
        WHERE estado IN ('pagado', 'preparando', 'enviado', 'entregado')
        ORDER BY id_pedido
        """
    ).fetchall()
    detalle: list[dict[str, Any]] = []
    creados = 0
    for (id_pedido,) in rows:
        try:
            r = generar_asientos_pedido_pagado(conn, id_pedido=int(id_pedido))
            n = len(r.get("asientos") or [])
            if n:
                creados += n
                detalle.append({"id_pedido": int(id_pedido), "asientos": n})
        except Exception as exc:
            logger.warning("Sync contable pedido %s: %s", id_pedido, exc)
            detalle.append({"id_pedido": int(id_pedido), "error": str(exc)})
    return {"procesados": len(rows), "creados": creados, "detalle": detalle}


def listar_asientos(
    conn: duckdb.DuckDBPyConnection, *, page: int = 1, page_size: int = 20,
) -> dict[str, Any]:
    offset = (page - 1) * page_size
    total = int(conn.execute("SELECT COUNT(*) FROM asientos_contables").fetchone()[0])
    rows = conn.execute(
        """
        SELECT a.id_asiento, a.numero, a.fecha, a.descripcion,
               CAST(a.total AS DOUBLE), a.id_pedido, a.id_factura
        FROM asientos_contables a ORDER BY a.id_asiento DESC LIMIT ? OFFSET ?
        """,
        [page_size, offset],
    ).fetchall()
    return {
        "total": total, "page": page, "page_size": page_size,
        "items": [
            {
                "id_asiento": int(r[0]), "numero": r[1], "fecha": str(r[2]) if r[2] else None,
                "descripcion": r[3], "total": float(r[4]),
                "id_pedido": int(r[5]) if r[5] is not None else None,
                "id_factura": int(r[6]) if r[6] is not None else None,
            }
            for r in rows
        ],
    }


def _saldo_cuenta(conn: duckdb.DuckDBPyConnection, codigo: str) -> float:
    row = conn.execute(
        """
        SELECT pc.tipo, CAST(COALESCE(SUM(al.debe), 0) AS DOUBLE), CAST(COALESCE(SUM(al.haber), 0) AS DOUBLE)
        FROM plan_cuentas pc
        LEFT JOIN asiento_lineas al ON al.id_cuenta = pc.id_cuenta
        WHERE pc.codigo = ?
        GROUP BY pc.tipo
        """,
        [codigo],
    ).fetchone()
    if not row:
        return 0.0
    debe, haber = float(row[1]), float(row[2])
    return round(debe - haber, 2) if row[0] in ("activo", "costo") else round(haber - debe, 2)


def valor_inventario_fisico(conn: duckdb.DuckDBPyConnection) -> float:
    if not table_exists(conn, "stock_almacen"):
        return 0.0
    row = conn.execute(
        """
        SELECT CAST(SUM(sa.cantidad_disponible * COALESCE(pr.costo_estandar, dp.precio_mayorista * 0.4, 0)) AS DOUBLE)
        FROM stock_almacen sa
        JOIN dim_producto dp ON dp.id_producto = sa.id_producto
        LEFT JOIN productos pr ON pr.id_producto = sa.id_producto
        """
    ).fetchone()
    return round(float(row[0] or 0), 2)


def regularizar_inventario(
    conn: duckdb.DuckDBPyConnection,
    *,
    saldo_objetivo: Optional[float] = None,
    nota: str = "",
) -> dict[str, Any]:
    """Ajusta Inventario (1301) al valor en bodega o al objetivo indicado."""
    objetivo = float(saldo_objetivo) if saldo_objetivo is not None else valor_inventario_fisico(conn)
    saldo_actual = _saldo_cuenta(conn, CUENTAS["inventario"])
    diff = round(objetivo - saldo_actual, 2)
    if abs(diff) < 0.01:
        return {
            "ajustado": False,
            "saldo_anterior": saldo_actual,
            "saldo_nuevo": saldo_actual,
            "monto": 0.0,
            "detalle": "El inventario contable ya coincide con el objetivo.",
        }
    id_inv = _cuenta_id(conn, CUENTAS["inventario"])
    id_contra = _cuenta_id(conn, CUENTAS["pagos_externos"])
    if diff > 0:
        lineas = [(id_inv, diff, 0.0), (id_contra, 0.0, diff)]
    else:
        monto = abs(diff)
        lineas = [(id_inv, 0.0, monto), (id_contra, monto, 0.0)]
    desc = f"Regularización inventario: {nota.strip() or 'ajuste vs stock físico'}"
    id_asiento = _crear_asiento(conn, id_pedido=None, id_factura=None, descripcion=desc[:240], lineas=lineas)
    return {
        "ajustado": True,
        "id_asiento": id_asiento,
        "saldo_anterior": saldo_actual,
        "saldo_nuevo": objetivo,
        "monto": abs(diff),
        "detalle": desc,
    }


def regularizar_costo_ventas(
    conn: duckdb.DuckDBPyConnection,
    *,
    margen_bruto_pct: float = 42.0,
    nota: str = "",
) -> dict[str, Any]:
    """Reduce COGS (5101) si supera los ingresos para evitar utilidad bruta negativa irreal."""
    ingresos = _saldo_cuenta(conn, CUENTAS["ingresos"]) + _saldo_cuenta(conn, CUENTAS["ingresos_netos"])
    costo_actual = _saldo_cuenta(conn, CUENTAS["costo"])
    if ingresos <= 0 or costo_actual <= ingresos:
        return {
            "ajustado": False,
            "saldo_anterior": costo_actual,
            "saldo_nuevo": costo_actual,
            "monto": 0.0,
            "detalle": "El costo de ventas no requiere ajuste.",
        }
    objetivo = round(ingresos * (1 - margen_bruto_pct / 100.0), 2)
    diff = round(objetivo - costo_actual, 2)
    if abs(diff) < 0.01:
        return {
            "ajustado": False,
            "saldo_anterior": costo_actual,
            "saldo_nuevo": costo_actual,
            "monto": 0.0,
            "detalle": "El costo de ventas ya está alineado.",
        }
    id_costo = _cuenta_id(conn, CUENTAS["costo"])
    id_contra = _cuenta_id(conn, CUENTAS["pagos_externos"])
    monto = abs(diff)
    lineas = [(id_costo, 0.0, monto), (id_contra, monto, 0.0)]
    desc = f"Regularización costo ventas: {nota.strip() or 'alineación con ingresos'}"
    id_asiento = _crear_asiento(conn, id_pedido=None, id_factura=None, descripcion=desc[:240], lineas=lineas)
    return {
        "ajustado": True,
        "id_asiento": id_asiento,
        "saldo_anterior": costo_actual,
        "saldo_nuevo": objetivo,
        "monto": monto,
        "detalle": desc,
    }


def reparar_saldos_negativos(conn: duckdb.DuckDBPyConnection) -> dict[str, Any]:
    """Corrige caja/inventario negativos y COGS desproporcionado (idempotente)."""
    resultado: dict[str, Any] = {"ajustes": []}
    caja = _saldo_cuenta(conn, CUENTAS["caja"])
    if caja < -0.01:
        r = regularizar_caja(conn, saldo_objetivo=0.0, nota="Auto-reparación caja negativa")
        if r.get("ajustado"):
            resultado["ajustes"].append({"cuenta": "1101", **r})
    inventario = _saldo_cuenta(conn, CUENTAS["inventario"])
    if inventario < -0.01:
        r = regularizar_inventario(conn, nota="Auto-reparación inventario negativo")
        if r.get("ajustado"):
            resultado["ajustes"].append({"cuenta": "1301", **r})
    ingresos = _saldo_cuenta(conn, CUENTAS["ingresos"]) + _saldo_cuenta(conn, CUENTAS["ingresos_netos"])
    costo = _saldo_cuenta(conn, CUENTAS["costo"])
    if ingresos > 0 and costo > ingresos:
        r = regularizar_costo_ventas(conn, nota="Auto-reparación utilidad bruta")
        if r.get("ajustado"):
            resultado["ajustes"].append({"cuenta": "5101", **r})
    resultado["reparado"] = bool(resultado["ajustes"])
    return resultado


def resumen_financiero(conn: duckdb.DuckDBPyConnection) -> dict[str, Any]:
    sincronizar_asientos_pedidos_pagados(conn)
    try:
        reparar_saldos_negativos(conn)
    except Exception as exc:
        logger.warning("Reparación de saldos negativos omitida: %s", exc)
    rows = conn.execute(
        """
        SELECT pc.codigo, pc.nombre, pc.tipo,
               CAST(SUM(al.debe) AS DOUBLE), CAST(SUM(al.haber) AS DOUBLE)
        FROM asiento_lineas al
        JOIN plan_cuentas pc ON pc.id_cuenta = al.id_cuenta
        GROUP BY pc.codigo, pc.nombre, pc.tipo ORDER BY pc.codigo
        """
    ).fetchall()
    cuentas = []
    for r in rows:
        debe, haber = float(r[3]), float(r[4])
        saldo = debe - haber if r[2] in ("activo", "costo") else haber - debe
        cuentas.append({
            "codigo": r[0], "nombre": r[1], "tipo": r[2],
            "debe": debe, "haber": haber, "saldo": round(saldo, 2),
        })
    n_asientos = int(conn.execute("SELECT COUNT(*) FROM asientos_contables").fetchone()[0])
    return {"n_asientos": n_asientos, "cuentas": cuentas}


def regularizar_caja(
    conn: duckdb.DuckDBPyConnection,
    *,
    saldo_objetivo: float = 0.0,
    nota: str = "",
) -> dict[str, Any]:
    """Ajusta la cuenta Caja (1101) hasta `saldo_objetivo` vía asiento de regularización.

    Contra: Pagos externos / financiamiento (3001). Útil cuando pagos de OC
    dejaron la caja en negativo por pruebas o desfase de cobros.
    """
    resumen = resumen_financiero(conn)
    caja = next((c for c in resumen["cuentas"] if c["codigo"] == CUENTAS["caja"]), None)
    saldo_actual = float(caja["saldo"]) if caja else 0.0
    diff = round(float(saldo_objetivo) - saldo_actual, 2)
    if abs(diff) < 0.01:
        return {
            "ajustado": False,
            "saldo_anterior": saldo_actual,
            "saldo_nuevo": saldo_actual,
            "monto": 0.0,
            "detalle": "La caja ya está en el saldo objetivo.",
        }

    id_caja = _cuenta_id(conn, CUENTAS["caja"])
    id_contra = _cuenta_id(conn, CUENTAS["pagos_externos"])
    if diff > 0:
        lineas = [(id_caja, diff, 0.0), (id_contra, 0.0, diff)]
        sentido = "aporte"
    else:
        monto = abs(diff)
        lineas = [(id_caja, 0.0, monto), (id_contra, monto, 0.0)]
        sentido = "retiro"

    desc = f"Regularización caja ({sentido}): {nota.strip() or 'ajuste manual a saldo objetivo'}"
    id_asiento = _crear_asiento(
        conn,
        id_pedido=None,
        id_factura=None,
        descripcion=desc[:240],
        lineas=lineas,
    )
    nuevo = resumen_financiero(conn)
    caja_n = next((c for c in nuevo["cuentas"] if c["codigo"] == CUENTAS["caja"]), None)
    return {
        "ajustado": True,
        "id_asiento": id_asiento,
        "saldo_anterior": saldo_actual,
        "saldo_nuevo": float(caja_n["saldo"]) if caja_n else float(saldo_objetivo),
        "monto": abs(diff),
        "sentido": sentido,
        "detalle": desc,
    }
