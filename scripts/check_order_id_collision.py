import duckdb
from shared.services.integracion_ventas_service import order_id_linea

c = duckdb.connect("db/globtrade.duckdb")
oid = order_id_linea(6, 9)
print("portal oid", oid)
row = c.execute(
    "SELECT id_venta, order_id, origen, id_producto, total_revenue, units_sold, order_date FROM fact_ventas WHERE order_id = ?",
    [oid],
).fetchone()
print("conflict row", row)

big = c.execute(
    """
    SELECT COUNT(*) FROM fact_ventas WHERE order_id >= 10000000000 AND origen = 'historico'
    """
).fetchone()[0]
print("historico rows with order_id >= 10B:", big)

portal = c.execute(
    "SELECT COUNT(*) FROM fact_ventas WHERE origen = 'portal'"
).fetchone()[0]
print("portal rows:", portal)

# pedidos portal integration status
for pid in range(1, 8):
    dets = c.execute("SELECT id_detalle FROM pedido_detalle WHERE id_pedido = ?", [pid]).fetchall()
    for (idd,) in dets:
        o = order_id_linea(pid, int(idd))
        ex = c.execute(
            "SELECT origen, id_producto, total_revenue FROM fact_ventas WHERE order_id = ?", [o]
        ).fetchone()
        print(f"pedido {pid} det {idd} oid {o} ->", ex)

c.close()
