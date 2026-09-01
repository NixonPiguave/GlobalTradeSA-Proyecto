"""extraccion.py — Etapa EXTRACCIÓN del proceso ETL.

Lee las fuentes y copia a tablas *staging* (prefijo `stg_`):
  1. data/ventas.parquet — histórico masivo (fuente analítica principal).
  2. pedidos del portal — tabla operativa `pedidos` (fuente B2B).
  3. fact_compras — compras registradas (fuente de compras/inventario).

Las transformaciones NO se aplican aquí (se hacen en transformacion.py).
"""
from __future__ import annotations

import time
from datetime import datetime

from etl_pkg.conexion import conectar, data_dir
from etl_pkg.util import garantizar_etl_control


def _registrar(conn, etapa, inicio, fin, filas, detalle=""):
    conn.execute(
        """
        INSERT INTO etl_control (id, etapa, inicio, fin, tiempo_s, filas, estado, detalle)
        VALUES (
          (SELECT COALESCE(MAX(id), 0) + 1 FROM etl_control),
          ?, ?, ?, ?, ?, 'OK', ?
        )
        """,
        [etapa, inicio, fin, round(fin - inicio, 3), filas, detalle],
    )


def _tabla_existe(conn, tabla):
    return conn.execute(
        "SELECT 1 FROM information_schema.tables WHERE table_name = ?",
        [tabla],
    ).fetchone() is not None


def ejecutar(conn=None, *, cerrar: bool | None = None):
    """Ejecuta la extracción completa. Devuelve las filas por etapa."""
    propia = conn is None
    if propia:
        conn = conectar()
    debe_cerrar = propia if cerrar is None else cerrar
    try:
        garantizar_etl_control(conn)
        inicio = time.time()
        resumen = {
            "ventas_parquet": _extraer_ventas_parquet(conn),
            "pedidos_portal": _extraer_pedidos_portal(conn),
            "compras": _extraer_compras(conn),
        }
        fin = time.time()
        _registrar(conn, "extraccion", inicio, fin, sum(resumen.values()))
        return resumen
    finally:
        if debe_cerrar:
            conn.close()


def _extraer_ventas_parquet(conn):
    fuente = data_dir() / "ventas.parquet"
    if not fuente.exists():
        return 0
    camino = str(fuente).replace("'", "''")
    conn.execute(
        f"""
        CREATE OR REPLACE TABLE stg_ventas AS
        SELECT * FROM read_parquet('{camino}')
        """
    )
    return int(conn.execute("SELECT COUNT(*) FROM stg_ventas").fetchone()[0])


def _extraer_pedidos_portal(conn):
    if not _tabla_existe(conn, "pedidos"):
        return 0
    conn.execute(
        """
        CREATE OR REPLACE TABLE stg_pedidos AS
        SELECT
            id_pedido, numero, id_cliente, id_country, id_channel, id_priority,
            fecha_pedido, estado, subtotal, impuesto_monto, descuento_monto, total_pedido
        FROM pedidos
        WHERE estado NOT IN ('borrador', 'cancelado')
        """
    )
    return int(conn.execute("SELECT COUNT(*) FROM stg_pedidos").fetchone()[0])


def _extraer_compras(conn):
    if not _tabla_existe(conn, "fact_compras"):
        return 0
    conn.execute("CREATE OR REPLACE TABLE stg_compras AS SELECT * FROM fact_compras")
    return int(conn.execute("SELECT COUNT(*) FROM stg_compras").fetchone()[0])