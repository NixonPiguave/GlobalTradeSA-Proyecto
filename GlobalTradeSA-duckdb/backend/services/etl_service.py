"""
etl_service.py — Lógica ETL para carga de CSV al modelo estrella DuckDB.

Cubre los Requisitos: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 3.8, 3.9, 3.10, 3.12
Propiedades de corrección: 2 (idempotencia de duplicados), 3 (consistencia del resumen)

Funciones públicas:
    process_csv(file_content, filename, conn) -> ETLResult
    get_job_progress(job_id) -> dict
    update_job_progress(job_id, progress_pct, status) -> None
"""

from __future__ import annotations

import io
import logging
import re
import threading
import uuid
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any

import pandas as pd
from fastapi import HTTPException

from backend.database import notify_db_changed
from backend.models.schemas import ETLResult

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------

MAX_FILE_SIZE_BYTES: int = 50 * 1024 * 1024  # 50 MB — Requisito 3.9

REQUIRED_COLUMNS: list[str] = [
    "region",
    "country",
    "item_type",
    "sales_channel",
    "order_priority",
    "order_date",
    "order_id",
    "ship_date",
    "units_sold",
    "unit_price",
    "unit_cost",
    "total_revenue",
    "total_cost",
    "total_profit",
]

NUMERIC_COLUMNS: list[str] = [
    "units_sold",
    "unit_price",
    "unit_cost",
    "total_revenue",
    "total_cost",
    "total_profit",
]

DATE_COLUMNS: list[str] = ["order_date", "ship_date"]

BATCH_SIZE: int = 1_000  # Requisito 3.6

# Patrón estricto YYYY-MM-DD
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

# ---------------------------------------------------------------------------
# Seguimiento de progreso de jobs (en memoria, thread-safe) — Requisito 3.11
# ---------------------------------------------------------------------------

_jobs: dict[str, dict[str, Any]] = {}
_jobs_lock = threading.Lock()


def _set_job(job_id: str, progress_pct: float, status: str) -> None:
    """Actualiza el estado de un job en el diccionario en memoria."""
    with _jobs_lock:
        _jobs[job_id] = {
            "job_id": job_id,
            "progress_pct": round(progress_pct, 2),
            "status": status,
        }


def get_job_progress(job_id: str) -> dict[str, Any]:
    """
    Devuelve el progreso de un job ETL.

    Returns:
        dict con ``job_id``, ``progress_pct`` (0–100) y ``status``
        (``"running"``, ``"completed"``, ``"failed"``).

    Raises:
        HTTPException(404): Si el job_id no existe.
    """
    with _jobs_lock:
        job = _jobs.get(job_id)
    if job is None:
        raise HTTPException(
            status_code=404,
            detail={
                "code": 404,
                "message": f"Job '{job_id}' no encontrado.",
            },
        )
    return job


def update_job_progress(job_id: str, progress_pct: int, status: str) -> None:
    """
    Actualiza el progreso de un job ETL existente o crea una entrada nueva.

    Función pública para que el router ETL pueda actualizar el estado del job
    desde fuera del servicio (p. ej., al iniciar el procesamiento asíncrono).

    Args:
        job_id: Identificador UUID del job.
        progress_pct: Porcentaje de progreso (0–100).
        status: Estado del job (``"running"``, ``"completed"``, ``"failed"``).
    """
    _set_job(job_id, float(progress_pct), status)


# ---------------------------------------------------------------------------
# Helpers de validación
# ---------------------------------------------------------------------------


def _try_decode(file_content: bytes) -> str:
    """
    Intenta decodificar *file_content* como UTF-8 y luego como latin-1.

    Raises:
        HTTPException(400): Si ambas codificaciones fallan.

    Returns:
        El texto decodificado.
    """
    for encoding in ("utf-8", "latin-1"):
        try:
            return file_content.decode(encoding)
        except (UnicodeDecodeError, ValueError):
            continue

    raise HTTPException(
        status_code=400,
        detail={
            "code": 400,
            "message": (
                "El archivo tiene un problema de codificación. "
                "No se pudo decodificar como UTF-8 ni como latin-1. "
                "Asegúrese de que el archivo esté codificado en UTF-8 o latin-1."
            ),
        },
    )


def _validate_columns(df: pd.DataFrame) -> None:
    """
    Verifica que el DataFrame contenga exactamente las 14 columnas requeridas.

    Raises:
        HTTPException(400): Con la lista de columnas faltantes.
    """
    # Normalizar nombres de columnas a minúsculas y sin espacios
    df.columns = [c.strip().lower() for c in df.columns]

    missing = [col for col in REQUIRED_COLUMNS if col not in df.columns]
    if missing:
        raise HTTPException(
            status_code=400,
            detail={
                "code": 400,
                "message": "El archivo CSV no contiene todas las columnas requeridas.",
                "detail": {
                    "missing_columns": missing,
                    "required_columns": REQUIRED_COLUMNS,
                },
            },
        )


def _validate_rows(df: pd.DataFrame) -> list[dict[str, Any]]:
    """
    Valida tipos de datos y formatos de fecha fila a fila.

    Returns:
        Lista de errores con ``{row, column, reason}`` para cada celda inválida.
        Lista vacía si todos los datos son válidos.
    """
    errors: list[dict[str, Any]] = []

    for idx, row in df.iterrows():
        # idx es 0-based desde pandas; el número de fila para el usuario es idx+2
        # (fila 1 = encabezado, fila 2 = primer dato)
        row_number = int(idx) + 2  # type: ignore[arg-type]

        # Validar columnas numéricas
        for col in NUMERIC_COLUMNS:
            value = row[col]
            if pd.isna(value):
                errors.append(
                    {
                        "row": row_number,
                        "column": col,
                        "reason": f"Valor nulo o vacío en columna numérica '{col}'.",
                    }
                )
                continue
            try:
                Decimal(str(value))
            except (InvalidOperation, ValueError, TypeError):
                errors.append(
                    {
                        "row": row_number,
                        "column": col,
                        "reason": f"Valor no numérico en '{col}': '{value}'.",
                    }
                )

        # Validar columnas de fecha (formato YYYY-MM-DD)
        for col in DATE_COLUMNS:
            value = row[col]
            if pd.isna(value):
                errors.append(
                    {
                        "row": row_number,
                        "column": col,
                        "reason": f"Valor nulo o vacío en columna de fecha '{col}'.",
                    }
                )
                continue
            str_value = str(value).strip()
            if not _DATE_RE.match(str_value):
                errors.append(
                    {
                        "row": row_number,
                        "column": col,
                        "reason": (
                            f"Formato de fecha inválido en '{col}': '{str_value}'. "
                            "Se esperaba YYYY-MM-DD."
                        ),
                    }
                )
                continue
            try:
                datetime.strptime(str_value, "%Y-%m-%d")
            except ValueError:
                errors.append(
                    {
                        "row": row_number,
                        "column": col,
                        "reason": (
                            f"Fecha inexistente en '{col}': '{str_value}'."
                        ),
                    }
                )

        # Validar order_id como entero
        order_id_val = row["order_id"]
        if pd.isna(order_id_val):
            errors.append(
                {
                    "row": row_number,
                    "column": "order_id",
                    "reason": "Valor nulo o vacío en 'order_id'.",
                }
            )
        else:
            try:
                int_val = int(float(str(order_id_val)))
                if int_val <= 0:
                    errors.append(
                        {
                            "row": row_number,
                            "column": "order_id",
                            "reason": (
                                f"'order_id' debe ser un entero positivo: '{order_id_val}'."
                            ),
                        }
                    )
            except (ValueError, TypeError):
                errors.append(
                    {
                        "row": row_number,
                        "column": "order_id",
                        "reason": (
                            f"'order_id' no es un entero válido: '{order_id_val}'."
                        ),
                    }
                )

    return errors


# ---------------------------------------------------------------------------
# Inserción por lotes
# ---------------------------------------------------------------------------

_INSERT_SQL = """
INSERT INTO fact_ventas (
    id_venta, order_id, id_region, id_country, id_item_type, id_channel, id_priority,
    order_date, ship_date, units_sold, unit_price, unit_cost,
    total_revenue, total_cost, total_profit
)
SELECT
    (SELECT COALESCE(MAX(id_venta), 0) FROM fact_ventas) + 1,
    ?,
    r.id_region,
    c.id_country,
    it.id_item_type,
    ch.id_channel,
    p.id_priority,
    CAST(? AS DATE),
    CAST(? AS DATE),
    ?, ?, ?, ?, ?, ?
FROM dim_region r
JOIN dim_country c ON c.country = ? AND c.id_region = r.id_region
JOIN dim_item_type it ON it.item_type = ?
JOIN dim_sales_channel ch ON ch.sales_channel = ?
JOIN dim_order_priority p ON p.order_priority = ?
WHERE r.region = ?
ON CONFLICT (order_id) DO NOTHING
RETURNING id_venta
"""


def _insert_batch(
    conn: Any,
    batch: pd.DataFrame,
    batch_index: int,
) -> tuple[int, int, list[dict[str, Any]]]:
    inserted = 0
    rejected = 0
    errors: list[dict[str, Any]] = []

    for idx, row in batch.iterrows():
        row_number = int(idx) + 2  # type: ignore[arg-type]
        region = str(row["region"]).strip()
        country = str(row["country"]).strip()
        item_type = str(row["item_type"]).strip()
        sales_channel = str(row["sales_channel"]).strip()
        order_priority = str(row["order_priority"]).strip()
        order_id = int(float(str(row["order_id"])))

        params = (
            order_id,
            str(row["order_date"]).strip(),
            str(row["ship_date"]).strip(),
            int(float(str(row["units_sold"]))),
            float(Decimal(str(row["unit_price"]))),
            float(Decimal(str(row["unit_cost"]))),
            float(Decimal(str(row["total_revenue"]))),
            float(Decimal(str(row["total_cost"]))),
            float(Decimal(str(row["total_profit"]))),
            country,
            item_type,
            sales_channel,
            order_priority,
            region,
        )
        try:
            result = conn.execute(_INSERT_SQL, params).fetchone()
            if result:
                inserted += 1
            else:
                rejected += 1
                errors.append({"row": row_number, "reason": f"order_id duplicado: {order_id}"})
        except Exception as exc:
            rejected += 1
            errors.append({"row": row_number, "reason": str(exc)})

    logger.info(
        "Lote %d: %d insertados, %d rechazados.",
        batch_index,
        inserted,
        rejected,
    )
    return inserted, rejected, errors


# ---------------------------------------------------------------------------
# Función principal ETL
# ---------------------------------------------------------------------------


def process_csv(file_content: bytes, filename: str, conn: Any) -> ETLResult:
    """
    Procesa un archivo CSV y carga los datos en la tabla ``ventas``.

    Flujo:
    1. Verificar tamaño (≤ 50 MB) — Requisito 3.9, 3.10
    2. Decodificar (UTF-8 → latin-1) — Requisito 3.5
    3. Leer con pandas y validar columnas — Requisito 3.2, 3.3
    4. Manejar CSV vacío — Requisito 3.12
    5. Validar tipos y fechas fila a fila — Requisito 3.4
    6. Insertar en lotes de 1,000 con ON CONFLICT DO NOTHING — Requisito 3.6, 3.8
    7. Devolver ETLResult — Requisito 3.7

    Args:
        file_content: Contenido binario del archivo CSV.
        filename: Nombre del archivo (para logging).
        conn: Conexión DuckDB obtenida con get_connection().

    Returns:
        ETLResult con job_id, inserted, rejected y errors.

    Raises:
        HTTPException(413): Si el archivo supera 50 MB.
        HTTPException(400): Si hay problemas de codificación o columnas faltantes.
        HTTPException(422): Si hay errores de validación de datos.
    """
    job_id = str(uuid.uuid4())
    _set_job(job_id, 0.0, "running")

    logger.info("Iniciando ETL job_id=%s archivo='%s' tamaño=%d bytes", job_id, filename, len(file_content))

    # ------------------------------------------------------------------
    # 1. Verificar tamaño — Requisito 3.9 / 3.10
    # ------------------------------------------------------------------
    if len(file_content) > MAX_FILE_SIZE_BYTES:
        _set_job(job_id, 0.0, "failed")
        raise HTTPException(
            status_code=413,
            detail={
                "code": 413,
                "message": (
                    f"El archivo supera el límite de 50 MB "
                    f"(tamaño recibido: {len(file_content) / (1024 * 1024):.2f} MB)."
                ),
            },
        )

    # ------------------------------------------------------------------
    # 2. Decodificar — Requisito 3.5
    # ------------------------------------------------------------------
    text_content = _try_decode(file_content)

    # ------------------------------------------------------------------
    # 3. Leer con pandas y validar columnas — Requisito 3.2 / 3.3
    # ------------------------------------------------------------------
    try:
        df = pd.read_csv(io.StringIO(text_content), dtype=str, keep_default_na=False)
    except Exception as exc:
        _set_job(job_id, 0.0, "failed")
        raise HTTPException(
            status_code=400,
            detail={
                "code": 400,
                "message": f"No se pudo leer el archivo CSV: {exc}",
            },
        ) from exc

    # Normalizar nombres de columnas
    df.columns = [c.strip().lower() for c in df.columns]

    _validate_columns(df)

    # Reordenar columnas al orden canónico
    df = df[REQUIRED_COLUMNS]

    # ------------------------------------------------------------------
    # 4. Manejar CSV vacío — Requisito 3.12
    # ------------------------------------------------------------------
    if df.empty:
        _set_job(job_id, 100.0, "completed")
        logger.info("ETL job_id=%s: CSV vacío, devolviendo resumen vacío.", job_id)
        return ETLResult(job_id=job_id, inserted=0, rejected=0, errors=[])

    # ------------------------------------------------------------------
    # 5. Validar tipos y fechas fila a fila — Requisito 3.4
    # ------------------------------------------------------------------
    # Reemplazar cadenas vacías por NaN para detectar nulos
    df.replace("", float("nan"), inplace=True)

    validation_errors = _validate_rows(df)
    if validation_errors:
        _set_job(job_id, 0.0, "failed")
        raise HTTPException(
            status_code=422,
            detail={
                "code": 422,
                "message": (
                    f"El archivo CSV contiene {len(validation_errors)} error(es) de validación."
                ),
                "detail": validation_errors,
            },
        )

    # ------------------------------------------------------------------
    # 6. Insertar en lotes de 1,000 — Requisito 3.6 / 3.8
    # ------------------------------------------------------------------
    total_rows = len(df)
    total_inserted = 0
    total_rejected = 0
    all_errors: list[dict[str, Any]] = []

    num_batches = (total_rows + BATCH_SIZE - 1) // BATCH_SIZE

    for batch_idx in range(num_batches):
        start = batch_idx * BATCH_SIZE
        end = min(start + BATCH_SIZE, total_rows)
        batch = df.iloc[start:end]

        batch_inserted, batch_rejected, batch_errors = _insert_batch(
            conn, batch, batch_idx + 1
        )

        total_inserted += batch_inserted
        total_rejected += batch_rejected
        all_errors.extend(batch_errors)

        # Actualizar progreso
        progress = ((batch_idx + 1) / num_batches) * 100.0
        _set_job(job_id, progress, "running")

    _set_job(job_id, 100.0, "completed")

    logger.info(
        "ETL job_id=%s completado: total=%d, insertados=%d, rechazados=%d.",
        job_id,
        total_rows,
        total_inserted,
        total_rejected,
    )

    if total_inserted > 0:
        notify_db_changed(conn)

    # ------------------------------------------------------------------
    # 7. Devolver ETLResult — Requisito 3.7
    # ------------------------------------------------------------------
    return ETLResult(
        job_id=job_id,
        inserted=total_inserted,
        rejected=total_rejected,
        errors=all_errors,
    )


def importar_parquet_db(conn: Any, parquet_path: str | Path) -> dict[str, Any]:
    """
    Importación masiva desde parquet con INSERT INTO ... SELECT (DuckDB nativo).
    Solo inserta order_id que aún no existen en fact_ventas.
    """
    import time
    from pathlib import Path

    t0 = time.perf_counter()
    path = Path(parquet_path)
    if not path.exists():
        raise FileNotFoundError(f"No se encontró el archivo parquet: {path}")

    before = int(conn.execute("SELECT COUNT(*) FROM fact_ventas").fetchone()[0])
    parquet_sql = path.as_posix().replace("'", "''")
    max_id = int(conn.execute("SELECT COALESCE(MAX(id_venta), 0) FROM fact_ventas").fetchone()[0])

    conn.execute(f"""
        CREATE OR REPLACE TEMP TABLE _stg_parquet AS
        SELECT
            * EXCLUDE (order_date, ship_date),
            strptime(order_date::VARCHAR, '%m/%d/%Y')::DATE AS order_date,
            strptime(ship_date::VARCHAR, '%m/%d/%Y')::DATE AS ship_date
        FROM read_parquet('{parquet_sql}')
    """)

    insert_select = f"""
        SELECT
            {max_id} + row_number() OVER (ORDER BY s.order_id),
            CAST(s.order_id AS BIGINT),
            r.id_region, c.id_country, it.id_item_type, ch.id_channel, p.id_priority,
            s.order_date, s.ship_date,
            CAST(s.units_sold AS INTEGER),
            CAST(s.unit_price AS DECIMAL(10,2)),
            CAST(s.unit_cost AS DECIMAL(10,2)),
            CAST(s.total_revenue AS DECIMAL(12,2)),
            CAST(s.total_cost AS DECIMAL(12,2)),
            CAST(s.total_profit AS DECIMAL(12,2))
        FROM _stg_parquet s
        JOIN dim_region r ON r.region = s.region
        JOIN dim_country c ON c.country = s.country AND c.id_region = r.id_region
        JOIN dim_item_type it ON it.item_type = s.item_type
        JOIN dim_sales_channel ch ON ch.sales_channel = s.sales_channel
        JOIN dim_order_priority p ON p.order_priority = s.order_priority
    """

    if before == 0:
        conn.execute(f"""
            INSERT INTO fact_ventas (
                id_venta, order_id, id_region, id_country, id_item_type, id_channel, id_priority,
                order_date, ship_date, units_sold, unit_price, unit_cost,
                total_revenue, total_cost, total_profit
            )
            {insert_select}
        """)
    else:
        conn.execute(f"""
            INSERT INTO fact_ventas (
                id_venta, order_id, id_region, id_country, id_item_type, id_channel, id_priority,
                order_date, ship_date, units_sold, unit_price, unit_cost,
                total_revenue, total_cost, total_profit
            )
            {insert_select}
            LEFT JOIN fact_ventas f ON f.order_id = CAST(s.order_id AS BIGINT)
            WHERE f.order_id IS NULL
        """)

    after = conn.execute("SELECT COUNT(*) FROM fact_ventas").fetchone()[0]
    inserted = int(after) - int(before)
    elapsed = time.perf_counter() - t0
    rps = round(inserted / elapsed, 3) if elapsed > 0 else 0.0

    logger.info("Parquet importado: %d registros en %.3f s", inserted, elapsed)

    if inserted > 0:
        notify_db_changed(conn)

    return {
        "registros": inserted,
        "inserted": inserted,
        "total_ventas": int(after),
        "tiempo_segundos": round(elapsed, 3),
        "registros_por_segundo": rps,
        "archivo": str(path),
    }


def importar_parquet(conn: Any, parquet_path: str | None = None) -> dict[str, Any]:
    """Wrapper HTTP: resuelve ruta por defecto y devuelve 404 si falta el archivo."""
    from pathlib import Path

    base = Path(__file__).resolve().parent.parent.parent
    path = Path(parquet_path) if parquet_path else base / "data" / "ventas.parquet"
    try:
        return importar_parquet_db(conn, path)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
