"""Verificación rápida de correcciones recientes (ejecutar desde raíz del repo)."""
from __future__ import annotations

import os
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

os.environ.setdefault("DUCKDB_PATH", str(ROOT / "db" / "globtrade.duckdb"))

import duckdb
from fastapi.testclient import TestClient

from shared.services.logistica_envio import estimar_envio_por_pais


def check_db_logistica() -> None:
    db = Path(os.environ["DUCKDB_PATH"])
    if not db.exists():
        print("SKIP DB: no existe", db)
        return
    conn = duckdb.connect(str(db), read_only=True)
    for table in ("zonas_envio", "transportistas"):
        cols = [
            r[0]
            for r in conn.execute(
                "SELECT column_name FROM information_schema.columns WHERE table_name = ?",
                [table],
            ).fetchall()
        ]
        n = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        print(f"  {table}: {n} filas, columnas={cols}")
    info = estimar_envio_por_pais(conn, pais="Peru")
    print(
        "  estimar_envio Peru:",
        info.get("macro_zona"),
        f"transportistas={len(info.get('transportistas', []))}",
        f"zonas={len(info.get('zonas', []))}",
    )
    conn.close()


def check_testclient() -> None:
    sys.path.insert(0, str(ROOT / "apps" / "admin"))
    sys.path.insert(0, str(ROOT / "apps" / "portal"))
    from backend.database import init_db
    from backend.main import app

    init_db(os.environ["DUCKDB_PATH"])
    client = TestClient(app)
    r = client.get("/api/configuracion/branding")
    assert r.status_code == 200, r.text
    print("  branding TestClient:", r.json())


def check_live() -> None:
    for label, url in (
        ("admin health", "http://localhost:8000/api/health"),
        ("portal categorias", "http://localhost:8001/api/productos/categorias"),
        ("portal branding", "http://localhost:8001/api/marketing/branding"),
        ("admin branding", "http://localhost:8000/api/configuracion/branding"),
    ):
        try:
            with urllib.request.urlopen(url, timeout=3) as resp:
                body = resp.read().decode()[:100]
                print(f"  {label}: {resp.status} {body}")
        except Exception as exc:
            code = getattr(exc, "code", None)
            print(f"  {label}: ERROR {code or exc}")


if __name__ == "__main__":
    print("=== DuckDB logística ===")
    check_db_logistica()
    print("=== TestClient admin ===")
    check_testclient()
    print("=== Servicios en ejecución ===")
    check_live()
