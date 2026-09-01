"""
reportlab_builder.py — PDFs con diseño profesional (sin depender de WeasyPrint/GTK).

Usado como fallback en Windows cuando WeasyPrint no está disponible.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm, mm
from reportlab.pdfgen import canvas as pdfcanvas
from reportlab.platypus import Image, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

# Paleta corporativa B2B — navy / slate / teal (documentos formales)
C_PRIMARY = colors.HexColor("#0B3A5C")       # navy profundo
C_PRIMARY_LIGHT = colors.HexColor("#1A5F8A") # azul corporativo
C_ACCENT = colors.HexColor("#0D7A6F")        # teal sobrio
C_SLATE = colors.HexColor("#1C2430")
C_MUTED = colors.HexColor("#5C6B7A")
C_BORDER = colors.HexColor("#D5DCE3")
C_ROW_ALT = colors.HexColor("#F5F7FA")
C_HEADER_BG = colors.HexColor("#0B3A5C")
C_HEADER_FG = colors.white
C_SOFT = colors.HexColor("#E8F1F6")
C_SOFT_TEAL = colors.HexColor("#E6F4F2")
C_BAND = colors.HexColor("#0B3A5C")


def _styles() -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()
    return {
        "brand": ParagraphStyle(
            "brand", parent=base["Normal"], fontSize=16, leading=20,
            textColor=C_PRIMARY, fontName="Helvetica-Bold", spaceAfter=2,
        ),
        "brand_sm": ParagraphStyle(
            "brand_sm", parent=base["Normal"], fontSize=11, leading=14,
            textColor=C_PRIMARY, fontName="Helvetica-Bold", spaceAfter=1,
        ),
        "tagline": ParagraphStyle(
            "tagline", parent=base["Normal"], fontSize=8, leading=10, textColor=C_MUTED,
        ),
        "doctitle": ParagraphStyle(
            "doctitle", parent=base["Normal"], fontSize=13, leading=16,
            textColor=C_PRIMARY, fontName="Helvetica-Bold", alignment=TA_RIGHT,
        ),
        "docmeta": ParagraphStyle(
            "docmeta", parent=base["Normal"], fontSize=9, leading=12,
            textColor=C_MUTED, alignment=TA_RIGHT,
        ),
        "section": ParagraphStyle(
            "section", parent=base["Normal"], fontSize=8, leading=10,
            textColor=C_PRIMARY, fontName="Helvetica-Bold", spaceBefore=10, spaceAfter=4,
        ),
        "body": ParagraphStyle(
            "body", parent=base["Normal"], fontSize=9, leading=12, textColor=C_SLATE,
        ),
        "footer": ParagraphStyle(
            "footer", parent=base["Normal"], fontSize=7, leading=9,
            textColor=C_MUTED, alignment=TA_CENTER,
        ),
        "cell": ParagraphStyle(
            "cell", parent=base["Normal"], fontSize=9, leading=11, textColor=C_SLATE,
        ),
        "cell_right": ParagraphStyle(
            "cell_right", parent=base["Normal"], fontSize=9, leading=11,
            textColor=C_SLATE, alignment=TA_RIGHT,
        ),
        "cell_head": ParagraphStyle(
            "cell_head", parent=base["Normal"], fontSize=8, leading=10,
            textColor=C_HEADER_FG, fontName="Helvetica-Bold",
        ),
        "cell_head_right": ParagraphStyle(
            "cell_head_right", parent=base["Normal"], fontSize=8, leading=10,
            textColor=C_HEADER_FG, fontName="Helvetica-Bold",
            alignment=TA_RIGHT,
        ),
        "cover_empresa": ParagraphStyle(
            "cover_empresa", parent=base["Normal"], fontSize=18, leading=22,
            textColor=C_PRIMARY, fontName="Helvetica-Bold", alignment=TA_CENTER, spaceAfter=2,
        ),
        "cover_tagline": ParagraphStyle(
            "cover_tagline", parent=base["Normal"], fontSize=9, leading=12,
            textColor=C_MUTED, alignment=TA_CENTER,
        ),
        "cover_title": ParagraphStyle(
            "cover_title", parent=base["Normal"], fontSize=22, leading=27,
            textColor=C_SLATE, fontName="Helvetica-Bold", alignment=TA_CENTER, spaceBefore=10,
        ),
        "cover_sub": ParagraphStyle(
            "cover_sub", parent=base["Normal"], fontSize=10, leading=14,
            textColor=C_MUTED, alignment=TA_CENTER, spaceBefore=4,
        ),
        "cover_meta": ParagraphStyle(
            "cover_meta", parent=base["Normal"], fontSize=8, leading=11,
            textColor=C_MUTED, alignment=TA_CENTER,
        ),
        "banner": ParagraphStyle(
            "banner", parent=base["Normal"], fontSize=10, leading=13,
            textColor=colors.white, fontName="Helvetica-Bold",
        ),
        "toc_num": ParagraphStyle(
            "toc_num", parent=base["Normal"], fontSize=9, leading=13,
            textColor=C_ACCENT, fontName="Helvetica-Bold",
        ),
        "toc_item": ParagraphStyle(
            "toc_item", parent=base["Normal"], fontSize=9, leading=13, textColor=C_SLATE,
        ),
        "kpi_label": ParagraphStyle(
            "kpi_label", parent=base["Normal"], fontSize=7, leading=9,
            textColor=C_MUTED, fontName="Helvetica-Bold", alignment=TA_CENTER,
        ),
        "kpi_value": ParagraphStyle(
            "kpi_value", parent=base["Normal"], fontSize=11, leading=14,
            textColor=C_PRIMARY, fontName="Helvetica-Bold", alignment=TA_CENTER,
        ),
        "total": ParagraphStyle(
            "total", parent=base["Normal"], fontSize=11, leading=14,
            textColor=C_PRIMARY, fontName="Helvetica-Bold", alignment=TA_RIGHT,
        ),
        "badge": ParagraphStyle(
            "badge", parent=base["Normal"], fontSize=8, leading=10,
            textColor=colors.white, fontName="Helvetica-Bold", alignment=TA_CENTER,
        ),
    }


def _p(text: str, style: str, st: dict[str, ParagraphStyle], *, empty: str = "—") -> Paragraph:
    raw = str(text).strip() if text is not None else ""
    safe = (raw or empty).replace("&", "&amp;")
    return Paragraph(safe, st[style])


def _load_logo_image(logo_ruta: str) -> Image | None:
    if not logo_ruta:
        return None
    logo_path = (_storage_root() / logo_ruta).resolve()
    storage = _storage_root().resolve()
    if not str(logo_path).startswith(str(storage)) or not logo_path.is_file():
        return None
    try:
        return Image(str(logo_path), width=2.4 * cm, height=1.35 * cm, kind="proportional")
    except Exception:
        return None


def _brand_cell(ctx: dict[str, Any], st: dict[str, ParagraphStyle]) -> Table:
    """Bloque izquierdo: logo + razón social en una sola fila alineada."""
    empresa = ctx.get("empresa_nombre") or "GLOBTRADE S.A."
    tagline = ctx.get("empresa_tagline") or "Comercio internacional · Distribución B2B"
    logo = _load_logo_image(ctx.get("empresa_logo") or "")

    text_tbl = Table(
        [[_p(empresa, "brand_sm" if logo else "brand", st)], [_p(tagline, "tagline", st)]],
        colWidths=[7.2 * cm],
    )
    text_tbl.setStyle(TableStyle([
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))

    if logo:
        outer = Table([[logo, text_tbl]], colWidths=[2.7 * cm, 7.3 * cm])
        outer.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ("TOPPADDING", (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ("LEFTPADDING", (1, 0), (1, 0), 8),
        ]))
        return outer

    wrap = Table([[text_tbl]], colWidths=[10 * cm])
    wrap.setStyle(TableStyle([
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
    ]))
    return wrap


def _is_blank_meta(value: Any) -> bool:
    if value is None:
        return True
    s = str(value).strip()
    return not s or s in ("—", "-", "–", "--", "N/A", "n/a")


def _doc_meta_cell(ctx: dict[str, Any], st: dict[str, ParagraphStyle]) -> list[Any]:
    """Bloque derecho: título y metadatos (sin rayas vacías)."""
    titulo = ctx.get("titulo") or "Comprobante"
    rows: list[Any] = [_p(titulo, "doctitle", st)]

    numero = ctx.get("numero")
    if not _is_blank_meta(numero):
        rows.append(_p(f"<b>{numero}</b>", "docmeta", st))

    fecha = ctx.get("fecha")
    if not _is_blank_meta(fecha):
        rows.append(_p(str(fecha), "docmeta", st))
    elif _is_blank_meta(numero) and not _is_blank_meta(ctx.get("fecha_generacion")):
        rows.append(_p(f"Generado: {ctx['fecha_generacion']}", "docmeta", st))

    subtitulo = ctx.get("subtitulo")
    if not _is_blank_meta(subtitulo) and subtitulo not in ("Sin filtros",):
        rows.append(_p(str(subtitulo), "docmeta", st))

    meta_tbl = Table([[r] for r in rows], colWidths=[8 * cm])
    meta_tbl.setStyle(TableStyle([
        ("ALIGN", (0, 0), (-1, -1), "RIGHT"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]))
    return [meta_tbl]


def _storage_root() -> Path:
    return Path(__file__).resolve().parent.parent / "storage"


def _header_block(ctx: dict[str, Any], st: dict[str, ParagraphStyle]) -> list[Any]:
    left = _brand_cell(ctx, st)
    right_items = _doc_meta_cell(ctx, st)

    top_band = Table([[""]], colWidths=[18 * cm], rowHeights=[5])
    top_band.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), C_BAND),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
    ]))

    accent = Table([[""]], colWidths=[18 * cm], rowHeights=[2.5])
    accent.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), C_ACCENT),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
    ]))

    tbl = Table([[left, right_items[0]]], colWidths=[10 * cm, 8 * cm])
    tbl.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
        ("BACKGROUND", (0, 0), (-1, -1), C_SOFT),
        ("BOX", (0, 0), (-1, -1), 0.4, C_BORDER),
        ("LEFTPADDING", (0, 0), (0, 0), 10),
        ("RIGHTPADDING", (1, 0), (1, 0), 10),
        ("TOPPADDING", (0, 0), (-1, -1), 10),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
    ]))

    return [top_band, accent, Spacer(1, 3 * mm), tbl, Spacer(1, 6 * mm)]


def _info_grid(rows: list[tuple[str, str]], st: dict[str, ParagraphStyle]) -> Table:
    data = [[_p(f"<b>{k}:</b> {v}", "body", st)] for k, v in rows]
    tbl = Table(data, colWidths=[18 * cm])
    tbl.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    return tbl


def _lines_table(items: list[dict[str, Any]], st: dict[str, ParagraphStyle], *, cost_mode: bool = False) -> Table:
    if cost_mode:
        headers = ["Producto", "Cant.", "Costo u.", "Subtotal"]
        rows = [
            [
                _p(i.get("producto", ""), "cell", st),
                _p(str(i.get("cantidad", "")), "cell_right", st),
                _p(i.get("costo_fmt", ""), "cell_right", st),
                _p(i.get("subtotal_fmt", ""), "cell_right", st),
            ]
            for i in items
        ]
    else:
        headers = ["Producto", "Cant.", "P. unit.", "Subtotal"]
        rows = [
            [
                _p(i.get("producto", ""), "cell", st),
                _p(str(i.get("cantidad", "")), "cell_right", st),
                _p(i.get("precio_unitario_fmt", ""), "cell_right", st),
                _p(i.get("subtotal_fmt", ""), "cell_right", st),
            ]
            for i in items
        ]

    head = [[_p(h, "cell_head", st) for h in headers]]
    data = head + rows
    col_w = [9.5 * cm, 2 * cm, 3 * cm, 3.5 * cm]
    tbl = Table(data, colWidths=col_w, repeatRows=1)
    style_cmds = [
        ("BACKGROUND", (0, 0), (-1, 0), C_HEADER_BG),
        ("TEXTCOLOR", (0, 0), (-1, 0), C_HEADER_FG),
        ("LINEBELOW", (0, 0), (-1, 0), 0, C_HEADER_BG),
        ("LINEBELOW", (0, 1), (-1, -1), 0.4, C_BORDER),
        ("BOX", (0, 0), (-1, -1), 0.6, C_BORDER),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
    ]
    for i in range(1, len(data)):
        if i % 2 == 0:
            style_cmds.append(("BACKGROUND", (0, i), (-1, i), C_ROW_ALT))
    tbl.setStyle(TableStyle(style_cmds))
    return tbl


def _totals_block(
    lines: list[tuple[str, str]],
    st: dict[str, ParagraphStyle],
    *,
    grand_label: str = "Total",
    grand_value: str | None = None,
) -> Table:
    rows = []
    for label, value in lines:
        rows.append([
            _p(label, "body", st),
            _p(value, "cell_right", st),
        ])
    final = grand_value if grand_value is not None else (lines[-1][1] if lines else "$0.00")
    rows.append([
        _p(f"<b>{grand_label}</b>", "total", st),
        _p(f"<b>{final}</b>", "total", st),
    ])
    tbl = Table(rows, colWidths=[4 * cm, 4 * cm])
    tbl.setStyle(TableStyle([
        ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
        ("LINEABOVE", (0, -1), (-1, -1), 2, C_PRIMARY_LIGHT),
        ("TOPPADDING", (0, -1), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -2), 3),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
    ]))
    wrapper = Table([[None, tbl]], colWidths=[10 * cm, 8 * cm])
    wrapper.setStyle(TableStyle([("ALIGN", (1, 0), (1, 0), "RIGHT")]))
    return wrapper


def _build_venta_doc(ctx: dict[str, Any], story: list[Any], st: dict[str, ParagraphStyle], *, mode: str) -> None:
    cliente = ctx.get("cliente") or {}
    pedido = ctx.get("pedido") or {}
    factura = ctx.get("factura") or {}

    story.append(_p("DATOS DEL CLIENTE", "section", st))
    info_rows = [
        ("Empresa", cliente.get("empresa") or "—"),
        ("País", cliente.get("pais") or "—"),
    ]
    if mode == "factura":
        info_rows += [
            ("Pedido ref.", pedido.get("numero") or "—"),
            ("Estado factura", factura.get("estado") or "—"),
        ]
    else:
        info_rows += [
            ("Pedido interno", pedido.get("numero") or "—"),
            ("Estado", pedido.get("estado") or "—"),
        ]
    story.append(_info_grid(info_rows, st))
    story.append(Spacer(1, 5 * mm))

    story.append(_p("DETALLE DE PRODUCTOS", "section", st))
    story.append(_lines_table(ctx.get("items") or [], st))
    story.append(Spacer(1, 4 * mm))

    total_lines: list[tuple[str, str]] = [("Subtotal", ctx.get("subtotal_fmt") or "$0.00")]
    if ctx.get("descuento_fmt"):
        total_lines.append((f"Descuento ({ctx.get('descuento_pct', '')}%)", f"−{ctx['descuento_fmt']}"))
    iva = ctx.get("iva_pct", 18)
    total_lines.append((f"IGV / IVA ({iva}%)", ctx.get("impuesto_fmt") or "$0.00"))
    grand = "Total factura" if mode == "factura" else "Total"
    story.append(_totals_block(
        total_lines, st, grand_label=grand, grand_value=ctx.get("total_fmt") or "$0.00",
    ))

    notas = pedido.get("notas")
    if notas:
        story.append(Spacer(1, 5 * mm))
        story.append(_p(f"<b>Notas:</b> {notas}", "body", st))


def _build_pago_doc(ctx: dict[str, Any], story: list[Any], st: dict[str, ParagraphStyle]) -> None:
    pago = ctx.get("pago") or {}
    pedido = ctx.get("pedido") or {}
    cliente = ctx.get("cliente") or {}

    story.append(_p("DATOS DEL PAGO", "section", st))
    story.append(_info_grid([
        ("Cliente", cliente.get("empresa") or "—"),
        ("Método", pago.get("metodo") or "—"),
        ("Pedido", pedido.get("numero") or "—"),
        ("Referencia", pago.get("referencia") or "—"),
        ("Estado", pago.get("estado") or "—"),
        ("Monto pagado", ctx.get("monto_fmt") or "—"),
    ], st))
    story.append(Spacer(1, 8 * mm))

    monto_box = Table(
        [[_p("MONTO CONFIRMADO", "section", st)], [_p(ctx.get("monto_fmt") or "$0.00", "total", st)]],
        colWidths=[18 * cm],
    )
    monto_box.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), C_SOFT_TEAL),
        ("BOX", (0, 0), (-1, -1), 1, C_ACCENT),
        ("LINEBEFORE", (0, 0), (0, -1), 4, C_ACCENT),
        ("TOPPADDING", (0, 0), (-1, -1), 10),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
        ("LEFTPADDING", (0, 0), (-1, -1), 12),
        ("ALIGN", (0, 1), (-1, 1), "CENTER"),
    ]))
    story.append(monto_box)
    story.append(Spacer(1, 6 * mm))
    story.append(_p(
        f"Se confirma el pago recibido por el monto indicado, asociado al pedido "
        f"<b>{pedido.get('numero') or '—'}</b>.",
        "body", st,
    ))


_NUMERIC_CELL_RE = re.compile(r"^[$€]?[-+]?(?:\d{1,3}(?:,\d{3})*|\d+)(?:\.\d+)?%?$")


def _detect_numeric_cols(headers: list[str], rows: list[list[Any]], sample: int = 40) -> list[bool]:
    """Una columna es numérica si la mayoría de sus valores parecen números."""
    numeric: list[bool] = []
    for col in range(len(headers)):
        vals = [r[col] for r in rows[:sample] if r[col] not in (None, "", "—")]
        if not vals:
            numeric.append(False)
            continue
        hits = sum(1 for v in vals if _NUMERIC_CELL_RE.match(str(v).strip()))
        numeric.append(hits / len(vals) >= 0.8)
    return numeric


def _generic_data_table(
    headers: list[str],
    rows: list[list[Any]],
    st: dict[str, ParagraphStyle],
) -> Table:
    numeric = _detect_numeric_cols(headers, rows)
    head = [[_p(h, "cell_head_right" if numeric[i] else "cell_head", st) for i, h in enumerate(headers)]]
    body = [
        [
            _p(str(cell) if cell is not None else "—", "cell_right" if numeric[col_idx] else "cell", st)
            for col_idx, cell in enumerate(row)
        ]
        for row in rows
    ]
    data = head + body
    ncols = max(len(headers), 1)
    width = 18 * cm
    col_w = [width / ncols] * ncols
    tbl = Table(data, colWidths=col_w, repeatRows=1)
    style_cmds = [
        ("BACKGROUND", (0, 0), (-1, 0), C_HEADER_BG),
        ("BOX", (0, 0), (-1, -1), 0.6, C_BORDER),
        ("LINEBELOW", (0, 1), (-1, -1), 0.4, C_BORDER),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
    ]
    for col, is_num in enumerate(numeric):
        align = "RIGHT" if is_num else "LEFT"
        style_cmds.append(("ALIGN", (col, 0), (col, 0), align))
    for i in range(1, len(data)):
        if i % 2 == 0:
            style_cmds.append(("BACKGROUND", (0, i), (-1, i), C_ROW_ALT))
    tbl.setStyle(TableStyle(style_cmds))
    return tbl


def _render_secciones(ctx: dict[str, Any], story: list[Any], st: dict[str, ParagraphStyle]) -> None:
    """Informes compuestos: una sección por página con su propia tabla y totales."""
    for i, sec in enumerate(ctx.get("secciones") or []):
        if i > 0:
            story.append(PageBreak())
        story.append(_p(sec.get("titulo") or "Sección", "section", st))
        story.append(Spacer(1, 4 * mm))

        sec_kpis = sec.get("kpis")
        if sec_kpis:
            kpi_cells = []
            for k in sec_kpis[:4]:
                kpi_cells.append([
                    _p(k.get("label") or "", "section", st),
                    _p(k.get("value") or "—", "cell", st),
                ])
            kpi_tbl = Table(kpi_cells, colWidths=[4.5 * cm] * len(kpi_cells))
            kpi_tbl.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, -1), C_ROW_ALT),
                ("BOX", (0, 0), (-1, -1), 0.5, C_BORDER),
                ("TOPPADDING", (0, 0), (-1, -1), 8),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ]))
            story.append(kpi_tbl)
            story.append(Spacer(1, 5 * mm))

        headers = sec.get("headers") or []
        rows = sec.get("rows") or []
        if headers and rows:
            story.append(_generic_data_table(headers, rows, st))
        elif not rows:
            story.append(_p("Sin registros para los filtros aplicados.", "body", st))

        totales = sec.get("totales") or ""
        if totales:
            story.append(Spacer(1, 4 * mm))
            tot_box = Table([[_p(totales, "total", st)]], colWidths=[18 * cm])
            tot_box.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, -1), C_SOFT),
                ("LEFTPADDING", (0, 0), (-1, -1), 12),
                ("TOPPADDING", (0, 0), (-1, -1), 10),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
                ("LINEBEFORE", (0, 0), (0, -1), 4, C_PRIMARY_LIGHT),
                ("BOX", (0, 0), (-1, -1), 0.5, C_BORDER),
            ]))
            story.append(tot_box)

        nota = sec.get("nota")
        if nota:
            story.append(Spacer(1, 4 * mm))
            story.append(_p(nota, "total", st))


class _NumberedCanvas(pdfcanvas.Canvas):
    """Canvas que numera páginas como 'Página X de Y' (dos pasadas)."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._saved_page_states: list[dict[str, Any]] = []

    def showPage(self) -> None:
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self) -> None:
        num_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self._draw_footer(num_pages)
            super().showPage()
        super().save()

    def _draw_footer(self, total_pages: int) -> None:
        self.saveState()
        self.setStrokeColor(C_BORDER)
        self.setLineWidth(0.5)
        self.line(2 * cm, 1.5 * cm, A4[0] - 2 * cm, 1.5 * cm)
        self.setFont("Helvetica", 7)
        self.setFillColor(C_MUTED)
        self.drawCentredString(A4[0] / 2, 1.05 * cm, f"Página {self._pageNumber} de {total_pages}")
        self.restoreState()


def _kpi_cards(kpis: list[dict[str, str]], st: dict[str, ParagraphStyle]) -> Table:
    """Filas de tarjetas KPI reutilizables (portada y secciones)."""
    cards = kpis[:4]
    n = len(cards)
    if n == 0:
        return Table([[]], colWidths=[18 * cm])
    cols = 4 if n == 4 else (3 if n == 3 else 2)
    rows_cells: list[list[Any]] = []
    for i in range(0, n, cols):
        row = []
        for k in cards[i:i + cols]:
            row.append([
                _p(k.get("label") or "", "kpi_label", st),
                _p(k.get("value") or "—", "kpi_value", st),
            ])
        while len(row) < cols:
            row.append(["", ""])
        rows_cells.append(row)
    tbl = Table(rows_cells, colWidths=[18 / cols * cm] * cols)
    tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), C_ROW_ALT),
        ("BOX", (0, 0), (-1, -1), 0.5, C_BORDER),
        ("INNERGRID", (0, 0), (-1, -1), 0.5, C_BORDER),
        ("TOPPADDING", (0, 0), (-1, -1), 9),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 9),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))
    return tbl


def _informe_cover(ctx: dict[str, Any], story: list[Any], st: dict[str, ParagraphStyle]) -> None:
    """Portada del informe: marca, título, período, KPIs y metadatos."""
    empresa = ctx.get("empresa_nombre") or "GLOBTRADE S.A."
    tagline = ctx.get("empresa_tagline") or "Comercio internacional · Distribución B2B"
    logo = _load_logo_image(ctx.get("empresa_logo") or "")

    story.append(Spacer(1, 2.4 * cm))
    if logo:
        logo_wrap = Table([[logo]], colWidths=[18 * cm])
        logo_wrap.setStyle(TableStyle([
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ]))
        story.append(logo_wrap)
        story.append(Spacer(1, 6 * mm))
    story.append(_p(empresa, "cover_empresa", st))
    story.append(_p(tagline, "cover_tagline", st))

    story.append(Spacer(1, 1.6 * cm))
    band = Table([[_p("", "banner", st)]], colWidths=[10 * cm])
    band.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), C_PRIMARY),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
    ]))
    band_wrap = Table([[band]], colWidths=[18 * cm])
    band_wrap.setStyle(TableStyle([("ALIGN", (0, 0), (-1, -1), "CENTER")]))
    story.append(band_wrap)
    story.append(Spacer(1, 4 * mm))

    story.append(_p(ctx.get("titulo") or "Informe", "cover_title", st))
    sub = ctx.get("subtitulo") or ""
    story.append(_p(sub if sub != "Sin filtros" else "Período: sin filtros", "cover_sub", st))

    story.append(Spacer(1, 1.4 * cm))
    kpis = ctx.get("kpis") or []
    if kpis:
        story.append(_kpi_cards(kpis, st))

    story.append(Spacer(1, 2.6 * cm))
    story.append(_p(
        f"Generado el {ctx.get('fecha_generacion', '')} · Documento electrónico de uso interno · {empresa}",
        "cover_meta", st,
    ))
    story.append(PageBreak())


def _informe_toc(ctx: dict[str, Any], story: list[Any], st: dict[str, ParagraphStyle]) -> None:
    """Índice de secciones del informe."""
    story.append(_p("CONTENIDO DEL INFORME", "section", st))
    story.append(Spacer(1, 3 * mm))
    secciones = ctx.get("secciones") or []
    toc_rows = [
        [_p(f"{i:02d}", "toc_num", st), _p(s.get("titulo") or "—", "toc_item", st)]
        for i, s in enumerate(secciones, 1)
    ]
    tbl = Table(toc_rows, colWidths=[1.5 * cm, 16.5 * cm])
    tbl.setStyle(TableStyle([
        ("LINEBELOW", (0, i), (-1, i), 0.4, C_BORDER) for i in range(0, len(toc_rows))
    ] + [
        ("TOPPADDING", (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
        ("LEFTPADDING", (0, 0), (0, -1), 0),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))
    story.append(tbl)
    story.append(PageBreak())


def _informe_seccion(sec: dict[str, Any], idx: int, story: list[Any], st: dict[str, ParagraphStyle]) -> None:
    """Sección numerada con banda de color, KPIs opcionales, tabla y totales."""
    banner = Table([[_p(f"{idx:02d}  ·  {sec.get('titulo') or 'Sección'}", "banner", st)]], colWidths=[18 * cm])
    banner.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), C_PRIMARY),
        ("TOPPADDING", (0, 0), (-1, -1), 10),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
        ("LEFTPADDING", (0, 0), (-1, -1), 12),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))
    story.append(banner)
    story.append(Spacer(1, 5 * mm))

    sec_kpis = sec.get("kpis")
    if sec_kpis:
        story.append(_kpi_cards(sec_kpis, st))
        story.append(Spacer(1, 5 * mm))

    headers = sec.get("headers") or []
    rows = sec.get("rows") or []
    if headers and rows:
        story.append(_generic_data_table(headers, rows, st))
    elif not rows:
        story.append(_p("Sin registros para los filtros aplicados.", "body", st))

    totales = sec.get("totales") or ""
    if totales:
        story.append(Spacer(1, 4 * mm))
        tot_box = Table([[_p(totales, "total", st)]], colWidths=[18 * cm])
        tot_box.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), C_SOFT),
            ("LEFTPADDING", (0, 0), (-1, -1), 12),
            ("TOPPADDING", (0, 0), (-1, -1), 10),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
            ("LINEBEFORE", (0, 0), (0, -1), 4, C_PRIMARY_LIGHT),
            ("BOX", (0, 0), (-1, -1), 0.5, C_BORDER),
        ]))
        story.append(tot_box)

    nota = sec.get("nota")
    if nota:
        story.append(Spacer(1, 4 * mm))
        story.append(_p(nota, "total", st))


def _build_informe_doc(ctx: dict[str, Any], story: list[Any], st: dict[str, ParagraphStyle]) -> None:
    """Informe compuesto profesional: portada, índice y secciones numeradas."""
    _informe_cover(ctx, story, st)
    _informe_toc(ctx, story, st)
    for i, sec in enumerate(ctx.get("secciones") or []):
        _informe_seccion(sec, i + 1, story, st)


def _build_reporte_doc(ctx: dict[str, Any], story: list[Any], st: dict[str, ParagraphStyle]) -> None:
    # Informes compuestos (varias secciones)
    if ctx.get("secciones"):
        _render_secciones(ctx, story, st)
        return

    # Subtítulo y fecha ya van en el encabezado; aquí solo KPIs y tabla.
    kpis = ctx.get("kpis") or []
    if kpis:
        kpi_cells = []
        for k in kpis[:4]:
            kpi_cells.append([
                _p(k.get("label") or "", "section", st),
                _p(k.get("value") or "—", "cell", st),
            ])
        kpi_tbl = Table(kpi_cells, colWidths=[4.5 * cm] * len(kpi_cells))
        kpi_tbl.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), C_ROW_ALT),
            ("BOX", (0, 0), (-1, -1), 0.5, C_BORDER),
            ("TOPPADDING", (0, 0), (-1, -1), 8),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
            ("LEFTPADDING", (0, 0), (-1, -1), 8),
            ("RIGHTPADDING", (0, 0), (-1, -1), 8),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ]))
        story.append(kpi_tbl)
        story.append(Spacer(1, 5 * mm))

    headers = ctx.get("headers") or []
    rows = ctx.get("rows") or []
    if headers and rows:
        story.append(_generic_data_table(headers, rows, st))
    elif not rows:
        story.append(_p("Sin registros para los filtros aplicados.", "body", st))

    totales = ctx.get("totales") or ""
    if totales:
        story.append(Spacer(1, 5 * mm))
        tot_box = Table([[_p(totales, "total", st)]], colWidths=[18 * cm])
        tot_box.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), C_SOFT),
            ("LEFTPADDING", (0, 0), (-1, -1), 12),
            ("TOPPADDING", (0, 0), (-1, -1), 10),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
            ("LINEBEFORE", (0, 0), (0, -1), 4, C_PRIMARY_LIGHT),
            ("BOX", (0, 0), (-1, -1), 0.5, C_BORDER),
        ]))
        story.append(tot_box)


def _build_oc_doc(ctx: dict[str, Any], story: list[Any], st: dict[str, ParagraphStyle]) -> None:
    orden = ctx.get("orden") or {}
    proveedor = ctx.get("proveedor") or {}
    story.append(_p("PROVEEDOR", "section", st))
    story.append(_info_grid([
        ("Razón social", proveedor.get("razon_social") or "—"),
        ("Estado OC", orden.get("estado") or "—"),
    ], st))
    story.append(Spacer(1, 5 * mm))
    story.append(_p("DETALLE", "section", st))
    story.append(_lines_table(ctx.get("items") or [], st, cost_mode=True))
    story.append(Spacer(1, 4 * mm))
    story.append(_totals_block([], st, grand_label="Total", grand_value=ctx.get("total_fmt") or "$0.00"))


def _build_cotizacion_doc(ctx: dict[str, Any], story: list[Any], st: dict[str, ParagraphStyle]) -> None:
    cliente = ctx.get("cliente") or {}
    cot = ctx.get("cotizacion") or {}
    story.append(_p("DATOS DE LA COTIZACIÓN", "section", st))
    story.append(_info_grid([
        ("Cliente", cliente.get("empresa") or "—"),
        ("Validez", cot.get("validez") or "30 días"),
        ("País", cliente.get("pais") or "—"),
        ("Referencia", ctx.get("numero") or "—"),
    ], st))
    story.append(Spacer(1, 5 * mm))
    story.append(_p("DETALLE COTIZADO", "section", st))
    story.append(_lines_table(ctx.get("items") or [], st))
    story.append(Spacer(1, 4 * mm))
    story.append(_totals_block(
        [("Subtotal", ctx.get("subtotal_fmt") or ctx.get("total_fmt") or "$0.00")],
        st, grand_label="Total cotizado", grand_value=ctx.get("total_fmt") or "$0.00",
    ))


def _build_nota_credito_doc(ctx: dict[str, Any], story: list[Any], st: dict[str, ParagraphStyle]) -> None:
    cliente = ctx.get("cliente") or {}
    story.append(_p("NOTA DE CRÉDITO", "section", st))
    story.append(_info_grid([
        ("Cliente", cliente.get("empresa") or "—"),
        ("Factura ref.", ctx.get("factura_ref") or "—"),
        ("Motivo", ctx.get("motivo") or "Devolución / ajuste"),
        ("Monto NC", ctx.get("total_fmt") or "—"),
    ], st))
    story.append(Spacer(1, 8 * mm))
    monto_box = Table(
        [[_p("MONTO ACREDITADO", "section", st)], [_p(ctx.get("total_fmt") or "$0.00", "total", st)]],
        colWidths=[18 * cm],
    )
    monto_box.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), C_SOFT_TEAL),
        ("BOX", (0, 0), (-1, -1), 1, C_ACCENT),
        ("LINEBEFORE", (0, 0), (0, -1), 4, C_ACCENT),
        ("TOPPADDING", (0, 0), (-1, -1), 10),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
        ("LEFTPADDING", (0, 0), (-1, -1), 12),
        ("ALIGN", (0, 1), (-1, 1), "CENTER"),
    ]))
    story.append(monto_box)


def _build_guia_doc(ctx: dict[str, Any], story: list[Any], st: dict[str, ParagraphStyle]) -> None:
    envio = ctx.get("envio") or {}
    cliente = ctx.get("cliente") or {}
    pedido = ctx.get("pedido") or {}
    story.append(_p("DATOS DE ENVÍO", "section", st))
    story.append(_info_grid([
        ("Cliente", cliente.get("empresa") or "—"),
        ("País", cliente.get("pais") or "—"),
        ("Pedido", pedido.get("numero") or ctx.get("pedido_numero") or "—"),
        ("Transportadora", envio.get("transportadora") or "—"),
        ("Estado", envio.get("estado") or "—"),
        ("Zona", envio.get("zona") or "—"),
        ("Dirección", ctx.get("direccion") or "—"),
    ], st))
    story.append(Spacer(1, 5 * mm))
    story.append(_p("MERCANCÍA", "section", st))
    items = ctx.get("items") or []
    if items:
        # Guía: solo producto + cantidad
        headers = ["Producto", "Cantidad"]
        rows = [[i.get("producto", "—"), str(i.get("cantidad", ""))] for i in items]
        story.append(_generic_data_table(headers, rows, st))
    else:
        story.append(_p("Sin ítems asociados.", "body", st))


def render_pdf_reportlab(template_name: str, context: dict[str, Any], output_path: Path) -> Path:
    """Genera PDF con tablas y estilos corporativos."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    st = _styles()
    story: list[Any] = []

    es_informe = template_name == "reportes/base_reporte.html" and context.get("informe")
    if es_informe:
        _build_informe_doc(context, story, st)
        doc = SimpleDocTemplate(
            str(output_path),
            pagesize=A4,
            leftMargin=2 * cm,
            rightMargin=2 * cm,
            topMargin=1.5 * cm,
            bottomMargin=2 * cm,
            title=context.get("titulo") or "Informe",
        )
        doc.build(story, canvasmaker=_NumberedCanvas)
        return output_path

    story.extend(_header_block(context, st))

    if template_name == "factura.html":
        _build_venta_doc(context, story, st, mode="factura")
    elif template_name == "pedido.html":
        _build_venta_doc(context, story, st, mode="pedido")
    elif template_name == "comprobante_pago.html":
        _build_pago_doc(context, story, st)
    elif template_name == "orden_compra.html":
        _build_oc_doc(context, story, st)
    elif template_name == "guia_remision.html":
        _build_guia_doc(context, story, st)
    elif template_name == "cotizacion.html":
        _build_cotizacion_doc(context, story, st)
    elif template_name == "nota_credito.html":
        _build_nota_credito_doc(context, story, st)
    elif template_name == "reportes/base_reporte.html":
        _build_reporte_doc(context, story, st)
    else:
        story.append(_p(context.get("titulo") or "Documento", "doctitle", st))
        story.append(Spacer(1, 4 * mm))
        if context.get("items"):
            story.append(_lines_table(context["items"], st))

    story.append(Spacer(1, 12 * mm))
    empresa = context.get("empresa_nombre") or "GlobalTrade S.A."
    foot = Table([[""]], colWidths=[18 * cm], rowHeights=[1.8])
    foot.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), C_ACCENT),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
    ]))
    story.append(foot)
    story.append(Spacer(1, 3 * mm))
    story.append(_p(
        f"Documento generado electrónicamente — {empresa} · {context.get('fecha_generacion', '')}",
        "footer", st,
    ))

    doc = SimpleDocTemplate(
        str(output_path),
        pagesize=A4,
        leftMargin=2 * cm,
        rightMargin=2 * cm,
        topMargin=1.5 * cm,
        bottomMargin=1.5 * cm,
        title=context.get("numero") or "Comprobante",
    )
    doc.build(story)
    return output_path
