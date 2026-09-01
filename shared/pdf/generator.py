"""
generator.py — HTML → PDF con WeasyPrint y fallback ReportLab estructurado.

En Windows (sin GTK/WeasyPrint) se usa reportlab_builder con diseño profesional,
no extracción de texto plano del HTML.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, select_autoescape

from shared.database.connection import repo_root
from shared.pdf.reportlab_builder import render_pdf_reportlab

logger = logging.getLogger(__name__)

TEMPLATES_DIR = repo_root() / "shared" / "templates" / "comprobantes"


def _jinja_env() -> Environment:
    return Environment(
        loader=FileSystemLoader(str(TEMPLATES_DIR)),
        autoescape=select_autoescape(["html", "xml"]),
    )


def render_template(template_name: str, context: dict[str, Any]) -> str:
    """Renderiza una plantilla Jinja2 a HTML."""
    tpl = _jinja_env().get_template(template_name)
    return tpl.render(**context)


def html_to_pdf(html: str, output_path: Path) -> Path:
    """Convierte HTML a PDF usando WeasyPrint si está disponible."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    from weasyprint import HTML  # type: ignore

    HTML(string=html, base_url=str(TEMPLATES_DIR)).write_pdf(str(output_path))
    logger.info("PDF generado con WeasyPrint: %s", output_path)
    return output_path


def generar_pdf_desde_plantilla(
    template_name: str,
    context: dict[str, Any],
    output_path: Path,
) -> Path:
    """Genera PDF con ReportLab; WeasyPrint solo si está instalado."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        return render_pdf_reportlab(template_name, context, output_path)
    except Exception as exc:
        logger.warning("ReportLab falló (%s); intento WeasyPrint.", exc)
        try:
            import weasyprint  # noqa: F401
        except ImportError as imp_err:
            raise RuntimeError(
                f"No se pudo generar el PDF (ReportLab: {exc}). "
                "WeasyPrint no está disponible en este entorno."
            ) from imp_err
        try:
            html = render_template(template_name, context)
            return html_to_pdf(html, output_path)
        except Exception as exc2:
            logger.error("No se pudo generar PDF: %s / %s", exc, exc2)
            raise
