"""
logistica_service.py — Transportistas, zonas/tarifas y tracking de envíos.

Macro-zonas operativas (3) a partir de dim_region (8):
  americas → Central America (3), North America (6), South America (8)
  emea     → Europe (4), MENA (5), Sub-Saharan Africa (7)
  apac     → Asia (1), Australia and Oceania (2)
El país de entrega del cliente determina la macro-zona y, con ella,
los transportistas / tarifas permitidos.
"""

from __future__ import annotations

from typing import Any, Optional

import duckdb

from shared.database.connection import table_exists
from shared.services.red_bodegas import (
    MACRO_BY_REGION,
    MACRO_HUB_REGION,
    MACRO_LABELS,
    macro_de_region,
)

ENVIO_ESTADOS: dict[str, str] = {
    "preparando": "En preparación",
    "en_transito": "En tránsito",
    "en_hub": "En centro de distribución",
    "entregado": "Entregado",
    "incidencia": "Incidencia",
}

ENVIO_TRANSICIONES: dict[str, tuple[str, ...]] = {
    "preparando": ("en_transito", "en_hub", "incidencia"),
    "en_hub": ("en_transito", "incidencia"),
    "en_transito": ("entregado", "incidencia"),
    "incidencia": ("en_transito", "entregado"),
    "entregado": (),
}

ENVIO_DESCRIPCIONES: dict[str, str] = {
    "en_transito": "En tránsito hacia el cliente",
    "en_hub": "Paquete en centro de distribución regional",
    "entregado": "Paquete entregado al destinatario",
    "incidencia": "Incidencia reportada en el envío",
}


def transiciones_envio(estado_actual: str | None) -> list[str]:
    if not estado_actual:
        return ["en_transito"]
    return list(ENVIO_TRANSICIONES.get(estado_actual, ()))


def siguiente_estado_envio(estado_actual: str | None) -> str | None:
    opts = transiciones_envio(estado_actual)
    return opts[0] if opts else None


def _col_macro(conn: duckdb.DuckDBPyConnection, tabla: str) -> bool:
    try:
        return bool(
            conn.execute(
                """
                SELECT 1 FROM information_schema.columns
                WHERE table_name = ? AND column_name = 'macro_zona'
                """,
                [tabla],
            ).fetchone()
        )
    except Exception:
        return False


def resolver_destino_por_pais(
    conn: duckdb.DuckDBPyConnection, pais: Optional[str]
) -> dict[str, Any]:
    """Resuelve país → dim_country → región analytics → macro logística."""
    pais_n = (pais or "").strip()
    if not pais_n:
        return {
            "pais": None,
            "id_country": None,
            "id_region": None,
            "region": None,
            "macro_zona": None,
            "macro_label": None,
        }
    row = conn.execute(
        """
        SELECT c.id_country, c.country, c.id_region, r.region
        FROM dim_country c
        LEFT JOIN dim_region r ON r.id_region = c.id_region
        WHERE lower(c.country) = lower(?)
        ORDER BY c.id_country
        LIMIT 1
        """,
        [pais_n],
    ).fetchone()
    if not row:
        row = conn.execute(
            """
            SELECT c.id_country, c.country, c.id_region, r.region
            FROM dim_country c
            LEFT JOIN dim_region r ON r.id_region = c.id_region
            WHERE lower(c.country) LIKE lower(?)
            ORDER BY length(c.country) ASC, c.id_country
            LIMIT 1
            """,
            [f"%{pais_n}%"],
        ).fetchone()
    if not row:
        return {
            "pais": pais_n,
            "id_country": None,
            "id_region": None,
            "region": None,
            "macro_zona": None,
            "macro_label": None,
        }
    id_region = int(row[2]) if row[2] is not None else None
    macro = macro_de_region(id_region)
    return {
        "pais": row[1],
        "id_country": int(row[0]),
        "id_region": id_region,
        "region": row[3],
        "macro_zona": macro,
        "macro_label": MACRO_LABELS.get(macro or "", macro),
    }


def destino_pedido(conn: duckdb.DuckDBPyConnection, id_pedido: int) -> dict[str, Any]:
    """País de entrega del pedido: cliente.pais (ficha) alineado a dim_country."""
    row = conn.execute(
        """
        SELECT c.pais, c.nombre_empresa, c.direccion, p.notas
        FROM pedidos p
        JOIN dim_cliente c ON c.id_cliente = p.id_cliente
        WHERE p.id_pedido = ?
        """,
        [id_pedido],
    ).fetchone()
    if not row:
        raise ValueError("Pedido no encontrado.")
    dest = resolver_destino_por_pais(conn, row[0])
    dest["empresa"] = row[1]
    dest["direccion_cliente"] = row[2]
    dest["notas_pedido"] = row[3]
    return dest


def listar_transportistas(
    conn: duckdb.DuckDBPyConnection,
    *,
    activos_only: bool = True,
    id_transportista: Optional[int] = None,
    macro_zona: Optional[str] = None,
) -> list[dict[str, Any]]:
    where_parts: list[str] = []
    params: list[Any] = []
    if activos_only:
        where_parts.append("t.activo = true")
    if id_transportista is not None:
        where_parts.append("t.id_transportista = ?")
        params.append(id_transportista)
    has_macro = _col_macro(conn, "transportistas")
    if macro_zona and has_macro:
        where_parts.append("lower(COALESCE(t.macro_zona, '')) = lower(?)")
        params.append(macro_zona)
    elif macro_zona and not has_macro:
        # Fallback: filtrar por id_region perteneciente a la macro
        ids = [rid for rid, m in MACRO_BY_REGION.items() if m == macro_zona]
        if ids:
            placeholders = ",".join("?" * len(ids))
            where_parts.append(f"t.id_region IN ({placeholders})")
            params.extend(ids)
    where = f"WHERE {' AND '.join(where_parts)}" if where_parts else ""
    sel_macro = "t.macro_zona" if has_macro else "CAST(NULL AS VARCHAR)"
    rows = conn.execute(
        f"""
        SELECT t.id_transportista, t.nombre, t.activo, t.id_region, r.region, {sel_macro}
        FROM transportistas t
        LEFT JOIN dim_region r ON r.id_region = t.id_region
        {where}
        ORDER BY t.nombre
        """,
        params,
    ).fetchall()
    out = []
    for r in rows:
        macro = (r[5] or "").strip().lower() or macro_de_region(int(r[3]) if r[3] is not None else None)
        out.append(
            {
                "id_transportista": int(r[0]),
                "nombre": r[1],
                "activo": bool(r[2]),
                "id_region": int(r[3]) if r[3] is not None else None,
                "region": r[4],
                "macro_zona": macro,
                "macro_label": MACRO_LABELS.get(macro or "", macro),
            }
        )
    return out


def listar_zonas_por_macro(
    conn: duckdb.DuckDBPyConnection, *, macro_zona: Optional[str] = None
) -> list[dict[str, Any]]:
    zonas = listar_zonas_tarifas(conn)
    if not macro_zona:
        return zonas
    return [z for z in zonas if (z.get("macro_zona") or "").lower() == macro_zona.lower()]


def opciones_envio_pedido(conn: duckdb.DuckDBPyConnection, id_pedido: int) -> dict[str, Any]:
    dest = destino_pedido(conn, id_pedido)
    macro = dest.get("macro_zona")
    transportistas = listar_transportistas(conn, activos_only=True, macro_zona=macro) if macro else []
    zonas = listar_zonas_por_macro(conn, macro_zona=macro) if macro else []
    return {
        **dest,
        "transportistas": transportistas,
        "zonas": zonas,
        "mensaje": (
            None
            if macro and transportistas
            else (
                "No hay país de entrega resuelto en la ficha del cliente; actualice el país del cliente o su dirección."
                if not macro
                else f"No hay transportistas activos para la macro-zona {MACRO_LABELS.get(macro, macro)}."
            )
        ),
    }


def _assert_transportista_destino(
    conn: duckdb.DuckDBPyConnection, *, id_pedido: int, id_transportista: int, id_zona: Optional[int] = None
) -> dict[str, Any]:
    opts = opciones_envio_pedido(conn, id_pedido)
    macro = opts.get("macro_zona")
    if not macro:
        raise ValueError(
            "El cliente no tiene un país de entrega reconocido. "
            "Actualice el país en la ficha del cliente antes de despachar."
        )
    ids_ok = {int(t["id_transportista"]) for t in opts["transportistas"]}
    if int(id_transportista) not in ids_ok:
        raise ValueError(
            f"El transportista no opera en {opts.get('macro_label') or macro} "
            f"(destino: {opts.get('pais') or 'sin país'})."
        )
    if id_zona is not None:
        zonas_ok = {int(z["id_zona"]) for z in opts["zonas"]}
        if int(id_zona) not in zonas_ok:
            raise ValueError(
                f"La zona de tarifa no corresponde a la macro-zona {opts.get('macro_label') or macro}."
            )
    return opts


def _validar_region(conn: duckdb.DuckDBPyConnection, id_region: Optional[int]) -> None:
    if id_region is None:
        return
    row = conn.execute("SELECT 1 FROM dim_region WHERE id_region = ?", [id_region]).fetchone()
    if not row:
        raise ValueError("La región indicada no existe.")


def crear_transportista(
    conn: duckdb.DuckDBPyConnection,
    *,
    nombre: str,
    id_region: Optional[int] = None,
    macro_zona: Optional[str] = None,
) -> dict[str, Any]:
    nombre = (nombre or "").strip()
    if len(nombre) < 2:
        raise ValueError("Nombre de transportista inválido.")
    if conn.execute(
        "SELECT 1 FROM transportistas WHERE LOWER(nombre) = LOWER(?)", [nombre]
    ).fetchone():
        raise ValueError("Ya existe un transportista con ese nombre.")
    macro = (macro_zona or "").strip().lower() or None
    if macro and macro not in MACRO_LABELS:
        raise ValueError("Macro-zona inválida. Use: americas, emea o apac.")
    if id_region is None and macro:
        id_region = MACRO_HUB_REGION.get(macro)
    if macro is None and id_region is not None:
        macro = macro_de_region(id_region)
    _validar_region(conn, id_region)
    n = int(conn.execute("SELECT COALESCE(MAX(id_transportista), 0) + 1 FROM transportistas").fetchone()[0])
    if _col_macro(conn, "transportistas"):
        conn.execute(
            "INSERT INTO transportistas (id_transportista, nombre, id_region, macro_zona, activo) VALUES (?, ?, ?, ?, true)",
            [n, nombre, id_region, macro],
        )
    else:
        conn.execute(
            "INSERT INTO transportistas (id_transportista, nombre, id_region, activo) VALUES (?, ?, ?, true)",
            [n, nombre, id_region],
        )
    lst = listar_transportistas(conn, activos_only=False, id_transportista=n)
    return lst[0] if lst else {"id_transportista": n, "nombre": nombre, "activo": True, "id_region": id_region, "macro_zona": macro}


def actualizar_transportista(
    conn: duckdb.DuckDBPyConnection,
    id_transportista: int,
    *,
    nombre: str,
    activo: Optional[bool] = None,
    id_region: Optional[int] = None,
    macro_zona: Optional[str] = None,
) -> Optional[dict[str, Any]]:
    row = conn.execute(
        "SELECT id_transportista FROM transportistas WHERE id_transportista = ?", [id_transportista]
    ).fetchone()
    if not row:
        return None
    nombre = (nombre or "").strip()
    if len(nombre) < 2:
        raise ValueError("Nombre de transportista inválido.")
    if conn.execute(
        "SELECT 1 FROM transportistas WHERE LOWER(nombre) = LOWER(?) AND id_transportista <> ?",
        [nombre, id_transportista],
    ).fetchone():
        raise ValueError("Ya existe un transportista con ese nombre.")
    macro = (macro_zona or "").strip().lower() or None
    if macro and macro not in MACRO_LABELS:
        raise ValueError("Macro-zona inválida. Use: americas, emea o apac.")
    if id_region is None and macro:
        id_region = MACRO_HUB_REGION.get(macro)
    if macro is None and id_region is not None:
        macro = macro_de_region(id_region)
    _validar_region(conn, id_region)
    if _col_macro(conn, "transportistas"):
        if activo is None:
            conn.execute(
                "UPDATE transportistas SET nombre = ?, id_region = ?, macro_zona = ? WHERE id_transportista = ?",
                [nombre, id_region, macro, id_transportista],
            )
        else:
            conn.execute(
                "UPDATE transportistas SET nombre = ?, activo = ?, id_region = ?, macro_zona = ? WHERE id_transportista = ?",
                [nombre, bool(activo), id_region, macro, id_transportista],
            )
    else:
        if activo is None:
            conn.execute(
                "UPDATE transportistas SET nombre = ?, id_region = ? WHERE id_transportista = ?",
                [nombre, id_region, id_transportista],
            )
        else:
            conn.execute(
                "UPDATE transportistas SET nombre = ?, activo = ?, id_region = ? WHERE id_transportista = ?",
                [nombre, bool(activo), id_region, id_transportista],
            )
    lst = listar_transportistas(conn, activos_only=False, id_transportista=id_transportista)
    return lst[0] if lst else None


def set_activo_transportista(
    conn: duckdb.DuckDBPyConnection, id_transportista: int, *, activo: bool
) -> Optional[dict[str, Any]]:
    row = conn.execute(
        "SELECT id_transportista FROM transportistas WHERE id_transportista = ?",
        [id_transportista],
    ).fetchone()
    if not row:
        return None
    conn.execute(
        "UPDATE transportistas SET activo = ? WHERE id_transportista = ?",
        [bool(activo), id_transportista],
    )
    lst = listar_transportistas(conn, activos_only=False, id_transportista=id_transportista)
    return lst[0] if lst else None


def eliminar_transportista(conn: duckdb.DuckDBPyConnection, id_transportista: int) -> None:
    """Elimina un transportista. Lanza ValueError si tiene envíos asociados."""
    row = conn.execute(
        "SELECT id_transportista FROM transportistas WHERE id_transportista = ?", [id_transportista]
    ).fetchone()
    if not row:
        raise KeyError("Transportista no encontrado.")
    if table_exists(conn, "envios"):
        n = int(
            conn.execute(
                "SELECT COUNT(*) FROM envios e WHERE e.id_transportista = ?",
                [id_transportista],
            ).fetchone()[0]
        )
        if n > 0:
            raise ValueError(
                f"No se puede eliminar el transportista porque tiene {n} envío(s) asociado(s). "
                "Puede desactivarlo para dejar de ofrecerlo."
            )
    conn.execute("DELETE FROM transportistas WHERE id_transportista = ?", [id_transportista])


def listar_zonas_tarifas(conn: duckdb.DuckDBPyConnection) -> list[dict[str, Any]]:
    if not table_exists(conn, "zonas_envio"):
        return []
    has_macro = _col_macro(conn, "zonas_envio")
    sel_macro = ", macro_zona" if has_macro else ", CAST(NULL AS VARCHAR)"
    zonas = conn.execute(
        f"SELECT id_zona, nombre, CAST(COALESCE(costo_base, 0) AS DOUBLE){sel_macro} FROM zonas_envio ORDER BY nombre"
    ).fetchall()
    result = []
    for z in zonas:
        tarifas = []
        if table_exists(conn, "tarifas_envio"):
            tarifas = [
                {"id_tarifa": int(t[0]), "peso_max": float(t[1]), "costo": float(t[2])}
                for t in conn.execute(
                    "SELECT id_tarifa, CAST(peso_max AS DOUBLE), CAST(costo AS DOUBLE) FROM tarifas_envio WHERE id_zona = ?",
                    [int(z[0])],
                ).fetchall()
            ]
        macro = (z[3] or "").strip().lower() or None
        result.append({
            "id_zona": int(z[0]),
            "nombre": z[1],
            "costo_base": float(z[2]),
            "macro_zona": macro,
            "macro_label": MACRO_LABELS.get(macro or "", macro),
            "tarifas": tarifas,
        })
    return result


def crear_zona(
    conn: duckdb.DuckDBPyConnection,
    *,
    nombre: str,
    costo_base: float,
    macro_zona: Optional[str] = None,
) -> dict[str, Any]:
    if not table_exists(conn, "zonas_envio"):
        raise ValueError("La tabla de zonas no existe.")
    nombre = (nombre or "").strip()
    if len(nombre) < 2:
        raise ValueError("Nombre de zona inválido.")
    try:
        costo_base_f = float(costo_base)
    except (TypeError, ValueError):
        raise ValueError("El costo base debe ser un número.")
    if costo_base_f < 0:
        raise ValueError("El costo base no puede ser negativo.")
    macro = (macro_zona or "").strip().lower() or None
    if macro and macro not in MACRO_LABELS:
        raise ValueError("Macro-zona inválida. Use: americas, emea o apac.")
    if conn.execute(
        "SELECT 1 FROM zonas_envio WHERE LOWER(nombre) = LOWER(?)", [nombre]
    ).fetchone():
        raise ValueError("Ya existe una zona con ese nombre.")
    if _col_macro(conn, "zonas_envio"):
        conn.execute(
            """
            INSERT INTO zonas_envio (id_zona, nombre, costo_base, macro_zona)
            VALUES ((SELECT COALESCE(MAX(id_zona), 0) + 1 FROM zonas_envio), ?, ?, ?)
            """,
            [nombre, costo_base_f, macro],
        )
    else:
        conn.execute(
            """
            INSERT INTO zonas_envio (id_zona, nombre, costo_base)
            VALUES ((SELECT COALESCE(MAX(id_zona), 0) + 1 FROM zonas_envio), ?, ?)
            """,
            [nombre, costo_base_f],
        )
    id_zona = int(
        conn.execute("SELECT id_zona FROM zonas_envio WHERE nombre = ? ORDER BY id_zona DESC LIMIT 1", [nombre]).fetchone()[0]
    )
    return {
        "id_zona": id_zona,
        "nombre": nombre,
        "costo_base": costo_base_f,
        "macro_zona": macro,
        "macro_label": MACRO_LABELS.get(macro or "", macro),
        "tarifas": [],
    }


def actualizar_zona(
    conn: duckdb.DuckDBPyConnection,
    *,
    id_zona: int,
    nombre: str,
    costo_base: float,
    macro_zona: Optional[str] = None,
) -> dict[str, Any]:
    row = conn.execute("SELECT id_zona FROM zonas_envio WHERE id_zona = ?", [id_zona]).fetchone()
    if not row:
        raise ValueError(f"Zona {id_zona} no existe.")
    nombre = (nombre or "").strip()
    if len(nombre) < 2:
        raise ValueError("Nombre de zona inválido.")
    try:
        costo_base_f = float(costo_base)
    except (TypeError, ValueError):
        raise ValueError("El costo base debe ser un número.")
    if costo_base_f < 0:
        raise ValueError("El costo base no puede ser negativo.")
    macro = (macro_zona or "").strip().lower() or None
    if macro and macro not in MACRO_LABELS:
        raise ValueError("Macro-zona inválida. Use: americas, emea o apac.")
    if conn.execute(
        "SELECT 1 FROM zonas_envio WHERE LOWER(nombre) = LOWER(?) AND id_zona <> ?", [nombre, id_zona]
    ).fetchone():
        raise ValueError("Ya existe una zona con ese nombre.")
    if _col_macro(conn, "zonas_envio"):
        conn.execute(
            "UPDATE zonas_envio SET nombre = ?, costo_base = ?, macro_zona = ? WHERE id_zona = ?",
            [nombre, costo_base_f, macro, id_zona],
        )
    else:
        conn.execute(
            "UPDATE zonas_envio SET nombre = ?, costo_base = ? WHERE id_zona = ?",
            [nombre, costo_base_f, id_zona],
        )
    return {
        "id_zona": id_zona,
        "nombre": nombre,
        "costo_base": costo_base_f,
        "macro_zona": macro,
        "macro_label": MACRO_LABELS.get(macro or "", macro),
    }


def eliminar_zona(conn: duckdb.DuckDBPyConnection, *, id_zona: int) -> None:
    if not table_exists(conn, "envios"):
        raise ValueError("No se puede eliminar la zona.")
    usado = conn.execute(
        "SELECT COUNT(*) FROM envios WHERE id_zona = ?", [id_zona]
    ).fetchone()[0]
    if usado:
        raise ValueError("La zona está usada por envíos; no se puede eliminar.")
    conn.execute("DELETE FROM zonas_envio WHERE id_zona = ?", [id_zona])
    if table_exists(conn, "tarifas_envio"):
        conn.execute("DELETE FROM tarifas_envio WHERE id_zona = ?", [id_zona])


def crear_tarifa(conn: duckdb.DuckDBPyConnection, *, id_zona: int, peso_max: float, costo: float) -> dict[str, Any]:
    if not table_exists(conn, "tarifas_envio"):
        raise ValueError("La tabla de tarifas no existe.")
    if not conn.execute("SELECT 1 FROM zonas_envio WHERE id_zona = ?", [id_zona]).fetchone():
        raise ValueError(f"Zona {id_zona} no existe.")
    try:
        peso_max_f = float(peso_max)
        costo_f = float(costo)
    except (TypeError, ValueError):
        raise ValueError("Peso máximo y costo deben ser números.")
    if peso_max_f <= 0 or costo_f < 0:
        raise ValueError("Peso máximo debe ser mayor a 0 y costo no negativo.")
    duplicada = conn.execute(
        "SELECT id_tarifa FROM tarifas_envio WHERE id_zona = ? AND peso_max = ?",
        [id_zona, peso_max_f],
    ).fetchone()
    if duplicada:
        raise ValueError("Ya existe una tarifa con ese mismo peso máximo para esta zona.")
    conn.execute(
        """
        INSERT INTO tarifas_envio (id_tarifa, id_zona, peso_max, costo)
        VALUES ((SELECT COALESCE(MAX(id_tarifa), 0) + 1 FROM tarifas_envio), ?, ?, ?)
        """,
        [id_zona, peso_max_f, costo_f],
    )
    id_tarifa = int(
        conn.execute(
            "SELECT id_tarifa FROM tarifas_envio WHERE id_zona = ? ORDER BY id_tarifa DESC LIMIT 1",
            [id_zona],
        ).fetchone()[0]
    )
    return {"id_tarifa": id_tarifa, "id_zona": id_zona, "peso_max": peso_max_f, "costo": costo_f}


def actualizar_tarifa(conn: duckdb.DuckDBPyConnection, *, id_tarifa: int, peso_max: float, costo: float) -> None:
    row = conn.execute(
        "SELECT id_zona FROM tarifas_envio WHERE id_tarifa = ?", [id_tarifa]
    ).fetchone()
    if not row:
        raise ValueError(f"Tarifa {id_tarifa} no existe.")
    id_zona = int(row[0])
    try:
        peso_max_f = float(peso_max)
        costo_f = float(costo)
    except (TypeError, ValueError):
        raise ValueError("Peso máximo y costo deben ser números.")
    if peso_max_f <= 0 or costo_f < 0:
        raise ValueError("Peso máximo debe ser mayor a 0 y costo no negativo.")
    duplicada = conn.execute(
        "SELECT id_tarifa FROM tarifas_envio WHERE id_zona = ? AND peso_max = ? AND id_tarifa <> ?",
        [id_zona, peso_max_f, id_tarifa],
    ).fetchone()
    if duplicada:
        raise ValueError("Ya existe una tarifa con ese mismo peso máximo para esta zona.")
    conn.execute(
        "UPDATE tarifas_envio SET peso_max = ?, costo = ? WHERE id_tarifa = ?",
        [peso_max_f, costo_f, id_tarifa],
    )


def eliminar_tarifa(conn: duckdb.DuckDBPyConnection, *, id_tarifa: int) -> None:
    if not conn.execute("SELECT 1 FROM tarifas_envio WHERE id_tarifa = ?", [id_tarifa]).fetchone():
        raise ValueError(f"Tarifa {id_tarifa} no existe.")
    conn.execute("DELETE FROM tarifas_envio WHERE id_tarifa = ?", [id_tarifa])


def obtener_envio_pedido(conn: duckdb.DuckDBPyConnection, id_pedido: int) -> Optional[dict[str, Any]]:
    if not table_exists(conn, "envios"):
        return None
    r = conn.execute(
        """
        SELECT e.id_envio, e.estado, e.fecha_despacho, t.nombre, e.id_transportista, e.id_zona
        FROM envios e
        LEFT JOIN transportistas t ON t.id_transportista = e.id_transportista
        WHERE e.id_pedido = ?
        ORDER BY e.id_envio DESC LIMIT 1
        """,
        [id_pedido],
    ).fetchone()
    if not r:
        return None
    eventos = []
    if table_exists(conn, "tracking_eventos"):
        eventos = [
            {"estado": ev[0], "fecha": str(ev[1]) if ev[1] else None, "descripcion": ev[2]}
            for ev in conn.execute(
                "SELECT estado, fecha, descripcion FROM tracking_eventos WHERE id_envio = ? ORDER BY fecha",
                [int(r[0])],
            ).fetchall()
        ]
    return {
        "id_envio": int(r[0]), "estado": r[1],
        "fecha_despacho": str(r[2]) if r[2] else None,
        "transportista": r[3], "id_transportista": int(r[4]) if r[4] else None,
        "id_zona": int(r[5]) if r[5] else None, "eventos": eventos,
        "transiciones_posibles": transiciones_envio(r[1]),
        "siguiente_estado": siguiente_estado_envio(r[1]),
        "descripcion_sugerida": ENVIO_DESCRIPCIONES.get(siguiente_estado_envio(r[1]) or "", ""),
    }


def listar_pedidos_envio(conn: duckdb.DuckDBPyConnection, *, limit: int = 80) -> list[dict[str, Any]]:
    """Pedidos operativos (pagado en adelante) con estado de envío asociado."""
    if not table_exists(conn, "pedidos"):
        return []
    rows = conn.execute(
        """
        SELECT p.id_pedido, COALESCE(p.numero, CAST(p.id_pedido AS VARCHAR)),
               c.nombre_empresa, p.estado, p.fecha_pedido,
               e.id_envio, e.estado, t.nombre, e.id_transportista, c.pais
        FROM pedidos p
        JOIN dim_cliente c ON c.id_cliente = p.id_cliente
        LEFT JOIN envios e ON e.id_envio = (
            SELECT MAX(ev.id_envio) FROM envios ev WHERE ev.id_pedido = p.id_pedido
        )
        LEFT JOIN transportistas t ON t.id_transportista = e.id_transportista
        WHERE p.estado IN ('pagado', 'preparando', 'enviado', 'entregado')
        ORDER BY p.id_pedido DESC
        LIMIT ?
        """,
        [limit],
    ).fetchall()
    out = []
    for r in rows:
        dest = resolver_destino_por_pais(conn, r[9])
        out.append(
            {
                "id_pedido": int(r[0]),
                "numero": r[1],
                "empresa": r[2],
                "estado_pedido": r[3],
                "fecha_pedido": str(r[4]) if r[4] else None,
                "id_envio": int(r[5]) if r[5] is not None else None,
                "estado_envio": r[6],
                "transportista": r[7],
                "id_transportista": int(r[8]) if r[8] is not None else None,
                "tiene_envio": r[5] is not None,
                "pais": dest.get("pais") or r[9],
                "region": dest.get("region"),
                "macro_zona": dest.get("macro_zona"),
                "macro_label": dest.get("macro_label"),
            }
        )
    return out


def crear_envio_pedido(
    conn: duckdb.DuckDBPyConnection,
    *,
    id_pedido: int,
    id_transportista: Optional[int] = None,
    id_zona: Optional[int] = None,
) -> dict[str, Any]:
    """Crea envío + evento inicial. Idempotente si ya existe envío activo."""
    existente = obtener_envio_pedido(conn, id_pedido)
    if existente:
        return existente

    if id_transportista is not None:
        _assert_transportista_destino(
            conn, id_pedido=id_pedido, id_transportista=id_transportista, id_zona=id_zona
        )
    else:
        opts = opciones_envio_pedido(conn, id_pedido)
        if opts["transportistas"]:
            id_transportista = int(opts["transportistas"][0]["id_transportista"])
        if id_zona is None and opts["zonas"]:
            id_zona = int(opts["zonas"][0]["id_zona"])

    if id_transportista is None:
        row = conn.execute("SELECT id_transportista FROM transportistas WHERE activo = true ORDER BY id_transportista LIMIT 1").fetchone()
        id_transportista = int(row[0]) if row else None
    if id_zona is None and table_exists(conn, "zonas_envio"):
        z = conn.execute("SELECT id_zona FROM zonas_envio ORDER BY id_zona LIMIT 1").fetchone()
        id_zona = int(z[0]) if z else None

    pedido_row = conn.execute("SELECT estado FROM pedidos WHERE id_pedido = ?", [id_pedido]).fetchone()
    pedido_estado = pedido_row[0] if pedido_row else None
    if pedido_estado in ("pagado", "preparando"):
        estado_envio = "preparando"
        desc_inicial = "Envío programado — pedido en preparación"
    else:
        estado_envio = "en_transito"
        desc_inicial = "Paquete despachado del hub regional"

    n = int(conn.execute("SELECT COALESCE(MAX(id_envio), 0) + 1 FROM envios").fetchone()[0])
    conn.execute(
        """
        INSERT INTO envios (id_envio, id_pedido, id_transportista, fecha_despacho, estado, id_zona)
        VALUES (?, ?, ?, current_timestamp, ?, ?)
        """,
        [n, id_pedido, id_transportista, estado_envio, id_zona],
    )
    _agregar_evento(conn, id_envio=n, estado=estado_envio, descripcion=desc_inicial)
    return obtener_envio_pedido(conn, id_pedido) or {"id_envio": n}


def _marcar_envio_en_transito(
    conn: duckdb.DuckDBPyConnection,
    *,
    id_pedido: int,
    id_transportista: Optional[int] = None,
    id_zona: Optional[int] = None,
) -> dict[str, Any]:
    """Pone el envío en tránsito (crea uno nuevo si no existe)."""
    if id_transportista is not None:
        _assert_transportista_destino(
            conn, id_pedido=id_pedido, id_transportista=id_transportista, id_zona=id_zona
        )

    existente = obtener_envio_pedido(conn, id_pedido)
    if existente and existente.get("id_envio"):
        id_envio = int(existente["id_envio"])
        if id_transportista is not None:
            conn.execute(
                "UPDATE envios SET id_transportista = ? WHERE id_envio = ?",
                [id_transportista, id_envio],
            )
        if id_zona is not None:
            conn.execute("UPDATE envios SET id_zona = ? WHERE id_envio = ?", [id_zona, id_envio])
        if existente.get("estado") != "en_transito":
            conn.execute(
                "UPDATE envios SET estado = 'en_transito', fecha_despacho = current_timestamp WHERE id_envio = ?",
                [id_envio],
            )
            _agregar_evento(
                conn, id_envio=id_envio,
                estado="en_transito", descripcion=ENVIO_DESCRIPCIONES["en_transito"],
            )
        return obtener_envio_pedido(conn, id_pedido) or existente

    if id_transportista is None:
        opts = opciones_envio_pedido(conn, id_pedido)
        if opts["transportistas"]:
            id_transportista = int(opts["transportistas"][0]["id_transportista"])
        if id_zona is None and opts["zonas"]:
            id_zona = int(opts["zonas"][0]["id_zona"])
    if id_transportista is None:
        row = conn.execute(
            "SELECT id_transportista FROM transportistas WHERE activo = true ORDER BY id_transportista LIMIT 1"
        ).fetchone()
        id_transportista = int(row[0]) if row else None
    if id_zona is None and table_exists(conn, "zonas_envio"):
        z = conn.execute("SELECT id_zona FROM zonas_envio ORDER BY id_zona LIMIT 1").fetchone()
        id_zona = int(z[0]) if z else None

    n = int(conn.execute("SELECT COALESCE(MAX(id_envio), 0) + 1 FROM envios").fetchone()[0])
    conn.execute(
        """
        INSERT INTO envios (id_envio, id_pedido, id_transportista, fecha_despacho, estado, id_zona)
        VALUES (?, ?, ?, current_timestamp, 'en_transito', ?)
        """,
        [n, id_pedido, id_transportista, id_zona],
    )
    _agregar_evento(
        conn, id_envio=n,
        estado="en_transito", descripcion=ENVIO_DESCRIPCIONES["en_transito"],
    )
    return obtener_envio_pedido(conn, id_pedido) or {"id_envio": n}


def asignar_transportista_y_despachar(
    conn: duckdb.DuckDBPyConnection,
    *,
    id_pedido: int,
    id_transportista: int,
    id_zona: Optional[int] = None,
    id_usuario: Optional[int] = None,
) -> dict[str, Any]:
    """Asigna transportista, despacha el envío y sincroniza el pedido a «enviado»."""
    from gmbackend.services.estado_pedido import avanzar_pedido_hasta

    if obtener_envio_pedido(conn, id_pedido):
        raise ValueError("Este pedido ya tiene un envío registrado.")

    opts = _assert_transportista_destino(
        conn, id_pedido=id_pedido, id_transportista=id_transportista, id_zona=id_zona
    )
    if id_zona is None and opts["zonas"]:
        id_zona = int(opts["zonas"][0]["id_zona"])

    envio = _marcar_envio_en_transito(
        conn, id_pedido=id_pedido, id_transportista=id_transportista, id_zona=id_zona,
    )
    avanzar_pedido_hasta(conn, id_pedido, "enviado", id_usuario=id_usuario)
    resultado = obtener_envio_pedido(conn, id_pedido) or envio
    try:
        from shared.services import notificacion_service as ns
        num = conn.execute("SELECT numero FROM pedidos WHERE id_pedido = ?", [id_pedido]).fetchone()
        tr = conn.execute(
            "SELECT nombre FROM transportistas WHERE id_transportista = ?", [id_transportista]
        ).fetchone()
        ns.notificar_staff_con_permiso(
            conn,
            permiso="mod.logistica",
            titulo=f"Despacho {num[0] if num else id_pedido}",
            cuerpo=f"Transportista: {tr[0] if tr else id_transportista} · envío en tránsito",
            link="/?page=logistica",
            tipo="logistica",
        )
    except Exception:
        pass
    return resultado


def on_pedido_enviado(
    conn: duckdb.DuckDBPyConnection,
    *,
    id_pedido: int,
    id_transportista: Optional[int] = None,
) -> None:
    """Hook al marcar pedido como enviado desde Pedidos B2B."""
    if not table_exists(conn, "envios"):
        return
    if id_transportista is None:
        opts = opciones_envio_pedido(conn, id_pedido)
        if not opts["transportistas"]:
            raise ValueError(opts.get("mensaje") or "Sin transportistas para el destino del cliente.")
        id_transportista = int(opts["transportistas"][0]["id_transportista"])
    _marcar_envio_en_transito(conn, id_pedido=id_pedido, id_transportista=id_transportista)


def _marcar_envio_entregado(conn: duckdb.DuckDBPyConnection, *, id_pedido: int) -> None:
    existente = obtener_envio_pedido(conn, id_pedido)
    if not existente or not existente.get("id_envio"):
        return
    id_envio = int(existente["id_envio"])
    if existente.get("estado") == "entregado":
        return
    _agregar_evento(
        conn, id_envio=id_envio,
        estado="entregado", descripcion=ENVIO_DESCRIPCIONES["entregado"],
    )
    conn.execute("UPDATE envios SET estado = 'entregado' WHERE id_envio = ?", [id_envio])


def _agregar_evento(
    conn: duckdb.DuckDBPyConnection, *, id_envio: int, estado: str, descripcion: str
) -> None:
    n = int(conn.execute("SELECT COALESCE(MAX(id_evento), 0) + 1 FROM tracking_eventos").fetchone()[0])
    conn.execute(
        """
        INSERT INTO tracking_eventos (id_evento, id_envio, estado, fecha, descripcion)
        VALUES (?, ?, ?, current_timestamp, ?)
        """,
        [n, id_envio, estado, descripcion],
    )


def registrar_evento_tracking(
    conn: duckdb.DuckDBPyConnection,
    *,
    id_envio: int,
    estado: str,
    descripcion: Optional[str] = None,
    id_usuario: Optional[int] = None,
) -> dict[str, Any]:
    row = conn.execute("SELECT estado FROM envios WHERE id_envio = ?", [id_envio]).fetchone()
    if not row:
        raise ValueError("Envío no encontrado.")
    estado_actual = row[0]
    permitidos = transiciones_envio(estado_actual)
    if estado not in permitidos:
        actual_label = ENVIO_ESTADOS.get(estado_actual, estado_actual)
        raise ValueError(
            f"No se puede pasar de «{actual_label}» a «{ENVIO_ESTADOS.get(estado, estado)}». "
            f"Opciones válidas: {', '.join(ENVIO_ESTADOS.get(e, e) for e in permitidos) or 'ninguna (envío finalizado)'}."
        )
    desc = descripcion or ENVIO_DESCRIPCIONES.get(estado, estado)
    _agregar_evento(conn, id_envio=id_envio, estado=estado, descripcion=desc)
    conn.execute("UPDATE envios SET estado = ? WHERE id_envio = ?", [estado, id_envio])
    pedido_row = conn.execute("SELECT id_pedido FROM envios WHERE id_envio = ?", [id_envio]).fetchone()
    if pedido_row:
        from gmbackend.services.estado_pedido import avanzar_pedido_hasta
        id_pedido = int(pedido_row[0])
        if estado == "en_transito":
            avanzar_pedido_hasta(conn, id_pedido, "enviado", id_usuario=id_usuario)
        elif estado == "entregado":
            avanzar_pedido_hasta(conn, id_pedido, "entregado", id_usuario=id_usuario)
        return obtener_envio_pedido(conn, id_pedido) or {"id_envio": id_envio, "estado": estado}
    return {"id_envio": id_envio, "estado": estado}


def on_pedido_entregado(conn: duckdb.DuckDBPyConnection, *, id_pedido: int) -> None:
    """Hook al marcar pedido como entregado desde Pedidos B2B."""
    if not table_exists(conn, "envios"):
        return
    try:
        _marcar_envio_entregado(conn, id_pedido=id_pedido)
    except Exception:
        pass


def listar_almacenes(
    conn: duckdb.DuckDBPyConnection, *, activos_only: bool = True, id_almacen: Optional[int] = None
) -> list[dict[str, Any]]:
    where = "WHERE a.activo = true" if activos_only else ""
    params: list[Any] = []
    if id_almacen is not None:
        where = "WHERE a.id_almacen = ?" if not where else f"{where} AND a.id_almacen = ?"
        params.append(id_almacen)
    rows = conn.execute(
        f"""
        SELECT a.id_almacen, a.nombre, a.direccion, a.id_region, r.region, a.activo,
               (SELECT COALESCE(SUM(sa.cantidad_disponible), 0) FROM stock_almacen sa WHERE sa.id_almacen = a.id_almacen) AS stock_total,
               (SELECT COUNT(*) FROM stock_almacen sa WHERE sa.id_almacen = a.id_almacen AND COALESCE(sa.cantidad_disponible, 0) > 0) AS skus,
               (SELECT COUNT(*) FROM alertas_stock al
                  JOIN stock_almacen sa ON sa.id_producto = al.id_producto AND sa.id_almacen = al.id_almacen
                 WHERE al.id_almacen = a.id_almacen AND al.activa = true
                   AND COALESCE(sa.cantidad_disponible, 0) <= al.umbral_minimo) AS alertas_stock,
               a.macro_zona, COALESCE(a.es_hub, false) AS es_hub, a.codigo,
               COALESCE(a.prioridad, 50) AS prioridad
        FROM almacenes a
        LEFT JOIN dim_region r ON r.id_region = a.id_region
        {where}
        ORDER BY COALESCE(a.prioridad, 50), a.id_almacen
        """,
        params,
    ).fetchall()
    salida = []
    for r in rows:
        macro = r[9] or macro_de_region(int(r[3])) if r[3] is not None else r[9]
        salida.append(
            {
                "id_almacen": int(r[0]),
                "nombre": r[1],
                "direccion": r[2],
                "id_region": int(r[3]) if r[3] is not None else None,
                "region": r[4],
                "activo": bool(r[5]),
                "stock_total": float(r[6] or 0),
                "skus": int(r[7] or 0),
                "alertas_stock": int(r[8] or 0),
                "macro_zona": macro,
                "macro_label": MACRO_LABELS.get(macro) if macro else None,
                "es_hub": bool(r[10]),
                "codigo": r[11],
                "prioridad": int(r[12] or 50),
                "rol": "Hub regional" if bool(r[10]) else "Bodega satélite",
            }
        )
    return salida


def crear_almacen(
    conn: duckdb.DuckDBPyConnection,
    *,
    nombre: str,
    direccion: Optional[str] = None,
    id_region: Optional[int] = None,
) -> dict[str, Any]:
    nombre = (nombre or "").strip()
    if len(nombre) < 2:
        raise ValueError("Nombre de almacén inválido.")
    if conn.execute(
        "SELECT 1 FROM almacenes WHERE LOWER(nombre) = LOWER(?)", [nombre]
    ).fetchone():
        raise ValueError("Ya existe un almacén con ese nombre.")
    _validar_region(conn, id_region)
    n = int(conn.execute("SELECT COALESCE(MAX(id_almacen), 0) + 1 FROM almacenes").fetchone()[0])
    macro = macro_de_region(id_region)
    conn.execute(
        """
        INSERT INTO almacenes (id_almacen, nombre, direccion, id_region, activo, macro_zona, es_hub, prioridad)
        VALUES (?, ?, ?, ?, true, ?, false, 20)
        """,
        [n, nombre, direccion or None, id_region, macro],
    )
    surtido = _surtir_almacen_nuevo(conn, n, nombre)

    lst = listar_almacenes(conn, activos_only=False, id_almacen=n)
    resultado = lst[0] if lst else {
        "id_almacen": n, "nombre": nombre, "direccion": direccion,
        "id_region": id_region, "region": None, "activo": True, "stock_total": 0,
    }
    resultado["surtido_inicial"] = surtido
    return resultado


def _surtir_almacen_nuevo(
    conn: duckdb.DuckDBPyConnection, id_almacen: int, nombre: str
) -> dict[str, Any]:
    """Carga inventario inicial en una bodega recién creada.

    Una bodega vacía haría aparecer productos agotados a los clientes de su
    zona, así que se surte con el objetivo de bodega satélite en cuanto nace.
    """
    from shared.services.config_service import obtener_config_int

    objetivo = float(obtener_config_int(conn, "STOCK_OBJETIVO_SATELITE", 150))
    if objetivo <= 0:
        return {"lineas": 0, "unidades": 0.0}

    productos = [
        int(r[0])
        for r in conn.execute(
            "SELECT id_producto FROM dim_producto WHERE activo = true"
        ).fetchall()
    ]
    if not productos:
        return {"lineas": 0, "unidades": 0.0}

    conn.execute(
        """
        INSERT INTO movimientos_inventario (id_movimiento, tipo, fecha, referencia, id_usuario)
        VALUES ((SELECT COALESCE(MAX(id_movimiento), 0) + 1 FROM movimientos_inventario),
                'entrada', current_timestamp, ?, NULL)
        """,
        [f"Surtido inicial — {nombre}"],
    )
    id_movimiento = int(
        conn.execute("SELECT MAX(id_movimiento) FROM movimientos_inventario").fetchone()[0]
    )
    for id_producto in productos:
        conn.execute(
            """
            INSERT INTO stock_almacen (id_stock, id_producto, id_almacen, cantidad_disponible, cantidad_reservada)
            SELECT (SELECT COALESCE(MAX(id_stock), 0) + 1 FROM stock_almacen), ?, ?, ?, 0
            WHERE NOT EXISTS (
              SELECT 1 FROM stock_almacen WHERE id_producto = ? AND id_almacen = ?
            )
            """,
            [id_producto, id_almacen, objetivo, id_producto, id_almacen],
        )
        conn.execute(
            """
            INSERT INTO movimiento_inventario_detalle (id_detalle, id_movimiento, id_producto, id_almacen, id_lote, cantidad)
            VALUES ((SELECT COALESCE(MAX(id_detalle), 0) + 1 FROM movimiento_inventario_detalle), ?, ?, ?, NULL, ?)
            """,
            [id_movimiento, id_producto, id_almacen, objetivo],
        )
    return {"lineas": len(productos), "unidades": round(objetivo * len(productos), 2)}


def actualizar_almacen(
    conn: duckdb.DuckDBPyConnection,
    id_almacen: int,
    *,
    nombre: str,
    direccion: Optional[str] = None,
    id_region: Optional[int] = None,
    activo: Optional[bool] = None,
) -> Optional[dict[str, Any]]:
    row = conn.execute(
        "SELECT id_almacen FROM almacenes WHERE id_almacen = ?", [id_almacen]
    ).fetchone()
    if not row:
        return None
    nombre = (nombre or "").strip()
    if len(nombre) < 2:
        raise ValueError("Nombre de almacén inválido.")
    if conn.execute(
        "SELECT 1 FROM almacenes WHERE LOWER(nombre) = LOWER(?) AND id_almacen <> ?",
        [nombre, id_almacen],
    ).fetchone():
        raise ValueError("Ya existe un almacén con ese nombre.")
    _validar_region(conn, id_region)
    if activo is None:
        conn.execute(
            "UPDATE almacenes SET nombre = ?, direccion = ?, id_region = ? WHERE id_almacen = ?",
            [nombre, direccion or None, id_region, id_almacen],
        )
    else:
        conn.execute(
            "UPDATE almacenes SET nombre = ?, direccion = ?, id_region = ?, activo = ? WHERE id_almacen = ?",
            [nombre, direccion or None, id_region, bool(activo), id_almacen],
        )
    lst = listar_almacenes(conn, activos_only=False, id_almacen=id_almacen)
    return lst[0] if lst else None


def set_activo_almacen(
    conn: duckdb.DuckDBPyConnection, id_almacen: int, *, activo: bool
) -> Optional[dict[str, Any]]:
    row = conn.execute(
        "SELECT id_almacen FROM almacenes WHERE id_almacen = ?", [id_almacen]
    ).fetchone()
    if not row:
        return None
    conn.execute(
        "UPDATE almacenes SET activo = ? WHERE id_almacen = ?",
        [bool(activo), id_almacen],
    )
    lst = listar_almacenes(conn, activos_only=False, id_almacen=id_almacen)
    return lst[0] if lst else None


def stock_por_almacen(
    conn: duckdb.DuckDBPyConnection, id_almacen: int, *, limite: int = 40
) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT p.id_producto, p.nombre_producto,
               CAST(COALESCE(sa.cantidad_disponible, 0) AS DOUBLE) AS disponible,
               CAST(COALESCE(sa.cantidad_reservada, 0) AS DOUBLE) AS reservada,
               CAST(COALESCE(al.umbral_minimo, p.stock_minimo, 0) AS DOUBLE) AS umbral
        FROM stock_almacen sa
        JOIN dim_producto p ON p.id_producto = sa.id_producto
        LEFT JOIN alertas_stock al
          ON al.id_producto = sa.id_producto AND al.id_almacen = sa.id_almacen AND al.activa = true
        WHERE sa.id_almacen = ?
        ORDER BY disponible ASC, p.nombre_producto
        LIMIT ?
        """,
        [id_almacen, max(1, min(int(limite), 200))],
    ).fetchall()
    return [
        {
            "id_producto": int(r[0]),
            "producto": r[1],
            "disponible": float(r[2] or 0),
            "reservada": float(r[3] or 0),
            "umbral": float(r[4] or 0),
            "bajo": float(r[2] or 0) <= float(r[4] or 0) and float(r[4] or 0) > 0,
        }
        for r in rows
    ]


def eliminar_almacen(conn: duckdb.DuckDBPyConnection, id_almacen: int) -> None:
    """Elimina un almacén. Lanza ValueError si tiene stock o movimientos."""
    row = conn.execute(
        "SELECT id_almacen FROM almacenes WHERE id_almacen = ?", [id_almacen]
    ).fetchone()
    if not row:
        raise KeyError("Almacén no encontrado.")
    if table_exists(conn, "stock_almacen"):
        n = int(
            conn.execute(
                "SELECT COUNT(*) FROM stock_almacen WHERE id_almacen = ?", [id_almacen]
            ).fetchone()[0]
        )
        if n > 0:
            raise ValueError(
                "No se puede eliminar: el almacén tiene registros de stock. Desactívelo en su lugar."
            )
    conn.execute("DELETE FROM almacenes WHERE id_almacen = ?", [id_almacen])
