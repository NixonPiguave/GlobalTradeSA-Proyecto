"""
backend/logger.py — Logging estructurado en JSON para GLOBTRADE S.A.

Implementa JSONFormatter con campos: timestamp, level, module, message, exception.
Niveles configurados según la estrategia del diseño:
  - INFO    : Arranque, conexión BD exitosa, creación de índices, resumen ETL.
  - WARNING : Índice no pudo crearse (continúa arranque), lote ETL con rechazos.
  - ERROR   : Variable de entorno faltante, fallo de conexión BD, error de consulta SQL.
  - CRITICAL: Fallo irrecuperable que detiene el arranque.

Requisitos: 1.2, 1.4
"""

import logging
import json
import sys
from datetime import datetime, timezone
from typing import Optional


class JSONFormatter(logging.Formatter):
    """
    Formateador que serializa cada registro de log como una línea JSON.

    Campos incluidos en cada entrada:
      - timestamp : ISO 8601 UTC del momento en que se emite el log.
      - level     : Nombre del nivel (INFO, WARNING, ERROR, CRITICAL, DEBUG).
      - module    : Nombre del módulo Python que originó el registro.
      - message   : Texto del mensaje de log.
      - exception : Traceback completo (solo presente cuando hay exc_info).
    """

    def format(self, record: logging.LogRecord) -> str:
        log_entry: dict = {
            "timestamp": datetime.now(tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "module": record.module,
            "message": record.getMessage(),
        }

        if record.exc_info:
            log_entry["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_entry, ensure_ascii=False)


def get_logger(name: str, level: int = logging.INFO) -> logging.Logger:
    """
    Devuelve un logger configurado con JSONFormatter que escribe en stdout.

    Args:
        name  : Nombre del logger (normalmente __name__ del módulo llamador).
        level : Nivel mínimo de log. Por defecto INFO.

    Returns:
        logging.Logger configurado con el handler JSON.

    Uso típico:
        from backend.logger import get_logger
        logger = get_logger(__name__)
        logger.info("Servidor iniciado")
        logger.error("Variable de entorno DB_HOST faltante")
    """
    logger = logging.getLogger(name)

    # Evitar añadir handlers duplicados si el logger ya fue configurado
    if logger.handlers:
        return logger

    logger.setLevel(level)

    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(level)
    handler.setFormatter(JSONFormatter())

    logger.addHandler(handler)

    # No propagar al root logger para evitar duplicados en entornos con
    # configuración global de logging
    logger.propagate = False

    return logger


def configure_root_logger(level: int = logging.INFO) -> None:
    """
    Configura el root logger con JSONFormatter.

    Útil para capturar logs de librerías de terceros (uvicorn, psycopg2, etc.)
    en el mismo formato JSON estructurado.

    Args:
        level: Nivel mínimo de log para el root logger. Por defecto INFO.
    """
    root = logging.getLogger()
    root.setLevel(level)

    # Reemplazar handlers existentes para evitar duplicados
    root.handlers.clear()

    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(level)
    handler.setFormatter(JSONFormatter())

    root.addHandler(handler)


# ---------------------------------------------------------------------------
# Logger de módulo — disponible para importación directa
# ---------------------------------------------------------------------------
# Ejemplo de uso en otros módulos:
#   from backend.logger import logger
#   logger.info("Pool de conexiones establecido")
# ---------------------------------------------------------------------------
logger: logging.Logger = get_logger("globtrade")
