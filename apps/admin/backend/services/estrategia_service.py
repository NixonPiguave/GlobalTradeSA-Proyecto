"""
estrategia_service.py — Módulo de estrategia: cuadro de mando (objetivos/OKR),
análisis de expansión de mercado, proyección de ventas y matriz de riesgos.

Todos los cálculos se derivan en vivo de fact_ventas (no se inventan cifras).
"""

from __future__ import annotations

import json
import logging
from datetime import date, datetime
from pathlib import Path
from typing import Any, Optional

import duckdb
import numpy as np

from backend.services.auditoria_service import registrar_auditoria
from shared.database.connection import table_exists
from shared.pdf.generator import generar_pdf_desde_plantilla
from backend.services import ia_service

logger = logging.getLogger(__name__)

TIPOS_METRICA = ("ingresos", "profit", "margen_pct", "unidades", "paises", "clientes")


def _ahora() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _next_id(conn: duckdb.DuckDBPyConnection, tabla: str, columna: str) -> int:
    row = conn.execute(
        f"SELECT COALESCE(MAX({columna}), 0) + 1 FROM {tabla}"
    ).fetchone()
    return int(row[0])


# --------------------------------------------------------------------------
# Cuadro de mando: objetivos con avance automático
# --------------------------------------------------------------------------

def _valor_metrica(conn: duckdb.DuckDBPyConnection, tipo: str) -> float:
    """Valor actual de una métrica estratégica calculada desde fact_ventas."""
    q = {
        "ingresos": "SELECT COALESCE(SUM(total_revenue), 0) FROM fact_ventas",
        "profit": "SELECT COALESCE(SUM(total_profit), 0) FROM fact_ventas",
        "margen_pct": (
            "SELECT COALESCE(SUM(total_profit), 0) / NULLIF(SUM(total_revenue), 0) * 100 "
            "FROM fact_ventas"
        ),
        "unidades": "SELECT COALESCE(SUM(units_sold), 0) FROM fact_ventas",
        "paises": "SELECT COUNT(DISTINCT id_country) FROM fact_ventas",
        "clientes": "SELECT COUNT(*) FROM dim_cliente",
    }
    if tipo not in q:
        return 0.0
    row = conn.execute(q[tipo]).fetchone()
    return float(row[0]) if row and row[0] is not None else 0.0


def _estado_objetivo(avance_pct: float) -> str:
    if avance_pct >= 100:
        return "cumplido"
    if avance_pct >= 60:
        return "en_curso"
    return "en_riesgo"


def listar_objetivos(
    conn: duckdb.DuckDBPyConnection,
    *,
    incluir_inactivos: bool = False,
) -> list[dict[str, Any]]:
    sql = "SELECT id_objetivo, nombre, descripcion, tipo_metrica, meta_numerica, periodo, orden, activo FROM objetivos_estrategicos"
    if not incluir_inactivos:
        sql += " WHERE activo = true"
    sql += " ORDER BY orden, id_objetivo"
    filas = conn.execute(sql).fetchall()
    resultado: list[dict[str, Any]] = []
    for f in filas:
        valor = _valor_metrica(conn, f[3])
        meta = float(f[4] or 0)
        avance = round(valor / meta * 100, 1) if meta > 0 else 0.0
        resultado.append({
            "id_objetivo": int(f[0]),
            "nombre": f[1],
            "descripcion": f[2],
            "tipo_metrica": f[3],
            "meta_numerica": meta,
            "valor_actual": round(valor, 2),
            "avance_pct": avance,
            "estado": _estado_objetivo(avance),
            "periodo": f[5],
            "orden": int(f[6] or 0),
            "activo": bool(f[7]),
        })
    return resultado


def crear_objetivo(
    conn: duckdb.DuckDBPyConnection,
    *,
    nombre: str,
    tipo_metrica: str,
    meta_numerica: float,
    descripcion: str = "",
    periodo: str = "",
    orden: int = 0,
    id_usuario_actor: Any = None,
) -> dict[str, Any]:
    if tipo_metrica not in TIPOS_METRICA:
        raise ValueError(f"Tipo de métrica inválido: {tipo_metrica}")
    if meta_numerica <= 0:
        raise ValueError("La meta debe ser un número positivo.")
    if not nombre.strip():
        raise ValueError("El nombre del objetivo es obligatorio.")
    nxt = _next_id(conn, "objetivos_estrategicos", "id_objetivo")
    conn.execute(
        """
        INSERT INTO objetivos_estrategicos
          (id_objetivo, nombre, descripcion, tipo_metrica, meta_numerica, periodo, orden, activo)
        VALUES (?, ?, ?, ?, ?, ?, ?, true)
        """,
        [nxt, nombre.strip(), descripcion, tipo_metrica, float(meta_numerica), periodo, int(orden)],
    )
    registrar_auditoria(
        conn, id_usuario=id_usuario_actor, entidad="objetivo", entidad_id=nxt,
        accion="crear", valor_nuevo={"nombre": nombre, "tipo_metrica": tipo_metrica, "meta": meta_numerica},
    )
    return {"id_objetivo": nxt, "nombre": nombre, "tipo_metrica": tipo_metrica}


def actualizar_objetivo(
    conn: duckdb.DuckDBPyConnection,
    *,
    id_objetivo: int,
    nombre: Optional[str] = None,
    descripcion: Optional[str] = None,
    tipo_metrica: Optional[str] = None,
    meta_numerica: Optional[float] = None,
    periodo: Optional[str] = None,
    orden: Optional[int] = None,
    activo: Optional[bool] = None,
    id_usuario_actor: Any = None,
) -> dict[str, Any]:
    fila = conn.execute(
        "SELECT id_objetivo FROM objetivos_estrategicos WHERE id_objetivo = ?", [id_objetivo]
    ).fetchone()
    if not fila:
        raise ValueError(f"Objetivo {id_objetivo} no encontrado.")
    if tipo_metrica is not None and tipo_metrica not in TIPOS_METRICA:
        raise ValueError(f"Tipo de métrica inválido: {tipo_metrica}")
    sets, params = [], []
    for col, val in [
        ("nombre", nombre), ("descripcion", descripcion), ("tipo_metrica", tipo_metrica),
        ("meta_numerica", meta_numerica), ("periodo", periodo), ("orden", orden), ("activo", activo),
    ]:
        if val is not None:
            sets.append(f"{col} = ?")
            params.append(val)
    if sets:
        conn.execute(
            f"UPDATE objetivos_estrategicos SET {', '.join(sets)} WHERE id_objetivo = ?",
            [*params, id_objetivo],
        )
    registrar_auditoria(
        conn, id_usuario=id_usuario_actor, entidad="objetivo", entidad_id=id_objetivo,
        accion="actualizar", valor_nuevo={"nombre": nombre, "tipo_metrica": tipo_metrica, "meta": meta_numerica},
    )
    return {"id_objetivo": id_objetivo}


def eliminar_objetivo(
    conn: duckdb.DuckDBPyConnection,
    *,
    id_objetivo: int,
    id_usuario_actor: Any = None,
) -> None:
    fila = conn.execute(
        "SELECT id_objetivo FROM objetivos_estrategicos WHERE id_objetivo = ?", [id_objetivo]
    ).fetchone()
    if not fila:
        raise ValueError(f"Objetivo {id_objetivo} no encontrado.")
    conn.execute("DELETE FROM objetivos_estrategicos WHERE id_objetivo = ?", [id_objetivo])
    registrar_auditoria(
        conn, id_usuario=id_usuario_actor, entidad="objetivo", entidad_id=id_objetivo,
        accion="eliminar", valor_anterior={"id_objetivo": id_objetivo},
    )


# --------------------------------------------------------------------------
# Análisis de expansión de mercado
# --------------------------------------------------------------------------

def analisis_expansion(conn: duckdb.DuckDBPyConnection) -> dict[str, Any]:
    """Ranking de países por atractivo (ingresos, margen, crecimiento) y
    riesgo de concentración del portafolio."""
    filas = conn.execute(
        """
        SELECT c.id_country, c.country,
               SUM(f.total_revenue) AS ingresos,
               SUM(f.total_profit) AS profit,
               COUNT(*) AS lineas
        FROM fact_ventas f
        JOIN dim_country c ON c.id_country = f.id_country
        GROUP BY c.id_country, c.country
        ORDER BY ingresos DESC
        LIMIT 25
        """
    ).fetchall()

    # Crecimiento: último trimestre vs trimestre anterior
    t_anterior = conn.execute(
        """
        SELECT SUM(total_revenue)
        FROM fact_ventas
        WHERE order_date >= (SELECT MAX(order_date) FROM fact_ventas) - INTERVAL 6 MONTH
          AND order_date <  (SELECT MAX(order_date) FROM fact_ventas) - INTERVAL 3 MONTH
        """
    ).fetchone()[0]
    t_ultimo = conn.execute(
        """
        SELECT SUM(total_revenue)
        FROM fact_ventas
        WHERE order_date >= (SELECT MAX(order_date) FROM fact_ventas) - INTERVAL 3 MONTH
        """
    ).fetchone()[0]
    crecimiento_global = (
        (float(t_ultimo) / float(t_anterior) - 1) * 100
        if t_anterior and float(t_anterior) > 0 else 0.0
    )

    total_ingresos = float(conn.execute("SELECT SUM(total_revenue) FROM fact_ventas").fetchone()[0]) or 1.0

    paises: list[dict[str, Any]] = []
    for f in filas:
        ingresos = float(f[2])
        profit = float(f[3])
        margen = profit / ingresos * 100 if ingresos > 0 else 0.0
        paises.append({
            "id_country": int(f[0]),
            "pais": f[1],
            "ingresos": round(ingresos, 2),
            "profit": round(profit, 2),
            "margen_pct": round(margen, 2),
            "participacion_pct": round(ingresos / total_ingresos * 100, 3),
            "lineas": int(f[4]),
        })

    # Score de atractivo: ingresos (50%) + margen (30%) + participación (20%), normalizado
    max_ing = max((p["ingresos"] for p in paises), default=1) or 1
    max_mar = max((p["margen_pct"] for p in paises), default=1) or 1
    for p in paises:
        p["score"] = round(
            (p["ingresos"] / max_ing) * 50
            + (p["margen_pct"] / max_mar) * 30
            + (p["participacion_pct"] / 100) * 20,
            1,
        )
    paises.sort(key=lambda p: p["score"], reverse=True)

    # Concentración del portafolio
    top_paises = conn.execute(
        """
        SELECT c.country, SUM(f.total_revenue) AS ingresos
        FROM fact_ventas f JOIN dim_country c ON c.id_country = f.id_country
        GROUP BY c.country ORDER BY ingresos DESC LIMIT 5
        """
    ).fetchall()
    concentracion_paises = [
        {
            "pais": r[0],
            "ingresos": round(float(r[1]), 2),
            "participacion_pct": round(float(r[1]) / total_ingresos * 100, 2),
        }
        for r in top_paises
    ]
    top_productos = conn.execute(
        """
        SELECT it.item_type, SUM(f.total_revenue) AS ingresos
        FROM fact_ventas f JOIN dim_item_type it ON it.id_item_type = f.id_item_type
        GROUP BY it.item_type ORDER BY ingresos DESC LIMIT 5
        """
    ).fetchall()
    concentracion_productos = [
        {
            "tipo": r[0],
            "ingresos": round(float(r[1]), 2),
            "participacion_pct": round(float(r[1]) / total_ingresos * 100, 2),
        }
        for r in top_productos
    ]

    recomendados = [
        {
            "pais": p["pais"],
            "score": p["score"],
            "margen_pct": p["margen_pct"],
            "participacion_pct": p["participacion_pct"],
            "razon": (
                "Mayor generación de ingresos del portafolio"
                if i == 0
                else ("Margen superior al promedio con base sólida de ingresos"
                      if p["margen_pct"] >= 30
                      else "Participación relevante con margen rentable")
            ),
        }
        for i, p in enumerate(paises[:3])
    ]

    return {
        "paises": paises,
        "recomendados": recomendados,
        "crecimiento_global_pct": round(crecimiento_global, 2),
        "concentracion_paises": concentracion_paises,
        "concentracion_productos": concentracion_productos,
        "total_paises": int(conn.execute("SELECT COUNT(DISTINCT id_country) FROM fact_ventas").fetchone()[0]),
        "generado": _ahora(),
    }


# --------------------------------------------------------------------------
# Proyección de ventas (regresión lineal)
# --------------------------------------------------------------------------

def _mes_siguiente(mes: str) -> str:
    anio, mes_num = int(mes[:4]), int(mes[5:7])
    mes_num += 1
    if mes_num > 12:
        mes_num = 1
        anio += 1
    return f"{anio:04d}-{mes_num:02d}"


def _segmentos_consecutivos_mes(filas: list[tuple]) -> list[list[tuple]]:
    """Agrupa meses sin huecos mayores a un mes entre puntos."""
    if not filas:
        return []
    segmentos: list[list[tuple]] = [[filas[0]]]
    for i in range(1, len(filas)):
        prev_mes, cur_mes = filas[i - 1][0], filas[i][0]
        if cur_mes != _mes_siguiente(prev_mes):
            segmentos.append([filas[i]])
        else:
            segmentos[-1].append(filas[i])
    return segmentos


def _serie_mensual_para_proyeccion(
    conn: duckdb.DuckDBPyConnection,
    ventana_meses: int,
    *,
    min_meses: int = 6,
) -> list[tuple[str, float]]:
    """Serie mensual del tramo histórico más denso (ignora meses sueltos recientes)."""
    todas = conn.execute(
        """
        SELECT strftime(order_date, '%Y-%m') AS mes,
               SUM(CAST(total_revenue AS DOUBLE)) AS ingresos
        FROM fact_ventas
        GROUP BY 1
        ORDER BY 1
        """
    ).fetchall()
    if not todas:
        return []

    segmentos = _segmentos_consecutivos_mes(todas)
    principal = max(segmentos, key=len)
    ventana = max(ventana_meses, min_meses)
    if len(principal) >= min_meses:
        recorte = principal[-ventana:] if len(principal) > ventana else principal
        return [(str(r[0]), float(r[1])) for r in recorte]

    plano = [(str(r[0]), float(r[1])) for r in todas]
    return plano[-ventana:] if len(plano) > ventana else plano


def proyeccion_ventas(
    conn: duckdb.DuckDBPyConnection,
    *,
    meses: int = 12,
    ventana_meses: int = 36,
) -> dict[str, Any]:
    """Serie mensual reciente + proyección lineal de los próximos `meses` meses.

    Usa el tramo consecutivo con más meses de ventas (p. ej. histórico 2010–2017),
    no la ventana calendario desde MAX(order_date), que falla si solo hay pedidos
    recientes del portal mezclados con un parquet antiguo.
    """
    min_meses = 6
    filas = _serie_mensual_para_proyeccion(conn, ventana_meses, min_meses=min_meses)
    if len(filas) < min_meses:
        raise ValueError(
            f"No hay suficientes meses de datos para proyectar (se requieren al menos {min_meses}; "
            f"hay {len(filas)})."
        )

    meses_reales = [r[0] for r in filas]
    valores = np.array([r[1] for r in filas], dtype=float)
    x = np.arange(len(valores), dtype=float)
    pendiente, intercepto = np.polyfit(x, valores, 1)

    n = len(valores)
    proyectados = [max(0.0, float(pendiente * (n + i) + intercepto)) for i in range(1, meses + 1)]

    ventana_hist = min(meses, n, 12)
    ultimo_anio = float(valores[-min(12, n):].sum())
    anio_proyectado = float(sum(proyectados[-12:]))
    crecimiento_anual = (anio_proyectado / ultimo_anio - 1) * 100 if ultimo_anio > 0 else 0.0

    historial_meses = min(meses, n)
    serie_real = [
        {"mes": m, "tipo": "real", "ingresos": round(float(v), 2)}
        for m, v in zip(meses_reales[-historial_meses:], valores[-historial_meses:])
    ]

    cursor = meses_reales[-1]
    prox_mes: list[str] = []
    for _ in range(meses):
        cursor = _mes_siguiente(cursor)
        prox_mes.append(cursor)

    serie_proy = [
        {"mes": m, "tipo": "proyectado", "ingresos": round(v, 2)}
        for m, v in zip(prox_mes, proyectados)
    ]
    serie = serie_real + serie_proy

    return {
        "serie": serie,
        "pendiente_mensual": round(float(pendiente), 2),
        "ingresos_ultimo_anio": round(ultimo_anio, 2),
        "ingresos_proyectados_anio": round(anio_proyectado, 2),
        "crecimiento_anual_pct": round(crecimiento_anual, 2),
        "meses_analizados": n,
        "ventana_meses": len(filas),
        "meses_proyectados": meses,
        "tramo_desde": meses_reales[0],
        "tramo_hasta": meses_reales[-1],
        "generado": _ahora(),
    }


def pdf_proyeccion(conn: duckdb.DuckDBPyConnection, datos: dict[str, Any]) -> bytes:
    """PDF del informe de proyección (misma plantilla de reportes)."""
    from backend.services.reporte_service import _ctx_reporte, _render_pdf

    headers = ["Mes", "Tipo", "Ingresos (USD)"]
    rows = [[s["mes"], s["tipo"], f"{s['ingresos']:,.2f}"] for s in datos["serie"]]
    ctx = _ctx_reporte(
        conn,
        "Proyección de Ventas — Informe Estratégico",
        f"Crecimiento anual proyectado: {datos['crecimiento_anual_pct']:.2f}% · Generado: {datos['generado']}",
        headers=headers,
        rows=rows,
        totales="",
        kpis=[
            {"label": "Ingresos último año", "value": f"${datos['ingresos_ultimo_anio']:,.2f}"},
            {"label": "Proyección próximos 12 meses", "value": f"${datos['ingresos_proyectados_anio']:,.2f}"},
            {"label": "Crecimiento anual", "value": f"{datos['crecimiento_anual_pct']:.2f}%"},
            {"label": "Meses analizados", "value": str(datos["meses_analizados"])},
        ],
    )
    return _render_pdf(ctx)


# --------------------------------------------------------------------------
# Matriz de riesgos estratégicos
# --------------------------------------------------------------------------

def _nivel_riesgo(probabilidad: int, impacto: int) -> str:
    score = probabilidad * impacto
    if score >= 16:
        return "critico"
    if score >= 9:
        return "alto"
    if score >= 4:
        return "medio"
    return "bajo"


def listar_riesgos(conn: duckdb.DuckDBPyConnection) -> list[dict[str, Any]]:
    filas = conn.execute(
        """
        SELECT r.id_riesgo, r.nombre, r.descripcion, r.probabilidad, r.impacto,
               r.mitigacion, r.id_objetivo, r.estado, o.nombre AS objetivo_nombre
        FROM riesgos_estrategicos r
        LEFT JOIN objetivos_estrategicos o ON o.id_objetivo = r.id_objetivo
        ORDER BY r.probabilidad * r.impacto DESC, r.id_riesgo
        """
    ).fetchall()
    return [
        {
            "id_riesgo": int(f[0]),
            "nombre": f[1],
            "descripcion": f[2],
            "probabilidad": int(f[3]),
            "impacto": int(f[4]),
            "nivel": _nivel_riesgo(int(f[3]), int(f[4])),
            "mitigacion": f[5],
            "id_objetivo": int(f[6]) if f[6] is not None else None,
            "objetivo_nombre": f[8],
            "estado": f[7],
        }
        for f in filas
    ]


def crear_riesgo(
    conn: duckdb.DuckDBPyConnection,
    *,
    nombre: str,
    probabilidad: int,
    impacto: int,
    descripcion: str = "",
    mitigacion: str = "",
    id_objetivo: Optional[int] = None,
    id_usuario_actor: Any = None,
) -> dict[str, Any]:
    if not (1 <= probabilidad <= 5 and 1 <= impacto <= 5):
        raise ValueError("Probabilidad e impacto deben estar entre 1 y 5.")
    if not nombre.strip():
        raise ValueError("El nombre del riesgo es obligatorio.")
    nxt = _next_id(conn, "riesgos_estrategicos", "id_riesgo")
    conn.execute(
        """
        INSERT INTO riesgos_estrategicos
          (id_riesgo, nombre, descripcion, probabilidad, impacto, mitigacion, id_objetivo, estado)
        VALUES (?, ?, ?, ?, ?, ?, ?, 'activo')
        """,
        [nxt, nombre.strip(), descripcion, int(probabilidad), int(impacto), mitigacion, id_objetivo],
    )
    registrar_auditoria(
        conn, id_usuario=id_usuario_actor, entidad="riesgo", entidad_id=nxt,
        accion="crear", valor_nuevo={"nombre": nombre, "probabilidad": probabilidad, "impacto": impacto},
    )
    return {"id_riesgo": nxt, "nombre": nombre, "nivel": _nivel_riesgo(int(probabilidad), int(impacto))}


def actualizar_riesgo(
    conn: duckdb.DuckDBPyConnection,
    *,
    id_riesgo: int,
    nombre: Optional[str] = None,
    descripcion: Optional[str] = None,
    probabilidad: Optional[int] = None,
    impacto: Optional[int] = None,
    mitigacion: Optional[str] = None,
    id_objetivo: Optional[int] = None,
    estado: Optional[str] = None,
    id_usuario_actor: Any = None,
) -> dict[str, Any]:
    fila = conn.execute(
        "SELECT id_riesgo FROM riesgos_estrategicos WHERE id_riesgo = ?", [id_riesgo]
    ).fetchone()
    if not fila:
        raise ValueError(f"Riesgo {id_riesgo} no encontrado.")
    if (probabilidad is not None and not 1 <= probabilidad <= 5) or (impacto is not None and not 1 <= impacto <= 5):
        raise ValueError("Probabilidad e impacto deben estar entre 1 y 5.")
    sets, params = [], []
    for col, val in [
        ("nombre", nombre), ("descripcion", descripcion), ("probabilidad", probabilidad),
        ("impacto", impacto), ("mitigacion", mitigacion), ("id_objetivo", id_objetivo),
        ("estado", estado),
    ]:
        if val is not None:
            sets.append(f"{col} = ?")
            params.append(val)
    if sets:
        conn.execute(
            f"UPDATE riesgos_estrategicos SET {', '.join(sets)} WHERE id_riesgo = ?",
            [*params, id_riesgo],
        )
    registrar_auditoria(
        conn, id_usuario=id_usuario_actor, entidad="riesgo", entidad_id=id_riesgo,
        accion="actualizar", valor_nuevo={"nombre": nombre, "probabilidad": probabilidad, "impacto": impacto},
    )
    return {"id_riesgo": id_riesgo}


def eliminar_riesgo(
    conn: duckdb.DuckDBPyConnection,
    *,
    id_riesgo: int,
    id_usuario_actor: Any = None,
) -> None:
    fila = conn.execute(
        "SELECT id_riesgo FROM riesgos_estrategicos WHERE id_riesgo = ?", [id_riesgo]
    ).fetchone()
    if not fila:
        raise ValueError(f"Riesgo {id_riesgo} no encontrado.")
    conn.execute("DELETE FROM riesgos_estrategicos WHERE id_riesgo = ?", [id_riesgo])
    registrar_auditoria(
        conn, id_usuario=id_usuario_actor, entidad="riesgo", entidad_id=id_riesgo,
        accion="eliminar", valor_anterior={"id_riesgo": id_riesgo},
    )


# --------------------------------------------------------------------------
# Informe estratégico integral con IA
# --------------------------------------------------------------------------

def datos_informe_estrategico(conn: duckdb.DuckDBPyConnection) -> dict[str, Any]:
    """Consolida todos los módulos estratégicos en un payload para la IA."""
    kpis = {
        "ingresos": _valor_metrica(conn, "ingresos"),
        "profit": _valor_metrica(conn, "profit"),
        "margen_pct": round(_valor_metrica(conn, "margen_pct"), 2),
        "unidades": _valor_metrica(conn, "unidades"),
        "paises": int(_valor_metrica(conn, "paises")),
        "clientes": int(_valor_metrica(conn, "clientes")),
    }
    try:
        expansion = analisis_expansion(conn)
    except Exception:  # noqa: BLE001
        expansion = {"recomendados": [], "concentracion_paises": [], "concentracion_productos": []}
    try:
        proyeccion = proyeccion_ventas(conn, meses=12)
    except Exception:  # noqa: BLE001
        proyeccion = {"crecimiento_anual_pct": 0.0, "ingresos_proyectados_anio": 0.0}
    return {
        "kpis": kpis,
        "objetivos": listar_objetivos(conn),
        "riesgos": listar_riesgos(conn),
        "expansion": {
            "recomendados": expansion.get("recomendados", []),
            "concentracion_paises": expansion.get("concentracion_paises", []),
            "concentracion_productos": expansion.get("concentracion_productos", []),
            "crecimiento_global_pct": expansion.get("crecimiento_global_pct", 0.0),
        },
        "proyeccion": {
            "crecimiento_anual_pct": proyeccion.get("crecimiento_anual_pct", 0.0),
            "ingresos_ultimo_anio": proyeccion.get("ingresos_ultimo_anio", 0.0),
            "ingresos_proyectados_anio": proyeccion.get("ingresos_proyectados_anio", 0.0),
        },
        "generado": _ahora(),
    }


def generar_informe_ia(
    conn: duckdb.DuckDBPyConnection,
    *,
    nivel: str = "estrategico",
) -> dict[str, Any]:
    """Informe estratégico/táctico/operativo consolidado vía IA."""
    cfg = ia_service._config(conn)
    if not cfg["api_key"]:
        return {
            "estado": "sin_configurar",
            "modelo": cfg["modelo"],
            "texto": "",
            "detalle": "El analizador IA no está configurado: falta IA_API_KEY en el entorno.",
        }
    nivel_n = (nivel or "estrategico").strip().lower()
    if nivel_n not in ("operativo", "tactico", "estrategico"):
        nivel_n = "estrategico"
    datos = datos_informe_estrategico(conn)
    prompts = {
        "estrategico": (
            "Eres el director de estrategia de GLOBTRADE S.A., empresa de comercio internacional "
            "con distribución B2B. Genera el INFORME ESTRATÉGICO INTEGRAL en español, tono ejecutivo, "
            "basándote EXCLUSIVAMENTE en el JSON que recibes. Estructura con 6 secciones:\n"
            "- Resumen ejecutivo: posición actual con cifras exactas.\n"
            "- Cuadro de mando: estado de los objetivos (avance %) y cuáles requieren atención.\n"
            "- Oportunidades de mercado: mercados recomendados y razones (cifras exactas).\n"
            "- Proyección: tendencia de ingresos y crecimiento proyectado.\n"
            "- Riesgos estratégicos: riesgos por nivel (crítico/alto/medio) y mitigaciones.\n"
            "- Decisiones recomendadas: 3 a 5 decisiones concretas de inversión, expansión o portafolio.\n"
            "Máximo 350 palabras. No inventes cifras. "
            "Formato: usa encabezados markdown ### con el nombre exacto de cada sección; "
            "viñetas con - ; negritas con **solo para cifras clave**; "
            "NO uses tablas markdown ni reglas --- ni portada con título/fecha."
        ),
        "tactico": (
            "Eres un analista táctico senior de GLOBTRADE S.A. Redacta un INFORME TÁCTICO en español "
            "basándote EXCLUSIVAMENTE en el JSON. Estructura con 5 secciones:\n"
            "- Panorama del período: cifras clave de ingresos, margen y avance de OKR.\n"
            "- Prioridades del trimestre: 3 a 5 focos accionables con métricas.\n"
            "- Mercados a impulsar: oportunidades con score/margen exactos.\n"
            "- Riesgos a vigilar: riesgos altos/críticos y mitigación.\n"
            "- Plan de 90 días: acciones concretas y medibles.\n"
            "Máximo 280 palabras. No inventes cifras. "
            "Formato: encabezados ### con el nombre exacto de sección; viñetas - ; "
            "sin tablas markdown ni portada."
        ),
        "operativo": (
            "Eres el jefe de operaciones de GLOBTRADE S.A. Redacta un INFORME OPERATIVO breve en español "
            "basándote EXCLUSIVAMENTE en el JSON. Estructura con 4 secciones:\n"
            "- Estado operativo: KPIs y objetivos en riesgo.\n"
            "- Alertas: señales que requieren acción inmediata.\n"
            "- Desempeño por mercado/categoría: concentración y focos.\n"
            "- Acciones de la semana: 3 a 5 pasos concretos.\n"
            "Máximo 220 palabras. No inventes cifras. "
            "Formato: encabezados ### con el nombre exacto de sección; viñetas - ; "
            "sin tablas markdown ni portada."
        ),
    }
    sistema = prompts[nivel_n]
    prompt_usuario = (
        f"Nivel de análisis: {nivel_n}.\n"
        "Datos del sistema estratégico de GLOBTRADE S.A. (JSON):\n"
        + json.dumps(datos, ensure_ascii=False, indent=1)
    )
    try:
        res = ia_service._llamar_robusto(cfg, {
            "sistema": sistema,
            "usuario": prompt_usuario,
        })
        contenido = ia_service.limpiar_salida_ia(res["choices"][0]["message"]["content"])
        return {
            "estado": "ok",
            "modelo": res.get("model", cfg["modelo"]),
            "nivel": nivel_n,
            "nivel_label": {"operativo": "Operativo", "tactico": "Táctico", "estrategico": "Estratégico"}[nivel_n],
            "texto": contenido,
            "tokens": res.get("usage", {}).get("total_tokens"),
            "kpis": [
                {"label": "Ingresos", "value": datos["kpis"].get("ingresos")},
                {"label": "Margen %", "value": datos["kpis"].get("margen_pct")},
                {"label": "Países", "value": datos["kpis"].get("paises")},
                {"label": "Clientes", "value": datos["kpis"].get("clientes")},
            ],
        }
    except Exception as e:  # noqa: BLE001
        return {
            "estado": "error",
            "modelo": cfg["modelo"],
            "texto": "",
            "detalle": str(e)[:500],
        }


def panel_analitico(conn: duckdb.DuckDBPyConnection) -> dict[str, Any]:
    """Datos para gráficos del módulo Estrategia (ClickHouse con fallback DuckDB)."""
    from backend.services import analytics_service

    motor = "DuckDB"
    paises: list[dict[str, Any]] = []
    lineas: list[dict[str, Any]] = []
    try:
        vp = analytics_service.consultar_vista(conn, "ventas-por-pais", limite=12)
        paises = vp.get("items") or []
        motor = vp.get("motor") or motor
    except Exception:  # noqa: BLE001
        pass
    try:
        vl = analytics_service.consultar_vista(conn, "ventas-por-linea", limite=10)
        lineas = vl.get("items") or []
        if vl.get("motor"):
            motor = vl["motor"]
    except Exception:  # noqa: BLE001
        pass

    try:
        from shared.services.clickhouse_service import clickhouse_disponible, estado_almacen
        ch = estado_almacen() if clickhouse_disponible() else {"disponible": False}
    except Exception:  # noqa: BLE001
        ch = {"disponible": False}

    return {
        "motor": motor,
        "clickhouse": ch,
        "ventas_por_pais": paises,
        "ventas_por_linea": lineas,
    }