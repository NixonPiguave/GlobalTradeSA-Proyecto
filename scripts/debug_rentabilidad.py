import duckdb
from pathlib import Path

db = Path(__file__).resolve().parents[1] / "db" / "globtrade.duckdb"
c = duckdb.connect(str(db), read_only=True)

print("=== productos congelados/premium ===")
print(c.execute("""
SELECT id_producto, nombre_producto, id_item_type FROM dim_producto
WHERE lower(nombre_producto) LIKE '%congel%' OR lower(nombre_producto) LIKE '%frozen%'
   OR lower(nombre_producto) LIKE '%premium%' OR lower(nombre_producto) LIKE '%congelados%'
""").fetchall())

print("\n=== categorias ===")
print(c.execute("""
SELECT id_categoria, nombre, id_item_type FROM categorias
WHERE lower(nombre) LIKE '%congel%' OR lower(nombre) LIKE '%premium%'
""").fetchall())

print("\n=== ultimos pedidos ===")
print(c.execute("""
SELECT p.id_pedido, p.numero, p.estado, CAST(p.fecha_pedido AS DATE), pr.nombre_producto, d.cantidad, d.subtotal
FROM pedidos p
JOIN pedido_detalle d ON d.id_pedido = p.id_pedido
JOIN dim_producto pr ON pr.id_producto = d.id_producto
ORDER BY p.id_pedido DESC LIMIT 8
""").fetchall())

print("\n=== fact_ventas portal (recientes) ===")
print(c.execute("""
SELECT fv.id_venta, fv.origen, fv.order_date, fv.total_revenue, fv.total_profit,
       pr.nombre_producto, dit.item_type
FROM fact_ventas fv
LEFT JOIN dim_producto pr ON pr.id_producto = fv.id_producto
JOIN dim_item_type dit ON dit.id_item_type = fv.id_item_type
WHERE fv.origen = 'portal' OR fv.order_id >= 10000000000
ORDER BY fv.id_venta DESC LIMIT 10
""").fetchall())

print("\n=== rentabilidad por item_type (hoy) ===")
print(c.execute("""
SELECT item_type, SUM(total_revenue), SUM(total_profit), SUM(units_sold)
FROM ventas
WHERE order_date >= CURRENT_DATE
GROUP BY item_type
ORDER BY 3 DESC
""").fetchall())

print("\n=== rentabilidad por item_type (sin filtro, top 5) ===")
print(c.execute("""
SELECT item_type, SUM(total_revenue), SUM(total_profit)
FROM ventas GROUP BY item_type ORDER BY 3 DESC LIMIT 5
""").fetchall())

c.close()
