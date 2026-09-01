"""Semilla de catálogo demo: 36 productos (3 por categoría) con rutas de imagen locales."""

from __future__ import annotations

import re
from typing import Any

PRODUCTOS_POR_CATEGORIA: dict[str, list[dict[str, Any]]] = {
    "Baby Food": [
        {"nombre": "Organic Baby Cereal — Oat & Banana", "desc": "Cereal infantil orgánico fortificado, ideal para compras mayoristas en retail.", "pu": 3.80, "pm": 2.95},
        {"nombre": "Baby Fruit Purée Pouches — Apple & Pear", "desc": "Pouch de puré de fruta para bebés, empaques listos para góndola.", "pu": 2.60, "pm": 1.95},
        {"nombre": "Infant Formula — Premium Milk Powder", "desc": "Fórmula premium en polvo con trazabilidad de lote para exportación.", "pu": 24.90, "pm": 19.50},
    ],
    "Beverages": [
        {"nombre": "Sparkling Water — Lime (24-pack)", "desc": "Agua con gas sabor lima, formato 24 unidades para canal mayorista.", "pu": 12.50, "pm": 9.90},
        {"nombre": "Cold Brew Coffee — Original (12-pack)", "desc": "Café cold brew listo para beber, alta rotación en tiendas de conveniencia.", "pu": 22.80, "pm": 18.20},
        {"nombre": "Orange Juice — 1L (12-pack)", "desc": "Jugo de naranja 100% exprimido, packaging para exportación.", "pu": 19.20, "pm": 15.40},
    ],
    "Cereal": [
        {"nombre": "Whole Grain Oats — 1kg", "desc": "Avena integral, ideal para supermercados y distribuidores.", "pu": 4.20, "pm": 3.25},
        {"nombre": "Corn Flakes — Family Pack", "desc": "Cereal de hojuelas de maíz, empaque familiar de alta demanda.", "pu": 5.60, "pm": 4.30},
        {"nombre": "Granola — Nuts & Honey", "desc": "Granola premium con miel y frutos secos para canal moderno.", "pu": 6.90, "pm": 5.10},
    ],
    "Clothes": [
        {"nombre": "Basic Cotton T-Shirts — 12 units", "desc": "Camisetas de algodón para abastecimiento corporativo y retail.", "pu": 39.90, "pm": 29.90},
        {"nombre": "Workwear Polo Shirts — 10 units", "desc": "Polos resistentes, pensadas para uniformes y compras por volumen.", "pu": 79.00, "pm": 59.00},
        {"nombre": "Eco Cotton Hoodies — 6 units", "desc": "Hoodies de algodón sostenible para campañas y merchandising.", "pu": 120.00, "pm": 92.00},
    ],
    "Cosmetics": [
        {"nombre": "Moisturizing Face Cream — 50ml (24 units)", "desc": "Crema hidratante de alta rotación, presentación para retail.", "pu": 168.00, "pm": 129.00},
        {"nombre": "Lip Balm — Shea Butter (48 units)", "desc": "Bálsamo labial con manteca de karité, ideal para exhibición en caja.", "pu": 96.00, "pm": 69.00},
        {"nombre": "Micellar Water — 400ml (12 units)", "desc": "Agua micelar, packaging para exportación y distribución mayorista.", "pu": 108.00, "pm": 84.00},
    ],
    "Fruits": [
        {"nombre": "Fresh Apples — Premium (20kg crate)", "desc": "Manzana premium para distribución internacional, cadena de frío.", "pu": 39.00, "pm": 31.00},
        {"nombre": "Bananas — Export Grade (18kg box)", "desc": "Banano de exportación, ideal para importadores y supermercados.", "pu": 27.50, "pm": 21.50},
        {"nombre": "Oranges — Valencia (15kg box)", "desc": "Naranja Valencia seleccionada, excelente rendimiento y frescura.", "pu": 32.00, "pm": 25.00},
    ],
    "Household": [
        {"nombre": "Dish Soap — Citrus (12 units)", "desc": "Detergente lavaloza concentrado, presentación mayorista.", "pu": 36.00, "pm": 27.00},
        {"nombre": "Laundry Detergent — 3L (6 units)", "desc": "Detergente de ropa para canal mayorista y exportación.", "pu": 72.00, "pm": 54.00},
        {"nombre": "Paper Towels — 12 rolls", "desc": "Toallas de papel, empaque de 12 rollos para supermercados.", "pu": 28.00, "pm": 20.50},
    ],
    "Meat": [
        {"nombre": "Frozen Beef Strips — 10kg", "desc": "Carne de res congelada para food service y distribución.", "pu": 98.00, "pm": 82.00},
        {"nombre": "Chicken Breast — Frozen (10kg)", "desc": "Pechuga de pollo congelada, estándares de exportación.", "pu": 76.00, "pm": 62.00},
        {"nombre": "Pork Ribs — Frozen (12kg)", "desc": "Costillas de cerdo congeladas para retail y horeca.", "pu": 88.00, "pm": 71.00},
    ],
    "Office Supplies": [
        {"nombre": "A4 Copy Paper — 5 reams", "desc": "Papel A4 para oficina, compra por volumen para empresas.", "pu": 21.00, "pm": 16.50},
        {"nombre": "Ballpoint Pens — 100 units", "desc": "Bolígrafos de escritura suave, pack de 100 unidades.", "pu": 18.50, "pm": 13.90},
        {"nombre": "Desk Notebooks — 50 units", "desc": "Cuadernos para escritorio, formato ideal para distribución.", "pu": 65.00, "pm": 49.00},
    ],
    "Personal Care": [
        {"nombre": "Shampoo — Daily Care (12 units)", "desc": "Shampoo de uso diario, presentación para retail.", "pu": 54.00, "pm": 41.00},
        {"nombre": "Toothpaste — Mint (24 units)", "desc": "Pasta dental mentolada, alta rotación en mayoristas.", "pu": 48.00, "pm": 36.00},
        {"nombre": "Hand Soap — Aloe (24 units)", "desc": "Jabón de manos con aloe, ideal para abastecimiento corporativo.", "pu": 42.00, "pm": 32.00},
    ],
    "Snacks": [
        {"nombre": "Mixed Nuts — 1kg (10 units)", "desc": "Mix de frutos secos premium para retail y vending.", "pu": 110.00, "pm": 89.00},
        {"nombre": "Potato Chips — Sea Salt (24 units)", "desc": "Papas fritas, formato 24 unidades para distribución.", "pu": 48.00, "pm": 36.00},
        {"nombre": "Protein Bars — Chocolate (24 units)", "desc": "Barras proteicas, empaque para canal moderno y gimnasios.", "pu": 72.00, "pm": 55.00},
    ],
    "Vegetables": [
        {"nombre": "Frozen Mixed Vegetables — 10kg", "desc": "Vegetales mixtos congelados para food service.", "pu": 42.00, "pm": 34.00},
        {"nombre": "Tomatoes — Roma (15kg box)", "desc": "Tomate Roma para mayoristas, excelente firmeza y frescura.", "pu": 29.00, "pm": 22.50},
        {"nombre": "Onions — Yellow (20kg sack)", "desc": "Cebolla amarilla para distribución y exportación.", "pu": 26.00, "pm": 20.00},
    ],
}

MARCAS = [
    ("GlobalTrade", "Marca propia del distribuidor"),
    ("FreshLine", "Línea frescos y refrigerados"),
    ("OfficePro", "Suministros de oficina"),
]


def _slug(text: str) -> str:
    s = text.lower().replace("—", "-").replace("&", "and")
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s[:48] or "producto"


def _img_path(categoria: str, nombre: str) -> str:
    return f"uploads/productos/{_slug(categoria)}-{_slug(nombre)}.jpg"


def seed_marcas(conn) -> None:
    for nombre, _desc in MARCAS:
        conn.execute(
            """
            INSERT INTO marcas (nombre, activo)
            SELECT ?, true
            WHERE NOT EXISTS (SELECT 1 FROM marcas WHERE nombre = ?)
            """,
            [nombre, nombre],
        )


def seed_catalogo_demo(conn) -> None:
    rows = conn.execute("SELECT id_item_type, item_type FROM dim_item_type ORDER BY id_item_type").fetchall()
    if not rows:
        return

    for id_item_type, item_type in rows:
        categoria = str(item_type)
        productos = PRODUCTOS_POR_CATEGORIA.get(categoria)
        if not productos:
            continue
        for p in productos:
            img = _img_path(categoria, p["nombre"])
            conn.execute(
                """
                INSERT INTO dim_producto (
                  nombre_producto, descripcion, id_item_type,
                  precio_unitario, precio_mayorista, imagen_url, activo
                )
                SELECT ?, ?, ?, ?, ?, ?, true
                WHERE NOT EXISTS (
                  SELECT 1 FROM dim_producto
                  WHERE nombre_producto = ? AND id_item_type = ?
                )
                """,
                [p["nombre"], p["desc"], int(id_item_type), p["pu"], p["pm"], img, p["nombre"], int(id_item_type)],
            )
            conn.execute(
                """
                UPDATE dim_producto
                SET descripcion = ?, precio_unitario = ?, precio_mayorista = ?
                WHERE nombre_producto = ? AND id_item_type = ?
                """,
                [p["desc"], p["pu"], p["pm"], p["nombre"], int(id_item_type)],
            )


def _slug_archivo(nombre: str) -> str:
    s = nombre.lower().replace("—", "-").replace("&", "and")
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s[:48] or "producto"


def _compact(texto: str) -> str:
    s = texto.lower().replace("&", "and")
    return re.sub(r"[^a-z0-9]", "", s)


def _coincide_imagen(archivo_stem: str, nombre_producto: str) -> bool:
    stem = re.sub(r"-[0-9a-f]{8}$", "", archivo_stem, flags=re.I)
    base = _slug_archivo(nombre_producto)
    if stem.startswith(base) or base in stem:
        return True
    prefijo = base[:24]
    if prefijo and stem.startswith(prefijo):
        return True

    compact_stem = _compact(stem)
    compact_nombre = _compact(nombre_producto)
    compact_sin_and = compact_nombre.replace("and", "")
    if len(compact_stem) >= 8 and (
        compact_stem in compact_nombre
        or compact_stem in compact_sin_and
        or compact_nombre.startswith(compact_stem)
    ):
        return True
    return False


def reparar_imagenes_desde_storage(conn, storage_root) -> None:
    """Alinea imagen_url con archivos reales en shared/storage (idempotente)."""
    from pathlib import Path

    carpeta = Path(storage_root) / "uploads" / "productos"
    if not carpeta.is_dir():
        return

    archivos = [f for f in carpeta.iterdir() if f.is_file()]
    if not archivos:
        return

    rows = conn.execute(
        "SELECT id_producto, nombre_producto, imagen_url FROM dim_producto WHERE activo = true"
    ).fetchall()

    for id_producto, nombre, imagen_url in rows:
        if imagen_url:
            ruta = Path(storage_root) / imagen_url
            if ruta.is_file():
                continue

        match = next((f for f in archivos if _coincide_imagen(f.stem, nombre)), None)
        if match is None:
            continue

        rel = f"uploads/productos/{match.name}"
        conn.execute(
            "UPDATE dim_producto SET imagen_url = ? WHERE id_producto = ?",
            [rel, int(id_producto)],
        )
