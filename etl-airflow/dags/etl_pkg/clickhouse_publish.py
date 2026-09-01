"""Reexporta publicación ClickHouse desde shared (usable por Airflow y admin)."""
from __future__ import annotations

import sys
from pathlib import Path

_raiz = Path("/proyecto")
if _raiz.is_dir() and str(_raiz) not in sys.path:
    sys.path.insert(0, str(_raiz))
else:
    # Ejecución local fuera de Docker
    _local = Path(__file__).resolve().parents[3]
    if str(_local) not in sys.path:
        sys.path.insert(0, str(_local))

from shared.services.clickhouse_publish import ejecutar, publicar_desde_duckdb

__all__ = ["ejecutar", "publicar_desde_duckdb"]
