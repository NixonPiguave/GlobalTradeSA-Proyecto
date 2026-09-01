import duckdb

c = duckdb.connect("db/globtrade.duckdb")
tables = c.execute(
    "SELECT table_name FROM information_schema.tables "
    "WHERE table_schema='main' AND table_type='BASE TABLE' ORDER BY 1"
).fetchall()
print("tablas:", len(tables))
print("productos:", c.execute("SELECT COUNT(*) FROM dim_producto").fetchone()[0])
print("ventas:", c.execute("SELECT COUNT(*) FROM fact_ventas").fetchone()[0])
for t in tables:
    print(t[0])
