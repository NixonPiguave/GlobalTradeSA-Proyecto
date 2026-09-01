"""
run.py — Arranque unificado GlobalTrade S.A. (un solo proceso, DuckDB compartido).

Panel administrativo :8000  (apps/admin/backend)
Portal B2B           :8001  (apps/portal/gmbackend)
"""

from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path

import uvicorn

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "apps" / "admin"))
sys.path.insert(0, str(ROOT / "apps" / "portal"))

from backend.main import app as admin_app
from gmbackend.main import app as b2b_app

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("unified")

ADMIN_PORT = 8000
B2B_PORT = 8001


def _migrate_db() -> None:
    """Aplica migraciones idempotentes antes de abrir los dos servidores.

    Asegura que existan secuencias y tablas (compras, recepciones, logística,
    fact_compras, zonas/tarifas) aunque la BD provenga de una versión anterior.
    """
    import duckdb

    from backend.config import get_settings
    from shared.database.init_sistema import (
        _create_erp_tables,
        _create_legacy_b2b_tables,
        _create_views,
        _ensure_sequences,
        _extend_compras,
        _extend_pedidos,
    )

    path = get_settings().duckdb_absolute_path
    try:
        conn = duckdb.connect(str(path))
    except duckdb.Error as exc:
        from shared.api.db_errors import mensaje_error_bd

        logger.error("No se pudo abrir DuckDB (%s): %s", path, exc)
        logger.error(mensaje_error_bd(exc))
        logger.error(
            "Restaura con: copy db\\globtrade.duckdb.bak_rebuild_20260827_202003 db\\globtrade.duckdb "
            "o ejecuta: python scripts/regenerar_fact_ventas.py"
        )
        raise SystemExit(1) from exc
    try:
        _ensure_sequences(conn)
        _create_legacy_b2b_tables(conn)
        _create_erp_tables(conn)
        _extend_pedidos(conn)
        _extend_compras(conn)
        _create_views(conn)
    finally:
        conn.close()


async def _serve() -> None:
    admin_cfg = uvicorn.Config(admin_app, host="0.0.0.0", port=ADMIN_PORT, log_level="info")
    b2b_cfg = uvicorn.Config(b2b_app, host="0.0.0.0", port=B2B_PORT, log_level="info")
    await asyncio.gather(uvicorn.Server(admin_cfg).serve(), uvicorn.Server(b2b_cfg).serve())


if __name__ == "__main__":
    logger.info("Iniciando GlobalTrade unificado: admin=%s portal=%s", ADMIN_PORT, B2B_PORT)
    _migrate_db()
    asyncio.run(_serve())
