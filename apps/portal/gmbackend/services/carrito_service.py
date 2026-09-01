"""
services/carrito_service.py — Carrito persistente con precios congelados.

Un carrito `activo` por cliente. Al agregar un producto se congela el precio
vigente (mayorista si cantidad >= mínimo mayorista, si no unitario).
"""

from __future__ import annotations

from typing import Any, Optional

import duckdb

from shared.services import precios_b2b, red_bodegas
from shared.services.config_service import obtener_config_int
from shared.database.ids import siguiente_id
from shared.services.promocion_service import calcular_totales_venta

from gmbackend.services.producto_service import _imagen_publica

MINIMO_MAYORISTA = 10  # fallback si no hay config


def _moq(conn: duckdb.DuckDBPyConnection) -> int:
    return obtener_config_int(conn, "MOQ_MAYORISTA", MINIMO_MAYORISTA)


def _red(conn: duckdb.DuckDBPyConnection, id_cliente: int) -> dict[str, Any]:
    return red_bodegas.red_de_cliente(conn, id_cliente=id_cliente)


def _almacenes(conn: duckdb.DuckDBPyConnection, id_cliente: int) -> list[int]:
    return list(_red(conn, id_cliente).get("almacenes") or [])


_SQL_PRECIOS_PRODUCTO = """
SELECT CAST(p.precio_unitario AS DOUBLE), CAST(p.precio_mayorista AS DOUBLE),
       CAST(COALESCE(p.descuento_pct, 0) AS DOUBLE), CAST(p.precio_rebajado AS DOUBLE),
       COALESCE(p.descuento_aplica_a, 'mayorista'), p.activo,
       p.id_item_type, p.fecha_rebaja_hasta, p.nombre_producto
FROM dim_producto p WHERE p.id_producto = ?
"""


class _Precios:
    """Datos de precio de un producto con su descuento ya resuelto."""

    __slots__ = ("unitario", "mayorista", "rebajado_manual", "activo", "nombre", "dto")

    def __init__(self, unitario, mayorista, rebajado_manual, activo, nombre, dto):
        self.unitario = unitario
        self.mayorista = mayorista
        self.rebajado_manual = rebajado_manual
        self.activo = activo
        self.nombre = nombre
        self.dto = dto


def _leer_precios(conn: duckdb.DuckDBPyConnection, id_producto: int) -> _Precios:
    prod = conn.execute(_SQL_PRECIOS_PRODUCTO, [id_producto]).fetchone()
    if not prod:
        raise ValueError("Producto no disponible.")
    dto = precios_b2b.resolver_descuento(
        conn,
        id_item_type=int(prod[6]) if prod[6] is not None else None,
        descuento_producto=float(prod[2] or 0),
        aplica_producto=prod[4],
        rebaja_hasta=prod[7],
    )
    return _Precios(
        unitario=float(prod[0] or 0),
        mayorista=float(prod[1] or 0),
        rebajado_manual=float(prod[3]) if prod[3] is not None else None,
        activo=bool(prod[5]),
        nombre=prod[8],
        dto=dto,
    )


def _precio_para(
    conn: duckdb.DuckDBPyConnection,
    cantidad: int,
    precios: _Precios,
    *,
    descuento_paquete: float = 0.0,
) -> float:
    """Precio de línea: tramo por MOQ, mejor descuento y bonus de paquete.

    El descuento de paquete es adicional porque premia comprar el bundle;
    producto y categoría, en cambio, nunca se suman entre sí.
    """
    dto = precios.dto
    retail = precios_b2b.precio_retail_efectivo(
        precios.unitario, pct=dto["pct"], aplica_a=dto["aplica_a"]
    )
    mayorista = precios_b2b.precio_mayorista_efectivo(
        precios.mayorista,
        pct=dto["pct"],
        aplica_a=dto["aplica_a"],
        precio_rebajado=precios.rebajado_manual,
        origen=dto["origen"],
    )
    base = mayorista if cantidad >= _moq(conn) else retail
    return precios_b2b.precio_con_descuento(base, descuento_paquete)


def obtener_carrito_activo(conn: duckdb.DuckDBPyConnection, id_cliente: int) -> Optional[int]:
    row = conn.execute(
        "SELECT id_carrito FROM carritos WHERE id_cliente = ? AND estado = 'activo' ORDER BY id_carrito DESC LIMIT 1",
        [id_cliente],
    ).fetchone()
    return int(row[0]) if row else None


def _crear_carrito(conn: duckdb.DuckDBPyConnection, id_cliente: int) -> int:
    id_carrito = siguiente_id(conn, "carritos")
    conn.execute(
        "INSERT INTO carritos (id_carrito, id_cliente, estado) VALUES (?, ?, 'activo')",
        [id_carrito, id_cliente],
    )
    return id_carrito


def _carrito_o_crear(conn: duckdb.DuckDBPyConnection, id_cliente: int) -> int:
    existente = obtener_carrito_activo(conn, id_cliente)
    return existente if existente is not None else _crear_carrito(conn, id_cliente)


def ver_carrito(conn: duckdb.DuckDBPyConnection, id_cliente: int) -> dict[str, Any]:
    red = _red(conn, id_cliente)
    zona = {
        "zona_entrega": red.get("macro_zona"),
        "zona_label": red.get("macro_label"),
        "bodega_asignada": red.get("bodega_principal"),
    }
    id_carrito = obtener_carrito_activo(conn, id_cliente)
    if id_carrito is None:
        vacio = calcular_totales_venta(conn, subtotal_items=0.0)
        return {"id_carrito": None, "items": [], "total": 0.0, "n_items": 0, **vacio, **zona}

    stock_zona_sql = red_bodegas.sql_stock_zona(red.get("almacenes"), "ci.id_producto")
    rows = conn.execute(
        f"""
        SELECT ci.id_item, ci.id_producto, p.nombre_producto, p.imagen_url,
               ci.cantidad, CAST(ci.precio_congelado AS DOUBLE), CAST(ci.subtotal AS DOUBLE),
               CAST({stock_zona_sql} AS DOUBLE) AS stock,
               COALESCE(p.sku, 'GM-' || LPAD(CAST(p.id_producto AS VARCHAR), 6, '0')) AS sku,
               it.item_type AS categoria
        FROM carrito_items ci
        JOIN dim_producto p ON p.id_producto = ci.id_producto
        LEFT JOIN dim_item_type it ON it.id_item_type = p.id_item_type
        WHERE ci.id_carrito = ?
        ORDER BY ci.id_item
        """,
        [id_carrito],
    ).fetchall()
    items = [
        {
            "id_item": int(r[0]),
            "id_producto": int(r[1]),
            "nombre_producto": r[2],
            "imagen_url": _imagen_publica(r[3]),
            "cantidad": int(r[4]),
            "precio": float(r[5]),
            "subtotal": float(r[6]),
            "stock_disponible": max(0.0, float(r[7])),
            "sku": r[8],
            "categoria": r[9],
        }
        for r in rows
    ]
    total = round(sum(i["subtotal"] for i in items), 2)
    totales = calcular_totales_venta(conn, subtotal_items=total)
    return {
        "id_carrito": id_carrito,
        "items": items,
        "total": total,
        "n_items": len(items),
        **totales,
        **zona,
    }


def _stock_disponible_neto(
    conn: duckdb.DuckDBPyConnection, id_producto: int, almacenes: list[int] | None = None
) -> float:
    return red_bodegas.stock_zona(conn, id_producto, almacenes)


def _bloquear_si_pedido_pendiente(conn: duckdb.DuckDBPyConnection, id_cliente: int) -> None:
    row = conn.execute(
        """
        SELECT numero FROM pedidos
        WHERE id_cliente = ? AND estado = 'pendiente_pago'
        ORDER BY id_pedido DESC LIMIT 1
        """,
        [id_cliente],
    ).fetchone()
    if row:
        raise ValueError(
            f"Tienes el pedido {row[0]} pendiente de pago. "
            "Complétalo en checkout o cancélalo antes de modificar el carrito."
        )


def agregar_item(
    conn: duckdb.DuckDBPyConnection,
    *,
    id_cliente: int,
    id_producto: int,
    cantidad: int,
) -> dict[str, Any]:
    if not isinstance(cantidad, int) or isinstance(cantidad, bool) or cantidad < 1 or cantidad > 100_000:
        raise ValueError("La cantidad debe ser un número entero entre 1 y 100.000.")
    _bloquear_si_pedido_pendiente(conn, id_cliente)
    precios = _leer_precios(conn, id_producto)
    if not precios.activo:
        raise ValueError("Producto no disponible.")

    red = _red(conn, id_cliente)
    almacenes = list(red.get("almacenes") or [])
    disponible = _stock_disponible_neto(conn, id_producto, almacenes)
    if disponible <= 0:
        zona = red.get("macro_label") or "tu zona de entrega"
        raise ValueError(f"Agotado en {zona}: este producto no tiene stock en la bodega que te atiende.")

    conn.execute("BEGIN TRANSACTION")
    try:
        id_carrito = _carrito_o_crear(conn, id_cliente)

        existente = conn.execute(
            "SELECT id_item, cantidad FROM carrito_items WHERE id_carrito = ? AND id_producto = ?",
            [id_carrito, id_producto],
        ).fetchone()

        nueva_cantidad = cantidad + (int(existente[1]) if existente else 0)
        if nueva_cantidad > disponible:
            raise ValueError(f"Stock insuficiente en tu zona: disponibles {disponible:g} unidades.")

        precio = _precio_para(conn, nueva_cantidad, precios)
        subtotal = round(precio * nueva_cantidad, 2)

        if existente:
            conn.execute(
                "UPDATE carrito_items SET cantidad = ?, precio_congelado = ?, subtotal = ? WHERE id_item = ?",
                [nueva_cantidad, precio, subtotal, int(existente[0])],
            )
        else:
            conn.execute(
                """
                INSERT INTO carrito_items (id_item, id_carrito, id_producto, cantidad, precio_congelado, subtotal)
                VALUES ((SELECT COALESCE(MAX(id_item), 0) + 1 FROM carrito_items), ?, ?, ?, ?, ?)
                """,
                [id_carrito, id_producto, nueva_cantidad, precio, subtotal],
            )
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise
    return ver_carrito(conn, id_cliente)


def actualizar_item(
    conn: duckdb.DuckDBPyConnection,
    *,
    id_cliente: int,
    id_item: int,
    cantidad: int,
) -> dict[str, Any]:
    if not isinstance(cantidad, int) or isinstance(cantidad, bool) or cantidad < 0 or cantidad > 100_000:
        raise ValueError("La cantidad debe ser un número entero entre 0 y 100.000.")
    _bloquear_si_pedido_pendiente(conn, id_cliente)
    id_carrito = obtener_carrito_activo(conn, id_cliente)
    if id_carrito is None:
        raise ValueError("No hay carrito activo.")

    item = conn.execute(
        "SELECT id_producto FROM carrito_items WHERE id_item = ? AND id_carrito = ?",
        [id_item, id_carrito],
    ).fetchone()
    if not item:
        raise ValueError("Item no encontrado en el carrito.")
    id_producto = int(item[0])

    conn.execute("BEGIN TRANSACTION")
    try:
        if cantidad == 0:
            conn.execute("DELETE FROM carrito_items WHERE id_item = ?", [id_item])
        else:
            red = _red(conn, id_cliente)
            disponible = _stock_disponible_neto(conn, id_producto, list(red.get("almacenes") or []))
            if disponible <= 0:
                zona = red.get("macro_label") or "tu zona de entrega"
                raise ValueError(f"Agotado en {zona}: sin stock en la bodega que te atiende.")
            if cantidad > disponible:
                raise ValueError(f"Stock insuficiente en tu zona: disponibles {disponible:g} unidades.")

            precio = _precio_para(conn, cantidad, _leer_precios(conn, id_producto))
            conn.execute(
                "UPDATE carrito_items SET cantidad = ?, precio_congelado = ?, subtotal = ? WHERE id_item = ?",
                [cantidad, precio, round(precio * cantidad, 2), id_item],
            )
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise
    return ver_carrito(conn, id_cliente)


def vaciar_carrito(conn: duckdb.DuckDBPyConnection, id_cliente: int) -> dict[str, Any]:
    id_carrito = obtener_carrito_activo(conn, id_cliente)
    if id_carrito is not None:
        conn.execute("DELETE FROM carrito_items WHERE id_carrito = ?", [id_carrito])
    return ver_carrito(conn, id_cliente)


def agregar_linea_reorden(
    conn: duckdb.DuckDBPyConnection,
    *,
    id_carrito: int,
    id_cliente: int,
    id_producto: int,
    cantidad_solicitada: int,
) -> dict[str, Any]:
    """Intenta agregar una línea al carrito tolerando omisiones (recompra desde pedido).

    No abre transacción ni valida pedido pendiente — lo orquesta ``volver_a_pedir``.
    """
    if not isinstance(cantidad_solicitada, int) or isinstance(cantidad_solicitada, bool):
        cantidad_solicitada = 0
    if cantidad_solicitada < 1:
        return {
            "estado": "omitido",
            "id_producto": id_producto,
            "nombre_producto": None,
            "cantidad_solicitada": cantidad_solicitada,
            "cantidad_agregada": 0,
            "motivo": "no_disponible",
        }

    try:
        precios = _leer_precios(conn, id_producto)
    except ValueError:
        return {
            "estado": "omitido",
            "id_producto": id_producto,
            "nombre_producto": None,
            "cantidad_solicitada": cantidad_solicitada,
            "cantidad_agregada": 0,
            "motivo": "no_disponible",
        }

    nombre = precios.nombre
    if not precios.activo:
        return {
            "estado": "omitido",
            "id_producto": id_producto,
            "nombre_producto": nombre,
            "cantidad_solicitada": cantidad_solicitada,
            "cantidad_agregada": 0,
            "motivo": "no_disponible",
        }

    red = _red(conn, id_cliente)
    almacenes = list(red.get("almacenes") or [])
    disponible = _stock_disponible_neto(conn, id_producto, almacenes)

    existente = conn.execute(
        "SELECT id_item, cantidad FROM carrito_items WHERE id_carrito = ? AND id_producto = ?",
        [id_carrito, id_producto],
    ).fetchone()
    existente_qty = int(existente[1]) if existente else 0
    objetivo = existente_qty + cantidad_solicitada

    if disponible <= 0 or existente_qty >= disponible:
        return {
            "estado": "omitido",
            "id_producto": id_producto,
            "nombre_producto": nombre,
            "cantidad_solicitada": cantidad_solicitada,
            "cantidad_agregada": 0,
            "motivo": "sin_stock",
        }

    if objetivo <= disponible:
        cantidad_final = objetivo
        cantidad_agregada = cantidad_solicitada
        estado = "agregado"
        motivo: str | None = None
    else:
        cantidad_final = int(disponible)
        cantidad_agregada = cantidad_final - existente_qty
        if cantidad_agregada <= 0:
            return {
                "estado": "omitido",
                "id_producto": id_producto,
                "nombre_producto": nombre,
                "cantidad_solicitada": cantidad_solicitada,
                "cantidad_agregada": 0,
                "motivo": "sin_stock",
            }
        estado = "ajustado"
        motivo = "stock_parcial"

    precio = _precio_para(conn, cantidad_final, precios)
    subtotal = round(precio * cantidad_final, 2)

    if existente:
        conn.execute(
            "UPDATE carrito_items SET cantidad = ?, precio_congelado = ?, subtotal = ? WHERE id_item = ?",
            [cantidad_final, precio, subtotal, int(existente[0])],
        )
    else:
        conn.execute(
            """
            INSERT INTO carrito_items (id_item, id_carrito, id_producto, cantidad, precio_congelado, subtotal)
            VALUES ((SELECT COALESCE(MAX(id_item), 0) + 1 FROM carrito_items), ?, ?, ?, ?, ?)
            """,
            [id_carrito, id_producto, cantidad_final, precio, subtotal],
        )

    resultado: dict[str, Any] = {
        "estado": estado,
        "id_producto": id_producto,
        "nombre_producto": nombre,
        "cantidad_solicitada": cantidad_solicitada,
        "cantidad_agregada": cantidad_agregada,
    }
    if motivo:
        resultado["motivo"] = motivo
    return resultado


def agregar_paquete(
    conn: duckdb.DuckDBPyConnection,
    *,
    id_cliente: int,
    id_catalogo: int,
    items: list[dict[str, int]],
) -> dict[str, Any]:
    """Agrega un catálogo configurado (varios productos con sus cantidades) al carrito.

    - Solo admite productos pertenecientes al catálogo.
    - Cantidad 0 = ese producto no se lleva; el resto se suma/actualiza en el carrito.
    - El precio se congela con el tramo por MOQ, el mejor descuento producto/categoría
      y, encima, el descuento propio del paquete.
    - El stock se valida contra las bodegas de la macro-zona del cliente.
    """
    if not items:
        raise ValueError("El paquete debe incluir al menos un producto con cantidad mayor a 0.")
    _bloquear_si_pedido_pendiente(conn, id_cliente)
    catalogo = conn.execute(
        "SELECT id_catalogo, nombre, activo FROM catalogos WHERE id_catalogo = ?", [id_catalogo]
    ).fetchone()
    if not catalogo or not bool(catalogo[2]):
        raise ValueError("Catálogo no disponible.")

    validos = {
        int(r[0])
        for r in conn.execute(
            "SELECT id_producto FROM catalogo_detalle WHERE id_catalogo = ?", [id_catalogo]
        ).fetchall()
    }

    dto_paquete = precios_b2b.descuento_paquete(conn, id_catalogo)["pct"]
    red = _red(conn, id_cliente)
    almacenes = list(red.get("almacenes") or [])
    zona_label = red.get("macro_label") or "tu zona de entrega"

    conn.execute("BEGIN TRANSACTION")
    try:
        id_carrito = _carrito_o_crear(conn, id_cliente)
        agregados = 0
        for item in items:
            id_producto = int(item["id_producto"])
            cantidad = int(item["cantidad"])
            if not isinstance(cantidad, int) or isinstance(cantidad, bool) or cantidad < 0 or cantidad > 100_000:
                raise ValueError("Cada cantidad debe ser un número entero entre 0 y 100.000.")
            if cantidad == 0:
                continue
            if id_producto not in validos:
                raise ValueError("Uno o más productos no pertenecen a este catálogo.")
            precios = _leer_precios(conn, id_producto)
            if not precios.activo:
                raise ValueError("Uno o más productos no están disponibles.")
            nombre = precios.nombre
            disponible = _stock_disponible_neto(conn, id_producto, almacenes)

            existente = conn.execute(
                "SELECT id_item, cantidad FROM carrito_items WHERE id_carrito = ? AND id_producto = ?",
                [id_carrito, id_producto],
            ).fetchone()
            nueva_cantidad = cantidad + (int(existente[1]) if existente else 0)
            if disponible <= 0:
                raise ValueError(f"{nombre} está agotado en {zona_label}.")
            if nueva_cantidad > disponible:
                raise ValueError(
                    f"Stock insuficiente de {nombre} en {zona_label}: disponibles {disponible:g} unidades."
                )

            precio = _precio_para(conn, nueva_cantidad, precios, descuento_paquete=dto_paquete)
            subtotal = round(precio * nueva_cantidad, 2)

            if existente:
                conn.execute(
                    "UPDATE carrito_items SET cantidad = ?, precio_congelado = ?, subtotal = ? WHERE id_item = ?",
                    [nueva_cantidad, precio, subtotal, int(existente[0])],
                )
            else:
                conn.execute(
                    """
                    INSERT INTO carrito_items (id_item, id_carrito, id_producto, cantidad, precio_congelado, subtotal)
                    VALUES ((SELECT COALESCE(MAX(id_item), 0) + 1 FROM carrito_items), ?, ?, ?, ?, ?)
                    """,
                    [id_carrito, id_producto, nueva_cantidad, precio, subtotal],
                )
            agregados += 1

        if agregados == 0:
            raise ValueError("El paquete debe incluir al menos un producto con cantidad mayor a 0.")
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise
    return ver_carrito(conn, id_cliente)
