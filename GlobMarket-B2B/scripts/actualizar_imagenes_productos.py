"""
Asigna a cada producto una imagen coherente con su categoría/nombre.
Solo guarda URLs que respondan HTTP 200 (GET).
IDs de Unsplash verificados contra images.unsplash.com.
"""
from __future__ import annotations

import os
from pathlib import Path

import duckdb
import requests
from dotenv import load_dotenv

HEADERS = {"User-Agent": "GlobMarket-B2B/1.0"}
PARAMS = "?auto=format&fit=crop&w=900&q=80"


def u(photo_id: str) -> str:
    return f"https://images.unsplash.com/{photo_id}{PARAMS}"


# nombre_producto (clave en BD) -> candidatos temáticos (orden de preferencia)
IMAGENES_POR_PRODUCTO: dict[str, list[str]] = {
    "Organic Baby Cereal — Oat & Banana": [
        u("photo-1550461716-dbf266b2a8a7"),  # avena en bol con plátano
        u("photo-1732299322196-ab4d02a8dd5d"),  # cereal con leche y cucharas
    ],
    "Baby Fruit Purée Pouches — Apple & Pear": [
        u("photo-1563699498778-aa8246fa5456"),
        u("photo-1652480275137-9de7ef17a0a3"),
    ],
    "Infant Formula — Premium Milk Powder": [
        u("photo-1623707430616-d9f956bcac2b"),
        u("photo-1635258559918-ed56f88004de"),
    ],
    "Sparkling Water — Lime (24-pack)": [
        u("photo-1510626176961-4b57d4fbad03"),
        u("photo-1548839140-29a749e1cf4d"),
    ],
    "Cold Brew Coffee — Original (12-pack)": [
        u("photo-1511920170033-f8396924c348"),
    ],
    "Orange Juice — 1L (12-pack)": [
        u("photo-1724213653740-10f861130a55"),
        u("photo-1577805947697-89e18249d767"),
    ],
    "Whole Grain Oats — 1kg": [
        u("photo-1676300185904-70b5bda359ae"),
        u("photo-1511690743698-d9d85f2fbf38"),
    ],
    "Corn Flakes — Family Pack": [
        u("photo-1511690743698-d9d85f2fbf38"),
        u("photo-1541592106381-b31e9677c0e5"),
    ],
    "Granola — Nuts & Honey": [
        u("photo-1551024601-bec78aea704b"),
    ],
    "Basic Cotton T-Shirts — 12 units": [
        u("photo-1521572163474-6864f9cf17ab"),
    ],
    "Workwear Polo Shirts — 10 units": [
        u("photo-1622445275463-afa2ab738c34"),
    ],
    "Eco Cotton Hoodies — 6 units": [
        u("photo-1556821840-3a63f95609a7"),
    ],
    "Moisturizing Face Cream — 50ml (24 units)": [
        u("photo-1522335789203-aabd1fc54bc9"),
    ],
    "Lip Balm — Shea Butter (48 units)": [
        u("photo-1596462502278-27bfdc403348"),
    ],
    "Micellar Water — 400ml (12 units)": [
        u("photo-1571781926291-c477ebfd024b"),
    ],
    "Fresh Apples — Premium (20kg crate)": [
        u("photo-1567306226416-28f0efdc88ce"),
    ],
    "Bananas — Export Grade (18kg box)": [
        u("photo-1571771894821-ce9b6c11b08e"),
    ],
    "Oranges — Valencia (15kg box)": [
        u("photo-1718915873518-b4320be0a6b0"),
        u("photo-1724213653740-10f861130a55"),
    ],
    "Dish Soap — Citrus (12 units)": [
        u("photo-1722842253242-1a40ba701095"),
        u("photo-1751606803218-67f4b896fc4e"),
    ],
    "Laundry Detergent — 3L (6 units)": [
        u("photo-1625479761497-540dcd8bd5fa"),
        u("photo-1649005011845-ef225c89da86"),
    ],
    "Paper Towels — 12 rolls": [
        u("photo-1771231591303-8e0daa821513"),
        u("photo-1655105469311-de74599bad6c"),
    ],
    "Frozen Beef Strips — 10kg": [
        u("photo-1603048297172-c92544798d5a"),
        u("photo-1558030006-450675393462"),
    ],
    "Chicken Breast — Frozen (10kg)": [
        u("photo-1606851577347-5ec511dfb22d"),
        u("photo-1633096013004-e2cb4023b560"),
    ],
    "Pork Ribs — Frozen (12kg)": [
        u("photo-1529692236671-f1f6cf9683ba"),
    ],
    "A4 Copy Paper — 5 reams": [
        u("photo-1516409590654-e8d51fc2d25c"),  # resma de hojas blancas
        u("photo-1621944192380-808416c390e2"),  # papel de impresora
    ],
    "Ballpoint Pens — 100 units": [
        u("photo-1455390582262-044cdead277a"),
    ],
    "Desk Notebooks — 50 units": [
        u("photo-1631543763678-6e529a1b8c9d"),  # pila de cuadernos de colores
        u("photo-1717079556888-c23cb91b450f"),  # cuadernos y bolígrafos en mesa
    ],
    "Shampoo — Daily Care (12 units)": [
        u("photo-1747858989102-cca0f4dc4a11"),
        u("photo-1701992678972-d5a053ad0fb0"),
    ],
    "Toothpaste — Mint (24 units)": [
        u("photo-1763048819607-ea55217cff34"),  # cepillo con pasta dental verde (menta)
        u("photo-1690725219036-3c9f57a08837"),  # tubo de pasta dental
    ],
    "Hand Soap — Aloe (24 units)": [
        u("photo-1713434638446-13b4a15b728e"),
        u("photo-1701992678972-d5a053ad0fb0"),
    ],
    "Mixed Nuts — 1kg (10 units)": [
        u("photo-1626697556426-8a55a8af4999"),
        u("photo-1671981200629-014c03829abb"),
    ],
    "Potato Chips — Sea Salt (24 units)": [
        u("photo-1741520149946-d2e652514b5a"),
        u("photo-1694101493127-eca6dfef5011"),
    ],
    "Protein Bars — Chocolate (24 units)": [
        u("photo-1606313564200-e75d5e30476c"),
    ],
    "Frozen Mixed Vegetables — 10kg": [
        u("photo-1540420773420-3366772f4999"),
        u("photo-1518843875459-f738682238a6"),
    ],
    "Tomatoes — Roma (15kg box)": [
        u("photo-1546094096-0df4bcaaa337"),
    ],
    "Onions — Yellow (20kg sack)": [
        u("photo-1668295037389-292efc20dafe"),  # cebollas amarillas en canasta
        u("photo-1700478934149-cdd592915713"),  # cajas de cebollas en mercado
    ],
}


def _duckdb_path() -> Path:
    root = Path(__file__).resolve().parent.parent
    load_dotenv(root / ".env", override=False)
    raw = os.environ.get("DUCKDB_PATH", "../GlobalTradeSA-duckdb/db/globtrade.duckdb").strip()
    ruta = Path(raw)
    if not ruta.is_absolute():
        ruta = (root / ruta).resolve()
    return ruta


def url_responde_200(url: str) -> bool:
    try:
        r = requests.get(url, timeout=25, headers=HEADERS, stream=True)
        ok = r.status_code == 200
        r.close()
        return ok
    except Exception:
        return False


def elegir_url(candidatos: list[str]) -> str | None:
    for url in candidatos:
        if url_responde_200(url):
            return url
    return None


def main() -> None:
    ruta = _duckdb_path()
    conn = duckdb.connect(str(ruta))
    try:
        rows = conn.execute(
            "SELECT id_producto, nombre_producto FROM dim_producto ORDER BY id_producto"
        ).fetchall()

        sin_match = 0
        sin_url = 0

        for id_producto, nombre in rows:
            nombre = str(nombre)
            candidatos = IMAGENES_POR_PRODUCTO.get(nombre)
            if not candidatos:
                sin_match += 1
                print(f"  Sin mapa temático: {nombre}")
                continue

            url = elegir_url(candidatos)
            if not url:
                sin_url += 1
                print(f"  Sin URL válida: {nombre}")
                continue

            conn.execute(
                "UPDATE dim_producto SET imagen_url = ? WHERE id_producto = ?",
                [url, int(id_producto)],
            )
            print(f"  OK id={id_producto}: {nombre[:45]}")

        print(f"\nListo. Sin mapa: {sin_match}, sin URL válida: {sin_url}")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
