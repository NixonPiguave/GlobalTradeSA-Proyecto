"""Carga precios demo en listas Público/Mayorista y asigna clientes B2B."""

from __future__ import annotations

import duckdb


def seed_listas_precios(conn: duckdb.DuckDBPyConnection) -> str:
    id_publico = conn.execute(
        "SELECT id_lista FROM listas_precios WHERE nombre = 'Público' LIMIT 1"
    ).fetchone()
    id_mayor = conn.execute(
        "SELECT id_lista FROM listas_precios WHERE nombre = 'Mayorista' LIMIT 1"
    ).fetchone()
    if not id_publico or not id_mayor:
        return "omitido: faltan listas Público/Mayorista"

    id_publico, id_mayor = int(id_publico[0]), int(id_mayor[0])
    productos = conn.execute(
        """
        SELECT id_producto,
               CAST(COALESCE(precio_unitario, 0) AS DOUBLE),
               CAST(COALESCE(precio_mayorista, 0) AS DOUBLE)
        FROM dim_producto
        WHERE COALESCE(activo, true) = true
        ORDER BY id_producto
        LIMIT 80
        """
    ).fetchall()

    n = 0
    for pid, pu, pm in productos:
        pu, pm = float(pu or 0), float(pm or 0)
        if pu <= 0 and pm <= 0:
            continue
        precio_publico = round(pu if pu > 0 else pm * 1.15, 2)
        precio_mayor = round(pm if pm > 0 else pu * 0.85, 2)
        for id_lista, precio in (
            (id_publico, precio_publico),
            (id_mayor, precio_mayor),
        ):
            ex = conn.execute(
                "SELECT id_detalle FROM lista_precio_detalle WHERE id_lista = ? AND id_producto = ?",
                [id_lista, pid],
            ).fetchone()
            if ex:
                conn.execute(
                    "UPDATE lista_precio_detalle SET precio = ?, cantidad_minima = 1 WHERE id_detalle = ?",
                    [precio, int(ex[0])],
                )
            else:
                conn.execute(
                    """
                    INSERT INTO lista_precio_detalle (id_detalle, id_lista, id_producto, precio, cantidad_minima)
                    VALUES (
                      (SELECT COALESCE(MAX(id_detalle), 0) + 1 FROM lista_precio_detalle),
                      ?, ?, ?, ?
                    )
                    """,
                    [id_lista, pid, precio, 1],
                )
            n += 1

    grupos = [
        ("Grandes cadenas (Mayorista)", id_mayor),
        ("Compras ocasionales (Público)", id_publico),
    ]
    grupo_ids: dict[str, int] = {}
    for nombre, id_lista in grupos:
        row = conn.execute(
            "SELECT id_grupo FROM grupos_cliente WHERE nombre = ?", [nombre]
        ).fetchone()
        if row:
            gid = int(row[0])
            conn.execute(
                "UPDATE grupos_cliente SET id_lista = ? WHERE id_grupo = ?", [id_lista, gid]
            )
        else:
            conn.execute(
                """
                INSERT INTO grupos_cliente (id_grupo, nombre, id_lista)
                VALUES (
                  (SELECT COALESCE(MAX(id_grupo), 0) + 1 FROM grupos_cliente),
                  ?, ?
                )
                """,
                [nombre, id_lista],
            )
            gid = int(
                conn.execute(
                    "SELECT id_grupo FROM grupos_cliente WHERE nombre = ?", [nombre]
                ).fetchone()[0]
            )
        grupo_ids[nombre] = gid

    asignados = 0
    for email, grupo_nombre in [
        ("compras@walmart.com", "Grandes cadenas (Mayorista)"),
        ("procurement@carrefour.com", "Grandes cadenas (Mayorista)"),
        ("sourcing@costco.com", "Grandes cadenas (Mayorista)"),
    ]:
        row = conn.execute(
            """
            SELECT dc.id_cliente FROM dim_cliente dc
            JOIN usuarios u ON u.id_usuario = dc.id_usuario
            WHERE u.email = ?
            """,
            [email],
        ).fetchone()
        if not row:
            continue
        id_cliente = int(row[0])
        id_grupo = grupo_ids[grupo_nombre]
        conn.execute("DELETE FROM cliente_grupo WHERE id_cliente = ?", [id_cliente])
        conn.execute(
            "INSERT INTO cliente_grupo (id_cliente, id_grupo) VALUES (?, ?)",
            [id_cliente, id_grupo],
        )
        asignados += 1

    return f"{len(productos)} productos × 2 listas ({n} filas), {asignados} clientes en Mayorista"
