"""
eliminar_usuario.py — Elimina un usuario B2B (y su cliente asociado) por email.

Uso:
    DUCKDB_PATH=/app/db/globtrade.duckdb python eliminar_usuario.py <email>

Borra de forma consistente:
  1) dim_cliente (filas con el id_usuario del email)
  2) usuarios (la fila del email)

Importante: ejecutar con la aplicacion detenida (DuckDB es de un solo escritor).
"""

from __future__ import annotations

import os
import sys

import duckdb


def main() -> int:
    if len(sys.argv) < 2 or not sys.argv[1].strip():
        print("Uso: python eliminar_usuario.py <email>")
        return 2

    email = sys.argv[1].strip().lower()
    db_path = os.environ.get("DUCKDB_PATH", "/app/db/globtrade.duckdb")

    con = duckdb.connect(db_path)
    try:
        row = con.execute(
            "SELECT id_usuario FROM usuarios WHERE lower(email) = ?", [email]
        ).fetchone()

        if not row:
            print(f"No existe ningun usuario con email '{email}'. Nada que borrar.")
            total = con.execute("SELECT COUNT(*) FROM usuarios").fetchone()[0]
            print(f"Usuarios actuales: {total}")
            return 0

        id_usuario = int(row[0])
        clientes = con.execute(
            "SELECT COUNT(*) FROM dim_cliente WHERE id_usuario = ?", [id_usuario]
        ).fetchone()[0]

        con.execute("DELETE FROM dim_cliente WHERE id_usuario = ?", [id_usuario])
        con.execute("DELETE FROM usuarios WHERE id_usuario = ?", [id_usuario])

        total = con.execute("SELECT COUNT(*) FROM usuarios").fetchone()[0]
        print(f"Usuario '{email}' (id_usuario={id_usuario}) eliminado.")
        print(f"Filas dim_cliente asociadas eliminadas: {clientes}")
        print(f"Usuarios restantes: {total}")
        return 0
    finally:
        con.close()


if __name__ == "__main__":
    raise SystemExit(main())
