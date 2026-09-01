"""
gmbackend/database.py — Conexión DuckDB compartida con el admin (run.py unificado).

Proxy serializado vía shared.database.connection (un hilo DuckDB).
"""

from __future__ import annotations

from collections.abc import Generator

import duckdb
from fastapi import Depends, HTTPException

from gmbackend.config import Settings, get_settings
from shared.api.db_errors import codigo_http_bd, detalle_respuesta_bd
from shared.database.connection import SerializedConnection, shared_connection


def get_db(
    settings: Settings = Depends(get_settings),
) -> Generator[SerializedConnection | duckdb.DuckDBPyConnection, None, None]:
    try:
        with shared_connection(settings.duckdb_absolute_path) as conn:
            conn.execute("SELECT 1").fetchone()
            yield conn
    except duckdb.Error as exc:
        detail = detalle_respuesta_bd(exc)
        raise HTTPException(
            status_code=codigo_http_bd(exc),
            detail={"message": detail["message"], "tipo": detail.get("tipo")},
        ) from exc
