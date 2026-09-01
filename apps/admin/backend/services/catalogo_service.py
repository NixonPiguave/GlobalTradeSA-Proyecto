"""
services/catalogo_service.py — CRUD de catálogos/paquetes configurables (panel admin).
"""

from __future__ import annotations

from typing import Any, Optional

import duckdb


def listar_catalogos(
    conn: duckdb.DuckDBPyConnection, *, incluir_inactivas: bool = False
) -> list[dict[str, Any]]:
    where = "" if incluir_inactivas else "WHERE COALESCE(c.activo, true) = true"
    rows = conn.execute(
        f"""
        SELECT c.id_catalogo, c.nombre, c.descripcion, c.id_item_type,
               it.item_type, COALESCE(c.activo, true) AS activo,
               (SELECT COUNT(*) FROM catalogo_detalle d JOIN dim_producto p ON p.id_producto = d.id_producto
                 WHERE d.id_catalogo = c.id_catalogo AND COALESCE(p.activo, true) = true) AS n_productos,
               ROUND(CAST(COALESCE(SUM(d.cantidad_base * COALESCE(d.precio_unitario, p.precio_mayorista, 0)), 0) AS DOUBLE), 2) AS precio_total,
               CAST(COALESCE(c.descuento_pct, 0) AS DOUBLE) AS descuento_pct,
               c.descuento_hasta, c.descuento_motivo
        FROM catalogos c
        LEFT JOIN dim_item_type it ON it.id_item_type = c.id_item_type
        LEFT JOIN catalogo_detalle d ON d.id_catalogo = c.id_catalogo
        LEFT JOIN dim_producto p ON p.id_producto = d.id_producto
        {where}
        GROUP BY c.id_catalogo, c.nombre, c.descripcion, c.id_item_type, it.item_type, c.activo,
                 c.descuento_pct, c.descuento_hasta, c.descuento_motivo
        ORDER BY c.nombre
        """,
    ).fetchall()
    return [
        {
            "id_catalogo": int(r[0]),
            "nombre": r[1],
            "descripcion": r[2],
            "id_item_type": int(r[3]) if r[3] is not None else None,
            "categoria": r[4],
            "activo": bool(r[5]),
            "n_productos": int(r[6]),
            "precio_total": float(r[7]),
            "descuento_pct": float(r[8] or 0),
            "descuento_hasta": str(r[9]) if r[9] else None,
            "descuento_motivo": r[10],
            "precio_total_final": round(float(r[7]) * (1 - float(r[8] or 0) / 100.0), 2),
        }
        for r in rows
    ]


def obtener_catalogo(conn: duckdb.DuckDBPyConnection, id_catalogo: int) -> Optional[dict[str, Any]]:
    cat = conn.execute(
        """
        SELECT c.id_catalogo, c.nombre, c.descripcion, c.id_item_type, it.item_type, COALESCE(c.activo, true),
               CAST(COALESCE(c.descuento_pct, 0) AS DOUBLE), c.descuento_hasta, c.descuento_motivo
        FROM catalogos c
        LEFT JOIN dim_item_type it ON it.id_item_type = c.id_item_type
        WHERE c.id_catalogo = ?
        """,
        [id_catalogo],
    ).fetchone()
    if not cat:
        return None
    productos = conn.execute(
        """
SELECT d.id_producto, p.nombre_producto, d.cantidad_base,
               d.precio_unitario, COALESCE(p.precio_mayorista, 0) AS precio_mayorista,
               p.imagen_url,
               COALESCE(p.activo, true) AS activo
        FROM catalogo_detalle d
        JOIN dim_producto p ON p.id_producto = d.id_producto
        WHERE d.id_catalogo = ?
        ORDER BY p.nombre_producto
        """,
        [id_catalogo],
    ).fetchall()
    return {
        "id_catalogo": int(cat[0]),
        "nombre": cat[1],
        "descripcion": cat[2],
        "id_item_type": int(cat[3]) if cat[3] is not None else None,
        "categoria": cat[4],
        "activo": bool(cat[5]),
        "descuento_pct": float(cat[6] or 0),
        "descuento_hasta": str(cat[7]) if cat[7] else None,
        "descuento_motivo": cat[8],
        "productos": [
            {
                "id_producto": int(p[0]),
                "nombre_producto": p[1],
                "cantidad_base": int(p[2]),
                "precio_unitario": float(p[3]) if p[3] is not None else None,
                "precio_mayorista": float(p[4]),
                "imagen_url": p[5],
                "activo": bool(p[6]),
            }
            for p in productos
        ],
    }


def crear_catalogo(
    conn: duckdb.DuckDBPyConnection,
    *,
    nombre: str,
    descripcion: Optional[str],
    id_item_type: Optional[int],
    activo: bool = True,
) -> dict[str, Any]:
    if id_item_type is not None:
        existe = conn.execute("SELECT 1 FROM dim_item_type WHERE id_item_type = ?", [id_item_type]).fetchone()
        if not existe:
            raise ValueError("El tipo de producto no existe.")
    conn.execute(
        """
        INSERT INTO catalogos (id_catalogo, nombre, descripcion, id_item_type, activo)
        SELECT COALESCE((SELECT MAX(id_catalogo) FROM catalogos), 0) + 1, ?, ?, ?, ?
        WHERE NOT EXISTS (SELECT 1 FROM catalogos WHERE nombre = ?)
        """,
        [nombre, descripcion, id_item_type, activo, nombre],
    )
    existe = conn.execute(
        "SELECT id_catalogo FROM catalogos WHERE nombre = ? ORDER BY id_catalogo DESC LIMIT 1", [nombre]
    ).fetchone()
    if not existe:
        raise ValueError("No se pudo crear el catálogo.")
    return obtener_catalogo(conn, int(existe[0]))


def actualizar_catalogo(
    conn: duckdb.DuckDBPyConnection,
    id_catalogo: int,
    *,
    nombre: Optional[str] = None,
    descripcion: Optional[str] = None,
    id_item_type: Optional[int] = None,
    activo: Optional[bool] = None,
    descuento_pct: Optional[float] = None,
    descuento_hasta: Optional[str] = None,
    descuento_motivo: Optional[str] = None,
    avisar_clientes: bool = True,
) -> Optional[dict[str, Any]]:
    actual = obtener_catalogo(conn, id_catalogo)
    if not actual:
        return None
    sets: list[str] = []
    params: list[Any] = []
    if nombre is not None:
        sets.append("nombre = ?")
        params.append(nombre)
    if descripcion is not None:
        sets.append("descripcion = ?")
        params.append(descripcion)
    if id_item_type is not None:
        if not conn.execute("SELECT 1 FROM dim_item_type WHERE id_item_type = ?", [id_item_type]).fetchone():
            raise ValueError("El tipo de producto no existe.")
        sets.append("id_item_type = ?")
        params.append(id_item_type)
    if activo is not None:
        sets.append("activo = ?")
        params.append(activo)

    dto_anterior = float(actual.get("descuento_pct") or 0)
    dto_nuevo = dto_anterior
    if descuento_pct is not None:
        dto_nuevo = max(0.0, min(90.0, float(descuento_pct)))
        sets.append("descuento_pct = ?")
        params.append(dto_nuevo)
    if descuento_hasta is not None:
        sets.append("descuento_hasta = ?")
        params.append(descuento_hasta or None)
    if descuento_motivo is not None:
        sets.append("descuento_motivo = ?")
        params.append(descuento_motivo or None)

    if not sets:
        return actual
    params.append(id_catalogo)
    conn.execute(f"UPDATE catalogos SET {', '.join(sets)} WHERE id_catalogo = ?", params)

    resultado = obtener_catalogo(conn, id_catalogo)
    if dto_nuevo > 0 and dto_nuevo != dto_anterior and avisar_clientes:
        _publicar_descuento_paquete(conn, resultado)
    return resultado


def _publicar_descuento_paquete(
    conn: duckdb.DuckDBPyConnection, catalogo: Optional[dict[str, Any]]
) -> None:
    """Avisa a los clientes cuando un paquete estrena descuento."""
    if not catalogo:
        return
    try:
        from shared.services import notificacion_service as ns

        id_catalogo = int(catalogo["id_catalogo"])
        ns.notificar_descuento(
            conn,
            ambito="paquete",
            nombre=catalogo["nombre"],
            descuento_pct=float(catalogo.get("descuento_pct") or 0),
            link=f"/pages/catalogo_paquete.html?id={id_catalogo}",
            hasta=catalogo.get("descuento_hasta"),
            motivo=catalogo.get("descuento_motivo"),
            usuarios_prioritarios=ns.usuarios_con_paquete_en_favoritos(conn, id_catalogo),
        )
        conn.execute(
            "UPDATE catalogos SET descuento_publicado = current_timestamp WHERE id_catalogo = ?",
            [id_catalogo],
        )
    except Exception:
        pass


def eliminar_catalogo(conn: duckdb.DuckDBPyConnection, id_catalogo: int) -> tuple[bool, str]:
    """Elimina o desactiva. Si tiene productos o historial de uso, solo desactiva."""
    if not conn.execute("SELECT 1 FROM catalogos WHERE id_catalogo = ?", [id_catalogo]).fetchone():
        return False, ""
    tiene_detalle = conn.execute(
        "SELECT 1 FROM catalogo_detalle WHERE id_catalogo = ? LIMIT 1", [id_catalogo]
    ).fetchone()
    # Si el nombre figura en notas de pedidos o hay detalle, preferimos soft-delete
    if tiene_detalle:
        conn.execute("UPDATE catalogos SET activo = false WHERE id_catalogo = ?", [id_catalogo])
        return True, "desactivado"
    conn.execute("DELETE FROM catalogo_detalle WHERE id_catalogo = ?", [id_catalogo])
    conn.execute("DELETE FROM catalogos WHERE id_catalogo = ?", [id_catalogo])
    return True, "eliminado"


def activar_desactivar_catalogo(conn: duckdb.DuckDBPyConnection, id_catalogo: int, activo: bool) -> bool:
    if not conn.execute("SELECT 1 FROM catalogos WHERE id_catalogo = ?", [id_catalogo]).fetchone():
        return False
    conn.execute("UPDATE catalogos SET activo = ? WHERE id_catalogo = ?", [activo, id_catalogo])
    return True


def agregar_producto(
    conn: duckdb.DuckDBPyConnection,
    id_catalogo: int,
    *,
    id_producto: int,
    cantidad_base: int,
    precio_unitario: Optional[float],
) -> dict[str, Any]:
    if not conn.execute("SELECT 1 FROM catalogos WHERE id_catalogo = ?", [id_catalogo]).fetchone():
        raise ValueError("Catálogo no encontrado.")
    prod = conn.execute(
        "SELECT CAST(precio_mayorista AS DOUBLE), activo FROM dim_producto WHERE id_producto = ?", [id_producto]
    ).fetchone()
    if not prod or not bool(prod[1]):
        raise ValueError("Producto no encontrado o inactivo.")
    precio = precio_unitario if precio_unitario is not None else float(prod[0])
    conn.execute(
        """
        INSERT INTO catalogo_detalle (id_catalogo, id_producto, cantidad_base, precio_unitario)
        SELECT ?, ?, ?, ?
        WHERE NOT EXISTS (SELECT 1 FROM catalogo_detalle WHERE id_catalogo = ? AND id_producto = ?)
        """,
        [id_catalogo, id_producto, cantidad_base, precio, id_catalogo, id_producto],
    )
    return obtener_catalogo(conn, id_catalogo)


def actualizar_producto(
    conn: duckdb.DuckDBPyConnection,
    id_catalogo: int,
    id_producto: int,
    *,
    cantidad_base: Optional[int],
    precio_unitario: Optional[float],
) -> Optional[dict[str, Any]]:
    if not conn.execute(
        "SELECT 1 FROM catalogo_detalle WHERE id_catalogo = ? AND id_producto = ?", [id_catalogo, id_producto]
    ).fetchone():
        return None
    sets: list[str] = []
    params: list[Any] = []
    if cantidad_base is not None:
        sets.append("cantidad_base = ?")
        params.append(cantidad_base)
    if precio_unitario is not None:
        sets.append("precio_unitario = ?")
        params.append(precio_unitario)
    if sets:
        params.extend([id_catalogo, id_producto])
        conn.execute(f"UPDATE catalogo_detalle SET {', '.join(sets)} WHERE id_catalogo = ? AND id_producto = ?", params)
    return obtener_catalogo(conn, id_catalogo)


def quitar_producto(conn: duckdb.DuckDBPyConnection, id_catalogo: int, id_producto: int) -> bool:
    if not conn.execute(
        "SELECT 1 FROM catalogo_detalle WHERE id_catalogo = ? AND id_producto = ?", [id_catalogo, id_producto]
    ).fetchone():
        return False
    conn.execute(
        "DELETE FROM catalogo_detalle WHERE id_catalogo = ? AND id_producto = ?", [id_catalogo, id_producto]
    )
    return True