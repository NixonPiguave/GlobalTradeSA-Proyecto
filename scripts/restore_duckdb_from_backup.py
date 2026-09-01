"""
Restaura globtrade.duckdb desde un backup sano conservando fact_ventas (~1,4M filas).

A diferencia de rebuild_duckdb.py (que recarga fact_ventas desde parquet = 100k),
este script copia fact_ventas del backup y solo recrea tablas corruptas
(wishlist*, zonas_envio).

Uso:
  python scripts/restore_duckdb_from_backup.py
  python scripts/restore_duckdb_from_backup.py --backup db/globtrade.duckdb.broken
  python scripts/restore_duckdb_from_backup.py --run-etl   # refresca tablas anal_*
"""

from __future__ import annotations

import argparse
import shutil
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "apps" / "admin"))

import duckdb

DEFAULT_BACKUP = ROOT / "db" / "globtrade.duckdb.bak_rebuild_20260827_202003"
TARGET = ROOT / "db" / "globtrade.duckdb"
NEW = ROOT / "db" / "globtrade_restored.duckdb"

# Tablas con metadata corrupta detectada en el backup del 27/08/2026
SKIP_TABLES = frozenset({
    "wishlist",
    "wishlist_items",
    "wishlist_catalogos",
    "zonas_envio",
})


def _list_tables(conn: duckdb.DuckDBPyConnection) -> list[str]:
    return [
        r[0]
        for r in conn.execute(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema='main' AND table_type='BASE TABLE' "
            "ORDER BY table_name"
        ).fetchall()
    ]


def restore(backup: Path) -> dict:
    if not backup.exists():
        raise SystemExit(f"No existe el backup: {backup}")

    if NEW.exists():
        NEW.unlink()

    src = duckdb.connect(str(backup), read_only=True)
    tables = _list_tables(src)
    src.close()

    dst = duckdb.connect(str(NEW))
    dst.execute(f"ATTACH '{backup.as_posix()}' AS old (READ_ONLY)")

    def _reopen_dst() -> duckdb.DuckDBPyConnection:
        nonlocal dst
        try:
            dst.execute("DETACH old")
        except Exception:
            pass
        try:
            dst.close()
        except Exception:
            pass
        dst = duckdb.connect(str(NEW))
        dst.execute(f"ATTACH '{backup.as_posix()}' AS old (READ_ONLY)")
        return dst

    copied: list[tuple[str, int]] = []
    skipped: list[tuple[str, str]] = []

    for table in tables:
        if table in SKIP_TABLES:
            skipped.append((table, "tabla marcada como corrupta; se recreará vacía"))
            continue
        try:
            dst.execute(f"CREATE TABLE {table} AS SELECT * FROM old.{table}")
            n = int(dst.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
            copied.append((table, n))
            print(f"  OK {table}: {n:,} filas")
        except Exception as exc:
            skipped.append((table, str(exc)[:120]))
            print(f"  SKIP {table}: {exc}")
            _reopen_dst()

    dst.execute("DETACH old")

    from shared.database.migrate_reestructuracion import aplicar_migraciones_reestructuracion
    from shared.services.integracion_ventas_service import reintegrar_pedidos_pendientes

    print("Aplicando migraciones (wishlist, zonas_envio, etc.)...")
    aplicar_migraciones_reestructuracion(dst)

    reint = reintegrar_pedidos_pendientes(dst)
    print(f"Portal reintegrado: +{reint.get('insertadas', 0)} líneas")

    fv = int(dst.execute("SELECT COUNT(*) FROM fact_ventas").fetchone()[0])
    rev = dst.execute(
        "SELECT SUM(CAST(total_revenue AS DOUBLE)) FROM fact_ventas"
    ).fetchone()[0]
    print(f"Verificación fact_ventas: {fv:,} filas · ingresos ~ ${float(rev or 0):,.2f}")

    dst.close()

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    if TARGET.exists():
        corrupt = TARGET.with_suffix(f".duckdb.corrupt_{stamp}")
        print(f"Respaldo de BD actual -> {corrupt.name}")
        TARGET.rename(corrupt)

    NEW.rename(TARGET)
    wal = TARGET.with_suffix(".duckdb.wal")
    if wal.exists():
        wal.unlink()

    return {
        "backup": str(backup),
        "fact_ventas": fv,
        "tablas_copiadas": len(copied),
        "tablas_omitidas": skipped,
    }


def run_etl_incremental() -> None:
    etl_script = ROOT / "etl-airflow" / "scripts" / "ejecutar_etl.py"
    if not etl_script.exists():
        print("ETL no encontrado; omitiendo.")
        return
    import subprocess

    print("Ejecutando ETL incremental (solo tablas anal_*, sin borrar fact_ventas)...")
    subprocess.run(
        [sys.executable, str(etl_script), "--estrategia", "incremental"],
        cwd=str(ROOT),
        check=False,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Restaura DuckDB conservando ~1,4M ventas.")
    parser.add_argument(
        "--backup",
        type=Path,
        default=DEFAULT_BACKUP,
        help="Ruta al archivo .duckdb de respaldo",
    )
    parser.add_argument(
        "--run-etl",
        action="store_true",
        help="Tras restaurar, ejecuta ETL incremental para refrescar anal_*",
    )
    args = parser.parse_args()

    print(f"Restaurando desde {args.backup.name} ...")
    result = restore(args.backup)
    print(f"Listo. fact_ventas = {result['fact_ventas']:,} filas.")

    if args.run_etl:
        run_etl_incremental()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
