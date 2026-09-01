"""
services/categoria_service.py — CRUD de categorías del catálogo (soft-delete).

Las categorías se mapean 1:1 con `dim_item_type` para mantener compatibilidad
con el histórico analítico. Crear una categoría nueva crea también su
`dim_item_type` (precios históricos en 0).
"""

from __future__ import annotations

from typing import Any, Optional

import duckdb

from shared.database.ids import siguiente_id


def _slug(nombre: str) -> str:
    import re

    s = nombre.lower().replace("—", "-").replace("&", "and")
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s[:60] or "categoria"


def asegurar_dim_item_type(conn: duckdb.DuckDBPyConnection, id_item_type: int) -> bool:
    """Crea dim_item_type faltante a partir de categorias. True si existe al final."""
    if conn.execute("SELECT 1 FROM dim_item_type WHERE id_item_type = ?", [id_item_type]).fetchone():
        return True
    row = conn.execute(
        "SELECT nombre FROM categorias WHERE id_item_type = ?",
        [id_item_type],
    ).fetchone()
    if not row:
        return False
    conn.execute(
        """
        INSERT INTO dim_item_type (id_item_type, item_type, unit_price, unit_cost)
        VALUES (?, ?, 0, 0)
        """,
        [id_item_type, row[0]],
    )
    return True


def reparar_categorias_huerfanas(conn: duckdb.DuckDBPyConnection) -> int:
    """Sincroniza categorias → dim_item_type cuando falta el maestro analítico."""
    rows = conn.execute(
        """
        SELECT c.id_item_type, c.nombre
        FROM categorias c
        LEFT JOIN dim_item_type d ON d.id_item_type = c.id_item_type
        WHERE c.id_item_type IS NOT NULL AND d.id_item_type IS NULL
        ORDER BY c.id_item_type
        """
    ).fetchall()
    for id_item_type, nombre in rows:
        conn.execute(
            """
            INSERT INTO dim_item_type (id_item_type, item_type, unit_price, unit_cost)
            VALUES (?, ?, 0, 0)
            """,
            [int(id_item_type), nombre],
        )
    return len(rows)


def listar_categorias(conn: duckdb.DuckDBPyConnection, *, incluir_inactivas: bool = False) -> list[dict[str, Any]]:
    where = "" if incluir_inactivas else "WHERE c.activo = true"
    rows = conn.execute(
        f"""
        SELECT c.id_categoria, c.nombre, c.slug, c.descripcion, c.imagen_path,
               c.activo, c.id_item_type,
               (SELECT COUNT(*) FROM dim_producto p WHERE p.id_item_type = c.id_item_type) AS n_productos,
               (SELECT COUNT(*) FROM dim_producto p WHERE p.id_item_type = c.id_item_type AND p.activo = true) AS n_activos,
               CAST(COALESCE(c.descuento_pct, 0) AS DOUBLE) AS descuento_pct,
               COALESCE(c.descuento_aplica_a, 'mayorista') AS descuento_aplica_a,
               c.descuento_hasta, c.descuento_motivo
        FROM categorias c
        {where}
        ORDER BY c.nombre
        """
    ).fetchall()
    return [
        {
            "id_categoria": int(r[0]),
            "nombre": r[1],
            "slug": r[2],
            "descripcion": r[3],
            "imagen_path": r[4],
            "activo": bool(r[5]),
            "id_item_type": int(r[6]) if r[6] is not None else None,
            "n_productos": int(r[7]),
            "n_activos": int(r[8]),
            "descuento_pct": float(r[9] or 0),
            "descuento_aplica_a": r[10] or "mayorista",
            "descuento_hasta": str(r[11]) if r[11] else None,
            "descuento_motivo": r[12],
        }
        for r in rows
    ]


def obtener_categoria(conn: duckdb.DuckDBPyConnection, id_categoria: int) -> Optional[dict[str, Any]]:
    r = conn.execute(
        """
        SELECT id_categoria, nombre, slug, descripcion, imagen_path, activo, id_item_type,
               CAST(COALESCE(descuento_pct, 0) AS DOUBLE), COALESCE(descuento_aplica_a, 'mayorista'),
               descuento_hasta, descuento_motivo
        FROM categorias WHERE id_categoria = ?
        """,
        [id_categoria],
    ).fetchone()
    if not r:
        return None
    return {
        "id_categoria": int(r[0]),
        "nombre": r[1],
        "slug": r[2],
        "descripcion": r[3],
        "imagen_path": r[4],
        "activo": bool(r[5]),
        "id_item_type": int(r[6]) if r[6] is not None else None,
        "descuento_pct": float(r[7] or 0),
        "descuento_aplica_a": r[8] or "mayorista",
        "descuento_hasta": str(r[9]) if r[9] else None,
        "descuento_motivo": r[10],
    }


def crear_categoria(
    conn: duckdb.DuckDBPyConnection,
    *,
    nombre: str,
    descripcion: Optional[str],
    imagen_path: Optional[str],
) -> dict[str, Any]:
    existente = conn.execute(
        "SELECT id_categoria FROM categorias WHERE lower(nombre) = lower(?)", [nombre]
    ).fetchone()
    if existente:
        raise ValueError(f"Ya existe una categoría con el nombre '{nombre}'.")

    conn.execute("BEGIN TRANSACTION")
    try:
        it = conn.execute(
            "SELECT id_item_type FROM dim_item_type WHERE lower(item_type) = lower(?)", [nombre]
        ).fetchone()
        if it:
            id_item_type = int(it[0])
        else:
            id_item_type = int(
                conn.execute("SELECT COALESCE(MAX(id_item_type), 0) + 1 FROM dim_item_type").fetchone()[0]
            )
            conn.execute(
                "INSERT INTO dim_item_type (id_item_type, item_type, unit_price, unit_cost) VALUES (?, ?, 0, 0)",
                [id_item_type, nombre],
            )

        id_categoria = siguiente_id(conn, "categorias")
        conn.execute(
            """
            INSERT INTO categorias (id_categoria, nombre, slug, descripcion, imagen_path, activo, id_item_type)
            VALUES (?, ?, ?, ?, ?, true, ?)
            """,
            [id_categoria, nombre, _slug(nombre), descripcion, imagen_path, id_item_type],
        )
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise

    if not asegurar_dim_item_type(conn, id_item_type):
        raise ValueError(f"No se pudo vincular la categoría con dim_item_type={id_item_type}.")

    return obtener_categoria(conn, id_categoria)


def actualizar_categoria(
    conn: duckdb.DuckDBPyConnection,
    id_categoria: int,
    cambios: dict[str, Any],
) -> Optional[dict[str, Any]]:
    actual = obtener_categoria(conn, id_categoria)
    if not actual:
        return None

    sets: list[str] = []
    params: list[Any] = []

    nuevo_nombre = cambios.get("nombre")
    if nuevo_nombre is not None and nuevo_nombre != actual["nombre"]:
        sets.append("nombre = ?")
        params.append(nuevo_nombre)
        sets.append("slug = ?")
        params.append(_slug(nuevo_nombre))

    if "descripcion" in cambios and cambios["descripcion"] != actual.get("descripcion"):
        sets.append("descripcion = ?")
        params.append(cambios["descripcion"])

    if "imagen_path" in cambios and cambios["imagen_path"] != actual.get("imagen_path"):
        sets.append("imagen_path = ?")
        params.append(cambios["imagen_path"])

    if "activo" in cambios:
        sets.append("activo = ?")
        params.append(bool(cambios["activo"]))

    dto_anterior = float(actual.get("descuento_pct") or 0)
    dto_nuevo = dto_anterior
    if "descuento_pct" in cambios and cambios["descuento_pct"] is not None:
        dto_nuevo = max(0.0, min(90.0, float(cambios["descuento_pct"])))
        sets.append("descuento_pct = ?")
        params.append(dto_nuevo)
    if "descuento_aplica_a" in cambios:
        aplica = str(cambios["descuento_aplica_a"] or "mayorista").strip().lower()
        if aplica not in ("mayorista", "retail", "ambos"):
            aplica = "mayorista"
        sets.append("descuento_aplica_a = ?")
        params.append(aplica)
    if "descuento_hasta" in cambios:
        sets.append("descuento_hasta = ?")
        params.append(cambios["descuento_hasta"] or None)
    if "descuento_motivo" in cambios:
        sets.append("descuento_motivo = ?")
        params.append(cambios["descuento_motivo"] or None)

    if not sets:
        return obtener_categoria(conn, id_categoria)

    conn.execute(
        f"UPDATE categorias SET {', '.join(sets)} WHERE id_categoria = ?",
        [*params, id_categoria],
    )
    if nuevo_nombre is not None and nuevo_nombre != actual["nombre"] and actual.get("id_item_type"):
        conn.execute(
            "UPDATE dim_item_type SET item_type = ? WHERE id_item_type = ?",
            [nuevo_nombre, actual["id_item_type"]],
        )

    resultado = obtener_categoria(conn, id_categoria)
    if dto_nuevo > 0 and dto_nuevo != dto_anterior:
        _publicar_descuento_categoria(conn, resultado, cambios.get("avisar_clientes", True))
    return resultado


def _publicar_descuento_categoria(
    conn: duckdb.DuckDBPyConnection, categoria: Optional[dict[str, Any]], avisar: bool
) -> None:
    """Avisa a los clientes del portal cuando la categoría estrena descuento."""
    if not categoria or not avisar:
        return
    try:
        from shared.services import notificacion_service as ns

        id_item_type = categoria.get("id_item_type")
        prioritarios: list[int] = []
        if id_item_type is not None:
            prioritarios = [
                int(r[0])
                for r in conn.execute(
                    """
                    SELECT DISTINCT w.id_usuario
                    FROM wishlist w
                    JOIN dim_producto p ON p.id_producto = w.id_producto
                    WHERE p.id_item_type = ?
                    """,
                    [int(id_item_type)],
                ).fetchall()
            ]
        link = "/pages/catalogo.html"
        if id_item_type is not None:
            link = f"/pages/catalogo.html?id_item_type={int(id_item_type)}"
        ns.notificar_descuento(
            conn,
            ambito="categoría",
            nombre=categoria["nombre"],
            descuento_pct=float(categoria.get("descuento_pct") or 0),
            link=link,
            hasta=categoria.get("descuento_hasta"),
            motivo=categoria.get("descuento_motivo"),
            usuarios_prioritarios=prioritarios,
        )
        conn.execute(
            "UPDATE categorias SET descuento_publicado = current_timestamp WHERE id_categoria = ?",
            [int(categoria["id_categoria"])],
        )
    except Exception:
        # La publicación del aviso nunca debe tumbar la edición de la categoría.
        pass


def set_categoria_activa(conn: duckdb.DuckDBPyConnection, id_categoria: int, activo: bool) -> bool:
    if not obtener_categoria(conn, id_categoria):
        return False
    conn.execute(
        "UPDATE categorias SET activo = ? WHERE id_categoria = ?",
        [bool(activo), id_categoria],
    )
    return True


def desactivar_categoria(conn: duckdb.DuckDBPyConnection, id_categoria: int) -> bool:
    return set_categoria_activa(conn, id_categoria, False)


def eliminar_categoria(conn: duckdb.DuckDBPyConnection, id_categoria: int) -> tuple[bool, str]:
    """Elimina de verdad si no hay productos; si hay, solo desactiva.

    Devuelve (ok, modo) con modo en {"eliminada", "desactivada"}.
    """
    actual = obtener_categoria(conn, id_categoria)
    if not actual:
        return False, ""
    id_item = actual.get("id_item_type")
    n_prod = 0
    if id_item is not None:
        n_prod = int(
            conn.execute(
                "SELECT COUNT(*) FROM dim_producto WHERE id_item_type = ?",
                [id_item],
            ).fetchone()[0]
            or 0
        )
    if n_prod > 0:
        conn.execute(
            "UPDATE categorias SET activo = false WHERE id_categoria = ?",
            [id_categoria],
        )
        return True, "desactivada"

    conn.execute("DELETE FROM categorias WHERE id_categoria = ?", [id_categoria])
    # Limpia el tipo maestro solo si no tiene histórico analítico ni otros vínculos
    if id_item is not None:
        usado = False
        for q in (
            "SELECT 1 FROM fact_ventas WHERE id_item_type = ? LIMIT 1",
            "SELECT 1 FROM dim_producto WHERE id_item_type = ? LIMIT 1",
            "SELECT 1 FROM categorias WHERE id_item_type = ? LIMIT 1",
        ):
            try:
                if conn.execute(q, [id_item]).fetchone():
                    usado = True
                    break
            except Exception:
                pass
        if not usado:
            try:
                conn.execute("DELETE FROM dim_item_type WHERE id_item_type = ?", [id_item])
            except Exception:
                pass
    return True, "eliminada"
