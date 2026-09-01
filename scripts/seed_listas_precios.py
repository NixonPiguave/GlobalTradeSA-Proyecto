"""
Carga precios de ejemplo en listas Público / Mayorista y asigna clientes demo.

Ejecutar desde la raíz:
    python scripts/seed_listas_precios.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import duckdb

from shared.database.seed_listas_precios import seed_listas_precios

DB = Path(os.environ.get("DUCKDB_PATH", ROOT / "db" / "globtrade.duckdb"))


def main() -> None:
    conn = duckdb.connect(str(DB))
    try:
        msg = seed_listas_precios(conn)
        conn.execute("CHECKPOINT")
        print(f"OK: {msg}")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
