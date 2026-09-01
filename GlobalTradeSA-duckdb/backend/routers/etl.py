"""
routers/etl.py — Endpoints ETL de GLOBTRADE S.A.

Rutas (montadas bajo /api/etl):
    POST /api/etl/upload            — Carga CSV multipart/form-data
    GET  /api/etl/progress/{job_id} — Progreso del job ETL

Requisitos cubiertos: 3.1, 3.7, 3.11
"""

from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, File, UploadFile

from backend.database import get_connection, release_thread_connection
from backend.services.etl_service import process_csv, get_job_progress, importar_parquet

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/upload", summary="Cargar archivo CSV de ventas")
async def etl_upload(file: UploadFile = File(..., description="Archivo CSV de ventas")) -> dict:
    """
    Recibe un archivo CSV multipart, lo procesa con el servicio ETL y devuelve
    el resumen con inserted, rejected y detalle de errores.
    Requisito 3.1, 3.7
    """
    content = await file.read()
    filename = file.filename or "upload.csv"

    def _process() -> dict:
        try:
            with get_connection() as conn:
                return process_csv(content, filename, conn).model_dump()
        finally:
            release_thread_connection()

    return await asyncio.to_thread(_process)


@router.get("/progress/{job_id}", summary="Progreso de un job ETL")
def etl_progress(job_id: str) -> dict:
    """
    Devuelve el progreso (0–100 %) y estado de un job ETL activo.
    Requisito 3.11
    """
    return get_job_progress(job_id)


def _importar_parquet_sync() -> dict:
    try:
        with get_connection() as conn:
            return importar_parquet(conn)
    finally:
        release_thread_connection()


@router.post("/importar-parquet", summary="Importar data/ventas.parquet a fact_ventas")
async def etl_importar_parquet() -> dict:
    """
    Carga masiva desde parquet usando INSERT INTO ... SELECT (nativo DuckDB).
    Omite order_id duplicados.
    """
    return await asyncio.to_thread(_importar_parquet_sync)
