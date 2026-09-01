"""
routers/reportes.py — Reportes del panel: catálogo, visualización en pantalla
(JSON) y exportación PDF/CSV. Requiere permiso mod.reportes (ver main.py).
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse, JSONResponse, Response

from backend.database import get_connection
from backend.middleware.authz import get_current_staff
from backend.services import ia_service, reporte_service

router = APIRouter()


@router.get("/", summary="Catálogo de reportes disponibles")
def listar_reportes(_: dict = Depends(get_current_staff)) -> dict:
    from backend.services import reporte_clickhouse_service

    return {
        "reportes": reporte_service.catalogo_reportes(),
        "clickhouse": reporte_clickhouse_service.estado_informes(),
    }


def _construir_filtros(**kwargs) -> dict:
    return {k: v for k, v in kwargs.items() if v is not None and v != ""}


@router.get("/vista/{nombre}", summary="Ver reporte en pantalla (JSON)")
def ver_reporte(
    nombre: str,
    desde: Optional[str] = None,
    hasta: Optional[str] = None,
    region: Optional[str] = None,
    country: Optional[str] = None,
    item_type: Optional[str] = None,
    sales_channel: Optional[str] = None,
    order_priority: Optional[str] = None,
    origen: Optional[str] = None,
    almacen: Optional[int] = None,
    estado: Optional[str] = None,
    producto: Optional[str] = None,
    limite: Optional[int] = None,
    _: dict = Depends(get_current_staff),
) -> JSONResponse:
    filtros = _construir_filtros(
        desde=desde, hasta=hasta, region=region, country=country,
        item_type=item_type, sales_channel=sales_channel,
        order_priority=order_priority, origen=origen, almacen=almacen,
        estado=estado, producto=producto, limite=limite,
    )
    with get_connection() as conn:
        try:
            datos = reporte_service.obtener_reporte_vista(conn, nombre=nombre, filtros=filtros)
        except ValueError as e:
            raise HTTPException(status_code=422, detail=str(e))
    return JSONResponse(content=datos)


@router.get("/programados", summary="Reportes generados por el DAG nocturno")
def listar_programados(_: dict = Depends(get_current_staff)) -> dict:
    with get_connection() as conn:
        return {"reportes": reporte_service.listar_reportes_programados(conn)}


@router.get("/programados/{id_reporte}/descargar", summary="Descargar reporte programado")
def descargar_programado(
    id_reporte: int,
    _: dict = Depends(get_current_staff),
) -> FileResponse:
    with get_connection() as conn:
        ruta = reporte_service.ruta_reporte_programado(conn, id_reporte)
    if ruta is None:
        raise HTTPException(status_code=404, detail="Reporte programado no encontrado o ya vencido.")
    media_type = "application/pdf" if ruta.suffix.lower() == ".pdf" else "text/csv; charset=utf-8"
    return FileResponse(str(ruta), media_type=media_type, filename=ruta.name)


@router.get("/ia/{nombre}", summary="Resumen ejecutivo del reporte con IA")
def resumen_ia(
    nombre: str,
    desde: Optional[str] = None,
    hasta: Optional[str] = None,
    region: Optional[str] = None,
    country: Optional[str] = None,
    item_type: Optional[str] = None,
    sales_channel: Optional[str] = None,
    order_priority: Optional[str] = None,
    origen: Optional[str] = None,
    almacen: Optional[int] = None,
    estado: Optional[str] = None,
    producto: Optional[str] = None,
    limite: Optional[int] = None,
    nivel: str = Query("tactico", pattern="^(operativo|tactico|estrategico)$"),
    _: dict = Depends(get_current_staff),
) -> JSONResponse:
    filtros = _construir_filtros(
        desde=desde, hasta=hasta, region=region, country=country,
        item_type=item_type, sales_channel=sales_channel,
        order_priority=order_priority, origen=origen, almacen=almacen,
        estado=estado, producto=producto, limite=limite,
    )
    with get_connection() as conn:
        resultado = ia_service.generar_resumen(conn, nombre=nombre, filtros=filtros, nivel=nivel)
    if resultado["estado"] == "error":
        raise HTTPException(status_code=502, detail=resultado.get("detalle") or "Error del proveedor IA.")
    return JSONResponse(content=resultado)


@router.get("/{nombre}", summary="Descargar reporte PDF o CSV")
def descargar_reporte(
    nombre: str,
    formato: str = Query("pdf", pattern="^(pdf|csv)$"),
    desde: Optional[str] = None,
    hasta: Optional[str] = None,
    region: Optional[str] = None,
    country: Optional[str] = None,
    item_type: Optional[str] = None,
    sales_channel: Optional[str] = None,
    order_priority: Optional[str] = None,
    origen: Optional[str] = None,
    almacen: Optional[int] = None,
    estado: Optional[str] = None,
    producto: Optional[str] = None,
    limite: Optional[int] = None,
    _: dict = Depends(get_current_staff),
) -> Response:
    filtros = _construir_filtros(
        desde=desde, hasta=hasta, region=region, country=country,
        item_type=item_type, sales_channel=sales_channel,
        order_priority=order_priority, origen=origen, almacen=almacen,
        estado=estado, producto=producto, limite=limite,
    )
    with get_connection() as conn:
        try:
            data, media_type, filename = reporte_service.generar_reporte(
                conn, nombre=nombre, formato=formato, filtros=filtros
            )
        except ValueError as e:
            raise HTTPException(status_code=422, detail=str(e))
    return Response(
        content=data,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )