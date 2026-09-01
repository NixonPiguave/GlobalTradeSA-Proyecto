"""Post-rebuild: elimina WAL obsoleto y aplica DDL faltante."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import duckdb
from shared.database.init_sistema import _create_extended_tables
from shared.database.migrate_reestructuracion import aplicar_migraciones_reestructuracion

DB = ROOT / "db" / "globtrade.duckdb"
WAL = DB.with_suffix(".duckdb.wal")
if WAL.exists():
    WAL.unlink()
    print("WAL eliminado")

c = duckdb.connect(str(DB))
aplicar_migraciones_reestructuracion(c)
_create_extended_tables(c)
c.execute(
    """
    CREATE TABLE IF NOT EXISTS wishlist_items (
      id_item BIGINT PRIMARY KEY, id_cliente BIGINT, id_producto BIGINT, fecha TIMESTAMP
    )
    """
)
c.execute("CHECKPOINT")
rev = c.execute("SELECT SUM(CAST(total_revenue AS DOUBLE)) FROM fact_ventas").fetchone()[0]
print(f"OK fact_ventas sum={float(rev or 0):,.0f}")
c.close()
