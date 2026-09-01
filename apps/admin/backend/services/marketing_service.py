"""
marketing_service.py — Banners y promociones del portal B2B (gestión admin).
"""

from __future__ import annotations

from typing import Any, Optional

import duckdb

from shared.database.connection import table_exists


def listar_banners(conn: duckdb.DuckDBPyConnection) -> list[dict[str, Any]]:
    if not table_exists(conn, "banners_portal"):
        return []
    rows = conn.execute(
        """
        SELECT id_banner, titulo, imagen_path, enlace, activo, orden
        FROM banners_portal ORDER BY orden, id_banner
        """
    ).fetchall()
    return [
        {
            "id_banner": int(r[0]),
            "titulo": r[1],
            "imagen_path": r[2],
            "imagen_url": f"/media/{r[2]}" if r[2] and not str(r[2]).startswith("/") else r[2],
            "enlace": r[3],
            "activo": bool(r[4]),
            "orden": int(r[5] or 0),
        }
        for r in rows
    ]


def crear_banner(
    conn: duckdb.DuckDBPyConnection,
    *,
    titulo: str,
    imagen_path: Optional[str] = None,
    enlace: Optional[str] = None,
    orden: int = 0,
    activo: bool = True,
) -> dict[str, Any]:
    id_banner = int(conn.execute("SELECT COALESCE(MAX(id_banner), 0) + 1 FROM banners_portal").fetchone()[0])
    conn.execute(
        """
        INSERT INTO banners_portal (id_banner, titulo, imagen_path, enlace, activo, orden)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        [id_banner, titulo, imagen_path, enlace, activo, orden],
    )
    return {"id_banner": id_banner, "titulo": titulo, "activo": activo}


def actualizar_banner(
    conn: duckdb.DuckDBPyConnection,
    id_banner: int,
    *,
    titulo: str,
    imagen_path: Optional[str],
    enlace: Optional[str],
    orden: int,
    activo: bool,
) -> None:
    conn.execute(
        """
        UPDATE banners_portal
        SET titulo = ?, imagen_path = ?, enlace = ?, orden = ?, activo = ?
        WHERE id_banner = ?
        """,
        [titulo, imagen_path, enlace, orden, activo, id_banner],
    )


def eliminar_banner(conn: duckdb.DuckDBPyConnection, id_banner: int) -> None:
    conn.execute("DELETE FROM banners_portal WHERE id_banner = ?", [id_banner])


def listar_promociones(conn: duckdb.DuckDBPyConnection) -> list[dict[str, Any]]:
    if not table_exists(conn, "promociones"):
        return []
    rows = conn.execute(
        """
        SELECT id_promocion, nombre, CAST(descuento_pct AS DOUBLE),
               fecha_inicio, fecha_fin, activa
        FROM promociones ORDER BY id_promocion
        """
    ).fetchall()
    return [
        {
            "id_promocion": int(r[0]),
            "nombre": r[1],
            "descuento_pct": float(r[2]),
            "fecha_inicio": str(r[3])[:10] if r[3] else None,
            "fecha_fin": str(r[4])[:10] if r[4] else None,
            "activa": bool(r[5]),
        }
        for r in rows
    ]


def _validar_rango_promocion(conn: duckdb.DuckDBPyConnection, *, nombre: str, fecha_inicio: str, fecha_fin: str, activa: bool, id_excluida: int | None = None) -> None:
    if not fecha_inicio or not fecha_fin:
        raise ValueError("La promoción requiere fecha de inicio y fecha de fin.")
    if fecha_fin < fecha_inicio:
        raise ValueError("La fecha de fin no puede ser anterior a la fecha de inicio.")
    if not activa:
        return
    duplicada = conn.execute(
        """
        SELECT id_promocion FROM promociones
        WHERE LOWER(nombre) = LOWER(?) AND COALESCE(id_promocion, 0) <> COALESCE(?, 0)
        """,
        [nombre, id_excluida or 0],
    ).fetchone()
    if duplicada:
        raise ValueError("Ya existe una promoción con ese nombre.")
    solapada = conn.execute(
        """
        SELECT id_promocion FROM promociones
        WHERE activa = true
          AND COALESCE(id_promocion, 0) <> COALESCE(?, 0)
          AND fecha_inicio <= ? AND fecha_fin >= ?
        """,
        [id_excluida or 0, fecha_fin, fecha_inicio],
    ).fetchone()
    if solapada:
        raise ValueError("La promoción se solapa con una promoción activa existente.")


def crear_promocion(
    conn: duckdb.DuckDBPyConnection,
    *,
    nombre: str,
    descuento_pct: float,
    fecha_inicio: str,
    fecha_fin: str,
    activa: bool = True,
) -> dict[str, Any]:
    _validar_rango_promocion(
        conn, nombre=nombre, fecha_inicio=fecha_inicio, fecha_fin=fecha_fin, activa=activa
    )
    id_promocion = int(conn.execute("SELECT COALESCE(MAX(id_promocion), 0) + 1 FROM promociones").fetchone()[0])
    conn.execute(
        """
        INSERT INTO promociones (id_promocion, nombre, descuento_pct, fecha_inicio, fecha_fin, activa)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        [id_promocion, nombre, descuento_pct, fecha_inicio, fecha_fin, activa],
    )
    if activa:
        try:
            from shared.services import notificacion_service as ns
            rows = conn.execute(
                """
                SELECT u.id_usuario
                FROM usuarios u
                JOIN dim_cliente c ON c.id_usuario = u.id_usuario
                LEFT JOIN cliente_preferencias cp ON cp.id_cliente = c.id_cliente
                WHERE u.activo = true AND u.rol = 'cliente'
                """
            ).fetchall()
            for (uid,) in rows:
                prefs_row = conn.execute(
                    """
                    SELECT preferencias_json FROM cliente_preferencias cp
                    JOIN dim_cliente c ON c.id_cliente = cp.id_cliente
                    WHERE c.id_usuario = ?
                    """,
                    [int(uid)],
                ).fetchone()
                allow = True
                if prefs_row and prefs_row[0]:
                    try:
                        import json
                        data = json.loads(prefs_row[0]) if isinstance(prefs_row[0], str) else dict(prefs_row[0])
                        allow = bool(data.get("notif_promociones", True))
                    except Exception:
                        allow = True
                if allow:
                    ns.crear(
                        conn,
                        id_usuario=int(uid),
                        titulo=f"Nueva promoción: {nombre}",
                        cuerpo=f"Descuento {descuento_pct:g}% vigente hasta {fecha_fin}.",
                        tipo="promo",
                        link="/pages/catalogo.html",
                    )
        except Exception:
            pass
    return {"id_promocion": id_promocion, "nombre": nombre, "activa": activa}


def actualizar_promocion(
    conn: duckdb.DuckDBPyConnection,
    id_promocion: int,
    *,
    nombre: str,
    descuento_pct: float,
    fecha_inicio: str,
    fecha_fin: str,
    activa: bool,
) -> None:
    if not conn.execute("SELECT 1 FROM promociones WHERE id_promocion = ?", [id_promocion]).fetchone():
        raise ValueError(f"Promoción {id_promocion} no existe.")
    _validar_rango_promocion(
        conn, nombre=nombre, fecha_inicio=fecha_inicio, fecha_fin=fecha_fin, activa=activa, id_excluida=id_promocion
    )
    conn.execute(
        """
        UPDATE promociones
        SET nombre = ?, descuento_pct = ?, fecha_inicio = ?, fecha_fin = ?, activa = ?
        WHERE id_promocion = ?
        """,
        [nombre, descuento_pct, fecha_inicio, fecha_fin, activa, id_promocion],
    )


def eliminar_promocion(conn: duckdb.DuckDBPyConnection, id_promocion: int) -> None:
    conn.execute("DELETE FROM promociones WHERE id_promocion = ?", [id_promocion])


def obtener_carrusel(conn: duckdb.DuckDBPyConnection) -> dict[str, Any]:
    from shared.services.config_service import obtener_config

    raw = (obtener_config(conn, "PORTAL_CARRUSEL_IDS", "") or "").strip()
    ids: list[int] = []
    for part in raw.replace(";", ",").split(","):
        part = part.strip()
        if part.isdigit():
            ids.append(int(part))
    productos = []
    if table_exists(conn, "dim_producto"):
        rows = conn.execute(
            """
            SELECT id_producto, nombre_producto, COALESCE(activo, true)
            FROM dim_producto ORDER BY nombre_producto LIMIT 200
            """
        ).fetchall()
        productos = [
            {"id_producto": int(r[0]), "nombre_producto": r[1], "activo": bool(r[2]), "en_carrusel": int(r[0]) in ids}
            for r in rows
        ]
    return {"ids": ids, "productos": productos}


def guardar_carrusel(conn: duckdb.DuckDBPyConnection, ids: list[int]) -> dict[str, Any]:
    from shared.services.config_service import actualizar_config

    clean = [int(i) for i in ids if int(i) > 0][:12]
    actualizar_config(conn, "PORTAL_CARRUSEL_IDS", ",".join(str(i) for i in clean))
    return {"ids": clean, "ok": True}
