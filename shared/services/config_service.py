"""
config_service.py — Parámetros configurables del sistema (IVA, MOQ, etc.).
"""

from __future__ import annotations

from typing import Any, Optional

import duckdb

from shared.database.connection import table_exists

DEFAULTS: dict[str, tuple[str, str]] = {
    "IVA_PCT": ("18", "Porcentaje de IVA aplicado en checkout"),
    "MOQ_MAYORISTA": ("10", "Cantidad mínima para precio mayorista"),
    "EMPRESA_NOMBRE": ("GLOBTRADE S.A.", "Nombre legal en comprobantes y reportes"),
    "EMPRESA_TAGLINE": ("Comercio internacional · Distribución B2B", "Subtítulo en documentos PDF"),
    "EMPRESA_LOGO": ("", "Ruta del logo en facturas y comprobantes PDF"),
    "IA_API_KEY": ("", "Clave API del proveedor IA (Groq, OpenAI, etc.)"),
    "IA_BASE_URL": ("https://api.groq.com/openai/v1", "URL base compatible con OpenAI"),
    "IA_MODEL": ("llama-3.3-70b-versatile", "Modelo IA por defecto"),
}

CLAVES_SENSIBLES: frozenset[str] = frozenset({"IA_API_KEY"})
CLAVES_IA: frozenset[str] = frozenset({"IA_API_KEY", "IA_BASE_URL", "IA_MODEL"})
# Parámetros gestionados en otras pantallas del admin (no editar en tabla genérica).
CLAVES_OCULTAS_PANEL: frozenset[str] = CLAVES_IA | frozenset({"PORTAL_CARRUSEL_IDS"})


def _ensure_table(conn: duckdb.DuckDBPyConnection) -> None:
    if not table_exists(conn, "configuracion_sistema"):
        return
    for clave, (valor, descripcion) in DEFAULTS.items():
        conn.execute(
            """
            INSERT INTO configuracion_sistema (clave, valor, descripcion)
            SELECT ?, ?, ?
            WHERE NOT EXISTS (SELECT 1 FROM configuracion_sistema WHERE clave = ?)
            """,
            [clave, valor, descripcion, clave],
        )


def enmascarar_secreto(valor: str) -> str:
    v = (valor or "").strip()
    if not v:
        return ""
    if len(v) <= 8:
        return "••••••••"
    return f"{v[:4]}…{v[-4:]}"


def listar_config(conn: duckdb.DuckDBPyConnection, *, incluir_ia: bool = False) -> list[dict[str, Any]]:
    if not table_exists(conn, "configuracion_sistema"):
        return []
    _ensure_table(conn)
    rows = conn.execute(
        "SELECT clave, valor, descripcion FROM configuracion_sistema ORDER BY clave"
    ).fetchall()
    items = [{"clave": r[0], "valor": r[1], "descripcion": r[2]} for r in rows]
    if incluir_ia:
        return items
    return [i for i in items if i["clave"] not in CLAVES_OCULTAS_PANEL]


def obtener_config(conn: duckdb.DuckDBPyConnection, clave: str, default: str = "") -> str:
    if not table_exists(conn, "configuracion_sistema"):
        return default
    _ensure_table(conn)
    row = conn.execute(
        "SELECT valor FROM configuracion_sistema WHERE clave = ?", [clave]
    ).fetchone()
    return str(row[0]) if row and row[0] is not None else default


def obtener_config_float(conn: duckdb.DuckDBPyConnection, clave: str, default: float) -> float:
    try:
        return float(obtener_config(conn, clave, str(default)))
    except (TypeError, ValueError):
        return default


def obtener_config_int(conn: duckdb.DuckDBPyConnection, clave: str, default: int) -> int:
    try:
        return int(float(obtener_config(conn, clave, str(default))))
    except (TypeError, ValueError):
        return default


def actualizar_config(conn: duckdb.DuckDBPyConnection, clave: str, valor: str) -> None:
    if not table_exists(conn, "configuracion_sistema"):
        raise ValueError("Tabla de configuración no disponible.")
    _ensure_table(conn)
    exists = conn.execute(
        "SELECT 1 FROM configuracion_sistema WHERE clave = ?", [clave]
    ).fetchone()
    if exists:
        conn.execute(
            "UPDATE configuracion_sistema SET valor = ? WHERE clave = ?",
            [valor, clave],
        )
    else:
        desc = DEFAULTS.get(clave, ("", ""))[1] or clave
        conn.execute(
            "INSERT INTO configuracion_sistema (clave, valor, descripcion) VALUES (?, ?, ?)",
            [clave, valor, desc],
        )
