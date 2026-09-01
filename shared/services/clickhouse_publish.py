"""Publicación de marts DuckDB hacia ClickHouse vía HTTP."""
from __future__ import annotations

import logging
import os
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

logger = logging.getLogger(__name__)


def _cfg() -> dict[str, str]:
    return {
        "host": os.environ.get("CLICKHOUSE_HOST", "127.0.0.1"),
        "port": os.environ.get("CLICKHOUSE_PORT", "8123"),
        "user": os.environ.get("CLICKHOUSE_USER", "default"),
        "password": os.environ.get("CLICKHOUSE_PASSWORD", ""),
        "db": os.environ.get("CLICKHOUSE_DB", "globtrade_dwh"),
    }


def _esc(s: str) -> str:
    return str(s or "").replace("'", "\\'")


def _fmt_datetime(v: Any) -> str:
    """Normaliza timestamps DuckDB → DateTime ClickHouse (YYYY-MM-DD HH:MM:SS)."""
    s = str(v or "").strip()
    if not s:
        return "1970-01-01 00:00:00"
    s = s.replace("T", " ").split(".")[0].split("+")[0].strip()
    if len(s) == 10:
        s += " 00:00:00"
    return s[:19] if len(s) >= 19 else s


def _post(sql: str) -> None:
    import base64

    cfg = _cfg()
    params = {"database": cfg["db"]}
    # fact_ventas histórico puede abarcar muchos meses; limitar particiones por INSERT
    if sql.lstrip().upper().startswith("INSERT"):
        params["max_partitions_per_insert_block"] = "5000"
    url = f"http://{cfg['host']}:{cfg['port']}/?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, data=sql.encode("utf-8"), method="POST")
    if cfg.get("user") is not None:
        cred = base64.b64encode(f"{cfg['user']}:{cfg.get('password') or ''}".encode()).decode()
        req.add_header("Authorization", f"Basic {cred}")
    try:
        with urllib.request.urlopen(req, timeout=300) as resp:
            resp.read()
    except urllib.error.HTTPError as e:
        raise RuntimeError(e.read().decode("utf-8", errors="replace")) from e


def _ping() -> bool:
    cfg = _cfg()
    try:
        with urllib.request.urlopen(f"http://{cfg['host']}:{cfg['port']}/ping", timeout=3) as r:
            return r.status == 200
    except Exception:
        return False


def _table_exists(conn, name: str) -> bool:
    try:
        row = conn.execute(
            "SELECT COUNT(*) FROM information_schema.tables WHERE table_name = ?",
            [name],
        ).fetchone()
        return bool(row and int(row[0]) > 0)
    except Exception:
        try:
            conn.execute(f"SELECT 1 FROM {name} LIMIT 1")
            return True
        except Exception:
            return False


def _publicar_operaciones(conn, tablas: dict[str, int]) -> None:
    """Marts operativos: inventario, pedidos, movimientos, recepciones, finanzas."""

    if _table_exists(conn, "stock_almacen"):
        try:
            inv = conn.execute(
                """
                SELECT p.nombre_producto, COALESCE(it.item_type, '—'), COALESCE(al.nombre, '—'),
                       CAST(COALESCE(al.id_almacen, 0) AS INTEGER),
                       CAST(COALESCE(sa.cantidad_disponible, 0) AS DOUBLE),
                       CAST(COALESCE(it.unit_cost, p.precio_unitario * 0.6, 0) AS DOUBLE)
                FROM dim_producto p
                LEFT JOIN dim_item_type it ON it.id_item_type = p.id_item_type
                LEFT JOIN stock_almacen sa ON sa.id_producto = p.id_producto
                LEFT JOIN almacenes al ON al.id_almacen = sa.id_almacen
                WHERE COALESCE(p.activo, true) = true AND sa.id_almacen IS NOT NULL
                """
            ).fetchall()
            _post("TRUNCATE TABLE IF EXISTS dwh_inventario")
            if inv:
                chunk = 400
                for i in range(0, len(inv), chunk):
                    batch = inv[i : i + chunk]
                    vals = ",".join(
                        f"('{_esc(r[0])}','{_esc(r[1])}','{_esc(r[2])}',{int(r[3])},"
                        f"{float(r[4])},{float(r[5])},{float(r[4]) * float(r[5])})"
                        for r in batch
                    )
                    _post(
                        "INSERT INTO dwh_inventario (producto,categoria,almacen,id_almacen,stock,costo_unit,valor) VALUES "
                        + vals
                    )
            tablas["dwh_inventario"] = len(inv)
        except Exception as exc:
            logger.warning("Publicación dwh_inventario omitida: %s", exc)

    if _table_exists(conn, "alertas_stock"):
        try:
            sb = conn.execute(
                """
                SELECT p.nombre_producto, COALESCE(al.nombre, '—'),
                       CAST(COALESCE(sa.cantidad_disponible, 0) AS DOUBLE),
                       CAST(COALESCE(a.umbral_minimo, 0) AS DOUBLE)
                FROM alertas_stock a
                JOIN dim_producto p ON p.id_producto = a.id_producto
                LEFT JOIN almacenes al ON al.id_almacen = a.id_almacen
                LEFT JOIN stock_almacen sa ON sa.id_producto = a.id_producto AND sa.id_almacen = a.id_almacen
                WHERE COALESCE(a.activa, true) = true
                  AND COALESCE(sa.cantidad_disponible, 0) < COALESCE(a.umbral_minimo, 0)
                """
            ).fetchall()
            _post("TRUNCATE TABLE IF EXISTS dwh_stock_bajo")
            if sb:
                vals = ",".join(
                    f"('{_esc(r[0])}','{_esc(r[1])}',{float(r[2])},{float(r[3])},{max(float(r[3]) - float(r[2]), 0)})"
                    for r in sb
                )
                _post(
                    "INSERT INTO dwh_stock_bajo (producto,almacen,disponible,umbral,deficit) VALUES " + vals
                )
            tablas["dwh_stock_bajo"] = len(sb)
        except Exception as exc:
            logger.warning("Publicación dwh_stock_bajo omitida: %s", exc)

    if _table_exists(conn, "pedidos"):
        try:
            pe = conn.execute(
                """
                SELECT COALESCE(estado, '—'), CAST(COUNT(*) AS INTEGER),
                       CAST(COALESCE(SUM(COALESCE(total, total_pedido, 0)), 0) AS DOUBLE)
                FROM pedidos GROUP BY estado
                """
            ).fetchall()
            _post("TRUNCATE TABLE IF EXISTS dwh_pedidos_estado")
            if pe:
                vals = ",".join(
                    f"('{_esc(r[0])}',{int(r[1])},{float(r[2])})" for r in pe
                )
                _post("INSERT INTO dwh_pedidos_estado (estado,cantidad,monto_total) VALUES " + vals)
            tablas["dwh_pedidos_estado"] = len(pe)

            pp = conn.execute(
                """
                SELECT COALESCE(p.numero, ''), COALESCE(c.nombre_empresa, '—'), COALESCE(p.estado, '—'),
                       CAST(COALESCE(p.total, p.total_pedido, 0) AS DOUBLE),
                       CAST(COALESCE(p.fecha_pedido, current_date) AS DATE),
                       CASE WHEN (SELECT COUNT(*) FROM envios e WHERE e.id_pedido = p.id_pedido) = 0
                            THEN 1 ELSE 0 END
                FROM pedidos p
                LEFT JOIN dim_cliente c ON c.id_cliente = p.id_cliente
                ORDER BY p.fecha_pedido DESC
                LIMIT 5000
                """
            ).fetchall()
            _post("TRUNCATE TABLE IF EXISTS dwh_pedidos_pendientes")
            if pp:
                chunk = 400
                for i in range(0, len(pp), chunk):
                    batch = pp[i : i + chunk]
                    vals = ",".join(
                        f"('{_esc(r[0])}','{_esc(r[1])}','{_esc(r[2])}',{float(r[3])},'{r[4]}',{int(r[5])})"
                        for r in batch
                    )
                    _post(
                        "INSERT INTO dwh_pedidos_pendientes (numero,cliente,estado,monto,fecha,sin_envio) VALUES "
                        + vals
                    )
            tablas["dwh_pedidos_pendientes"] = len(pp)
        except Exception as exc:
            logger.warning("Publicación pedidos ClickHouse omitida: %s", exc)

    if _table_exists(conn, "movimientos_inventario"):
        try:
            mv = conn.execute(
                """
                SELECT mi.fecha, mi.tipo, COALESCE(p.nombre_producto, '—'),
                       COALESCE(al.nombre, '—'), CAST(COALESCE(d.cantidad, 0) AS DOUBLE),
                       COALESCE(mi.referencia, '')
                FROM movimientos_inventario mi
                LEFT JOIN movimiento_inventario_detalle d ON d.id_movimiento = mi.id_movimiento
                LEFT JOIN dim_producto p ON p.id_producto = d.id_producto
                LEFT JOIN almacenes al ON al.id_almacen = d.id_almacen
                ORDER BY mi.fecha DESC
                LIMIT 10000
                """
            ).fetchall()
            _post("TRUNCATE TABLE IF EXISTS dwh_movimientos")
            if mv:
                chunk = 400
                for i in range(0, len(mv), chunk):
                    batch = mv[i : i + chunk]
                    vals = ",".join(
                        f"('{_fmt_datetime(r[0])}','{_esc(r[1])}','{_esc(r[2])}','{_esc(r[3])}',"
                        f"{float(r[4])},'{_esc(r[5])}')"
                        for r in batch
                    )
                    _post(
                        "INSERT INTO dwh_movimientos (fecha,tipo,producto,almacen,cantidad,referencia) VALUES "
                        + vals
                    )
            tablas["dwh_movimientos"] = len(mv)
        except Exception as exc:
            logger.warning("Publicación dwh_movimientos omitida: %s", exc)

    if _table_exists(conn, "recepciones_compra"):
        try:
            rec = conn.execute(
                """
                SELECT r.id_recepcion, COALESCE(oc.numero, ''), pr.razon_social,
                       CAST(r.fecha AS DATE), COALESCE(r.estado, ''), CAST(COUNT(d.id_detalle) AS INTEGER),
                       CAST(COALESCE(SUM(d.cantidad_recibida * COALESCE(ocd.costo_unitario, 0)), 0) AS DOUBLE)
                FROM recepciones_compra r
                JOIN ordenes_compra oc ON oc.id_oc = r.id_oc
                JOIN proveedores pr ON pr.id_proveedor = oc.id_proveedor
                LEFT JOIN recepcion_compra_detalle d ON d.id_recepcion = r.id_recepcion
                LEFT JOIN orden_compra_detalle ocd ON ocd.id_oc = oc.id_oc AND ocd.id_producto = d.id_producto
                GROUP BY r.id_recepcion, oc.numero, pr.razon_social, r.fecha, r.estado
                ORDER BY r.id_recepcion DESC
                """
            ).fetchall()
            _post("TRUNCATE TABLE IF EXISTS dwh_recepciones")
            if rec:
                chunk = 400
                for i in range(0, len(rec), chunk):
                    batch = rec[i : i + chunk]
                    vals = ",".join(
                        f"({int(r[0])},'{_esc(r[1])}','{_esc(r[2])}','{r[3]}','{_esc(r[4])}',"
                        f"{int(r[5])},{float(r[6])})"
                        for r in batch
                    )
                    _post(
                        "INSERT INTO dwh_recepciones (id_recepcion,oc_numero,proveedor,fecha,estado,lineas,valor_recibido) VALUES "
                        + vals
                    )
            tablas["dwh_recepciones"] = len(rec)
        except Exception as exc:
            logger.warning("Publicación dwh_recepciones omitida: %s", exc)

    if _table_exists(conn, "asiento_lineas") and _table_exists(conn, "plan_cuentas"):
        try:
            fin = conn.execute(
                """
                SELECT pc.codigo, pc.nombre, pc.tipo,
                       CAST(SUM(al.debe) AS DOUBLE), CAST(SUM(al.haber) AS DOUBLE)
                FROM asiento_lineas al
                JOIN plan_cuentas pc ON pc.id_cuenta = al.id_cuenta
                GROUP BY pc.codigo, pc.nombre, pc.tipo
                ORDER BY ABS(SUM(al.debe) - SUM(al.haber)) DESC
                """
            ).fetchall()
            _post("TRUNCATE TABLE IF EXISTS dwh_finanzas")
            if fin:
                vals_list = []
                for r in fin:
                    debe, haber = float(r[3]), float(r[4])
                    saldo = debe - haber if r[2] in ("activo", "costo") else haber - debe
                    vals_list.append(
                        f"('{_esc(r[0])}','{_esc(r[1])}','{_esc(r[2])}',{debe},{haber},{saldo})"
                    )
                chunk = 200
                for i in range(0, len(vals_list), chunk):
                    _post(
                        "INSERT INTO dwh_finanzas (codigo,nombre,tipo,debe,haber,saldo) VALUES "
                        + ",".join(vals_list[i : i + chunk])
                    )
            tablas["dwh_finanzas"] = len(fin)
        except Exception as exc:
            logger.warning("Publicación dwh_finanzas omitida: %s", exc)

    tes_rows: list[tuple[str, str]] = []
    try:
        from backend.services.operaciones_service import panel_operaciones

        k = panel_operaciones(conn).get("kpis", {})
        tes_rows = [
            ("Caja (1101)", f"${float(k.get('caja', 0)):,.2f}"),
            ("Cuentas por pagar", f"${float(k.get('cuentas_por_pagar', 0)):,.2f}"),
            ("Compras del período", f"${float(k.get('compras_del_periodo', 0)):,.2f}"),
            ("Ventas del período", f"${float(k.get('ventas_del_periodo', 0)):,.2f}"),
            ("OC por aprobar", str(int(k.get("oc_por_aprobar", 0)))),
            ("Pedidos sin despachar", str(int(k.get("pedidos_sin_despachar", 0)))),
        ]
    except Exception:
        tes_rows = [("Estado", "Sin datos operativos")]
    try:
        _post("TRUNCATE TABLE IF EXISTS dwh_tesoreria")
        if tes_rows:
            vals = ",".join(f"('{_esc(a)}','{_esc(b)}')" for a, b in tes_rows)
            _post("INSERT INTO dwh_tesoreria (metrica,valor) VALUES " + vals)
        tablas["dwh_tesoreria"] = len(tes_rows)
    except Exception as exc:
        logger.warning("Publicación dwh_tesoreria omitida: %s", exc)


def publicar_desde_duckdb(conn) -> dict[str, Any]:
    if not _ping():
        return {"publicado": False, "motivo": "ClickHouse no disponible"}

    # Asegurar esquema (idempotente). Recrear ventas/compras si el PARTITION viejo es mensual.
    _post("CREATE DATABASE IF NOT EXISTS globtrade_dwh")
    for drop in ("dwh_ventas", "dwh_compras"):
        try:
            _post(f"DROP TABLE IF EXISTS {drop}")
        except Exception:
            pass
    for ddl in (
        """CREATE TABLE IF NOT EXISTS dwh_ventas (
            order_date Date, country String, region String, item_type String,
            nombre_producto String, linea String, marca String, sales_channel String,
            origen String, order_id Int64,
            units_sold Int64, total_revenue Float64, total_cost Float64, total_profit Float64
        ) ENGINE = MergeTree() PARTITION BY toYear(order_date) ORDER BY (order_date, country, item_type)""",
        """CREATE TABLE IF NOT EXISTS dwh_compras (
            fecha Date, proveedor String, numero String, estado String, total_compra Float64
        ) ENGINE = MergeTree() PARTITION BY toYear(fecha) ORDER BY (fecha, proveedor)""",
        """CREATE TABLE IF NOT EXISTS dwh_clientes (
            nombre_cliente String, pais String, total_comprado Float64, total_pagado Float64, cxc Float64
        ) ENGINE = MergeTree() ORDER BY (total_comprado, nombre_cliente)""",
        """CREATE TABLE IF NOT EXISTS dwh_proveedores (
            proveedor String, pais String, total_comprado Float64, num_oc Int32
        ) ENGINE = MergeTree() ORDER BY (total_comprado, proveedor)""",
        """CREATE TABLE IF NOT EXISTS dwh_geografia (
            country String, region String, total_revenue Float64, units_sold Int64, num_pedidos Int32
        ) ENGINE = MergeTree() ORDER BY (total_revenue, country)""",
        """CREATE TABLE IF NOT EXISTS dwh_inventario (
            producto String, categoria String, almacen String, id_almacen Int32,
            stock Float64, costo_unit Float64, valor Float64
        ) ENGINE = MergeTree() ORDER BY (producto, id_almacen)""",
        """CREATE TABLE IF NOT EXISTS dwh_stock_bajo (
            producto String, almacen String, disponible Float64, umbral Float64, deficit Float64
        ) ENGINE = MergeTree() ORDER BY (deficit, producto)""",
        """CREATE TABLE IF NOT EXISTS dwh_pedidos_estado (
            estado String, cantidad Int32, monto_total Float64
        ) ENGINE = MergeTree() ORDER BY (cantidad, estado)""",
        """CREATE TABLE IF NOT EXISTS dwh_pedidos_pendientes (
            numero String, cliente String, estado String, monto Float64, fecha Date, sin_envio UInt8
        ) ENGINE = MergeTree() ORDER BY (fecha, numero)""",
        """CREATE TABLE IF NOT EXISTS dwh_movimientos (
            fecha DateTime, tipo String, producto String, almacen String,
            cantidad Float64, referencia String
        ) ENGINE = MergeTree() PARTITION BY toYear(fecha) ORDER BY (fecha, producto)""",
        """CREATE TABLE IF NOT EXISTS dwh_recepciones (
            id_recepcion Int64, oc_numero String, proveedor String, fecha Date,
            estado String, lineas Int32, valor_recibido Float64
        ) ENGINE = MergeTree() PARTITION BY toYear(fecha) ORDER BY (fecha, id_recepcion)""",
        """CREATE TABLE IF NOT EXISTS dwh_finanzas (
            codigo String, nombre String, tipo String,
            debe Float64, haber Float64, saldo Float64
        ) ENGINE = MergeTree() ORDER BY (codigo)""",
        """CREATE TABLE IF NOT EXISTS dwh_tesoreria (
            metrica String, valor String
        ) ENGINE = MergeTree() ORDER BY metrica""",
        """CREATE TABLE IF NOT EXISTS dwh_cuentas_por_pagar (
            proveedor String, ruc String,
            comprado Float64, recibido Float64, pagado Float64, pendiente Float64
        ) ENGINE = MergeTree() ORDER BY (pendiente, proveedor)""",
        """CREATE TABLE IF NOT EXISTS etl_sync_meta (
            tabla String, filas UInt64, synced_at DateTime DEFAULT now()
        ) ENGINE = ReplacingMergeTree(synced_at) ORDER BY tabla""",
    ):
        try:
            _post(ddl)
        except Exception:
            pass

    tablas: dict[str, int] = {}

    rows = conn.execute(
        """
        SELECT CAST(fv.order_date AS DATE) AS order_date,
               COALESCE(c.country, '—') AS country,
               COALESCE(r.region, '—') AS region,
               COALESCE(it.item_type, '—') AS item_type,
               COALESCE(dp.nombre_producto, '—') AS nombre_producto,
               COALESCE(l.nombre, 'Sin línea') AS linea,
               COALESCE(m.nombre, 'Sin marca') AS marca,
               COALESCE(ch.sales_channel, '—') AS sales_channel,
               COALESCE(fv.origen, 'historico') AS origen,
               CAST(COALESCE(fv.order_id, 0) AS BIGINT) AS order_id,
               CAST(fv.units_sold AS BIGINT) AS units_sold,
               CAST(fv.total_revenue AS DOUBLE) AS total_revenue,
               CAST(fv.total_cost AS DOUBLE) AS total_cost,
               CAST(fv.total_profit AS DOUBLE) AS total_profit
        FROM fact_ventas fv
        LEFT JOIN dim_country c ON c.id_country = fv.id_country
        LEFT JOIN dim_region r ON r.id_region = fv.id_region
        LEFT JOIN dim_item_type it ON it.id_item_type = fv.id_item_type
        LEFT JOIN dim_producto dp ON dp.id_producto = fv.id_producto
        LEFT JOIN lineas_producto l ON l.id_linea = dp.id_linea
        LEFT JOIN marcas m ON m.id_marca = dp.id_marca
        LEFT JOIN dim_sales_channel ch ON ch.id_channel = fv.id_channel
        """
    ).fetchall()
    _post("TRUNCATE TABLE IF EXISTS dwh_ventas")
    if rows:
        chunk = 400
        for i in range(0, len(rows), chunk):
            batch = rows[i : i + chunk]
            vals = ",".join(
                f"('{r[0]}','{_esc(r[1])}','{_esc(r[2])}','{_esc(r[3])}','{_esc(r[4])}',"
                f"'{_esc(r[5])}','{_esc(r[6])}','{_esc(r[7])}','{_esc(r[8])}',"
                f"{int(r[9])},{int(r[10])},{float(r[11])},{float(r[12])},{float(r[13])})"
                for r in batch
            )
            _post(
                "INSERT INTO dwh_ventas (order_date,country,region,item_type,nombre_producto,linea,marca,sales_channel,origen,order_id,units_sold,total_revenue,total_cost,total_profit) VALUES "
                + vals
            )
    tablas["dwh_ventas"] = len(rows)

    geo = conn.execute(
        """
        SELECT COALESCE(c.country, '—'), COALESCE(r.region, '—'),
               CAST(SUM(fv.total_revenue) AS DOUBLE), CAST(SUM(fv.units_sold) AS BIGINT),
               COUNT(DISTINCT fv.order_id)
        FROM fact_ventas fv
        LEFT JOIN dim_country c ON c.id_country = fv.id_country
        LEFT JOIN dim_region r ON r.id_region = fv.id_region
        GROUP BY c.country, r.region
        """
    ).fetchall()
    _post("TRUNCATE TABLE IF EXISTS dwh_geografia")
    if geo:
        vals = ",".join(
            f"('{_esc(g[0])}','{_esc(g[1])}',{float(g[2])},{int(g[3])},{int(g[4])})" for g in geo
        )
        _post(
            "INSERT INTO dwh_geografia (country,region,total_revenue,units_sold,num_pedidos) VALUES "
            + vals
        )
    tablas["dwh_geografia"] = len(geo)

    oc_rows = conn.execute(
        """
        SELECT CAST(oc.fecha AS DATE), pr.razon_social, COALESCE(oc.numero, ''),
               COALESCE(oc.estado, 'borrador'), CAST(COALESCE(oc.total, 0) AS DOUBLE)
        FROM ordenes_compra oc
        JOIN proveedores pr ON pr.id_proveedor = oc.id_proveedor
        ORDER BY oc.fecha DESC
        """
    ).fetchall()
    _post("TRUNCATE TABLE IF EXISTS dwh_compras")
    if oc_rows:
        chunk = 400
        for i in range(0, len(oc_rows), chunk):
            batch = oc_rows[i : i + chunk]
            vals = ",".join(
                f"('{r[0]}','{_esc(r[1])}','{_esc(r[2])}','{_esc(r[3])}',{float(r[4])})"
                for r in batch
            )
            _post(
                "INSERT INTO dwh_compras (fecha,proveedor,numero,estado,total_compra) VALUES " + vals
            )
    tablas["dwh_compras"] = len(oc_rows)

    prov = conn.execute(
        """
        SELECT pr.razon_social, COALESCE(c.country, '—'),
               CAST(SUM(COALESCE(oc.total, 0)) AS DOUBLE), COUNT(DISTINCT oc.id_oc)
        FROM ordenes_compra oc
        JOIN proveedores pr ON pr.id_proveedor = oc.id_proveedor
        LEFT JOIN dim_country c ON c.id_country = pr.id_country
        GROUP BY pr.razon_social, c.country
        """
    ).fetchall()
    _post("TRUNCATE TABLE IF EXISTS dwh_proveedores")
    if prov:
        vals = ",".join(
            f"('{_esc(p[0])}','{_esc(p[1])}',{float(p[2])},{int(p[3])})" for p in prov
        )
        _post("INSERT INTO dwh_proveedores (proveedor,pais,total_comprado,num_oc) VALUES " + vals)
    tablas["dwh_proveedores"] = len(prov)

    cli = conn.execute(
        """
        SELECT dc.nombre_empresa, dc.pais,
               CAST(SUM(COALESCE(p.total, p.total_pedido, 0)) AS DOUBLE),
               CAST(SUM(CASE WHEN p.estado IN ('pagado','preparando','enviado','entregado')
                    THEN COALESCE(p.total, p.total_pedido, 0) ELSE 0 END) AS DOUBLE)
        FROM dim_cliente dc
        LEFT JOIN pedidos p ON p.id_cliente = dc.id_cliente
        GROUP BY dc.nombre_empresa, dc.pais
        HAVING SUM(COALESCE(p.total, p.total_pedido, 0)) > 0
        """
    ).fetchall()
    _post("TRUNCATE TABLE IF EXISTS dwh_clientes")
    if cli:
        vals = ",".join(
            f"('{_esc(c[0])}','{_esc(c[1])}',{float(c[2])},{float(c[3])},{float(c[2])-float(c[3])})"
            for c in cli
        )
        _post(
            "INSERT INTO dwh_clientes (nombre_cliente,pais,total_comprado,total_pagado,cxc) VALUES "
            + vals
        )
    tablas["dwh_clientes"] = len(cli)

    cxp_rows: list[tuple] = []
    if _table_exists(conn, "ordenes_compra") and _table_exists(conn, "proveedores"):
        try:
            cxp_rows = conn.execute(
                """
                SELECT pr.razon_social, COALESCE(pr.ruc, '—'),
                       CAST(SUM(COALESCE(oc.total, 0)) AS DOUBLE),
                       CAST(SUM(CASE WHEN lower(COALESCE(oc.estado, '')) IN ('recibida', 'completa', 'cerrada')
                            THEN COALESCE(oc.total, 0) ELSE 0 END) AS DOUBLE),
                       CAST(0 AS DOUBLE)
                FROM ordenes_compra oc
                JOIN proveedores pr ON pr.id_proveedor = oc.id_proveedor
                GROUP BY pr.razon_social, pr.ruc
                HAVING SUM(COALESCE(oc.total, 0)) > 0
                """
            ).fetchall()
            if _table_exists(conn, "asientos_contables"):
                enriched = []
                for r in cxp_rows:
                    pagado = 0.0
                    pid = conn.execute(
                        "SELECT id_proveedor FROM proveedores WHERE razon_social = ? LIMIT 1",
                        [r[0]],
                    ).fetchone()
                    if pid:
                        prow = conn.execute(
                            """
                            SELECT CAST(COALESCE(SUM(a.total), 0) AS DOUBLE)
                            FROM asientos_contables a
                            JOIN ordenes_compra x ON x.id_oc = a.id_oc
                            WHERE a.descripcion LIKE 'pago_oc:%' AND x.id_proveedor = ?
                            """,
                            [int(pid[0])],
                        ).fetchone()
                        pagado = float(prow[0] or 0) if prow else 0.0
                    comprado, recibido = float(r[2]), float(r[3])
                    pendiente = max(recibido - pagado, 0.0)
                    enriched.append((r[0], r[1], comprado, recibido, pagado, pendiente))
                cxp_rows = enriched
            else:
                cxp_rows = [
                    (r[0], r[1], float(r[2]), float(r[3]), 0.0, max(float(r[3]), 0.0))
                    for r in cxp_rows
                ]
        except Exception as exc:
            logger.warning("Publicación dwh_cuentas_por_pagar omitida: %s", exc)
            cxp_rows = []
    _post("TRUNCATE TABLE IF EXISTS dwh_cuentas_por_pagar")
    if cxp_rows:
        vals = ",".join(
            f"('{_esc(r[0])}','{_esc(r[1])}',{float(r[2])},{float(r[3])},{float(r[4])},{float(r[5])})"
            for r in cxp_rows if float(r[5]) > 0
        )
        if vals:
            _post(
                "INSERT INTO dwh_cuentas_por_pagar (proveedor,ruc,comprado,recibido,pagado,pendiente) VALUES "
                + vals
            )
    tablas["dwh_cuentas_por_pagar"] = len([r for r in cxp_rows if float(r[5]) > 0])

    _publicar_operaciones(conn, tablas)

    for t, n in tablas.items():
        _post(f"INSERT INTO etl_sync_meta (tabla, filas) VALUES ('{t}', {n})")

    return {"publicado": True, "tablas": tablas, "total_filas": sum(tablas.values())}


def ejecutar(conn=None):
    own = conn is None
    if own:
        try:
            from etl_pkg.conexion import conectar
            conn = conectar()
        except ImportError:
            import duckdb
            import os
            path = os.environ.get("DUCKDB_PATH", "db/globtrade.duckdb")
            conn = duckdb.connect(path)
    try:
        return publicar_desde_duckdb(conn)
    finally:
        if own and conn:
            conn.close()
