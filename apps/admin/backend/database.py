"""
database.py — Conexión DuckDB embebida y helpers SQL.

Requisitos cubiertos: 1.3, 1.4, 1.6, 1.7, 1.8, 7.2, 7.6
"""

from __future__ import annotations

import logging
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Optional

import duckdb
from fastapi import HTTPException

from shared.api.db_errors import codigo_http_bd, detalle_respuesta_bd, es_error_bd
from shared.database.connection import close_shared, shared_connection

logger = logging.getLogger(__name__)

_query_time_local = threading.local()
_conn_local = threading.local()

_db_path: Optional[str] = None
_init_lock = threading.Lock()
_db_revision: int = 0
_revision_lock = threading.Lock()

QUERY_TIMEOUT_SECONDS: int = 30


def _is_readonly() -> bool:
    return str((__import__("os").environ.get("DUCKDB_READONLY", "") or "")).strip().lower() in {"1", "true", "yes"}

_INDEX_DEFINITIONS: list[tuple[str, str]] = [
    # Solo order_id: idx_fact_order_date rompe UPDATE en order_date (bug DuckDB + ART).
    ("idx_fact_order_id", "CREATE INDEX IF NOT EXISTS idx_fact_order_id ON fact_ventas(order_id)"),
]

_OBSOLETE_INDEXES: list[str] = [
    "idx_fact_order_date",
    "idx_fact_region",
    "idx_fact_country",
    "idx_fact_channel",
    "idx_fact_id_venta",
    "idx_fact_item_type",
    "idx_fact_date_region",
]


def reset_query_time() -> None:
    _query_time_local.total_ms = 0.0


def get_query_time_ms() -> int:
    return int(getattr(_query_time_local, "total_ms", 0.0))


def _add_query_time(elapsed_seconds: float) -> None:
    current = getattr(_query_time_local, "total_ms", 0.0)
    _query_time_local.total_ms = current + elapsed_seconds * 1000.0


def init_db(db_path: str) -> None:
    """Inicializa la ruta de la base DuckDB y verifica que el archivo exista o se pueda crear."""
    global _db_path

    with _init_lock:
        if _db_path is not None:
            logger.warning("init_db() llamado cuando DuckDB ya estaba inicializado; se omite.")
            return

        path = Path(db_path)
        path.parent.mkdir(parents=True, exist_ok=True)

        logger.info("Inicializando DuckDB embebido en: %s", path.resolve())

        try:
            with shared_connection(path) as conn:
                conn.execute("SELECT 1").fetchone()
        except duckdb.Error as exc:
            logger.error("Fallo al conectar con DuckDB: %s", exc)
            raise

        _db_path = str(path.resolve())
        logger.info("DuckDB inicializado correctamente.")


def get_db_revision() -> int:
    """Versión lógica de la BD; se incrementa tras escrituras masivas o CRUD."""
    return _db_revision


def notify_db_changed(conn: duckdb.DuckDBPyConnection | None = None) -> None:
    """
    Hace visibles los cambios entre conexiones DuckDB del mismo proceso.
    Tras CHECKPOINT, invalida conexiones en otros hilos en su próximo acceso.
    """
    global _db_revision
    if conn is not None:
        try:
            conn.execute("CHECKPOINT")
        except duckdb.Error as exc:
            logger.debug("CHECKPOINT omitido: %s", exc)
    with _revision_lock:
        _db_revision += 1


def release_thread_connection() -> None:
    """Cierra la conexión DuckDB del hilo actual sin invalidar la ruta global."""
    conn = getattr(_conn_local, "conn", None)
    if conn is not None:
        try:
            conn.close()
        except Exception as exc:
            logger.warning("Error al cerrar conexión DuckDB del hilo: %s", exc)
        _conn_local.conn = None
        _conn_local.revision = None


def close_db() -> None:
    """Cierra la conexión compartida y resetea la ruta (apagado del servidor)."""
    global _db_path
    release_thread_connection()
    close_shared()
    _db_path = None
    logger.info("Conexión DuckDB cerrada.")


@contextmanager
def get_connection():
    """Context manager: conexión DuckDB compartida serializada (admin + portal)."""
    if _db_path is None:
        raise HTTPException(
            status_code=503,
            detail={
                "code": 503,
                "message": "Servidor temporalmente no disponible",
                "detail": "La base de datos DuckDB no ha sido inicializada.",
            },
        )
    with shared_connection(_db_path) as conn:
        yield conn


def execute_query(
    conn: duckdb.DuckDBPyConnection,
    sql: str,
    params: Optional[tuple | list] = None,
    timeout_seconds: int = QUERY_TIMEOUT_SECONDS,
    fetch: str = "all",
) -> Any:
    """
    Ejecuta una consulta SQL parametrizada con marcadores ``?``.

    Args:
        conn: Conexión DuckDB del hilo actual.
        sql: SQL con placeholders ``?``.
        params: Valores para los placeholders.
        timeout_seconds: Reservado para compatibilidad (DuckDB embebido).
        fetch: ``all``, ``one`` o ``none``.
    """
    _ = timeout_seconds
    start_time = time.monotonic()

    try:
        if params is not None:
            result = conn.execute(sql, params)
        else:
            result = conn.execute(sql)

        elapsed = time.monotonic() - start_time
        _add_query_time(elapsed)

        if fetch == "all":
            rows = result.fetchall()
            logger.debug("Consulta ejecutada en %.3f s: %s", elapsed, sql[:120])
            return rows
        if fetch == "one":
            row = result.fetchone()
            logger.debug("Consulta ejecutada en %.3f s: %s", elapsed, sql[:120])
            return row
        logger.debug("Consulta ejecutada en %.3f s: %s", elapsed, sql[:120])
        return None

    except duckdb.Error as exc:
        logger.error("Error de base de datos al ejecutar consulta: %s", exc)
        try:
            conn.rollback()
        except Exception:
            pass
        msg = str(exc).lower()
        if "timeout" in msg or "interrupted" in msg:
            raise HTTPException(
                status_code=504,
                detail={
                    "code": 504,
                    "message": "Tiempo límite de consulta excedido",
                    "detail": f"La consulta superó el límite de {timeout_seconds} segundos.",
                },
            ) from exc
        if es_error_bd(exc):
            detail = detalle_respuesta_bd(exc)
            raise HTTPException(
                status_code=codigo_http_bd(exc),
                detail={"message": detail["message"], "tipo": detail.get("tipo")},
            ) from exc
        raise HTTPException(
            status_code=503,
            detail={"message": detalle_respuesta_bd(exc)["message"]},
        ) from exc


def create_indexes() -> None:
    """Crea índices sobre fact_ventas si la tabla existe."""
    logger.info("Verificando y creando índices sobre fact_ventas...")

    if _db_path is None:
        logger.error("create_indexes() llamado antes de init_db(); se omite.")
        return

    if _is_readonly():
        logger.info("Modo DUCKDB_READONLY=1: se omite creación/eliminación de índices.")
        return

    try:
        with get_connection() as conn:
            tables = conn.execute(
                "SELECT table_name FROM information_schema.tables WHERE table_name = 'fact_ventas'"
            ).fetchall()
            if not tables:
                logger.warning("Tabla fact_ventas no existe; se omiten índices.")
                return

            for obsolete in _OBSOLETE_INDEXES:
                try:
                    conn.execute(f"DROP INDEX IF EXISTS {obsolete}")
                    logger.info("Índice obsoleto '%s' eliminado.", obsolete)
                except duckdb.Error:
                    pass

            for index_name, ddl in _INDEX_DEFINITIONS:
                try:
                    conn.execute(ddl)
                    logger.info("Índice '%s' verificado/creado correctamente.", index_name)
                except duckdb.Error as exc:
                    logger.warning(
                        "No se pudo crear el índice '%s': %s. El arranque continúa.",
                        index_name,
                        exc,
                    )
    except HTTPException:
        logger.warning("No se pudo obtener conexión para crear índices.")

    logger.info("Proceso de creación de índices finalizado.")
    release_thread_connection()


def warmup_worker() -> None:
    """
    Precalienta librerías analíticas y una conexión DuckDB en un hilo de trabajo.
    Evita bloqueos o demoras en la primera petición POST tras el arranque.
    """
    import numpy as _np  # noqa: F401
    import pyarrow as _pa  # noqa: F401

    _ = _np, _pa
    if _db_path is None:
        return
    try:
        with get_connection() as conn:
            conn.execute("SELECT COUNT(*) FROM fact_ventas").fetchone()
    except duckdb.Error as exc:
        logger.warning("Warm-up DuckDB omitido: %s", exc)
    finally:
        release_thread_connection()
