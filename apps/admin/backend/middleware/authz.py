"""
middleware/authz.py — Dependencias de autorización por rol para el panel admin.

Uso en routers:

    from backend.middleware.authz import require_staff, require_admin

    @router.get("/", dependencies=[Depends(require_staff)])
    def listar(...): ...

`get_current_staff` devuelve el usuario autenticado (dict) para auditoría.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import Depends, Header, HTTPException, status

from backend.database import get_connection
from backend.services.auth_service import ROLES_NO_PANEL, decodificar_token, obtener_usuario


def _extraer_token(authorization: str | None) -> str:
    if not authorization:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Falta header Authorization.")
    raw = authorization.strip()
    if not raw.lower().startswith("bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token Bearer requerido.")
    token = raw[7:].strip()
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token vacío.")
    return token


def _permisos_de_rol(conn, rol: str) -> set[str]:
    """Permisos vigentes de un rol (tablas permisos + rol_permiso + roles)."""
    import duckdb  # noqa: F401  (tipado)
    rows = conn.execute(
        """
        SELECT p.codigo
        FROM permisos p
        JOIN rol_permiso rp ON rp.id_permiso = p.id_permiso
        JOIN roles r ON r.id_rol = rp.id_rol
        WHERE r.nombre = ?
        """,
        [rol],
    ).fetchall()
    return {str(r[0]) for r in rows}


def get_current_staff(
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    """Valida el JWT y devuelve el usuario staff actual (con sus permisos)."""
    token = _extraer_token(authorization)
    try:
        payload = decodificar_token(token)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token inválido o expirado.")

    sub = payload.get("sub")
    if not sub:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token inválido (sub ausente).")
    try:
        id_usuario = int(sub)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token inválido (sub no numérico).")

    with get_connection() as conn:
        usuario = obtener_usuario(conn, id_usuario=id_usuario)
        if usuario and bool(usuario.get("activo")):
            usuario["permisos"] = sorted(_permisos_de_rol(conn, usuario["rol"]))

    if not usuario or not usuario["activo"]:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Usuario no encontrado o inactivo.")
    if usuario["rol"] in ROLES_NO_PANEL:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Acceso restringido al personal autorizado.")
    return usuario


def require_staff(usuario: dict[str, Any] = Depends(get_current_staff)) -> dict[str, Any]:
    """Cualquier rol de staff (admin, vendedor, almacen)."""
    return usuario


def require_admin(usuario: dict[str, Any] = Depends(get_current_staff)) -> dict[str, Any]:
    """Solo rol admin."""
    if usuario["rol"] != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Se requiere rol administrador.")
    return usuario


def require_rol(*roles: str):
    """Factory: dependencia que exige uno de los roles dados."""

    def _dep(usuario: dict[str, Any] = Depends(get_current_staff)) -> dict[str, Any]:
        if usuario["rol"] not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Se requiere uno de los roles: {', '.join(roles)}.",
            )
        return usuario

    return _dep


def require_perm(*codigos: str):
    """
    Factory: dependencia que exige al menos uno de los permisos dados.

    El rol 'admin' tiene todos los permisos de forma implícita (no depende
    de la tabla rol_permiso), por lo que nunca se ve restringido.
    """

    def _dep(usuario: dict[str, Any] = Depends(get_current_staff)) -> dict[str, Any]:
        if usuario["rol"] == "admin":
            return usuario
        if not codigos or not any(c in usuario.get("permisos", ()) for c in codigos):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="No tiene permiso para acceder a este módulo.",
            )
        return usuario

    return _dep
