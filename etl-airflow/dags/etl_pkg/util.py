"""util.py — Helpers compartidos del paquete ETL."""
from __future__ import annotations


def garantizar_etl_control(conn):
    """Crea (si no existe) la tabla de control/bitácora del proceso ETL."""
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS etl_control (
          id BIGINT PRIMARY KEY,
          etapa VARCHAR,
          inicio DOUBLE,
          fin DOUBLE,
          tiempo_s DOUBLE,
          filas BIGINT,
          estado VARCHAR,
          detalle VARCHAR
        )
        """
    )
