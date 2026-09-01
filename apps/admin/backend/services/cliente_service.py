"""
services/cliente_service.py — Clientes B2B y cuenta corriente (CxC) para el panel.
"""

from __future__ import annotations

from typing import Any, Optional

import duckdb


from shared.database.connection import table_exists


def _tablas_grupo_ok(conn: duckdb.DuckDBPyConnection) -> bool:
    return table_exists(conn, "grupos_cliente") and table_exists(conn, "cliente_grupo")


def _info_grupo_cliente(conn: duckdb.DuckDBPyConnection, id_cliente: int) -> dict[str, Any]:
    if not _tablas_grupo_ok(conn):
        return {"id_grupo": None, "grupo": None, "id_lista": None, "lista_precio": "Público"}
    row = conn.execute(
        """
        SELECT g.id_grupo, g.nombre, g.id_lista, lp.nombre
        FROM cliente_grupo cg
        JOIN grupos_cliente g ON g.id_grupo = cg.id_grupo
        LEFT JOIN listas_precios lp ON lp.id_lista = g.id_lista
        WHERE cg.id_cliente = ?
        LIMIT 1
        """,
        [id_cliente],
    ).fetchone()
    if not row:
        publico = conn.execute(
            "SELECT id_lista, nombre FROM listas_precios WHERE lower(nombre) = 'público' LIMIT 1"
        ).fetchone()
        return {
            "id_grupo": None,
            "grupo": None,
            "id_lista": int(publico[0]) if publico else None,
            "lista_precio": publico[1] if publico else "Público",
        }
    return {
        "id_grupo": int(row[0]),
        "grupo": row[1],
        "id_lista": int(row[2]) if row[2] is not None else None,
        "lista_precio": row[3] or "Público",
    }


def listar_grupos_cliente(conn: duckdb.DuckDBPyConnection) -> list[dict[str, Any]]:
    if not table_exists(conn, "grupos_cliente"):
        return []
    rows = conn.execute(
        """
        SELECT g.id_grupo, g.nombre, g.id_lista, lp.nombre
        FROM grupos_cliente g
        LEFT JOIN listas_precios lp ON lp.id_lista = g.id_lista
        ORDER BY g.nombre
        """
    ).fetchall()
    return [
        {
            "id_grupo": int(r[0]),
            "nombre": r[1],
            "id_lista": int(r[2]) if r[2] is not None else None,
            "lista_precio": r[3],
        }
        for r in rows
    ]


def asignar_grupo_cliente(
    conn: duckdb.DuckDBPyConnection,
    id_cliente: int,
    *,
    id_grupo: Optional[int],
) -> Optional[dict[str, Any]]:
    existe = conn.execute(
        "SELECT 1 FROM dim_cliente WHERE id_cliente = ?", [id_cliente]
    ).fetchone()
    if not existe:
        return None
    if not _tablas_grupo_ok(conn):
        raise ValueError("Las tablas de grupos de cliente no están disponibles.")

    conn.execute("DELETE FROM cliente_grupo WHERE id_cliente = ?", [id_cliente])
    if id_grupo is not None:
        grupo = conn.execute(
            "SELECT id_grupo FROM grupos_cliente WHERE id_grupo = ?", [int(id_grupo)]
        ).fetchone()
        if not grupo:
            raise ValueError("El grupo comercial seleccionado no existe.")
        conn.execute(
            "INSERT INTO cliente_grupo (id_cliente, id_grupo) VALUES (?, ?)",
            [id_cliente, int(id_grupo)],
        )
    return obtener_cliente(conn, id_cliente)


def listar_clientes(conn: duckdb.DuckDBPyConnection, *, q: Optional[str] = None) -> list[dict[str, Any]]:
    where = ""
    params: list[Any] = []
    if q:
        where = "WHERE lower(c.nombre_empresa) LIKE ? OR lower(u.email) LIKE ?"
        params = [f"%{q.lower()}%", f"%{q.lower()}%"]
    rows = conn.execute(
        f"""
        SELECT c.id_cliente, c.nombre_empresa, c.pais, c.telefono, u.email, u.activo,
               (SELECT COUNT(*) FROM pedidos p WHERE p.id_cliente = c.id_cliente) AS n_pedidos,
               (SELECT CAST(COALESCE(SUM(COALESCE(p.total, p.total_pedido, 0)), 0) AS DOUBLE)
                  FROM pedidos p WHERE p.id_cliente = c.id_cliente AND p.estado NOT IN ('cancelado', 'borrador')) AS total_comprado,
               g.id_grupo, g.nombre, lp.nombre
        FROM dim_cliente c
        LEFT JOIN usuarios u ON u.id_usuario = c.id_usuario
        LEFT JOIN cliente_grupo cg ON cg.id_cliente = c.id_cliente
        LEFT JOIN grupos_cliente g ON g.id_grupo = cg.id_grupo
        LEFT JOIN listas_precios lp ON lp.id_lista = g.id_lista
        {where}
        ORDER BY c.nombre_empresa
        """,
        params,
    ).fetchall()
    return [
        {
            "id_cliente": int(r[0]),
            "nombre_empresa": r[1],
            "pais": r[2],
            "telefono": r[3],
            "email": r[4],
            "activo": bool(r[5]) if r[5] is not None else False,
            "n_pedidos": int(r[6]),
            "total_comprado": float(r[7]),
            "id_grupo": int(r[8]) if r[8] is not None else None,
            "grupo": r[9],
            "lista_precio": r[10] or "Público",
        }
        for r in rows
    ]


def obtener_cliente(conn: duckdb.DuckDBPyConnection, id_cliente: int) -> Optional[dict[str, Any]]:
    r = conn.execute(
        """
        SELECT c.id_cliente, c.id_usuario, c.nombre_empresa, c.pais, c.telefono, c.direccion, u.email, u.activo, u.fecha_registro
        FROM dim_cliente c
        LEFT JOIN usuarios u ON u.id_usuario = c.id_usuario
        WHERE c.id_cliente = ?
        """,
        [id_cliente],
    ).fetchone()
    if not r:
        return None

    pedidos = conn.execute(
        """
        SELECT p.id_pedido, p.numero, p.fecha_pedido, p.estado, CAST(COALESCE(p.total, p.total_pedido, 0) AS DOUBLE)
        FROM pedidos p WHERE p.id_cliente = ? ORDER BY p.id_pedido DESC LIMIT 50
        """,
        [id_cliente],
    ).fetchall()

    # CxC: total facturado (pedidos no cancelados) - total pagado (pagos aprobados)
    facturado = float(
        conn.execute(
            """
            SELECT CAST(COALESCE(SUM(COALESCE(total, total_pedido, 0)), 0) AS DOUBLE)
            FROM pedidos WHERE id_cliente = ? AND estado NOT IN ('cancelado', 'borrador', 'pendiente_pago')
            """,
            [id_cliente],
        ).fetchone()[0]
    )
    pagado = float(
        conn.execute(
            """
            SELECT CAST(COALESCE(SUM(pg.monto), 0) AS DOUBLE)
            FROM pagos pg JOIN pedidos p ON p.id_pedido = pg.id_pedido
            WHERE p.id_cliente = ? AND pg.estado = 'aprobado'
            """,
            [id_cliente],
        ).fetchone()[0]
    )

    return {
        "id_cliente": int(r[0]),
        "id_usuario": int(r[1]) if r[1] is not None else None,
        "nombre_empresa": r[2],
        "pais": r[3],
        "telefono": r[4],
        "direccion": r[5],
        "email": r[6],
        "activo": bool(r[7]) if r[7] is not None else False,
        "fecha_registro": str(r[8]) if r[8] is not None else None,
        **_info_grupo_cliente(conn, id_cliente),
        "pedidos": [
            {
                "id_pedido": int(p[0]),
                "numero": p[1],
                "fecha": str(p[2]) if p[2] is not None else None,
                "estado": p[3],
                "total": float(p[4]),
            }
            for p in pedidos
        ],
        "cxc": {
            "facturado": round(facturado, 2),
            "pagado": round(pagado, 2),
            "saldo": round(facturado - pagado, 2),
        },
    }


def activar_desactivar_cliente(
    conn: duckdb.DuckDBPyConnection, id_cliente: int, activo: bool
) -> bool:
    cliente = conn.execute(
        "SELECT id_usuario FROM dim_cliente WHERE id_cliente = ?", [id_cliente]
    ).fetchone()
    if not cliente or cliente[0] is None:
        return False
    conn.execute("UPDATE usuarios SET activo = ? WHERE id_usuario = ?", [activo, int(cliente[0])])
    return True


def actualizar_cliente(
    conn: duckdb.DuckDBPyConnection,
    id_cliente: int,
    *,
    nombre_empresa: str,
    pais: str,
    telefono: Optional[str],
    direccion: Optional[str],
) -> Optional[dict[str, Any]]:
    existe = conn.execute(
        "SELECT 1 FROM dim_cliente WHERE id_cliente = ?", [id_cliente]
    ).fetchone()
    if not existe:
        return None
    valido = conn.execute(
        "SELECT 1 FROM dim_country WHERE country IS NOT NULL AND lower(country) = lower(?)",
        [pais],
    ).fetchone()
    if not valido:
        raise ValueError("El país no es válido. Selecciona un país de la lista.")
    conn.execute(
        """
        UPDATE dim_cliente
        SET nombre_empresa = ?, pais = ?, telefono = ?, direccion = ?
        WHERE id_cliente = ?
        """,
        [nombre_empresa, pais, telefono, direccion, id_cliente],
    )
    return obtener_cliente(conn, id_cliente)
