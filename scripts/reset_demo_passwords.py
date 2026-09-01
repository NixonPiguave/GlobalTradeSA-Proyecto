"""Restablece la contraseña de TODOS los usuarios (ERP + clientes B2B) a la demo unificada."""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import duckdb

from shared.database.connection import resolve_duckdb_path
from shared.database.init_sistema import DEMO_PASSWORD, _hash_password

DEFAULT_PASSWORD = DEMO_PASSWORD  # 12345678


def reset_passwords(conn: duckdb.DuckDBPyConnection, password: str = DEFAULT_PASSWORD) -> list[tuple]:
    hashed = _hash_password(password)
    rows = conn.execute(
        """
        UPDATE usuarios
        SET password_hash = ?
        RETURNING email, COALESCE(rol, '—') AS rol
        """,
        [hashed],
    ).fetchall()
    try:
        conn.execute("CHECKPOINT")
    except duckdb.Error:
        pass
    return [(str(r[0]), str(r[1])) for r in rows]


def main() -> int:
    db_path = resolve_duckdb_path(os.environ.get("DUCKDB_PATH"))
    print(f"Base de datos: {db_path}")
    conn = duckdb.connect(str(db_path))
    try:
        if not conn.execute(
            "SELECT 1 FROM information_schema.tables WHERE table_name = 'usuarios'"
        ).fetchone():
            print("ERROR: no existe la tabla usuarios.")
            return 1
        rows = reset_passwords(conn)
        if not rows:
            print("AVISO: no hay filas en usuarios.")
            return 0
        print(f"OK: {len(rows)} cuenta(s) con contraseña «{DEFAULT_PASSWORD}»")
        for email, rol in sorted(rows, key=lambda x: (x[1], x[0])):
            print(f"  · [{rol}] {email}")
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
