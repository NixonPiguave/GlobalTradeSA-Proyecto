"""
reporte_service.py — Consultas agregadas y exportación PDF/CSV de reportes del panel.

Informes simples: una sola consulta/tabla (ventas, ventas-detalle, inventario,
pedidos, clientes-CxC, rentabilidad, compras, stock-bajo, cuentas-por-pagar,
recepciones, kardex, proveedores, resumen-financiero).

Informes compuestos: varias secciones en un mismo documento
(informe-gerencial, informe-operativo).
"""

from __future__ import annotations

import csv
import io
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import duckdb

from shared.database.connection import repo_root, table_exists
from shared.pdf.generator import generar_pdf_desde_plantilla
from shared.services.config_service import obtener_config

logger = logging.getLogger(__name__)

REPORTES_VALIDOS = {
    "ventas", "ventas-detalle", "inventario-valorizado", "pedidos-por-estado",
    "clientes-cxc", "rentabilidad-producto", "resumen-financiero", "compras",
    "stock-bajo", "cuentas-por-pagar", "recepciones", "kardex", "proveedores",
    "informe-gerencial", "informe-operativo", "informe-comercial",
    "informe-logistico", "informe-financiero",
}

SIMPLE_REPORTES = {
    "inventario-valorizado", "pedidos-por-estado", "clientes-cxc",
    "rentabilidad-producto", "resumen-financiero", "compras",
    "stock-bajo", "cuentas-por-pagar", "recepciones", "kardex", "proveedores",
}

COMPUESTOS = {"informe-gerencial", "informe-operativo", "informe-comercial", "informe-logistico", "informe-financiero"}


def _ahora() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def column_exists(conn: duckdb.DuckDBPyConnection, table: str, column: str) -> bool:
    rows = conn.execute(f"PRAGMA table_info('{table}')").fetchall()
    return any(row[1] == column for row in rows)


def _fmt_money(v: Any) -> str:
    return f"${float(v or 0):,.2f}"


def dir_reportes_generados() -> Path:
    """Directorio compartido donde el DAG nocturno deja los reportes (PDF/CSV)."""
    raiz = Path(__file__).resolve().parents[4]
    direc = raiz / "shared" / "storage" / "reportes"
    direc.mkdir(parents=True, exist_ok=True)
    return direc


def listar_reportes_programados(conn: duckdb.DuckDBPyConnection, limite: int = 200) -> list[dict[str, Any]]:
    """Entregas del DAG etl_04_reportes_dag (tabla reportes_generados)."""
    if not table_exists(conn, "reportes_generados"):
        return []
    rows = conn.execute(
        """
        SELECT id, fecha, nombre, archivo, filtros, formato, duracion_ms, estado, bytes, detalle
        FROM reportes_generados
        ORDER BY fecha DESC, id DESC
        LIMIT ?
        """,
        [int(limite)],
    ).fetchall()
    return [
        {
            "id": int(r[0]),
            "fecha": str(r[1]),
            "nombre": r[2],
            "archivo": r[3],
            "filtros": r[4],
            "formato": r[5],
            "duracion_ms": int(r[6]) if r[6] is not None else None,
            "estado": r[7],
            "bytes": int(r[8]) if r[8] is not None else None,
            "detalle": r[9] or "",
        }
        for r in rows
    ]


def ruta_reporte_programado(conn: duckdb.DuckDBPyConnection, id_reporte: int) -> Optional[Path]:
    """Devuelve la ruta real del artefacto si existe en el registro y en disco."""
    if not table_exists(conn, "reportes_generados"):
        return None
    row = conn.execute(
        "SELECT archivo FROM reportes_generados WHERE id = ?",
        [int(id_reporte)],
    ).fetchone()
    if not row:
        return None
    ruta = dir_reportes_generados() / str(row[0])
    return ruta if ruta.is_file() else None


def _fmt_margen(profit: float, rev: float) -> str:
    return f"{(profit / rev * 100):.1f}%" if rev else "—"


def _rows_to_csv(headers: list[str], rows: list[list[Any]]) -> bytes:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(headers)
    for r in rows:
        w.writerow(r)
    return buf.getvalue().encode("utf-8-sig")


def _secciones_to_csv(secciones: list[dict[str, Any]]) -> bytes:
    """CSV multi-sección: cada sección va encabezada por su título."""
    buf = io.StringIO()
    w = csv.writer(buf)
    for s in secciones:
        w.writerow([])
        w.writerow([f"### {s.get('titulo') or 'Sección'}"])
        w.writerow(s.get("headers") or [])
        for r in s.get("rows") or []:
            w.writerow(r)
        if s.get("totales"):
            w.writerow([s["totales"]])
    return buf.getvalue().encode("utf-8-sig")


def _pdf_storage_dir() -> Path:
    """Directorio escribible para PDFs temporales (volume shared/storage en Docker)."""
    d = repo_root() / "shared" / "storage" / "comprobantes"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _vista_clickhouse_usable(vista: dict[str, Any]) -> bool:
    """True si la vista de ClickHouse trae filas; si no, conviene fallback DuckDB."""
    if not vista:
        return False
    if vista.get("tipo") == "compuesto":
        secciones = vista.get("secciones") or []
        return any((s.get("rows") for s in secciones))
    return bool(vista.get("rows"))


def _ctx_reporte(
    conn: duckdb.DuckDBPyConnection,
    titulo: str,
    subtitulo: str,
    **extra: Any,
) -> dict[str, Any]:
    ctx: dict[str, Any] = {
        "titulo": titulo,
        "subtitulo": subtitulo,
        "fecha_generacion": _ahora(),
        "empresa_nombre": obtener_config(conn, "EMPRESA_NOMBRE", "GLOBTRADE S.A."),
        "empresa_tagline": obtener_config(conn, "EMPRESA_TAGLINE", "Comercio internacional · Distribución B2B"),
        "empresa_logo": obtener_config(conn, "EMPRESA_LOGO", ""),
    }
    ctx.update(extra)
    return ctx


def _render_pdf(ctx: dict[str, Any], tmp_name: str = "_tmp_reporte.pdf", keep: bool = False) -> bytes:
    tmp = _pdf_storage_dir() / tmp_name
    generar_pdf_desde_plantilla("reportes/base_reporte.html", ctx, tmp)
    data = tmp.read_bytes()
    if not keep:
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass
    return data


def _rows_to_pdf(
    conn: duckdb.DuckDBPyConnection,
    titulo: str,
    subtitulo: str,
    headers: list[str],
    rows: list[list[Any]],
    totales: str = "",
    kpis: Optional[list[dict[str, str]]] = None,
    tmp_name: str = "_tmp_reporte.pdf",
    keep: bool = False,
) -> bytes:
    ctx = _ctx_reporte(
        conn, titulo, subtitulo,
        headers=headers,
        rows=[[str(c) if c is not None else "" for c in r] for r in rows],
        totales=totales,
        kpis=kpis or [],
    )
    return _render_pdf(ctx, tmp_name, keep=keep)


def _rows_to_pdf_completo(
    conn: duckdb.DuckDBPyConnection,
    titulo: str,
    subtitulo: str,
    headers: list[str],
    rows: list[list[Any]],
    totales: str = "",
    kpis: Optional[list[dict[str, str]]] = None,
    chunk: int = 5000,
) -> bytes:
    """PDF completo sin truncar: genera partes y las fusiona con pypdf."""
    if len(rows) <= chunk:
        return _rows_to_pdf(conn, titulo, subtitulo, headers, rows, totales, kpis)
    try:
        from pypdf import PdfWriter
    except ImportError:
        return _rows_to_pdf(
            conn, titulo, subtitulo, headers, rows[:chunk],
            f"{totales} · PDF limitado a {chunk:,} filas; use CSV para el detalle completo",
            kpis,
        )
    storage = _pdf_storage_dir()
    total_parts = (len(rows) + chunk - 1) // chunk
    parts: list[Path] = []
    try:
        for i in range(0, len(rows), chunk):
            n = i // chunk + 1
            part = storage / f"_tmp_reporte_part_{n}.pdf"
            chunk_rows = rows[i:i + chunk]
            part_totales = f"Parte {n} de {total_parts}"
            if n == 1 and totales:
                part_totales += f" · {totales}"
            _rows_to_pdf(
                conn, titulo, subtitulo, headers, chunk_rows, part_totales,
                kpis if n == 1 else None, tmp_name=part.name, keep=True,
            )
            parts.append(part)
        writer = PdfWriter()
        for p in parts:
            writer.append(str(p))
        out = storage / "_tmp_reporte_completo.pdf"
        try:
            with out.open("wb") as fh:
                writer.write(fh)
            return out.read_bytes()
        finally:
            writer.close()
            try:
                out.unlink(missing_ok=True)
            except OSError:
                pass
    finally:
        for p in parts:
            try:
                p.unlink(missing_ok=True)
            except OSError:
                pass


def _secciones_to_pdf(
    conn: duckdb.DuckDBPyConnection,
    titulo: str,
    subtitulo: str,
    secciones: list[dict[str, Any]],
    kpis: Optional[list[dict[str, str]]] = None,
) -> bytes:
    ctx = _ctx_reporte(conn, titulo, subtitulo, secciones=secciones, kpis=kpis or [], informe=True)
    return _render_pdf(ctx)


def _exportar_vista(
    conn: duckdb.DuckDBPyConnection,
    vista: dict[str, Any],
    formato: str,
) -> tuple[bytes, str, str]:
    """Exporta PDF/CSV desde datos ya materializados (p. ej. ClickHouse)."""
    nombre = str(vista.get("nombre") or "reporte")
    titulo = str(vista.get("titulo") or TITULOS.get(nombre, nombre))
    subtitulo = str(vista.get("subtitulo") or "Sin filtros")
    filename = f"{nombre.replace('-', '_')}.{formato}"
    kpis = vista.get("kpis") or []

    if vista.get("tipo") == "compuesto" or vista.get("secciones"):
        secciones = vista.get("secciones") or []
        if formato == "csv":
            return _secciones_to_csv(secciones), "text/csv; charset=utf-8", filename
        return _secciones_to_pdf(conn, titulo, subtitulo, secciones, kpis), "application/pdf", filename

    headers = list(vista.get("headers") or [])
    rows = list(vista.get("rows") or [])
    totales = str(vista.get("totales") or "")
    if formato == "csv":
        return _rows_to_csv(headers, rows), "text/csv; charset=utf-8", filename
    kpis_rows = kpis if kpis else _kpis_reporte(nombre, headers, rows, totales)
    return _rows_to_pdf(conn, titulo, subtitulo, headers, rows, totales, kpis_rows), "application/pdf", filename


# ---------------------------------------------------------------------------
# Consultas compartidas de fact_ventas
# ---------------------------------------------------------------------------

def _cond_ventas(conn: duckdb.DuckDBPyConnection, f: dict[str, Any]) -> tuple[list[str], list[Any], list[str]]:
    conds, params = [], []
    extra_joins: list[str] = []
    if table_exists(conn, "dim_sales_channel"):
        extra_joins.append("LEFT JOIN dim_sales_channel ch ON ch.id_channel = fv.id_channel")
    if table_exists(conn, "dim_order_priority"):
        extra_joins.append("LEFT JOIN dim_order_priority pp ON pp.id_priority = fv.id_priority")
    for key, col in [("region", "r.region"), ("country", "c.country"), ("item_type", "it.item_type"),
                     ("sales_channel", "ch.sales_channel"), ("order_priority", "pp.order_priority")]:
        if f.get(key):
            conds.append(f"{col} = ?")
            params.append(f[key])
    if f.get("desde"):
        conds.append("fv.order_date >= ?")
        params.append(f["desde"])
    if f.get("hasta"):
        conds.append("fv.order_date <= ?")
        params.append(f["hasta"])
    if f.get("origen") and table_exists(conn, "fact_ventas") and column_exists(conn, "fact_ventas", "origen"):
        conds.append("fv.origen = ?")
        params.append(f["origen"])
    return conds, params, extra_joins


def _consulta_ventas(conn: duckdb.DuckDBPyConnection, f: dict[str, Any]) -> tuple[list[str], list[list[Any]], str]:
    conds, params, extra_joins = _cond_ventas(conn, f)
    where = ("WHERE " + " AND ".join(conds)) if conds else ""
    joins = " ".join(extra_joins)
    limit_sql = ""
    if f.get("limite"):
        limit_sql = " LIMIT ?"
        params.append(int(f["limite"]))
    rows = conn.execute(
        f"""
        SELECT r.region, c.country, it.item_type, fv.order_date, fv.order_id,
               CAST(fv.units_sold AS INTEGER), CAST(fv.total_revenue AS DOUBLE), CAST(fv.total_profit AS DOUBLE)
        FROM fact_ventas fv
        LEFT JOIN dim_region r ON r.id_region = fv.id_region
        LEFT JOIN dim_country c ON c.id_country = fv.id_country
        LEFT JOIN dim_item_type it ON it.id_item_type = fv.id_item_type
        {joins}
        {where}
        ORDER BY fv.order_date DESC, fv.order_id DESC
        {limit_sql}
        """,
        params,
    ).fetchall()
    headers = ["Región", "País", "Producto", "Fecha", "Order ID", "Unidades", "Ingresos", "Profit"]
    data = [[r[0], r[1], r[2], str(r[3])[:10] if r[3] else "", r[4], r[5], _fmt_money(r[6]), _fmt_money(r[7])] for r in rows]
    return headers, data, ""


def _ventas_globales(conn: duckdb.DuckDBPyConnection, f: dict[str, Any]) -> tuple[int, int, float, float, float]:
    conds, params, extra_joins = _cond_ventas(conn, f)
    where = ("WHERE " + " AND ".join(conds)) if conds else ""
    joins = " ".join(extra_joins)
    r = conn.execute(
        f"""
        SELECT CAST(COUNT(*) AS BIGINT), CAST(COALESCE(SUM(fv.units_sold), 0) AS BIGINT),
               CAST(COALESCE(SUM(fv.total_revenue), 0) AS DOUBLE),
               CAST(COALESCE(SUM(fv.total_cost), 0) AS DOUBLE),
               CAST(COALESCE(SUM(fv.total_profit), 0) AS DOUBLE)
        FROM fact_ventas fv
        LEFT JOIN dim_region r ON r.id_region = fv.id_region
        LEFT JOIN dim_country c ON c.id_country = fv.id_country
        LEFT JOIN dim_item_type it ON it.id_item_type = fv.id_item_type
        {joins}
        {where}
        """,
        params,
    ).fetchone()
    return (int(r[0] or 0), int(r[1] or 0), float(r[2] or 0), float(r[3] or 0), float(r[4] or 0))


def _ventas_por_pais(conn: duckdb.DuckDBPyConnection, f: dict[str, Any]) -> tuple[list[str], list[list[Any]]]:
    conds, params, extra_joins = _cond_ventas(conn, f)
    where = ("WHERE " + " AND ".join(conds)) if conds else ""
    joins = " ".join(extra_joins)
    rows = conn.execute(
        f"""
        SELECT COALESCE(c.country, '—'), COALESCE(r.region, '—'),
               CAST(SUM(fv.units_sold) AS BIGINT),
               CAST(SUM(fv.total_revenue) AS DOUBLE), CAST(SUM(fv.total_profit) AS DOUBLE)
        FROM fact_ventas fv
        LEFT JOIN dim_region r ON r.id_region = fv.id_region
        LEFT JOIN dim_country c ON c.id_country = fv.id_country
        {joins}
        {where}
        GROUP BY c.country, r.region ORDER BY SUM(fv.total_revenue) DESC LIMIT 200
        """,
        params,
    ).fetchall()
    headers = ["País", "Región", "Unidades", "Ingresos", "Profit", "Margen"]
    data = [[r[0], r[1], int(r[2]), _fmt_money(r[3]), _fmt_money(r[4]), _fmt_margen(float(r[4]), float(r[3]))] for r in rows]
    return headers, data


def _ventas_por_mes(conn: duckdb.DuckDBPyConnection, f: dict[str, Any]) -> tuple[list[str], list[list[Any]]]:
    conds, params, extra_joins = _cond_ventas(conn, f)
    where = ("WHERE " + " AND ".join(conds)) if conds else ""
    joins = " ".join(extra_joins)
    rows = conn.execute(
        f"""
        SELECT strftime(fv.order_date, '%Y-%m') AS mes,
               CAST(SUM(fv.units_sold) AS BIGINT),
               CAST(SUM(fv.total_revenue) AS DOUBLE), CAST(SUM(fv.total_profit) AS DOUBLE)
        FROM fact_ventas fv
        LEFT JOIN dim_region r ON r.id_region = fv.id_region
        LEFT JOIN dim_country c ON c.id_country = fv.id_country
        {joins}
        {where}
        GROUP BY 1 ORDER BY 1
        """,
        params,
    ).fetchall()
    headers = ["Mes", "Unidades", "Ingresos", "Profit"]
    data = [[r[0], int(r[1]), _fmt_money(r[2]), _fmt_money(r[3])] for r in rows]
    return headers, data


def _top_productos(conn: duckdb.DuckDBPyConnection, f: dict[str, Any], limite: int = 10) -> tuple[list[str], list[list[Any]]]:
    conds, params, extra_joins = _cond_ventas(conn, f)
    where = ("WHERE " + " AND ".join(conds)) if conds else ""
    joins = " ".join(extra_joins)
    rows = conn.execute(
        f"""
        SELECT COALESCE(it.item_type, '—'),
               CAST(SUM(fv.units_sold) AS BIGINT),
               CAST(SUM(fv.total_revenue) AS DOUBLE), CAST(SUM(fv.total_profit) AS DOUBLE)
        FROM fact_ventas fv
        LEFT JOIN dim_item_type it ON it.id_item_type = fv.id_item_type
        {joins}
        {where}
        GROUP BY it.item_type ORDER BY SUM(fv.total_revenue) DESC LIMIT ?
        """,
        params + [limite],
    ).fetchall()
    headers = ["Producto", "Unidades", "Ingresos", "Profit", "Margen"]
    data = [[r[0], int(r[1]), _fmt_money(r[2]), _fmt_money(r[3]), _fmt_margen(float(r[3]), float(r[2]))] for r in rows]
    return headers, data


# ---------------------------------------------------------------------------
# Informes simples nuevos
# ---------------------------------------------------------------------------

def _consulta_stock_bajo(conn: duckdb.DuckDBPyConnection, f: dict[str, Any]) -> tuple[list[str], list[list[Any]], str]:
    if not table_exists(conn, "alertas_stock"):
        return ["Producto", "Almacén", "Disponible", "Umbral", "Déficit"], [], ""
    conds, params = ["COALESCE(a.activa, true) = true", "COALESCE(sa.cantidad_disponible, 0) < COALESCE(a.umbral_minimo, 0)"], []
    if f.get("almacen"):
        conds.append("a.id_almacen = ?")
        params.append(f["almacen"])
    where = " AND ".join(conds)
    rows = conn.execute(
        f"""
        SELECT p.nombre_producto, COALESCE(al.nombre, '—'),
               CAST(COALESCE(sa.cantidad_disponible, 0) AS DOUBLE),
               CAST(COALESCE(a.umbral_minimo, 0) AS DOUBLE)
        FROM alertas_stock a
        JOIN dim_producto p ON p.id_producto = a.id_producto
        LEFT JOIN almacenes al ON al.id_almacen = a.id_almacen
        LEFT JOIN stock_almacen sa ON sa.id_producto = a.id_producto AND sa.id_almacen = a.id_almacen
        WHERE {where}
        ORDER BY (COALESCE(a.umbral_minimo, 0) - COALESCE(sa.cantidad_disponible, 0)) DESC
        """,
        params,
    ).fetchall()
    headers = ["Producto", "Almacén", "Disponible", "Umbral", "Déficit"]
    data = []
    for r in rows:
        disp, umb = float(r[2]), float(r[3])
        data.append([r[0], r[1], f"{disp:,.2f}", f"{umb:,.2f}", f"{max(umb - disp, 0):,.2f}"])
    return headers, data, f"{len(rows)} productos bajo umbral"


def _consulta_cuentas_por_pagar(conn: duckdb.DuckDBPyConnection, f: dict[str, Any]) -> tuple[list[str], list[list[Any]], str]:
    if not table_exists(conn, "fact_compras"):
        return ["Proveedor", "RUC", "Comprado", "Recibido", "Pagado", "Pendiente"], [], ""
    conds, params = [], []
    if f.get("desde"):
        conds.append("CAST(oc.fecha AS DATE) >= ?")
        params.append(f["desde"])
    if f.get("hasta"):
        conds.append("CAST(oc.fecha AS DATE) <= ?")
        params.append(f["hasta"])
    where = ("WHERE " + " AND ".join(conds)) if conds else ""
    rows = conn.execute(
        f"""
        SELECT oc.id_proveedor, pr.razon_social, COALESCE(pr.ruc, '—'),
               CAST(COALESCE(SUM(fc.costo), 0) AS DOUBLE),
               CAST(COALESCE(SUM(fc.cantidad * d.costo_unitario), 0) AS DOUBLE)
        FROM fact_compras fc
        JOIN ordenes_compra oc ON oc.id_oc = fc.id_oc
        JOIN proveedores pr ON pr.id_proveedor = oc.id_proveedor
        JOIN orden_compra_detalle d ON d.id_oc = oc.id_oc AND d.id_producto = fc.id_producto
        {where}
        GROUP BY oc.id_proveedor, pr.razon_social, pr.ruc
        ORDER BY pr.razon_social
        """,
        params,
    ).fetchall()
    headers = ["Proveedor", "RUC", "Comprado", "Recibido", "Pagado", "Pendiente"]
    data = []
    total_pendiente = 0.0
    for r in rows:
        pagado = 0.0
        if table_exists(conn, "asientos_contables"):
            pag_row = conn.execute(
                """
                SELECT CAST(COALESCE(SUM(a.total), 0) AS DOUBLE)
                FROM asientos_contables a
                JOIN ordenes_compra x ON x.id_oc = a.id_oc
                WHERE a.descripcion LIKE 'pago_oc:%' AND x.id_proveedor = ?
                """,
                [int(r[0])],
            ).fetchone()
            pagado = float(pag_row[0] or 0)
        pendiente = max(float(r[3]) - pagado, 0.0)
        total_pendiente += pendiente
        data.append([r[1], r[2], _fmt_money(r[3]), _fmt_money(r[4]), _fmt_money(pagado), _fmt_money(pendiente)])
    return headers, data, f"Total pendiente: ${total_pendiente:,.2f}"


def _consulta_recepciones(conn: duckdb.DuckDBPyConnection, f: dict[str, Any]) -> tuple[list[str], list[list[Any]], str]:
    if not table_exists(conn, "recepciones_compra"):
        return ["ID", "OC", "Proveedor", "Fecha", "Estado", "Líneas", "Valor recibido"], [], ""
    conds, params = [], []
    if f.get("desde"):
        conds.append("CAST(r.fecha AS DATE) >= ?")
        params.append(f["desde"])
    if f.get("hasta"):
        conds.append("CAST(r.fecha AS DATE) <= ?")
        params.append(f["hasta"])
    if f.get("estado"):
        conds.append("r.estado = ?")
        params.append(f["estado"])
    where = ("WHERE " + " AND ".join(conds)) if conds else ""
    rows = conn.execute(
        f"""
        SELECT r.id_recepcion, oc.numero, pr.razon_social, r.fecha, r.estado,
               CAST(COUNT(d.id_detalle) AS INTEGER),
               CAST(COALESCE(SUM(d.cantidad_recibida * COALESCE(ocd.costo_unitario, 0)), 0) AS DOUBLE)
        FROM recepciones_compra r
        JOIN ordenes_compra oc ON oc.id_oc = r.id_oc
        JOIN proveedores pr ON pr.id_proveedor = oc.id_proveedor
        LEFT JOIN recepcion_compra_detalle d ON d.id_recepcion = r.id_recepcion
        LEFT JOIN orden_compra_detalle ocd ON ocd.id_oc = oc.id_oc AND ocd.id_producto = d.id_producto
        {where}
        GROUP BY r.id_recepcion, oc.numero, pr.razon_social, r.fecha, r.estado
        ORDER BY r.id_recepcion DESC
        """,
        params,
    ).fetchall()
    headers = ["ID", "OC", "Proveedor", "Fecha", "Estado", "Líneas", "Valor recibido"]
    estado_label = {"completa": "Completa", "parcial": "Parcial"}
    data = [[int(r[0]), r[1], r[2], str(r[3])[:19], estado_label.get(r[4], r[4]), int(r[5]), _fmt_money(r[6])] for r in rows]
    return headers, data, f"{len(rows)} recepciones"


def _consulta_kardex(conn: duckdb.DuckDBPyConnection, f: dict[str, Any]) -> tuple[list[str], list[list[Any]], str]:
    if not table_exists(conn, "movimientos_inventario"):
        return ["Fecha", "Tipo", "Producto", "Almacén", "Cantidad", "Referencia"], [], ""
    conds, params = [], []
    if f.get("desde"):
        conds.append("CAST(mi.fecha AS DATE) >= ?")
        params.append(f["desde"])
    if f.get("hasta"):
        conds.append("CAST(mi.fecha AS DATE) <= ?")
        params.append(f["hasta"])
    if f.get("producto"):
        conds.append("p.nombre_producto LIKE ?")
        params.append(f"%{f['producto']}%")
    if f.get("almacen"):
        conds.append("d.id_almacen = ?")
        params.append(f["almacen"])
    where = ("WHERE " + " AND ".join(conds)) if conds else ""
    rows = conn.execute(
        f"""
        SELECT mi.fecha, mi.tipo, COALESCE(p.nombre_producto, '—'),
               COALESCE(al.nombre, '—'), CAST(COALESCE(d.cantidad, 0) AS DOUBLE), mi.referencia
        FROM movimientos_inventario mi
        LEFT JOIN movimiento_inventario_detalle d ON d.id_movimiento = mi.id_movimiento
        LEFT JOIN dim_producto p ON p.id_producto = d.id_producto
        LEFT JOIN almacenes al ON al.id_almacen = d.id_almacen
        {where}
        ORDER BY mi.fecha DESC, mi.id_movimiento DESC
        """,
        params,
    ).fetchall()
    headers = ["Fecha", "Tipo", "Producto", "Almacén", "Cantidad", "Referencia"]
    data = [[str(r[0])[:19], r[1], r[2], r[3], float(r[4]), r[5] or ""] for r in rows]
    return headers, data, f"{len(rows)} movimientos"


def _consulta_proveedores(conn: duckdb.DuckDBPyConnection, f: dict[str, Any]) -> tuple[list[str], list[list[Any]], str]:
    if not table_exists(conn, "proveedores"):
        return ["ID", "Razón social", "RUC", "País", "Órdenes", "Activo"], [], ""
    rows = conn.execute(
        """
        SELECT p.id_proveedor, p.razon_social, COALESCE(p.ruc, '—'), COALESCE(c.country, '—'),
               (SELECT COUNT(*) FROM ordenes_compra oc WHERE oc.id_proveedor = p.id_proveedor),
               p.activo
        FROM proveedores p
        LEFT JOIN dim_country c ON c.id_country = p.id_country
        ORDER BY p.razon_social
        """
    ).fetchall()
    headers = ["ID", "Razón social", "RUC", "País", "Órdenes", "Activo"]
    data = [[int(r[0]), r[1], r[2], r[3], int(r[4]), "Sí" if r[5] else "No"] for r in rows]
    return headers, data, f"{len(rows)} proveedores"


# ---------------------------------------------------------------------------
# Informes compuestos
# ---------------------------------------------------------------------------

def _compras_por_proveedor(conn: duckdb.DuckDBPyConnection, f: dict[str, Any], limite: int = 10) -> tuple[list[str], list[list[Any]]]:
    conds, params = ["oc.estado != 'cancelada'"], []
    if f.get("desde"):
        conds.append("CAST(oc.fecha AS DATE) >= ?")
        params.append(f["desde"])
    if f.get("hasta"):
        conds.append("CAST(oc.fecha AS DATE) <= ?")
        params.append(f["hasta"])
    where = "WHERE " + " AND ".join(conds)
    rows = conn.execute(
        f"""
        SELECT pr.razon_social, CAST(COUNT(oc.id_oc) AS INTEGER),
               CAST(COALESCE(SUM(oc.total), 0) AS DOUBLE)
        FROM ordenes_compra oc
        JOIN proveedores pr ON pr.id_proveedor = oc.id_proveedor
        {where}
        GROUP BY pr.razon_social ORDER BY 3 DESC LIMIT ?
        """,
        params + [limite],
    ).fetchall()
    headers = ["Proveedor", "Órdenes", "Monto total"]
    data = [[r[0], int(r[1]), _fmt_money(r[2])] for r in rows]
    return headers, data


def _pedidos_sin_despacho(conn: duckdb.DuckDBPyConnection, f: dict[str, Any], limite: int = 50) -> tuple[list[str], list[list[Any]]]:
    conds, params = ["p.estado IN ('pagado', 'preparando', 'enviado')"], []
    if f.get("desde"):
        conds.append("CAST(p.fecha_pedido AS DATE) >= ?")
        params.append(f["desde"])
    if f.get("hasta"):
        conds.append("CAST(p.fecha_pedido AS DATE) <= ?")
        params.append(f["hasta"])
    where = "WHERE " + " AND ".join(conds)
    rows = conn.execute(
        f"""
        SELECT p.numero, COALESCE(c.nombre_empresa, '—'), p.estado,
               CAST(COALESCE(p.total, p.total_pedido, 0) AS DOUBLE),
               (SELECT COUNT(*) FROM envios e WHERE e.id_pedido = p.id_pedido)
        FROM pedidos p
        LEFT JOIN dim_cliente c ON c.id_cliente = p.id_cliente
        {where} AND (SELECT COUNT(*) FROM envios e WHERE e.id_pedido = p.id_pedido) = 0
        ORDER BY p.fecha_pedido DESC LIMIT ?
        """,
        params + [limite],
    ).fetchall()
    headers = ["Nº pedido", "Cliente", "Estado", "Monto", "Envíos"]
    data = [[r[0], r[1], r[2], _fmt_money(r[3]), int(r[4])] for r in rows]
    return headers, data


def _tesoreria_operativa(conn: duckdb.DuckDBPyConnection, f: dict[str, Any]) -> list[list[Any]]:
    try:
        from backend.services.operaciones_service import panel_operaciones
        k = panel_operaciones(conn).get("kpis", {})
        rows: list[list[Any]] = [
            ["Caja (1101)", _fmt_money(k.get("caja", 0))],
            ["Cuentas por pagar", _fmt_money(k.get("cuentas_por_pagar", 0))],
            ["Compras del período", _fmt_money(k.get("compras_del_periodo", 0))],
            ["Ventas del período", _fmt_money(k.get("ventas_del_periodo", 0))],
            ["OC por aprobar", str(k.get("oc_por_aprobar", 0))],
            ["Pedidos sin despachar", str(k.get("pedidos_sin_despachar", 0))],
        ]
        return rows
    except Exception:
        return [["Caja (1101)", "—"], ["Cuentas por pagar", "—"]]


def _ventas_por_dim(conn: duckdb.DuckDBPyConnection, f: dict[str, Any], col: str, label: str) -> tuple[list[str], list[list[Any]]]:
    conds, params, extra_joins = _cond_ventas(conn, f)
    where = ("WHERE " + " AND ".join(conds)) if conds else ""
    joins = " ".join(extra_joins)
    rows = conn.execute(
        f"""
        SELECT COALESCE({col}, '—'),
               CAST(SUM(fv.units_sold) AS BIGINT),
               CAST(SUM(fv.total_revenue) AS DOUBLE), CAST(SUM(fv.total_profit) AS DOUBLE)
        FROM fact_ventas fv
        LEFT JOIN dim_region r ON r.id_region = fv.id_region
        LEFT JOIN dim_country c ON c.id_country = fv.id_country
        {joins}
        {where}
        GROUP BY 1 ORDER BY SUM(fv.total_revenue) DESC LIMIT 100
        """,
        params,
    ).fetchall()
    headers = [label, "Unidades", "Ingresos", "Profit", "Margen"]
    data = [[r[0], int(r[1]), _fmt_money(r[2]), _fmt_money(r[3]), _fmt_margen(float(r[3]), float(r[2]))] for r in rows]
    return headers, data


def _consulta_oc_por_aprobar(conn: duckdb.DuckDBPyConnection, f: dict[str, Any], limite: int = 20) -> tuple[list[str], list[list[Any]]]:
    if not table_exists(conn, "ordenes_compra"):
        return ["Número", "Proveedor", "Fecha", "Total"], []
    rows = conn.execute(
        """
        SELECT oc.numero, pr.razon_social, oc.fecha, CAST(oc.total AS DOUBLE)
        FROM ordenes_compra oc
        JOIN proveedores pr ON pr.id_proveedor = oc.id_proveedor
        WHERE oc.estado = 'borrador'
        ORDER BY oc.fecha DESC LIMIT ?
        """,
        [limite],
    ).fetchall()
    headers = ["Número", "Proveedor", "Fecha", "Total"]
    data = [[r[0], r[1], str(r[2])[:19], _fmt_money(r[3])] for r in rows]
    return headers, data


def _envios_por_transportista(conn: duckdb.DuckDBPyConnection, f: dict[str, Any]) -> tuple[list[str], list[list[Any]], str]:
    if not table_exists(conn, "envios") or not table_exists(conn, "transportistas"):
        return ["Transportista", "Envíos", "Pedidos"], [], ""
    rows = conn.execute(
        """
        SELECT COALESCE(t.nombre, '—'), CAST(COUNT(DISTINCT e.id_envio) AS INTEGER),
               CAST(COUNT(DISTINCT e.id_pedido) AS INTEGER)
        FROM envios e
        LEFT JOIN transportistas t ON t.id_transportista = e.id_transportista
        GROUP BY t.nombre ORDER BY 2 DESC
        """
    ).fetchall()
    headers = ["Transportista", "Envíos", "Pedidos"]
    data = [[r[0], int(r[1]), int(r[2])] for r in rows]
    total = sum(int(r[1]) for r in rows)
    return headers, data, f"{total} envíos registrados"


def _movimientos_por_tipo(conn: duckdb.DuckDBPyConnection, f: dict[str, Any]) -> tuple[list[str], list[list[Any]]]:
    if not table_exists(conn, "movimientos_inventario"):
        return ["Tipo", "Movimientos"], []
    conds, params = [], []
    if f.get("desde"):
        conds.append("CAST(fecha AS DATE) >= ?")
        params.append(f["desde"])
    if f.get("hasta"):
        conds.append("CAST(fecha AS DATE) <= ?")
        params.append(f["hasta"])
    where = ("WHERE " + " AND ".join(conds)) if conds else ""
    rows = conn.execute(
        f"SELECT tipo, CAST(COUNT(*) AS INTEGER) FROM movimientos_inventario {where} GROUP BY tipo ORDER BY 2 DESC",
        params,
    ).fetchall()
    headers = ["Tipo", "Movimientos"]
    data = [[r[0], int(r[1])] for r in rows]
    return headers, data


def _zonas_tarifas(conn: duckdb.DuckDBPyConnection, f: dict[str, Any]) -> tuple[list[str], list[list[Any]]]:
    if not table_exists(conn, "zonas_envio"):
        return ["Zona", "Costo base", "Peso máximo", "Costo"], []
    rows = conn.execute(
        """
        SELECT z.nombre, CAST(COALESCE(z.costo_base, 0) AS DOUBLE),
               CAST(COALESCE(t.peso_max, 0) AS DOUBLE), CAST(COALESCE(t.costo, 0) AS DOUBLE)
        FROM zonas_envio z
        LEFT JOIN tarifas_envio t ON t.id_zona = z.id_zona
        ORDER BY z.nombre, t.peso_max
        """
    ).fetchall()
    headers = ["Zona", "Costo base", "Peso máximo (kg)", "Costo"]
    data = [[r[0], _fmt_money(r[1]), f"{float(r[2]):,.2f}", _fmt_money(r[3])] for r in rows]
    return headers, data


def _saldos_por_cuenta(conn: duckdb.DuckDBPyConnection, f: dict[str, Any], limite: int = 12) -> tuple[list[str], list[list[Any]], str]:
    if not table_exists(conn, "asiento_lineas") or not table_exists(conn, "plan_cuentas"):
        return ["Cuenta", "Nombre", "Tipo", "Debe", "Haber", "Saldo"], [], ""
    rows = conn.execute(
        """
        SELECT pc.codigo, pc.nombre, pc.tipo,
               CAST(SUM(al.debe) AS DOUBLE), CAST(SUM(al.haber) AS DOUBLE)
        FROM asiento_lineas al
        JOIN plan_cuentas pc ON pc.id_cuenta = al.id_cuenta
        GROUP BY pc.codigo, pc.nombre, pc.tipo
        ORDER BY ABS(SUM(al.debe) - SUM(al.haber)) DESC LIMIT ?
        """,
        [limite],
    ).fetchall()
    headers = ["Cuenta", "Nombre", "Tipo", "Debe", "Haber", "Saldo"]
    data = []
    for r in rows:
        debe, haber = float(r[3]), float(r[4])
        saldo = debe - haber if r[2] in ("activo", "costo") else haber - debe
        data.append([r[0], r[1], r[2], _fmt_money(debe), _fmt_money(haber), _fmt_money(saldo)])
    return headers, data, "Saldos por cuenta (activo/costo: debe − haber; ingreso/pasivo: haber − debe)"


def _secciones_informe_ventas(conn: duckdb.DuckDBPyConnection, f: dict[str, Any]) -> list[dict[str, Any]]:
    n, unidades, rev, cost, profit = _ventas_globales(conn, f)
    resumen = [
        ["Líneas de venta", n],
        ["Unidades vendidas", unidades],
        ["Ingresos", _fmt_money(rev)],
        ["Costos", _fmt_money(cost)],
        ["Profit", _fmt_money(profit)],
        ["Margen", _fmt_margen(profit, rev)],
    ]
    h_pais, r_pais = _ventas_por_pais(conn, f)
    h_mes, r_mes = _ventas_por_mes(conn, f)
    h_top, r_top = _top_productos(conn, f, 10)
    det_headers, det_rows, _ = _consulta_ventas(conn, {**f, "limite": 200})
    return [
        {"titulo": "Resumen del período", "headers": ["Métrica", "Valor"], "rows": resumen},
        {"titulo": "Ventas por país", "headers": h_pais, "rows": r_pais},
        {"titulo": "Ventas por mes", "headers": h_mes, "rows": r_mes},
        {"titulo": "Top 10 productos por ingresos", "headers": h_top, "rows": r_top},
        {"titulo": "Detalle reciente (últimas 200 líneas)", "headers": det_headers, "rows": det_rows,
         "nota": "Detalle completo disponible en el reporte «ventas-detalle» (PDF paginado o CSV)."},
    ]


def _secciones_informe_gerencial(conn: duckdb.DuckDBPyConnection, f: dict[str, Any]) -> list[dict[str, Any]]:
    n, unidades, rev, cost, profit = _ventas_globales(conn, f)
    resumen = [
        ["Líneas de venta", n],
        ["Unidades vendidas", unidades],
        ["Ingresos", _fmt_money(rev)],
        ["Costos", _fmt_money(cost)],
        ["Profit", _fmt_money(profit)],
        ["Margen", _fmt_margen(profit, rev)],
    ]
    h_pais, r_pais = _ventas_por_pais(conn, f)
    h_top, r_top = _top_productos(conn, f, 10)
    h_comp, r_comp = _compras_por_proveedor(conn, f, 10)
    h_sb, r_sb, tot_sb = _consulta_stock_bajo(conn, f)
    h_cxc, r_cxc, _ = _consulta_clientes_cxc(conn, f)
    secciones = [
        {"titulo": "Resumen del período", "headers": ["Métrica", "Valor"], "rows": resumen},
        {"titulo": "Ventas por país", "headers": h_pais, "rows": r_pais},
        {"titulo": "Top 10 productos por ingresos", "headers": h_top, "rows": r_top},
        {"titulo": "Compras por proveedor (top 10)", "headers": h_comp, "rows": r_comp},
        {"titulo": "Alertas de stock bajo", "headers": h_sb, "rows": r_sb, "totales": tot_sb},
        {"titulo": "Clientes con cuentas por cobrar (top 10)", "headers": h_cxc, "rows": r_cxc[:10]},
    ]
    return secciones


def _secciones_informe_operativo(conn: duckdb.DuckDBPyConnection, f: dict[str, Any]) -> list[dict[str, Any]]:
    h_ped, r_ped, _ = _consulta_pedidos_estado(conn, f)
    h_sd, r_sd = _pedidos_sin_despacho(conn, f, 50)
    h_rec, r_rec, tot_rec = _consulta_recepciones(conn, f)
    h_ap, r_ap = _consulta_oc_por_aprobar(conn, f, 20)
    h_sb, r_sb, tot_sb = _consulta_stock_bajo(conn, f)
    tes = _tesoreria_operativa(conn, f)
    return [
        {"titulo": "Pedidos por estado", "headers": h_ped, "rows": r_ped},
        {"titulo": "Pedidos sin despacho (últimos 50)", "headers": h_sd, "rows": r_sd},
        {"titulo": "Recepciones recientes (últimas 20)", "headers": h_rec, "rows": r_rec[:20], "totales": tot_rec},
        {"titulo": "Órdenes de compra por aprobar (últimas 20)", "headers": h_ap, "rows": r_ap},
        {"titulo": "Alertas de stock bajo", "headers": h_sb, "rows": r_sb, "totales": tot_sb},
        {"titulo": "Resumen de tesorería", "headers": ["Métrica", "Valor"], "rows": tes},
    ]


def _secciones_informe_comercial(conn: duckdb.DuckDBPyConnection, f: dict[str, Any]) -> list[dict[str, Any]]:
    h_can, r_can = _ventas_por_dim(conn, f, "ch.sales_channel", "Canal")
    h_pr, r_pr = _ventas_por_dim(conn, f, "pp.order_priority", "Prioridad")
    h_ori, r_ori = _ventas_por_dim(conn, f, "fv.origen", "Origen")
    h_ren, r_ren, _ = _consulta_rentabilidad(conn, f)
    h_ped, r_ped, _ = _consulta_pedidos_estado(conn, f)
    h_cxc, r_cxc, tot_cxc = _consulta_clientes_cxc(conn, f)
    return [
        {"titulo": "Ventas por canal", "headers": h_can, "rows": r_can},
        {"titulo": "Ventas por prioridad de pedido", "headers": h_pr, "rows": r_pr},
        {"titulo": "Ventas por origen (histórico vs portal)", "headers": h_ori, "rows": r_ori},
        {"titulo": "Rentabilidad por producto (top 15)", "headers": h_ren, "rows": r_ren[:15]},
        {"titulo": "Pedidos del portal por estado", "headers": h_ped, "rows": r_ped},
        {"titulo": "Clientes con cuentas por cobrar (top 10)", "headers": h_cxc, "rows": r_cxc[:10], "totales": tot_cxc},
    ]


def _secciones_informe_logistico(conn: duckdb.DuckDBPyConnection, f: dict[str, Any]) -> list[dict[str, Any]]:
    h_sd, r_sd = _pedidos_sin_despacho(conn, f, 50)
    h_tr, r_tr, tot_tr = _envios_por_transportista(conn, f)
    h_rec, r_rec, tot_rec = _consulta_recepciones(conn, f)
    h_sb, r_sb, tot_sb = _consulta_stock_bajo(conn, f)
    h_mv, r_mv = _movimientos_por_tipo(conn, f)
    h_zt, r_zt = _zonas_tarifas(conn, f)
    return [
        {"titulo": "Pedidos sin despacho (últimos 50)", "headers": h_sd, "rows": r_sd},
        {"titulo": "Envíos por transportista", "headers": h_tr, "rows": r_tr, "totales": tot_tr},
        {"titulo": "Recepciones recientes (últimas 20)", "headers": h_rec, "rows": r_rec[:20], "totales": tot_rec},
        {"titulo": "Movimientos de inventario por tipo", "headers": h_mv, "rows": r_mv},
        {"titulo": "Alertas de stock bajo", "headers": h_sb, "rows": r_sb, "totales": tot_sb},
        {"titulo": "Zonas y tarifas de envío", "headers": h_zt, "rows": r_zt},
    ]


def _secciones_informe_financiero(conn: duckdb.DuckDBPyConnection, f: dict[str, Any]) -> list[dict[str, Any]]:
    h_res, r_res, _ = _consulta_resumen(conn, f)
    tes = _tesoreria_operativa(conn, f)
    h_cxp, r_cxp, tot_cxp = _consulta_cuentas_por_pagar(conn, f)
    h_cxc, r_cxc, tot_cxc = _consulta_clientes_cxc(conn, f)
    h_sal, r_sal, tot_sal = _saldos_por_cuenta(conn, f, 12)
    h_comp, r_comp = _compras_por_proveedor(conn, f, 10)
    return [
        {"titulo": "Resumen financiero del período", "headers": h_res, "rows": r_res},
        {"titulo": "Caja y tesorería", "headers": ["Métrica", "Valor"], "rows": tes},
        {"titulo": "Cuentas por pagar — proveedores", "headers": h_cxp, "rows": r_cxp, "totales": tot_cxp},
        {"titulo": "Cuentas por cobrar — clientes (top 10)", "headers": h_cxc, "rows": r_cxc[:10], "totales": tot_cxc},
        {"titulo": "Balance de saldos por cuenta (top 12)", "headers": h_sal, "rows": r_sal, "totales": tot_sal},
        {"titulo": "Compras por proveedor (top 10)", "headers": h_comp, "rows": r_comp},
    ]


# ---------------------------------------------------------------------------
# Informes simples existentes
# ---------------------------------------------------------------------------

def _consulta_inventario(conn: duckdb.DuckDBPyConnection, f: dict[str, Any]) -> tuple[list[str], list[list[Any]], str]:
    almacen = int(f.get("almacen") or 1)
    rows = conn.execute(
        """
        SELECT p.nombre_producto, COALESCE(it.item_type, '—'),
               CAST(COALESCE(sa.cantidad_disponible, 0) AS DOUBLE),
               CAST(COALESCE(it.unit_cost, p.precio_unitario * 0.6, 0) AS DOUBLE)
        FROM dim_producto p
        LEFT JOIN dim_item_type it ON it.id_item_type = p.id_item_type
        LEFT JOIN stock_almacen sa ON sa.id_producto = p.id_producto AND sa.id_almacen = ?
        WHERE p.activo = true
        ORDER BY p.nombre_producto
        """,
        [almacen],
    ).fetchall()
    headers = ["Producto", "Categoría", "Stock", "Costo u.", "Valor"]
    data = []
    total_val = 0.0
    for r in rows:
        stock, costo = float(r[2]), float(r[3])
        valor = stock * costo
        total_val += valor
        data.append([r[0], r[1], f"{stock:,.0f}", _fmt_money(costo), _fmt_money(valor)])
    return headers, data, f"Valor total inventario: ${total_val:,.2f}"


def _consulta_pedidos_estado(conn: duckdb.DuckDBPyConnection, f: dict[str, Any]) -> tuple[list[str], list[list[Any]], str]:
    conds, params = [], []
    if f.get("desde"):
        conds.append("fecha_pedido >= ?")
        params.append(f["desde"])
    if f.get("hasta"):
        conds.append("fecha_pedido <= ?")
        params.append(f["hasta"])
    where = ("WHERE " + " AND ".join(conds)) if conds else ""
    rows = conn.execute(
        f"""
        SELECT estado, COUNT(*), CAST(SUM(COALESCE(total, total_pedido, 0)) AS DOUBLE)
        FROM pedidos {where}
        GROUP BY estado ORDER BY COUNT(*) DESC
        """,
        params,
    ).fetchall()
    headers = ["Estado", "Cantidad", "Monto total"]
    data = [[r[0], int(r[1]), _fmt_money(r[2])] for r in rows]
    return headers, data, ""


def _consulta_clientes_cxc(conn: duckdb.DuckDBPyConnection, f: dict[str, Any]) -> tuple[list[str], list[list[Any]], str]:
    rows = conn.execute(
        """
        SELECT c.nombre_empresa, c.pais,
               (SELECT COUNT(*) FROM pedidos p WHERE p.id_cliente = c.id_cliente),
               (SELECT CAST(COALESCE(SUM(COALESCE(p.total, p.total_pedido, 0)), 0) AS DOUBLE)
                  FROM pedidos p
                 WHERE p.id_cliente = c.id_cliente AND p.estado NOT IN ('cancelado', 'borrador')),
               (SELECT CAST(COALESCE(SUM(pg.monto), 0) AS DOUBLE)
                  FROM pagos pg
                  JOIN pedidos p ON p.id_pedido = pg.id_pedido
                 WHERE p.id_cliente = c.id_cliente AND pg.estado = 'aprobado')
        FROM dim_cliente c
        WHERE EXISTS (SELECT 1 FROM pedidos p WHERE p.id_cliente = c.id_cliente)
        ORDER BY 4 DESC
        """
    ).fetchall()
    headers = ["Cliente", "País", "Pedidos", "Comprado", "Pagado", "CxC"]
    data = []
    total_cxc = 0.0
    for r in rows:
        comprado, pagado = float(r[3]), float(r[4])
        cxc = max(comprado - pagado, 0)
        total_cxc += cxc
        data.append([r[0], r[1] or "—", int(r[2]), _fmt_money(comprado), _fmt_money(pagado), _fmt_money(cxc)])
    return headers, data, f"CxC total estimada: ${total_cxc:,.2f}"


def _consulta_compras(conn: duckdb.DuckDBPyConnection, f: dict[str, Any]) -> tuple[list[str], list[list[Any]], str]:
    if not table_exists(conn, "ordenes_compra"):
        return ["ID", "Número", "Proveedor", "Fecha", "Estado", "Total", "Método", "Recepciones"], [], ""
    conds, params = [], []
    if f.get("desde"):
        conds.append("CAST(oc.fecha AS DATE) >= ?")
        params.append(f["desde"])
    if f.get("hasta"):
        conds.append("CAST(oc.fecha AS DATE) <= ?")
        params.append(f["hasta"])
    if f.get("estado"):
        conds.append("oc.estado = ?")
        params.append(f["estado"])
    where = ("WHERE " + " AND ".join(conds)) if conds else ""
    cols = [c[1] for c in conn.execute("PRAGMA table_info('ordenes_compra')").fetchall()]
    metod_col = "oc.metodo_pago" if "metodo_pago" in cols else "'caja'"
    rows = conn.execute(
        f"""
        SELECT oc.id_oc, oc.numero, pr.razon_social, oc.fecha, oc.estado,
               CAST(oc.total AS DOUBLE), {metod_col},
               COALESCE((SELECT COUNT(*) FROM recepciones_compra r WHERE r.id_oc = oc.id_oc), 0)
        FROM ordenes_compra oc
        JOIN proveedores pr ON pr.id_proveedor = oc.id_proveedor
        {where}
        ORDER BY oc.id_oc DESC
        """,
        params,
    ).fetchall()
    headers = ["ID", "Número", "Proveedor", "Fecha", "Estado", "Total", "Método", "Recepciones"]
    method_label = {"caja": "Caja", "externo": "Pago externo", "credito": "Crédito"}
    data = [
        [int(r[0]), r[1], r[2], str(r[3])[:19], r[4], _fmt_money(r[5]),
         method_label.get(r[6] or "caja", r[6] or "—"), int(r[7])]
        for r in rows
    ]
    total_compras = sum(float(r[5] or 0) for r in rows)
    return headers, data, f"Total compras: ${total_compras:,.2f} ({len(rows)} OC)"


def _consulta_rentabilidad(conn: duckdb.DuckDBPyConnection, f: dict[str, Any]) -> tuple[list[str], list[list[Any]], str]:
    conds, params = [], []
    if f.get("desde"):
        conds.append("fv.order_date >= ?")
        params.append(f["desde"])
    if f.get("hasta"):
        conds.append("fv.order_date <= ?")
        params.append(f["hasta"])
    where = ("WHERE " + " AND ".join(conds)) if conds else ""
    rows = conn.execute(
        f"""
        SELECT it.item_type,
               CAST(SUM(fv.units_sold) AS BIGINT),
               CAST(SUM(fv.total_revenue) AS DOUBLE),
               CAST(SUM(fv.total_cost) AS DOUBLE),
               CAST(SUM(fv.total_profit) AS DOUBLE)
        FROM fact_ventas fv
        LEFT JOIN dim_item_type it ON it.id_item_type = fv.id_item_type
        {where}
        {"AND" if where else "WHERE"} lower(COALESCE(it.item_type, '')) NOT IN ('peperoni', 'pepperoni')
        GROUP BY it.item_type
        HAVING ABS(COALESCE(SUM(fv.total_revenue), 0)) >= 0.01
            OR ABS(COALESCE(SUM(fv.total_profit), 0)) >= 0.01
        ORDER BY SUM(fv.total_profit) DESC
        LIMIT 200
        """,
        params,
    ).fetchall()
    headers = ["Producto", "Unidades", "Ingresos", "Costo", "Profit", "Margen %"]
    data = []
    for r in rows:
        rev, profit = float(r[2]), float(r[4])
        data.append([r[0], int(r[1]), _fmt_money(rev), _fmt_money(r[3]), _fmt_money(profit), _fmt_margen(profit, rev)])
    return headers, data, ""


def _consulta_resumen(conn: duckdb.DuckDBPyConnection, f: dict[str, Any]) -> tuple[list[str], list[list[Any]], str]:
    conds, params = [], []
    if f.get("desde"):
        conds.append("order_date >= ?")
        params.append(f["desde"])
    if f.get("hasta"):
        conds.append("order_date <= ?")
        params.append(f["hasta"])
    where = ("WHERE " + " AND ".join(conds)) if conds else ""
    n, rev, cost, profit = 0, 0.0, 0.0, 0.0
    try:
        r = conn.execute(
            f"""
            SELECT CAST(COUNT(*) AS BIGINT), CAST(SUM(total_revenue) AS DOUBLE),
                   CAST(SUM(total_cost) AS DOUBLE), CAST(SUM(total_profit) AS DOUBLE)
            FROM fact_ventas {where}
            """,
            params,
        ).fetchone()
        n, rev, cost, profit = int(r[0] or 0), float(r[1] or 0), float(r[2] or 0), float(r[3] or 0)
    except duckdb.Error:
        if table_exists(conn, "pedidos"):
            ped_row = conn.execute(
                """
                SELECT COUNT(*),
                       COALESCE(SUM(CAST(COALESCE(subtotal, total, total_pedido, 0) AS DOUBLE)), 0)
                FROM pedidos WHERE estado NOT IN ('cancelado', 'pendiente_pago', 'borrador')
                """
            ).fetchone()
            n = int(ped_row[0] or 0)
            rev = float(ped_row[1] or 0)
    headers = ["Métrica", "Valor"]
    data = [
        ["Líneas de venta", n],
        ["Ingresos", _fmt_money(rev)],
        ["Costos", _fmt_money(cost)],
        ["Profit", _fmt_money(profit)],
        ["Margen", _fmt_margen(profit, rev)],
    ]
    pedidos = 0
    if table_exists(conn, "pedidos"):
        pedidos = int(conn.execute("SELECT COUNT(*) FROM pedidos WHERE estado NOT IN ('cancelado')").fetchone()[0] or 0)
    data.append(["Pedidos activos (portal)", pedidos])
    return headers, data, ""


TITULOS = {
    "ventas": "Reporte de Ventas (Ejecutivo)",
    "ventas-detalle": "Reporte de Ventas — Detalle Completo",
    "inventario-valorizado": "Inventario Valorizado",
    "pedidos-por-estado": "Pedidos por Estado",
    "clientes-cxc": "Clientes y Cuentas por Cobrar",
    "rentabilidad-producto": "Rentabilidad por Producto",
    "resumen-financiero": "Resumen Financiero",
    "compras": "Reporte de Compras",
    "stock-bajo": "Stock Bajo — Alertas",
    "cuentas-por-pagar": "Cuentas por Pagar — Proveedores",
    "recepciones": "Recepciones de Compra",
    "kardex": "Kardex de Inventario",
    "proveedores": "Directorio de Proveedores",
    "informe-gerencial": "Informe Gerencial",
    "informe-operativo": "Informe Operativo",
    "informe-comercial": "Informe Comercial",
    "informe-logistico": "Informe Logístico",
    "informe-financiero": "Informe Financiero",
}


def generar_reporte(
    conn: duckdb.DuckDBPyConnection,
    *,
    nombre: str,
    formato: str,
    filtros: Optional[dict[str, Any]] = None,
) -> tuple[bytes, str, str]:
    """Devuelve (contenido, media_type, filename)."""
    if nombre not in REPORTES_VALIDOS:
        raise ValueError(f"Reporte desconocido: {nombre}")
    formato = (formato or "pdf").lower()
    if formato not in ("pdf", "csv"):
        raise ValueError("formato debe ser pdf o csv")

    f = filtros or {}
    try:
        from backend.services import reporte_clickhouse_service

        ch_vista = reporte_clickhouse_service.obtener_vista(nombre, f)
        if ch_vista and _vista_clickhouse_usable(ch_vista):
            return _exportar_vista(conn, ch_vista, formato)
        if ch_vista:
            logger.info("Informe %s: ClickHouse sin filas, fallback DuckDB", nombre)
    except Exception as exc:
        logger.warning("Informe %s: fallback DuckDB tras error ClickHouse: %s", nombre, exc)

    subtitulo_parts = [f"{k}={v}" for k, v in f.items() if v]
    subtitulo = " · ".join(subtitulo_parts) if subtitulo_parts else "Sin filtros"
    titulo = TITULOS[nombre]
    ext = formato
    filename = f"{nombre.replace('-', '_')}.{ext}"

    if nombre in COMPUESTOS:
        builders = {
            "informe-gerencial": _secciones_informe_gerencial,
            "informe-operativo": _secciones_informe_operativo,
            "informe-comercial": _secciones_informe_comercial,
            "informe-logistico": _secciones_informe_logistico,
            "informe-financiero": _secciones_informe_financiero,
        }
        secciones = builders[nombre](conn, f)
        if formato == "csv":
            return _secciones_to_csv(secciones), "text/csv; charset=utf-8", filename
        kpis = _kpis_compuesto(nombre, conn, f)
        return _secciones_to_pdf(conn, titulo, subtitulo, secciones, kpis), "application/pdf", filename

    if nombre == "ventas":
        if formato == "csv":
            headers, rows, _ = _consulta_ventas(conn, f)
            return _rows_to_csv(headers, rows), "text/csv; charset=utf-8", filename
        secciones = _secciones_informe_ventas(conn, f)
        kpis = _kpis_ventas_globales(conn, f)
        return _secciones_to_pdf(conn, titulo, subtitulo, secciones, kpis), "application/pdf", filename

    if nombre == "ventas-detalle":
        headers, rows, totales = _consulta_ventas(conn, f)
        if formato == "csv":
            return _rows_to_csv(headers, rows), "text/csv; charset=utf-8", filename
        kpis = _kpis_reporte(nombre, headers, rows, totales)
        return _rows_to_pdf_completo(conn, titulo, subtitulo, headers, rows, totales, kpis), "application/pdf", filename

    consultas: dict[str, Any] = {
        "inventario-valorizado": _consulta_inventario,
        "pedidos-por-estado": _consulta_pedidos_estado,
        "clientes-cxc": _consulta_clientes_cxc,
        "rentabilidad-producto": _consulta_rentabilidad,
        "compras": _consulta_compras,
        "stock-bajo": _consulta_stock_bajo,
        "cuentas-por-pagar": _consulta_cuentas_por_pagar,
        "recepciones": _consulta_recepciones,
        "kardex": _consulta_kardex,
        "proveedores": _consulta_proveedores,
    }
    consulta = consultas.get(nombre, _consulta_resumen)
    headers, rows, totales = consulta(conn, f)
    if formato == "csv":
        return _rows_to_csv(headers, rows), "text/csv; charset=utf-8", filename
    kpis = _kpis_reporte(nombre, headers, rows, totales)
    return _rows_to_pdf(conn, titulo, subtitulo, headers, rows, totales, kpis), "application/pdf", filename


def _kpis_reporte(nombre: str, headers: list[str], rows: list[list[Any]], totales: str) -> list[dict[str, str]]:
    """Resumen ejecutivo breve para la cabecera del PDF."""
    n = len(rows)
    kpis = [{"label": "Registros", "value": str(n)}]
    if totales:
        kpis.append({"label": "Resumen", "value": totales[:80]})
    if nombre == "ventas" and rows:
        try:
            rev_idx = next((i for i, h in enumerate(headers) if "ingreso" in h.lower() or h.lower() == "revenue"), None)
            if rev_idx is not None:
                total_rev = sum(float(str(r[rev_idx]).replace(",", "").replace("$", "") or 0) for r in rows)
                kpis.append({"label": "Ingresos listados", "value": f"${total_rev:,.2f}"})
        except (ValueError, TypeError):
            pass
    return kpis[:4]


def _kpis_ventas_globales(conn: duckdb.DuckDBPyConnection, f: dict[str, Any]) -> list[dict[str, str]]:
    n, unidades, rev, cost, profit = _ventas_globales(conn, f)
    return [
        {"label": "Líneas", "value": f"{n:,}"},
        {"label": "Unidades", "value": f"{unidades:,}"},
        {"label": "Ingresos", "value": _fmt_money(rev)},
        {"label": "Margen", "value": _fmt_margen(profit, rev)},
    ]


def _kpis_compuesto(nombre: str, conn: duckdb.DuckDBPyConnection, f: dict[str, Any]) -> list[dict[str, str]]:
    if nombre == "informe-gerencial":
        n, _, rev, _, profit = _ventas_globales(conn, f)
        cxp = 0.0
        try:
            _, _, tot = _consulta_cuentas_por_pagar(conn, f)
            cxp = float(tot.split("$")[1].replace(",", "")) if "$" in tot else 0.0
        except Exception:
            pass
        return [
            {"label": "Ingresos", "value": _fmt_money(rev)},
            {"label": "Profit", "value": _fmt_money(profit)},
            {"label": "Líneas", "value": f"{n:,}"},
            {"label": "CxP", "value": _fmt_money(cxp)},
        ]
    if nombre == "informe-comercial":
        n, unidades, rev, _, profit = _ventas_globales(conn, f)
        return [
            {"label": "Ingresos", "value": _fmt_money(rev)},
            {"label": "Unidades", "value": f"{unidades:,}"},
            {"label": "Profit", "value": _fmt_money(profit)},
            {"label": "Líneas", "value": f"{n:,}"},
        ]
    if nombre == "informe-logistico":
        sin_despachar = 0
        envios = 0
        recepciones = 0
        stock_bajo = 0
        try:
            _, r_sd = _pedidos_sin_despacho(conn, f, 500)
            sin_despachar = len(r_sd)
        except Exception:
            pass
        if table_exists(conn, "envios"):
            envios = int(conn.execute("SELECT COUNT(*) FROM envios").fetchone()[0] or 0)
        if table_exists(conn, "recepciones_compra"):
            recepciones = int(conn.execute("SELECT COUNT(*) FROM recepciones_compra").fetchone()[0] or 0)
        if table_exists(conn, "alertas_stock"):
            stock_bajo = int(conn.execute(
                "SELECT COUNT(*) FROM alertas_stock a JOIN stock_almacen sa ON sa.id_producto = a.id_producto AND sa.id_almacen = a.id_almacen WHERE COALESCE(a.activa, true) = true AND COALESCE(sa.cantidad_disponible, 0) < COALESCE(a.umbral_minimo, 0)"
            ).fetchone()[0] or 0)
        return [
            {"label": "Sin despachar", "value": str(sin_despachar)},
            {"label": "Envíos", "value": f"{envios:,}"},
            {"label": "Recepciones", "value": f"{recepciones:,}"},
            {"label": "Stock bajo", "value": str(stock_bajo)},
        ]
    if nombre == "informe-financiero":
        try:
            from shared.services.contabilidad_service import resumen_financiero
            res = resumen_financiero(conn)
            caja = next((c["saldo"] for c in res.get("cuentas", []) if c["codigo"] == "1101"), 0.0)
            return [
                {"label": "Caja (1101)", "value": _fmt_money(caja)},
                {"label": "Asientos", "value": str(res.get("n_asientos", 0))},
                {"label": "CxC clientes", "value": _fmt_money(_total_cxc(conn))},
                {"label": "CxP proveedores", "value": _fmt_money(_total_cxp(conn))},
            ]
        except Exception:
            return [{"label": "Caja (1101)", "value": "—"}]
    try:
        from backend.services.operaciones_service import panel_operaciones
        k = panel_operaciones(conn).get("kpis", {})
        return [
            {"label": "Caja (1101)", "value": _fmt_money(k.get("caja", 0))},
            {"label": "CxP", "value": _fmt_money(k.get("cuentas_por_pagar", 0))},
            {"label": "OC por aprobar", "value": str(k.get("oc_por_aprobar", 0))},
            {"label": "Sin despachar", "value": str(k.get("pedidos_sin_despachar", 0))},
        ]
    except Exception:
        return [{"label": "Panel operativo", "value": "—"}]


def _total_cxp(conn: duckdb.DuckDBPyConnection) -> float:
    try:
        _, _, tot = _consulta_cuentas_por_pagar(conn, {})
        return float(tot.split("$")[1].replace(",", "")) if "$" in tot else 0.0
    except Exception:
        return 0.0


def _total_cxc(conn: duckdb.DuckDBPyConnection) -> float:
    try:
        _, _, tot = _consulta_clientes_cxc(conn, {})
        return float(tot.split("$")[1].replace(",", "")) if "$" in tot else 0.0
    except Exception:
        return 0.0


DESCRIPCIONES = {
    "ventas": "Resumen ejecutivo de ventas: KPIs, ventas por país y por mes, top productos y detalle reciente.",
    "ventas-detalle": "Cada línea de venta del período (filtrable por fechas, región, canal y país).",
    "inventario-valorizado": "Stock actual por producto con costo unitario, cantidad y valor total.",
    "pedidos-por-estado": "Conteo de pedidos agrupados por estado y origen.",
    "clientes-cxc": "Clientes con saldo de cuentas por cobrar vencido y total.",
    "rentabilidad-producto": "Ingresos, costo, profit y margen por producto.",
    "resumen-financiero": "Indicadores financieros globales del período (ingresos, costos, caja, cuentas).",
    "compras": "Órdenes de compra registradas con su estado y total.",
    "stock-bajo": "Productos con stock por debajo del umbral mínimo de reposición.",
    "cuentas-por-pagar": "Saldos pendientes por proveedor y vencimiento.",
    "recepciones": "Recepciones de compra registradas en el almacén.",
    "kardex": "Movimientos de inventario por producto (entradas, salidas y periodicidad).",
    "proveedores": "Directorio completo de proveedores.",
    "informe-gerencial": "Visión integral: ventas, compras, inventario y cartera en un solo documento.",
    "informe-operativo": "Operaciones diarias: órdenes de compra, stock, recepciones y pedidos sin despachar.",
    "informe-comercial": "Área comercial: canales, campañas, clientes y rentabilidad.",
    "informe-logistico": "Logística y envíos: transportistas, zonas, tarifas y movimientos de inventario.",
    "informe-financiero": "Contabilidad: saldos por cuenta, caja y cuentas por cobrar/pagar.",
}

FILTROS_POR_REPORTE = {
    "ventas": ["desde", "hasta", "region", "country", "sales_channel", "origen", "limite"],
    "ventas-detalle": ["desde", "hasta", "region", "country", "sales_channel", "origen", "limite"],
    "inventario-valorizado": ["almacen", "producto"],
    "pedidos-por-estado": ["desde", "hasta", "origen"],
    "clientes-cxc": [],
    "rentabilidad-producto": ["desde", "hasta"],
    "resumen-financiero": ["desde", "hasta"],
    "compras": ["desde", "hasta", "estado"],
    "stock-bajo": ["almacen"],
    "cuentas-por-pagar": ["desde", "hasta"],
    "recepciones": ["desde", "hasta", "estado"],
    "kardex": ["desde", "hasta", "producto", "almacen"],
    "proveedores": [],
    "informe-gerencial": ["desde", "hasta", "region", "country"],
    "informe-operativo": ["desde", "hasta"],
    "informe-comercial": ["desde", "hasta", "region", "country", "sales_channel"],
    "informe-logistico": ["desde", "hasta"],
    "informe-financiero": ["desde", "hasta"],
}


def catalogo_reportes() -> list[dict[str, Any]]:
    """Lista de reportes disponibles para el selector de la UI."""
    items: list[dict[str, Any]] = []
    for nombre, titulo in TITULOS.items():
        items.append({
            "id": nombre,
            "titulo": titulo,
            "tipo": "compuesto" if (nombre in COMPUESTOS or nombre == "ventas") else "simple",
            "descripcion": DESCRIPCIONES.get(nombre, ""),
            "filtros": FILTROS_POR_REPORTE.get(nombre, []),
        })
    return items


def obtener_reporte_vista(
    conn: duckdb.DuckDBPyConnection,
    *,
    nombre: str,
    filtros: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Datos del reporte listos para mostrar en pantalla (sin generar PDF/CSV).

    Reportes simples devuelven {tipo:'tabla', headers, rows, totales, kpis};
    los compuestos devuelven {tipo:'compuesto', secciones:[{titulo, nota,
    headers, rows, totales}]} además de los KPIs globales.
    """
    if nombre not in REPORTES_VALIDOS:
        raise ValueError(f"Reporte desconocido: {nombre}")

    f = filtros or {}
    try:
        from backend.services import reporte_clickhouse_service

        ch = reporte_clickhouse_service.obtener_vista(nombre, f)
        if ch and _vista_clickhouse_usable(ch):
            ch.setdefault("motor", "ClickHouse")
            return ch
        if ch:
            logger.info("Vista %s: ClickHouse sin filas, fallback DuckDB", nombre)
    except Exception as exc:
        logger.warning("Vista %s: fallback DuckDB tras error ClickHouse: %s", nombre, exc)

    subtitulo_parts = [f"{k}={v}" for k, v in f.items() if v]
    subtitulo = " · ".join(subtitulo_parts) if subtitulo_parts else "Sin filtros"
    base = {
        "tipo": "compuesto",
        "nombre": nombre,
        "titulo": TITULOS[nombre],
        "subtitulo": subtitulo,
    }

    if nombre in COMPUESTOS:
        builders = {
            "informe-gerencial": _secciones_informe_gerencial,
            "informe-operativo": _secciones_informe_operativo,
            "informe-comercial": _secciones_informe_comercial,
            "informe-logistico": _secciones_informe_logistico,
            "informe-financiero": _secciones_informe_financiero,
        }
        secciones = builders[nombre](conn, f)
        if not secciones:
            raise ValueError("El reporte no devolvió secciones para los filtros indicados.")
        return {**base, "kpis": _kpis_compuesto(nombre, conn, f), "secciones": secciones, "motor": "DuckDB", "orquestacion": "Consulta operativa en línea"}

    if nombre == "ventas":
        secciones = _secciones_informe_ventas(conn, f)
        if not secciones:
            raise ValueError("El reporte no devolvió secciones para los filtros indicados.")
        return {**base, "kpis": _kpis_ventas_globales(conn, f), "secciones": secciones, "motor": "DuckDB", "orquestacion": "Consulta operativa en línea"}

    if nombre == "ventas-detalle":
        headers, rows, totales = _consulta_ventas(conn, f)
    else:
        consultas: dict[str, Any] = {
            "inventario-valorizado": _consulta_inventario,
            "pedidos-por-estado": _consulta_pedidos_estado,
            "clientes-cxc": _consulta_clientes_cxc,
            "rentabilidad-producto": _consulta_rentabilidad,
            "compras": _consulta_compras,
            "stock-bajo": _consulta_stock_bajo,
            "cuentas-por-pagar": _consulta_cuentas_por_pagar,
            "recepciones": _consulta_recepciones,
            "kardex": _consulta_kardex,
            "proveedores": _consulta_proveedores,
        }
        headers, rows, totales = consultas.get(nombre, _consulta_resumen)(conn, f)

    return {
        **base,
        "tipo": "tabla",
        "headers": headers,
        "rows": rows,
        "totales": totales,
        "kpis": _kpis_reporte(nombre, headers, rows, totales),
        "motor": "DuckDB",
        "orquestacion": "Consulta operativa en línea",
    }
