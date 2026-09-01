"""
backend/middleware — Paquete de middleware para GLOBTRADE S.A.

Exporta:
  - add_error_handlers : Registra los manejadores globales de excepciones.
"""

from backend.middleware.error_handler import add_error_handlers

__all__ = ["add_error_handlers"]
