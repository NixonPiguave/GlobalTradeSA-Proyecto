#!/usr/bin/env python3
"""
Extrae ventas desde PocketBase y guarda data/ventas.parquet.
Usa las mismas variables de entorno que la API (ver .env.example).
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

from backend.config import get_settings
from backend.services.pocketbase_sync_service import extract_pocketbase_to_parquet


def main() -> None:
    settings = get_settings()
    if not settings.POCKETBASE_EMAIL or not settings.POCKETBASE_PASSWORD:
        print("Error: configure POCKETBASE_EMAIL y POCKETBASE_PASSWORD en .env")
        sys.exit(1)

    path = settings.parquet_absolute_path
    print(f"Extrayendo PocketBase → {path}")
    meta = extract_pocketbase_to_parquet(
        path,
        base_url=settings.POCKETBASE_URL,
        email=settings.POCKETBASE_EMAIL,
        password=settings.POCKETBASE_PASSWORD,
    )
    print(f"Listo: {meta['registros_extraidos']} registros → {meta['archivo']}")


if __name__ == "__main__":
    main()
