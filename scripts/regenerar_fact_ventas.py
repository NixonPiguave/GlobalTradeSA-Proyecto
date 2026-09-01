"""
Reconstruye globtrade.duckdb cuando fact_ventas está corrupta en los backups.

Estrategia:
  1. Copia tablas sanas del backup (excepto fact_ventas y wishlist*/zonas_envio).
  2. Crea fact_ventas vacía.
  3. Carga 100.000 filas históricas desde data/ventas.parquet (ETL).
  4. Genera ~1.300.011 ventas sintéticas (generador vectorizado) → ~1.400.011 total.
  5. Aplica migraciones y reintegra pedidos del portal.
  6. Opcional: ETL incremental para refrescar tablas anal_*.

Uso:
  python scripts/regenerar_fact_ventas.py
  python scripts/regenerar_fact_ventas.py --run-etl
"""

from __future__ import annotations

import argparse
import shutil
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "apps" / "admin"))

import duckdb

DEFAULT_BACKUP = ROOT / "db" / "globtrade.duckdb.bak_rebuild_20260827_202003"
TARGET = ROOT / "db" / "globtrade.duckdb"
NEW = ROOT / "db" / "globtrade_regen.duckdb"
PARQUET = ROOT / "data" / "ventas.parquet"
TARGET_ROWS = 1_400_011
PARQUET_ROWS = 100_000
GENERATE_TOTAL = TARGET_ROWS - PARQUET_ROWS  # 1_300_011

SKIP = frozenset({"fact_ventas", "wishlist", "wishlist_items", "wishlist_catalogos", "zonas_envio"})

FACT_VENTAS_DDL = """
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


def _tables(backup: Path) -> list[str]:
    con = duckdb.connect(str(backup), read_only=True)
    rows = con.execute(
        "SELECT table_name FROM information_schema.tables "
        "WHERE table_schema='main' AND table_type='BASE TABLE' ORDER BY table_name"
    ).fetchall()
    con.close()
    return [r[0] for r in rows]


def _copy_table(backup: Path, dst: duckdb.DuckDBPyConnection, table: str) -> int:
    dst.execute(f"ATTACH '{backup.as_posix()}' AS src (READ_ONLY)")
    try:
        dst.execute(f"CREATE TABLE {table} AS SELECT * FROM src.{table}")
        return int(dst.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
    finally:
        dst.execute("DETACH src")


def rebuild(backup: Path, *, run_etl: bool = False) -> dict:
    if not backup.exists():
        raise SystemExit(f"No existe backup: {backup}")
    if not PARQUET.exists():
        raise SystemExit(f"No existe parquet: {PARQUET}")

    if NEW.exists():
        NEW.unlink()

    dst = duckdb.connect(str(NEW))
    tables = _tables(backup)
    copied, skipped = [], []

    print("Fase 1 — copiando tablas sanas del backup...")
    for table in tables:
        if table in SKIP:
            skipped.append(table)
            print(f"  SKIP {table} (se recrea después)")
            continue
        try:
            n = _copy_table(backup, dst, table)
            copied.append((table, n))
            print(f"  OK {table}: {n:,}")
        except Exception as exc:
            skipped.append(table)
            print(f"  FAIL {table}: {exc}")

    print("Fase 2 — fact_ventas: parquet + generador...")
    dst.execute(FACT_VENTAS_DDL)

    from backend.services.etl_service import importar_parquet_db
    from backend.services.generador_service import generar_ventas

    imp = importar_parquet_db(dst, PARQUET)
    print(f"  Parquet: +{imp['inserted']:,} filas (total {imp['total_ventas']:,})")

    restante = GENERATE_TOTAL
    lote = 500_000
    generados = 0
    t0 = time.perf_counter()
    while restante > 0:
        n = min(restante, lote)
        res = generar_ventas(dst, n)
        generados += res["inserted"]
        restante -= n
        print(
            f"  Generador: +{res['inserted']:,} "
            f"({res['registros_por_segundo']:,.0f} reg/s) · total {res['total_ventas']:,}"
        )
    gen_s = round(time.perf_counter() - t0, 1)

    fv = int(dst.execute("SELECT COUNT(*) FROM fact_ventas").fetchone()[0])
    rev = float(dst.execute("SELECT SUM(CAST(total_revenue AS DOUBLE)) FROM fact_ventas").fetchone()[0] or 0)

    print("Fase 3 — migraciones y portal...")
    from shared.database.migrate_reestructuracion import aplicar_migraciones_reestructuracion
    from shared.services.integracion_ventas_service import reintegrar_pedidos_pendientes

    aplicar_migraciones_reestructuracion(dst)
    from shared.database.init_sistema import _create_views

    _create_views(dst)
    reint = reintegrar_pedidos_pendientes(dst)
    print(f"  Portal reintegrado: +{reint.get('insertadas', 0)} líneas")

    dst.close()

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    if TARGET.exists():
        old = TARGET.with_suffix(f".duckdb.pre_regen_{stamp}")
        print(f"Respaldo BD actual -> {old.name}")
        shutil.copy2(TARGET, old)

    if NEW.exists():
        if TARGET.exists():
            TARGET.unlink()
        NEW.rename(TARGET)
        wal = TARGET.with_suffix(".duckdb.wal")
        if wal.exists():
            wal.unlink()

    result = {
        "fact_ventas": fv,
        "parquet": imp["inserted"],
        "generados": generados,
        "ingresos": rev,
        "gen_segundos": gen_s,
        "tablas_copiadas": len(copied),
    }

    if run_etl:
        _run_etl()

    return result


def _run_etl() -> None:
    import subprocess

    script = ROOT / "etl-airflow" / "scripts" / "ejecutar_etl.py"
    if not script.exists():
        return
    print("Fase 4 — ETL incremental (anal_*)...")
    env = {**dict(__import__("os").environ), "PYTHONPATH": f"{ROOT};{ROOT / 'apps' / 'admin'};{ROOT / 'apps' / 'portal'};{ROOT / 'etl-airflow' / 'dags'}"}
    subprocess.run(
        [sys.executable, str(script), "--estrategia", "incremental"],
        cwd=str(ROOT),
        env=env,
        check=False,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Regenera fact_ventas (~1,4M filas).")
    parser.add_argument("--backup", type=Path, default=DEFAULT_BACKUP)
    parser.add_argument("--run-etl", action="store_true")
    args = parser.parse_args()

    print(f"Objetivo: {TARGET_ROWS:,} filas ({PARQUET_ROWS:,} parquet + {GENERATE_TOTAL:,} sintéticas)")
    result = rebuild(args.backup, run_etl=args.run_etl)
    print(
        f"\nListo.\n"
        f"  fact_ventas: {result['fact_ventas']:,}\n"
        f"  parquet:     {result['parquet']:,}\n"
        f"  generados:   {result['generados']:,} en {result['gen_segundos']}s\n"
        f"  ingresos:    ${result['ingresos']:,.2f}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
