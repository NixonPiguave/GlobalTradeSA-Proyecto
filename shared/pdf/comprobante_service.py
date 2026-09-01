"""
comprobante_service.py — Numeración por serie, generación y registro de PDFs.

Los PDFs se guardan en shared/storage/comprobantes/ y se registran en la tabla
`comprobantes` para reutilización (idempotente por tipo + entidad).
"""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Optional
from zoneinfo import ZoneInfo

import duckdb

from shared.database.connection import column_exists, repo_root, table_exists
from shared.pdf.generator import generar_pdf_desde_plantilla
from shared.services.config_service import obtener_config

logger = logging.getLogger(__name__)

_TZ_EC = ZoneInfo("America/Guayaquil")


def _ahora_ec() -> str:
    return datetime.now(_TZ_EC).strftime("%Y-%m-%d %H:%M")


def _fecha_ec() -> str:
    return datetime.now(_TZ_EC).strftime("%Y-%m-%d")

TIPOS_VALIDOS = {
    "pedido", "factura", "comprobante_pago", "guia_remision",
    "orden_compra", "cotizacion", "nota_credito",
}
PREFIJOS = {
    "pedido": "PED", "factura": "FAC", "comprobante_pago": "PAG",
    "guia_remision": "GRE", "orden_compra": "OC", "cotizacion": "COT", "nota_credito": "NC",
}
PLANTILLAS = {
    "pedido": "pedido.html", "factura": "factura.html", "comprobante_pago": "comprobante_pago.html",
    "guia_remision": "guia_remision.html", "orden_compra": "orden_compra.html",
    "cotizacion": "cotizacion.html", "nota_credito": "nota_credito.html",
}
TITULOS = {
    "pedido": "Comprobante de Pedido", "factura": "Factura de Venta",
    "comprobante_pago": "Comprobante de Pago", "guia_remision": "Guía de Remisión",
    "orden_compra": "Orden de Compra", "cotizacion": "Cotización", "nota_credito": "Nota de Crédito",
}


def storage_dir() -> Path:
    d = repo_root() / "shared" / "storage" / "comprobantes"
    d.mkdir(parents=True, exist_ok=True)
    return d


def pdf_abs_path(rel_path: str) -> Path:
    """Ruta absoluta del PDF a partir del pdf_path relativo (comprobantes/...)."""
    return repo_root() / "shared" / "storage" / rel_path


def _fmt_money(v: float) -> str:
    return f"${v:,.2f}"


def siguiente_numero(conn: duckdb.DuckDBPyConnection, tipo: str) -> tuple[str, str]:
    """Incremento atómico de serie. Devuelve (serie, numero_visible)."""
    if tipo not in TIPOS_VALIDOS:
        raise ValueError(f"Tipo de comprobante inválido: {tipo}")
    anio = datetime.now(_TZ_EC).year
    prefijo = PREFIJOS[tipo]
    serie = f"{prefijo}-{anio}"

    row = conn.execute(
        "SELECT id_serie, ultimo_numero FROM comprobante_series WHERE tipo = ? AND serie = ? AND anio = ?",
        [tipo, serie, anio],
    ).fetchone()
    if row:
        nuevo = int(row[1]) + 1
        conn.execute("UPDATE comprobante_series SET ultimo_numero = ? WHERE id_serie = ?", [nuevo, int(row[0])])
    else:
        nuevo = 1
        conn.execute(
            """
            INSERT INTO comprobante_series (id_serie, tipo, serie, anio, ultimo_numero)
            VALUES ((SELECT COALESCE(MAX(id_serie), 0) + 1 FROM comprobante_series), ?, ?, ?, ?)
            """,
            [tipo, serie, anio, nuevo],
        )
    numero = f"{serie}-{nuevo:06d}"
    return serie, numero


def _registrar_comprobante(
    conn: duckdb.DuckDBPyConnection,
    *,
    tipo: str,
    serie: str,
    numero: str,
    entidad_tipo: str,
    entidad_id: int,
    pdf_path: str,
    id_usuario: Optional[int],
) -> int:
    existente = conn.execute(
        "SELECT id_comprobante FROM comprobantes WHERE tipo = ? AND entidad_tipo = ? AND entidad_id = ?",
        [tipo, entidad_tipo, entidad_id],
    ).fetchone()
    if existente:
        conn.execute(
            "UPDATE comprobantes SET serie=?, numero=?, pdf_path=?, fecha_generacion=current_timestamp, id_usuario=? WHERE id_comprobante=?",
            [serie, numero, pdf_path, id_usuario, int(existente[0])],
        )
        return int(existente[0])
    conn.execute(
        """
        INSERT INTO comprobantes (id_comprobante, tipo, serie, numero, entidad_tipo, entidad_id, pdf_path, id_usuario)
        VALUES ((SELECT COALESCE(MAX(id_comprobante), 0) + 1 FROM comprobantes), ?, ?, ?, ?, ?, ?, ?)
        RETURNING id_comprobante
        """,
        [tipo, serie, numero, entidad_tipo, entidad_id, pdf_path, id_usuario],
    )
    return int(conn.fetchone()[0])


def obtener_comprobante_meta(
    conn: duckdb.DuckDBPyConnection, *, tipo: str, entidad_id: int
) -> Optional[dict[str, Any]]:
    r = conn.execute(
        """
        SELECT id_comprobante, tipo, serie, numero, entidad_tipo, entidad_id, pdf_path, fecha_generacion
        FROM comprobantes WHERE tipo = ? AND entidad_id = ?
        ORDER BY id_comprobante DESC LIMIT 1
        """,
        [tipo, entidad_id],
    ).fetchone()
    if not r:
        return None
    return {
        "id_comprobante": int(r[0]), "tipo": r[1], "serie": r[2], "numero": r[3],
        "entidad_tipo": r[4], "entidad_id": int(r[5]), "pdf_path": r[6],
        "fecha_generacion": str(r[7]) if r[7] else None,
    }


def _enriquecer_ctx(conn: duckdb.DuckDBPyConnection, ctx: dict[str, Any]) -> dict[str, Any]:
    ctx["empresa_nombre"] = obtener_config(conn, "EMPRESA_NOMBRE", "GLOBTRADE S.A.")
    ctx["empresa_tagline"] = obtener_config(conn, "EMPRESA_TAGLINE", "Comercio internacional · Distribución B2B")
    ctx["empresa_logo"] = obtener_config(conn, "EMPRESA_LOGO", "")
    return ctx


def _contexto_pedido(conn: duckdb.DuckDBPyConnection, id_pedido: int) -> dict[str, Any]:
    desc_cols = ""
    if column_exists(conn, "pedidos", "descuento_pct"):
        desc_cols = ", CAST(COALESCE(p.descuento_pct, 0) AS DOUBLE), CAST(COALESCE(p.descuento_monto, 0) AS DOUBLE)"
    r = conn.execute(
        f"""
        SELECT p.numero, p.estado, p.notas, CAST(COALESCE(p.subtotal,0) AS DOUBLE),
               CAST(COALESCE(p.impuesto_monto,0) AS DOUBLE), CAST(COALESCE(p.total,0) AS DOUBLE),
               c.nombre_empresa, c.pais
               {desc_cols}
        FROM pedidos p JOIN dim_cliente c ON c.id_cliente = p.id_cliente WHERE p.id_pedido = ?
        """,
        [id_pedido],
    ).fetchone()
    if not r:
        raise ValueError(f"Pedido {id_pedido} no encontrado.")
    items_raw = conn.execute(
        """
        SELECT pr.nombre_producto, d.cantidad, CAST(d.precio_unitario AS DOUBLE), CAST(d.subtotal AS DOUBLE)
        FROM pedido_detalle d JOIN dim_producto pr ON pr.id_producto = d.id_producto WHERE d.id_pedido = ?
        """,
        [id_pedido],
    ).fetchall()
    iva_row = conn.execute("SELECT valor FROM configuracion_sistema WHERE clave = 'IVA_PCT'").fetchone()
    iva_pct = float(iva_row[0]) if iva_row else 18.0
    items = [
        {"producto": i[0], "cantidad": int(i[1]), "precio_unitario_fmt": _fmt_money(float(i[2])), "subtotal_fmt": _fmt_money(float(i[3]))}
        for i in items_raw
    ]
    subtotal, impuesto, total = float(r[3]), float(r[4]), float(r[5])
    desc_pct, desc_monto = (float(r[8] or 0), float(r[9] or 0)) if len(r) > 9 else (0.0, 0.0)
    ahora = _ahora_ec()
    ctx = {
        "titulo": TITULOS["pedido"], "numero": "", "fecha": _fecha_ec(), "fecha_generacion": ahora,
        "pedido": {"numero": r[0], "estado": r[1], "notas": r[2]},
        "cliente": {"empresa": r[6], "pais": r[7]},
        "items": items, "iva_pct": iva_pct,
        "subtotal_fmt": _fmt_money(subtotal), "impuesto_fmt": _fmt_money(impuesto), "total_fmt": _fmt_money(total),
        "descuento_pct": desc_pct, "descuento_fmt": _fmt_money(desc_monto) if desc_monto > 0 else None,
    }
    return _enriquecer_ctx(conn, ctx)


def _contexto_factura(conn: duckdb.DuckDBPyConnection, id_factura: int) -> dict[str, Any]:
    from shared.services.factura_service import asegurar_detalle_factura

    asegurar_detalle_factura(conn, id_factura)
    r = conn.execute(
        """
        SELECT f.numero, f.estado, CAST(f.subtotal AS DOUBLE), CAST(f.impuesto_monto AS DOUBLE),
               CAST(f.total AS DOUBLE), p.numero, c.nombre_empresa, c.pais
        FROM facturas_venta f
        JOIN pedidos p ON p.id_pedido = f.id_pedido
        JOIN dim_cliente c ON c.id_cliente = f.id_cliente
        WHERE f.id_factura = ?
        """,
        [id_factura],
    ).fetchone()
    if not r:
        raise ValueError(f"Factura {id_factura} no encontrada.")
    items_raw = conn.execute(
        """
        SELECT pr.nombre_producto, d.cantidad, CAST(d.precio_unitario AS DOUBLE), CAST(d.subtotal AS DOUBLE)
        FROM factura_venta_detalle d JOIN dim_producto pr ON pr.id_producto = d.id_producto WHERE d.id_factura = ?
        """,
        [id_factura],
    ).fetchall()
    iva_row = conn.execute("SELECT valor FROM configuracion_sistema WHERE clave = 'IVA_PCT'").fetchone()
    iva_pct = float(iva_row[0]) if iva_row else 18.0
    items = [
        {"producto": i[0], "cantidad": int(i[1]), "precio_unitario_fmt": _fmt_money(float(i[2])), "subtotal_fmt": _fmt_money(float(i[3]))}
        for i in items_raw
    ]
    ahora = _ahora_ec()
    ctx = {
        "titulo": TITULOS["factura"], "numero": r[0], "fecha": _fecha_ec(), "fecha_generacion": ahora,
        "factura": {"numero": r[0], "estado": r[1]},
        "pedido": {"numero": r[5]},
        "cliente": {"empresa": r[6], "pais": r[7]},
        "items": items, "iva_pct": iva_pct,
        "subtotal_fmt": _fmt_money(float(r[2])), "impuesto_fmt": _fmt_money(float(r[3])), "total_fmt": _fmt_money(float(r[4])),
    }
    return _enriquecer_ctx(conn, ctx)


def _contexto_pago(conn: duckdb.DuckDBPyConnection, id_pago: int) -> dict[str, Any]:
    r = conn.execute(
        """
        SELECT pg.numero, pg.estado, CAST(pg.monto AS DOUBLE), pg.referencia, mp.nombre,
               p.numero, c.nombre_empresa
        FROM pagos pg
        JOIN pedidos p ON p.id_pedido = pg.id_pedido
        JOIN dim_cliente c ON c.id_cliente = p.id_cliente
        LEFT JOIN metodos_pago mp ON mp.id_metodo = pg.id_metodo
        WHERE pg.id_pago = ?
        """,
        [id_pago],
    ).fetchone()
    if not r:
        raise ValueError(f"Pago {id_pago} no encontrado.")
    ahora = _ahora_ec()
    ctx = {
        "titulo": TITULOS["comprobante_pago"], "numero": r[0], "fecha": _fecha_ec(), "fecha_generacion": ahora,
        "pago": {"numero": r[0], "estado": r[1], "referencia": r[3], "metodo": r[4] or "simulado"},
        "pedido": {"numero": r[5]},
        "cliente": {"empresa": r[6]},
        "monto_fmt": _fmt_money(float(r[2])),
    }
    return _enriquecer_ctx(conn, ctx)


def _contexto_orden_compra(conn: duckdb.DuckDBPyConnection, id_oc: int) -> dict[str, Any]:
    r = conn.execute(
        """
        SELECT oc.numero, oc.estado, CAST(oc.total AS DOUBLE), pr.razon_social
        FROM ordenes_compra oc JOIN proveedores pr ON pr.id_proveedor = oc.id_proveedor WHERE oc.id_oc = ?
        """,
        [id_oc],
    ).fetchone()
    if not r:
        raise ValueError(f"Orden de compra {id_oc} no encontrada.")
    items_raw = conn.execute(
        """
        SELECT p.nombre_producto, CAST(d.cantidad AS DOUBLE), CAST(d.costo_unitario AS DOUBLE), CAST(d.subtotal AS DOUBLE)
        FROM orden_compra_detalle d JOIN dim_producto p ON p.id_producto = d.id_producto WHERE d.id_oc = ?
        """,
        [id_oc],
    ).fetchall()
    items = [
        {"producto": i[0], "cantidad": i[1], "costo_fmt": _fmt_money(float(i[2])), "subtotal_fmt": _fmt_money(float(i[3]))}
        for i in items_raw
    ]
    ahora = _ahora_ec()
    ctx = {
        "titulo": TITULOS["orden_compra"], "numero": r[0], "fecha": _fecha_ec(), "fecha_generacion": ahora,
        "orden": {"numero": r[0], "estado": r[1]},
        "proveedor": {"razon_social": r[3]},
        "items": items, "total_fmt": _fmt_money(float(r[2])),
    }
    return _enriquecer_ctx(conn, ctx)


def _contexto_guia_remision(conn: duckdb.DuckDBPyConnection, id_envio: int) -> dict[str, Any]:
    row = conn.execute(
        """
        SELECT e.fecha_despacho, e.estado, t.nombre, p.numero,
               c.nombre_empresa, c.pais, COALESCE(c.direccion, ''), z.nombre
        FROM envios e
        JOIN pedidos p ON p.id_pedido = e.id_pedido
        JOIN dim_cliente c ON c.id_cliente = p.id_cliente
        LEFT JOIN transportistas t ON t.id_transportista = e.id_transportista
        LEFT JOIN zonas_envio z ON z.id_zona = e.id_zona
        WHERE e.id_envio = ?
        """,
        [id_envio],
    ).fetchone()
    if not row:
        raise ValueError(f"Envío {id_envio} no encontrado.")
    fecha_despacho, estado, transportadora, numero_pedido, empresa, pais, direccion, zona = row
    items_raw = conn.execute(
        """
        SELECT pr.nombre_producto, d.cantidad
        FROM pedido_detalle d
        JOIN dim_producto pr ON pr.id_producto = d.id_producto
        WHERE d.id_pedido = (SELECT id_pedido FROM envios WHERE id_envio = ?)
        """,
        [id_envio],
    ).fetchall()
    items = [{"producto": i[0], "cantidad": int(i[1])} for i in items_raw]
    ahora = _ahora_ec()
    ctx = {
        "titulo": TITULOS["guia_remision"],
        "numero": "", "fecha": (str(fecha_despacho)[:10]) if fecha_despacho else _fecha_ec(),
        "fecha_generacion": ahora,
        "envio": {"id_envio": id_envio, "estado": estado, "transportadora": transportadora or "—", "zona": zona or ""},
        "cliente": {"empresa": empresa, "pais": pais},
        "pedido": {"numero": numero_pedido},
        "pedido_numero": numero_pedido,
        "direccion": direccion or "",
        "items": items,
    }
    return _enriquecer_ctx(conn, ctx)


def _contexto_cotizacion(conn: duckdb.DuckDBPyConnection, id_cotizacion: int) -> dict[str, Any]:
    if not table_exists(conn, "cotizaciones"):
        raise ValueError("Módulo de cotizaciones no disponible.")
    r = conn.execute(
        """
        SELECT c.numero, c.estado, CAST(COALESCE(c.total, 0) AS DOUBLE), c.validez,
               cl.nombre_empresa, cl.pais
        FROM cotizaciones c
        JOIN dim_cliente cl ON cl.id_cliente = c.id_cliente
        WHERE c.id_cotizacion = ?
        """,
        [id_cotizacion],
    ).fetchone()
    if not r:
        raise ValueError(f"Cotización {id_cotizacion} no encontrada.")
    items_raw = conn.execute(
        """
        SELECT p.nombre_producto, d.cantidad, CAST(d.precio AS DOUBLE), CAST(d.subtotal AS DOUBLE)
        FROM cotizacion_detalle d
        JOIN dim_producto p ON p.id_producto = d.id_producto
        WHERE d.id_cotizacion = ?
        """,
        [id_cotizacion],
    ).fetchall()
    items = [
        {
            "producto": i[0],
            "cantidad": int(i[1]),
            "precio_unitario_fmt": _fmt_money(float(i[2])),
            "subtotal_fmt": _fmt_money(float(i[3])),
        }
        for i in items_raw
    ]
    validez = str(r[3])[:10] if r[3] else "30 días"
    ctx = {
        "titulo": TITULOS["cotizacion"],
        "numero": r[0] or f"COT-{id_cotizacion}",
        "fecha": _fecha_ec(),
        "fecha_generacion": _ahora_ec(),
        "cliente": {"empresa": r[4], "pais": r[5]},
        "cotizacion": {"validez": validez, "estado": r[1]},
        "items": items,
        "total_fmt": _fmt_money(float(r[2])),
    }
    return _enriquecer_ctx(conn, ctx)


def _contexto_nota_credito(conn: duckdb.DuckDBPyConnection, id_devolucion: int) -> dict[str, Any]:
    if not table_exists(conn, "devoluciones_cliente"):
        raise ValueError("Módulo de devoluciones no disponible.")
    r = conn.execute(
        """
        SELECT d.motivo, CAST(COALESCE(d.total, 0) AS DOUBLE), d.estado,
               p.numero, c.nombre_empresa, f.numero
        FROM devoluciones_cliente d
        JOIN pedidos p ON p.id_pedido = d.id_pedido
        JOIN dim_cliente c ON c.id_cliente = p.id_cliente
        LEFT JOIN facturas_venta f ON f.id_pedido = p.id_pedido
        WHERE d.id_devolucion = ?
        """,
        [id_devolucion],
    ).fetchone()
    if not r:
        raise ValueError(f"Devolución {id_devolucion} no encontrada.")
    ctx = {
        "titulo": TITULOS["nota_credito"],
        "numero": f"NC-{id_devolucion:06d}",
        "fecha": _fecha_ec(),
        "fecha_generacion": _ahora_ec(),
        "cliente": {"empresa": r[4]},
        "factura_ref": r[5] or r[3],
        "motivo": r[0] or "Devolución / ajuste",
        "total_fmt": _fmt_money(float(r[1])),
        "pedido": {"numero": r[3]},
    }
    return _enriquecer_ctx(conn, ctx)


def _construir_contexto(conn: duckdb.DuckDBPyConnection, tipo: str, entidad_id: int) -> dict[str, Any]:
    if tipo == "pedido":
        return _contexto_pedido(conn, entidad_id)
    if tipo == "factura":
        return _contexto_factura(conn, entidad_id)
    if tipo == "comprobante_pago":
        return _contexto_pago(conn, entidad_id)
    if tipo == "orden_compra":
        return _contexto_orden_compra(conn, entidad_id)
    if tipo == "guia_remision":
        return _contexto_guia_remision(conn, entidad_id)
    if tipo == "cotizacion":
        return _contexto_cotizacion(conn, entidad_id)
    if tipo == "nota_credito":
        return _contexto_nota_credito(conn, entidad_id)
    ahora = _ahora_ec()
    ctx = {"titulo": TITULOS.get(tipo, tipo), "numero": f"{PREFIJOS.get(tipo,'DOC')}-{entidad_id}", "fecha": _fecha_ec(), "fecha_generacion": ahora, "cliente": {"empresa": "—"}, "items": [], "total_fmt": "$0.00", "pedido": {"numero": ""}}
    return _enriquecer_ctx(conn, ctx)


def verificar_acceso_cliente(
    conn: duckdb.DuckDBPyConnection, *, tipo: str, entidad_id: int, id_cliente: int
) -> bool:
    """True si el comprobante pertenece al cliente."""
    if tipo == "pedido":
        r = conn.execute("SELECT 1 FROM pedidos WHERE id_pedido = ? AND id_cliente = ?", [entidad_id, id_cliente]).fetchone()
        return bool(r)
    if tipo == "factura":
        r = conn.execute("SELECT 1 FROM facturas_venta WHERE id_factura = ? AND id_cliente = ?", [entidad_id, id_cliente]).fetchone()
        return bool(r)
    if tipo == "comprobante_pago":
        r = conn.execute(
            "SELECT 1 FROM pagos pg JOIN pedidos p ON p.id_pedido = pg.id_pedido WHERE pg.id_pago = ? AND p.id_cliente = ?",
            [entidad_id, id_cliente],
        ).fetchone()
        return bool(r)
    return False


def generar_pdf(
    conn: duckdb.DuckDBPyConnection,
    *,
    tipo: str,
    entidad_id: int,
    id_usuario: Optional[int] = None,
    forzar: bool = False,
) -> dict[str, Any]:
    """Genera el PDF del comprobante. Reutiliza número de serie si ya existe; siempre refresca el archivo."""
    if tipo not in TIPOS_VALIDOS:
        raise ValueError(f"Tipo inválido: {tipo}")

    meta_prev = obtener_comprobante_meta(conn, tipo=tipo, entidad_id=entidad_id)
    ctx = _construir_contexto(conn, tipo, entidad_id)

    if meta_prev:
        serie, numero = meta_prev["serie"], meta_prev["numero"]
        nombre_archivo = Path(meta_prev["pdf_path"]).name
    elif tipo == "factura":
        fila = conn.execute(
            "SELECT numero FROM facturas_venta WHERE id_factura = ?",
            [entidad_id],
        ).fetchone()
        if fila and fila[0]:
            numero = fila[0]
            serie = numero.rsplit("-", 1)[0] if "-" in numero else numero
            nombre_archivo = f"{tipo}_{entidad_id}_{numero.replace('/', '-')}.pdf"
        else:
            serie, numero = siguiente_numero(conn, tipo)
            nombre_archivo = f"{tipo}_{entidad_id}_{numero.replace('/', '-')}.pdf"
    else:
        serie, numero = siguiente_numero(conn, tipo)
        nombre_archivo = f"{tipo}_{entidad_id}_{numero.replace('/', '-')}.pdf"

    ctx["numero"] = numero
    abs_path = storage_dir() / nombre_archivo
    generar_pdf_desde_plantilla(PLANTILLAS[tipo], ctx, abs_path)

    rel_path = f"comprobantes/{nombre_archivo}"
    entidad_tipo = {
        "pedido": "pedido", "factura": "factura", "comprobante_pago": "pago",
        "orden_compra": "orden_compra", "guia_remision": "envio",
        "cotizacion": "cotizacion", "nota_credito": "devolucion",
    }.get(tipo, tipo)
    id_comp = _registrar_comprobante(
        conn, tipo=tipo, serie=serie, numero=numero,
        entidad_tipo=entidad_tipo, entidad_id=entidad_id,
        pdf_path=rel_path, id_usuario=id_usuario,
    )
    return {
        "id_comprobante": id_comp, "tipo": tipo, "serie": serie, "numero": numero,
        "pdf_path": rel_path, "abs_path": str(abs_path),
    }


def leer_pdf_bytes(conn: duckdb.DuckDBPyConnection, *, tipo: str, entidad_id: int, id_usuario: Optional[int] = None) -> tuple[bytes, str]:
    """Devuelve (bytes, filename) del PDF, generándolo si hace falta."""
    meta = generar_pdf(conn, tipo=tipo, entidad_id=entidad_id, id_usuario=id_usuario)
    path = pdf_abs_path(meta["pdf_path"])
    if not path.exists():
        raise FileNotFoundError(f"PDF no encontrado: {path}")
    return path.read_bytes(), f"{meta['numero']}.pdf"
