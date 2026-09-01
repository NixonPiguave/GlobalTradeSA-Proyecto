"""Refresca vista ventas, tablas anal_* y etl_control para el dashboard ERP."""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from shared.database.connection import connect, resolve_duckdb_path
from shared.services.analiticas_service import refrescar_analiticas_dashboard


def main() -> int:
    db_path = resolve_duckdb_path(os.environ.get("DUCKDB_PATH"))
    print(f"Base de datos: {db_path}")
    conn = connect(str(db_path))
    try:
        result = refrescar_analiticas_dashboard(conn)
        print(f"OK: {result['filas_fact_ventas']:,} filas en fact_ventas")
        print(f"OK: {result['tablas_analiticas']} tablas analíticas")
        for row in result["kpis"]:
            print(f"  · {row['kpi']}: {row['valor']:,.2f} {row['unidad']}")
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
