"""
Catálogo canónico de permisos del panel ERP.
Debe coincidir con nav.js, app.js (PAGE_PERM_DEFAULT) y require_perm en main.py.
"""

from __future__ import annotations

from typing import Any

# (codigo, descripcion corta, grupo menú, páginas que habilita)
PERMISOS_CATALOGO: list[tuple[str, str, str, str]] = [
    (
        "mod.dashboard",
        "Panel ejecutivo",
        "Dirección",
        "Panel ejecutivo, Inteligencia de datos",
    ),
    (
        "mod.estrategia",
        "Estrategia e IA",
        "Dirección",
        "Estrategia, cuadro de mando y proyecciones",
    ),
    (
        "mod.operaciones",
        "Pedidos B2B",
        "Comercial",
        "Pedidos del portal y centro operaciones",
    ),
    (
        "mod.ventas",
        "Ventas y rentabilidad",
        "Comercial / Informes",
        "Ventas históricas, Rentabilidad",
    ),
    (
        "mod.clientes",
        "Clientes",
        "Comercial",
        "Clientes y cuentas por cobrar",
    ),
    (
        "mod.catalogo",
        "Catálogo",
        "Comercial / Sistema",
        "Catálogo, regiones, países, canales y categorías maestras",
    ),
    (
        "mod.marketing",
        "Marketing portal",
        "Comercial",
        "Banners y promociones del portal B2B",
    ),
    (
        "mod.inventario",
        "Inventario",
        "Operaciones",
        "Stock, kardex y alertas",
    ),
    (
        "mod.compras",
        "Compras",
        "Operaciones",
        "Proveedores, órdenes de compra y recepciones",
    ),
    (
        "mod.logistica",
        "Logística",
        "Operaciones",
        "Transportistas, envíos y tracking",
    ),
    (
        "mod.finanzas",
        "Finanzas",
        "Operaciones",
        "Contabilidad, CxP y comprobantes",
    ),
    (
        "mod.reportes",
        "Centro de informes",
        "Informes",
        "Informes PDF/CSV, analytics y Generador / ETL",
    ),
    (
        "mod.gobierno",
        "Usuarios y configuración",
        "Sistema",
        "Usuarios, roles, configuración y auditoría",
    ),
]

ROLES_STAFF_DEFAULT: list[tuple[str, str]] = [
    ("vendedor", "Gestión de ventas y pedidos"),
    ("almacen", "Gestión de inventario y compras"),
    ("gerente", "Informes, analítica y rentabilidad"),
]

ROLES_PERMISOS_DEFAULT: dict[str, list[str]] = {
    "admin": [p[0] for p in PERMISOS_CATALOGO],
    "vendedor": ["mod.dashboard", "mod.ventas", "mod.clientes", "mod.reportes"],
    "almacen": [
        "mod.dashboard",
        "mod.inventario",
        "mod.compras",
        "mod.operaciones",
        "mod.logistica",
        "mod.catalogo",
        "mod.reportes",
    ],
    "gerente": [
        "mod.dashboard",
        "mod.reportes",
        "mod.ventas",
    ],
}

USUARIO_GERENTE_DEMO = (
    "gerente@globmarket.com",
    "Gerente Informes",
)


def sincronizar_permisos_catalogo(conn) -> int:
    """Inserta o actualiza permisos del catálogo. Devuelve cuántos se upsertaron."""
    n = 0
    for codigo, descripcion, _grupo, paginas in PERMISOS_CATALOGO:
        desc_full = f"{descripcion} — {paginas}"
        conn.execute(
            """
            INSERT INTO permisos (codigo, descripcion)
            SELECT ?, ?
            WHERE NOT EXISTS (SELECT 1 FROM permisos WHERE codigo = ?)
            """,
            [codigo, desc_full, codigo],
        )
        conn.execute(
            "UPDATE permisos SET descripcion = ? WHERE codigo = ?",
            [desc_full, codigo],
        )
        n += 1
    return n


def reparar_roles_sin_id(conn) -> int:
    """Asigna id_rol a filas legacy creadas sin PK (p. ej. rol custom desde UI antigua)."""
    rows = conn.execute("SELECT nombre FROM roles WHERE id_rol IS NULL").fetchall()
    n = 0
    for (nombre,) in rows:
        nxt = int(conn.execute("SELECT COALESCE(MAX(id_rol), 0) + 1 FROM roles").fetchone()[0])
        conn.execute(
            "UPDATE roles SET id_rol = ? WHERE nombre = ? AND id_rol IS NULL",
            [nxt, nombre],
        )
        n += 1
    return n


def _asegurar_rol(conn, nombre: str, descripcion: str) -> None:
    row = conn.execute("SELECT id_rol FROM roles WHERE nombre = ?", [nombre]).fetchone()
    if row:
        if row[0] is None:
            nxt = int(conn.execute("SELECT COALESCE(MAX(id_rol), 0) + 1 FROM roles").fetchone()[0])
            conn.execute("UPDATE roles SET id_rol = ? WHERE nombre = ?", [nxt, nombre])
        conn.execute(
            "UPDATE roles SET descripcion = ? WHERE nombre = ? AND COALESCE(descripcion, '') = ''",
            [descripcion, nombre],
        )
        return
    nxt = int(conn.execute("SELECT COALESCE(MAX(id_rol), 0) + 1 FROM roles").fetchone()[0])
    conn.execute(
        "INSERT INTO roles (id_rol, nombre, descripcion) VALUES (?, ?, ?)",
        [nxt, nombre, descripcion],
    )


def sincronizar_roles_staff(conn) -> None:
    for nombre, descripcion in ROLES_STAFF_DEFAULT:
        _asegurar_rol(conn, nombre, descripcion)


def asignar_permisos_rol_nombre(conn, rol: str, codigos: list[str]) -> int:
    row = conn.execute("SELECT id_rol FROM roles WHERE nombre = ?", [rol]).fetchone()
    if not row:
        return 0
    id_rol = int(row[0])
    conn.execute("DELETE FROM rol_permiso WHERE id_rol = ?", [id_rol])
    n = 0
    for codigo in codigos:
        prow = conn.execute("SELECT id_permiso FROM permisos WHERE codigo = ?", [codigo]).fetchone()
        if not prow:
            continue
        conn.execute(
            """
            INSERT INTO rol_permiso (id_rol, id_permiso)
            SELECT ?, ?
            WHERE NOT EXISTS (
              SELECT 1 FROM rol_permiso WHERE id_rol = ? AND id_permiso = ?
            )
            """,
            [id_rol, int(prow[0]), id_rol, int(prow[0])],
        )
        n += 1
    return n


def sincronizar_roles_permisos_default(conn, *, roles: list[str] | None = None) -> dict[str, int]:
    """Reaplica permisos por defecto a los roles indicados (p. ej. gerente recién creado)."""
    objetivos = roles or list(ROLES_PERMISOS_DEFAULT.keys())
    out: dict[str, int] = {}
    for rol in objetivos:
        codigos = ROLES_PERMISOS_DEFAULT.get(rol)
        if not codigos:
            continue
        out[rol] = asignar_permisos_rol_nombre(conn, rol, codigos)
    return out


def permiso_a_dict(row: tuple[Any, ...]) -> dict[str, Any]:
    codigo = str(row[1])
    meta = next((p for p in PERMISOS_CATALOGO if p[0] == codigo), None)
    grupo = meta[2] if meta else "Otros"
    paginas = meta[3] if meta else ""
    label = meta[1] if meta else codigo.replace("mod.", "")
    return {
        "id_permiso": int(row[0]),
        "codigo": codigo,
        "descripcion": row[2],
        "grupo": grupo,
        "label": label,
        "paginas": paginas,
    }


def reparar_usuarios_sin_id(conn) -> int:
    rows = conn.execute("SELECT email FROM usuarios WHERE id_usuario IS NULL").fetchall()
    n = 0
    for (email,) in rows:
        nxt = int(conn.execute("SELECT COALESCE(MAX(id_usuario), 0) + 1 FROM usuarios").fetchone()[0])
        conn.execute(
            "UPDATE usuarios SET id_usuario = ? WHERE email = ? AND id_usuario IS NULL",
            [nxt, email],
        )
        n += 1
    return n


def sincronizar_gobierno_demo(conn, *, password_hash_fn) -> dict[str, Any]:
    """
    Sincroniza catálogo, rol gerente y usuario demo.
    `password_hash_fn` recibe la contraseña en claro y devuelve el hash.
    """
    reparar_roles_sin_id(conn)
    sincronizar_permisos_catalogo(conn)
    sincronizar_roles_staff(conn)
    perms = sincronizar_roles_permisos_default(conn, roles=["gerente"])

    email, nombre = USUARIO_GERENTE_DEMO
    existe = conn.execute("SELECT id_usuario FROM usuarios WHERE email = ?", [email]).fetchone()
    if not existe:
        nxt = int(conn.execute("SELECT COALESCE(MAX(id_usuario), 0) + 1 FROM usuarios").fetchone()[0])
        conn.execute(
            """
            INSERT INTO usuarios (id_usuario, email, password_hash, rol, activo, nombre)
            VALUES (?, ?, ?, 'gerente', true, ?)
            """,
            [nxt, email, password_hash_fn("12345678"), nombre],
        )
    else:
        reparar_usuarios_sin_id(conn)
        conn.execute(
            """
            UPDATE usuarios
            SET rol = 'gerente', activo = true, nombre = ?, password_hash = ?
            WHERE email = ?
            """,
            [nombre, password_hash_fn("12345678"), email],
        )
    reparar_usuarios_sin_id(conn)
    return {"permisos_catalogo": len(PERMISOS_CATALOGO), "gerente_permisos": perms.get("gerente", 0), "email": email}
