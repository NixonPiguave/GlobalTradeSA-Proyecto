"""
precios_b2b.py — Resolución de descuentos en la jerarquía comercial.

Tres niveles, con reglas explícitas para que el precio sea reproducible:

1. Producto   (`dim_producto.descuento_pct` / `precio_rebajado`)
2. Categoría  (`categorias.descuento_pct`) — aplica a todos sus productos
3. Paquete    (`catalogos.descuento_pct`) — solo al comprar vía paquete

Entre producto y categoría gana **el mayor descuento vigente** (el cliente
recibe la mejor oferta, nunca se suman). El descuento del paquete sí es
adicional: premia el volumen de comprar el bundle completo y se aplica sobre
el precio de línea ya rebajado.

Una fecha `descuento_hasta` / `fecha_rebaja_hasta` en el pasado invalida el
descuento sin necesidad de un job de limpieza.
"""

from __future__ import annotations

from datetime import date
from typing import Any, Optional

import duckdb

from shared.database.connection import table_exists

APLICA_VALIDOS = ("mayorista", "retail", "ambos")


def _normalizar_aplica(valor: Any) -> str:
    aplica = str(valor or "mayorista").strip().lower()
    return aplica if aplica in APLICA_VALIDOS else "mayorista"


def _vigente(hasta: Any) -> bool:
    if hasta is None:
        return True
    try:
        limite = hasta if isinstance(hasta, date) else date.fromisoformat(str(hasta)[:10])
    except (TypeError, ValueError):
        return True
    return limite >= date.today()


def _columna_existe(conn: duckdb.DuckDBPyConnection, tabla: str, columna: str) -> bool:
    try:
        return bool(
            conn.execute(
                """
                SELECT 1 FROM information_schema.columns
                WHERE table_name = ? AND column_name = ?
                """,
                [tabla, columna],
            ).fetchone()
        )
    except Exception:
        return False


def descuento_categoria(
    conn: duckdb.DuckDBPyConnection, id_item_type: Optional[int]
) -> dict[str, Any]:
    """Descuento vigente de la categoría de un producto."""
    vacio = {"pct": 0.0, "aplica_a": "mayorista", "motivo": None, "hasta": None, "nombre": None}
    if id_item_type is None or not table_exists(conn, "categorias"):
        return vacio
    if not _columna_existe(conn, "categorias", "descuento_pct"):
        return vacio
    row = conn.execute(
        """
        SELECT CAST(COALESCE(descuento_pct, 0) AS DOUBLE),
               COALESCE(descuento_aplica_a, 'mayorista'),
               descuento_motivo, descuento_hasta, nombre
        FROM categorias
        WHERE id_item_type = ? AND COALESCE(activo, true) = true
        ORDER BY COALESCE(descuento_pct, 0) DESC
        LIMIT 1
        """,
        [int(id_item_type)],
    ).fetchone()
    if not row:
        return vacio
    pct = float(row[0] or 0)
    if pct <= 0 or not _vigente(row[3]):
        return {**vacio, "nombre": row[4]}
    return {
        "pct": pct,
        "aplica_a": _normalizar_aplica(row[1]),
        "motivo": row[2],
        "hasta": row[3],
        "nombre": row[4],
    }


def descuento_paquete(
    conn: duckdb.DuckDBPyConnection, id_catalogo: Optional[int]
) -> dict[str, Any]:
    """Descuento adicional por comprar el paquete completo."""
    vacio = {"pct": 0.0, "motivo": None, "hasta": None, "nombre": None}
    if id_catalogo is None or not table_exists(conn, "catalogos"):
        return vacio
    if not _columna_existe(conn, "catalogos", "descuento_pct"):
        return vacio
    row = conn.execute(
        """
        SELECT CAST(COALESCE(descuento_pct, 0) AS DOUBLE), descuento_motivo, descuento_hasta, nombre
        FROM catalogos WHERE id_catalogo = ?
        """,
        [int(id_catalogo)],
    ).fetchone()
    if not row:
        return vacio
    pct = float(row[0] or 0)
    if pct <= 0 or not _vigente(row[2]):
        return {**vacio, "nombre": row[3]}
    return {"pct": pct, "motivo": row[1], "hasta": row[2], "nombre": row[3]}


def mejor_descuento(
    *,
    pct_producto: Any = 0,
    aplica_producto: Any = "mayorista",
    rebaja_hasta: Any = None,
    pct_categoria: Any = 0,
    aplica_categoria: Any = "mayorista",
    categoria_hasta: Any = None,
    categoria_nombre: Any = None,
    categoria_motivo: Any = None,
) -> dict[str, Any]:
    """Compara descuento de producto vs categoría sin tocar la base de datos.

    Devuelve `{pct, aplica_a, origen, etiqueta}` con `origen` en
    'producto' | 'categoria' | 'ninguno'.
    """
    prod = float(pct_producto or 0)
    if not _vigente(rebaja_hasta):
        prod = 0.0
    cat = float(pct_categoria or 0)
    if not _vigente(categoria_hasta):
        cat = 0.0

    if prod <= 0 and cat <= 0:
        return {
            "pct": 0.0,
            "aplica_a": _normalizar_aplica(aplica_producto),
            "origen": "ninguno",
            "etiqueta": None,
        }

    if cat > prod:
        etiqueta = categoria_motivo or (
            f"Descuento en {categoria_nombre}" if categoria_nombre else "Descuento por categoría"
        )
        return {
            "pct": cat,
            "aplica_a": _normalizar_aplica(aplica_categoria),
            "origen": "categoria",
            "etiqueta": etiqueta,
        }

    return {
        "pct": prod,
        "aplica_a": _normalizar_aplica(aplica_producto),
        "origen": "producto",
        "etiqueta": "Precio rebajado",
    }


def resolver_descuento(
    conn: duckdb.DuckDBPyConnection,
    *,
    id_item_type: Optional[int],
    descuento_producto: float = 0.0,
    aplica_producto: Any = "mayorista",
    rebaja_hasta: Any = None,
) -> dict[str, Any]:
    """Mejor descuento entre producto y su categoría, leyendo la categoría."""
    cat = descuento_categoria(conn, id_item_type)
    return mejor_descuento(
        pct_producto=descuento_producto,
        aplica_producto=aplica_producto,
        rebaja_hasta=rebaja_hasta,
        pct_categoria=cat["pct"],
        aplica_categoria=cat["aplica_a"],
        categoria_hasta=cat["hasta"],
        categoria_nombre=cat["nombre"],
        categoria_motivo=cat["motivo"],
    )


def precio_con_descuento(base: float, pct: float) -> float:
    base = float(base or 0)
    pct = float(pct or 0)
    if base <= 0 or pct <= 0:
        return round(base, 2)
    return round(base * (1 - pct / 100.0), 2)


def precio_mayorista_efectivo(
    precio_mayorista: float,
    *,
    pct: float,
    aplica_a: str,
    precio_rebajado: Optional[float] = None,
    origen: str = "producto",
) -> float:
    """Precio mayorista tras el descuento resuelto.

    `precio_rebajado` es un precio fijado a mano por el ERP y solo manda
    cuando el descuento ganador viene del propio producto.
    """
    aplica = _normalizar_aplica(aplica_a)
    if aplica not in ("mayorista", "ambos"):
        return round(float(precio_mayorista or 0), 2)
    if origen == "producto" and precio_rebajado is not None and precio_rebajado > 0:
        return round(float(precio_rebajado), 2)
    return precio_con_descuento(precio_mayorista, pct)


def precio_retail_efectivo(precio_unitario: float, *, pct: float, aplica_a: str) -> float:
    aplica = _normalizar_aplica(aplica_a)
    if aplica not in ("retail", "ambos"):
        return round(float(precio_unitario or 0), 2)
    return precio_con_descuento(precio_unitario, pct)
