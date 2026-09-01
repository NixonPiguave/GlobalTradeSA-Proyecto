"""conexion.py — Resolución de rutas y conexión DuckDB del proceso ETL.

En Airflow las rutas llegan por variables de entorno (DUCKDB_PATH y DATA_DIR).
En desarrollo local se resuelven automáticamente desde la raíz del repositorio.
"""
from __future__ import annotations

import os
from pathlib import Path


def _raiz_proyecto() -> Path:
    """Sube desde etl-airflow/dags/etl_pkg hasta la raíz del repositorio."""
    p = Path(__file__).resolve()
    return p.parents[3]


def duckdb_path() -> str:
    env = os.environ.get("DUCKDB_PATH", "").strip()
    if env:
        return env
    return str(_raiz_proyecto() / "db" / "globtrade.duckdb")


def data_dir() -> Path:
    env = os.environ.get("DATA_DIR", "").strip()
    return Path(env) if env else (_raiz_proyecto() / "data")


def conectar(*, reintentos: int = 3, espera_s: float = 2.0):
    """Abre DuckDB exclusivo. Falla con mensaje claro si la app ya tiene el archivo."""
    import time

    import duckdb

    ruta = duckdb_path()
    os.makedirs(os.path.dirname(ruta), exist_ok=True)
    ultimo: Exception | None = None
    for intento in range(max(1, reintentos)):
        try:
            return duckdb.connect(ruta)
        except duckdb.IOException as exc:
            ultimo = exc
            if "Conflicting lock" not in str(exc):
                raise
            if intento + 1 >= reintentos:
                break
            time.sleep(espera_s)
    raise RuntimeError(
        "DuckDB está en uso por globaltrade-apps (portal/admin). "
        "No abras otra conexión en paralelo: usa POST /api/etl/pipeline "
        "o ejecuta con GLOBALTRADE_ETL_VIA_API=1 / --via-api."
    ) from ultimo


def ejecutar_via_api(*, estrategia: str = "incremental", base_url: str | None = None) -> dict:
    """Delega el ETL al proceso unificado (misma conexión serializada)."""
    import json
    import os
    import urllib.error
    import urllib.request

    url_base = (base_url or os.environ.get("GLOBALTRADE_API_URL", "http://localhost:8000")).rstrip("/")
    token = os.environ.get("ETL_INTERNAL_TOKEN", "").strip()
    if not token:
        raise RuntimeError("Falta ETL_INTERNAL_TOKEN para ejecutar el ETL vía API.")

    payload = json.dumps({"estrategia": estrategia}).encode("utf-8")
    req = urllib.request.Request(
        f"{url_base}/api/etl/pipeline/internal",
        data=payload,
        headers={
            "Content-Type": "application/json",
            "X-ETL-Internal-Token": token,
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=3600) as resp:
            body = resp.read().decode("utf-8")
            return json.loads(body) if body else {}
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:500]
        raise RuntimeError(f"ETL vía API falló (HTTP {exc.code}): {detail}") from exc


def sync_clickhouse_via_api(*, base_url: str | None = None) -> dict:
    """Delega la publicación DuckDB→ClickHouse al proceso unificado."""
    import json
    import os
    import urllib.error
    import urllib.request

    url_base = (base_url or os.environ.get("GLOBALTRADE_API_URL", "http://localhost:8000")).rstrip("/")
    token = os.environ.get("ETL_INTERNAL_TOKEN", "").strip()
    if not token:
        raise RuntimeError("Falta ETL_INTERNAL_TOKEN para publicar ClickHouse vía API.")

    req = urllib.request.Request(
        f"{url_base}/api/dashboard/sync-clickhouse/internal",
        data=b"{}",
        headers={
            "Content-Type": "application/json",
            "X-ETL-Internal-Token": token,
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=3600) as resp:
            body = resp.read().decode("utf-8")
            return json.loads(body) if body else {}
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:500]
        raise RuntimeError(f"ClickHouse vía API falló (HTTP {exc.code}): {detail}") from exc