"""
Smoke tests — health checks y descarga PDF sin servidor externo.

Requiere BD inicializada: python shared/database/init_sistema.py
Ejecutar: $env:PYTHONPATH=".;apps/admin;apps/portal"; pytest apps/admin/backend/tests/test_smoke.py -q
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "apps" / "admin"))
sys.path.insert(0, str(ROOT / "apps" / "portal"))

os.environ.setdefault("JWT_SECRET", "smoke-test-secret")
os.environ.setdefault("DUCKDB_PATH", str(ROOT / "db" / "globtrade.duckdb"))

DB = Path(os.environ["DUCKDB_PATH"])


@pytest.fixture(scope="module")
def admin_client():
    if not DB.exists():
        pytest.skip("Ejecute init_sistema.py antes del smoke test.")
    from fastapi.testclient import TestClient
    from backend.main import app
    with TestClient(app) as client:
        yield client


@pytest.fixture(scope="module")
def portal_client():
    if not DB.exists():
        pytest.skip("Ejecute init_sistema.py antes del smoke test.")
    from fastapi.testclient import TestClient
    from gmbackend.main import app
    with TestClient(app) as client:
        yield client


def test_admin_health(admin_client):
    r = admin_client.get("/api/health")
    assert r.status_code == 200
    assert r.json().get("status") == "ok"


def test_branding_publico_sin_auth(admin_client):
    r = admin_client.get("/api/configuracion/branding")
    assert r.status_code == 200, r.text
    data = r.json()
    assert "nombre" in data
    assert data.get("marca_corta") == "GT"


def test_portal_productos(portal_client):
    r = portal_client.get("/api/productos/categorias")
    assert r.status_code == 200


def test_admin_login_y_pdf(admin_client):
    login = admin_client.post("/api/auth/login", json={
        "email": "admin@globmarket.com",
        "password": "12345678",
    })
    assert login.status_code == 200, login.text
    token = login.json().get("access_token")
    assert token

    headers = {"Authorization": f"Bearer {token}"}
    r = admin_client.get("/api/reportes/resumen-financiero?formato=pdf", headers=headers)
    assert r.status_code == 200
    assert "pdf" in (r.headers.get("content-type") or "")
    assert len(r.content) > 500


def test_admin_maestras_regiones(admin_client):
    login = admin_client.post("/api/auth/login", json={
        "email": "admin@globmarket.com",
        "password": "12345678",
    })
    assert login.status_code == 200, login.text
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    r = admin_client.get("/api/maestras/regiones", headers=headers)
    assert r.status_code == 200, r.text
    body = r.json()
    assert "data" in body
    assert body.get("total", 0) >= 1
