import sys
sys.path.insert(0, '/app')
from shared.database.init_sistema import _hash_password
from shared.database.permisos_catalogo import sincronizar_gobierno_demo, ROLES_PERMISOS_DEFAULT
import duckdb

conn = duckdb.connect('/app/db/globtrade.duckdb')
res = sincronizar_gobierno_demo(conn, password_hash_fn=_hash_password)
for rol in ('vendedor', 'almacen'):
    for codigo in ROLES_PERMISOS_DEFAULT.get(rol, []):
        conn.execute(
            """
            INSERT INTO rol_permiso (id_rol, id_permiso)
            SELECT r.id_rol, p.id_permiso FROM roles r, permisos p
            WHERE r.nombre = ? AND p.codigo = ?
              AND NOT EXISTS (
                SELECT 1 FROM rol_permiso rp
                WHERE rp.id_rol = r.id_rol AND rp.id_permiso = p.id_permiso
              )
            """,
            [rol, codigo],
        )
rows = conn.execute(
    """
    SELECT p.codigo FROM roles r
    JOIN rol_permiso rp ON rp.id_rol = r.id_rol
    JOIN permisos p ON p.id_permiso = rp.id_permiso
    WHERE r.nombre = 'gerente' ORDER BY p.codigo
    """
).fetchall()
print('gerente_perms:', [x[0] for x in rows])
u = conn.execute(
    "SELECT email, rol FROM usuarios WHERE email = 'gerente@globmarket.com'"
).fetchone()
print('user:', u)
print('sync_ok', res)
