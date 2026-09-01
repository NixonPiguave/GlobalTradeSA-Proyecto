from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import duckdb
from jose import JWTError, jwt
from passlib.context import CryptContext

from gmbackend.config import Settings

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

    conn.execute("BEGIN TRANSACTION")
    try:
        password_hash = hash_password(password)

        conn.execute(
            """
            INSERT INTO usuarios (email, password_hash, rol, activo)
            VALUES (?, ?, 'cliente', true)
            RETURNING id_usuario, email, rol, activo, fecha_registro
            """,
            [email, password_hash],
        )
        usuario = conn.fetchone()
        if not usuario:
            raise RuntimeError("No se pudo crear el usuario.")

        id_usuario = int(usuario[0])

        conn.execute(
            """
            INSERT INTO dim_cliente (id_usuario, nombre_empresa, pais, telefono, direccion)
            VALUES (?, ?, ?, ?, ?)
            RETURNING id_cliente, id_usuario, nombre_empresa, pais, telefono, direccion
            """,
            [id_usuario, nombre_empresa, pais, telefono, direccion],
        )
        cliente = conn.fetchone()
        if not cliente:
            raise RuntimeError("No se pudo crear el cliente.")

        conn.execute("COMMIT")
        return {
            "usuario": {
                "id_usuario": int(usuario[0]),
                "email": usuario[1],
                "rol": usuario[2],
                "activo": bool(usuario[3]),
                "fecha_registro": usuario[4],
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
    conn.execute(
        """
        SELECT id_usuario, email, password_hash, rol, activo, fecha_registro
        FROM usuarios
        WHERE email = ?
        """,
        [email],
    )
    row = conn.fetchone()
    if not row:
        return None

    if not bool(row[4]):
        return None

    if not verificar_password(password, row[2]):
        return None

    return {
        "id_usuario": int(row[0]),
        "email": row[1],
        "rol": row[3],
        "activo": bool(row[4]),
        "fecha_registro": row[5],
    }


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

