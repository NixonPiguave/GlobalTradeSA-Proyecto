"""
backend/config.py — Lectura y validación de variables de entorno.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

from backend.logger import get_logger

load_dotenv(override=False)

logger = get_logger(__name__)

_REQUIRED_ENV_VARS = ("DUCKDB_PATH",)


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name, "").strip().lower()
    if not raw:
        return default
    return raw in ("1", "true", "yes", "on")


@dataclass(frozen=True)
class Settings:
    """Parámetros de la aplicación."""

    DUCKDB_PATH: str
    POCKETBASE_URL: str
    POCKETBASE_EMAIL: str
    POCKETBASE_PASSWORD: str
    POCKETBASE_SYNC_ON_STARTUP: bool
    PARQUET_PATH: str

    @property
    def duckdb_absolute_path(self) -> Path:
        path = Path(self.DUCKDB_PATH)
        if not path.is_absolute():
            base = Path(__file__).resolve().parent.parent
            path = base / path
        return path

    @property
    def parquet_absolute_path(self) -> Path:
        path = Path(self.PARQUET_PATH)
        if not path.is_absolute():
            base = Path(__file__).resolve().parent.parent
            path = base / path
        return path

    @classmethod
    def from_env(cls) -> "Settings":
        missing: list[str] = []

        for var in _REQUIRED_ENV_VARS:
            value = os.environ.get(var, "")
            if not value.strip():
                logger.error("Variable de entorno requerida ausente o vacía: %s", var)
                missing.append(var)

        if missing:
            raise SystemExit(
                "Arranque interrumpido: faltan las siguientes variables de "
                f"entorno requeridas: {', '.join(missing)}"
            )

        base = Path(__file__).resolve().parent.parent
        default_parquet = str(base / "data" / "ventas.parquet")

        return cls(
            DUCKDB_PATH=os.environ["DUCKDB_PATH"].strip(),
            POCKETBASE_URL=os.environ.get("POCKETBASE_URL", "http://127.0.0.1:8090").strip(),
            POCKETBASE_EMAIL=os.environ.get("POCKETBASE_EMAIL", "").strip(),
            POCKETBASE_PASSWORD=os.environ.get("POCKETBASE_PASSWORD", ""),
            POCKETBASE_SYNC_ON_STARTUP=_env_bool("POCKETBASE_SYNC_ON_STARTUP", default=False),
            PARQUET_PATH=os.environ.get("PARQUET_PATH", default_parquet).strip(),
        )


def get_settings() -> Settings:
    return Settings.from_env()
