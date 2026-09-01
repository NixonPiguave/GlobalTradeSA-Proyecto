"""Router de analytics — consultas ClickHouse con fallback DuckDB."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from backend.database import get_connection
from backend.middleware.authz import require_staff
from backend.services import analytics_service

router = APIRouter()


@router.get("/estado", summary="Estado del almacén analítico ClickHouse")
def analytics_estado(_: dict = Depends(require_staff)) -> dict:
    return analytics_service.almacen_estado()


@router.get("/vistas", summary="Catálogo de vistas analíticas")
def analytics_vistas(_: dict = Depends(require_staff)) -> dict:
    return {
        "vistas": sorted(analytics_service.VISTAS),
        "descripcion": {
            "ranking-proveedores": "Top proveedores por monto de compra",
            "ranking-clientes": "Top clientes por volumen de compra",
            "ventas-por-pais": "Ventas agregadas por país",
            "ventas-por-linea": "Ventas por línea de producto",
            "margen-por-categoria": "Margen por categoría",
            "pedidos-por-estado": "Distribución de pedidos por estado",
        },
    }


@router.get("/{vista}", summary="Datos analíticos para gráficos")
def analytics_vista(
    vista: str,
    desde: Optional[str] = Query(default=None),
    hasta: Optional[str] = Query(default=None),
    limite: int = Query(default=15, ge=1, le=100),
    _: dict = Depends(require_staff),
) -> dict:
    try:
        with get_connection() as conn:
            return analytics_service.consultar_vista(conn, vista, desde=desde, hasta=hasta, limite=limite)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
