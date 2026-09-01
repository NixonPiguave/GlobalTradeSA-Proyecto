"""
cuenta_service.py — Cuenta B2B self-service (estilo VTEX/BigCommerce):
direcciones, contactos, preferencias y cambio de contraseña.
"""

from __future__ import annotations

import json
from typing import Any, Optional

import duckdb

from gmbackend.services.auth_service import (
    _pais_valido,
    hash_password,
    obtener_usuario_y_cliente,
    verificar_password,
)
from shared.services import listas_precio_service
from shared.database.connection import table_exists

TIPOS_DIRECCION = ("envio", "facturacion", "ambos")
PREFS_DEFAULT = {
    "notif_pedidos": True,
    "notif_promociones": True,
    "notif_stock": False,
    "moneda_preferida": "USD",
}


def _id_cliente(conn: duckdb.DuckDBPyConnection, id_usuario: int) -> int:
    data = obtener_usuario_y_cliente(conn, id_usuario=id_usuario)
    if not data or not data.get("cliente"):
        raise ValueError("La cuenta no tiene ficha de cliente B2B.")
    return int(data["cliente"]["id_cliente"])


def _next_id(conn: duckdb.DuckDBPyConnection, tabla: str, col: str) -> int:
    row = conn.execute(f"SELECT COALESCE(MAX({col}), 0) + 1 FROM {tabla}").fetchone()
    return int(row[0])


# ---------------------------------------------------------------------------
# Contraseña
# ---------------------------------------------------------------------------

def cambiar_password(
    conn: duckdb.DuckDBPyConnection,
    *,
    id_usuario: int,
    password_actual: str,
    password_nueva: str,
) -> None:
    row = conn.execute(
        "SELECT password_hash FROM usuarios WHERE id_usuario = ?",
        [id_usuario],
    ).fetchone()
    if not row:
        raise ValueError("Usuario no encontrado.")
    if not verificar_password(password_actual, row[0]):
        raise ValueError("La contraseña actual no es correcta.")
    if password_actual == password_nueva:
        raise ValueError("La nueva contraseña debe ser distinta a la actual.")
    if len(password_nueva) < 8:
        raise ValueError("La nueva contraseña debe tener al menos 8 caracteres.")
    conn.execute(
        "UPDATE usuarios SET password_hash = ? WHERE id_usuario = ?",
        [hash_password(password_nueva), id_usuario],
    )


# ---------------------------------------------------------------------------
# Direcciones
# ---------------------------------------------------------------------------

def listar_direcciones(conn: duckdb.DuckDBPyConnection, id_usuario: int) -> list[dict[str, Any]]:
    id_cliente = _id_cliente(conn, id_usuario)
    if not table_exists(conn, "cliente_direcciones_extra"):
        row = conn.execute(
            "SELECT direccion, ciudad, pais FROM dim_cliente WHERE id_cliente = ?",
            [id_cliente],
        ).fetchone()
        if not row or not (row[0] or "").strip():
            return []
        return [
            {
                "id_direccion": 0,
                "alias": "Principal",
                "direccion": row[0],
                "ciudad": row[1],
                "pais": row[2],
                "es_principal": True,
                "activo": True,
                "tipo": "envio",
            }
        ]
    rows = conn.execute(
        """
        SELECT id_direccion, alias, direccion, ciudad, pais, es_principal, activo,
               COALESCE(tipo, 'envio') AS tipo
        FROM cliente_direcciones_extra
        WHERE id_cliente = ? AND COALESCE(activo, true) = true
        ORDER BY es_principal DESC, id_direccion DESC
        """,
        [id_cliente],
    ).fetchall()
    return [
        {
            "id_direccion": int(r[0]),
            "alias": r[1] or "Dirección",
            "direccion": r[2],
            "ciudad": r[3],
            "pais": r[4],
            "es_principal": bool(r[5]),
            "activo": bool(r[6]),
            "tipo": r[7] or "envio",
        }
        for r in rows
    ]


def crear_direccion(
    conn: duckdb.DuckDBPyConnection,
    *,
    id_usuario: int,
    alias: str,
    direccion: str,
    ciudad: Optional[str],
    pais: str,
    tipo: str = "envio",
    es_principal: bool = False,
) -> dict[str, Any]:
    id_cliente = _id_cliente(conn, id_usuario)
    if not _pais_valido(conn, pais):
        raise ValueError("El país no es válido. Selecciona un país de la lista.")
    tipo_n = (tipo or "envio").strip().lower()
    if tipo_n not in TIPOS_DIRECCION:
        raise ValueError("Tipo de dirección inválido (envio, facturacion, ambos).")
    alias_n = (alias or "Dirección").strip()[:80] or "Dirección"
    dir_n = direccion.strip()
    if len(dir_n) < 5:
        raise ValueError("La dirección debe tener al menos 5 caracteres.")

    existentes = listar_direcciones(conn, id_usuario)
    if not existentes:
        es_principal = True

    if es_principal:
        conn.execute(
            "UPDATE cliente_direcciones_extra SET es_principal = false WHERE id_cliente = ?",
            [id_cliente],
        )

    nid = _next_id(conn, "cliente_direcciones_extra", "id_direccion")
    # tipo column may not exist on older DBs — ensure via migration
    try:
        conn.execute(
            """
            INSERT INTO cliente_direcciones_extra
              (id_direccion, id_cliente, alias, direccion, ciudad, pais, es_principal, activo, tipo)
            VALUES (?, ?, ?, ?, ?, ?, ?, true, ?)
            """,
            [nid, id_cliente, alias_n, dir_n, ciudad, pais, bool(es_principal), tipo_n],
        )
    except Exception:
        conn.execute(
            """
            INSERT INTO cliente_direcciones_extra
              (id_direccion, id_cliente, alias, direccion, ciudad, pais, es_principal, activo)
            VALUES (?, ?, ?, ?, ?, ?, ?, true)
            """,
            [nid, id_cliente, alias_n, dir_n, ciudad, pais, bool(es_principal)],
        )

    if es_principal:
        conn.execute(
            "UPDATE dim_cliente SET direccion = ?, pais = ? WHERE id_cliente = ?",
            [dir_n, pais, id_cliente],
        )

    for d in listar_direcciones(conn, id_usuario):
        if d["id_direccion"] == nid:
            return d
    raise RuntimeError("No se pudo crear la dirección.")


def actualizar_direccion(
    conn: duckdb.DuckDBPyConnection,
    *,
    id_usuario: int,
    id_direccion: int,
    alias: Optional[str] = None,
    direccion: Optional[str] = None,
    ciudad: Optional[str] = None,
    pais: Optional[str] = None,
    tipo: Optional[str] = None,
    es_principal: Optional[bool] = None,
) -> dict[str, Any]:
    id_cliente = _id_cliente(conn, id_usuario)
    row = conn.execute(
        """
        SELECT id_direccion FROM cliente_direcciones_extra
        WHERE id_direccion = ? AND id_cliente = ? AND COALESCE(activo, true) = true
        """,
        [id_direccion, id_cliente],
    ).fetchone()
    if not row:
        raise ValueError("Dirección no encontrada.")

    sets: list[str] = []
    params: list[Any] = []
    if alias is not None:
        sets.append("alias = ?")
        params.append(alias.strip()[:80] or "Dirección")
    if direccion is not None:
        d = direccion.strip()
        if len(d) < 5:
            raise ValueError("La dirección debe tener al menos 5 caracteres.")
        sets.append("direccion = ?")
        params.append(d)
    if ciudad is not None:
        sets.append("ciudad = ?")
        params.append(ciudad.strip() or None)
    if pais is not None:
        if not _pais_valido(conn, pais):
            raise ValueError("El país no es válido.")
        sets.append("pais = ?")
        params.append(pais)
    if tipo is not None:
        t = tipo.strip().lower()
        if t not in TIPOS_DIRECCION:
            raise ValueError("Tipo de dirección inválido.")
        sets.append("tipo = ?")
        params.append(t)
    if es_principal is True:
        conn.execute(
            "UPDATE cliente_direcciones_extra SET es_principal = false WHERE id_cliente = ?",
            [id_cliente],
        )
        sets.append("es_principal = true")

    if sets:
        params.extend([id_direccion, id_cliente])
        conn.execute(
            f"UPDATE cliente_direcciones_extra SET {', '.join(sets)} WHERE id_direccion = ? AND id_cliente = ?",
            params,
        )

    dirs = listar_direcciones(conn, id_usuario)
    actual = next((d for d in dirs if d["id_direccion"] == id_direccion), None)
    if actual and actual.get("es_principal"):
        conn.execute(
            "UPDATE dim_cliente SET direccion = ?, pais = ? WHERE id_cliente = ?",
            [actual["direccion"], actual["pais"], id_cliente],
        )
    if not actual:
        raise ValueError("Dirección no encontrada.")
    return actual


def eliminar_direccion(conn: duckdb.DuckDBPyConnection, *, id_usuario: int, id_direccion: int) -> None:
    id_cliente = _id_cliente(conn, id_usuario)
    row = conn.execute(
        """
        SELECT es_principal FROM cliente_direcciones_extra
        WHERE id_direccion = ? AND id_cliente = ? AND COALESCE(activo, true) = true
        """,
        [id_direccion, id_cliente],
    ).fetchone()
    if not row:
        raise ValueError("Dirección no encontrada.")
    conn.execute(
        "UPDATE cliente_direcciones_extra SET activo = false, es_principal = false WHERE id_direccion = ?",
        [id_direccion],
    )
    if bool(row[0]):
        otra = conn.execute(
            """
            SELECT id_direccion, direccion, pais FROM cliente_direcciones_extra
            WHERE id_cliente = ? AND COALESCE(activo, true) = true
            ORDER BY id_direccion DESC LIMIT 1
            """,
            [id_cliente],
        ).fetchone()
        if otra:
            conn.execute(
                "UPDATE cliente_direcciones_extra SET es_principal = true WHERE id_direccion = ?",
                [int(otra[0])],
            )
            conn.execute(
                "UPDATE dim_cliente SET direccion = ?, pais = ? WHERE id_cliente = ?",
                [otra[1], otra[2], id_cliente],
            )


# ---------------------------------------------------------------------------
# Contactos
# ---------------------------------------------------------------------------

def listar_contactos(conn: duckdb.DuckDBPyConnection, id_usuario: int) -> list[dict[str, Any]]:
    id_cliente = _id_cliente(conn, id_usuario)
    rows = conn.execute(
        """
        SELECT id_contacto, nombre, cargo, email, telefono
        FROM cliente_contactos WHERE id_cliente = ?
        ORDER BY id_contacto DESC
        """,
        [id_cliente],
    ).fetchall()
    return [
        {
            "id_contacto": int(r[0]),
            "nombre": r[1],
            "cargo": r[2],
            "email": r[3],
            "telefono": r[4],
        }
        for r in rows
    ]


def crear_contacto(
    conn: duckdb.DuckDBPyConnection,
    *,
    id_usuario: int,
    nombre: str,
    cargo: Optional[str],
    email: Optional[str],
    telefono: Optional[str],
) -> dict[str, Any]:
    id_cliente = _id_cliente(conn, id_usuario)
    nom = (nombre or "").strip()
    if len(nom) < 2:
        raise ValueError("El nombre del contacto es obligatorio.")
    nid = _next_id(conn, "cliente_contactos", "id_contacto")
    conn.execute(
        """
        INSERT INTO cliente_contactos (id_contacto, id_cliente, nombre, cargo, email, telefono)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        [nid, id_cliente, nom, (cargo or None), (email or None), (telefono or None)],
    )
    return {
        "id_contacto": nid,
        "nombre": nom,
        "cargo": cargo,
        "email": email,
        "telefono": telefono,
    }


def actualizar_contacto(
    conn: duckdb.DuckDBPyConnection,
    *,
    id_usuario: int,
    id_contacto: int,
    nombre: Optional[str] = None,
    cargo: Optional[str] = None,
    email: Optional[str] = None,
    telefono: Optional[str] = None,
) -> dict[str, Any]:
    id_cliente = _id_cliente(conn, id_usuario)
    if not conn.execute(
        "SELECT 1 FROM cliente_contactos WHERE id_contacto = ? AND id_cliente = ?",
        [id_contacto, id_cliente],
    ).fetchone():
        raise ValueError("Contacto no encontrado.")
    sets: list[str] = []
    params: list[Any] = []
    if nombre is not None:
        n = nombre.strip()
        if len(n) < 2:
            raise ValueError("El nombre del contacto es obligatorio.")
        sets.append("nombre = ?")
        params.append(n)
    if cargo is not None:
        sets.append("cargo = ?")
        params.append(cargo.strip() or None)
    if email is not None:
        sets.append("email = ?")
        params.append(email.strip() or None)
    if telefono is not None:
        sets.append("telefono = ?")
        params.append(telefono.strip() or None)
    if sets:
        params.extend([id_contacto, id_cliente])
        conn.execute(
            f"UPDATE cliente_contactos SET {', '.join(sets)} WHERE id_contacto = ? AND id_cliente = ?",
            params,
        )
    for c in listar_contactos(conn, id_usuario):
        if c["id_contacto"] == id_contacto:
            return c
    raise ValueError("Contacto no encontrado.")


def eliminar_contacto(conn: duckdb.DuckDBPyConnection, *, id_usuario: int, id_contacto: int) -> None:
    id_cliente = _id_cliente(conn, id_usuario)
    existe = conn.execute(
        "SELECT 1 FROM cliente_contactos WHERE id_contacto = ? AND id_cliente = ?",
        [id_contacto, id_cliente],
    ).fetchone()
    if not existe:
        raise ValueError("Contacto no encontrado.")
    conn.execute(
        "DELETE FROM cliente_contactos WHERE id_contacto = ? AND id_cliente = ?",
        [id_contacto, id_cliente],
    )


# ---------------------------------------------------------------------------
# Preferencias
# ---------------------------------------------------------------------------

def obtener_preferencias(conn: duckdb.DuckDBPyConnection, id_usuario: int) -> dict[str, Any]:
    id_cliente = _id_cliente(conn, id_usuario)
    row = conn.execute(
        "SELECT preferencias_json FROM cliente_preferencias WHERE id_cliente = ?",
        [id_cliente],
    ).fetchone()
    prefs = dict(PREFS_DEFAULT)
    if row and row[0]:
        try:
            data = json.loads(row[0]) if isinstance(row[0], str) else dict(row[0])
            prefs.update({k: data[k] for k in PREFS_DEFAULT if k in data})
        except Exception:
            pass
    return prefs


def guardar_preferencias(
    conn: duckdb.DuckDBPyConnection,
    *,
    id_usuario: int,
    preferencias: dict[str, Any],
) -> dict[str, Any]:
    id_cliente = _id_cliente(conn, id_usuario)
    merged = dict(PREFS_DEFAULT)
    merged.update({k: preferencias[k] for k in PREFS_DEFAULT if k in preferencias})
    merged["notif_pedidos"] = bool(merged["notif_pedidos"])
    merged["notif_promociones"] = bool(merged["notif_promociones"])
    merged["notif_stock"] = bool(merged["notif_stock"])
    moneda = str(merged.get("moneda_preferida") or "USD").upper()
    if moneda not in ("USD", "EUR", "PEN", "MXN"):
        moneda = "USD"
    merged["moneda_preferida"] = moneda
    payload = json.dumps(merged, ensure_ascii=False)
    existe = conn.execute(
        "SELECT 1 FROM cliente_preferencias WHERE id_cliente = ?", [id_cliente]
    ).fetchone()
    if existe:
        conn.execute(
            "UPDATE cliente_preferencias SET preferencias_json = ? WHERE id_cliente = ?",
            [payload, id_cliente],
        )
    else:
        conn.execute(
            "INSERT INTO cliente_preferencias (id_cliente, preferencias_json) VALUES (?, ?)",
            [id_cliente, payload],
        )
    return merged


def resumen_cuenta(conn: duckdb.DuckDBPyConnection, id_usuario: int) -> dict[str, Any]:
    data = obtener_usuario_y_cliente(conn, id_usuario=id_usuario)
    if not data:
        raise ValueError("Usuario no encontrado.")
    return {
        **data,
        "lista_precio": listas_precio_service.info_lista_cliente(
            conn, data.get("cliente", {}).get("id_cliente")
        ),
        "direcciones": listar_direcciones(conn, id_usuario),
        "contactos": listar_contactos(conn, id_usuario),
        "preferencias": obtener_preferencias(conn, id_usuario),
    }


def estimar_envio_cliente(
    conn: duckdb.DuckDBPyConnection,
    *,
    id_usuario: int,
    pais: Optional[str] = None,
) -> dict[str, Any]:
    """Estima zona/tarifa y transportistas según país de entrega del cliente."""
    from shared.services.logistica_envio import estimar_envio_por_pais

    if not pais:
        dirs = listar_direcciones(conn, id_usuario)
        principal = next((d for d in dirs if d.get("es_principal") and d.get("tipo") in ("envio", "ambos")), None)
        if not principal:
            principal = next((d for d in dirs if d.get("tipo") in ("envio", "ambos")), None)
        pais = (principal or {}).get("pais") or None
        if not pais:
            data = obtener_usuario_y_cliente(conn, id_usuario=id_usuario)
            pais = (data or {}).get("cliente", {}).get("pais")
    return estimar_envio_por_pais(conn, pais=pais)
