import duckdb
c = duckdb.connect("db/globtrade.duckdb")
old = c.execute(
    "SELECT COUNT(*) FROM fact_ventas WHERE origen = 'portal' AND order_id < 90000000000000"
).fetchone()[0]
new = c.execute(
    "SELECT COUNT(*) FROM fact_ventas WHERE origen = 'portal' AND order_id >= 90000000000000"
).fetchone()[0]
print("portal old base:", old, "new base:", new)
# remove duplicates at old base (superseded by new base rows)
if old and new:
    c.execute(
        "DELETE FROM fact_ventas WHERE origen = 'portal' AND order_id < 90000000000000"
    )
    print("deleted old portal rows:", old)
c.close()
