"""Generación segura de IDs cuando DuckDB no aplica DEFAULT en la PK."""

from __future__ import annotations

import duckdb

_TABLA_PK: dict[str, str] = {
    "ordenes_compra": "id_oc",
    "recepciones_compra": "id_recepcion",
    "proveedores": "id_proveedor",
    "dim_producto": "id_producto",
    "categorias": "id_categoria",
    "movimientos_inventario": "id_movimiento",
    "pedidos": "id_pedido",
    "pedido_detalle": "id_detalle",
    "pagos": "id_pago",
    "carritos": "id_carrito",
    "usuarios": "id_usuario",
    "clientes": "id_cliente",
    "dim_cliente": "id_cliente",
}


def siguiente_id(
    conn: duckdb.DuckDBPyConnection,
    tabla: str,
    columna: str | None = None,
) -> int:
    col = columna or _TABLA_PK.get(tabla)
    if not col or tabla not in _TABLA_PK:
        raise ValueError(f"Tabla no permitida para siguiente_id: {tabla}")
    row = conn.execute(
        f"SELECT COALESCE(MAX({col}), 0) + 1 FROM {tabla}"  # noqa: S608 — tabla en whitelist
    ).fetchone()
    return int(row[0])
