"""
routers/estrategia.py — Módulo estratégico: cuadro de mando (objetivos/OKR),
análisis de expansión de mercado, proyección de ventas, matriz de riesgos e
informe estratégico integral con IA.

Exige el permiso `mod.estrategia`.
"""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel, Field

from backend.database import get_connection
from backend.middleware.authz import require_perm
from backend.services import estrategia_service, ia_service

router = APIRouter(dependencies=[Depends(require_perm("mod.estrategia"))])


def _error(exc: Exception) -> HTTPException:
    return HTTPException(status_code=400, detail=str(exc))


# --- Modelos de request ----------------------------------------------------

class ObjetivoCreate(BaseModel):
    nombre: str = Field(min_length=2, max_length=200)
    tipo_metrica: str
    meta_numerica: float
    descripcion: str = ""
    periodo: str = ""
    orden: int = 0


class ObjetivoUpdate(BaseModel):
    nombre: Optional[str] = None
    descripcion: Optional[str] = None
    tipo_metrica: Optional[str] = None
    meta_numerica: Optional[float] = None
    periodo: Optional[str] = None
    orden: Optional[int] = None
    activo: Optional[bool] = None


class RiesgoCreate(BaseModel):
    nombre: str = Field(min_length=2, max_length=200)
    probabilidad: int = Field(ge=1, le=5)
    impacto: int = Field(ge=1, le=5)
    descripcion: str = ""
    mitigacion: str = ""
    id_objetivo: Optional[int] = None


class RiesgoUpdate(BaseModel):
    nombre: Optional[str] = None
    descripcion: Optional[str] = None
    probabilidad: Optional[int] = Field(default=None, ge=1, le=5)
    impacto: Optional[int] = Field(default=None, ge=1, le=5)
    mitigacion: Optional[str] = None
    id_objetivo: Optional[int] = None
    estado: Optional[str] = None


# --- Cuadro de mando --------------------------------------------------------

@router.get("/objetivos", summary="Cuadro de mando con avance automático")
def listar_objetivos(
    incluir_inactivos: bool = False,
    _: dict = Depends(require_perm("mod.estrategia")),
) -> list[dict[str, Any]]:
    with get_connection() as conn:
        return estrategia_service.listar_objetivos(conn, incluir_inactivos=incluir_inactivos)


@router.post("/objetivos", summary="Crear objetivo estratégico")
def crear_objetivo(
    body: ObjetivoCreate,
    usuario: dict = Depends(require_perm("mod.estrategia")),
) -> dict[str, Any]:
    try:
        with get_connection() as conn:
            return estrategia_service.crear_objetivo(
                conn,
                nombre=body.nombre,
                tipo_metrica=body.tipo_metrica,
                meta_numerica=body.meta_numerica,
                descripcion=body.descripcion,
                periodo=body.periodo,
                orden=body.orden,
                id_usuario_actor=usuario.get("id_usuario"),
            )
    except ValueError as exc:
        raise _error(exc) from exc


@router.put("/objetivos/{id_objetivo}", summary="Actualizar objetivo")
def actualizar_objetivo(
    id_objetivo: int,
    body: ObjetivoUpdate,
    usuario: dict = Depends(require_perm("mod.estrategia")),
) -> dict[str, Any]:
    try:
        with get_connection() as conn:
            return estrategia_service.actualizar_objetivo(
                conn, id_objetivo=id_objetivo, **body.model_dump(exclude_unset=True),
                id_usuario_actor=usuario.get("id_usuario"),
            )
    except ValueError as exc:
        raise _error(exc) from exc


@router.delete("/objetivos/{id_objetivo}", summary="Eliminar objetivo")
def eliminar_objetivo(
    id_objetivo: int,
    usuario: dict = Depends(require_perm("mod.estrategia")),
) -> dict[str, str]:
    try:
        with get_connection() as conn:
            estrategia_service.eliminar_objetivo(
                conn, id_objetivo=id_objetivo, id_usuario_actor=usuario.get("id_usuario"),
            )
    except ValueError as exc:
        raise _error(exc) from exc
    return {"ok": "true"}


# --- Expansión de mercado ----------------------------------------------------

@router.get("/expansion", summary="Análisis de expansión de mercado")
def analisis_expansion(
    _: dict = Depends(require_perm("mod.estrategia")),
) -> dict[str, Any]:
    with get_connection() as conn:
        return estrategia_service.analisis_expansion(conn)


# --- Proyección de ventas -----------------------------------------------------

@router.get("/proyeccion", summary="Proyección de ventas (regresión lineal)")
def proyeccion_ventas(
    meses: int = Query(12, ge=1, le=24),
    formato: str = Query("json", pattern="^(json|pdf)$"),
    _: dict = Depends(require_perm("mod.estrategia")),
) -> Any:
    try:
        with get_connection() as conn:
            datos = estrategia_service.proyeccion_ventas(conn, meses=meses)
            if formato == "pdf":
                data = estrategia_service.pdf_proyeccion(conn, datos)
                return Response(
                    content=data,
                    media_type="application/pdf",
                    headers={"Content-Disposition": 'attachment; filename="proyeccion_ventas.pdf"'},
                )
            return datos
    except ValueError as exc:
        raise _error(exc) from exc


# --- Matriz de riesgos ---------------------------------------------------------

@router.get("/riesgos", summary="Matriz de riesgos estratégicos")
def listar_riesgos(
    _: dict = Depends(require_perm("mod.estrategia")),
) -> list[dict[str, Any]]:
    with get_connection() as conn:
        return estrategia_service.listar_riesgos(conn)


@router.post("/riesgos", summary="Crear riesgo estratégico")
def crear_riesgo(
    body: RiesgoCreate,
    usuario: dict = Depends(require_perm("mod.estrategia")),
) -> dict[str, Any]:
    try:
        with get_connection() as conn:
            return estrategia_service.crear_riesgo(
                conn,
                nombre=body.nombre,
                probabilidad=body.probabilidad,
                impacto=body.impacto,
                descripcion=body.descripcion,
                mitigacion=body.mitigacion,
                id_objetivo=body.id_objetivo,
                id_usuario_actor=usuario.get("id_usuario"),
            )
    except ValueError as exc:
        raise _error(exc) from exc


@router.put("/riesgos/{id_riesgo}", summary="Actualizar riesgo")
def actualizar_riesgo(
    id_riesgo: int,
    body: RiesgoUpdate,
    usuario: dict = Depends(require_perm("mod.estrategia")),
) -> dict[str, Any]:
    try:
        with get_connection() as conn:
            return estrategia_service.actualizar_riesgo(
                conn, id_riesgo=id_riesgo, **body.model_dump(exclude_unset=True),
                id_usuario_actor=usuario.get("id_usuario"),
            )
    except ValueError as exc:
        raise _error(exc) from exc


@router.delete("/riesgos/{id_riesgo}", summary="Eliminar riesgo")
def eliminar_riesgo(
    id_riesgo: int,
    usuario: dict = Depends(require_perm("mod.estrategia")),
) -> dict[str, str]:
    try:
        with get_connection() as conn:
            estrategia_service.eliminar_riesgo(
                conn, id_riesgo=id_riesgo, id_usuario_actor=usuario.get("id_usuario"),
            )
    except ValueError as exc:
        raise _error(exc) from exc
    return {"ok": "true"}


# --- Informe integral con IA ---------------------------------------------------

@router.get("/panel-analitico", summary="Datos para gráficos (ClickHouse / DuckDB)")
def panel_analitico(
    _: dict = Depends(require_perm("mod.estrategia")),
) -> dict[str, Any]:
    with get_connection() as conn:
        return estrategia_service.panel_analitico(conn)


@router.get("/informe-ia", summary="Informe estratégico/táctico/operativo con IA")
def informe_ia(
    nivel: str = Query("estrategico", pattern="^(operativo|tactico|estrategico)$"),
    _: dict = Depends(require_perm("mod.estrategia")),
) -> dict[str, Any]:
    with get_connection() as conn:
        resultado = estrategia_service.generar_informe_ia(conn, nivel=nivel)
    if resultado["estado"] == "error":
        raise HTTPException(status_code=502, detail=resultado.get("detalle") or "Error del proveedor IA.")
    return resultado