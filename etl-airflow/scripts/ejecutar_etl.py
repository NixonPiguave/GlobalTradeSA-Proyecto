"""scripts/ejecutar_etl.py — Ejecución local del ETL sin Airflow (equivalente al DAG).

Uso:
  python etl-airflow/scripts/ejecutar_etl.py [--estrategia incremental|rebuild]
  python etl-airflow/scripts/ejecutar_etl.py --via-api   # con Docker/apps en marcha

Con la app unificada corriendo, usa --via-api o GLOBALTRADE_ETL_VIA_API=1.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "dags"))

from etl_pkg import carga, extraccion, transformacion  # noqa: E402
from etl_pkg.conexion import conectar, ejecutar_via_api  # noqa: E402


def _via_api() -> bool:
    return os.environ.get("GLOBALTRADE_ETL_VIA_API", "").strip().lower() in {"1", "true", "yes"}


def main() -> int:
    parser = argparse.ArgumentParser(description="Ejecuta el ETL GlobalTrade local.")
    parser.add_argument("--estrategia", default="incremental", choices=["incremental", "rebuild"])
    parser.add_argument(
        "--via-api",
        action="store_true",
        help="Delega al admin (:8000) cuando DuckDB ya está abierto por globaltrade-apps.",
    )
    args = parser.parse_args()

    if args.via_api or _via_api():
        print(json.dumps(ejecutar_via_api(estrategia=args.estrategia), indent=2, ensure_ascii=False))
        return 0

    inicio = time.time()
    conn = conectar()
    try:
        r1 = extraccion.ejecutar(conn, cerrar=False)
        r2 = transformacion.ejecutar(conn, cerrar=False)
        r3 = carga.ejecutar(conn, estrategia=args.estrategia, cerrar=False)
    finally:
        conn.close()

    print(json.dumps(
        {
            "estrategia": args.estrategia,
            "extraccion": r1,
            "transformacion": r2,
            "carga": r3,
            "total_s": round(time.time() - inicio, 3),
        },
        indent=2,
        ensure_ascii=False,
    ))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
