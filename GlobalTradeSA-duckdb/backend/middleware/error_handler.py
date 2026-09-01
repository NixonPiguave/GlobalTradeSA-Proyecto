"""
backend/middleware/error_handler.py — Manejador global de excepciones para GLOBTRADE S.A.

Captura excepciones no controladas y las transforma en respuestas JSON estructuradas
con los campos `code`, `message` y opcionalmente `detail`.

Catálogo de errores cubierto:
  400 — Parámetro inválido, formato de fecha incorrecto, columnas CSV faltantes.
  404 — Registro no encontrado en tabla maestra.
  409 — Intento de eliminar registro con dependencias (integridad referencial).
  413 — CSV supera 50 MB.
  422 — Datos malformados en CSV o campos obligatorios ausentes (Pydantic).
  503 — Pool de conexiones agotado.
  504 — Timeout de consulta (>30 s) o exportación CSV (>15 s).
  500 — Error interno no controlado.

Requisitos: 8.4
"""

from __future__ import annotations

from http import HTTPStatus
from typing import Any

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from backend.logger import get_logger

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Mensajes predeterminados por código HTTP (en español)
# ---------------------------------------------------------------------------

_DEFAULT_MESSAGES: dict[int, str] = {
    400: "Solicitud inválida",
    404: "Registro no encontrado",
    409: "Restricción de integridad referencial",
    413: "El archivo supera el límite de 50 MB",
    422: "Error de validación",
    500: "Error interno del servidor",
    503: "Servidor temporalmente no disponible",
    504: "Tiempo límite de consulta excedido",
}


def _http_phrase(code: int) -> str | None:
    """Devuelve la frase HTTP estándar en inglés para un código dado, o None."""
    try:
        return HTTPStatus(code).phrase
    except ValueError:
        return None


def _build_response(
    code: int,
    message: str,
    detail: Any = None,
) -> JSONResponse:
    """
    Construye una JSONResponse con el formato estándar de error de GLOBTRADE.

    El campo `detail` se incluye en el cuerpo solo cuando no es None ni vacío,
    para mantener respuestas compactas en los casos que no lo requieren
    (404, 413, 503, 504).

    Args:
        code    : Código HTTP de la respuesta.
        message : Mensaje legible en español.
        detail  : Información adicional (dict, list, str) o None.

    Returns:
        JSONResponse con status_code = code y cuerpo JSON estructurado.
    """
    body: dict[str, Any] = {"code": code, "message": message}
    if detail is not None and detail != "" and detail != [] and detail != {}:
        body["detail"] = detail
    return JSONResponse(status_code=code, content=body)


# ---------------------------------------------------------------------------
# Handler: HTTPException
# ---------------------------------------------------------------------------

async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    """
    Convierte cualquier HTTPException de FastAPI en la respuesta JSON estándar.

    FastAPI populates `exc.detail` with the HTTP reason phrase (e.g. "Not Found")
    when no explicit detail is provided. We detect this case and substitute the
    Spanish catalog message instead.

    Routers can enrich the error by passing an explicit string or dict:
        raise HTTPException(status_code=404, detail="Región con id=99 no encontrada")
        raise HTTPException(status_code=409, detail="Restricción de integridad referencial: paises → regiones")
        raise HTTPException(status_code=400, detail={"message": "Fecha inválida", "detail": {"field": "date_from"}})
    """
    code: int = exc.status_code
    default_message = _DEFAULT_MESSAGES.get(code, "Error en la solicitud")
    phrase = _http_phrase(code)  # English HTTP reason phrase, e.g. "Not Found"

    if exc.detail is None or exc.detail == phrase:
        # No meaningful detail — use the Spanish catalog message
        message = default_message
        detail = None
    elif isinstance(exc.detail, str):
        # Explicit string detail — use it as the message
        message = exc.detail
        detail = None
    elif isinstance(exc.detail, dict):
        # Dict detail may carry separate "message" and "detail" keys
        message = exc.detail.get("message", default_message)
        detail = exc.detail.get("detail", None)
    else:
        message = default_message
        detail = exc.detail

    logger.warning(
        "HTTPException capturada — %s %s: %s",
        code,
        str(request.url),
        message,
    )

    return _build_response(code, message, detail)


# ---------------------------------------------------------------------------
# Handler: RequestValidationError (Pydantic / FastAPI)
# ---------------------------------------------------------------------------

async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """
    Convierte errores de validación de Pydantic (422 Unprocessable Entity) en
    la respuesta JSON estándar con detalle de los campos inválidos.

    El campo `detail` es una lista de objetos con:
      - loc   : Ubicación del campo (e.g. ["body", "order_date"]).
      - msg   : Mensaje de error en inglés de Pydantic.
      - type  : Tipo de error de Pydantic (e.g. "value_error.date").

    Requisito 8.4 — los errores de validación deben devolver HTTP 422 con
    detalle de los campos inválidos.
    """
    errors = exc.errors()

    # Normalizar la lista de errores para el formato de respuesta
    detail = [
        {
            "loc": list(err.get("loc", [])),
            "msg": err.get("msg", ""),
            "type": err.get("type", ""),
        }
        for err in errors
    ]

    logger.warning(
        "Error de validacion de request — %s (%d campo(s) invalido(s))",
        str(request.url),
        len(detail),
    )

    return _build_response(
        code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        message="Error de validación en los datos enviados",
        detail=detail,
    )


# ---------------------------------------------------------------------------
# Handler: Excepciones no controladas (catch-all)
# ---------------------------------------------------------------------------

async def unhandled_exception_handler(
    request: Request, exc: Exception
) -> JSONResponse:
    """
    Captura cualquier excepción no controlada y devuelve HTTP 500.

    El traceback completo se registra en el log con nivel ERROR para facilitar
    la depuración, pero NO se expone en la respuesta al cliente por seguridad.

    Requisito 8.4 — errores internos no controlados deben devolver HTTP 500
    con el mensaje genérico "Error interno del servidor".
    """
    logger.error(
        "Excepcion no controlada — %s %s: %s",
        type(exc).__name__,
        str(request.url),
        str(exc),
        exc_info=exc,
    )

    return _build_response(
        code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        message=_DEFAULT_MESSAGES[500],
    )


# ---------------------------------------------------------------------------
# Función de registro — punto de entrada público
# ---------------------------------------------------------------------------

def add_error_handlers(app: FastAPI) -> None:
    """
    Registra todos los manejadores de excepciones en la instancia de FastAPI.

    Debe llamarse durante la inicialización de la aplicación, antes de que
    comience a recibir solicitudes.

    Args:
        app: Instancia de FastAPI sobre la que se registran los handlers.

    Uso típico en main.py:
        from backend.middleware.error_handler import add_error_handlers

        app = FastAPI()
        add_error_handlers(app)

    Handlers registrados:
        - HTTPException          → http_exception_handler
        - RequestValidationError → validation_exception_handler
        - Exception              → unhandled_exception_handler
    """
    app.add_exception_handler(HTTPException, http_exception_handler)  # type: ignore[arg-type]
    app.add_exception_handler(RequestValidationError, validation_exception_handler)  # type: ignore[arg-type]
    app.add_exception_handler(Exception, unhandled_exception_handler)  # type: ignore[arg-type]

    logger.info("Manejadores de excepciones registrados correctamente")
