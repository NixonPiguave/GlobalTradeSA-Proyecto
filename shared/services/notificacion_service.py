"""notificacion_service.py — Campana de avisos ERP / portal."""

from __future__ import annotations

import json
from typing import Any, Optional, Sequence

import duckdb


def _next_id(conn: duckdb.DuckDBPyConnection) -> int:
    row = conn.execute("SELECT COALESCE(MAX(id_notif), 0) + 1 FROM notificaciones").fetchone()
    return int(row[0])


def asegurar_tabla(conn: duckdb.DuckDBPyConnection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS notificaciones (
          id_notif BIGINT PRIMARY KEY,
          id_usuario BIGINT NOT NULL,
          titulo VARCHAR NOT NULL,
          cuerpo VARCHAR,
          tipo VARCHAR DEFAULT 'info',
          link VARCHAR,
          leida BOOLEAN DEFAULT false,
          fecha TIMESTAMP DEFAULT current_timestamp
        )
        """
    )


def _existe_reciente_usuario(
    conn: duckdb.DuckDBPyConnection,
    *,
    id_usuario: int,
    titulo: str,
    cuerpo: str = "",
    horas: int = 12,
) -> bool:
    """Evita duplicar el mismo aviso para un usuario en la ventana indicada."""
    row = conn.execute(
        """
        SELECT 1 FROM notificaciones
        WHERE id_usuario = ? AND titulo = ? AND COALESCE(cuerpo, '') = ?
          AND fecha >= current_timestamp - INTERVAL ? HOUR
        LIMIT 1
        """,
        [int(id_usuario), titulo[:200], (cuerpo or "")[:500], max(1, int(horas))],
    ).fetchone()
    return row is not None


def compactar_duplicados(conn: duckdb.DuckDBPyConnection, *, id_usuario: int) -> int:
    """Elimina avisos repetidos (mismo título+cuerpo), conservando el más reciente."""
    asegurar_tabla(conn)
    antes = conn.execute(
        "SELECT COUNT(*) FROM notificaciones WHERE id_usuario = ?",
        [int(id_usuario)],
    ).fetchone()[0]
    conn.execute(
        """
        DELETE FROM notificaciones
        WHERE id_usuario = ?
          AND id_notif NOT IN (
            SELECT MAX(id_notif)
            FROM notificaciones
            WHERE id_usuario = ?
            GROUP BY titulo, COALESCE(cuerpo, ''), tipo
          )
        """,
        [int(id_usuario), int(id_usuario)],
    )
    despues = conn.execute(
        "SELECT COUNT(*) FROM notificaciones WHERE id_usuario = ?",
        [int(id_usuario)],
    ).fetchone()[0]
    return max(0, int(antes or 0) - int(despues or 0))


def crear(
    conn: duckdb.DuckDBPyConnection,
    *,
    id_usuario: int,
    titulo: str,
    cuerpo: str = "",
    tipo: str = "info",
    link: Optional[str] = None,
    dedupe_horas: int = 12,
) -> Optional[dict[str, Any]]:
    asegurar_tabla(conn)
    if _existe_reciente_usuario(
        conn,
        id_usuario=int(id_usuario),
        titulo=titulo,
        cuerpo=cuerpo,
        horas=dedupe_horas,
    ):
        return None
    nid = _next_id(conn)
    conn.execute(
        """
        INSERT INTO notificaciones (id_notif, id_usuario, titulo, cuerpo, tipo, link, leida)
        VALUES (?, ?, ?, ?, ?, ?, false)
        """,
        [nid, id_usuario, titulo[:200], (cuerpo or "")[:500], tipo[:40], link],
    )
    return {"id_notif": nid, "titulo": titulo, "leida": False}


def listar(
    conn: duckdb.DuckDBPyConnection,
    *,
    id_usuario: int,
    limit: int = 30,
    solo_no_leidas: bool = False,
) -> list[dict[str, Any]]:
    asegurar_tabla(conn)
    where = "WHERE id_usuario = ?"
    params: list[Any] = [id_usuario]
    if solo_no_leidas:
        where += " AND COALESCE(leida, false) = false"
    rows = conn.execute(
        f"""
        SELECT id_notif, titulo, cuerpo, tipo, link, leida, fecha
        FROM notificaciones {where}
        ORDER BY fecha DESC, id_notif DESC
        LIMIT ?
        """,
        [*params, max(1, min(limit, 100))],
    ).fetchall()
    return [
        {
            "id_notif": int(r[0]),
            "titulo": r[1],
            "cuerpo": r[2],
            "tipo": r[3],
            "link": r[4],
            "leida": bool(r[5]),
            "fecha": r[6],
        }
        for r in rows
    ]


def no_leidas(conn: duckdb.DuckDBPyConnection, *, id_usuario: int) -> int:
    asegurar_tabla(conn)
    row = conn.execute(
        "SELECT COUNT(*) FROM notificaciones WHERE id_usuario = ? AND COALESCE(leida, false) = false",
        [id_usuario],
    ).fetchone()
    return int(row[0] or 0)


def marcar_leida(conn: duckdb.DuckDBPyConnection, *, id_usuario: int, id_notif: int) -> bool:
    asegurar_tabla(conn)
    row = conn.execute(
        "SELECT 1 FROM notificaciones WHERE id_notif = ? AND id_usuario = ?",
        [id_notif, id_usuario],
    ).fetchone()
    if not row:
        return False
    conn.execute(
        "UPDATE notificaciones SET leida = true WHERE id_notif = ? AND id_usuario = ?",
        [id_notif, id_usuario],
    )
    return True


def marcar_todas(conn: duckdb.DuckDBPyConnection, *, id_usuario: int) -> int:
    asegurar_tabla(conn)
    before = no_leidas(conn, id_usuario=id_usuario)
    conn.execute(
        "UPDATE notificaciones SET leida = true WHERE id_usuario = ? AND COALESCE(leida, false) = false",
        [id_usuario],
    )
    return before


def eliminar(conn: duckdb.DuckDBPyConnection, *, id_usuario: int, id_notif: int) -> bool:
    asegurar_tabla(conn)
    conn.execute(
        "DELETE FROM notificaciones WHERE id_notif = ? AND id_usuario = ?",
        [id_notif, id_usuario],
    )
    return True


def limpiar(conn: duckdb.DuckDBPyConnection, *, id_usuario: int) -> int:
    """Vacía la bandeja del usuario (libera el panel)."""
    asegurar_tabla(conn)
    row = conn.execute(
        "SELECT COUNT(*) FROM notificaciones WHERE id_usuario = ?",
        [id_usuario],
    ).fetchone()
    n = int(row[0] or 0)
    conn.execute("DELETE FROM notificaciones WHERE id_usuario = ?", [id_usuario])
    return n


def sincronizar_alertas_stock(conn: duckdb.DuckDBPyConnection) -> int:
    """Crea avisos de stock bajo si no hay uno reciente (últimas 12 h) del mismo producto."""
    from shared.database.connection import table_exists

    asegurar_tabla(conn)
    if not table_exists(conn, "alertas_stock") or not table_exists(conn, "stock_almacen"):
        return 0
    try:
        rows = conn.execute(
            """
            SELECT p.nombre_producto, a.id_producto, a.id_almacen,
                   CAST(COALESCE(sa.cantidad_disponible, 0) AS DOUBLE) AS disp,
                   CAST(a.umbral_minimo AS DOUBLE) AS umbral,
                   alm.nombre AS almacen
            FROM alertas_stock a
            JOIN dim_producto p ON p.id_producto = a.id_producto
            LEFT JOIN stock_almacen sa
              ON sa.id_producto = a.id_producto AND sa.id_almacen = a.id_almacen
            LEFT JOIN almacenes alm ON alm.id_almacen = a.id_almacen
            WHERE a.activa = true
              AND COALESCE(sa.cantidad_disponible, 0) <= a.umbral_minimo
            ORDER BY disp ASC
            LIMIT 15
            """
        ).fetchall()
    except Exception:
        return 0
    creadas = 0
    for nombre, id_prod, id_alm, disp, umbral, alm_nom in rows:
        cuerpo = (
            f"Disponible {float(disp):g} / umbral {float(umbral):g}"
            + (f" en {alm_nom}" if alm_nom else f" (almacén #{id_alm})")
        )
        titulo = f"Stock bajo: {nombre}"
        n = notificar_staff_con_permiso(
            conn,
            permiso="mod.inventario",
            titulo=titulo[:200],
            cuerpo=cuerpo,
            link="/?page=inventario",
            tipo="stock",
        )
        creadas += n
    return creadas


def _cliente_acepta(
    conn: duckdb.DuckDBPyConnection, id_usuario: int, preferencia: Optional[str]
) -> bool:
    """Preferencia de notificación del cliente; si no hay registro, acepta."""
    if not preferencia:
        return True
    try:
        row = conn.execute(
            """
            SELECT cp.preferencias_json
            FROM cliente_preferencias cp
            JOIN dim_cliente c ON c.id_cliente = cp.id_cliente
            WHERE c.id_usuario = ?
            """,
            [int(id_usuario)],
        ).fetchone()
    except Exception:
        return True
    if not row or not row[0]:
        return True
    try:
        datos = json.loads(row[0]) if isinstance(row[0], str) else dict(row[0])
        return bool(datos.get(preferencia, True))
    except Exception:
        return True


def notificar_clientes(
    conn: duckdb.DuckDBPyConnection,
    *,
    titulo: str,
    cuerpo: str = "",
    link: Optional[str] = None,
    tipo: str = "promo",
    preferencia: Optional[str] = "notif_promociones",
    solo_usuarios: Optional[Sequence[int]] = None,
) -> int:
    """Avisa a los clientes del portal respetando sus preferencias.

    `solo_usuarios` limita el envío (por ejemplo, quienes tienen el producto
    en favoritos); si es None se notifica a toda la cartera activa.
    """
    asegurar_tabla(conn)
    if solo_usuarios is not None:
        destinatarios = [int(u) for u in solo_usuarios]
        if not destinatarios:
            return 0
    else:
        destinatarios = [
            int(r[0])
            for r in conn.execute(
                """
                SELECT DISTINCT u.id_usuario
                FROM usuarios u
                JOIN dim_cliente c ON c.id_usuario = u.id_usuario
                WHERE u.activo = true AND u.rol = 'cliente'
                """
            ).fetchall()
        ]

    enviadas = 0
    for id_usuario in destinatarios:
        if not _cliente_acepta(conn, id_usuario, preferencia):
            continue
        if crear(conn, id_usuario=id_usuario, titulo=titulo, cuerpo=cuerpo, tipo=tipo, link=link):
            enviadas += 1
    return enviadas


def usuarios_con_producto_en_favoritos(
    conn: duckdb.DuckDBPyConnection, id_producto: int
) -> list[int]:
    try:
        return [
            int(r[0])
            for r in conn.execute(
                "SELECT DISTINCT id_usuario FROM wishlist WHERE id_producto = ?", [int(id_producto)]
            ).fetchall()
        ]
    except Exception:
        return []


def usuarios_con_paquete_en_favoritos(
    conn: duckdb.DuckDBPyConnection, id_catalogo: int
) -> list[int]:
    try:
        return [
            int(r[0])
            for r in conn.execute(
                "SELECT DISTINCT id_usuario FROM wishlist_catalogos WHERE id_catalogo = ?",
                [int(id_catalogo)],
            ).fetchall()
        ]
    except Exception:
        return []


def notificar_descuento(
    conn: duckdb.DuckDBPyConnection,
    *,
    ambito: str,
    nombre: str,
    descuento_pct: float,
    link: str,
    hasta: Optional[str] = None,
    motivo: Optional[str] = None,
    usuarios_prioritarios: Optional[Sequence[int]] = None,
) -> int:
    """Publica un descuento a la cartera de clientes.

    `ambito` es 'categoría', 'paquete' o 'producto' y solo afecta el texto.
    Los clientes que lo tienen en favoritos reciben un aviso más directo.
    """
    etiqueta = f"{descuento_pct:g}%"
    detalle = motivo or f"Descuento de {etiqueta} en {nombre}"
    if hasta:
        detalle = f"{detalle}. Vigente hasta {hasta}."

    prioritarios = [int(u) for u in (usuarios_prioritarios or [])]
    enviadas = 0
    if prioritarios:
        enviadas += notificar_clientes(
            conn,
            titulo=f"Bajó de precio algo que guardaste: {nombre}",
            cuerpo=detalle,
            tipo="promo",
            link=link,
            preferencia="notif_promociones",
            solo_usuarios=prioritarios,
        )

    todos = [
        int(r[0])
        for r in conn.execute(
            """
            SELECT DISTINCT u.id_usuario
            FROM usuarios u
            JOIN dim_cliente c ON c.id_usuario = u.id_usuario
            WHERE u.activo = true AND u.rol = 'cliente'
            """
        ).fetchall()
    ]
    resto = [u for u in todos if u not in prioritarios]
    enviadas += notificar_clientes(
        conn,
        titulo=f"Nuevo descuento del {etiqueta} en {nombre}",
        cuerpo=detalle,
        tipo="promo",
        link=link,
        preferencia="notif_promociones",
        solo_usuarios=resto,
    )
    return enviadas


def notificar_pedido_portal_staff(
    conn: duckdb.DuckDBPyConnection,
    *,
    id_cliente: int,
    numero: str,
    total: float,
    estado: str = "pagado",
) -> int:
    """Avisa al staff ERP cuando un cliente del portal crea o paga un pedido."""
    row = conn.execute(
        "SELECT nombre_empresa FROM dim_cliente WHERE id_cliente = ?",
        [int(id_cliente)],
    ).fetchone()
    cliente = (row[0] if row and row[0] else f"Cliente #{id_cliente}").strip()
    monto = f"${float(total):,.2f}"
    if estado == "pendiente_pago":
        titulo = f"Pedido pendiente {numero}"
        cuerpo = f"{cliente} confirmó un pedido por {monto} (aún sin pagar)."
    else:
        titulo = f"Nuevo pedido {numero}"
        cuerpo = f"{cliente} realizó un pedido por {monto}."
    return notificar_staff_con_permiso(
        conn,
        permiso="mod.operaciones",
        titulo=titulo,
        cuerpo=cuerpo,
        link="/?page=pedidos",
        tipo="pedido",
    )


def notificar_staff_con_permiso(
    conn: duckdb.DuckDBPyConnection,
    *,
    permiso: str,
    titulo: str,
    cuerpo: str = "",
    link: Optional[str] = None,
    tipo: str = "info",
) -> int:
    """Crea aviso a usuarios staff activos con el permiso (o rol admin)."""
    asegurar_tabla(conn)
    rows = conn.execute(
        """
        SELECT DISTINCT u.id_usuario
        FROM usuarios u
        WHERE u.activo = true AND u.rol <> 'cliente'
          AND (
            u.rol = 'admin'
            OR EXISTS (
              SELECT 1 FROM rol_permiso rp
              JOIN roles r ON r.id_rol = rp.id_rol
              JOIN permisos p ON p.id_permiso = rp.id_permiso
              WHERE r.nombre = u.rol AND p.codigo = ?
            )
          )
        """,
        [permiso],
    ).fetchall()
    n = 0
    for (uid,) in rows:
        if crear(
            conn,
            id_usuario=int(uid),
            titulo=titulo,
            cuerpo=cuerpo,
            tipo=tipo,
            link=link,
        ):
            n += 1
    return n
