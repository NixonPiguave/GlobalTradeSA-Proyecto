"""
gmbackend/config.py — Lectura y validación de variables de entorno.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(override=False)


def _env_int(nombre: str, default: int) -> int:
    raw = os.environ.get(nombre, "").strip()
    if not raw:
        return default
    return int(raw)


def _env_list(nombre: str, default: str) -> list[str]:
    raw = os.environ.get(nombre, default).strip()
    if not raw:
        return []
    return [p.strip() for p in raw.split(",") if p.strip()]


@dataclass(frozen=True)
class Settings:
    DUCKDB_PATH: str
    JWT_SECRET: str
    JWT_ALGORITHM: str
    JWT_EXPIRE_MINUTES: int
    CORS_ORIGINS: list[str]

    @property
    def duckdb_absolute_path(self) -> Path:
        ruta = Path(self.DUCKDB_PATH)
        if not ruta.is_absolute():
            base = Path(__file__).resolve().parent.parent  # GlobMarket-B2B/
            ruta = (base / ruta).resolve()
        return ruta

    @classmethod
    def from_env(cls) -> "Settings":
        duckdb_path = os.environ.get("DUCKDB_PATH", "../GlobalTradeSA-duckdb/db/globtrade.duckdb").strip()
        jwt_secret = os.environ.get("JWT_SECRET", "").strip()

        if not jwt_secret:
            raise SystemExit("Arranque interrumpido: falta la variable requerida JWT_SECRET (ver .env.example).")

        return cls(
            DUCKDB_PATH=duckdb_path,
            JWT_SECRET=jwt_secret,
            JWT_ALGORITHM=os.environ.get("JWT_ALGORITHM", "HS256").strip() or "HS256",
            JWT_EXPIRE_MINUTES=_env_int("JWT_EXPIRE_MINUTES", default=60),
            CORS_ORIGINS=_env_list("CORS_ORIGINS", default="http://127.0.0.1:8001,http://localhost:8001"),
        )


def get_settings() -> Settings:
    return Settings.from_env()

