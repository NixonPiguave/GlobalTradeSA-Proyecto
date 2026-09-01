"""Consultas logísticas de solo lectura compartidas (portal + admin)."""

from __future__ import annotations

from typing import Any, Optional

import duckdb

from shared.services.red_bodegas import MACRO_LABELS, macro_de_region


def resolver_destino_por_pais(
    conn: duckdb.DuckDBPyConnection, pais: Optional[str]
) -> dict[str, Any]:
    """País → dim_country → región → macro-zona logística."""
    pais_n = (pais or "").strip()
    if not pais_n:
        return {
            "pais": None,
            "id_country": None,
            "id_region": None,
            "region": None,
            "macro_zona": None,
            "macro_label": None,
        }
    row = conn.execute(
        """
        SELECT c.id_country, c.country, c.id_region, r.region
        FROM dim_country c
        LEFT JOIN dim_region r ON r.id_region = c.id_region
        WHERE lower(c.country) = lower(?)
        ORDER BY c.id_country
        LIMIT 1
        """,
        [pais_n],
    ).fetchone()
    if not row:
        row = conn.execute(
            """
            SELECT c.id_country, c.country, c.id_region, r.region
            FROM dim_country c
            LEFT JOIN dim_region r ON r.id_region = c.id_region
            WHERE lower(c.country) LIKE lower(?)
            ORDER BY length(c.country) ASC, c.id_country
            LIMIT 1
            """,
            [f"%{pais_n}%"],
        ).fetchone()
    if not row:
        return {
            "pais": pais_n,
            "id_country": None,
            "id_region": None,
            "region": None,
            "macro_zona": None,
            "macro_label": None,
        }
    id_region = int(row[2]) if row[2] is not None else None
    macro = macro_de_region(id_region)
    return {
        "pais": row[1],
        "id_country": int(row[0]),
        "id_region": id_region,
        "region": row[3],
        "macro_zona": macro,
        "macro_label": MACRO_LABELS.get(macro or "", macro),
    }


def listar_transportistas_macro(
    conn: duckdb.DuckDBPyConnection, *, macro_zona: Optional[str]
) -> list[dict[str, Any]]:
    if not macro_zona:
        return []
    try:
        from shared.database.connection import table_exists

        if not table_exists(conn, "transportistas"):
            return []
        rows = conn.execute(
            """
            SELECT id_transportista, nombre
            FROM transportistas
            WHERE activo = true
              AND lower(COALESCE(macro_zona, '')) = lower(?)
            ORDER BY nombre
            """,
            [macro_zona],
        ).fetchall()
    except Exception:
        return []
    return [{"id_transportista": int(r[0]), "nombre": r[1]} for r in rows]


def listar_zonas_macro(
    conn: duckdb.DuckDBPyConnection, *, macro_zona: Optional[str]
) -> list[dict[str, Any]]:
    if not macro_zona:
        return []
    try:
        from shared.database.connection import table_exists
        if not table_exists(conn, "zonas_envio"):
            return []
        has_macro = bool(
            conn.execute(
                "SELECT 1 FROM information_schema.columns WHERE table_name = 'zonas_envio' AND column_name = 'macro_zona'"
            ).fetchone()
        )
        if has_macro:
            has_activo = bool(
                conn.execute(
                    "SELECT 1 FROM information_schema.columns WHERE table_name = 'zonas_envio' AND column_name = 'activo'"
                ).fetchone()
            )
            filtro_activo = " AND activo = true" if has_activo else ""
            rows = conn.execute(
                f"""
                SELECT id_zona, nombre, CAST(COALESCE(costo_base, 0) AS DOUBLE)
                FROM zonas_envio
                WHERE lower(COALESCE(macro_zona, '')) = lower(?){filtro_activo}
                ORDER BY nombre
                """,
                [macro_zona],
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT id_zona, nombre, CAST(COALESCE(costo_base, 0) AS DOUBLE)
                FROM zonas_envio
                ORDER BY nombre LIMIT 5
                """
            ).fetchall()
    except Exception:
        return []
    return [
        {"id_zona": int(r[0]), "nombre": r[1], "costo_base": float(r[2]), "tarifas": []}
        for r in rows
    ]


def estimar_envio_por_pais(
    conn: duckdb.DuckDBPyConnection, *, pais: Optional[str]
) -> dict[str, Any]:
    dest = resolver_destino_por_pais(conn, pais)
    macro = dest.get("macro_zona")
    transportistas = listar_transportistas_macro(conn, macro_zona=macro) if macro else []
    zonas = listar_zonas_macro(conn, macro_zona=macro) if macro else []
    costo_base = float(zonas[0]["costo_base"]) if zonas else None
    return {
        **dest,
        "transportistas": transportistas,
        "zonas": zonas,
        "costo_estimado": costo_base,
        "mensaje": (
            f"Envíos a {dest.get('pais')} usan la red {dest.get('macro_label')}."
            if macro
            else "Indique un país de entrega válido para calcular la zona logística."
        ),
    }
