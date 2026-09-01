"""
services/producto_service.py — CRUD de productos del catálogo B2B.

Los productos viven en `dim_producto` (leída por el portal). El stock se
mantiene en `stock_almacen` (almacén central id=1).
"""

from __future__ import annotations

from typing import Any, Optional

import duckdb

from backend.services.categoria_service import asegurar_dim_item_type
from shared.database.ids import siguiente_id

ALMACEN_CENTRAL = 1


def _row_to_producto(r: tuple) -> dict[str, Any]:
    return {
        "id_producto": int(r[0]),
        "nombre_producto": r[1],
        "descripcion": r[2],
        "id_item_type": int(r[3]),
        "categoria": r[4],
        "precio_unitario": float(r[5]) if r[5] is not None else None,
        "precio_mayorista": float(r[6]) if r[6] is not None else None,
        "imagen_url": r[7],
        "activo": bool(r[8]),
        "stock": float(r[9]) if r[9] is not None else 0.0,
        "id_marca": int(r[10]) if r[10] is not None else None,
        "id_linea": int(r[11]) if r[11] is not None else None,
        "marca": r[12],
        "linea": r[13],
        "sku": r[14],
        "descuento_pct": float(r[15] or 0),
        "precio_rebajado": float(r[16]) if r[16] is not None else None,
        "descuento_aplica_a": (r[17] if len(r) > 17 and r[17] else "mayorista") or "mayorista",
        "stock_minimo": float(r[18]) if len(r) > 18 and r[18] is not None else 10.0,
        "fecha_rebaja_hasta": str(r[19])[:10] if len(r) > 19 and r[19] else None,
        "descuento_motivo": r[20] if len(r) > 20 else None,
    }


_SELECT = """
SELECT p.id_producto, p.nombre_producto, p.descripcion, p.id_item_type,
       it.item_type AS categoria,
       CAST(p.precio_unitario AS DOUBLE), CAST(p.precio_mayorista AS DOUBLE),
       p.imagen_url, p.activo,
       CAST(COALESCE(sa.cantidad_disponible, 0) AS DOUBLE) AS stock,
       p.id_marca, p.id_linea, m.nombre AS marca, l.nombre AS linea,
       COALESCE(p.sku, 'GM-' || LPAD(CAST(p.id_producto AS VARCHAR), 6, '0')) AS sku,
       CAST(COALESCE(p.descuento_pct, 0) AS DOUBLE),
       CAST(p.precio_rebajado AS DOUBLE),
       COALESCE(p.descuento_aplica_a, 'mayorista'),
       CAST(COALESCE(p.stock_minimo, COALESCE(al.umbral_minimo, 10)) AS DOUBLE) AS stock_minimo,
       p.fecha_rebaja_hasta, p.descuento_motivo
FROM dim_producto p
JOIN dim_item_type it ON it.id_item_type = p.id_item_type
LEFT JOIN marcas m ON m.id_marca = p.id_marca
LEFT JOIN lineas_producto l ON l.id_linea = p.id_linea
LEFT JOIN stock_almacen sa ON sa.id_producto = p.id_producto AND sa.id_almacen = %d
LEFT JOIN alertas_stock al ON al.id_producto = p.id_producto AND al.id_almacen = %d AND al.activa = true
""" % (ALMACEN_CENTRAL, ALMACEN_CENTRAL)


def listar_productos(
    conn: duckdb.DuckDBPyConnection,
    *,
    id_item_type: Optional[int] = None,
    q: Optional[str] = None,
    incluir_inactivos: bool = False,
    precio_min: Optional[float] = None,
    precio_max: Optional[float] = None,
    activo: Optional[bool] = None,
    page: int = 1,
    page_size: int = 20,
) -> dict[str, Any]:
    page = max(1, page)
    page_size = max(1, min(page_size, 100))

    where: list[str] = []
    params: list[Any] = []
    if activo is not None:
        where.append("p.activo = ?")
        params.append(activo)
    elif not incluir_inactivos:
        where.append("p.activo = true")
    if id_item_type is not None:
        where.append("p.id_item_type = ?")
        params.append(id_item_type)
    if q:
        where.append("lower(p.nombre_producto) LIKE ?")
        params.append(f"%{q.lower()}%")
    precio_expr = "COALESCE(p.precio_rebajado, p.precio_mayorista, p.precio_unitario)"
    if precio_min is not None:
        where.append(f"{precio_expr} >= ?")
        params.append(float(precio_min))
    if precio_max is not None:
        where.append(f"{precio_expr} <= ?")
        params.append(float(precio_max))
    where_sql = ("WHERE " + " AND ".join(where)) if where else ""

    total = int(
        conn.execute(f"SELECT COUNT(*) FROM dim_producto p {where_sql}", params).fetchone()[0]
    )
    rows = conn.execute(
        f"{_SELECT} {where_sql} ORDER BY p.nombre_producto LIMIT ? OFFSET ?",
        [*params, page_size, (page - 1) * page_size],
    ).fetchall()
    return {
        "items": [_row_to_producto(r) for r in rows],
        "page": page,
        "page_size": page_size,
        "total_items": total,
        "total_pages": max(1, -(-total // page_size)),
    }


def obtener_producto(conn: duckdb.DuckDBPyConnection, id_producto: int) -> Optional[dict[str, Any]]:
    r = conn.execute(f"{_SELECT} WHERE p.id_producto = ?", [id_producto]).fetchone()
    return _row_to_producto(r) if r else None


def _asegurar_stock_row(conn: duckdb.DuckDBPyConnection, id_producto: int) -> None:
    existe = conn.execute(
        "SELECT 1 FROM stock_almacen WHERE id_producto = ? AND id_almacen = ?",
        [id_producto, ALMACEN_CENTRAL],
    ).fetchone()
    if not existe:
        conn.execute(
            """
            INSERT INTO stock_almacen (id_stock, id_producto, id_almacen, cantidad_disponible, cantidad_reservada)
            VALUES ((SELECT COALESCE(MAX(id_stock), 0) + 1 FROM stock_almacen), ?, ?, 0, 0)
            """,
            [id_producto, ALMACEN_CENTRAL],
        )


def _validar_marca_linea(
    conn: duckdb.DuckDBPyConnection,
    *,
    id_marca: Optional[int],
    id_linea: Optional[int],
) -> None:
    if id_marca is not None:
        row = conn.execute(
            "SELECT 1 FROM marcas WHERE id_marca = ? AND COALESCE(activo, true) = true",
            [id_marca],
        ).fetchone()
        if not row:
            raise ValueError("La marca seleccionada no existe o está inactiva.")
    if id_linea is not None:
        row = conn.execute(
            "SELECT id_marca FROM lineas_producto WHERE id_linea = ? AND COALESCE(activo, true) = true",
            [id_linea],
        ).fetchone()
        if not row:
            raise ValueError("La línea seleccionada no existe o está inactiva.")
        linea_marca = int(row[0]) if row[0] is not None else None
        if id_marca is not None and linea_marca is not None and linea_marca != id_marca:
            raise ValueError("La línea no pertenece a la marca seleccionada.")
        if id_marca is None and linea_marca is not None:
            raise ValueError("Selecciona la marca correspondiente a la línea.")


def crear_producto(
    conn: duckdb.DuckDBPyConnection,
    *,
    nombre_producto: str,
    descripcion: Optional[str],
    id_item_type: int,
    precio_unitario: float,
    precio_mayorista: float,
    imagen_url: Optional[str],
    stock_inicial: float = 0,
    stock_minimo: float = 10,
    id_marca: Optional[int] = None,
    id_linea: Optional[int] = None,
    sku: Optional[str] = None,
    descuento_pct: float = 0,
    precio_rebajado: Optional[float] = None,
    descuento_aplica_a: str = "mayorista",
    fecha_rebaja_hasta: Optional[str] = None,
    descuento_motivo: Optional[str] = None,
) -> dict[str, Any]:
    if precio_mayorista > precio_unitario:
        raise ValueError("El precio mayorista no puede ser mayor que el precio unitario.")
    aplica = (descuento_aplica_a or "mayorista").strip().lower()
    if aplica not in ("mayorista", "retail", "ambos"):
        raise ValueError("descuento_aplica_a debe ser mayorista, retail o ambos.")

    asegurar_dim_item_type(conn, id_item_type)
    cat = conn.execute(
        "SELECT 1 FROM dim_item_type WHERE id_item_type = ?", [id_item_type]
    ).fetchone()
    if not cat:
        raise ValueError(f"No existe la categoría (id_item_type={id_item_type}).")

    duplicado = conn.execute(
        "SELECT 1 FROM dim_producto WHERE lower(nombre_producto) = lower(?) AND id_item_type = ?",
        [nombre_producto, id_item_type],
    ).fetchone()
    if duplicado:
        raise ValueError("Ya existe un producto con ese nombre en la misma categoría.")

    _validar_marca_linea(conn, id_marca=id_marca, id_linea=id_linea)
    if id_marca is not None and id_linea is None:
        n_lineas = conn.execute(
            "SELECT COUNT(*) FROM lineas_producto WHERE id_marca = ? AND COALESCE(activo, true) = true",
            [id_marca],
        ).fetchone()[0]
        if int(n_lineas or 0) > 0:
            raise ValueError("Seleccione la línea de producto para la marca indicada.")

    # Flujo B2B: el alta no inventa stock; entra por OC / movimiento de inventario.
    stock_inicial = 0.0
    umbral = max(0.0, float(stock_minimo if stock_minimo is not None else 10))

    sku_val = (sku or "").strip() or None

    conn.execute("BEGIN TRANSACTION")
    try:
        id_producto = siguiente_id(conn, "dim_producto")
        if not sku_val:
            sku_val = f"GM-{id_producto:06d}"
        conn.execute(
            """
            INSERT INTO dim_producto (
              id_producto, nombre_producto, descripcion, id_item_type, precio_unitario, precio_mayorista,
              imagen_url, activo, id_marca, id_linea, sku, descuento_pct, precio_rebajado,
              descuento_aplica_a, stock_minimo, fecha_rebaja_hasta, descuento_motivo
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, true, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                id_producto, nombre_producto, descripcion, id_item_type, precio_unitario, precio_mayorista,
                imagen_url, id_marca, id_linea, sku_val, float(descuento_pct or 0), precio_rebajado,
                aplica, umbral, fecha_rebaja_hasta or None, (descuento_motivo or None),
            ],
        )
        _asegurar_stock_row(conn, id_producto)
        from backend.services.inventario_service import fijar_alerta
        fijar_alerta(
            conn, id_producto=id_producto, umbral_minimo=umbral, id_almacen=ALMACEN_CENTRAL,
        )
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise

    return obtener_producto(conn, id_producto)


def actualizar_producto(
    conn: duckdb.DuckDBPyConnection,
    id_producto: int,
    cambios: dict[str, Any],
) -> Optional[dict[str, Any]]:
    actual = obtener_producto(conn, id_producto)
    if not actual:
        return None

    avisar_clientes = bool(cambios.pop("avisar_clientes", True))
    dto_anterior = float(actual.get("descuento_pct") or 0)

    nuevo_pu = cambios.get("precio_unitario", actual["precio_unitario"])
    nuevo_pm = cambios.get("precio_mayorista", actual["precio_mayorista"])
    if nuevo_pu is not None and nuevo_pm is not None and nuevo_pm > nuevo_pu:
        raise ValueError("El precio mayorista no puede ser mayor que el precio unitario.")

    if "id_marca" in cambios or "id_linea" in cambios:
        _validar_marca_linea(
            conn,
            id_marca=cambios.get("id_marca", actual.get("id_marca")),
            id_linea=cambios.get("id_linea", actual.get("id_linea")),
        )

    campos = {
        "nombre_producto": "nombre_producto",
        "descripcion": "descripcion",
        "id_item_type": "id_item_type",
        "id_marca": "id_marca",
        "id_linea": "id_linea",
        "sku": "sku",
        "precio_unitario": "precio_unitario",
        "precio_mayorista": "precio_mayorista",
        "descuento_pct": "descuento_pct",
        "precio_rebajado": "precio_rebajado",
        "descuento_aplica_a": "descuento_aplica_a",
        "fecha_rebaja_hasta": "fecha_rebaja_hasta",
        "descuento_motivo": "descuento_motivo",
        "imagen_url": "imagen_url",
        "activo": "activo",
        "stock_minimo": "stock_minimo",
    }
    sets: list[str] = []
    params: list[Any] = []
    for key, col in campos.items():
        if key not in cambios:
            continue
        if key == "activo":
            sets.append(f"{col} = ?")
            params.append(bool(cambios[key]))
            continue
        if cambios[key] is not None:
            sets.append(f"{col} = ?")
            params.append(cambios[key])
    if sets:
        conn.execute(
            f"UPDATE dim_producto SET {', '.join(sets)} WHERE id_producto = ?",
            [*params, id_producto],
        )
    if "stock_minimo" in cambios and cambios["stock_minimo"] is not None:
        from backend.services.inventario_service import fijar_alerta
        fijar_alerta(
            conn,
            id_producto=id_producto,
            umbral_minimo=float(cambios["stock_minimo"]),
            id_almacen=ALMACEN_CENTRAL,
        )
    resultado = obtener_producto(conn, id_producto)
    dto_nuevo = float((resultado or {}).get("descuento_pct") or 0)
    if resultado and dto_nuevo > 0 and dto_nuevo != dto_anterior and avisar_clientes:
        _publicar_descuento_producto(conn, resultado)
    return resultado


def _publicar_descuento_producto(
    conn: duckdb.DuckDBPyConnection, producto: Optional[dict[str, Any]]
) -> None:
    """Avisa a los clientes cuando un producto estrena o cambia su descuento."""
    if not producto:
        return
    try:
        from shared.services import notificacion_service as ns

        id_producto = int(producto["id_producto"])
        prioritarios = [
            int(r[0])
            for r in conn.execute(
                "SELECT DISTINCT id_usuario FROM wishlist WHERE id_producto = ?",
                [id_producto],
            ).fetchall()
        ]
        ns.notificar_descuento(
            conn,
            ambito="producto",
            nombre=producto["nombre_producto"],
            descuento_pct=float(producto.get("descuento_pct") or 0),
            link=f"/pages/producto.html?id={id_producto}",
            hasta=producto.get("fecha_rebaja_hasta"),
            motivo=producto.get("descuento_motivo"),
            usuarios_prioritarios=prioritarios,
        )
    except Exception:
        pass


def desactivar_producto(conn: duckdb.DuckDBPyConnection, id_producto: int) -> bool:
    return set_producto_activo(conn, id_producto, False)


def _producto_historial_duro(conn: duckdb.DuckDBPyConnection, id_producto: int) -> bool:
    """True si hay historial comercial que debe preservarse (ventas/pedidos/OC)."""
    consultas = [
        "SELECT 1 FROM fact_ventas WHERE id_producto = ? LIMIT 1",
        "SELECT 1 FROM pedido_detalle WHERE id_producto = ? LIMIT 1",
        "SELECT 1 FROM carrito_items WHERE id_producto = ? LIMIT 1",
        "SELECT 1 FROM orden_compra_detalle WHERE id_producto = ? LIMIT 1",
        "SELECT 1 FROM reservas_stock WHERE id_producto = ? LIMIT 1",
    ]
    for q in consultas:
        try:
            if conn.execute(q, [id_producto]).fetchone():
                return True
        except Exception:
            continue
    return False


def _producto_referenciado(conn: duckdb.DuckDBPyConnection, id_producto: int) -> bool:
    """Compat: historial comercial o stock positivo."""
    if _producto_historial_duro(conn, id_producto):
        return True
    try:
        return bool(
            conn.execute(
                "SELECT 1 FROM stock_almacen WHERE id_producto = ? AND cantidad_disponible > 0 LIMIT 1",
                [id_producto],
            ).fetchone()
        )
    except Exception:
        return False


def eliminar_producto(conn: duckdb.DuckDBPyConnection, id_producto: int) -> tuple[bool, str]:
    """Borra el producto si no tiene ventas/pedidos/OC; si tiene, solo lo desactiva.

    Limpia stock, alertas, paquetes, wishlist y líneas de movimiento de prueba.
    Devuelve (ok, modo) con modo en {"eliminado", "desactivado"}.
    """
    row = conn.execute(
        "SELECT activo FROM dim_producto WHERE id_producto = ?", [id_producto]
    ).fetchone()
    if not row:
        return False, ""
    if _producto_historial_duro(conn, id_producto):
        conn.execute(
            "UPDATE dim_producto SET activo = false WHERE id_producto = ?",
            [id_producto],
        )
        return True, "desactivado"
    for q in (
        "DELETE FROM catalogo_detalle WHERE id_producto = ?",
        "DELETE FROM alertas_stock WHERE id_producto = ?",
        "DELETE FROM stock_almacen WHERE id_producto = ?",
        "DELETE FROM wishlist WHERE id_producto = ?",
        "DELETE FROM promocion_productos WHERE id_producto = ?",
        "DELETE FROM lista_precio_detalle WHERE id_producto = ?",
        "DELETE FROM movimiento_inventario_detalle WHERE id_producto = ?",
    ):
        try:
            conn.execute(q, [id_producto])
        except Exception:
            pass
    # Cabeceras de movimiento sin detalle
    try:
        conn.execute(
            """
            DELETE FROM movimientos_inventario
            WHERE id_movimiento NOT IN (
              SELECT DISTINCT id_movimiento FROM movimiento_inventario_detalle
            )
            """
        )
    except Exception:
        pass
    conn.execute("DELETE FROM dim_producto WHERE id_producto = ?", [id_producto])
    return True, "eliminado"


def set_producto_activo(conn: duckdb.DuckDBPyConnection, id_producto: int, activo: bool) -> bool:
    if not conn.execute("SELECT 1 FROM dim_producto WHERE id_producto = ?", [id_producto]).fetchone():
        return False
    conn.execute("UPDATE dim_producto SET activo = ? WHERE id_producto = ?", [bool(activo), id_producto])
    return True
