from __future__ import annotations

import duckdb
from fastapi import APIRouter, Depends

from gmbackend.database import get_db

router = APIRouter(prefix="/api/catalogo", tags=["catalogo"])


@router.get("/paises", summary="Listar países para selects (registro y perfil)")
def paises(conn: duckdb.DuckDBPyConnection = Depends(get_db)) -> list[dict]:
    rows = conn.execute(
        "SELECT DISTINCT country FROM dim_country WHERE country IS NOT NULL ORDER BY country"
    ).fetchall()
    return [{"country": r[0]} for r in rows]