"""
Cliente ClickHouse HTTP con fallback silencioso si no está disponible.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from typing import Any


def _cfg() -> dict[str, str]:
    return {
        "host": os.environ.get("CLICKHOUSE_HOST", "127.0.0.1"),
        "port": os.environ.get("CLICKHOUSE_PORT", "8123"),
        "user": os.environ.get("CLICKHOUSE_USER", "default"),
        "password": os.environ.get("CLICKHOUSE_PASSWORD", ""),
        "db": os.environ.get("CLICKHOUSE_DB", "globtrade_dwh"),
    }


def clickhouse_disponible() -> bool:
    cfg = _cfg()
    url = f"http://{cfg['host']}:{cfg['port']}/ping"
    try:
        with urllib.request.urlopen(url, timeout=2) as resp:
            return resp.status == 200
    except Exception:
        return False


def ejecutar_query(sql: str, *, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    cfg = _cfg()
    q = sql.strip()
    if params:
        for k, v in params.items():
            rep = "NULL" if v is None else json.dumps(v) if isinstance(v, (dict, list)) else str(v)
            q = q.replace(f"{{{k}}}", rep)
    url = (
        f"http://{cfg['host']}:{cfg['port']}/?"
        + urllib.parse.urlencode({"database": cfg["db"], "default_format": "JSONEachRow"})
    )
    req = urllib.request.Request(
        url,
        data=q.encode("utf-8"),
        method="POST",
        headers={"Content-Type": "text/plain; charset=utf-8"},
    )
    if cfg["user"]:
        import base64

        cred = base64.b64encode(f"{cfg['user']}:{cfg['password']}".encode()).decode()
        req.add_header("Authorization", f"Basic {cred}")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = resp.read().decode("utf-8").strip()
            if not body:
                return []
            return [json.loads(line) for line in body.splitlines() if line.strip()]
    except urllib.error.HTTPError as e:
        err = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"ClickHouse error: {err}") from e


def estado_almacen() -> dict[str, Any]:
    if not clickhouse_disponible():
        return {"disponible": False, "tablas": [], "total_filas": 0}
    tablas = [
        "dwh_ventas", "dwh_compras", "dwh_clientes", "dwh_proveedores", "dwh_geografia",
        "dwh_inventario", "dwh_stock_bajo", "dwh_pedidos_estado", "dwh_pedidos_pendientes",
        "dwh_movimientos", "dwh_recepciones", "dwh_finanzas", "dwh_tesoreria",
        "dwh_cuentas_por_pagar",
    ]
    out = []
    total = 0
    for t in tablas:
        try:
            rows = ejecutar_query(f"SELECT count() AS n FROM {t}")
            n = int(rows[0]["n"]) if rows else 0
            total += n
            meta = ejecutar_query(
                f"SELECT max(synced_at) AS synced_at FROM etl_sync_meta WHERE tabla = '{t}'"
            )
            synced = meta[0].get("synced_at") if meta else None
            out.append({"tabla": t, "filas": n, "synced_at": synced})
        except Exception:
            out.append({"tabla": t, "filas": 0, "synced_at": None})
    return {"disponible": True, "tablas": out, "total_filas": total, "motor": "ClickHouse"}
