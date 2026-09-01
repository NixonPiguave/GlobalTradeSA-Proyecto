#!/usr/bin/env python3
"""Sincroniza catálogo de permisos, rol gerente y usuario demo en DuckDB."""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import duckdb

from shared.database.init_sistema import _hash_password
from shared.database.permisos_catalogo import (
    ROLES_PERMISOS_DEFAULT,
    sincronizar_gobierno_demo,
    sincronizar_roles_permisos_default,
)


def main() -> None:
    db_path = Path(os.environ.get("DUCKDB_PATH", ROOT / "db" / "globtrade.duckdb"))
    conn = duckdb.connect(str(db_path))
    try:
        res = sincronizar_gobierno_demo(conn, password_hash_fn=_hash_password)
        # Reaplica defaults de vendedor/almacen sin borrar roles custom (solo inserta faltantes)
        for rol in ("vendedor", "almacen"):
            for codigo in ROLES_PERMISOS_DEFAULT.get(rol, []):
                conn.execute(
                    """
                    INSERT INTO rol_permiso (id_rol, id_permiso)
                    SELECT r.id_rol, p.id_permiso
                    FROM roles r, permisos p
                    WHERE r.nombre = ? AND p.codigo = ?
                      AND NOT EXISTS (
                        SELECT 1 FROM rol_permiso rp
                        WHERE rp.id_rol = r.id_rol AND rp.id_permiso = p.id_permiso
                      )
                    """,
                    [rol, codigo],
                )
        print(f"[sync_permisos] catálogo={res['permisos_catalogo']} gerente_perms={res['gerente_permisos']}")
        print(f"[sync_permisos] usuario: {res['email']} / 12345678")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
