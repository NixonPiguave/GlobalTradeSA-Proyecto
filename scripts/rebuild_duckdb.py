"""
Reconstruye globtrade.duckdb copiando tablas sanas a un archivo nuevo.
Omite tablas corruptas (fact_ventas, wishlist*) y las recrea.

Uso: python scripts/rebuild_duckdb.py
Requiere: servicios detenidos (docker stop globaltrade-apps).
"""

from __future__ import annotations

import shutil
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "apps" / "admin"))

import duckdb

SRC = ROOT / "db" / "globtrade.duckdb"
NEW = ROOT / "db" / "globtrade_new.duckdb"
PARQUET = ROOT / "data" / "ventas.parquet"
SKIP = {"fact_ventas", "wishlist", "wishlist_items", "wishlist_catalogos"}


def main() -> None:
    if not SRC.exists():
        raise SystemExit(f"No existe {SRC}")
    if not PARQUET.exists():
        raise SystemExit(f"No existe {PARQUET}")

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = SRC.with_suffix(f".duckdb.bak_rebuild_{stamp}")
    print(f"Backup -> {backup.name}")
    shutil.copy2(SRC, backup)

    if NEW.exists():
        NEW.unlink()

    src = duckdb.connect(str(SRC), read_only=True)
    tables = [
        r[0]
        for r in src.execute(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema='main' AND table_type='BASE TABLE' ORDER BY table_name"
        ).fetchall()
    ]
    src.close()

    dst = duckdb.connect(str(NEW))
    dst.execute(f"ATTACH '{SRC.as_posix()}' AS old (READ_ONLY)")
    copied, failed = [], []
    for t in tables:
        if t in SKIP:
            continue
        try:
            dst.execute(f"CREATE TABLE {t} AS SELECT * FROM old.{t}")
            n = dst.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
            copied.append((t, int(n)))
            print(f"  OK {t}: {n} filas")
        except Exception as exc:
            failed.append((t, str(exc)[:100]))
            print(f"  SKIP {t}: {exc}")
    dst.execute("DETACH old")

    dst.execute(
        """
        CREATE TABLE fact_ventas (
          id_venta INTEGER PRIMARY KEY,
          order_id BIGINT NOT NULL UNIQUE,
          id_region INTEGER NOT NULL,
          id_country INTEGER NOT NULL,
          id_item_type INTEGER NOT NULL,
          id_channel INTEGER NOT NULL,
          id_priority INTEGER NOT NULL,
          order_date DATE NOT NULL,
          ship_date DATE NOT NULL,
          units_sold INTEGER NOT NULL,
          unit_price DECIMAL(10,2) NOT NULL,
          unit_cost DECIMAL(10,2) NOT NULL,
          total_revenue DECIMAL(12,2) NOT NULL,
          total_cost DECIMAL(12,2) NOT NULL,
          total_profit DECIMAL(12,2) NOT NULL,
          id_producto BIGINT,
          origen VARCHAR DEFAULT 'historico'
        )
        """
    )

    from backend.services.etl_service import importar_parquet_db

    imp = importar_parquet_db(dst, PARQUET)
    print(f"fact_ventas: +{imp['inserted']} filas")

    from shared.database.migrate_reestructuracion import aplicar_migraciones_reestructuracion
    from shared.services.integracion_ventas_service import reintegrar_pedidos_pendientes

    aplicar_migraciones_reestructuracion(dst)
    dst.execute(
        """
        CREATE TABLE IF NOT EXISTS wishlist_items (
          id_item BIGINT PRIMARY KEY, id_cliente BIGINT, id_producto BIGINT, fecha TIMESTAMP
        )
        """
    )
    reint = reintegrar_pedidos_pendientes(dst)
    print(f"Portal reintegrado: +{reint['insertadas']} lineas")

    rev = dst.execute(
        "SELECT SUM(CAST(total_revenue AS DOUBLE)) FROM fact_ventas"
    ).fetchone()[0]
    print(f"Verificacion: ingresos ~ ${float(rev or 0):,.2f}")
    dst.close()

    broken = SRC.with_suffix(".duckdb.broken")
    if broken.exists():
        broken.unlink()
    SRC.rename(broken)
    NEW.rename(SRC)
    wal = SRC.with_suffix(".duckdb.wal")
    if wal.exists():
        wal.unlink()
    print(f"Listo. Antigua BD en {broken.name}")
    if failed:
        print(f"Tablas no copiadas ({len(failed)}):", [f[0] for f in failed])


if __name__ == "__main__":
    main()
