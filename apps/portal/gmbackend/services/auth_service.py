from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import duckdb
from jose import JWTError, jwt
from passlib.context import CryptContext

from gmbackend.config import Settings
from shared.database.ids import siguiente_id

logger = logging.getLogger(__name__)

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verificar_password(password: str, password_hash: str) -> bool:
    return pwd_context.verify(password, password_hash)


def crear_access_token(
    *,
    settings: Settings,
    id_usuario: int,
    rol: str,
    expires_minutes: int,
) -> str:
    ahora = datetime.now(timezone.utc)
    exp = ahora + timedelta(minutes=expires_minutes)
    payload = {
        "sub": str(id_usuario),
        "rol": rol,
        "iat": int(ahora.timestamp()),
        "exp": int(exp.timestamp()),
    }
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


def decodificar_token(settings: Settings, token: str) -> dict[str, Any]:
    try:
        payload = jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])
        return payload
    except JWTError as e:
        raise ValueError("Token inválido o expirado.") from e


def _pais_valido(conn: duckdb.DuckDBPyConnection, pais: str) -> bool:
    """El país debe existir en el catálogo de países (dim_country)."""
    row = conn.execute(
        "SELECT 1 FROM dim_country WHERE country IS NOT NULL AND lower(country) = lower(?)",
        [pais],
    ).fetchone()
    return bool(row)


def registrar_cliente(
    conn: duckdb.DuckDBPyConnection,
    *,
    email: str,
    password: str,
    nombre_empresa: str,
    pais: str,
    telefono: Optional[str],
    direccion: Optional[str],
) -> dict[str, Any]:
    """
    Registra un usuario tipo cliente + su ficha dim_cliente.
    """
    logger.info("Registro de nuevo cliente B2B: %s", email)

    if not _pais_valido(conn, pais):
        raise ValueError("El país no es válido. Selecciona un país de la lista.")

    conn.execute("BEGIN TRANSACTION")
    try:
        password_hash = hash_password(password)

        id_usuario = siguiente_id(conn, "usuarios")
        conn.execute(
            """
            INSERT INTO usuarios (id_usuario, email, password_hash, rol, activo, fecha_registro)
            VALUES (?, ?, ?, 'cliente', true, current_timestamp)
            """,
            [id_usuario, email, password_hash],
        )
        usuario = conn.execute(
            "SELECT id_usuario, email, rol, activo, fecha_registro FROM usuarios WHERE id_usuario = ?",
            [id_usuario],
        ).fetchone()
        if not usuario:
            raise RuntimeError("No se pudo crear el usuario.")

        id_cliente = siguiente_id(conn, "dim_cliente")
        conn.execute(
            """
            INSERT INTO dim_cliente (id_cliente, id_usuario, nombre_empresa, pais, telefono, direccion)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            [id_cliente, id_usuario, nombre_empresa, pais, telefono, direccion],
        )
        cliente = conn.execute(
            """
            SELECT id_cliente, id_usuario, nombre_empresa, pais, telefono, direccion
            FROM dim_cliente WHERE id_cliente = ?
            """,
            [id_cliente],
        ).fetchone()
        if not cliente:
            raise RuntimeError("No se pudo crear el cliente.")

        conn.execute("COMMIT")
        fecha_reg = usuario[4] or datetime.now(timezone.utc)
        return {
            "usuario": {
                "id_usuario": int(usuario[0]),
                "email": usuario[1],
                "rol": usuario[2],
                "activo": bool(usuario[3]),
                "fecha_registro": fecha_reg,
            },
            "cliente": {
                "id_cliente": int(cliente[0]),
                "id_usuario": int(cliente[1]),
                "nombre_empresa": cliente[2],
                "pais": cliente[3],
                "telefono": cliente[4],
                "direccion": cliente[5],
            },
        }
    except Exception:
        conn.execute("ROLLBACK")
        logger.exception("Error registrando cliente: %s", email)
        raise


def autenticar_usuario(
    conn: duckdb.DuckDBPyConnection,
    *,
    email: str,
    password: str,
) -> dict[str, Any] | None:
    row = _buscar_usuario(conn, email)
    if not row:
        return None

    if not bool(row[4]):
        return {"deshabilitado": True}

    if not verificar_password(password, row[2]):
        return None

    if row[3] != "cliente":
        return {"rol_invalido": True}

    return {
        "id_usuario": int(row[0]),
        "email": row[1],
        "rol": row[3],
        "activo": bool(row[4]),
        "fecha_registro": row[5],
    }


def _buscar_usuario(
    conn: duckdb.DuckDBPyConnection,
    email: str,
) -> tuple | None:
    """Devuelve la fila de usuarios; None si no existe el email."""
    conn.execute(
        """
        SELECT id_usuario, email, password_hash, rol, activo, fecha_registro
        FROM usuarios
        WHERE email = ?
        """,
        [email],
    )
    return conn.fetchone()


def obtener_usuario_y_cliente(
    conn: duckdb.DuckDBPyConnection,
    *,
    id_usuario: int,
) -> dict[str, Any] | None:
    conn.execute(
        """
        SELECT id_usuario, email, rol, activo, fecha_registro
        FROM usuarios
        WHERE id_usuario = ?
        """,
        [id_usuario],
    )
    u = conn.fetchone()
    if not u:
        return None

    conn.execute(
        """
        SELECT id_cliente, id_usuario, nombre_empresa, pais, telefono, direccion
        FROM dim_cliente
        WHERE id_usuario = ?
        """,
        [id_usuario],
    )
    c = conn.fetchone()

    return {
        "usuario": {
            "id_usuario": int(u[0]),
            "email": u[1],
            "rol": u[2],
            "activo": bool(u[3]),
            "fecha_registro": u[4],
        },
        "cliente": (
            None
            if not c
            else {
                "id_cliente": int(c[0]),
                "id_usuario": int(c[1]),
                "nombre_empresa": c[2],
                "pais": c[3],
                "telefono": c[4],
                "direccion": c[5],
            }
        ),
    }


def actualizar_perfil_cliente(
    conn: duckdb.DuckDBPyConnection,
    *,
    id_usuario: int,
    pais: str,
    telefono: Optional[str],
    direccion: Optional[str],
) -> dict[str, Any]:
    data = obtener_usuario_y_cliente(conn, id_usuario=id_usuario)
    if not data or not data.get("cliente"):
        raise ValueError("La cuenta no tiene ficha de cliente B2B.")

    if not _pais_valido(conn, pais):
        raise ValueError("El país no es válido. Selecciona un país de la lista.")

    id_cliente = data["cliente"]["id_cliente"]
    conn.execute(
        "UPDATE dim_cliente SET pais = ?, telefono = ?, direccion = ? WHERE id_cliente = ?",
        [pais, telefono, direccion, id_cliente],
    )
    return obtener_usuario_y_cliente(conn, id_usuario=id_usuario)

