"""
services/inventario_service.py — Stock por almacén, movimientos, ajustes y alertas.

Reglas:
- El stock disponible nunca queda negativo (ValueError si el ajuste lo violaría).
- Todo cambio de stock registra un movimiento + detalle.
"""

from __future__ import annotations

from typing import Any, Optional

import duckdb

from shared.database.connection import table_exists
from shared.database.ids import siguiente_id
from shared.services import red_bodegas

ALMACEN_CENTRAL = red_bodegas.ALMACEN_CENTRAL


def _asegurar_stock_row(conn: duckdb.DuckDBPyConnection, id_producto: int, id_almacen: int) -> None:
    existe = conn.execute(
        "SELECT 1 FROM stock_almacen WHERE id_producto = ? AND id_almacen = ?",
        [id_producto, id_almacen],
    ).fetchone()
    if not existe:
        conn.execute(
            """
            INSERT INTO stock_almacen (id_stock, id_producto, id_almacen, cantidad_disponible, cantidad_reservada)
            VALUES ((SELECT COALESCE(MAX(id_stock), 0) + 1 FROM stock_almacen), ?, ?, 0, 0)
            """,
            [id_producto, id_almacen],
        )


def obtener_stock(conn: duckdb.DuckDBPyConnection, id_producto: int, id_almacen: int = ALMACEN_CENTRAL) -> dict[str, Any]:
    r = conn.execute(
        """
        SELECT CAST(COALESCE(cantidad_disponible, 0) AS DOUBLE),
               CAST(COALESCE(cantidad_reservada, 0) AS DOUBLE)
        FROM stock_almacen WHERE id_producto = ? AND id_almacen = ?
        """,
        [id_producto, id_almacen],
    ).fetchone()
    disponible = float(r[0]) if r else 0.0
    reservada = float(r[1]) if r else 0.0
    return {"id_producto": id_producto, "id_almacen": id_almacen, "disponible": disponible, "reservada": reservada}


def _registrar_movimiento(
    conn: duckdb.DuckDBPyConnection,
    *,
    tipo: str,
    referencia: str,
    id_usuario: Optional[int],
    detalles: list[tuple[int, int, float]],  # (id_producto, id_almacen, cantidad +/-)
) -> int:
    id_movimiento = siguiente_id(conn, "movimientos_inventario")
    conn.execute(
        """
        INSERT INTO movimientos_inventario (id_movimiento, tipo, referencia, id_usuario)
        VALUES (?, ?, ?, ?)
        """,
        [id_movimiento, tipo, referencia, id_usuario],
    )
    for id_producto, id_almacen, cantidad in detalles:
        conn.execute(
            """
            INSERT INTO movimiento_inventario_detalle (id_detalle, id_movimiento, id_producto, id_almacen, id_lote, cantidad)
            VALUES ((SELECT COALESCE(MAX(id_detalle), 0) + 1 FROM movimiento_inventario_detalle), ?, ?, ?, NULL, ?)
            """,
            [id_movimiento, id_producto, id_almacen, cantidad],
        )
    return id_movimiento


def modificar_stock(
    conn: duckdb.DuckDBPyConnection,
    *,
    id_producto: int,
    cantidad: float,
    tipo: str,
    referencia: str,
    id_usuario: Optional[int] = None,
    id_almacen: int = ALMACEN_CENTRAL,
) -> dict[str, Any]:
    """Suma (cantidad > 0) o descuenta (cantidad < 0) stock disponible de forma atómica.

    Lanza ValueError si el resultado sería negativo. Debe llamarse dentro de
    una transacción del caller o como operación única.
    """
    _asegurar_stock_row(conn, id_producto, id_almacen)
    actual = obtener_stock(conn, id_producto, id_almacen)
    nuevo = actual["disponible"] + cantidad
    if nuevo < 0:
        raise ValueError(
            f"Stock insuficiente para el producto {id_producto}: disponible {actual['disponible']}, se requiere {abs(cantidad)}."
        )
    conn.execute(
        "UPDATE stock_almacen SET cantidad_disponible = ? WHERE id_producto = ? AND id_almacen = ?",
        [nuevo, id_producto, id_almacen],
    )
    _registrar_movimiento(
        conn,
        tipo=tipo,
        referencia=referencia,
        id_usuario=id_usuario,
        detalles=[(id_producto, id_almacen, cantidad)],
    )
    return obtener_stock(conn, id_producto, id_almacen)


def ajustar_stock(
    conn: duckdb.DuckDBPyConnection,
    *,
    id_producto: int,
    cantidad: float,
    motivo: str,
    id_usuario: Optional[int],
    id_almacen: int = ALMACEN_CENTRAL,
) -> dict[str, Any]:
    conn.execute("BEGIN TRANSACTION")
    try:
        resultado = modificar_stock(
            conn,
            id_producto=id_producto,
            cantidad=cantidad,
            tipo="ajuste",
            referencia=motivo,
            id_usuario=id_usuario,
            id_almacen=id_almacen,
        )
        conn.execute("COMMIT")
        return resultado
    except Exception:
        conn.execute("ROLLBACK")
        raise


def listar_stock(
    conn: duckdb.DuckDBPyConnection,
    *,
    solo_bajo: bool = False,
    q: Optional[str] = None,
    id_almacen: Optional[int] = None,
    macro_zona: Optional[str] = None,
) -> list[dict[str, Any]]:
    """Inventario por producto: total de la red y desglose por macro-zona.

    `id_almacen` restringe a una bodega concreta; `macro_zona` a una región
    operativa. Sin filtros muestra la red completa, que es la lectura que
    necesita el ERP para decidir reposiciones y transferencias.
    """
    where: list[str] = ["p.activo = true"]
    params: list[Any] = []
    if q:
        where.append("lower(p.nombre_producto) LIKE ?")
        params.append(f"%{q.lower()}%")

    filtro_stock = ""
    if id_almacen is not None:
        filtro_stock = f" AND sa.id_almacen = {int(id_almacen)}"
    elif macro_zona in red_bodegas.MACROS:
        ids = red_bodegas.bodegas_de_macro(conn, macro_zona)
        filtro_stock = red_bodegas.sql_filtro_almacenes(ids) if ids else " AND 1 = 0"

    def stock_zona_sql(macro: str) -> str:
        ids = red_bodegas.bodegas_de_macro(conn, macro)
        if not ids:
            return "0"
        return (
            "COALESCE((SELECT SUM(z.cantidad_disponible) FROM stock_almacen z "
            f"WHERE z.id_producto = p.id_producto{red_bodegas.sql_filtro_almacenes(ids, 'z')}), 0)"
        )

    rows = conn.execute(
        f"""
        SELECT p.id_producto, p.nombre_producto, it.item_type,
               CAST(COALESCE((
                 SELECT SUM(sa.cantidad_disponible) FROM stock_almacen sa
                 WHERE sa.id_producto = p.id_producto{filtro_stock}
               ), 0) AS DOUBLE) AS disponible,
               CAST(COALESCE((
                 SELECT SUM(sa.cantidad_reservada) FROM stock_almacen sa
                 WHERE sa.id_producto = p.id_producto{filtro_stock}
               ), 0) AS DOUBLE) AS reservada,
               CAST(COALESCE(p.stock_minimo, COALESCE((
                 SELECT al.umbral_minimo FROM alertas_stock al
                 WHERE al.id_producto = p.id_producto AND al.activa = true LIMIT 1
               ), 0)) AS DOUBLE) AS umbral,
               CAST({stock_zona_sql('americas')} AS DOUBLE) AS stock_americas,
               CAST({stock_zona_sql('emea')} AS DOUBLE) AS stock_emea,
               CAST({stock_zona_sql('apac')} AS DOUBLE) AS stock_apac
        FROM dim_producto p
        JOIN dim_item_type it ON it.id_item_type = p.id_item_type
        WHERE {' AND '.join(where)}
        ORDER BY p.nombre_producto
        """,
        params,
    ).fetchall()

    items = []
    for r in rows:
        disponible = float(r[3])
        umbral = float(r[5])
        zonas = {
            "americas": float(r[6]),
            "emea": float(r[7]),
            "apac": float(r[8]),
        }
        items.append(
            {
                "id_producto": int(r[0]),
                "nombre_producto": r[1],
                "categoria": r[2],
                "disponible": disponible,
                "reservada": float(r[4]),
                "umbral_minimo": umbral,
                "bajo_stock": umbral > 0 and disponible <= umbral,
                "stock_americas": zonas["americas"],
                "stock_emea": zonas["emea"],
                "stock_apac": zonas["apac"],
                "zonas_agotadas": [
                    red_bodegas.MACRO_LABELS[z] for z, v in zonas.items() if v <= 0
                ],
            }
        )
    if solo_bajo:
        items = [i for i in items if i["bajo_stock"] or i["zonas_agotadas"]]
    return items


def listar_movimientos(
    conn: duckdb.DuckDBPyConnection, *, limit: int = 100, id_producto: Optional[int] = None
) -> list[dict[str, Any]]:
    limit = max(1, min(limit, 500))
    where = ""
    params: list[Any] = []
    if id_producto is not None:
        where = "WHERE d.id_producto = ?"
        params.append(id_producto)
    rows = conn.execute(
        f"""
        SELECT m.id_movimiento, m.tipo, m.fecha, m.referencia, u.email,
               d.id_producto, p.nombre_producto, CAST(d.cantidad AS DOUBLE)
        FROM movimientos_inventario m
        LEFT JOIN usuarios u ON u.id_usuario = m.id_usuario
        LEFT JOIN movimiento_inventario_detalle d ON d.id_movimiento = m.id_movimiento
        LEFT JOIN dim_producto p ON p.id_producto = d.id_producto
        {where}
        ORDER BY m.id_movimiento DESC
        LIMIT ?
        """,
        params + [limit],
    ).fetchall()
    return [
        {
            "id_movimiento": int(r[0]),
            "tipo": r[1],
            "fecha": str(r[2]) if r[2] is not None else None,
            "referencia": r[3],
            "usuario": r[4],
            "id_producto": int(r[5]) if r[5] is not None else None,
            "producto": r[6],
            "cantidad": float(r[7]) if r[7] is not None else None,
        }
        for r in rows
    ]


def fijar_alerta(
    conn: duckdb.DuckDBPyConnection,
    *,
    id_producto: int,
    umbral_minimo: float,
    id_almacen: int = ALMACEN_CENTRAL,
) -> dict[str, Any]:
    existente = conn.execute(
        "SELECT id_alerta FROM alertas_stock WHERE id_producto = ? AND id_almacen = ?",
        [id_producto, id_almacen],
    ).fetchone()
    if existente:
        conn.execute(
            "UPDATE alertas_stock SET umbral_minimo = ?, activa = true WHERE id_alerta = ?",
            [umbral_minimo, int(existente[0])],
        )
        id_alerta = int(existente[0])
    else:
        conn.execute(
            """
            INSERT INTO alertas_stock (id_alerta, id_producto, id_almacen, umbral_minimo, activa)
            VALUES ((SELECT COALESCE(MAX(id_alerta), 0) + 1 FROM alertas_stock), ?, ?, ?, true)
            RETURNING id_alerta
            """,
            [id_producto, id_almacen, umbral_minimo],
        )
        id_alerta = int(conn.fetchone()[0])
    try:
        conn.execute(
            "UPDATE dim_producto SET stock_minimo = ? WHERE id_producto = ?",
            [umbral_minimo, id_producto],
        )
    except Exception:
        pass
    try:
        from shared.services import notificacion_service as ns
        nombre = conn.execute(
            "SELECT nombre_producto FROM dim_producto WHERE id_producto = ?", [id_producto]
        ).fetchone()
        ns.notificar_staff_con_permiso(
            conn,
            permiso="mod.inventario",
            titulo="Stock mínimo configurado",
            cuerpo=f"{nombre[0] if nombre else id_producto}: umbral {umbral_minimo:g}",
            link="/?page=inventario",
            tipo="stock",
        )
        if table_exists(conn, "wishlist"):
            favs = conn.execute(
                "SELECT DISTINCT id_usuario FROM wishlist WHERE id_producto = ?",
                [id_producto],
            ).fetchall()
            for (uid,) in favs:
                prefs_row = conn.execute(
                    """
                    SELECT preferencias_json FROM cliente_preferencias cp
                    JOIN dim_cliente c ON c.id_cliente = cp.id_cliente
                    WHERE c.id_usuario = ?
                    """,
                    [int(uid)],
                ).fetchone()
                allow = False
                if prefs_row and prefs_row[0]:
                    try:
                        import json
                        data = json.loads(prefs_row[0]) if isinstance(prefs_row[0], str) else dict(prefs_row[0])
                        allow = bool(data.get("notif_stock", False))
                    except Exception:
                        allow = False
                if allow:
                    ns.crear(
                        conn,
                        id_usuario=int(uid),
                        titulo="Alerta de stock en favoritos",
                        cuerpo=f"{nombre[0] if nombre else id_producto}: umbral mínimo {umbral_minimo:g}",
                        tipo="stock",
                        link="/pages/favoritos.html",
                    )
    except Exception:
        pass
    return {"id_alerta": id_alerta, "id_producto": id_producto, "id_almacen": id_almacen, "umbral_minimo": umbral_minimo}


def panorama_red(conn: duckdb.DuckDBPyConnection) -> dict[str, Any]:
    """Estado de la red de distribución: bodegas por zona, cobertura y huecos."""
    bodegas = red_bodegas.listar_bodegas_red(conn, activas_only=False)
    total_productos = int(
        conn.execute("SELECT COUNT(*) FROM dim_producto WHERE activo = true").fetchone()[0]
    )

    detalle = []
    for b in bodegas:
        fila = conn.execute(
            """
            SELECT CAST(COALESCE(SUM(sa.cantidad_disponible), 0) AS DOUBLE),
                   COUNT(*) FILTER (WHERE sa.cantidad_disponible > 0)
            FROM stock_almacen sa
            JOIN dim_producto p ON p.id_producto = sa.id_producto AND p.activo = true
            WHERE sa.id_almacen = ?
            """,
            [b["id_almacen"]],
        ).fetchone()
        unidades = float(fila[0] or 0)
        skus = int(fila[1] or 0)
        detalle.append(
            {
                **b,
                "unidades": unidades,
                "skus_con_stock": skus,
                "cobertura_pct": round(skus / total_productos * 100, 1) if total_productos else 0.0,
                "vacia": unidades <= 0,
            }
        )

    zonas = []
    for macro in red_bodegas.MACROS:
        de_zona = [d for d in detalle if d["macro_zona"] == macro and d["activo"]]
        ids = [d["id_almacen"] for d in de_zona]
        agotados = 0
        if ids:
            agotados = int(
                conn.execute(
                    f"""
                    SELECT COUNT(*) FROM dim_producto p
                    WHERE p.activo = true
                      AND COALESCE((SELECT SUM(sa.cantidad_disponible) FROM stock_almacen sa
                                    WHERE sa.id_producto = p.id_producto
                                    {red_bodegas.sql_filtro_almacenes(ids)}), 0) <= 0
                    """
                ).fetchone()[0]
            )
        else:
            agotados = total_productos
        zonas.append(
            {
                "macro_zona": macro,
                "macro_label": red_bodegas.MACRO_LABELS[macro],
                "n_bodegas": len(de_zona),
                "unidades": round(sum(d["unidades"] for d in de_zona), 2),
                "productos_agotados": agotados,
                "cobertura_pct": round((total_productos - agotados) / total_productos * 100, 1)
                if total_productos
                else 0.0,
            }
        )

    return {
        "total_productos": total_productos,
        "bodegas": detalle,
        "zonas": zonas,
        "cross_zona": red_bodegas.cross_zona_habilitado(conn),
        "bodegas_vacias": [d["nombre"] for d in detalle if d["vacia"] and d["activo"]],
    }


def transferir_stock(
    conn: duckdb.DuckDBPyConnection,
    *,
    id_producto: int,
    id_almacen_origen: int,
    id_almacen_destino: int,
    cantidad: float,
    id_usuario: Optional[int] = None,
) -> dict[str, Any]:
    """Traslada unidades entre bodegas y avisa a inventario del movimiento."""
    conn.execute("BEGIN TRANSACTION")
    try:
        resultado = red_bodegas.transferir(
            conn,
            id_producto=id_producto,
            id_almacen_origen=id_almacen_origen,
            id_almacen_destino=id_almacen_destino,
            cantidad=cantidad,
            id_usuario=id_usuario,
        )
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise

    try:
        from shared.services import notificacion_service as ns

        nombres = conn.execute(
            """
            SELECT (SELECT nombre_producto FROM dim_producto WHERE id_producto = ?),
                   (SELECT nombre FROM almacenes WHERE id_almacen = ?),
                   (SELECT nombre FROM almacenes WHERE id_almacen = ?)
            """,
            [id_producto, id_almacen_origen, id_almacen_destino],
        ).fetchone()
        ns.notificar_staff_con_permiso(
            conn,
            permiso="mod.inventario",
            titulo="Transferencia entre bodegas",
            cuerpo=f"{nombres[0]}: {cantidad:g} u. de {nombres[1]} a {nombres[2]}.",
            link="/?page=inventario",
            tipo="logistica",
        )
    except Exception:
        pass
    return resultado


def reabastecer_red(
    conn: duckdb.DuckDBPyConnection,
    *,
    id_usuario: Optional[int] = None,
    solo_vacias: bool = True,
) -> dict[str, Any]:
    """Surte las bodegas que no alcanzan su objetivo de inventario.

    Genera una entrada de inventario (reposición del proveedor al hub o
    satélite), no una transferencia: el objetivo es que ninguna zona quede
    sin poder atender a sus clientes.
    """
    from shared.services.config_service import obtener_config_int

    objetivo_hub = float(obtener_config_int(conn, "STOCK_OBJETIVO_HUB", 600))
    objetivo_sat = float(obtener_config_int(conn, "STOCK_OBJETIVO_SATELITE", 150))

    bodegas = red_bodegas.listar_bodegas_red(conn)
    productos = [
        int(r[0])
        for r in conn.execute("SELECT id_producto FROM dim_producto WHERE activo = true").fetchall()
    ]
    if not bodegas or not productos:
        return {"lineas": 0, "unidades": 0.0, "bodegas": 0}

    lineas = 0
    unidades = 0.0
    bodegas_tocadas: set[int] = set()

    conn.execute("BEGIN TRANSACTION")
    try:
        for b in bodegas:
            objetivo = objetivo_hub if b["es_hub"] else objetivo_sat
            actuales = {
                int(r[0]): float(r[1] or 0)
                for r in conn.execute(
                    "SELECT id_producto, cantidad_disponible FROM stock_almacen WHERE id_almacen = ?",
                    [b["id_almacen"]],
                ).fetchall()
            }
            for id_producto in productos:
                actual = actuales.get(id_producto, 0.0)
                if solo_vacias and actual > 0:
                    continue
                if actual >= objetivo:
                    continue
                falta = objetivo - actual
                modificar_stock(
                    conn,
                    id_producto=id_producto,
                    cantidad=falta,
                    tipo="entrada",
                    referencia=f"Reabastecimiento red — {b['nombre']}",
                    id_usuario=id_usuario,
                    id_almacen=b["id_almacen"],
                )
                lineas += 1
                unidades += falta
                bodegas_tocadas.add(b["id_almacen"])
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise

    if lineas:
        try:
            from shared.services import notificacion_service as ns

            ns.notificar_staff_con_permiso(
                conn,
                permiso="mod.inventario",
                titulo="Red de bodegas reabastecida",
                cuerpo=f"{lineas} líneas y {unidades:g} unidades repartidas en {len(bodegas_tocadas)} bodegas.",
                link="/?page=inventario",
                tipo="stock",
            )
        except Exception:
            pass
    return {"lineas": lineas, "unidades": round(unidades, 2), "bodegas": len(bodegas_tocadas)}


def stock_producto_por_bodega(
    conn: duckdb.DuckDBPyConnection, id_producto: int
) -> dict[str, Any]:
    """Desglose de un producto bodega por bodega, con su zona."""
    nombre = conn.execute(
        "SELECT nombre_producto FROM dim_producto WHERE id_producto = ?", [id_producto]
    ).fetchone()
    return {
        "id_producto": id_producto,
        "producto": nombre[0] if nombre else None,
        "bodegas": red_bodegas.desglose_stock_producto(conn, id_producto),
        "por_zona": red_bodegas.resumen_por_zona(conn, id_producto),
    }


def alertas_activas(conn: duckdb.DuckDBPyConnection) -> list[dict[str, Any]]:
    rows = conn.execute(
        f"""
        SELECT a.id_alerta, a.id_producto, p.nombre_producto,
               CAST(a.umbral_minimo AS DOUBLE),
               CAST(COALESCE(sa.cantidad_disponible, 0) AS DOUBLE) AS disponible
        FROM alertas_stock a
        JOIN dim_producto p ON p.id_producto = a.id_producto
        LEFT JOIN stock_almacen sa ON sa.id_producto = a.id_producto AND sa.id_almacen = a.id_almacen
        WHERE a.activa = true
          AND COALESCE(sa.cantidad_disponible, 0) <= a.umbral_minimo
        ORDER BY disponible ASC
        """
    ).fetchall()
    return [
        {
            "id_alerta": int(r[0]),
            "id_producto": int(r[1]),
            "producto": r[2],
            "umbral_minimo": float(r[3]),
            "disponible": float(r[4]),
        }
        for r in rows
    ]
