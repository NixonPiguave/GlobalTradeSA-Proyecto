"""Integración HTTP checkout (requiere portal en :8001). Ejecutar dentro de globaltrade-apps."""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
import uuid

import pytest

BASE = os.environ.get("PORTAL_E2E_BASE", "http://127.0.0.1:8001")


def _req(method: str, path: str, *, token: str | None = None, body: dict | None = None) -> dict:
    data = json.dumps(body).encode() if body is not None else None
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    r = urllib.request.Request(f"{BASE}{path}", data=data, headers=headers, method=method)
    with urllib.request.urlopen(r, timeout=60) as resp:
        raw = resp.read().decode()
        return json.loads(raw) if raw else {}


@pytest.mark.integration
def test_checkout_y_pago_http():
    email = f"checkout_pytest_{uuid.uuid4().hex[:8]}@example.com"
    password = "Test1234!"
    _req(
        "POST",
        "/api/auth/registro",
        body={
            "email": email,
            "password": password,
            "nombre_empresa": "Checkout Pytest S.A.",
            "pais": "Ecuador",
            "telefono": "+593991234567",
        },
    )
    login = _req("POST", "/api/auth/login", body={"email": email, "password": password})
    token = login["access_token"]

    prods = _req("GET", "/api/productos?limite=3")
    items = prods.get("items") or []
    assert items, "Catálogo vacío"
    pid = items[0]["id_producto"]

    _req("POST", "/api/carrito/items", token=token, body={"id_producto": pid, "cantidad": 1})

    pedido = _req(
        "POST",
        "/api/pedidos/checkout",
        token=token,
        body={
            "direccion_entrega": "Av. Test 123",
            "ciudad": "Quito",
            "pais": "Ecuador",
            "notas": "Pytest E2E",
        },
    )
    assert pedido["estado"] == "pendiente_pago"
    assert pedido.get("numero")
    assert pedido["items"], "Pedido sin líneas"

    pago = _req(
        "POST",
        "/api/pedidos/pagar",
        token=token,
        body={"id_pedido": pedido["id_pedido"], "metodo": "simulado", "referencia": "PYTEST"},
    )
    assert pago.get("estado") in ("pagado", "preparando", None) or pago.get("pedido", {}).get("estado") == "pagado"
