"""
routers/dashboard.py — Endpoints del Dashboard de GLOBTRADE S.A.

Rutas (montadas bajo /api/dashboard):
    GET /api/dashboard/kpis        — KPIs globales con filtro de fecha y región
    GET /api/dashboard/charts      — Datos para las 3 gráficas de barras
    GET /api/dashboard/top-paises  — Top 5 países por total_profit

Parámetros aceptados:
    date_from / fecha_inicio  — fecha inicio YYYY-MM-DD
    date_to   / fecha_fin     — fecha fin YYYY-MM-DD
    region                    — filtro por región (ventas.region)

Requisitos cubiertos: 2.1, 2.3, 2.4, 2.5, 2.6, 2.7, 2.9
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Header, Query

from backend.database import get_connection, notify_db_changed
from backend.middleware.authz import require_perm, require_staff
from backend.models.validators import validate_date_range
from backend.services.kpi_service import get_kpis, get_charts_data, get_top_paises
from shared.services.integracion_ventas_service import reintegrar_pedidos_pendientes

logger = logging.getLogger(__name__)

router = APIRouter()
internal_router = APIRouter()


def _resolve_dates(
    date_from: Optional[str],
    date_to: Optional[str],
    fecha_inicio: Optional[str],
    fecha_fin: Optional[str],
) -> tuple[Optional[str], Optional[str]]:
    """Acepta tanto date_from/date_to como los alias fecha_inicio/fecha_fin del frontend."""
    return (date_from or fecha_inicio), (date_to or fecha_fin)


@router.get("/kpis", summary="KPIs globales")
def dashboard_kpis(
    date_from:    Optional[str] = Query(default=None, description="Fecha inicio YYYY-MM-DD"),
    date_to:      Optional[str] = Query(default=None, description="Fecha fin YYYY-MM-DD"),
    fecha_inicio: Optional[str] = Query(default=None, description="Alias de date_from"),
    fecha_fin:    Optional[str] = Query(default=None, description="Alias de date_to"),
    region:       Optional[str] = Query(default=None, description="Filtrar por región"),
    origen:       Optional[str] = Query(default=None, description="Filtrar por origen: historico | portal"),
) -> dict:
    """
    Devuelve total_revenue, total_cost, total_profit y units_sold.
    Acepta filtro opcional por rango de fechas y región.
    Requisito 2.1, 2.6
    """
    raw_from, raw_to = _resolve_dates(date_from, date_to, fecha_inicio, fecha_fin)
    parsed_from, parsed_to = validate_date_range(raw_from, raw_to)
    with get_connection() as conn:
        result = get_kpis(conn, date_from=parsed_from, date_to=parsed_to, region=region, origen=origen)
    result["date_from"] = raw_from
    result["date_to"] = raw_to
    return result


@router.get("/charts", summary="Datos para gráficas de barras")
def dashboard_charts(
    date_from:    Optional[str] = Query(default=None, description="Fecha inicio YYYY-MM-DD"),
    date_to:      Optional[str] = Query(default=None, description="Fecha fin YYYY-MM-DD"),
    fecha_inicio: Optional[str] = Query(default=None, description="Alias de date_from"),
    fecha_fin:    Optional[str] = Query(default=None, description="Alias de date_to"),
    region:       Optional[str] = Query(default=None, description="Filtrar por región"),
    origen:       Optional[str] = Query(default=None, description="Filtrar por origen: historico | portal"),
) -> dict:
    """
    Devuelve datos agrupados por región, canal de venta y tipo de producto.
    Requisito 2.3, 2.4, 2.5, 2.6
    """
    raw_from, raw_to = _resolve_dates(date_from, date_to, fecha_inicio, fecha_fin)
    parsed_from, parsed_to = validate_date_range(raw_from, raw_to)
    with get_connection() as conn:
        return get_charts_data(conn, date_from=parsed_from, date_to=parsed_to, region=region, origen=origen)


@router.get("/top-paises", summary="Top 5 países por total_profit")
def dashboard_top_paises(
    date_from:    Optional[str] = Query(default=None, description="Fecha inicio YYYY-MM-DD"),
    date_to:      Optional[str] = Query(default=None, description="Fecha fin YYYY-MM-DD"),
    fecha_inicio: Optional[str] = Query(default=None, description="Alias de date_from"),
    fecha_fin:    Optional[str] = Query(default=None, description="Alias de date_to"),
    region:       Optional[str] = Query(default=None, description="Filtrar por región"),
    origen:       Optional[str] = Query(default=None, description="Filtrar por origen: historico | portal"),
) -> list:
    """
    Devuelve los 5 países con mayor total_profit como lista directa.
    Requisito 2.7
    """
    raw_from, raw_to = _resolve_dates(date_from, date_to, fecha_inicio, fecha_fin)
    parsed_from, parsed_to = validate_date_range(raw_from, raw_to)
    with get_connection() as conn:
        return get_top_paises(conn, date_from=parsed_from, date_to=parsed_to, region=region, origen=origen)


@router.post("/refrescar-analiticas", summary="Reconstruir tablas analíticas y vista ventas")
def refrescar_analiticas(_: dict = Depends(require_staff)) -> dict:
    """Idempotente: recrea anal_* desde fact_ventas (útil tras restaurar BD o migrar)."""
    from shared.services.analiticas_service import refrescar_analiticas_dashboard

    with get_connection() as conn:
        resultado = refrescar_analiticas_dashboard(conn)
        notify_db_changed(conn)
    return resultado


@router.get("/etl-estado", summary="Información adicional: estado de la sincronización ETL")
def dashboard_etl_estado() -> dict:
    """
    Información adicional del dashboard: KPIs persistidos por el ETL (anal_kpis),
    últimas ejecuciones (etl_control) y tablas analíticas disponibles.
    """
    with get_connection() as conn:
        if conn.execute(
            "SELECT 1 FROM information_schema.tables WHERE table_name = 'anal_kpis'"
        ).fetchone():
            kpis_rows = conn.execute(
                "SELECT kpi, valor, unidad FROM anal_kpis ORDER BY kpi"
            ).fetchall()
        else:
            kpis_rows = []
        if conn.execute(
            "SELECT 1 FROM information_schema.tables WHERE table_name = 'etl_control'"
        ).fetchone():
            ultimas_rows = conn.execute(
                "SELECT etapa, inicio, tiempo_s, filas, estado, detalle "
                "FROM etl_control ORDER BY id DESC LIMIT 3"
            ).fetchall()
        else:
            ultimas_rows = []
        tablas = [r[0] for r in conn.execute(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_name LIKE 'anal_%' ORDER BY table_name"
        ).fetchall()]
        filas_fact = int(
            conn.execute("SELECT COUNT(*) FROM fact_ventas").fetchone()[0]
        )
    return {
        "kpis": [
            {"kpi": r[0], "valor": r[1], "unidad": r[2]} for r in kpis_rows
        ],
        "ultimas_ejecuciones": [
            {
                "etapa": r[0],
                "inicio": (
                    datetime.fromtimestamp(r[1]).strftime("%Y-%m-%d %H:%M:%S")
                    if r[1] is not None
                    else None
                ),
                "tiempo_s": r[2],
                "filas": r[3],
                "estado": r[4],
                "detalle": r[5],
            }
            for r in ultimas_rows
        ],
        "tablas_analiticas": tablas,
        "filas_fact_ventas": filas_fact,
    }


@router.post("/sync-clickhouse", summary="Publicar marts DuckDB hacia ClickHouse")
def sync_clickhouse(_: dict = Depends(require_staff)) -> dict:
    return _ejecutar_sync_clickhouse()


def _validar_token_interno(token: str | None) -> None:
    import os

    from fastapi import HTTPException

    esperado = os.environ.get("ETL_INTERNAL_TOKEN", "").strip()
    if not esperado or not token or token.strip() != esperado:
        raise HTTPException(status_code=403, detail="Token interno ETL inválido.")


@internal_router.post("/sync-clickhouse/internal", summary="Publicar marts (token interno Airflow/Docker)")
def sync_clickhouse_internal(
    x_etl_internal_token: str | None = Header(default=None, alias="X-ETL-Internal-Token"),
) -> dict:
    _validar_token_interno(x_etl_internal_token)
    return _ejecutar_sync_clickhouse()


def _ejecutar_sync_clickhouse() -> dict:
    from shared.services.clickhouse_publish import publicar_desde_duckdb
    from shared.services.clickhouse_service import clickhouse_disponible

    if not clickhouse_disponible():
        return {"publicado": False, "motivo": "ClickHouse no disponible"}
    with get_connection() as conn:
        return publicar_desde_duckdb(conn)


@router.post("/reintegrar-pedidos", summary="Reintegrar pedidos pagados a fact_ventas")
def reintegrar_pedidos(_: dict = Depends(require_staff)) -> dict:
    """Idempotente: inserta líneas de pedidos portal que aún no están en fact_ventas."""
    with get_connection() as conn:
        resultado = reintegrar_pedidos_pendientes(conn)
        if resultado.get("insertadas", 0) > 0:
            notify_db_changed()
    return resultado


@router.get("/operaciones", summary="KPIs y alertas del Panel de Operaciones")
def operaciones(_: dict = Depends(require_perm("mod.dashboard", "mod.operaciones"))) -> dict:
    from backend.services.operaciones_service import panel_operaciones

    with get_connection() as conn:
        return panel_operaciones(conn)
