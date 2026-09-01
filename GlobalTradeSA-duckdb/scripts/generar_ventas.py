#!/usr/bin/env python3
"""Genera ventas sintéticas (vectorizado, bulk INSERT)."""

from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import duckdb

from backend.services.generador_service import generar_ventas

DB_PATH = ROOT / "db" / "globtrade.duckdb"
CANTIDAD = 100_000


def main() -> None:
    if not DB_PATH.exists():
        print(f"Error: ejecute primero scripts/cargar_duckdb.py ({DB_PATH} no existe)")
        sys.exit(1)

    con = duckdb.connect(str(DB_PATH))
    result = generar_ventas(con, CANTIDAD)
    total = con.execute("SELECT COUNT(*) FROM fact_ventas").fetchone()[0]
    con.close()

    print(
        f"✅ {result['registros']:,} registros generados en "
        f"{result['tiempo_segundos']:.3f} segundos "
        f"({result['registros_por_segundo']:,.3f} reg/seg)"
    )
    print(f"Total en fact_ventas: {total:,}")


if __name__ == "__main__":
    main()
