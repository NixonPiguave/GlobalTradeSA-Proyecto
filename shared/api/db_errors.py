"""
Traducción de errores DuckDB a mensajes HTTP legibles en español.
"""

from __future__ import annotations

from typing import Any

try:
    import duckdb
except ImportError:  # pragma: no cover
    duckdb = None  # type: ignore[assignment]


_CORRUPTION_MARKERS = (
    "metadata pointer",
    "internal error",
    "invalidated",
    "corrupt",
    "fatal error",
    "database has been invalidated",
)


def _es_catalogo_faltante(msg: str) -> bool:
    return "does not exist" in msg or "no existe" in msg


def es_error_bd(exc: BaseException) -> bool:
    """True si la excepción proviene de DuckDB o indica corrupción de archivo."""
    if duckdb is not None and isinstance(exc, duckdb.Error):
        return True
    msg = str(exc).lower()
    return any(marker in msg for marker in _CORRUPTION_MARKERS)


def mensaje_error_bd(exc: BaseException) -> str:
    """Mensaje en español para el cliente según el tipo de fallo de base de datos."""
    msg = str(exc).lower()
    if "permission denied" in msg:
        return (
            "Sin permiso para escribir la base de datos. "
            "Usa Docker (docker-compose.full.yml) o cierra procesos que tengan abierto globtrade.duckdb."
        )
    if "already open" in msg or "file is already open" in msg:
        return (
            "La base de datos está en uso por otro proceso. "
            "Reinicia el servidor (python run.py) y evita abrir globtrade.duckdb en otra app."
        )
    if _es_catalogo_faltante(msg):
        return "Falta una tabla o columna requerida. Ejecuta las migraciones del sistema."
    if any(m in msg for m in _CORRUPTION_MARKERS):
        return (
            "La base de datos no está disponible o está dañada. "
            "Reinicia el servidor o restaura desde un respaldo."
        )
    if "constraint" in msg or "unique" in msg:
        return "Conflicto de datos: la operación viola una restricción de la base de datos."
    if "transaction" in msg:
        return "No se pudo completar la transacción. Intenta de nuevo."
    return "Error al acceder a la base de datos. Intenta de nuevo en unos segundos."


def codigo_http_bd(exc: BaseException) -> int:
    """503 para indisponibilidad; 409 para conflictos de integridad."""
    msg = str(exc).lower()
    if "already open" in msg or "file is already open" in msg:
        return 503
    if any(m in msg for m in _CORRUPTION_MARKERS):
        return 503
    if "constraint" in msg or "unique" in msg:
        return 409
    return 503


def detalle_respuesta_bd(exc: BaseException) -> dict[str, Any]:
    return {
        "message": mensaje_error_bd(exc),
        "tipo": type(exc).__name__,
    }
