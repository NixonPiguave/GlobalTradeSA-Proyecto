"""
services/auth_service.py — Autenticación de usuarios administrativos (JWT + bcrypt).

Comparte la tabla `usuarios` con el portal B2B; solo roles de staff
(admin, vendedor, almacen) pueden acceder al panel.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import duckdb
from jose import JWTError, jwt
from passlib.context import CryptContext

from backend.logger import get_logger

logger = get_logger(__name__)

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Roles con acceso al panel administrativo. 'cliente' es el único rol del
# portal B2B y queda excluido; cualquier otro rol (admin, vendedor, almacen
# o roles personalizados creados desde Gobierno de acceso) puede entrar.
ROLES_NO_PANEL = {"cliente"}


def _jwt_secret() -> str:
    return os.environ.get("JWT_SECRET", "dev-secret-change-me").strip() or "dev-secret-change-me"


def _jwt_algorithm() -> str:
    return os.environ.get("JWT_ALGORITHM", "HS256").strip() or "HS256"


def _jwt_expire_minutes() -> int:
    raw = os.environ.get("JWT_EXPIRE_MINUTES", "").strip()
    try:
        return int(raw) if raw else 480
    except ValueError:
        return 480


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verificar_password(password: str, password_hash: str) -> bool:
    try:
        return pwd_context.verify(password, password_hash)
    except Exception:
        return False


def crear_access_token(*, id_usuario: int, rol: str) -> str:
    ahora = datetime.now(timezone.utc)
    exp = ahora + timedelta(minutes=_jwt_expire_minutes())
    payload = {
        "sub": str(id_usuario),
        "rol": rol,
        "scope": "admin",
        "iat": int(ahora.timestamp()),
        "exp": int(exp.timestamp()),
    }
    return jwt.encode(payload, _jwt_secret(), algorithm=_jwt_algorithm())


def decodificar_token(token: str) -> dict[str, Any]:
    try:
        return jwt.decode(token, _jwt_secret(), algorithms=[_jwt_algorithm()])
    except JWTError as e:
        raise ValueError("Token inválido o expirado.") from e


def autenticar_staff(
    conn: duckdb.DuckDBPyConnection, *, email: str, password: str
) -> Optional[dict[str, Any]]:
    """Autentica un usuario y valida que tenga rol de staff."""
    from shared.database.permisos_catalogo import reparar_usuarios_sin_id

    reparar_usuarios_sin_id(conn)
    row = conn.execute(
        """
        SELECT id_usuario, email, password_hash, rol, activo
        FROM usuarios WHERE email = ?
        """,
        [email],
    ).fetchone()
    if not row or not bool(row[4]) or row[0] is None:
        return None
    if row[3] in ROLES_NO_PANEL:
        logger.warning("Intento de login admin con rol no autorizado: %s (%s)", email, row[3])
        return None
    if not verificar_password(password, row[2]):
        return None
    return {"id_usuario": int(row[0]), "email": row[1], "rol": row[3], "activo": True}


def obtener_usuario(conn: duckdb.DuckDBPyConnection, *, id_usuario: int) -> Optional[dict[str, Any]]:
    row = conn.execute(
        "SELECT id_usuario, email, rol, activo FROM usuarios WHERE id_usuario = ?",
        [id_usuario],
    ).fetchone()
    if not row:
        return None
    return {
        "id_usuario": int(row[0]),
        "email": row[1],
        "rol": row[2],
        "activo": bool(row[3]),
    }


def listar_roles(conn: duckdb.DuckDBPyConnection) -> list[dict[str, Any]]:
    rows = conn.execute("SELECT id_rol, nombre, descripcion FROM roles ORDER BY id_rol").fetchall()
    return [{"id_rol": int(r[0]), "nombre": r[1], "descripcion": r[2]} for r in rows]
