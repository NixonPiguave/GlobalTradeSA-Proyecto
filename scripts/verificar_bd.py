"""
Verifica que globtrade.duckdb se pueda abrir y ejecutar consultas básicas.

Uso:
  python scripts/verificar_bd.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import duckdb

from shared.api.db_errors import mensaje_error_bd

TARGET = ROOT / "db" / "globtrade.duckdb"
BACKUP = ROOT / "db" / "globtrade.duckdb.bak_rebuild_20260827_202003"


def probar(path: Path) -> bool:
    print(f"Comprobando {path.name}...")
    try:
        conn = duckdb.connect(str(path), read_only=True)
        conn.execute("SELECT 1").fetchone()
        for tabla in ("pedidos", "dim_cliente", "carritos", "fact_ventas"):
            try:
                n = conn.execute(f"SELECT COUNT(*) FROM {tabla}").fetchone()[0]
                print(f"  {tabla}: {n:,} filas")
            except duckdb.Error as exc:
                print(f"  {tabla}: ERROR — {exc}")
        conn.close()
        return True
    except duckdb.Error as exc:
        print(f"  FALLO — {mensaje_error_bd(exc)}")
        return False


def main() -> int:
    ok = probar(TARGET)
    if not ok:
        print()
        print("La base activa no es usable. Opciones:")
        if BACKUP.exists():
            print(f"  1. Copiar respaldo sano: {BACKUP.name} -> globtrade.duckdb")
            print("  2. Regenerar ventas: python scripts/regenerar_fact_ventas.py")
        return 1
    print("Base de datos OK.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
