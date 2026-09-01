"""
routers/etl.py — Endpoints ETL de GLOBTRADE S.A.

Rutas (montadas bajo /api/etl):
    POST /api/etl/upload            — Carga CSV multipart/form-data
    GET  /api/etl/progress/{job_id} — Progreso del job ETL
    POST /api/etl/pipeline          — Pipeline completo (extracción→carga)
    POST /api/etl/pipeline/internal — Pipeline vía token interno (Airflow/Docker)

Requisitos cubiertos: 3.1, 3.7, 3.11
"""

from __future__ import annotations

import asyncio
import logging
import os

from fastapi import APIRouter, File, Header, HTTPException, UploadFile
from pydantic import BaseModel, Field

from backend.database import get_connection, notify_db_changed, release_thread_connection
from backend.services.etl_service import process_csv, get_job_progress, importar_parquet
from shared.services.etl_pipeline_service import ejecutar_pipeline

logger = logging.getLogger(__name__)

router = APIRouter()
internal_router = APIRouter()


class PipelineRequest(BaseModel):
    estrategia: str = Field(default="incremental", pattern="^(incremental|rebuild)$")


def _pipeline_sync(estrategia: str) -> dict:
    try:
        with get_connection() as conn:
            resumen = ejecutar_pipeline(conn, estrategia=estrategia)
            notify_db_changed(conn)
            return resumen
    finally:
        release_thread_connection()


def _validar_token_interno(token: str | None) -> None:
    esperado = os.environ.get("ETL_INTERNAL_TOKEN", "").strip()
    if not esperado or not token or token.strip() != esperado:
        raise HTTPException(status_code=403, detail="Token interno ETL inválido.")


@internal_router.post("/pipeline/internal", summary="Pipeline ETL (token interno Airflow/Docker)")
async def etl_pipeline_internal(
    body: PipelineRequest,
    x_etl_internal_token: str | None = Header(default=None, alias="X-ETL-Internal-Token"),
) -> dict:
    _validar_token_interno(x_etl_internal_token)
    try:
        return await asyncio.to_thread(_pipeline_sync, body.estrategia)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/pipeline", summary="Ejecutar pipeline ETL completo")
async def etl_pipeline(body: PipelineRequest) -> dict:
    """Extracción → transformación → carga en la conexión compartida (seguro con portal activo)."""
    try:
        return await asyncio.to_thread(_pipeline_sync, body.estrategia)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


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
