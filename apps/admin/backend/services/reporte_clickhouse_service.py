"""
reporte_clickhouse_service.py — Informes desde ClickHouse (publicado por Airflow).

DAG: etl_03_clickhouse_publish. Si ClickHouse no está disponible, el caller
debe hacer fallback a DuckDB.
"""
from __future__ import annotations

import logging
import time
from typing import Any, Optional

from shared.services.clickhouse_service import clickhouse_disponible, ejecutar_query, estado_almacen

logger = logging.getLogger(__name__)

_TITULOS: dict[str, str] = {
    "ventas": "Reporte de Ventas (Ejecutivo)",
    "ventas-detalle": "Reporte de Ventas — Detalle Completo",
    "inventario-valorizado": "Inventario Valorizado",
    "pedidos-por-estado": "Pedidos por Estado",
    "clientes-cxc": "Clientes y Cuentas por Cobrar",
    "rentabilidad-producto": "Rentabilidad por Producto",
    "resumen-financiero": "Resumen Financiero",
    "compras": "Reporte de Compras",
    "stock-bajo": "Stock Bajo Umbral",
    "cuentas-por-pagar": "Cuentas por Pagar",
    "recepciones": "Recepciones de Compra",
    "kardex": "Kardex de Inventario",
    "proveedores": "Directorio de Proveedores",
    "informe-gerencial": "Informe Gerencial",
    "informe-operativo": "Informe Operativo",
    "informe-comercial": "Informe Comercial",
    "informe-logistico": "Informe Logístico",
    "informe-financiero": "Informe Financiero",
}


def _fmt_money(v: float | int | None) -> str:
    return f"${float(v or 0):,.2f}"


def _fmt_margen(profit: float, revenue: float) -> str:
    if not revenue:
        return "—"
    return f"{(profit / revenue) * 100:.1f}%"


def _esc(s: Any) -> str:
    return str(s or "").replace("'", "\\'")


def _almacen_nombre(f: dict[str, Any]) -> str | None:
    alm = f.get("almacen")
    if alm in (None, "", 0):
        return None
    try:
        rows = ejecutar_query(
            f"SELECT almacen FROM dwh_inventario WHERE id_almacen = {int(alm)} LIMIT 1"
        )
        if rows:
            return str(rows[0].get("almacen") or "")
    except (ValueError, TypeError):
        return str(alm)
    return str(alm) if alm else None


def _subtitulo(f: dict[str, Any]) -> str:
    parts = [f"{k}={v}" for k, v in f.items() if v]
    return " · ".join(parts) if parts else "Sin filtros"


def _fecha_cond(campo: str, f: dict[str, Any]) -> str:
    conds = ["1=1"]
    if f.get("desde"):
        conds.append(f"{campo} >= toDate('{_esc(f['desde'])}')")
    if f.get("hasta"):
        conds.append(f"{campo} <= toDate('{_esc(f['hasta'])}')")
    return " AND ".join(conds)


def _filtro_ventas(f: dict[str, Any]) -> str:
    conds = [_fecha_cond("order_date", f)]
    if f.get("region"):
        conds.append(f"region = '{_esc(f['region'])}'")
    if f.get("country"):
        conds.append(f"country = '{_esc(f['country'])}'")
    if f.get("sales_channel"):
        conds.append(f"sales_channel = '{_esc(f['sales_channel'])}'")
    if f.get("origen"):
        conds.append(f"origen = '{_esc(f['origen'])}'")
    return " AND ".join(conds)


def _meta(nombre: str, f: dict[str, Any], *, tipo: str = "tabla") -> dict[str, Any]:
    return {
        "tipo": tipo,
        "nombre": nombre,
        "titulo": _TITULOS.get(nombre, nombre),
        "subtitulo": _subtitulo(f),
        "motor": "ClickHouse",
        "orquestacion": "Airflow · etl_03_clickhouse_publish",
    }


def _tabla(nombre: str, f: dict[str, Any], headers: list[str], rows: list[list[Any]], *, totales: str = "", kpis: list | None = None) -> dict[str, Any]:
    return {
        **_meta(nombre, f),
        "headers": headers,
        "rows": rows,
        "totales": totales,
        "kpis": kpis or [],
    }


def _kpis_ventas(f: dict[str, Any]) -> list[dict[str, str]]:
    where = _filtro_ventas(f)
    rows = ejecutar_query(
        f"""
        SELECT sum(units_sold) AS u, sum(total_revenue) AS rev,
               sum(total_profit) AS profit, count() AS lineas
        FROM dwh_ventas WHERE {where}
        """
    )
    r = rows[0] if rows else {}
    rev = float(r.get("rev") or 0)
    profit = float(r.get("profit") or 0)
    return [
        {"label": "Unidades", "value": f"{int(r.get('u') or 0):,}"},
        {"label": "Ingresos", "value": _fmt_money(rev)},
        {"label": "Profit", "value": _fmt_money(profit)},
        {"label": "Margen", "value": _fmt_margen(profit, rev)},
    ]


def _ventas_por_dim(col: str, label: str, f: dict[str, Any]) -> tuple[list[str], list[list[Any]]]:
    where = _filtro_ventas(f)
    rows = ejecutar_query(
        f"""
        SELECT {col} AS dim,
               sum(units_sold) AS u,
               sum(total_revenue) AS rev,
               sum(total_profit) AS profit
        FROM dwh_ventas
        WHERE {where}
        GROUP BY dim
        ORDER BY rev DESC
        LIMIT 100
        """
    )
    headers = [label, "Unidades", "Ingresos", "Profit", "Margen"]
    data = [
        [
            r.get("dim") or "—",
            int(r.get("u") or 0),
            _fmt_money(r.get("rev")),
            _fmt_money(r.get("profit")),
            _fmt_margen(float(r.get("profit") or 0), float(r.get("rev") or 0)),
        ]
        for r in rows
    ]
    return headers, data


def _vista_ventas_detalle(f: dict[str, Any]) -> dict[str, Any]:
    where = _filtro_ventas(f)
    lim = int(f.get("limite") or 500)
    rows = ejecutar_query(
        f"""
        SELECT region, country, item_type, order_date, order_id,
               units_sold, total_revenue, total_profit
        FROM dwh_ventas
        WHERE {where}
        ORDER BY order_date DESC, order_id DESC
        LIMIT {lim}
        """
    )
    headers = ["Región", "País", "Producto", "Fecha", "Order ID", "Unidades", "Ingresos", "Profit"]
    data = [
        [
            r.get("region") or "—",
            r.get("country") or "—",
            r.get("item_type") or "—",
            str(r.get("order_date") or "")[:10],
            int(r.get("order_id") or 0),
            int(r.get("units_sold") or 0),
            _fmt_money(r.get("total_revenue")),
            _fmt_money(r.get("total_profit")),
        ]
        for r in rows
    ]
    return _tabla("ventas-detalle", f, headers, data, totales=f"{len(rows)} líneas", kpis=_kpis_ventas(f))


def _vista_compras(f: dict[str, Any]) -> dict[str, Any]:
    where = _fecha_cond("fecha", f)
    if f.get("estado"):
        where += f" AND estado = '{_esc(f['estado'])}'"
    rows = ejecutar_query(
        f"""
        SELECT numero, proveedor, fecha, estado, total_compra
        FROM dwh_compras
        WHERE {where}
        ORDER BY fecha DESC
        LIMIT {int(f.get('limite') or 500)}
        """
    )
    headers = ["Número", "Proveedor", "Fecha", "Estado", "Total"]
    data = [
        [r.get("numero"), r.get("proveedor"), str(r.get("fecha"))[:10], r.get("estado"), _fmt_money(r.get("total_compra"))]
        for r in rows
    ]
    total = sum(float(r.get("total_compra") or 0) for r in rows)
    return _tabla(
        "compras", f, headers, data,
        totales=f"Total compras: {_fmt_money(total)} ({len(rows)} OC)",
        kpis=[{"label": "Órdenes", "value": str(len(rows))}, {"label": "Monto total", "value": _fmt_money(total)}],
    )


def _vista_proveedores(f: dict[str, Any]) -> dict[str, Any]:
    rows = ejecutar_query(
        f"""
        SELECT proveedor, pais, total_comprado, num_oc
        FROM dwh_proveedores
        ORDER BY total_comprado DESC
        LIMIT {int(f.get('limite') or 200)}
        """
    )
    headers = ["Proveedor", "País", "Total comprado", "N° OC"]
    data = [
        [r.get("proveedor"), r.get("pais"), _fmt_money(r.get("total_comprado")), int(r.get("num_oc") or 0)]
        for r in rows
    ]
    return _tabla("proveedores", f, headers, data, totales=f"{len(rows)} proveedores")


def _vista_clientes_cxc(f: dict[str, Any]) -> dict[str, Any]:
    rows = ejecutar_query(
        f"""
        SELECT nombre_cliente, pais, total_comprado, total_pagado, cxc
        FROM dwh_clientes
        ORDER BY cxc DESC
        LIMIT {int(f.get('limite') or 200)}
        """
    )
    headers = ["Cliente", "País", "Comprado", "Pagado", "CxC"]
    total_cxc = 0.0
    data = []
    for r in rows:
        cxc = float(r.get("cxc") or 0)
        total_cxc += cxc
        data.append([
            r.get("nombre_cliente"),
            r.get("pais") or "—",
            _fmt_money(r.get("total_comprado")),
            _fmt_money(r.get("total_pagado")),
            _fmt_money(cxc),
        ])
    return _tabla(
        "clientes-cxc", f, headers, data,
        totales=f"CxC total estimada: {_fmt_money(total_cxc)}",
        kpis=[{"label": "Clientes", "value": str(len(rows))}, {"label": "CxC total", "value": _fmt_money(total_cxc)}],
    )


def _vista_rentabilidad(f: dict[str, Any]) -> dict[str, Any]:
    where = _filtro_ventas(f)
    rows = ejecutar_query(
        f"""
        SELECT item_type,
               sum(units_sold) AS u,
               sum(total_revenue) AS rev,
               sum(total_cost) AS cost,
               sum(total_profit) AS profit
        FROM dwh_ventas
        WHERE {where}
          AND lower(item_type) NOT IN ('peperoni', 'pepperoni')
        GROUP BY item_type
        HAVING abs(rev) >= 0.01 OR abs(profit) >= 0.01
        ORDER BY profit DESC
        LIMIT {int(f.get('limite') or 200)}
        """
    )
    headers = ["Categoría", "Unidades", "Ingresos", "Costos", "Profit", "Margen"]
    data = [
        [
            r.get("item_type") or "—",
            int(r.get("u") or 0),
            _fmt_money(r.get("rev")),
            _fmt_money(r.get("cost")),
            _fmt_money(r.get("profit")),
            _fmt_margen(float(r.get("profit") or 0), float(r.get("rev") or 0)),
        ]
        for r in rows
    ]
    return _tabla("rentabilidad-producto", f, headers, data, totales=f"{len(rows)} categorías", kpis=_kpis_ventas(f))


def _vista_inventario(f: dict[str, Any]) -> dict[str, Any]:
    almacen = int(f.get("almacen") or 0)
    where = "1=1"
    if almacen:
        where = f"id_almacen = {almacen}"
    if f.get("producto"):
        where += f" AND lower(producto) LIKE '%{_esc(str(f['producto']).lower())}%'"
    rows = ejecutar_query(
        f"""
        SELECT producto, categoria, almacen, stock, costo_unit, valor
        FROM dwh_inventario
        WHERE {where}
        ORDER BY producto
        LIMIT 2000
        """
    )
    headers = ["Producto", "Categoría", "Stock", "Costo u.", "Valor"]
    data = []
    total_val = 0.0
    for r in rows:
        val = float(r.get("valor") or 0)
        total_val += val
        data.append([
            r.get("producto"),
            r.get("categoria"),
            f"{float(r.get('stock') or 0):,.0f}",
            _fmt_money(r.get("costo_unit")),
            _fmt_money(val),
        ])
    return _tabla(
        "inventario-valorizado", f, headers, data,
        totales=f"Valor total inventario: {_fmt_money(total_val)}",
        kpis=[{"label": "Productos", "value": str(len(rows))}, {"label": "Valor", "value": _fmt_money(total_val)}],
    )


def _vista_stock_bajo(f: dict[str, Any]) -> dict[str, Any]:
    conds = ["1=1"]
    nombre_alm = _almacen_nombre(f)
    if nombre_alm:
        conds.append(f"almacen = '{_esc(nombre_alm)}'")
    where = " AND ".join(conds)
    rows = ejecutar_query(
        f"""
        SELECT producto, almacen, disponible, umbral, deficit
        FROM dwh_stock_bajo
        WHERE {where}
        ORDER BY deficit DESC
        LIMIT 500
        """
    )
    headers = ["Producto", "Almacén", "Disponible", "Umbral", "Déficit"]
    data = [
        [
            r.get("producto"),
            r.get("almacen"),
            f"{float(r.get('disponible') or 0):,.2f}",
            f"{float(r.get('umbral') or 0):,.2f}",
            f"{float(r.get('deficit') or 0):,.2f}",
        ]
        for r in rows
    ]
    return _tabla("stock-bajo", f, headers, data, totales=f"{len(rows)} productos bajo umbral")


def _vista_pedidos_estado(f: dict[str, Any]) -> dict[str, Any]:
    if f.get("desde") or f.get("hasta"):
        conds = ["1=1"]
        if f.get("desde"):
            conds.append(f"fecha >= toDate('{_esc(f['desde'])}')")
        if f.get("hasta"):
            conds.append(f"fecha <= toDate('{_esc(f['hasta'])}')")
        where = " AND ".join(conds)
        rows = ejecutar_query(
            f"""
            SELECT estado, count() AS cantidad, sum(monto) AS monto_total
            FROM dwh_pedidos_pendientes
            WHERE {where}
            GROUP BY estado
            ORDER BY cantidad DESC
            """
        )
    else:
        rows = ejecutar_query(
            """
            SELECT estado, cantidad, monto_total
            FROM dwh_pedidos_estado
            ORDER BY cantidad DESC
            """
        )
    headers = ["Estado", "Cantidad", "Monto total"]
    data = [[r.get("estado"), int(r.get("cantidad") or 0), _fmt_money(r.get("monto_total"))] for r in rows]
    return _tabla("pedidos-por-estado", f, headers, data)


def _vista_recepciones(f: dict[str, Any]) -> dict[str, Any]:
    where = _fecha_cond("fecha", f)
    if f.get("estado"):
        where += f" AND estado = '{_esc(f['estado'])}'"
    rows = ejecutar_query(
        f"""
        SELECT id_recepcion, oc_numero, proveedor, fecha, estado, lineas, valor_recibido
        FROM dwh_recepciones
        WHERE {where}
        ORDER BY id_recepcion DESC
        LIMIT 500
        """
    )
    estado_label = {"completa": "Completa", "parcial": "Parcial"}
    headers = ["ID", "OC", "Proveedor", "Fecha", "Estado", "Líneas", "Valor recibido"]
    data = [
        [
            int(r.get("id_recepcion") or 0),
            r.get("oc_numero"),
            r.get("proveedor"),
            str(r.get("fecha") or "")[:10],
            estado_label.get(r.get("estado"), r.get("estado")),
            int(r.get("lineas") or 0),
            _fmt_money(r.get("valor_recibido")),
        ]
        for r in rows
    ]
    return _tabla("recepciones", f, headers, data, totales=f"{len(rows)} recepciones")


def _vista_kardex(f: dict[str, Any]) -> dict[str, Any]:
    conds = ["1=1"]
    if f.get("desde"):
        conds.append(f"toDate(fecha) >= toDate('{_esc(f['desde'])}')")
    if f.get("hasta"):
        conds.append(f"toDate(fecha) <= toDate('{_esc(f['hasta'])}')")
    if f.get("producto"):
        conds.append(f"lower(producto) LIKE '%{_esc(str(f['producto']).lower())}%'")
    nombre_alm = _almacen_nombre(f)
    if nombre_alm:
        conds.append(f"almacen = '{_esc(nombre_alm)}'")
    where = " AND ".join(conds)
    rows = ejecutar_query(
        f"""
        SELECT fecha, tipo, producto, almacen, cantidad, referencia
        FROM dwh_movimientos
        WHERE {where}
        ORDER BY fecha DESC
        LIMIT 1000
        """
    )
    headers = ["Fecha", "Tipo", "Producto", "Almacén", "Cantidad", "Referencia"]
    data = [
        [
            str(r.get("fecha") or "")[:19],
            r.get("tipo"),
            r.get("producto"),
            r.get("almacen"),
            float(r.get("cantidad") or 0),
            r.get("referencia") or "",
        ]
        for r in rows
    ]
    return _tabla("kardex", f, headers, data, totales=f"{len(rows)} movimientos")


def _vista_resumen_financiero(f: dict[str, Any]) -> dict[str, Any]:
    kpis = _kpis_ventas(f)
    rows = ejecutar_query(
        """
        SELECT codigo, nombre, tipo, debe, haber, saldo
        FROM dwh_finanzas
        ORDER BY abs(saldo) DESC
        LIMIT 15
        """
    )
    headers = ["Cuenta", "Nombre", "Tipo", "Debe", "Haber", "Saldo"]
    data = [
        [
            r.get("codigo"),
            r.get("nombre"),
            r.get("tipo"),
            _fmt_money(r.get("debe")),
            _fmt_money(r.get("haber")),
            _fmt_money(r.get("saldo")),
        ]
        for r in rows
    ]
    resumen = [["Ventas (ingresos CH)", kpis[1]["value"]], ["Profit", kpis[2]["value"]], ["Margen", kpis[3]["value"]]]
    return {
        **_meta("resumen-financiero", f, tipo="compuesto"),
        "kpis": kpis,
        "secciones": [
            {"titulo": "Indicadores de ventas", "headers": ["Métrica", "Valor"], "rows": resumen},
            {"titulo": "Saldos por cuenta (top 15)", "headers": headers, "rows": data},
        ],
    }


def _vista_cuentas_por_pagar(f: dict[str, Any]) -> dict[str, Any]:
    try:
        n = int((ejecutar_query("SELECT count() AS n FROM dwh_cuentas_por_pagar") or [{}])[0].get("n") or 0)
    except Exception:
        n = 0
    if n > 0:
        rows = ejecutar_query(
            """
            SELECT proveedor, ruc, comprado, recibido, pagado, pendiente
            FROM dwh_cuentas_por_pagar
            ORDER BY pendiente DESC
            LIMIT 200
            """
        )
        headers = ["Proveedor", "RUC", "Comprado", "Recibido", "Pagado", "Pendiente"]
        total = 0.0
        data = []
        for r in rows:
            pend = float(r.get("pendiente") or 0)
            total += pend
            data.append([
                r.get("proveedor"),
                r.get("ruc") or "—",
                _fmt_money(r.get("comprado")),
                _fmt_money(r.get("recibido")),
                _fmt_money(r.get("pagado")),
                _fmt_money(pend),
            ])
        return _tabla("cuentas-por-pagar", f, headers, data, totales=f"Total pendiente: {_fmt_money(total)}")

    conds = ["1=1"]
    if f.get("desde"):
        conds.append(f"fecha >= toDate('{_esc(f['desde'])}')")
    if f.get("hasta"):
        conds.append(f"fecha <= toDate('{_esc(f['hasta'])}')")
    where = " AND ".join(conds)
    rows = ejecutar_query(
        f"""
        SELECT proveedor,
               sum(total_compra) AS comprado,
               count() AS num_oc,
               sumIf(total_compra, lower(estado) NOT IN ('pagada', 'cancelada', 'cerrada')) AS pendiente
        FROM dwh_compras
        WHERE {where}
        GROUP BY proveedor
        HAVING pendiente > 0
        ORDER BY pendiente DESC
        LIMIT 200
        """
    )
    headers = ["Proveedor", "Total comprado", "N° OC", "Pendiente est."]
    total = 0.0
    data = []
    for r in rows:
        pend = float(r.get("pendiente") or 0)
        total += pend
        data.append([
            r.get("proveedor"),
            _fmt_money(r.get("comprado")),
            int(r.get("num_oc") or 0),
            _fmt_money(pend),
        ])
    return _tabla(
        "cuentas-por-pagar", f, headers, data,
        totales=f"Total pendiente (OC abiertas): {_fmt_money(total)}",
    )


def _tesoreria_rows() -> list[list[str]]:
    rows = ejecutar_query("SELECT metrica, valor FROM dwh_tesoreria ORDER BY metrica")
    return [[r.get("metrica") or "—", r.get("valor") or "—"] for r in rows]


def _pedidos_sin_despacho(limite: int = 50) -> tuple[list[str], list[list[Any]]]:
    rows = ejecutar_query(
        f"""
        SELECT numero, cliente, estado, monto
        FROM dwh_pedidos_pendientes
        WHERE sin_envio = 1 AND estado IN ('pagado', 'preparando', 'enviado')
        ORDER BY fecha DESC
        LIMIT {limite}
        """
    )
    headers = ["Nº pedido", "Cliente", "Estado", "Monto"]
    data = [[r.get("numero"), r.get("cliente"), r.get("estado"), _fmt_money(r.get("monto"))] for r in rows]
    return headers, data


def _vista_ventas_compuesto(f: dict[str, Any]) -> dict[str, Any]:
    h_pais, r_pais = _ventas_por_dim("country", "País", f)
    h_can, r_can = _ventas_por_dim("sales_channel", "Canal", f)
    h_ori, r_ori = _ventas_por_dim("origen", "Origen", f)
    h_mes, r_mes = _ventas_por_dim("formatDateTime(order_date, '%Y-%m')", "Mes", f)
    secciones = [
        {"titulo": "Ventas por país", "headers": h_pais, "rows": r_pais},
        {"titulo": "Ventas por canal", "headers": h_can, "rows": r_can},
        {"titulo": "Ventas por origen", "headers": h_ori, "rows": r_ori},
        {"titulo": "Ventas por mes", "headers": h_mes, "rows": r_mes},
    ]
    return {**_meta("ventas", f, tipo="compuesto"), "kpis": _kpis_ventas(f), "secciones": secciones}


def _vista_informe_comercial(f: dict[str, Any]) -> dict[str, Any]:
    h_can, r_can = _ventas_por_dim("sales_channel", "Canal", f)
    h_ori, r_ori = _ventas_por_dim("origen", "Origen", f)
    h_ren, r_ren = _ventas_por_dim("item_type", "Categoría", f)
    cxc = _vista_clientes_cxc({**f, "limite": 10})
    ped_v = _vista_pedidos_estado(f)
    h_ped, r_ped = ped_v["headers"], ped_v["rows"]
    secciones = [
        {"titulo": "Ventas por canal", "headers": h_can, "rows": r_can},
        {"titulo": "Ventas por origen (histórico vs portal)", "headers": h_ori, "rows": r_ori},
        {"titulo": "Rentabilidad por categoría (top 15)", "headers": h_ren, "rows": r_ren[:15]},
        {"titulo": "Pedidos por estado", "headers": h_ped, "rows": r_ped},
        {
            "titulo": "Clientes con cuentas por cobrar (top 10)",
            "headers": cxc["headers"],
            "rows": cxc["rows"][:10],
            "totales": cxc.get("totales"),
        },
    ]
    return {**_meta("informe-comercial", f, tipo="compuesto"), "kpis": _kpis_ventas(f), "secciones": secciones}


def _vista_informe_gerencial(f: dict[str, Any]) -> dict[str, Any]:
    h_reg, r_reg = _ventas_por_dim("region", "Región", f)
    h_pais, r_pais = _ventas_por_dim("country", "País", f)
    prov = _vista_proveedores({**f, "limite": 10})
    cxc = _vista_clientes_cxc({**f, "limite": 10})
    sb = _vista_stock_bajo(f)
    secciones = [
        {"titulo": "Ingresos por región", "headers": h_reg, "rows": r_reg},
        {"titulo": "Ingresos por país (top 15)", "headers": h_pais, "rows": r_pais[:15]},
        {"titulo": "Top proveedores por compras", "headers": prov["headers"], "rows": prov["rows"]},
        {"titulo": "Clientes con mayor CxC", "headers": cxc["headers"], "rows": cxc["rows"]},
        {"titulo": "Alertas de stock bajo", "headers": sb["headers"], "rows": sb["rows"], "totales": sb.get("totales")},
    ]
    return {**_meta("informe-gerencial", f, tipo="compuesto"), "kpis": _kpis_ventas(f), "secciones": secciones}


def _vista_informe_financiero(f: dict[str, Any]) -> dict[str, Any]:
    cxc = _vista_clientes_cxc({**f, "limite": 10})
    prov = _vista_proveedores({**f, "limite": 10})
    compras = _vista_compras({**f, "limite": 10})
    fin = ejecutar_query(
        "SELECT codigo, nombre, tipo, debe, haber, saldo FROM dwh_finanzas ORDER BY abs(saldo) DESC LIMIT 12"
    )
    h_fin = ["Cuenta", "Nombre", "Tipo", "Debe", "Haber", "Saldo"]
    r_fin = [
        [r.get("codigo"), r.get("nombre"), r.get("tipo"), _fmt_money(r.get("debe")), _fmt_money(r.get("haber")), _fmt_money(r.get("saldo"))]
        for r in fin
    ]
    kpis = _kpis_ventas(f)
    secciones = [
        {"titulo": "Resumen de ventas (ClickHouse)", "headers": ["Métrica", "Valor"], "rows": [[k["label"], k["value"]] for k in kpis]},
        {"titulo": "Caja y tesorería", "headers": ["Métrica", "Valor"], "rows": _tesoreria_rows()},
        {"titulo": "Cuentas por cobrar — clientes (top 10)", "headers": cxc["headers"], "rows": cxc["rows"], "totales": cxc.get("totales")},
        {"titulo": "Balance de saldos por cuenta (top 12)", "headers": h_fin, "rows": r_fin},
        {"titulo": "Compras por proveedor (top 10)", "headers": prov["headers"], "rows": prov["rows"]},
        {"titulo": "Órdenes de compra recientes", "headers": compras["headers"], "rows": compras["rows"]},
    ]
    return {**_meta("informe-financiero", f, tipo="compuesto"), "kpis": kpis, "secciones": secciones}


def _vista_informe_operativo(f: dict[str, Any]) -> dict[str, Any]:
    ped = _vista_pedidos_estado(f)
    h_sd, r_sd = _pedidos_sin_despacho(50)
    rec = _vista_recepciones(f)
    sb = _vista_stock_bajo(f)
    oc = ejecutar_query(
        """
        SELECT numero, proveedor, fecha, estado, total_compra
        FROM dwh_compras
        WHERE estado = 'borrador'
        ORDER BY fecha DESC
        LIMIT 20
        """
    )
    h_ap = ["Número", "Proveedor", "Fecha", "Estado", "Total"]
    r_ap = [[r.get("numero"), r.get("proveedor"), str(r.get("fecha"))[:10], r.get("estado"), _fmt_money(r.get("total_compra"))] for r in oc]
    secciones = [
        {"titulo": "Pedidos por estado", "headers": ped["headers"], "rows": ped["rows"]},
        {"titulo": "Pedidos sin despacho (últimos 50)", "headers": h_sd, "rows": r_sd},
        {"titulo": "Recepciones recientes", "headers": rec["headers"], "rows": rec["rows"][:20], "totales": rec.get("totales")},
        {"titulo": "Órdenes de compra por aprobar", "headers": h_ap, "rows": r_ap},
        {"titulo": "Alertas de stock bajo", "headers": sb["headers"], "rows": sb["rows"], "totales": sb.get("totales")},
        {"titulo": "Resumen de tesorería", "headers": ["Métrica", "Valor"], "rows": _tesoreria_rows()},
    ]
    return {**_meta("informe-operativo", f, tipo="compuesto"), "kpis": _kpis_ventas(f), "secciones": secciones}


def _vista_informe_logistico(f: dict[str, Any]) -> dict[str, Any]:
    h_sd, r_sd = _pedidos_sin_despacho(50)
    rec = _vista_recepciones(f)
    sb = _vista_stock_bajo(f)
    mv = ejecutar_query(
        """
        SELECT tipo, count() AS n, sum(abs(cantidad)) AS u
        FROM dwh_movimientos
        GROUP BY tipo
        ORDER BY n DESC
        """
    )
    h_mv = ["Tipo", "Movimientos", "Unidades"]
    r_mv = [[r.get("tipo"), int(r.get("n") or 0), f"{float(r.get('u') or 0):,.0f}"] for r in mv]
    secciones = [
        {"titulo": "Pedidos sin despacho (últimos 50)", "headers": h_sd, "rows": r_sd},
        {"titulo": "Recepciones recientes", "headers": rec["headers"], "rows": rec["rows"][:20], "totales": rec.get("totales")},
        {"titulo": "Movimientos de inventario por tipo", "headers": h_mv, "rows": r_mv},
        {"titulo": "Alertas de stock bajo", "headers": sb["headers"], "rows": sb["rows"], "totales": sb.get("totales")},
    ]
    return {**_meta("informe-logistico", f, tipo="compuesto"), "kpis": _kpis_ventas(f), "secciones": secciones}


_HANDLERS = {
    "ventas": _vista_ventas_compuesto,
    "ventas-detalle": _vista_ventas_detalle,
    "inventario-valorizado": _vista_inventario,
    "pedidos-por-estado": _vista_pedidos_estado,
    "clientes-cxc": _vista_clientes_cxc,
    "rentabilidad-producto": _vista_rentabilidad,
    "resumen-financiero": _vista_resumen_financiero,
    "compras": _vista_compras,
    "stock-bajo": _vista_stock_bajo,
    "cuentas-por-pagar": _vista_cuentas_por_pagar,
    "recepciones": _vista_recepciones,
    "kardex": _vista_kardex,
    "proveedores": _vista_proveedores,
    "informe-comercial": _vista_informe_comercial,
    "informe-gerencial": _vista_informe_gerencial,
    "informe-financiero": _vista_informe_financiero,
    "informe-operativo": _vista_informe_operativo,
    "informe-logistico": _vista_informe_logistico,
}


def obtener_vista(nombre: str, filtros: Optional[dict[str, Any]] = None) -> Optional[dict[str, Any]]:
    """Devuelve el reporte desde ClickHouse o None si no aplica / no hay motor."""
    if not clickhouse_disponible():
        return None
    handler = _HANDLERS.get(nombre)
    if not handler:
        return None
    f = filtros or {}
    t0 = time.perf_counter()
    try:
        out = handler(f)
        out["_queryTimeMs"] = round((time.perf_counter() - t0) * 1000, 1)
        return out
    except Exception as exc:
        logger.warning("ClickHouse informe %s falló: %s", nombre, exc)
        return None


def estado_informes() -> dict[str, Any]:
    base = estado_almacen()
    base["orquestacion"] = "Airflow · etl_03_clickhouse_publish (02:30) · etl_04_reportes_dag (02:30)"
    base["informes_clickhouse"] = len(_HANDLERS)
    return base
