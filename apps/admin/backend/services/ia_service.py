"""
ia_service.py — Análisis ejecutivo con IA (proveedor OpenAI-compatible).

Usa la misma consulta de datos de los reportes (reporte_service.obtener_reporte_vista)
y envía SOLO data agregada (KPIs y filas) al proveedor para obtener un resumen
ejecutivo. No se exponen datos crudos por cliente ni SQL.

Admite un nivel de análisis (`nivel`): operativo, tactico o estrategico, cada uno
con un encuadre distinto para el modelo. Además calcula localmente estadísticas
(promedios, máximos) que se pasan al modelo para que no invente cifras.

Configuración (entorno): IA_API_KEY, IA_BASE_URL, IA_MODEL.
"""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from typing import Any, Optional

from backend.services import reporte_service
from backend.config import get_settings


def limpiar_salida_ia(texto: str) -> str:
    """Quita cadenas de razonamiento interno y basura de modelos (think, etc.)."""
    t = str(texto or "")
    if not t.strip():
        return ""
    # Bloques cerrados de thinking / reasoning
    for tag in ("think", "thinking", "reasoning", "redacted_thinking", "reflection"):
        t = re.sub(rf"<{tag}\b[^>]*>[\s\S]*?</{tag}>", "", t, flags=re.IGNORECASE)
    # Think abierto sin cierre: cortar hasta el primer heading o sección útil
    t = re.sub(
        r"<think\b[^>]*>[\s\S]*?(?=(?:\n#{1,4}\s|\n\*\*[A-ZÁÉÍÓÚ]|Resumen|Panorama|###))",
        "",
        t,
        flags=re.IGNORECASE,
    )
    t = re.sub(r"</?think\b[^>]*>", "", t, flags=re.IGNORECASE)
    # Volcados de instrucciones del modelo (roleplay interno)
    if re.search(r"(?i)analyze user input|role:\s*|max\s*\d+\s*words|do not invent", t):
        partes = re.split(
            r"(?=\n#{1,4}\s|\n\*\*(?:Resumen|Panorama|Estado|Prioridades|Mercados|Riesgos|Decisiones|Alertas|Acciones))",
            t,
        )
        utiles = [p for p in partes if re.search(
            r"(?i)resumen|panorama|cuadro|oportunidad|proyec|riesgo|decisi|priorid|mercado|alerta|acci[oó]n|estado operativo",
            p,
        )]
        if utiles:
            t = "\n".join(utiles)
    return t.strip()

NIVELES = {
    "operativo": {
        "nombre": "Operativo",
        "sistema": (
            "Eres el jefe de operaciones de GLOBTRADE S.A., empresa de comercio "
            "internacional con distribución B2B. Redacta un análisis OPERATIVO breve en "
            "español, tono directo y ejecutable, basándote EXCLUSIVAMENTE en los datos que recibes. "
            "Estructura el texto con 4 secciones:\n"
            "- Resumen: panorama de la operación del período.\n"
            "- Ejecución: 2 a 4 datos destacados de pedidos, stock, despachos o ventas con cifras exactas.\n"
            "- Alertas operativas: 1 a 3 señales que requieren acción inmediata (desabastecimiento, picos, caídas).\n"
            "- Acciones inmediatas: 2 a 4 pasos concretos y medibles para el día a día.\n"
            "Máximo 160 palabras. No inventes cifras. Si una sección no aplica, dilo breve y honesto. "
            "Responde SOLO el informe final. Prohibido mostrar razonamiento interno, "
            "etiquetas <think>, listas de instrucciones o análisis del prompt."
        ),
    },
    "tactico": {
        "nombre": "Táctico",
        "sistema": (
            "Eres un analista ejecutivo senior de GLOBTRADE S.A., empresa de comercio "
            "internacional con distribución B2B. Redacta un análisis TÁCTICO breve en "
            "español, con tono directo, basándote EXCLUSIVAMENTE en los datos que recibes. "
            "Estructura el texto con 4 secciones:\n"
            "- Resumen: panorama general del período.\n"
            "- Hallazgos: 2 a 4 datos destacados (rentabilidad, tendencias, comparativas) con las cifras exactas.\n"
            "- Riesgos: 1 a 3 señales de alerta si los datos lo sugieren.\n"
            "- Recomendaciones: 2 a 4 acciones concretas de negocio a mediano plazo.\n"
            "Máximo 160 palabras. No inventes cifras ni datos que no estén en el JSON. "
            "Si una sección no aplica, dilo de forma breve y honesta. "
            "Responde SOLO el informe final. Prohibido mostrar razonamiento interno o etiquetas <think>."
        ),
    },
    "estrategico": {
        "nombre": "Estratégico",
        "sistema": (
            "Eres el director de estrategia de GLOBTRADE S.A., empresa de comercio "
            "internacional con distribución B2B (clientes mayoristas como Walmart, Costco y "
            "Carrefour en 167 países). Redacta un análisis ESTRATÉGICO breve en español, "
            "con visión de largo plazo, basándote EXCLUSIVAMENTE en los datos que recibes. "
            "Estructura el texto con 4 secciones:\n"
            "- Panorama estratégico: contexto y posición del negocio en el período.\n"
            "- Oportunidades de mercado: 2 a 4 oportunidades detectadas (mercados, países, "
            "segmentos o canales) con las cifras exactas.\n"
            "- Riesgos estratégicos: 1 a 3 riesgos de fondo (concentración, dependencias, tendencias negativas).\n"
            "- Decisiones recomendadas: 2 a 4 decisiones de inversión, expansión o portafolio.\n"
            "Máximo 180 palabras. No inventes cifras. Si una sección no aplica, dilo breve y honesto. "
            "Responde SOLO el informe final. Prohibido mostrar razonamiento interno o etiquetas <think>."
        ),
    },
}


def _config(conn=None) -> dict[str, str]:
    s = get_settings()
    api_key = s.IA_API_KEY
    base_url = (s.IA_BASE_URL or "https://api.groq.com/openai/v1").rstrip("/")
    modelo = s.IA_MODEL or "llama-3.3-70b-versatile"
    fuente = "entorno" if api_key else "ninguna"
    if conn is not None:
        from shared.services.config_service import obtener_config

        db_key = obtener_config(conn, "IA_API_KEY", "").strip()
        db_url = obtener_config(conn, "IA_BASE_URL", "").strip()
        db_model = obtener_config(conn, "IA_MODEL", "").strip()
        if db_key:
            api_key = db_key
            fuente = "base_datos"
        elif api_key:
            fuente = "entorno"
        if db_url:
            base_url = db_url.rstrip("/")
        if db_model:
            modelo = db_model
    return {
        "api_key": api_key,
        "base_url": base_url,
        "modelo": modelo,
        "fuente": fuente,
    }


def _compactar(datos: dict[str, Any], max_filas: int = 12) -> dict[str, Any]:
    """Reduce el reporte a un payload JSON pequeño para el modelo."""
    fan_out = {
        "titulo": datos.get("titulo"),
        "subtitulo": datos.get("subtitulo"),
        "kpis": datos.get("kpis") or [],
        "totales": datos.get("totales") or "",
    }
    if datos.get("tipo") != "compuesto":
        fan_out["tabla"] = {
            "cabeceras": datos.get("headers") or [],
            "filas": [list(r) for r in (datos.get("rows") or [])[:max_filas]],
        }
        return fan_out
    fan_out["secciones"] = [
        {
            "titulo": s.get("titulo") or "Sección",
            "cabeceras": s.get("headers") or [],
            "filas": [list(r) for r in (s.get("rows") or [])[:max_filas]],
            "totales": s.get("totales") or "",
        }
        for s in (datos.get("secciones") or [])[:16]
    ]
    return fan_out


def _extraer_tablas(compacto: dict[str, Any]) -> list[dict[str, Any]]:
    """Devuelve las tablas (cabeceras + filas) presentes en el payload compacto."""
    tablas: list[dict[str, Any]] = []
    if "tabla" in compacto and compacto["tabla"].get("filas"):
        tablas.append(compacto["tabla"])
    for s in compacto.get("secciones") or []:
        if s.get("filas"):
            tablas.append(s)
    return tablas


def _estadisticas(compacto: dict[str, Any], max_filas: int = 5) -> dict[str, Any]:
    """Estadísticas calculadas localmente: promedios y máximos de las columnas
    numéricas de las tablas. Evita que el modelo invente cifras."""
    resumen: dict[str, Any] = {"tablas": [], "top": []}
    num = 0
    for t in _extraer_tablas(compacto):
        headers = [str(h) for h in (t.get("cabeceras") or [])]
        filas = [list(r) for r in (t.get("filas") or [])]
        if not headers or not filas:
            continue
        cols: list[dict[str, Any]] = []
        for i, h in enumerate(headers):
            valores: list[float] = []
            for f in filas:
                if i < len(f):
                    try:
                        v = float(str(f[i]).replace(",", "").replace("$", "").strip())
                        valores.append(v)
                    except (TypeError, ValueError):
                        pass
            if valores:
                cols.append({
                    "columna": h,
                    "max": round(max(valores), 2),
                    "min": round(min(valores), 2),
                    "promedio": round(sum(valores) / len(valores), 2),
                })
        num += len(filas)
        resumen["tablas"].append({
            "titulo": t.get("titulo") or "Tabla",
            "columnas": cols,
            "filas_analizadas": len(filas),
        })
    # Primeras filas destacadas del payload (ya ordenadas por el reporte)
    for t in _extraer_tablas(compacto)[:1]:
        headers = [str(h) for h in (t.get("cabeceras") or [])]
        for f in (t.get("filas") or [])[:max_filas]:
            resumen["top"].append(dict(zip(headers, [str(x) for x in f])))
    resumen["total_filas_analizadas"] = num
    return resumen


def _llamar(base: str, api_key: str, model: str, prompt: str, timeout: int = 120) -> dict[str, Any]:
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": prompt["sistema"]},
            {"role": "user", "content": prompt["usuario"]},
        ],
        "temperature": 0.3,
        "max_tokens": 1100,
    }
    req = urllib.request.Request(
        f"{base}/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"
            ),
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as respuesta:
        return json.loads(respuesta.read().decode("utf-8"))


def _candidatos_modelo(cfg: dict[str, Any]) -> list[str]:
    candidatos = [cfg.get("modelo") or "llama-3.3-70b-versatile"]
    try:
        disponibles = _listar_modelos(cfg["base_url"], cfg["api_key"])
        preferidos = [
            m
            for m in disponibles
            if any(x in m.lower() for x in ("llama", "gpt-oss", "qwen", "gemma", "mixtral"))
        ]
        candidatos.extend(preferidos[:6] or disponibles[:6])
    except Exception:
        candidatos.extend(["llama-3.3-70b-versatile", "llama-3.1-8b-instant", "gemma2-9b-it"])
    vistos: list[str] = []
    out: list[str] = []
    for m in candidatos:
        if m and m not in vistos:
            vistos.append(m)
            out.append(m)
    return out


def _llamar_robusto(cfg: dict[str, Any], prompt: dict[str, str], timeout: int = 120) -> dict[str, Any]:
    """Llama al proveedor IA; si el modelo da 404/400, prueba candidatos vivos."""
    ultimo_err = ""
    for modelo in _candidatos_modelo(cfg):
        try:
            res = _llamar(cfg["base_url"], cfg["api_key"], modelo, prompt, timeout=timeout)
            if not res.get("model"):
                res["model"] = modelo
            return res
        except urllib.error.HTTPError as e:
            detalle = e.read()[:300].decode("utf-8", errors="replace")
            ultimo_err = f"HTTP {e.code} del proveedor IA ({modelo}): {detalle}"
            if e.code not in (404, 400):
                raise RuntimeError(ultimo_err) from e
        except urllib.error.URLError as e:
            raise RuntimeError(f"No se pudo conectar con el proveedor IA: {e.reason}") from e
    raise RuntimeError(ultimo_err or "No se pudo validar ningún modelo IA disponible")


def generar_resumen(
    conn,
    nombre: str,
    filtros: Optional[dict[str, Any]] = None,
    nivel: str = "tactico",
) -> dict[str, Any]:
    """Resumen ejecutivo del reporte `nombre` vía el proveedor IA configurado."""
    cfg = _config(conn)
    perfil = NIVELES.get(nivel, NIVELES["tactico"])

    try:
        datos = reporte_service.obtener_reporte_vista(conn, nombre=nombre, filtros=filtros)
    except ValueError as e:
        return {"estado": "error", "modelo": cfg["modelo"], "texto": "", "detalle": str(e)}

    if not cfg["api_key"]:
        return {
            "estado": "sin_configurar",
            "modelo": cfg["modelo"],
            "texto": "",
            "detalle": "El analizador IA no está configurado: indica la API key en Configuración o IA_API_KEY en .env.",
        }

    compacto = _compactar(datos)
    estadisticas = _estadisticas(compacto)
    prompt = {
        "sistema": perfil["sistema"],
        "usuario": (
            f"Genera el análisis {perfil['nombre'].lower()} del reporte "
            f"«{datos.get('titulo', nombre)}» (filtros: {datos.get('subtitulo', 'sin filtros')}).\n\n"
            f"Estadísticas calculadas del reporte:\n"
            f"{json.dumps(estadisticas, ensure_ascii=False, indent=1)}\n\n"
            f"Datos del reporte (JSON):\n"
            f"{json.dumps(compacto, ensure_ascii=False, indent=1)}"
        ),
    }
    try:
        res = _llamar_robusto(cfg, prompt)
        contenido = limpiar_salida_ia(res["choices"][0]["message"]["content"])
        return {
            "estado": "ok",
            "modelo": res.get("model", cfg["modelo"]),
            "nivel": nivel if nivel in NIVELES else "tactico",
            "nivel_label": perfil["nombre"],
            "texto": contenido,
            "tokens": res.get("usage", {}).get("total_tokens"),
            "kpis": datos.get("kpis") or [],
        }
    except Exception as e:  # noqa: BLE001
        return {
            "estado": "error",
            "modelo": cfg["modelo"],
            "texto": "",
            "detalle": str(e)[:500],
        }


def _listar_modelos(base: str, api_key: str) -> list[str]:
    req = urllib.request.Request(
        f"{base.rstrip('/')}/models",
        headers={
            "Authorization": f"Bearer {api_key}",
            "User-Agent": "GlobalTradeSA/1.0",
        },
        method="GET",
    )
    with urllib.request.urlopen(req, timeout=20) as respuesta:
        data = json.loads(respuesta.read().decode("utf-8"))
    ids = [str(m.get("id") or "") for m in (data.get("data") or []) if m.get("id")]
    return [m for m in ids if m]


def probar_conexion(conn=None) -> dict[str, Any]:
    cfg = _config(conn)
    if not cfg.get("api_key"):
        return {
            "estado": "sin_configurar",
            "detalle": "Indica la API key en Configuración o en IA_API_KEY (.env).",
        }
    # Preferir el modelo configurado; si 404, tomar uno vivo del catálogo del proveedor
    try:
        res = _llamar_robusto(
            cfg,
            {
                "sistema": "Responde únicamente con la palabra OK.",
                "usuario": "Confirma que la conexión funciona respondiendo OK.",
            },
            timeout=30,
        )
        texto = res["choices"][0]["message"]["content"].strip()
        return {
            "estado": "ok",
            "modelo": res.get("model", cfg["modelo"]),
            "respuesta": texto[:120],
        }
    except Exception as e:  # noqa: BLE001
        return {"estado": "error", "detalle": str(e)[:300]}
