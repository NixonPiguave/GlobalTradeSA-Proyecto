"""
red_bodegas.py — Red de distribución: qué bodega sirve a cada cliente.

Modelo operativo (3 macro-zonas sobre las 8 regiones analíticas de dim_region):

    americas → Central America (3), North America (6), South America (8)
    emea     → Europe (4), MENA (5), Sub-Saharan Africa (7)
    apac     → Asia (1), Australia and Oceania (2)

Cada macro-zona tiene un hub principal y bodegas satélite. La disponibilidad
que ve un cliente es la de SU macro-zona: si el hub APAC no tiene unidades, el
cliente de Japón ve "agotado" aunque quede stock en Américas. El cruce entre
zonas solo ocurre si `FULFILLMENT_CROSS_ZONA` está activo en configuración.

Este módulo es la única fuente de verdad para:
  - resolver país/cliente → macro-zona → bodegas elegibles
  - consultar stock disponible dentro de una zona
  - planificar de qué bodegas se descuenta un pedido (y devolverlo al cancelar)
"""

from __future__ import annotations

from typing import Any, Iterable, Optional, Sequence

import duckdb

from shared.database.connection import table_exists
from shared.services.config_service import obtener_config_int

ALMACEN_CENTRAL = 1

MACRO_BY_REGION: dict[int, str] = {
    1: "apac",       # Asia
    2: "apac",       # Australia and Oceania
    3: "americas",   # Central America
    4: "emea",       # Europe
    5: "emea",       # Middle East and North Africa
    6: "americas",   # North America
    7: "emea",       # Sub-Saharan Africa
    8: "americas",   # South America
}

MACRO_LABELS: dict[str, str] = {
    "americas": "Américas",
    "emea": "EMEA (Europa / Medio Oriente / África)",
    "apac": "APAC (Asia / Oceanía)",
}

MACRO_HUB_REGION: dict[str, int] = {"americas": 8, "emea": 4, "apac": 1}

MACROS: tuple[str, ...] = ("americas", "emea", "apac")


def macro_de_region(id_region: Optional[int]) -> Optional[str]:
    if id_region is None:
        return None
    try:
        return MACRO_BY_REGION.get(int(id_region))
    except (TypeError, ValueError):
        return None


def macro_label(macro: Optional[str]) -> Optional[str]:
    if not macro:
        return None
    return MACRO_LABELS.get(macro, macro)


def _tiene_columna(conn: duckdb.DuckDBPyConnection, tabla: str, columna: str) -> bool:
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


def cross_zona_habilitado(conn: duckdb.DuckDBPyConnection) -> bool:
    """Si está activo, una zona sin stock puede servirse desde otra macro-zona."""
    return obtener_config_int(conn, "FULFILLMENT_CROSS_ZONA", 0) == 1


# ---------------------------------------------------------------------------
# Resolución geográfica
# ---------------------------------------------------------------------------

def resolver_region_pais(
    conn: duckdb.DuckDBPyConnection, pais: Optional[str]
) -> dict[str, Any]:
    """país (texto libre) → dim_country → dim_region → macro-zona."""
    vacio = {
        "pais": None,
        "id_country": None,
        "id_region": None,
        "region": None,
        "macro_zona": None,
        "macro_label": None,
    }
    nombre = (pais or "").strip()
    if not nombre or not table_exists(conn, "dim_country"):
        return vacio

    row = conn.execute(
        """
        SELECT c.id_country, c.country, c.id_region, r.region
        FROM dim_country c
        LEFT JOIN dim_region r ON r.id_region = c.id_region
        WHERE LOWER(TRIM(c.country)) = LOWER(TRIM(?))
        LIMIT 1
        """,
        [nombre],
    ).fetchone()
    if not row:
        row = conn.execute(
            """
            SELECT c.id_country, c.country, c.id_region, r.region
            FROM dim_country c
            LEFT JOIN dim_region r ON r.id_region = c.id_region
            WHERE LOWER(c.country) LIKE '%' || LOWER(TRIM(?)) || '%'
            ORDER BY LENGTH(c.country)
            LIMIT 1
            """,
            [nombre],
        ).fetchone()
    if not row:
        return {**vacio, "pais": nombre}

    id_region = int(row[2]) if row[2] is not None else None
    macro = macro_de_region(id_region)
    return {
        "pais": row[1] or nombre,
        "id_country": int(row[0]) if row[0] is not None else None,
        "id_region": id_region,
        "region": row[3],
        "macro_zona": macro,
        "macro_label": macro_label(macro),
    }


def pais_de_cliente(conn: duckdb.DuckDBPyConnection, id_cliente: Optional[int]) -> Optional[str]:
    if id_cliente is None:
        return None
    row = conn.execute(
        "SELECT pais FROM dim_cliente WHERE id_cliente = ?", [int(id_cliente)]
    ).fetchone()
    return row[0] if row and row[0] else None


def pais_de_proveedor(conn: duckdb.DuckDBPyConnection, id_proveedor: Optional[int]) -> Optional[str]:
    if id_proveedor is None or not table_exists(conn, "proveedores"):
        return None
    row = conn.execute(
        """
        SELECT c.country
        FROM proveedores p
        LEFT JOIN dim_country c ON c.id_country = p.id_country
        WHERE p.id_proveedor = ?
        """,
        [int(id_proveedor)],
    ).fetchone()
    return row[0] if row and row[0] else None


def geo_de_proveedor(
    conn: duckdb.DuckDBPyConnection, id_proveedor: Optional[int]
) -> dict[str, Any]:
    """País del proveedor → región → macro-zona → hub de recepción sugerido."""
    vacio: dict[str, Any] = {
        "id_proveedor": id_proveedor,
        "pais": None,
        "id_country": None,
        "id_region": None,
        "region": None,
        "macro_zona": None,
        "macro_label": None,
        "id_almacen_sugerido": ALMACEN_CENTRAL,
        "bodega_sugerida": None,
    }
    if id_proveedor is None or not table_exists(conn, "proveedores"):
        return vacio
    row = conn.execute(
        """
        SELECT p.id_proveedor, c.country, c.id_country, c.id_region, r.region
        FROM proveedores p
        LEFT JOIN dim_country c ON c.id_country = p.id_country
        LEFT JOIN dim_region r ON r.id_region = c.id_region
        WHERE p.id_proveedor = ?
        """,
        [int(id_proveedor)],
    ).fetchone()
    if not row:
        return vacio
    id_region = int(row[3]) if row[3] is not None else None
    macro = macro_de_region(id_region)
    hub = hub_de_macro(conn, macro) if macro else None
    return {
        "id_proveedor": int(row[0]),
        "pais": row[1],
        "id_country": int(row[2]) if row[2] is not None else None,
        "id_region": id_region,
        "region": row[4],
        "macro_zona": macro,
        "macro_label": macro_label(macro),
        "id_almacen_sugerido": (hub or {}).get("id_almacen", ALMACEN_CENTRAL),
        "bodega_sugerida": (hub or {}).get("nombre"),
    }


# ---------------------------------------------------------------------------
# Bodegas de la red
# ---------------------------------------------------------------------------

def _macro_de_almacen(id_almacen: int, macro_col: Optional[str], id_region: Optional[int]) -> Optional[str]:
    if macro_col and macro_col in MACRO_LABELS:
        return macro_col
    derivada = macro_de_region(id_region)
    if derivada:
        return derivada
    return "americas" if int(id_almacen) == ALMACEN_CENTRAL else None


def listar_bodegas_red(
    conn: duckdb.DuckDBPyConnection,
    *,
    macro: Optional[str] = None,
    activas_only: bool = True,
) -> list[dict[str, Any]]:
    """Bodegas de la red ordenadas por preferencia de despacho (hub primero)."""
    if not table_exists(conn, "almacenes"):
        return []

    tiene_macro = _tiene_columna(conn, "almacenes", "macro_zona")
    tiene_hub = _tiene_columna(conn, "almacenes", "es_hub")
    tiene_prio = _tiene_columna(conn, "almacenes", "prioridad")

    col_macro = "a.macro_zona" if tiene_macro else "CAST(NULL AS VARCHAR)"
    col_hub = "COALESCE(a.es_hub, false)" if tiene_hub else "false"
    col_prio = "COALESCE(a.prioridad, 50)" if tiene_prio else "50"

    where = "WHERE COALESCE(a.activo, true) = true" if activas_only else "WHERE 1 = 1"

    rows = conn.execute(
        f"""
        SELECT a.id_almacen, a.nombre, a.direccion, a.id_region, r.region,
               {col_macro} AS macro_zona, {col_hub} AS es_hub, {col_prio} AS prioridad,
               COALESCE(a.activo, true) AS activo
        FROM almacenes a
        LEFT JOIN dim_region r ON r.id_region = a.id_region
        {where}
        ORDER BY {col_prio}, a.id_almacen
        """
    ).fetchall()

    bodegas: list[dict[str, Any]] = []
    for r in rows:
        id_almacen = int(r[0])
        id_region = int(r[3]) if r[3] is not None else None
        macro_zona = _macro_de_almacen(id_almacen, r[5], id_region)
        bodegas.append(
            {
                "id_almacen": id_almacen,
                "nombre": r[1],
                "direccion": r[2],
                "id_region": id_region,
                "region": r[4],
                "macro_zona": macro_zona,
                "macro_label": macro_label(macro_zona),
                "es_hub": bool(r[6]),
                "prioridad": int(r[7] or 50),
                "activo": bool(r[8]),
            }
        )

    bodegas.sort(key=lambda b: (0 if b["es_hub"] else 1, b["prioridad"], b["id_almacen"]))
    if macro:
        bodegas = [b for b in bodegas if b["macro_zona"] == macro]
    return bodegas


def bodegas_de_macro(conn: duckdb.DuckDBPyConnection, macro: Optional[str]) -> list[int]:
    """IDs de bodega que sirven una macro-zona, en orden de despacho."""
    if not macro:
        return []
    return [b["id_almacen"] for b in listar_bodegas_red(conn, macro=macro)]


def hub_de_macro(conn: duckdb.DuckDBPyConnection, macro: Optional[str]) -> Optional[dict[str, Any]]:
    bodegas = listar_bodegas_red(conn, macro=macro)
    if not bodegas:
        return None
    for b in bodegas:
        if b["es_hub"]:
            return b
    return bodegas[0]


def red_de_cliente(
    conn: duckdb.DuckDBPyConnection,
    *,
    id_cliente: Optional[int] = None,
    pais: Optional[str] = None,
) -> dict[str, Any]:
    """Contexto de fulfillment de un cliente: su zona y las bodegas que lo sirven.

    Si no se puede determinar la zona (visitante sin sesión, país no mapeado),
    devuelve la red completa para no ocultar el catálogo, marcando `zona_resuelta`.
    """
    nombre_pais = pais or pais_de_cliente(conn, id_cliente)
    geo = resolver_region_pais(conn, nombre_pais)
    macro = geo.get("macro_zona")

    if macro:
        almacenes = bodegas_de_macro(conn, macro)
        if not almacenes:
            almacenes = [ALMACEN_CENTRAL]
        if cross_zona_habilitado(conn):
            resto = [
                b["id_almacen"]
                for b in listar_bodegas_red(conn)
                if b["id_almacen"] not in almacenes
            ]
            almacenes = almacenes + resto
        hub = hub_de_macro(conn, macro)
        return {
            **geo,
            "zona_resuelta": True,
            "almacenes": almacenes,
            "id_almacen_principal": (hub or {}).get("id_almacen", almacenes[0]),
            "bodega_principal": (hub or {}).get("nombre"),
        }

    todas = [b["id_almacen"] for b in listar_bodegas_red(conn)] or [ALMACEN_CENTRAL]
    return {
        **geo,
        "zona_resuelta": False,
        "almacenes": todas,
        "id_almacen_principal": todas[0],
        "bodega_principal": None,
    }


# ---------------------------------------------------------------------------
# Stock por zona
# ---------------------------------------------------------------------------

def _lista_ids(almacenes: Optional[Sequence[int]]) -> list[int]:
    if not almacenes:
        return []
    salida: list[int] = []
    for a in almacenes:
        try:
            valor = int(a)
        except (TypeError, ValueError):
            continue
        if valor > 0 and valor not in salida:
            salida.append(valor)
    return salida


def sql_filtro_almacenes(almacenes: Optional[Sequence[int]], alias: str = "sa") -> str:
    """Fragmento SQL `AND sa.id_almacen IN (...)`. Vacío = todas las bodegas."""
    ids = _lista_ids(almacenes)
    if not ids:
        return ""
    return f" AND {alias}.id_almacen IN ({', '.join(str(i) for i in ids)})"


def sql_stock_zona(almacenes: Optional[Sequence[int]], columna_producto: str) -> str:
    """Subconsulta escalar con el stock neto de un producto en la zona."""
    return (
        "COALESCE((SELECT SUM(sa.cantidad_disponible - sa.cantidad_reservada) "
        f"FROM stock_almacen sa WHERE sa.id_producto = {columna_producto}"
        f"{sql_filtro_almacenes(almacenes)}), 0)"
    )


def stock_zona(
    conn: duckdb.DuckDBPyConnection,
    id_producto: int,
    almacenes: Optional[Sequence[int]] = None,
) -> float:
    if not table_exists(conn, "stock_almacen"):
        return 0.0
    row = conn.execute(
        f"""
        SELECT CAST(COALESCE(SUM(sa.cantidad_disponible - sa.cantidad_reservada), 0) AS DOUBLE)
        FROM stock_almacen sa
        WHERE sa.id_producto = ?{sql_filtro_almacenes(almacenes)}
        """,
        [int(id_producto)],
    ).fetchone()
    return max(0.0, float(row[0] or 0))


def desglose_stock_producto(
    conn: duckdb.DuckDBPyConnection, id_producto: int
) -> list[dict[str, Any]]:
    """Stock del producto bodega por bodega, con su zona. Para trazabilidad."""
    if not table_exists(conn, "stock_almacen"):
        return []
    bodegas = {b["id_almacen"]: b for b in listar_bodegas_red(conn, activas_only=False)}
    rows = conn.execute(
        """
        SELECT sa.id_almacen,
               CAST(COALESCE(sa.cantidad_disponible, 0) AS DOUBLE),
               CAST(COALESCE(sa.cantidad_reservada, 0) AS DOUBLE)
        FROM stock_almacen sa
        WHERE sa.id_producto = ?
        """,
        [int(id_producto)],
    ).fetchall()
    salida = []
    for r in rows:
        info = bodegas.get(int(r[0]), {})
        salida.append(
            {
                "id_almacen": int(r[0]),
                "almacen": info.get("nombre") or f"Bodega {int(r[0])}",
                "macro_zona": info.get("macro_zona"),
                "macro_label": info.get("macro_label"),
                "region": info.get("region"),
                "es_hub": bool(info.get("es_hub")),
                "disponible": float(r[1]),
                "reservado": float(r[2]),
                "neto": max(0.0, float(r[1]) - float(r[2])),
            }
        )
    salida.sort(key=lambda s: (0 if s["es_hub"] else 1, s["id_almacen"]))
    return salida


def resumen_por_zona(conn: duckdb.DuckDBPyConnection, id_producto: int) -> dict[str, float]:
    """Stock neto agregado por macro-zona."""
    resumen = {m: 0.0 for m in MACROS}
    for fila in desglose_stock_producto(conn, id_producto):
        macro = fila.get("macro_zona")
        if macro in resumen:
            resumen[macro] += fila["neto"]
    return resumen


# ---------------------------------------------------------------------------
# Planificación de despacho
# ---------------------------------------------------------------------------

def plan_despacho(
    conn: duckdb.DuckDBPyConnection,
    id_producto: int,
    cantidad: float,
    almacenes: Sequence[int],
) -> list[tuple[int, float]]:
    """Reparte `cantidad` entre las bodegas de la zona, en orden de preferencia.

    Devuelve [(id_almacen, cantidad)]. Lanza ValueError si la zona no cubre.
    """
    restante = float(cantidad)
    if restante <= 0:
        return []
    ids = _lista_ids(almacenes)
    if not ids:
        raise ValueError("No hay bodegas asignadas para esta zona de entrega.")

    disponibles = {
        int(r[0]): max(0.0, float(r[1] or 0))
        for r in conn.execute(
            f"""
            SELECT sa.id_almacen,
                   CAST(COALESCE(sa.cantidad_disponible, 0) - COALESCE(sa.cantidad_reservada, 0) AS DOUBLE)
            FROM stock_almacen sa
            WHERE sa.id_producto = ?{sql_filtro_almacenes(almacenes)}
            """,
            [int(id_producto)],
        ).fetchall()
    }

    plan: list[tuple[int, float]] = []
    for id_almacen in ids:
        if restante <= 0:
            break
        libre = disponibles.get(id_almacen, 0.0)
        if libre <= 0:
            continue
        toma = min(libre, restante)
        plan.append((id_almacen, toma))
        restante -= toma

    if restante > 0:
        total = sum(disponibles.values())
        raise ValueError(
            f"Stock insuficiente en la zona de entrega: disponibles {total:g} unidades."
        )
    return plan


def _asegurar_fila_stock(conn: duckdb.DuckDBPyConnection, id_producto: int, id_almacen: int) -> None:
    existe = conn.execute(
        "SELECT 1 FROM stock_almacen WHERE id_producto = ? AND id_almacen = ?",
        [int(id_producto), int(id_almacen)],
    ).fetchone()
    if existe:
        return
    conn.execute(
        """
        INSERT INTO stock_almacen (id_stock, id_producto, id_almacen, cantidad_disponible, cantidad_reservada)
        VALUES ((SELECT COALESCE(MAX(id_stock), 0) + 1 FROM stock_almacen), ?, ?, 0, 0)
        """,
        [int(id_producto), int(id_almacen)],
    )


def _nuevo_movimiento(
    conn: duckdb.DuckDBPyConnection, *, tipo: str, referencia: str, id_usuario: Optional[int]
) -> int:
    conn.execute(
        """
        INSERT INTO movimientos_inventario (id_movimiento, tipo, fecha, referencia, id_usuario)
        VALUES ((SELECT COALESCE(MAX(id_movimiento), 0) + 1 FROM movimientos_inventario),
                ?, current_timestamp, ?, ?)
        """,
        [tipo, referencia, id_usuario],
    )
    row = conn.execute("SELECT MAX(id_movimiento) FROM movimientos_inventario").fetchone()
    return int(row[0])


def _registrar_detalle(
    conn: duckdb.DuckDBPyConnection,
    *,
    id_movimiento: int,
    id_producto: int,
    id_almacen: int,
    cantidad: float,
) -> None:
    conn.execute(
        """
        INSERT INTO movimiento_inventario_detalle (id_detalle, id_movimiento, id_producto, id_almacen, id_lote, cantidad)
        VALUES ((SELECT COALESCE(MAX(id_detalle), 0) + 1 FROM movimiento_inventario_detalle), ?, ?, ?, NULL, ?)
        """,
        [id_movimiento, int(id_producto), int(id_almacen), cantidad],
    )


def validar_stock_zona(
    conn: duckdb.DuckDBPyConnection,
    items: Iterable[dict[str, Any]],
    almacenes: Sequence[int],
) -> None:
    """Valida que la zona pueda cubrir todos los ítems. Lanza ValueError con detalle."""
    for item in items:
        id_producto = int(item["id_producto"])
        cantidad = float(item["cantidad"])
        disponible = stock_zona(conn, id_producto, almacenes)
        if disponible < cantidad:
            nombre = item.get("nombre_producto")
            if not nombre:
                row = conn.execute(
                    "SELECT nombre_producto FROM dim_producto WHERE id_producto = ?", [id_producto]
                ).fetchone()
                nombre = row[0] if row else f"producto {id_producto}"
            if disponible <= 0:
                raise ValueError(
                    f"{nombre} está agotado en la bodega que atiende tu zona de entrega."
                )
            raise ValueError(
                f"Stock insuficiente de {nombre} en tu zona: disponibles {disponible:g} unidades."
            )


def descontar_stock_zona(
    conn: duckdb.DuckDBPyConnection,
    items: Iterable[dict[str, Any]],
    almacenes: Sequence[int],
    *,
    referencia: str,
    id_usuario: Optional[int] = None,
) -> list[dict[str, Any]]:
    """Descuenta stock repartiendo entre las bodegas de la zona. Registra movimiento."""
    lista = list(items)
    if not lista:
        return []
    id_movimiento = _nuevo_movimiento(
        conn, tipo="salida", referencia=referencia, id_usuario=id_usuario
    )
    asignaciones: list[dict[str, Any]] = []
    for item in lista:
        id_producto = int(item["id_producto"])
        cantidad = float(item["cantidad"])
        for id_almacen, toma in plan_despacho(conn, id_producto, cantidad, almacenes):
            conn.execute(
                """
                UPDATE stock_almacen SET cantidad_disponible = cantidad_disponible - ?
                WHERE id_producto = ? AND id_almacen = ?
                """,
                [toma, id_producto, id_almacen],
            )
            _registrar_detalle(
                conn,
                id_movimiento=id_movimiento,
                id_producto=id_producto,
                id_almacen=id_almacen,
                cantidad=-toma,
            )
            asignaciones.append(
                {"id_producto": id_producto, "id_almacen": id_almacen, "cantidad": toma}
            )
    return asignaciones


def reponer_stock_zona(
    conn: duckdb.DuckDBPyConnection,
    items: Iterable[dict[str, Any]],
    almacenes: Sequence[int],
    *,
    referencia: str,
    id_usuario: Optional[int] = None,
) -> None:
    """Devuelve stock a la zona (cancelaciones). Usa el hub como destino."""
    lista = list(items)
    if not lista:
        return
    ids = _lista_ids(almacenes) or [ALMACEN_CENTRAL]
    destino = ids[0]
    id_movimiento = _nuevo_movimiento(
        conn, tipo="entrada", referencia=referencia, id_usuario=id_usuario
    )
    for item in lista:
        id_producto = int(item["id_producto"])
        cantidad = float(item["cantidad"])
        if cantidad <= 0:
            continue
        _asegurar_fila_stock(conn, id_producto, destino)
        conn.execute(
            """
            UPDATE stock_almacen SET cantidad_disponible = cantidad_disponible + ?
            WHERE id_producto = ? AND id_almacen = ?
            """,
            [cantidad, id_producto, destino],
        )
        _registrar_detalle(
            conn,
            id_movimiento=id_movimiento,
            id_producto=id_producto,
            id_almacen=destino,
            cantidad=cantidad,
        )


def transferir(
    conn: duckdb.DuckDBPyConnection,
    *,
    id_producto: int,
    id_almacen_origen: int,
    id_almacen_destino: int,
    cantidad: float,
    id_usuario: Optional[int] = None,
    referencia: Optional[str] = None,
) -> dict[str, Any]:
    """Traslado entre bodegas: descuenta en origen, suma en destino, deja rastro."""
    if int(id_almacen_origen) == int(id_almacen_destino):
        raise ValueError("La bodega de origen y destino deben ser distintas.")
    cantidad = float(cantidad)
    if cantidad <= 0:
        raise ValueError("La cantidad a transferir debe ser mayor a 0.")

    disponible = stock_zona(conn, id_producto, [id_almacen_origen])
    if disponible < cantidad:
        raise ValueError(f"La bodega de origen solo tiene {disponible:g} unidades.")

    ref = referencia or f"TRF-{int(id_almacen_origen)}-{int(id_almacen_destino)}"
    id_movimiento = _nuevo_movimiento(
        conn, tipo="transferencia", referencia=ref, id_usuario=id_usuario
    )
    conn.execute(
        """
        UPDATE stock_almacen SET cantidad_disponible = cantidad_disponible - ?
        WHERE id_producto = ? AND id_almacen = ?
        """,
        [cantidad, int(id_producto), int(id_almacen_origen)],
    )
    _registrar_detalle(
        conn,
        id_movimiento=id_movimiento,
        id_producto=id_producto,
        id_almacen=int(id_almacen_origen),
        cantidad=-cantidad,
    )
    _asegurar_fila_stock(conn, id_producto, int(id_almacen_destino))
    conn.execute(
        """
        UPDATE stock_almacen SET cantidad_disponible = cantidad_disponible + ?
        WHERE id_producto = ? AND id_almacen = ?
        """,
        [cantidad, int(id_producto), int(id_almacen_destino)],
    )
    _registrar_detalle(
        conn,
        id_movimiento=id_movimiento,
        id_producto=id_producto,
        id_almacen=int(id_almacen_destino),
        cantidad=cantidad,
    )

    if table_exists(conn, "transferencias_almacen"):
        conn.execute(
            """
            INSERT INTO transferencias_almacen (id_transferencia, id_almacen_origen, id_almacen_destino, fecha, estado)
            VALUES ((SELECT COALESCE(MAX(id_transferencia), 0) + 1 FROM transferencias_almacen), ?, ?, current_timestamp, 'completada')
            """,
            [int(id_almacen_origen), int(id_almacen_destino)],
        )

    return {
        "id_movimiento": id_movimiento,
        "id_producto": int(id_producto),
        "id_almacen_origen": int(id_almacen_origen),
        "id_almacen_destino": int(id_almacen_destino),
        "cantidad": cantidad,
    }
