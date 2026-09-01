"""
Tests de inventario: stock no negativo, movimientos y recepción de OC.

Ejecutar desde la raíz del repo:
    $env:PYTHONPATH=".;apps/admin;apps/portal"
    pytest apps/admin/backend/tests/test_inventario_service.py -q
"""

from __future__ import annotations

import duckdb
import pytest

from backend.services import compras_service, inventario_service, proveedor_service


@pytest.fixture()
def conn():
    c = duckdb.connect(":memory:")
    c.execute("CREATE SEQUENCE seq_dim_producto START 1")
    c.execute("CREATE SEQUENCE seq_proveedores START 1")
    c.execute("CREATE SEQUENCE seq_movimientos START 1")
    c.execute("CREATE SEQUENCE seq_ordenes_compra START 1")
    c.execute("CREATE SEQUENCE seq_recepciones START 1")
    c.execute(
        """
        CREATE TABLE dim_item_type (id_item_type INTEGER PRIMARY KEY, item_type VARCHAR, unit_price DECIMAL(10,2), unit_cost DECIMAL(10,2));
        CREATE TABLE dim_country (id_country INTEGER PRIMARY KEY, country VARCHAR, id_region INTEGER);
        CREATE TABLE dim_region (id_region INTEGER PRIMARY KEY, region VARCHAR);
        CREATE TABLE dim_producto (
          id_producto BIGINT PRIMARY KEY DEFAULT nextval('seq_dim_producto'),
          nombre_producto VARCHAR NOT NULL, descripcion VARCHAR, id_item_type BIGINT NOT NULL,
          precio_unitario DECIMAL(10,2), precio_mayorista DECIMAL(10,2), imagen_url VARCHAR, activo BOOLEAN DEFAULT true,
          id_marca BIGINT, id_linea BIGINT, sku VARCHAR, descuento_pct DECIMAL(5,2) DEFAULT 0,
          precio_rebajado DECIMAL(10,2), descuento_aplica_a VARCHAR DEFAULT 'mayorista',
          stock_minimo DECIMAL(12,4) DEFAULT 10, fecha_rebaja_hasta DATE, descuento_motivo VARCHAR
        );
        CREATE TABLE stock_almacen (
          id_stock BIGINT PRIMARY KEY, id_producto BIGINT, id_almacen BIGINT,
          cantidad_disponible DECIMAL(12,4) DEFAULT 0, cantidad_reservada DECIMAL(12,4) DEFAULT 0
        );
        CREATE TABLE movimientos_inventario (
          id_movimiento BIGINT PRIMARY KEY DEFAULT nextval('seq_movimientos'),
          tipo VARCHAR, fecha TIMESTAMP DEFAULT current_timestamp, referencia VARCHAR, id_usuario BIGINT
        );
        CREATE TABLE movimiento_inventario_detalle (
          id_detalle BIGINT PRIMARY KEY, id_movimiento BIGINT, id_producto BIGINT,
          id_almacen BIGINT, id_lote BIGINT, cantidad DECIMAL(12,4)
        );
        CREATE TABLE alertas_stock (
          id_alerta BIGINT PRIMARY KEY, id_producto BIGINT, id_almacen BIGINT,
          umbral_minimo DECIMAL(12,4), activa BOOLEAN DEFAULT true
        );
        CREATE TABLE usuarios (id_usuario BIGINT PRIMARY KEY, email VARCHAR);
        CREATE TABLE proveedores (
          id_proveedor BIGINT PRIMARY KEY DEFAULT nextval('seq_proveedores'),
          razon_social VARCHAR, ruc VARCHAR, id_country BIGINT, activo BOOLEAN DEFAULT true
        );
        CREATE TABLE ordenes_compra (
          id_oc BIGINT PRIMARY KEY DEFAULT nextval('seq_ordenes_compra'),
          numero VARCHAR, id_proveedor BIGINT, fecha TIMESTAMP, estado VARCHAR, total DECIMAL(12,2),
          metodo_pago VARCHAR DEFAULT 'caja'
        );
        CREATE TABLE orden_compra_detalle (
          id_detalle BIGINT PRIMARY KEY, id_oc BIGINT, id_producto BIGINT,
          cantidad DECIMAL(12,4), costo_unitario DECIMAL(10,2), subtotal DECIMAL(12,2)
        );
        CREATE TABLE recepciones_compra (
          id_recepcion BIGINT PRIMARY KEY DEFAULT nextval('seq_recepciones'),
          id_oc BIGINT, fecha TIMESTAMP, id_almacen BIGINT, estado VARCHAR
        );
        CREATE TABLE recepcion_compra_detalle (
          id_detalle BIGINT PRIMARY KEY, id_recepcion BIGINT, id_producto BIGINT,
          cantidad_recibida DECIMAL(12,4), id_lote BIGINT, observacion VARCHAR
        );
        CREATE TABLE fact_compras (
          id_compra BIGINT PRIMARY KEY, id_oc BIGINT, id_producto BIGINT,
          cantidad DECIMAL(12,4), costo DECIMAL(12,2), fecha TIMESTAMP
        );
        CREATE TABLE almacenes (
          id_almacen BIGINT PRIMARY KEY, nombre VARCHAR, direccion VARCHAR,
          macro_zona VARCHAR, activo BOOLEAN DEFAULT true
        );
        INSERT INTO almacenes VALUES (1, 'Central', 'HQ', 'americas', true);
        CREATE TABLE marcas (id_marca BIGINT PRIMARY KEY, nombre VARCHAR, activo BOOLEAN DEFAULT true);
        CREATE TABLE lineas_producto (
          id_linea BIGINT PRIMARY KEY, nombre VARCHAR, id_marca BIGINT, activo BOOLEAN DEFAULT true
        );
        """
    )
    c.execute("INSERT INTO dim_item_type VALUES (1, 'Snacks', 10, 6)")
    c.execute(
        "INSERT INTO dim_producto (nombre_producto, id_item_type, precio_unitario, precio_mayorista) VALUES ('Prod A', 1, 10, 8)"
    )
    yield c
    c.close()


def test_ajuste_positivo_incrementa_stock(conn):
    resultado = inventario_service.ajustar_stock(
        conn, id_producto=1, cantidad=50, motivo="carga inicial", id_usuario=None
    )
    assert resultado["disponible"] == 50


def test_stock_no_puede_quedar_negativo(conn):
    inventario_service.ajustar_stock(conn, id_producto=1, cantidad=10, motivo="init", id_usuario=None)
    with pytest.raises(ValueError, match="Stock insuficiente"):
        inventario_service.ajustar_stock(conn, id_producto=1, cantidad=-11, motivo="salida", id_usuario=None)
    # El stock queda intacto tras el fallo
    assert inventario_service.obtener_stock(conn, 1)["disponible"] == 10


def test_movimientos_registrados(conn):
    inventario_service.ajustar_stock(conn, id_producto=1, cantidad=5, motivo="entrada", id_usuario=None)
    inventario_service.ajustar_stock(conn, id_producto=1, cantidad=-2, motivo="salida", id_usuario=None)
    movimientos = inventario_service.listar_movimientos(conn)
    assert len(movimientos) == 2
    cantidades = sorted(m["cantidad"] for m in movimientos)
    assert cantidades == [-2, 5]


def test_recepcion_oc_incrementa_stock(conn):
    prov = proveedor_service.crear_proveedor(conn, razon_social="ACME", ruc=None, id_country=None)
    orden = compras_service.crear_orden_compra(
        conn,
        id_proveedor=prov["id_proveedor"],
        items=[{"id_producto": 1, "cantidad": 30, "costo_unitario": 6.0}],
    )
    assert orden["estado"] == "borrador"
    compras_service.cambiar_estado_oc(conn, orden["id_oc"], "aprobada")
    resultado = compras_service.recibir_orden(conn, id_oc=orden["id_oc"], id_almacen=1, id_usuario=None)
    assert resultado["orden"]["estado"] == "recibida"
    assert inventario_service.obtener_stock(conn, 1)["disponible"] == 30


def test_recepcion_requiere_aprobada(conn):
    prov = proveedor_service.crear_proveedor(conn, razon_social="ACME2", ruc=None, id_country=None)
    orden = compras_service.crear_orden_compra(
        conn,
        id_proveedor=prov["id_proveedor"],
        items=[{"id_producto": 1, "cantidad": 5, "costo_unitario": 6.0}],
    )
    with pytest.raises(ValueError, match="aprobada"):
        compras_service.recibir_orden(conn, id_oc=orden["id_oc"], id_almacen=1, id_usuario=None)


def test_alertas_stock_bajo(conn):
    inventario_service.ajustar_stock(conn, id_producto=1, cantidad=3, motivo="init", id_usuario=None)
    inventario_service.fijar_alerta(conn, id_producto=1, umbral_minimo=5)
    alertas = inventario_service.alertas_activas(conn)
    assert len(alertas) == 1
    assert alertas[0]["disponible"] == 3


def test_costo_sugerido_desde_catalogo(conn):
    sug = compras_service.costo_sugerido_compra(conn, id_producto=1)
    assert sug["costo_unitario"] == 8.0
    assert sug["origen"] == "precio_producto"


def test_costo_sugerido_ultima_compra_proveedor(conn):
    prov = proveedor_service.crear_proveedor(conn, razon_social="ACME", ruc=None, id_country=None)
    compras_service.crear_orden_compra(
        conn,
        id_proveedor=prov["id_proveedor"],
        items=[{"id_producto": 1, "cantidad": 10, "costo_unitario": 5.25}],
    )
    sug = compras_service.costo_sugerido_compra(
        conn, id_producto=1, id_proveedor=prov["id_proveedor"]
    )
    assert sug["costo_unitario"] == 5.25
    assert sug["origen"] == "ultima_compra_proveedor"


def test_crear_producto_sin_stock_inicial(conn):
    """El alta B2B no inventa stock; entra por OC o movimiento manual."""
    from backend.services import producto_service

    producto = producto_service.crear_producto(
        conn,
        nombre_producto="Nuevo sin stock",
        descripcion=None,
        id_item_type=1,
        precio_unitario=12,
        precio_mayorista=9,
        imagen_url=None,
        stock_inicial=25,
    )
    assert producto["stock"] == 0
    assert inventario_service.obtener_stock(conn, producto["id_producto"])["disponible"] == 0
    assert inventario_service.listar_movimientos(conn) == []
