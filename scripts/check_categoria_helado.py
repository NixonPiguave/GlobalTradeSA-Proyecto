import duckdb
c = duckdb.connect("db/globtrade.duckdb", read_only=True)
print("=== producto 37 ===")
print(c.execute("""
SELECT p.id_producto, p.nombre_producto, p.id_item_type, it.item_type,
       cat.nombre AS categoria
FROM dim_producto p
LEFT JOIN dim_item_type it ON it.id_item_type = p.id_item_type
LEFT JOIN categorias cat ON cat.id_item_type = p.id_item_type
WHERE p.id_producto = 37 OR p.nombre_producto ILIKE '%helado%'
""").fetchall())
print("=== categorias congelados ===")
print(c.execute("""
SELECT id_categoria, nombre, id_item_type FROM categorias
WHERE nombre ILIKE '%congel%' OR nombre ILIKE '%premium%'
""").fetchall())
print("=== item_types congelados ===")
print(c.execute("""
SELECT id_item_type, item_type FROM dim_item_type
WHERE item_type ILIKE '%congel%' OR item_type ILIKE '%premium%'
""").fetchall())
print("=== fact_ventas dimensiones ===")
print(c.execute("""
SELECT v.dimension_producto, SUM(v.total_revenue), SUM(v.units_sold), v.origen
FROM ventas v
WHERE v.dimension_producto ILIKE '%helado%' OR v.dimension_producto ILIKE '%congel%'
GROUP BY v.dimension_producto, v.origen
""").fetchall())
c.close()
