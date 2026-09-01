"""Tests activar/desactivar categorías."""

from __future__ import annotations

import duckdb
import pytest

from backend.services.categoria_service import (
    actualizar_categoria,
    desactivar_categoria,
    obtener_categoria,
    set_categoria_activa,
)


@pytest.fixture()
def conn():
    c = duckdb.connect(":memory:")
    c.execute(
        """
        CREATE TABLE dim_item_type (
          id_item_type INTEGER PRIMARY KEY, item_type VARCHAR,
          unit_price DECIMAL(10,2), unit_cost DECIMAL(10,2)
        );
        CREATE TABLE categorias (
          id_categoria BIGINT PRIMARY KEY,
          nombre VARCHAR NOT NULL, slug VARCHAR UNIQUE, descripcion VARCHAR,
          imagen_path VARCHAR, activo BOOLEAN DEFAULT true, id_item_type BIGINT,
          descuento_pct DECIMAL(5,2) DEFAULT 0, descuento_aplica_a VARCHAR DEFAULT 'mayorista',
          descuento_hasta DATE, descuento_motivo VARCHAR
        );
        INSERT INTO dim_item_type VALUES (1, 'Baby Food', 0, 0);
        INSERT INTO categorias (
          id_categoria, nombre, slug, descripcion, imagen_path, activo, id_item_type
        ) VALUES (8, 'Baby Food', 'baby-food', 'Baby Food', NULL, true, 1);
        """
    )
    yield c
    c.close()


def test_desactivar_y_reactivar_categoria(conn):
    assert desactivar_categoria(conn, 8) is True
    assert obtener_categoria(conn, 8)["activo"] is False
    assert set_categoria_activa(conn, 8, True) is True
    assert obtener_categoria(conn, 8)["activo"] is True


def test_actualizar_solo_activo_sin_tocar_slug(conn):
    desactivar_categoria(conn, 8)
    cat = actualizar_categoria(conn, 8, {"activo": True})
    assert cat is not None
    assert cat["activo"] is True
    assert cat["slug"] == "baby-food"


def test_actualizar_mismo_nombre_no_rompe(conn):
    desactivar_categoria(conn, 8)
    cat = actualizar_categoria(
        conn, 8, {"nombre": "Baby Food", "descripcion": "Baby Food", "activo": True}
    )
    assert cat["activo"] is True
