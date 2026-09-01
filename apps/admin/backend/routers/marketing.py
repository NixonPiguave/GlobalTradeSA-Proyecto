"""
routers/marketing.py — Gestión de banners y promociones del portal B2B.
"""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from pydantic import BaseModel, Field

import duckdb

from backend.database import get_connection, notify_db_changed
from backend.middleware.authz import require_staff
from backend.services import marketing_service
from backend.services.imagen_service import guardar_imagen
from shared.api.db_errors import codigo_http_bd, detalle_respuesta_bd, es_error_bd

router = APIRouter()


class BannerIn(BaseModel):
    titulo: str = Field(min_length=2, max_length=120)
    imagen_path: Optional[str] = None
    enlace: Optional[str] = None
    orden: int = 0
    activo: bool = True


class PromocionIn(BaseModel):
    nombre: str = Field(min_length=2, max_length=120)
    descuento_pct: float = Field(ge=0, le=100)
    fecha_inicio: str
    fecha_fin: str
    activa: bool = True


@router.post("/banners/imagen", status_code=201, summary="Subir imagen de banner")
async def subir_imagen_banner(file: UploadFile = File(...), _: dict = Depends(require_staff)) -> dict[str, str]:
    contenido = await file.read()
    try:
        ruta = guardar_imagen(contenido, file.filename or "banner", subdir="banners")
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    return {"ruta": ruta, "url": f"/media/{ruta}"}


@router.get("/banners", summary="Listar banners del portal")
def banners(_: dict = Depends(require_staff)) -> list[dict[str, Any]]:
    with get_connection() as conn:
        return marketing_service.listar_banners(conn)


@router.post("/banners", status_code=201, summary="Crear banner")
def crear_banner(body: BannerIn, _: dict = Depends(require_staff)) -> dict[str, Any]:
    with get_connection() as conn:
        result = marketing_service.crear_banner(
            conn,
            titulo=body.titulo,
            imagen_path=body.imagen_path,
            enlace=body.enlace,
            orden=body.orden,
            activo=body.activo,
        )
        notify_db_changed(conn)
        return result


@router.put("/banners/{id_banner}", summary="Actualizar banner")
def actualizar_banner(id_banner: int, body: BannerIn, _: dict = Depends(require_staff)) -> dict[str, str]:
    with get_connection() as conn:
        marketing_service.actualizar_banner(
            conn, id_banner,
            titulo=body.titulo,
            imagen_path=body.imagen_path,
            enlace=body.enlace,
            orden=body.orden,
            activo=body.activo,
        )
        notify_db_changed(conn)
    return {"status": "ok"}


@router.delete("/banners/{id_banner}", summary="Eliminar banner")
def eliminar_banner(id_banner: int, _: dict = Depends(require_staff)) -> dict[str, str]:
    with get_connection() as conn:
        marketing_service.eliminar_banner(conn, id_banner)
        notify_db_changed(conn)
    return {"status": "ok"}


@router.get("/promociones", summary="Listar promociones")
def promociones(_: dict = Depends(require_staff)) -> list[dict[str, Any]]:
    with get_connection() as conn:
        return marketing_service.listar_promociones(conn)


@router.post("/promociones", status_code=201, summary="Crear promoción")
def crear_promocion(body: PromocionIn, _: dict = Depends(require_staff)) -> dict[str, Any]:
    with get_connection() as conn:
        try:
            result = marketing_service.crear_promocion(
                conn,
                nombre=body.nombre,
                descuento_pct=body.descuento_pct,
                fecha_inicio=body.fecha_inicio,
                fecha_fin=body.fecha_fin,
                activa=body.activa,
            )
            notify_db_changed(conn)
            return result
        except ValueError as e:
            raise HTTPException(status_code=422, detail=str(e)) from e
        except duckdb.Error as e:
            raise HTTPException(
                status_code=codigo_http_bd(e),
                detail=detalle_respuesta_bd(e)["message"],
            ) from e


@router.put("/promociones/{id_promocion}", summary="Actualizar promoción")
def actualizar_promocion(id_promocion: int, body: PromocionIn, _: dict = Depends(require_staff)) -> dict[str, str]:
    with get_connection() as conn:
        try:
            marketing_service.actualizar_promocion(
                conn, id_promocion,
                nombre=body.nombre,
                descuento_pct=body.descuento_pct,
                fecha_inicio=body.fecha_inicio,
                fecha_fin=body.fecha_fin,
                activa=body.activa,
            )
            notify_db_changed(conn)
        except ValueError as e:
            raise HTTPException(status_code=422, detail=str(e)) from e
        except duckdb.Error as e:
            raise HTTPException(
                status_code=codigo_http_bd(e),
                detail=detalle_respuesta_bd(e)["message"],
            ) from e
    return {"status": "ok"}


@router.delete("/promociones/{id_promocion}", summary="Eliminar promoción")
def eliminar_promocion(id_promocion: int, _: dict = Depends(require_staff)) -> dict[str, str]:
    with get_connection() as conn:
        try:
            marketing_service.eliminar_promocion(conn, id_promocion)
            notify_db_changed(conn)
        except ValueError as e:
            raise HTTPException(status_code=422, detail=str(e)) from e
        except duckdb.Error as e:
            raise HTTPException(
                status_code=codigo_http_bd(e),
                detail=detalle_respuesta_bd(e)["message"],
            ) from e
    return {"status": "ok"}


class CarruselIn(BaseModel):
    ids: list[int] = Field(default_factory=list)


@router.get("/carrusel", summary="Productos del carrusel del portal")
def get_carrusel(_: dict = Depends(require_staff)) -> dict[str, Any]:
    with get_connection() as conn:
        return marketing_service.obtener_carrusel(conn)


@router.put("/carrusel", summary="Guardar productos del carrusel")
def put_carrusel(body: CarruselIn, _: dict = Depends(require_staff)) -> dict[str, Any]:
    with get_connection() as conn:
        result = marketing_service.guardar_carrusel(conn, body.ids)
        notify_db_changed(conn)
        return result
