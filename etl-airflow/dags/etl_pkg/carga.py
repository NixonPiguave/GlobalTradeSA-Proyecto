"""carga.py — Etapa CARGA (ELT) hacia el esquema analítico final.

Estrategia (documentada en README.md):
  * 'incremental' (por defecto): inserta SOLO los order_id que no existen aún
    en fact_ventas (idempotente: repetir la ejecución no duplica datos).
  * 'rebuild': borra fact_ventas y la recarga completa (solo migraciones).

Después carga las tablas analíticas (kpis.py) para informes y dashboards.
"""
from __future__ import annotations

import time

from etl_pkg.conexion import conectar
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


def _insertar_ventas(conn, *, max_id, solo_nuevas):
    """INSERT ... SELECT con mapeo a las dimensiones (patrón del proyecto)."""
    cond = (
        " LEFT JOIN fact_ventas f ON f.order_id = CAST(s.order_id AS BIGINT)"
        " WHERE f.order_id IS NULL"
        if solo_nuevas
        else ""
    )
    conn.execute(
        f"""
        INSERT INTO fact_ventas (
            id_venta, order_id, id_region, id_country, id_item_type, id_channel, id_priority,
            order_date, ship_date, units_sold, unit_price, unit_cost,
            total_revenue, total_cost, total_profit
        )
        SELECT
            {max_id} + row_number() OVER (ORDER BY s.order_id),
            CAST(s.order_id AS BIGINT),
            r.id_region, c.id_country, it.id_item_type, ch.id_channel, p.id_priority,
            s.order_date, s.ship_date,
            CAST(s.units_sold AS INTEGER),
            CAST(s.unit_price AS DECIMAL(10,2)),
            CAST(s.unit_cost AS DECIMAL(10,2)),
            CAST(s.total_revenue AS DECIMAL(12,2)),
            CAST(s.total_cost AS DECIMAL(12,2)),
            CAST(s.total_profit AS DECIMAL(12,2))
        FROM stg_ventas_objetivo s
        JOIN dim_region r ON r.region = s.region
        JOIN dim_country c ON c.country = s.country AND c.id_region = r.id_region
        JOIN dim_item_type it ON it.item_type = s.item_type
        JOIN dim_sales_channel ch ON ch.sales_channel = s.sales_channel
        JOIN dim_order_priority p ON p.order_priority = s.order_priority
        {cond}
        """
    )


def cargar_ventas(conn, *, estrategia="incremental"):
    """Carga stg_ventas_objetivo -> fact_ventas. Devuelve filas insertadas."""
    conn.execute("BEGIN TRANSACTION")
    try:
        if estrategia == "rebuild":
            conn.execute("DELETE FROM fact_ventas")
        before = int(conn.execute("SELECT COUNT(*) FROM fact_ventas").fetchone()[0])
        max_id = int(conn.execute("SELECT COALESCE(MAX(id_venta), 0) FROM fact_ventas").fetchone()[0])
        _insertar_ventas(conn, max_id=max_id, solo_nuevas=not (estrategia == "rebuild" or before == 0))
        after = int(conn.execute("SELECT COUNT(*) FROM fact_ventas").fetchone()[0])
        conn.execute("COMMIT")
        insertadas = int(after) - int(before)
    except Exception:
        conn.execute("ROLLBACK")
        raise

    try:
        conn.execute("CHECKPOINT")
    except Exception:
        pass
    return insertadas


def ejecutar(conn=None, *, estrategia="incremental", cerrar: bool | None = None):
    propia = conn is None
    if propia:
        conn = conectar()
    debe_cerrar = propia if cerrar is None else cerrar
    try:
        garantizar_etl_control(conn)
        inicio = time.time()

        from etl_pkg import kpis

        resumen = {}
        resumen["ventas_insertadas"] = cargar_ventas(conn, estrategia=estrategia)
        resumen["tablas_analiticas"] = kpis.refrescar_tablas(conn, estrategia=estrategia)
        resumen["filas_fact_ventas"] = int(
            conn.execute("SELECT COUNT(*) FROM fact_ventas").fetchone()[0]
        )

        fin = time.time()
        _registrar(
            conn, "carga", inicio, fin,
            resumen["ventas_insertadas"] + resumen["tablas_analiticas"],
            f"estrategia={estrategia}",
        )
        try:
            conn.execute("CHECKPOINT")
        except Exception:
            pass
        return resumen
    finally:
        if debe_cerrar:
            conn.close()