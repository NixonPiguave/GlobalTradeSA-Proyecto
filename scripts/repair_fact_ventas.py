"""
Repara fact_ventas corrupta: recrea la tabla e importa desde data/ventas.parquet
y reintegra pedidos del portal pagados.

Uso (desde la raíz del repo, con servicios detenidos si hay bloqueo):
    python scripts/repair_fact_ventas.py
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

DB_PATH = ROOT / "db" / "globtrade.duckdb"
PARQUET = ROOT / "data" / "ventas.parquet"


def _tabla_sana(conn: duckdb.DuckDBPyConnection) -> bool:
    try:
        conn.execute(
            "SELECT SUM(CAST(total_revenue AS DOUBLE)) FROM fact_ventas"
        ).fetchone()
        return True
    except Exception:
        return False


def main() -> None:
    if not DB_PATH.exists():
        raise SystemExit(f"No existe la BD: {DB_PATH}")
    if not PARQUET.exists():
        raise SystemExit(f"No existe {PARQUET}")

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = DB_PATH.with_suffix(f".duckdb.bak_repair_{stamp}")
    print(f"Copia de seguridad -> {backup.name}")
    shutil.copy2(DB_PATH, backup)

    def _repair(conn: duckdb.DuckDBPyConnection) -> None:
        print("Recreando fact_ventas...")
        conn.execute("DROP TABLE IF EXISTS fact_ventas")
        conn.execute(
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

        imp = importar_parquet_db(conn, PARQUET)
        print(f"Parquet: +{imp['inserted']} filas (total {imp['total_ventas']})")

        from shared.services.integracion_ventas_service import reintegrar_pedidos_pendientes

        reint = reintegrar_pedidos_pendientes(conn)
        print(
            f"Portal: {reint['procesados']} pedidos, +{reint['insertadas']} lineas, "
            f"{reint['omitidas']} omitidas"
        )

        if not _tabla_sana(conn):
            raise RuntimeError("La tabla sigue corrupta tras la reparacion.")

        n = conn.execute("SELECT COUNT(*) FROM fact_ventas").fetchone()[0]
        rev = conn.execute(
            "SELECT SUM(CAST(total_revenue AS DOUBLE)) FROM fact_ventas"
        ).fetchone()[0]
        print(f"Reparacion OK: {n} filas, ingresos ~ ${float(rev or 0):,.2f}")

    conn = duckdb.connect(str(DB_PATH))
    try:
        if _tabla_sana(conn):
            n = conn.execute("SELECT COUNT(*) FROM fact_ventas").fetchone()[0]
            print(f"fact_ventas OK ({n} filas). No se requiere reparacion.")
            return
    except Exception:
        pass
    finally:
        conn.close()

    # Nueva conexion limpia tras posible invalidacion por lectura corrupta
    conn2 = duckdb.connect(str(DB_PATH))
    try:
        _repair(conn2)
    except duckdb.FatalException:
        conn2.close()
        print("BD invalidada; restaurando copia y reintentando...")
        shutil.copy2(backup, DB_PATH)
        conn3 = duckdb.connect(str(DB_PATH))
        try:
            _repair(conn3)
        finally:
            conn3.close()
    else:
        conn2.close()


if __name__ == "__main__":
    main()
