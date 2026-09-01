"""
marketing_service.py — Banners y promociones activas del portal B2B.
"""

from __future__ import annotations

from typing import Any

import duckdb

from shared.database.connection import table_exists


def listar_banners_activos(conn: duckdb.DuckDBPyConnection) -> list[dict[str, Any]]:
    if not table_exists(conn, "banners_portal"):
        return []
    rows = conn.execute(
        """
        SELECT id_banner, titulo, imagen_path, enlace, orden
        FROM banners_portal WHERE activo = true
        ORDER BY orden, id_banner
        """
    ).fetchall()
    return [
        {
            "id_banner": int(r[0]), "titulo": r[1],
            "imagen_url": _imagen_banner_url(r[2]),
            "enlace": r[3] or "/pages/catalogo.html", "orden": int(r[4] or 0),
        }
        for r in rows
    ]


def _imagen_banner_url(path: str | None) -> str | None:
    if not path:
        return None
    p = str(path).strip()
    if p.startswith(("http://", "https://")):
        return p
    if p.startswith("/media/"):
        return p
    if p.startswith("/pages/") or p.endswith(".html"):
        return None
    if p.startswith("/"):
        p = p.lstrip("/")
    return f"/media/{p}"


def listar_promociones_activas(conn: duckdb.DuckDBPyConnection) -> list[dict[str, Any]]:
    if not table_exists(conn, "promociones"):
        return []
    rows = conn.execute(
        """
        SELECT id_promocion, nombre, CAST(descuento_pct AS DOUBLE), fecha_inicio, fecha_fin
        FROM promociones
        WHERE activa = true AND (fecha_fin IS NULL OR fecha_fin >= current_date)
        ORDER BY descuento_pct DESC
        """
    ).fetchall()
    return [
        {
            "id_promocion": int(r[0]), "nombre": r[1], "descuento_pct": float(r[2]),
            "fecha_inicio": str(r[3]) if r[3] else None, "fecha_fin": str(r[4]) if r[4] else None,
        }
        for r in rows
    ]


def datos_home(conn: duckdb.DuckDBPyConnection) -> dict[str, Any]:
    return {
        "banners": listar_banners_activos(conn),
        "promociones": listar_promociones_activas(conn),
        "carrusel": listar_carrusel_productos(conn),
    }


def listar_carrusel_productos(conn: duckdb.DuckDBPyConnection) -> list[dict[str, Any]]:
    """Productos destacados del home. Si hay IDs en config, usa esos; si no, muestra hasta 8 activos."""
    from gmbackend.services.producto_service import _imagen_publica
    from shared.services.config_service import obtener_config

    raw = (obtener_config(conn, "PORTAL_CARRUSEL_IDS", "") or "").strip()
    ids: list[int] = []
    if raw:
        for part in raw.replace(";", ",").split(","):
            part = part.strip()
            if part.isdigit():
                ids.append(int(part))

    if not table_exists(conn, "dim_producto"):
        return []

    if ids:
        placeholders = ",".join(["?"] * len(ids))
        rows = conn.execute(
            f"""
            SELECT p.id_producto, p.nombre_producto, p.imagen_url,
                   CAST(p.precio_mayorista AS DOUBLE), CAST(COALESCE(p.descuento_pct, 0) AS DOUBLE),
                   CAST(p.precio_rebajado AS DOUBLE), m.nombre, l.nombre
            FROM dim_producto p
            LEFT JOIN marcas m ON m.id_marca = p.id_marca
            LEFT JOIN lineas_producto l ON l.id_linea = p.id_linea
            WHERE p.id_producto IN ({placeholders}) AND COALESCE(p.activo, true) = true
            """,
            ids,
        ).fetchall()
        by_id = {int(r[0]): r for r in rows}
        ordered = [by_id[i] for i in ids if i in by_id]
    else:
        ordered = conn.execute(
            """
            SELECT p.id_producto, p.nombre_producto, p.imagen_url,
                   CAST(p.precio_mayorista AS DOUBLE), CAST(COALESCE(p.descuento_pct, 0) AS DOUBLE),
                   CAST(p.precio_rebajado AS DOUBLE), m.nombre, l.nombre
            FROM dim_producto p
            LEFT JOIN marcas m ON m.id_marca = p.id_marca
            LEFT JOIN lineas_producto l ON l.id_linea = p.id_linea
            WHERE COALESCE(p.activo, true) = true
            ORDER BY COALESCE(p.descuento_pct, 0) DESC, p.id_producto
            LIMIT 8
            """
        ).fetchall()

    out = []
    for r in ordered:
        dto = float(r[4] or 0)
        mayorista = float(r[3] or 0)
        rebajado = float(r[5]) if r[5] is not None else None
        if rebajado is None and dto > 0 and mayorista > 0:
            rebajado = round(mayorista * (1 - dto / 100.0), 2)
        out.append({
            "id_producto": int(r[0]),
            "nombre_producto": r[1],
            "imagen_url": _imagen_publica(r[2]),
            "precio_mayorista": mayorista,
            "descuento_pct": dto,
            "precio_rebajado": rebajado,
            "marca": r[6],
            "linea": r[7],
        })
    return out

