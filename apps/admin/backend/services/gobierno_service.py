"""
services/gobierno_service.py — CRUD de usuarios, roles y permisos (gobierno de acceso).

Trabaja sobre las tablas `usuarios`, `roles`, `permisos` y `rol_permiso`.
El rol 'admin' es protegido: nunca se elimina ni se le quitan permisos.
"""

from __future__ import annotations

from typing import Any

import duckdb

from backend.services.auth_service import ROLES_NO_PANEL, hash_password
from backend.services.auditoria_service import registrar_auditoria

ROL_PROTEGIDO = "admin"


def _validar_rol_usuario(conn: duckdb.DuckDBPyConnection, rol: str) -> None:
    """Un usuario del panel debe tener un rol que no sea 'cliente' y que exista en roles."""
    if rol in ROLES_NO_PANEL:
        raise ValueError("El rol 'cliente' no puede usarse en el panel administrativo.")
    row = conn.execute("SELECT 1 FROM roles WHERE nombre = ?", [rol]).fetchone()
    if not row:
        raise ValueError(f"El rol '{rol}' no existe. Cree el rol primero o elija otro.")


def _secuencia_existe(conn: duckdb.DuckDBPyConnection, nombre: str) -> bool:
    try:
        row = conn.execute(
            """
            SELECT COUNT(*) FROM information_schema.sequences
            WHERE sequence_schema = 'main' AND sequence_name = ?
            """,
            [nombre],
        ).fetchone()
        return bool(row and row[0])
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Usuarios
# ---------------------------------------------------------------------------

def listar_usuarios_staff(
    conn: duckdb.DuckDBPyConnection,
    *,
    q: str = "",
    rol: str = "",
    activo: Any = None,
    limit: int = 100,
    incluir_clientes: bool = False,
) -> list[dict[str, Any]]:
    where: list[str] = []
    params: list[Any] = []
    if not incluir_clientes:
        where.append("u.rol <> 'cliente'")
    if q:
        where.append("(u.email LIKE ? OR COALESCE(u.nombre, '') LIKE ?)")
        params.extend([f"%{q}%", f"%{q}%"])
    if rol:
        where.append("u.rol = ?")
        params.append(rol)
    if activo is not None:
        where.append("u.activo = ?")
        params.append(1 if activo else 0)
    where_sql = ("WHERE " + " AND ".join(where)) if where else ""
    rows = conn.execute(
        f"""
        SELECT u.id_usuario, u.email, COALESCE(u.nombre, ''), u.rol, u.activo, u.fecha_registro,
               u.id_region, r.region
        FROM usuarios u
        LEFT JOIN dim_region r ON r.id_region = u.id_region
        {where_sql}
        ORDER BY u.id_usuario
        LIMIT ?
        """,
        [*params, limit],
    ).fetchall()
    return [
        {
            "id_usuario": int(r[0]),
            "email": r[1],
            "nombre": r[2],
            "rol": r[3],
            "activo": bool(r[4]),
            "fecha_registro": str(r[5]) if r[5] is not None else None,
            "id_region": int(r[6]) if r[6] is not None else None,
            "region": r[7],
        }
        for r in rows
    ]


def _validar_region(conn: duckdb.DuckDBPyConnection, id_region: Optional[int]) -> None:
    if id_region is None:
        return
    row = conn.execute("SELECT 1 FROM dim_region WHERE id_region = ?", [id_region]).fetchone()
    if not row:
        raise ValueError("La región indicada no existe.")


def crear_usuario_staff(
    conn: duckdb.DuckDBPyConnection,
    *,
    email: str,
    password: str,
    rol: str,
    nombre: str = "",
    id_region: Optional[int] = None,
    id_usuario_actor: Any = None,
) -> dict[str, Any]:
    email = email.strip().lower()
    _validar_rol_usuario(conn, rol)
    _validar_region(conn, id_region)
    exists = conn.execute(
        "SELECT 1 FROM usuarios WHERE email = ?", [email]
    ).fetchone()
    if exists:
        raise ValueError("Ya existe un usuario con ese correo.")
    # Sincroniza la secuencia con el máximo actual para no colisionar con IDs
    # asignados manualmente (MAX+1) ni con los que genera el portal vía nextval.
    if _secuencia_existe(conn, "seq_usuarios"):
        conn.execute(
            "SELECT setval('seq_usuarios', (SELECT COALESCE(MAX(id_usuario), 0) FROM usuarios))"
        )
        nxt_value = conn.execute("SELECT nextval('seq_usuarios')").fetchone()[0]
    else:
        nxt_value = conn.execute(
            "SELECT COALESCE(MAX(id_usuario), 0) + 1 FROM usuarios"
        ).fetchone()[0]
    nxt = nxt_value
    conn.execute(
        """
        INSERT INTO usuarios (id_usuario, email, password_hash, rol, activo, id_region)
        VALUES (?, ?, ?, ?, true, ?)
        """,
        [nxt, email, hash_password(password), rol, id_region],
    )
    if nombre:
        conn.execute(
            "UPDATE usuarios SET nombre = ? WHERE id_usuario = ?",
            [nombre, nxt],
        )
    registrar_auditoria(
        conn,
        id_usuario=id_usuario_actor,
        entidad="usuario",
        entidad_id=nxt,
        accion="crear",
        valor_nuevo={"email": email, "rol": rol, "id_region": id_region},
    )
    return {"id_usuario": int(nxt), "email": email, "rol": rol, "id_region": id_region}


def actualizar_usuario_staff(
    conn: duckdb.DuckDBPyConnection,
    *,
    id_usuario: int,
    email: str | None = None,
    rol: str | None = None,
    nombre: str | None = None,
    password: str | None = None,
    activo: bool | None = None,
    id_region: int | str | None = None,
    id_usuario_actor: Any = None,
) -> dict[str, Any]:
    row = conn.execute(
        "SELECT id_usuario, email, rol, activo, id_region FROM usuarios WHERE id_usuario = ?",
        [id_usuario],
    ).fetchone()
    if not row:
        raise ValueError("Usuario no encontrado.")
    viejo = {"email": row[1], "rol": row[2], "activo": bool(row[3]), "id_region": row[4]}
    nuevo = dict(viejo)
    sets: list[str] = []
    params: list[Any] = []
    if rol is not None:
        _validar_rol_usuario(conn, rol)
        if viejo["rol"] == ROL_PROTEGIDO:
            raise ValueError("No se puede cambiar el rol del administrador del sistema.")
        sets.append("rol = ?")
        params.append(rol)
        nuevo["rol"] = rol
    if email is not None and email != viejo["email"]:
        otro = conn.execute(
            "SELECT 1 FROM usuarios WHERE email = ? AND id_usuario <> ?",
            [email, id_usuario],
        ).fetchone()
        if otro:
            raise ValueError("Ya existe un usuario con ese correo.")
        sets.append("email = ?")
        params.append(email)
        nuevo["email"] = email
    if nombre is not None:
        sets.append("nombre = ?")
        params.append(nombre)
        nuevo["nombre"] = nombre
    if password is not None:
        sets.append("password_hash = ?")
        params.append(hash_password(password))
    if activo is not None:
        sets.append("activo = ?")
        params.append(1 if activo else 0)
        nuevo["activo"] = activo
    if id_region is not None:
        id_region_val = None
        if str(id_region).strip() != "":
            id_region_val = int(id_region)
            _validar_region(conn, id_region_val)
        sets.append("id_region = ?")
        params.append(id_region_val)
        nuevo["id_region"] = id_region_val
    if not sets:
        return {"id_usuario": id_usuario, **_vacio_usuario(nuevo)}
    params.append(id_usuario)
    conn.execute(f"UPDATE usuarios SET {', '.join(sets)} WHERE id_usuario = ?", params)
    registrar_auditoria(
        conn,
        id_usuario=id_usuario_actor,
        entidad="usuario",
        entidad_id=id_usuario,
        accion="editar",
        valor_anterior=viejo,
        valor_nuevo=nuevo,
    )
    return {"id_usuario": id_usuario, **nuevo}


def desactivar_usuario_staff(
    conn: duckdb.DuckDBPyConnection,
    *,
    id_usuario: int,
    id_usuario_actor: Any = None,
) -> dict[str, Any]:
    row = conn.execute(
        "SELECT id_usuario, email, rol FROM usuarios WHERE id_usuario = ?",
        [id_usuario],
    ).fetchone()
    if not row:
        raise ValueError("Usuario no encontrado.")
    if int(row[0]) == int(id_usuario_actor or 0):
        raise ValueError("No puede desactivar su propia cuenta.")
    if row[2] == ROL_PROTEGIDO:
        raise ValueError("La cuenta del administrador no se puede desactivar.")
    conn.execute(
        "UPDATE usuarios SET activo = false WHERE id_usuario = ?",
        [id_usuario],
    )
    registrar_auditoria(
        conn,
        id_usuario=id_usuario_actor,
        entidad="usuario",
        entidad_id=id_usuario,
        accion="desactivar",
        valor_nuevo={"email": row[1], "rol": row[2]},
    )
    return {"id_usuario": int(row[0]), "email": row[1], "activo": False}


def _vacio_usuario(v: dict[str, Any]) -> dict[str, Any]:
    return {
        "email": v.get("email"),
        "rol": v.get("rol"),
        "nombre": v.get("nombre"),
        "activo": v.get("activo"),
        "id_region": v.get("id_region"),
    }


# ---------------------------------------------------------------------------
# Roles y permisos
# ---------------------------------------------------------------------------

def listar_roles_detalle(conn: duckdb.DuckDBPyConnection) -> list[dict[str, Any]]:
    from shared.database.permisos_catalogo import reparar_roles_sin_id

    reparar_roles_sin_id(conn)
    rows = conn.execute(
        """
        SELECT r.id_rol, r.nombre, r.descripcion,
               (SELECT COUNT(*) FROM usuarios u WHERE u.rol = r.nombre) AS n_usuarios
        FROM roles r
        ORDER BY r.id_rol
        """
    ).fetchall()
    resultado = []
    for r in rows:
        if r[0] is None:
            continue
        codigos = [
            str(x[0])
            for x in conn.execute(
                """
                SELECT p.codigo FROM permisos p
                JOIN rol_permiso rp ON rp.id_permiso = p.id_permiso
                WHERE rp.id_rol = ?
                """,
                [r[0]],
            ).fetchall()
        ]
        resultado.append(
            {
                "id_rol": int(r[0]),
                "nombre": r[1],
                "descripcion": r[2],
                "usuarios": int(r[3]),
                "protegido": r[1] == ROL_PROTEGIDO,
                "permisos": codigos,
            }
        )
    return resultado


def listar_permisos(conn: duckdb.DuckDBPyConnection) -> list[dict[str, Any]]:
    from shared.database.permisos_catalogo import permiso_a_dict, sincronizar_permisos_catalogo

    sincronizar_permisos_catalogo(conn)
    rows = conn.execute(
        """
        SELECT id_permiso, codigo, descripcion FROM permisos
        ORDER BY
          CASE codigo
            WHEN 'mod.dashboard' THEN 1
            WHEN 'mod.estrategia' THEN 2
            WHEN 'mod.operaciones' THEN 3
            WHEN 'mod.ventas' THEN 4
            WHEN 'mod.clientes' THEN 5
            WHEN 'mod.catalogo' THEN 6
            WHEN 'mod.marketing' THEN 7
            WHEN 'mod.inventario' THEN 8
            WHEN 'mod.compras' THEN 9
            WHEN 'mod.logistica' THEN 10
            WHEN 'mod.finanzas' THEN 11
            WHEN 'mod.reportes' THEN 12
            WHEN 'mod.gobierno' THEN 13
            ELSE 99
          END,
          id_permiso
        """
    ).fetchall()
    return [permiso_a_dict(r) for r in rows]


def crear_rol(
    conn: duckdb.DuckDBPyConnection,
    *,
    nombre: str,
    descripcion: str = "",
    id_usuario_actor: Any = None,
) -> dict[str, Any]:
    nombre = nombre.strip()
    if not nombre:
        raise ValueError("El nombre del rol es obligatorio.")
    if nombre in ("admin", "vendedor", "almacen", "cliente"):
        raise ValueError(f"'{nombre}' es un rol reservado del sistema.")
    existe = conn.execute("SELECT 1 FROM roles WHERE nombre = ?", [nombre]).fetchone()
    if existe:
        raise ValueError("Ya existe un rol con ese nombre.")
    nxt = conn.execute("SELECT COALESCE(MAX(id_rol), 0) + 1 FROM roles").fetchone()[0]
    conn.execute(
        "INSERT INTO roles (id_rol, nombre, descripcion) VALUES (?, ?, ?)",
        [nxt, nombre, descripcion],
    )
    registrar_auditoria(
        conn,
        id_usuario=id_usuario_actor,
        entidad="rol",
        entidad_id=nxt,
        accion="crear",
        valor_nuevo={"nombre": nombre, "descripcion": descripcion},
    )
    return {"id_rol": int(nxt), "nombre": nombre, "descripcion": descripcion, "protegido": False, "permisos": []}


def actualizar_rol(
    conn: duckdb.DuckDBPyConnection,
    *,
    id_rol: int,
    nombre: str | None = None,
    descripcion: str | None = None,
    id_usuario_actor: Any = None,
) -> dict[str, Any]:
    row = conn.execute("SELECT id_rol, nombre, descripcion FROM roles WHERE id_rol = ?", [id_rol]).fetchone()
    if not row:
        raise ValueError("Rol no encontrado.")
    old_name, old_desc = row[1], row[2]
    if old_name == ROL_PROTEGIDO:
        raise ValueError("El rol Administrador es protegido y no se puede modificar.")
    nuevo_nombre, nueva_desc = old_name, old_desc
    if nombre is not None and nombre.strip() and nombre.strip() != old_name:
        if nombre.strip() in ("admin", "vendedor", "almacen", "cliente"):
            raise ValueError(f"'{nombre}' es un rol reservado del sistema.")
        if conn.execute("SELECT 1 FROM roles WHERE nombre = ?", [nombre]).fetchone():
            raise ValueError("Ya existe un rol con ese nombre.")
        conn.execute("UPDATE usuarios SET rol = ? WHERE rol = ?", [nombre, old_name])
        conn.execute("UPDATE roles SET nombre = ? WHERE id_rol = ?", [nombre, id_rol])
        nuevo_name = nombre
    if descripcion is not None:
        conn.execute("UPDATE roles SET descripcion = ? WHERE id_rol = ?", [descripcion, id_rol])
        nueva_desc = descripcion
    registrar_auditoria(
        conn,
        id_usuario=id_usuario_actor,
        entidad="rol",
        entidad_id=id_rol,
        accion="editar",
        valor_anterior={"nombre": old_name, "descripcion": old_desc},
        valor_nuevo={"nombre": nuevo_name, "descripcion": nueva_desc},
    )
    return {"id_rol": id_rol, "nombre": nuevo_name, "descripcion": nueva_desc}


def eliminar_rol(
    conn: duckdb.DuckDBPyConnection,
    *,
    id_rol: int,
    id_usuario_actor: Any = None,
) -> dict[str, Any]:
    row = conn.execute("SELECT id_rol, nombre FROM roles WHERE id_rol = ?", [id_rol]).fetchone()
    if not row:
        raise ValueError("Rol no encontrado.")
    if row[1] == ROL_PROTEGIDO:
        raise ValueError("El rol Administrador no se puede eliminar.")
    n_usuarios = conn.execute(
        "SELECT COUNT(*) FROM usuarios WHERE rol = ?", [row[1]]
    ).fetchone()[0]
    if n_usuarios:
        raise ValueError(f"No se puede eliminar: {n_usuarios} usuario(s) lo usan.")
    conn.execute("DELETE FROM rol_permiso WHERE id_rol = ?", [id_rol])
    conn.execute("DELETE FROM roles WHERE id_rol = ?", [id_rol])
    registrar_auditoria(
        conn,
        id_usuario=id_usuario_actor,
        entidad="rol",
        entidad_id=id_rol,
        accion="eliminar",
        valor_nuevo={"nombre": row[1]},
    )
    return {"eliminado": True, "id_rol": int(row[0])}


def asignar_permisos_rol(
    conn: duckdb.DuckDBPyConnection,
    *,
    id_rol: int,
    codigos: list[str],
    id_usuario_actor: Any = None,
) -> dict[str, Any]:
    row = conn.execute("SELECT id_rol, nombre FROM roles WHERE id_rol = ?", [id_rol]).fetchone()
    if not row:
        raise ValueError("Rol no encontrado.")
    if row[1] == ROL_PROTEGIDO:
        raise ValueError("El rol Administrador siempre tiene todos los permisos.")
    validos = {
        str(x[0]) for x in conn.execute("SELECT codigo FROM permisos").fetchall()
    }
    codigos = [c for c in codigos if c in validos]
    conn.execute("DELETE FROM rol_permiso WHERE id_rol = ?", [id_rol])
    for codigo in codigos:
        conn.execute(
            """
            INSERT INTO rol_permiso (id_rol, id_permiso)
            SELECT ?, p.id_permiso FROM permisos p WHERE p.codigo = ?
            """,
            [id_rol, codigo],
        )
    registrar_auditoria(
        conn,
        id_usuario=id_usuario_actor,
        entidad="rol",
        entidad_id=id_rol,
        accion="permisos",
        valor_nuevo={"permisos": codigos},
    )
    return {"id_rol": int(row[0]), "permisos": codigos, "actualizados": len(codigos)}