"""
promocion_service.py — Promociones activas y cálculo de descuentos en ventas B2B.
"""

from __future__ import annotations

from typing import Any, Optional

import duckdb

from shared.database.connection import table_exists
from shared.services.config_service import obtener_config_float


def mejor_promocion_activa(conn: duckdb.DuckDBPyConnection) -> Optional[dict[str, Any]]:
    """Devuelve la promoción activa con mayor % de descuento vigente hoy."""
    if not table_exists(conn, "promociones"):
        return None
    row = conn.execute(
        """
        SELECT id_promocion, nombre, CAST(descuento_pct AS DOUBLE)
        FROM promociones
        WHERE activa = true
          AND (fecha_inicio IS NULL OR fecha_inicio <= current_date)
          AND (fecha_fin IS NULL OR fecha_fin >= current_date)
        ORDER BY descuento_pct DESC, id_promocion
        LIMIT 1
        """
    ).fetchone()
    if not row:
        return None
    return {
        "id_promocion": int(row[0]),
        "nombre": row[1],
        "descuento_pct": float(row[2]),
    }


def calcular_totales_venta(
    conn: duckdb.DuckDBPyConnection,
    *,
    subtotal_items: float,
    aplicar_promocion: bool = True,
) -> dict[str, Any]:
    """
    Calcula subtotal, descuento promocional, base imponible, IVA y total.
    El descuento se aplica sobre el subtotal de ítems antes del IVA.
    """
    subtotal = round(float(subtotal_items), 2)
    promo = mejor_promocion_activa(conn) if aplicar_promocion else None
    descuento_pct = float(promo["descuento_pct"]) if promo else 0.0
    descuento_monto = round(subtotal * descuento_pct / 100.0, 2) if promo else 0.0
    base_imponible = round(subtotal - descuento_monto, 2)
    iva_pct = obtener_config_float(conn, "IVA_PCT", 18.0)
    impuesto = round(base_imponible * iva_pct / 100.0, 2)
    total = round(base_imponible + impuesto, 2)
    return {
        "subtotal": subtotal,
        "promocion": promo,
        "id_promocion": int(promo["id_promocion"]) if promo else None,
        "promocion_nombre": promo["nombre"] if promo else None,
        "descuento_pct": descuento_pct,
        "descuento_monto": descuento_monto,
        "base_imponible": base_imponible,
        "iva_pct": iva_pct,
        "impuesto": impuesto,
        "total": total,
        "total_con_iva": total,
    }
