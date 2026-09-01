"""
Sincronización PocketBase → data/ventas.parquet → DuckDB (fact_ventas).
"""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any, Optional

import requests

from backend.services.etl_service import importar_parquet_db

logger = logging.getLogger(__name__)

DEFAULT_COLLECTION = "ventas"
PER_PAGE = 500


def extract_pocketbase_to_parquet(
    parquet_path: Path,
    *,
    base_url: str,
    email: str,
    password: str,
    collection: str = DEFAULT_COLLECTION,
    timeout: float = 60.0,
) -> dict[str, Any]:
    """
    Extrae todos los registros de una colección PocketBase y guarda Parquet.
    """
    parquet_path.parent.mkdir(parents=True, exist_ok=True)
    base = base_url.rstrip("/")
    session = requests.Session()

    auth_resp = session.post(
        f"{base}/api/collections/_superusers/auth-with-password",
        json={"identity": email, "password": password},
        timeout=timeout,
    )
    auth_resp.raise_for_status()
    token = auth_resp.json().get("token")
    if not token:
        raise ValueError("PocketBase no devolvió token de autenticación.")
    session.headers.update({"Authorization": f"Bearer {token}"})

    todos: list[dict] = []
    pagina = 1
    while True:
        resp = session.get(
            f"{base}/api/collections/{collection}/records",
            params={"page": pagina, "perPage": PER_PAGE},
            timeout=timeout,
        )
        resp.raise_for_status()
        data = resp.json()
        items = data.get("items", [])
        todos.extend(items)
        total_pages = data.get("totalPages", pagina)
        logger.info("PocketBase página %d/%s — acumulados: %d", pagina, total_pages, len(todos))
        if pagina >= total_pages:
            break
        pagina += 1

    import pandas as pd

    df = pd.DataFrame(todos)
    drop_cols = ["id", "created", "updated", "collectionId", "collectionName"]
    df = df.drop(columns=[c for c in drop_cols if c in df.columns], errors="ignore")
    df.to_parquet(parquet_path, index=False)

    return {
        "registros_extraidos": len(df),
        "archivo": str(parquet_path.resolve()),
        "coleccion": collection,
    }


def _fact_ventas_exists(conn: Any) -> bool:
    row = conn.execute(
        """
        SELECT COUNT(*) FROM information_schema.tables
        WHERE table_schema = 'main' AND table_name = 'fact_ventas'
        """
    ).fetchone()
    return bool(row and row[0] > 0)


def sync_pocketbase_to_duckdb(
    conn: Any,
    parquet_path: Path,
    *,
    base_url: str,
    email: str,
    password: str,
    collection: str = DEFAULT_COLLECTION,
) -> dict[str, Any]:
    """
    PocketBase → Parquet → inserción incremental en fact_ventas (solo order_id nuevos).
    """
    t0 = time.perf_counter()
    extract_meta = extract_pocketbase_to_parquet(
        parquet_path,
        base_url=base_url,
        email=email,
        password=password,
        collection=collection,
    )

    if not _fact_ventas_exists(conn):
        elapsed = time.perf_counter() - t0
        logger.warning(
            "Parquet actualizado pero fact_ventas no existe. Ejecute scripts/cargar_duckdb.py primero."
        )
        return {
            "ok": False,
            "motivo": "fact_ventas_no_existe",
            "parquet": extract_meta,
            "insertados": 0,
            "tiempo_segundos": round(elapsed, 3),
        }

    import_meta = importar_parquet_db(conn, parquet_path)
    elapsed = time.perf_counter() - t0
    return {
        "ok": True,
        "parquet": extract_meta,
        "duckdb": import_meta,
        "insertados": import_meta.get("inserted", 0),
        "tiempo_segundos": round(elapsed, 3),
    }


def try_startup_sync(
    conn: Any,
    parquet_path: Path,
    *,
    enabled: bool,
    base_url: Optional[str],
    email: Optional[str],
    password: Optional[str],
) -> Optional[dict[str, Any]]:
    """Ejecuta sync si está habilitado; nunca lanza excepción al arranque."""
    if not enabled:
        logger.info("Sincronización PocketBase al arranque: desactivada (POCKETBASE_SYNC_ON_STARTUP).")
        return None

    if not all((base_url, email, password)):
        logger.info(
            "Sincronización PocketBase al arranque: omitida (faltan POCKETBASE_URL, EMAIL o PASSWORD)."
        )
        return None

    try:
        logger.info("Sincronización PocketBase → DuckDB al arranque...")
        result = sync_pocketbase_to_duckdb(
            conn,
            parquet_path,
            base_url=base_url.strip(),
            email=email.strip(),
            password=password,
        )
        logger.info(
            "Sync al arranque completado: extraídos=%s, insertados=%s, %.3fs",
            result.get("parquet", {}).get("registros_extraidos"),
            result.get("insertados"),
            result.get("tiempo_segundos"),
        )
        return result
    except requests.RequestException as exc:
        logger.warning(
            "Sync PocketBase falló (¿servidor apagado?): %s — la API sigue con datos locales.",
            exc,
        )
        return {"ok": False, "motivo": "pocketbase_no_disponible", "detalle": str(exc)}
    except Exception as exc:
        logger.warning("Sync PocketBase falló: %s — la API sigue con datos locales.", exc)
        return {"ok": False, "motivo": "error_sync", "detalle": str(exc)}
