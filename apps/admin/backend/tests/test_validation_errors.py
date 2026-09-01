"""Tests unitarios de traducción de errores de validación."""

from __future__ import annotations

import pytest

from shared.api.validation_errors import (
    field_label,
    format_validation_errors,
    translate_pydantic_msg,
    validation_summary,
)


def test_field_label_body_field():
    assert field_label(["body", "nombre_producto"]) == "Nombre del producto"


def test_field_label_array_index():
    assert field_label(["body", "items", 0, "cantidad"]) == "Cantidad"


def test_translate_required_spanish():
    assert translate_pydantic_msg("Field required") == "Este campo es obligatorio."


def test_translate_value_error_spanish_passthrough():
    msg = "La cantidad del ajuste debe ser distinta de cero."
    assert translate_pydantic_msg(f"Value error, {msg}", "value_error") == msg


def test_format_validation_errors_includes_msg_es():
    detail = format_validation_errors(
        [
            {
                "loc": ("body", "cantidad"),
                "msg": "Input should be greater than 0",
                "type": "greater_than",
            }
        ]
    )
    assert len(detail) == 1
    assert detail[0]["label"] == "Cantidad"
    assert "Cantidad:" in detail[0]["msg_es"]
    assert "mayor" in detail[0]["msg_es"].lower()


def test_validation_summary_joins_messages():
    detail = format_validation_errors(
        [
            {"loc": ("body", "email"), "msg": "Field required", "type": "missing"},
            {"loc": ("body", "password"), "msg": "Field required", "type": "missing"},
        ]
    )
    summary = validation_summary(detail)
    assert "Correo electrónico" in summary
    assert "Contraseña" in summary


def test_ajuste_stock_cantidad_cero_rechazada():
    from pydantic import ValidationError

    from backend.models.inventario import AjusteStock

    with pytest.raises(ValidationError) as exc:
        AjusteStock(id_producto=1, cantidad=0, motivo="test ajuste")
    detail = format_validation_errors(exc.value.errors())
    assert any("distinta de cero" in (e.get("msg_es") or "") for e in detail)


def test_translate_email_spanish():
    msg = "value is not a valid email address: An email address must have an @-sign."
    assert translate_pydantic_msg(msg, "value_error") == "Correo electrónico inválido."


def test_translate_min_length_no_typo():
    msg = "String should have at least 2 characters"
    assert translate_pydantic_msg(msg) == "Mínimo 2 caracteres."


def test_admin_422_ajuste_stock(admin_client):
    login = admin_client.post("/api/auth/login", json={
        "email": "admin@globmarket.com",
        "password": "12345678",
    })
    if login.status_code != 200:
        pytest.skip(f"Login admin no disponible: {login.text}")
    token = login.json()["access_token"]
    r = admin_client.post(
        "/api/inventario/ajustes",
        headers={"Authorization": f"Bearer {token}"},
        json={"id_producto": 1, "cantidad": 0, "motivo": "prueba"},
    )
    assert r.status_code == 422, r.text
    data = r.json()
    assert data.get("detail") and data["detail"][0].get("msg_es")
    assert "cero" in data["message"].lower() or "cero" in str(data["detail"]).lower()


@pytest.fixture(scope="module")
def admin_client():
    import os
    from pathlib import Path
    from fastapi.testclient import TestClient

    root = Path(__file__).resolve().parents[4]
    os.environ.setdefault("JWT_SECRET", "test-validation")
    os.environ.setdefault("DUCKDB_PATH", str(root / "db" / "globtrade.duckdb"))
    db = Path(os.environ["DUCKDB_PATH"])
    if not db.exists():
        pytest.skip("BD no disponible")
    from backend.main import app

    with TestClient(app) as client:
        yield client


@pytest.fixture(scope="module")
def portal_client():
    import os
    from pathlib import Path
    from fastapi.testclient import TestClient

    root = Path(__file__).resolve().parents[4]
    os.environ.setdefault("JWT_SECRET", "test-validation")
    os.environ.setdefault("DUCKDB_PATH", str(root / "db" / "globtrade.duckdb"))
    from gmbackend.main import app

    with TestClient(app) as client:
        yield client


def test_portal_422_registro_email(portal_client):
    r = portal_client.post("/api/auth/registro", json={
        "nombre_empresa": "Empresa Demo",
        "email": "correo-invalido",
        "password": "12345678",
        "pais": "Peru",
    })
    assert r.status_code == 422, r.text
    data = r.json()
    assert "Correo electrónico inválido" in data.get("message", "")
    assert data["detail"][0].get("msg_es", "").startswith("Correo electrónico")
