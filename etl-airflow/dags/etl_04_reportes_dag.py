"""etl_04_reportes_dag.py — DAG de generación programada de reportes ejecutivos.

Corre después del pipeline ETL (diario 02:30) y genera el paquete de
reportes PDF/CSV en shared/storage/reportes/, el mismo directorio que el panel
consume en la sección "Reportes programados". Reutiliza reporte_service: el
contenido es idéntico al que se ve en pantalla, sin duplicar SQL.

Cada entrega se registra en la tabla `reportes_generados` de la DuckDB del
proyecto (expuesta por GET /api/reportes/programados). Los artefactos con más
de RETENCION_DIAS días se eliminan en la tarea de limpieza.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import sys
import time
from pathlib import Path

from airflow.decorators import dag, task
from airflow.utils.dates import days_ago


def _zona_local() -> dt.tzinfo | None:
    """Zona horaria de operación (Perú). Si no hay tzdata, se usa hora local del contenedor."""
    try:
        from zoneinfo import ZoneInfo

        return ZoneInfo("America/Lima")
    except Exception:  # noqa: BLE001
        return None


ZONA = _zona_local()


def _ahora_local() -> dt.datetime:
    now = dt.datetime.now(ZONA) if ZONA else dt.datetime.now()
    return now


def _hoy_local() -> dt.date:
    return _ahora_local().date()


def _raiz_proyecto() -> Path:
    """Ancla: DUCKDB_PATH=/proyecto/db/globtrade.duckdb (Airflow) o ruta relativa local."""
    env = os.environ.get("DUCKDB_PATH", "").strip()
    if env:
        return Path(env).resolve().parents[1]
    return Path(__file__).resolve().parents[2]


RAIZ = _raiz_proyecto()
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(RAIZ / "apps" / "admin"))

from backend.services import reporte_service  # noqa: E402
from etl_pkg.conexion import conectar, sync_clickhouse_via_api  # noqa: E402

# Paquete diario: qué reportes se generan y en qué formato.
PAQUETE_DIARIO = [
    {"nombre": "informe-gerencial", "formato": "pdf"},
    {"nombre": "informe-financiero", "formato": "pdf"},
    {"nombre": "informe-comercial", "formato": "pdf"},
    {"nombre": "informe-logistico", "formato": "pdf"},
    {"nombre": "informe-operativo", "formato": "pdf"},
    {"nombre": "ventas-detalle", "formato": "pdf", "filtros_extra": {"limite": 1000}},
    {"nombre": "clientes-cxc", "formato": "pdf"},
    {"nombre": "cuentas-por-pagar", "formato": "pdf"},
    {"nombre": "stock-bajo", "formato": "csv"},
]

WINDOW_DAYS = 30      # ventana de fechas incluida en cada reporte
RETENCION_DIAS = 30   # días que se conservan los artefactos en disco


def _tabla_reportes(conn) -> None:
    conn.execute("CREATE SEQUENCE IF NOT EXISTS seq_reporte_gen START 1")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS reportes_generados (
            id          BIGINT PRIMARY KEY DEFAULT nextval('seq_reporte_gen'),
            fecha       TIMESTAMP,
            nombre      VARCHAR,
            archivo     VARCHAR,
            filtros     VARCHAR,
            formato     VARCHAR,
            duracion_ms BIGINT,
            estado      VARCHAR,
            bytes       BIGINT,
            detalle     VARCHAR
        )
        """
    )


@dag(
    dag_id="etl_04_reportes_dag",
    default_args={"owner": "gobierno-datos", "retries": 0},
    description="Paquete diario de reportes ejecutivos (PDF/CSV) para el panel",
    schedule="30 2 * * *",
    start_date=days_ago(1),
    catchup=False,
    max_active_runs=1,
    is_paused_upon_creation=False,
    tags=["reportes", "estrategico", "programados"],
)
def etl_reportes_programados() -> None:
    @task(task_id="generar_paquete")
    def generar_paquete() -> dict:
        import os

        if os.environ.get("GLOBALTRADE_ETL_VIA_API", "").strip().lower() in {"1", "true", "yes"}:
            try:
                sync_clickhouse_via_api()
            except Exception:
                pass

        hoy = _hoy_local()
        stamp = hoy.isoformat()
        filtros_base = {
            "desde": (hoy - dt.timedelta(days=WINDOW_DAYS)).isoformat(),
            "hasta": hoy.isoformat(),
        }

        dir_destino = reporte_service.dir_reportes_generados()
        dir_destino.mkdir(parents=True, exist_ok=True)

        conn = conectar()
        _tabla_reportes(conn)
        entregas = []
        try:
            for item in PAQUETE_DIARIO:
                nombre, formato = item["nombre"], item["formato"]
                filtros = {**filtros_base, **item.get("filtros_extra", {})}
                archivo = f"{stamp}_{nombre.replace('-', '_')}.{formato}"
                t0 = time.perf_counter()
                try:
                    data, _, _ = reporte_service.generar_reporte(
                        conn, nombre=nombre, formato=formato, filtros=filtros
                    )
                    estado, detalle = "ok", ""
                except Exception as exc:  # noqa: BLE001
                    data, estado, detalle = b"", "error", str(exc)[:500]
                duracion = int((time.perf_counter() - t0) * 1000)
                if estado == "ok":
                    (dir_destino / archivo).write_bytes(data)
                conn.execute(
                    """
                    INSERT INTO reportes_generados
                        (fecha, nombre, archivo, filtros, formato, duracion_ms, estado, bytes, detalle)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    [_ahora_local().replace(tzinfo=None), nombre, archivo, json.dumps(filtros),
                     formato, duracion, estado, len(data), detalle],
                )
                entregas.append({
                    "nombre": nombre, "formato": formato, "archivo": archivo,
                    "estado": estado, "duracion_ms": duracion, "bytes": len(data),
                })
        finally:
            conn.close()

        manifest = {"fecha": stamp, "ventana": filtros_base, "entregas": entregas}
        (dir_destino / f"manifest_{stamp}.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2)
        )
        ok = sum(1 for e in entregas if e["estado"] == "ok")
        return {"generados": ok, "total": len(entregas), "stamp": stamp}

    @task(task_id="limpiar_antiguos")
    def limpiar_antiguos() -> int:
        dir_repo = reporte_service.dir_reportes_generados()
        corte = dt.date.today() - dt.timedelta(days=RETENCION_DIAS)
        borrados = 0
        for archivo in dir_repo.glob("*"):
            if not archivo.is_file():
                continue
            try:
                fecha_archivo = dt.datetime.strptime(archivo.stem.split("_", 1)[0], "%Y-%m-%d").date()
            except ValueError:
                continue
            if fecha_archivo < corte:
                archivo.unlink(missing_ok=True)
                borrados += 1
        return {"borrados": borrados}

    generar_paquete() >> limpiar_antiguos()


etl_04_reportes_dag = etl_reportes_programados()