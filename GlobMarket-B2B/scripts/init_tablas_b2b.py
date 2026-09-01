from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import duckdb
from dotenv import load_dotenv
from passlib.context import CryptContext


pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def _hash_password(password: str) -> str:
    return pwd_context.hash(password)


def _project_root() -> Path:
    return Path(__file__).resolve().parent.parent  # GlobMarket-B2B/


def _duckdb_path() -> Path:
    load_dotenv(_project_root() / ".env", override=False)
    raw = os.environ.get("DUCKDB_PATH", "../GlobalTradeSA-duckdb/db/globtrade.duckdb").strip()
    ruta = Path(raw)
    if not ruta.is_absolute():
        ruta = (_project_root() / ruta).resolve()
    return ruta


def _execute_many(conn: duckdb.DuckDBPyConnection, sql: str, rows: list[list[Any]]) -> None:
    for r in rows:
        conn.execute(sql, r)


def crear_tablas(conn: duckdb.DuckDBPyConnection) -> None:
    # DuckDB (Windows) no siempre soporta IDENTITY; usamos SEQUENCE + nextval.
    conn.execute("CREATE SEQUENCE IF NOT EXISTS seq_usuarios START 1")
    conn.execute("CREATE SEQUENCE IF NOT EXISTS seq_dim_cliente START 1")
    conn.execute("CREATE SEQUENCE IF NOT EXISTS seq_dim_producto START 1")
    conn.execute("CREATE SEQUENCE IF NOT EXISTS seq_pedidos START 1")
    conn.execute("CREATE SEQUENCE IF NOT EXISTS seq_pedido_detalle START 1")

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS usuarios (
          id_usuario BIGINT PRIMARY KEY DEFAULT nextval('seq_usuarios'),
          email VARCHAR UNIQUE NOT NULL,
          password_hash VARCHAR NOT NULL,
          rol VARCHAR DEFAULT 'cliente',
          activo BOOLEAN DEFAULT true,
          fecha_registro TIMESTAMP DEFAULT current_timestamp
        )
        """
    )

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS dim_cliente (
          id_cliente BIGINT PRIMARY KEY DEFAULT nextval('seq_dim_cliente'),
          id_usuario BIGINT,
          nombre_empresa VARCHAR NOT NULL,
          pais VARCHAR NOT NULL,
          telefono VARCHAR,
          direccion VARCHAR
        )
        """
    )

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS dim_producto (
          id_producto BIGINT PRIMARY KEY DEFAULT nextval('seq_dim_producto'),
          nombre_producto VARCHAR NOT NULL,
          descripcion VARCHAR,
          id_item_type BIGINT NOT NULL,
          precio_unitario DECIMAL(10,2),
          precio_mayorista DECIMAL(10,2),
          imagen_url VARCHAR,
          activo BOOLEAN DEFAULT true
        )
        """
    )

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS pedidos (
          id_pedido BIGINT PRIMARY KEY DEFAULT nextval('seq_pedidos'),
          id_cliente BIGINT NOT NULL,
          id_country BIGINT NOT NULL,
          id_channel BIGINT NOT NULL,
          id_priority BIGINT NOT NULL,
          fecha_pedido TIMESTAMP DEFAULT current_timestamp,
          estado VARCHAR DEFAULT 'pendiente',
          total_pedido DECIMAL(12,2),
          notas VARCHAR
        )
        """
    )

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS pedido_detalle (
          id_detalle BIGINT PRIMARY KEY DEFAULT nextval('seq_pedido_detalle'),
          id_pedido BIGINT NOT NULL,
          id_producto BIGINT NOT NULL,
          cantidad BIGINT NOT NULL,
          precio_unitario DECIMAL(10,2),
          subtotal DECIMAL(12,2)
        )
        """
    )


def seed_usuarios_y_clientes(conn: duckdb.DuckDBPyConnection) -> None:
    # Admin
    conn.execute(
        """
        INSERT INTO usuarios (email, password_hash, rol, activo)
        SELECT ?, ?, 'admin', true
        WHERE NOT EXISTS (SELECT 1 FROM usuarios WHERE email = ?)
        """,
        ["admin@globmarket.com", _hash_password("12345678"), "admin@globmarket.com"],
    )

    # 3 clientes
    clientes = [
        ("compras@walmart.com", "12345678", "cliente"),
        ("procurement@carrefour.com", "12345678", "cliente"),
        ("sourcing@costco.com", "12345678", "cliente"),
    ]
    for email, password, rol in clientes:
        conn.execute(
            """
            INSERT INTO usuarios (email, password_hash, rol, activo)
            SELECT ?, ?, ?, true
            WHERE NOT EXISTS (SELECT 1 FROM usuarios WHERE email = ?)
            """,
            [email, _hash_password(password), rol, email],
        )

    # dim_cliente para esos 3 usuarios
    seeds_clientes = [
        ("compras@walmart.com", "Walmart Inc.", "United States", "+1 479-273-4000", "702 SW 8th St, Bentonville, AR"),
        ("procurement@carrefour.com", "Carrefour S.A.", "France", "+33 1 64 50 50 50", "93 Avenue de Paris, Massy, Île-de-France"),
        ("sourcing@costco.com", "Costco Wholesale", "United States", "+1 425-313-8100", "999 Lake Dr, Issaquah, WA"),
    ]
    for email, nombre, pais, telefono, direccion in seeds_clientes:
        conn.execute("SELECT id_usuario FROM usuarios WHERE email = ?", [email])
        r = conn.fetchone()
        if not r:
            continue
        id_usuario = int(r[0])
        conn.execute(
            """
            INSERT INTO dim_cliente (id_usuario, nombre_empresa, pais, telefono, direccion)
            SELECT ?, ?, ?, ?, ?
            WHERE NOT EXISTS (SELECT 1 FROM dim_cliente WHERE id_usuario = ?)
            """,
            [id_usuario, nombre, pais, telefono, direccion, id_usuario],
        )


def seed_productos(conn: duckdb.DuckDBPyConnection) -> None:
    conn.execute("SELECT id_item_type, item_type FROM dim_item_type ORDER BY id_item_type")
    categorias = conn.fetchall()
    if not categorias:
        raise RuntimeError("No se encontraron categorías en dim_item_type (Sistema 1).")

    # (item_type) -> 3 productos
    productos_por_categoria: dict[str, list[dict[str, Any]]] = {
        "Baby Food": [
            {
                "nombre": "Organic Baby Cereal — Oat & Banana",
                "desc": "Cereal infantil orgánico fortificado, ideal para compras mayoristas en retail.",
                "pu": 3.80,
                "pm": 2.95,
                "img": "https://images.unsplash.com/photo-1550461716-dbf266b2a8a7?auto=format&fit=crop&w=1200&q=80",
            },
            {
                "nombre": "Baby Fruit Purée Pouches — Apple & Pear",
                "desc": "Pouch de puré de fruta para bebés, empaques listos para góndola.",
                "pu": 2.60,
                "pm": 1.95,
                "img": "https://images.unsplash.com/photo-1563699498778-aa8246fa5456?auto=format&fit=crop&w=1200&q=80",
            },
            {
                "nombre": "Infant Formula — Premium Milk Powder",
                "desc": "Fórmula premium en polvo con trazabilidad de lote para exportación.",
                "pu": 24.90,
                "pm": 19.50,
                "img": "https://images.unsplash.com/photo-1623707430616-d9f956bcac2b?auto=format&fit=crop&w=1200&q=80",
            },
        ],
        "Beverages": [
            {
                "nombre": "Sparkling Water — Lime (24-pack)",
                "desc": "Agua con gas sabor lima, formato 24 unidades para canal mayorista.",
                "pu": 12.50,
                "pm": 9.90,
                "img": "https://images.unsplash.com/photo-1510626176961-4b57d4fbad03?auto=format&fit=crop&w=1200&q=80",
            },
            {
                "nombre": "Cold Brew Coffee — Original (12-pack)",
                "desc": "Café cold brew listo para beber, alta rotación en tiendas de conveniencia.",
                "pu": 22.80,
                "pm": 18.20,
                "img": "https://images.unsplash.com/photo-1511920170033-f8396924c348?auto=format&fit=crop&w=1200&q=80",
            },
            {
                "nombre": "Orange Juice — 1L (12-pack)",
                "desc": "Jugo de naranja 100% exprimido, packaging para exportación.",
                "pu": 19.20,
                "pm": 15.40,
                "img": "https://images.unsplash.com/photo-1724213653740-10f861130a55?auto=format&fit=crop&w=1200&q=80",
            },
        ],
        "Cereal": [
            {
                "nombre": "Whole Grain Oats — 1kg",
                "desc": "Avena integral, ideal para supermercados y distribuidores.",
                "pu": 4.20,
                "pm": 3.25,
                "img": "https://images.unsplash.com/photo-1676300185904-70b5bda359ae?auto=format&fit=crop&w=1200&q=80",
            },
            {
                "nombre": "Corn Flakes — Family Pack",
                "desc": "Cereal de hojuelas de maíz, empaque familiar de alta demanda.",
                "pu": 5.60,
                "pm": 4.30,
                "img": "https://images.unsplash.com/photo-1511690743698-d9d85f2fbf38?auto=format&fit=crop&w=1200&q=80",
            },
            {
                "nombre": "Granola — Nuts & Honey",
                "desc": "Granola premium con miel y frutos secos para canal moderno.",
                "pu": 6.90,
                "pm": 5.10,
                "img": "https://images.unsplash.com/photo-1551024601-bec78aea704b?auto=format&fit=crop&w=1200&q=80",
            },
        ],
        "Clothes": [
            {
                "nombre": "Basic Cotton T-Shirts — 12 units",
                "desc": "Camisetas de algodón para abastecimiento corporativo y retail.",
                "pu": 39.90,
                "pm": 29.90,
                "img": "https://images.unsplash.com/photo-1521572163474-6864f9cf17ab?auto=format&fit=crop&w=1200&q=80",
            },
            {
                "nombre": "Workwear Polo Shirts — 10 units",
                "desc": "Polos resistentes, pensadas para uniformes y compras por volumen.",
                "pu": 79.00,
                "pm": 59.00,
                "img": "https://images.unsplash.com/photo-1622445275463-afa2ab738c34?auto=format&fit=crop&w=1200&q=80",
            },
            {
                "nombre": "Eco Cotton Hoodies — 6 units",
                "desc": "Hoodies de algodón sostenible para campañas y merchandising.",
                "pu": 120.00,
                "pm": 92.00,
                "img": "https://images.unsplash.com/photo-1556821840-3a63f95609a7?auto=format&fit=crop&w=1200&q=80",
            },
        ],
        "Cosmetics": [
            {
                "nombre": "Moisturizing Face Cream — 50ml (24 units)",
                "desc": "Crema hidratante de alta rotación, presentación para retail.",
                "pu": 168.00,
                "pm": 129.00,
                "img": "https://images.unsplash.com/photo-1522335789203-aabd1fc54bc9?auto=format&fit=crop&w=1200&q=80",
            },
            {
                "nombre": "Lip Balm — Shea Butter (48 units)",
                "desc": "Bálsamo labial con manteca de karité, ideal para exhibición en caja.",
                "pu": 96.00,
                "pm": 69.00,
                "img": "https://images.unsplash.com/photo-1596462502278-27bfdc403348?auto=format&fit=crop&w=1200&q=80",
            },
            {
                "nombre": "Micellar Water — 400ml (12 units)",
                "desc": "Agua micelar, packaging para exportación y distribución mayorista.",
                "pu": 108.00,
                "pm": 84.00,
                "img": "https://images.unsplash.com/photo-1571781926291-c477ebfd024b?auto=format&fit=crop&w=1200&q=80",
            },
        ],
        "Fruits": [
            {
                "nombre": "Fresh Apples — Premium (20kg crate)",
                "desc": "Manzana premium para distribución internacional, cadena de frío.",
                "pu": 39.00,
                "pm": 31.00,
                "img": "https://images.unsplash.com/photo-1567306226416-28f0efdc88ce?auto=format&fit=crop&w=1200&q=80",
            },
            {
                "nombre": "Bananas — Export Grade (18kg box)",
                "desc": "Banano de exportación, ideal para importadores y supermercados.",
                "pu": 27.50,
                "pm": 21.50,
                "img": "https://images.unsplash.com/photo-1571771894821-ce9b6c11b08e?auto=format&fit=crop&w=1200&q=80",
            },
            {
                "nombre": "Oranges — Valencia (15kg box)",
                "desc": "Naranja Valencia seleccionada, excelente rendimiento y frescura.",
                "pu": 32.00,
                "pm": 25.00,
                "img": "https://images.unsplash.com/photo-1718915873518-b4320be0a6b0?auto=format&fit=crop&w=1200&q=80",
            },
        ],
        "Household": [
            {
                "nombre": "Dish Soap — Citrus (12 units)",
                "desc": "Detergente lavaloza concentrado, presentación mayorista.",
                "pu": 36.00,
                "pm": 27.00,
                "img": "https://images.unsplash.com/photo-1722842253242-1a40ba701095?auto=format&fit=crop&w=1200&q=80",
            },
            {
                "nombre": "Laundry Detergent — 3L (6 units)",
                "desc": "Detergente de ropa para canal mayorista y exportación.",
                "pu": 72.00,
                "pm": 54.00,
                "img": "https://images.unsplash.com/photo-1625479761497-540dcd8bd5fa?auto=format&fit=crop&w=1200&q=80",
            },
            {
                "nombre": "Paper Towels — 12 rolls",
                "desc": "Toallas de papel, empaque de 12 rollos para supermercados.",
                "pu": 28.00,
                "pm": 20.50,
                "img": "https://images.unsplash.com/photo-1771231591303-8e0daa821513?auto=format&fit=crop&w=1200&q=80",
            },
        ],
        "Meat": [
            {
                "nombre": "Frozen Beef Strips — 10kg",
                "desc": "Carne de res congelada para food service y distribución.",
                "pu": 98.00,
                "pm": 82.00,
                "img": "https://images.unsplash.com/photo-1603048297172-c92544798d5a?auto=format&fit=crop&w=1200&q=80",
            },
            {
                "nombre": "Chicken Breast — Frozen (10kg)",
                "desc": "Pechuga de pollo congelada, estándares de exportación.",
                "pu": 76.00,
                "pm": 62.00,
                "img": "https://images.unsplash.com/photo-1606851577347-5ec511dfb22d?auto=format&fit=crop&w=1200&q=80",
            },
            {
                "nombre": "Pork Ribs — Frozen (12kg)",
                "desc": "Costillas de cerdo congeladas para retail y horeca.",
                "pu": 88.00,
                "pm": 71.00,
                "img": "https://images.unsplash.com/photo-1529692236671-f1f6cf9683ba?auto=format&fit=crop&w=1200&q=80",
            },
        ],
        "Office Supplies": [
            {
                "nombre": "A4 Copy Paper — 5 reams",
                "desc": "Papel A4 para oficina, compra por volumen para empresas.",
                "pu": 21.00,
                "pm": 16.50,
                "img": "https://images.unsplash.com/photo-1516409590654-e8d51fc2d25c?auto=format&fit=crop&w=1200&q=80",
            },
            {
                "nombre": "Ballpoint Pens — 100 units",
                "desc": "Bolígrafos de escritura suave, pack de 100 unidades.",
                "pu": 18.50,
                "pm": 13.90,
                "img": "https://images.unsplash.com/photo-1455390582262-044cdead277a?auto=format&fit=crop&w=1200&q=80",
            },
            {
                "nombre": "Desk Notebooks — 50 units",
                "desc": "Cuadernos para escritorio, formato ideal para distribución.",
                "pu": 65.00,
                "pm": 49.00,
                "img": "https://images.unsplash.com/photo-1631543763678-6e529a1b8c9d?auto=format&fit=crop&w=1200&q=80",
            },
        ],
        "Personal Care": [
            {
                "nombre": "Shampoo — Daily Care (12 units)",
                "desc": "Shampoo de uso diario, presentación para retail.",
                "pu": 54.00,
                "pm": 41.00,
                "img": "https://images.unsplash.com/photo-1747858989102-cca0f4dc4a11?auto=format&fit=crop&w=1200&q=80",
            },
            {
                "nombre": "Toothpaste — Mint (24 units)",
                "desc": "Pasta dental mentolada, alta rotación en mayoristas.",
                "pu": 48.00,
                "pm": 36.00,
                "img": "https://images.unsplash.com/photo-1763048819607-ea55217cff34?auto=format&fit=crop&w=1200&q=80",
            },
            {
                "nombre": "Hand Soap — Aloe (24 units)",
                "desc": "Jabón de manos con aloe, ideal para abastecimiento corporativo.",
                "pu": 42.00,
                "pm": 32.00,
                "img": "https://images.unsplash.com/photo-1713434638446-13b4a15b728e?auto=format&fit=crop&w=1200&q=80",
            },
        ],
        "Snacks": [
            {
                "nombre": "Mixed Nuts — 1kg (10 units)",
                "desc": "Mix de frutos secos premium para retail y vending.",
                "pu": 110.00,
                "pm": 89.00,
                "img": "https://images.unsplash.com/photo-1626697556426-8a55a8af4999?auto=format&fit=crop&w=1200&q=80",
            },
            {
                "nombre": "Potato Chips — Sea Salt (24 units)",
                "desc": "Papas fritas, formato 24 unidades para distribución.",
                "pu": 48.00,
                "pm": 36.00,
                "img": "https://images.unsplash.com/photo-1741520149946-d2e652514b5a?auto=format&fit=crop&w=1200&q=80",
            },
            {
                "nombre": "Protein Bars — Chocolate (24 units)",
                "desc": "Barras proteicas, empaque para canal moderno y gimnasios.",
                "pu": 72.00,
                "pm": 55.00,
                "img": "https://images.unsplash.com/photo-1606313564200-e75d5e30476c?auto=format&fit=crop&w=1200&q=80",
            },
        ],
        "Vegetables": [
            {
                "nombre": "Frozen Mixed Vegetables — 10kg",
                "desc": "Vegetales mixtos congelados para food service.",
                "pu": 42.00,
                "pm": 34.00,
                "img": "https://images.unsplash.com/photo-1540420773420-3366772f4999?auto=format&fit=crop&w=1200&q=80",
            },
            {
                "nombre": "Tomatoes — Roma (15kg box)",
                "desc": "Tomate Roma para mayoristas, excelente firmeza y frescura.",
                "pu": 29.00,
                "pm": 22.50,
                "img": "https://images.unsplash.com/photo-1546094096-0df4bcaaa337?auto=format&fit=crop&w=1200&q=80",
            },
            {
                "nombre": "Onions — Yellow (20kg sack)",
                "desc": "Cebolla amarilla para distribución y exportación.",
                "pu": 26.00,
                "pm": 20.00,
                "img": "https://images.unsplash.com/photo-1668295037389-292efc20dafe?auto=format&fit=crop&w=1200&q=80",
            },
        ],
    }

    for id_item_type, item_type in categorias:
        nombre_categoria = str(item_type)
        productos = productos_por_categoria.get(nombre_categoria)
        if not productos:
            # Si hubiera categorías inesperadas, no se insertan productos.
            continue

        for p in productos:
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
                [
                    p["nombre"],
                    p["desc"],
                    int(id_item_type),
                    p["pu"],
                    p["pm"],
                    p["img"],
                    p["nombre"],
                    int(id_item_type),
                ],
            )
            conn.execute(
                """
                UPDATE dim_producto
                SET imagen_url = ?, descripcion = ?
                WHERE nombre_producto = ? AND id_item_type = ?
                """,
                [p["img"], p["desc"], p["nombre"], int(id_item_type)],
            )


def main() -> None:
    ruta = _duckdb_path()
    if not ruta.exists():
        raise SystemExit(f"No se encontró DuckDB en: {ruta}")

    conn = duckdb.connect(str(ruta))
    try:
        crear_tablas(conn)
        seed_usuarios_y_clientes(conn)
        seed_productos(conn)
    finally:
        conn.close()

    print("OK — Tablas B2B creadas y semillas insertadas (si no existían).")
    print("Verificando y asignando URLs de imagen válidas...")
    import subprocess
    import sys

    script_img = Path(__file__).resolve().parent / "actualizar_imagenes_productos.py"
    subprocess.run([sys.executable, str(script_img)], check=True)


if __name__ == "__main__":
    main()
