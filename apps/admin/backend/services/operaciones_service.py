"""
operaciones_service.py — KPIs y alertas del Panel de Operaciones.

Cruza compras, inventario, pedidos, logística y contabilidad para dar una
visión operativa del día a día (aprobaciones, recepciones, stock, despachos
y deuda a proveedores).
"""

from __future__ import annotations

from typing import Any

import duckdb

from shared.services.contabilidad_service import resumen_financiero


def _count(conn: duckdb.DuckDBPyConnection, sql: str, *params: Any) -> int:
    r = conn.execute(sql, list(params)).fetchone()
    return int(r[0] or 0) if r else 0


def panel_operaciones(conn: duckdb.DuckDBPyConnection) -> dict[str, Any]:
    kpis: dict[str, Any] = {}

    if conn.execute(
        "SELECT COUNT(*) FROM information_schema.tables WHERE table_name = 'ordenes_compra'"
    ).fetchone()[0]:
        kpis["oc_por_aprobar"] = _count(
            conn, "SELECT COUNT(*) FROM ordenes_compra WHERE estado = 'borrador'"
        )
        kpis["oc_por_recibir"] = _count(
            conn, "SELECT COUNT(*) FROM ordenes_compra WHERE estado IN ('aprobada', 'parcialmente_recibida')"
        )
        kpis["oc_recibidas_parciales"] = _count(
            conn, "SELECT COUNT(*) FROM ordenes_compra WHERE estado = 'parcialmente_recibida'"
        )
    else:
        kpis.update(oc_por_aprobar=0, oc_por_recibir=0, oc_recibidas_parciales=0)

    # Stock bajo
    try:
        from backend.services import inventario_service

        alertas = inventario_service.alertas_activas(conn)
        kpis["stock_bajo"] = len(alertas)
        kpis["stock_bajo_lista"] = [
            {"id_producto": a["id_producto"], "producto": a["producto"],
             "disponible": a["disponible"], "umbral_minimo": a["umbral_minimo"]}
            for a in alertas[:10]
        ]
    except Exception:
        kpis.update(stock_bajo=0, stock_bajo_lista=[])

    # Pedidos operativos sin despachar
    try:
        from backend.services import logistica_service

        pedidos = logistica_service.listar_pedidos_envio(conn, limit=1000)
    except Exception:
        pedidos = []
    con_envio = {p.get("id_pedido") for p in pedidos if p.get("tiene_envio")}
    kpis["pedidos_operativos"] = len(pedidos)
    kpis["pedidos_sin_despachar"] = len([p for p in pedidos if not p.get("tiene_envio")])
    kpis["despachos_sin_entrega"] = len(
        [p for p in pedidos if p.get("tiene_envio") and p.get("estado_envio") not in ("entregado",)]
    )

    # Finanzas / contabilidad
    try:
        caja = 0.0
        try:
            resumen = resumen_financiero(conn)
            for c in resumen.get("cuentas", []):
                if c.get("codigo") == "1101":
                    caja = c.get("saldo", 0)
        except Exception:
            resumen = {}
            caja = 0.0
        kpis["caja"] = round(caja, 2)

        from backend.services import compras_service

        cxp = compras_service.cuentas_por_pagar(conn)
        kpis["cuentas_por_pagar"] = round(cxp.get("total_pendiente", 0.0) or 0.0, 2)
        if conn.execute(
            "SELECT COUNT(*) FROM information_schema.tables WHERE table_name = 'fact_compras'"
        ).fetchone()[0]:
            r = conn.execute(
                "SELECT CAST(COALESCE(SUM(costo), 0) AS DOUBLE) FROM fact_compras "
                "WHERE strftime(fecha, '%Y-%m') = strftime(current_timestamp, '%Y-%m')"
            ).fetchone()
            kpis["compras_del_periodo"] = round(float(r[0] or 0), 2)
        else:
            kpis["compras_del_periodo"] = 0.0
    except Exception:
        kpis.update(caja=0.0, cuentas_por_pagar=0.0, compras_del_periodo=0.0)

    # Efectivo de la caja mensual (asientos 'cobro' en el mes)
    try:
        kpis["ventas_del_periodo"] = _count(
            conn,
            "SELECT COALESCE(SUM(CAST(total AS DOUBLE)),0) FROM asientos_contables "
            "WHERE descripcion LIKE 'cobro:%' AND strftime(fecha, '%Y-%m') = strftime(current_timestamp, '%Y-%m')",
        )
    except Exception:
        kpis["ventas_del_periodo"] = 0.0

    return {"kpis": kpis, "pedidos": pedidos[:50], "alertas_stock": kpis.get("stock_bajo_lista", [])}