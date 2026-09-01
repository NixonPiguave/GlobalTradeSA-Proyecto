#!/usr/bin/env python3
"""Crea 2 líneas por cada marca activa (Premium + Estándar). Idempotente."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from shared.database.connection import connect
from shared.database.migrate_reestructuracion import _seed_lineas_por_marca


def main() -> int:
    conn = connect()
    try:
        antes = conn.execute(
            """
            SELECT m.id_marca, m.nombre, COUNT(l.id_linea) AS n
            FROM marcas m
            LEFT JOIN lineas_producto l
              ON l.id_marca = m.id_marca AND COALESCE(l.activo, true) = true
            WHERE COALESCE(m.activo, true) = true
            GROUP BY m.id_marca, m.nombre
            ORDER BY m.nombre
            """
        ).fetchall()
        print("Marcas antes:")
        for _id, nombre, n in antes:
            print(f"  · {nombre}: {int(n or 0)} línea(s)")

        _seed_lineas_por_marca(conn)

        despues = conn.execute(
            """
            SELECT m.nombre, l.nombre
            FROM marcas m
            JOIN lineas_producto l ON l.id_marca = m.id_marca AND COALESCE(l.activo, true)
            WHERE COALESCE(m.activo, true) = true
            ORDER BY m.nombre, l.nombre
            """
        ).fetchall()
        print("\nLíneas por marca:")
        marca_actual = None
        for marca, linea in despues:
            if marca != marca_actual:
                print(f"\n  {marca}:")
                marca_actual = marca
            print(f"    - {linea}")

        resumen = conn.execute(
            """
            SELECT m.nombre, COUNT(l.id_linea) AS n
            FROM marcas m
            LEFT JOIN lineas_producto l
              ON l.id_marca = m.id_marca AND COALESCE(l.activo, true) = true
            WHERE COALESCE(m.activo, true) = true
            GROUP BY m.id_marca, m.nombre
            HAVING COUNT(l.id_linea) < 2
            """
        ).fetchall()
        if resumen:
            print("\nAVISO: Marcas con menos de 2 lineas:", [r[0] for r in resumen])
            return 1
        print("\nOK: Todas las marcas activas tienen al menos 2 lineas.")
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
