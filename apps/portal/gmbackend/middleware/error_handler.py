"""
gmbackend/middleware/error_handler.py — Manejadores globales de excepciones del portal B2B.
"""

from __future__ import annotations

from http import HTTPStatus
from typing import Any

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from shared.api.validation_errors import format_validation_errors, validation_summary
from shared.api.db_errors import codigo_http_bd, detalle_respuesta_bd, es_error_bd

_DEFAULT_MESSAGES: dict[int, str] = {
    400: "Solicitud inválida",
    401: "No autorizado",
    403: "Acceso denegado",
    404: "No encontrado",
    409: "Conflicto",
    422: "Error de validación",
    500: "Error interno del servidor",
}


def _http_phrase(code: int) -> str | None:
    try:
        return HTTPStatus(code).phrase
    except ValueError:
        return None


def _build_response(code: int, message: str, detail: Any = None) -> JSONResponse:
    body: dict[str, Any] = {"code": code, "message": message}
    if detail is not None and detail != "" and detail != [] and detail != {}:
        body["detail"] = detail
    return JSONResponse(status_code=code, content=body)


async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    code: int = exc.status_code
    default_message = _DEFAULT_MESSAGES.get(code, "Error en la solicitud")
    phrase = _http_phrase(code)

    if exc.detail is None or exc.detail == phrase:
        message = default_message
        detail = None
    elif isinstance(exc.detail, str):
        message = exc.detail
        detail = None
    elif isinstance(exc.detail, dict):
        message = exc.detail.get("message", default_message)
        detail = exc.detail.get("detail", None)
    else:
        message = default_message
        detail = exc.detail

    return _build_response(code, message, detail)


async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    detail = format_validation_errors(exc.errors())
    message = validation_summary(detail)
    return _build_response(
        code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        message=message,
        detail=detail,
    )


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    if es_error_bd(exc):
        detail = detalle_respuesta_bd(exc)
        return _build_response(
            code=codigo_http_bd(exc),
            message=detail["message"],
            detail={"tipo": detail.get("tipo")},
        )
    return _build_response(
        code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        message=_DEFAULT_MESSAGES[500],
    )


def add_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(HTTPException, http_exception_handler)  # type: ignore[arg-type]
    app.add_exception_handler(RequestValidationError, validation_exception_handler)  # type: ignore[arg-type]
    app.add_exception_handler(Exception, unhandled_exception_handler)  # type: ignore[arg-type]
