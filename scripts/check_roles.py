import duckdb

c = duckdb.connect("/app/db/globtrade.duckdb", read_only=True)
print("roles:", c.execute("SELECT id_rol, nombre FROM roles ORDER BY id_rol").fetchall())
print("gerente:", c.execute("SELECT email, rol FROM usuarios WHERE email = 'gerente@globmarket.com'").fetchall())
print("gerente_perms:", c.execute("""
    SELECT p.codigo FROM roles r
    JOIN rol_permiso rp ON rp.id_rol = r.id_rol
    JOIN permisos p ON p.id_permiso = rp.id_permiso
    WHERE r.nombre = 'gerente'
""").fetchall())
