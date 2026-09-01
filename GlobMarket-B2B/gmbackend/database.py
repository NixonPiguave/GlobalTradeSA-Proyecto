"""
gmbackend/database.py — Conexión DuckDB (DI por request).

Reglas:
- Una conexión por request (yield dependency) y cierre garantizado.
- Consultas siempre parametrizadas con '?'.
"""

from __future__ import annotations

from collections.abc import Generator

import duckdb
from fastapi import Depends

from gmbackend.config import Settings, get_settings


def crear_conexion(settings: Settings) -> duckdb.DuckDBPyConnection:
    return duckdb.connect(str(settings.duckdb_absolute_path))


def get_db(settings: Settings = Depends(get_settings)) -> Generator[duckdb.DuckDBPyConnection, None, None]:
    conn = crear_conexion(settings)
    try:
        yield conn
    finally:
        try:
            conn.close()
        except Exception:
            pass

