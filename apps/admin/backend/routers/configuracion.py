"""
routers/configuracion.py — Parámetros del sistema configurables desde el admin.
"""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel, Field

from backend.database import get_connection, notify_db_changed
from backend.middleware.authz import require_staff
from backend.services.auditoria_service import registrar_auditoria
from backend.services.imagen_service import guardar_imagen
from shared.services.config_service import (
    CLAVES_IA,
    CLAVES_OCULTAS_PANEL,
    actualizar_config,
    enmascarar_secreto,
    listar_config,
)

router = APIRouter()

_NUMERIC_KEYS = {"IVA_PCT", "MOQ_MAYORISTA"}


def _validar_valor(clave: str, valor: str) -> str:
    valor = valor.strip()
    if clave in _NUMERIC_KEYS:
        try:
            numero = float(valor)
        except ValueError:
            raise HTTPException(
                status_code=422,
                detail={
                    "code": 422,
                    "message": f"El parámetro {clave} debe ser un número.",
                },
            )
        if numero < 0:
            raise HTTPException(
                status_code=422,
                detail={"code": 422, "message": f"El parámetro {clave} no puede ser negativo."},
            )
        if clave == "IVA_PCT" and numero > 100:
            raise HTTPException(
                status_code=422,
                detail={"code": 422, "message": "El porcentaje de IVA debe estar entre 0 y 100."},
            )
    return valor


class ConfigUpdate(BaseModel):
    valor: str = Field(min_length=1, max_length=500)


class IaConfigUpdate(BaseModel):
    api_key: Optional[str] = Field(default=None, max_length=500)
    base_url: Optional[str] = Field(default=None, max_length=300)
    model: Optional[str] = Field(default=None, max_length=120)


@router.get("", summary="Listar configuración del sistema")
def listar(_: dict = Depends(require_staff)) -> list[dict[str, Any]]:
    with get_connection() as conn:
        return listar_config(conn)


@router.get("/ia", summary="Configuración del proveedor IA")
def obtener_ia(_: dict = Depends(require_staff)) -> dict[str, Any]:
    from backend.services.ia_service import _config

    with get_connection() as conn:
        cfg = _config(conn)
        return {
            "api_key_configured": bool(cfg.get("api_key")),
            "api_key_masked": enmascarar_secreto(cfg.get("api_key") or ""),
            "base_url": cfg.get("base_url"),
            "model": cfg.get("modelo"),
            "fuente": cfg.get("fuente"),
        }


@router.put("/ia", summary="Actualizar proveedor IA")
def actualizar_ia(
    body: IaConfigUpdate,
    usuario: dict = Depends(require_staff),
) -> dict[str, Any]:
    from backend.services.ia_service import _config

    with get_connection() as conn:
        if body.api_key is not None:
            clave = body.api_key.strip()
            if clave and clave not in {"********", "••••••••"}:
                if len(clave) < 8:
                    raise HTTPException(
                        status_code=422,
                        detail={"code": 422, "message": "La API key debe tener al menos 8 caracteres."},
                    )
                actualizar_config(conn, "IA_API_KEY", clave)
        if body.base_url is not None:
            url = body.base_url.strip()
            if not url:
                raise HTTPException(status_code=422, detail={"code": 422, "message": "La URL base no puede estar vacía."})
            if not url.startswith(("http://", "https://")):
                raise HTTPException(status_code=422, detail={"code": 422, "message": "La URL base debe comenzar con http:// o https://"})
            actualizar_config(conn, "IA_BASE_URL", url.rstrip("/"))
        if body.model is not None:
            modelo = body.model.strip()
            if not modelo:
                raise HTTPException(status_code=422, detail={"code": 422, "message": "El modelo no puede estar vacío."})
            actualizar_config(conn, "IA_MODEL", modelo)

        cfg = _config(conn)
        registrar_auditoria(
            conn,
            id_usuario=usuario["id_usuario"],
            entidad="configuracion",
            entidad_id=0,
            accion="actualizar_ia",
            valor_nuevo={
                "base_url": cfg.get("base_url"),
                "model": cfg.get("modelo"),
                "api_key_configured": bool(cfg.get("api_key")),
            },
        )
        notify_db_changed(conn)
        return {
            "status": "ok",
            "api_key_configured": bool(cfg.get("api_key")),
            "api_key_masked": enmascarar_secreto(cfg.get("api_key") or ""),
            "base_url": cfg.get("base_url"),
            "model": cfg.get("modelo"),
            "fuente": cfg.get("fuente"),
        }


@router.post("/logo", status_code=201, summary="Subir logo de empresa para comprobantes PDF")
async def subir_logo(file: UploadFile = File(...), _: dict = Depends(require_staff)) -> dict[str, str]:
    contenido = await file.read()
    with get_connection() as conn:
        ruta = guardar_imagen(contenido, file.filename or "logo", subdir="empresa")
        actualizar_config(conn, "EMPRESA_LOGO", ruta)
        notify_db_changed(conn)
    return {"ruta": ruta, "url": f"/media/{ruta}"}


@router.delete("/logo", summary="Quitar logo de comprobantes")
def quitar_logo(_: dict = Depends(require_staff)) -> dict[str, str]:
    with get_connection() as conn:
        actualizar_config(conn, "EMPRESA_LOGO", "")
        notify_db_changed(conn)
    return {"status": "ok"}


@router.post("/test-ia", summary="Probar conexión con el servicio de IA")
def test_ia(_: dict = Depends(require_staff)) -> dict:
    from backend.services.ia_service import probar_conexion

    with get_connection() as conn:
        return probar_conexion(conn)


@router.put("/{clave}", summary="Actualizar parámetro")
def actualizar(clave: str, body: ConfigUpdate, _: dict = Depends(require_staff)) -> dict[str, str]:
    if clave == "logo":
        raise HTTPException(status_code=405, detail="Usa POST /api/configuracion/logo para subir el logo.")
    if clave in CLAVES_OCULTAS_PANEL:
        raise HTTPException(
            status_code=405,
            detail="Este parámetro se gestiona en otra sección del panel (Marketing o Configuración IA).",
        )
    valor_validado = _validar_valor(clave, body.valor)
    with get_connection() as conn:
        actualizar_config(conn, clave, valor_validado)
        notify_db_changed(conn)
    return {"status": "ok", "clave": clave}
