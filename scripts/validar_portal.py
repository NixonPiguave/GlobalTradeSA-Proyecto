#!/usr/bin/env python3
"""Smoke test portal B2B + admin (Docker o local). Exit 0 si todo OK."""
from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request

PORTAL = "http://localhost:8001"
ADMIN = "http://localhost:8000"
EMAIL = "dislasandina@gmail.com"
PASSWORD = "12345678"
ADMIN_EMAIL = "admin@globmarket.com"


def _get(url: str, token: str | None = None, timeout: int = 20) -> tuple[int, dict | list | None]:
    req = urllib.request.Request(url)
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8")
            return resp.status, json.loads(body) if body else None
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        try:
            data = json.loads(body)
        except json.JSONDecodeError:
            data = {"raw": body[:300]}
        return e.code, data


def _post_json(url: str, payload: dict, timeout: int = 20) -> tuple[int, dict | None]:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8")
            return resp.status, json.loads(body) if body else None
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        try:
            parsed = json.loads(body)
        except json.JSONDecodeError:
            parsed = {"raw": body[:300]}
        return e.code, parsed


def main() -> int:
    fails: list[str] = []

    def check(name: str, ok: bool, detail: str = "") -> None:
        if ok:
            print(f"  OK  {name}" + (f" — {detail}" if detail else ""))
        else:
            print(f"  FAIL {name}" + (f" — {detail}" if detail else ""))
            fails.append(name)

    print("=== Portal B2B (:8001) ===")
    code, _ = _get(f"{PORTAL}/api/productos/categorias")
    check("categorias (público)", code == 200, f"HTTP {code}")

    code, data = _get(f"{PORTAL}/api/productos?limit=5")
    n = len((data or {}).get("items") or []) if isinstance(data, dict) else 0
    check("productos (público)", code == 200 and n > 0, f"{n} items")

    code, data = _get(f"{PORTAL}/api/catalogos")
    n = len(data) if isinstance(data, list) else 0
    check("catalogos", code == 200 and n > 0, f"{n} paquetes")

    code, data = _post_json(f"{PORTAL}/api/auth/login", {"email": EMAIL, "password": PASSWORD})
    token = (data or {}).get("access_token") if isinstance(data, dict) else None
    check("login cliente", code == 200 and bool(token))

    if token:
        code, data = _get(f"{PORTAL}/api/productos?limit=5", token=token)
        n = len((data or {}).get("items") or []) if isinstance(data, dict) else 0
        check("productos (auth)", code == 200 and n > 0, f"{n} items")

        code, data = _get(f"{PORTAL}/api/productos/categorias", token=token)
        n = len(data) if isinstance(data, list) else 0
        check("categorias (auth)", code == 200 and n > 0, f"{n} cats")

        code, _ = _get(f"{PORTAL}/api/carrito", token=token)
        check("carrito", code == 200)

        code, data = _get(f"{PORTAL}/api/auth/me", token=token)
        check("auth/me", code == 200, (data or {}).get("usuario", {}).get("email", ""))

    print("\n=== Admin ERP (:8000) ===")
    code, data = _post_json(f"{ADMIN}/api/auth/login", {"email": ADMIN_EMAIL, "password": PASSWORD})
    atoken = (data or {}).get("access_token") if isinstance(data, dict) else None
    check("login admin", code == 200 and bool(atoken))

    if atoken:
        code, data = _get(f"{ADMIN}/api/dashboard/kpis", token=atoken)
        rev = (data or {}).get("total_revenue") if isinstance(data, dict) else None
        check("dashboard/kpis", code == 200 and rev is not None, f"revenue={rev}")

        code, _ = _get(f"{ADMIN}/api/dashboard/etl-estado", token=atoken)
        check("dashboard/etl-estado", code == 200)

    print()
    if fails:
        print(f"FALLARON {len(fails)} prueba(s): {', '.join(fails)}")
        return 1
    print("Todas las pruebas pasaron.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
