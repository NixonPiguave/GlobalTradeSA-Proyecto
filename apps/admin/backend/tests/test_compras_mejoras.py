"""
Tests de las mejoras de compras: método de pago, recepción parcial,
asientos por método, historial de recepciones y cuentas por pagar.

Ejecutar desde la raíz del repo:
    $env:PYTHONPATH=".;apps/admin;apps/portal"
    pytest apps/admin/backend/tests/test_compras_mejoras.py -q
"""

from __future__ import annotations

import duckdb
import pytest

from backend.services import compras_service, inventario_service, proveedor_service


@pytest.fixture()
def conn():
    c = duckdb.connect(":memory:")
    for seq in ("seq_dim_producto", "seq_proveedores", "seq_movimientos",
                "seq_ordenes_compra", "seq_recepciones"):
        c.execute(f"CREATE SEQUENCE {seq} START 1")
    c.execute(
        """
        CREATE TABLE dim_item_type (id_item_type INTEGER PRIMARY KEY, item_type VARCHAR, unit_price DECIMAL(10,2), unit_cost DECIMAL(10,2));
        CREATE TABLE dim_country (id_country INTEGER PRIMARY KEY, country VARCHAR, id_region INTEGER);
        CREATE TABLE dim_region (id_region INTEGER PRIMARY KEY, region VARCHAR);
        CREATE TABLE dim_producto (
          id_producto BIGINT PRIMARY KEY DEFAULT nextval('seq_dim_producto'),
          nombre_producto VARCHAR NOT NULL, descripcion VARCHAR, id_item_type BIGINT NOT NULL,
          precio_unitario DECIMAL(10,2), precio_mayorista DECIMAL(10,2), imagen_url VARCHAR, activo BOOLEAN DEFAULT true
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
        CREATE TABLE proveedores (
          id_proveedor BIGINT PRIMARY KEY DEFAULT nextval('seq_proveedores'),
          razon_social VARCHAR, ruc VARCHAR, id_country BIGINT, activo BOOLEAN DEFAULT true
        );
        CREATE TABLE ordenes_compra (
          id_oc BIGINT PRIMARY KEY DEFAULT nextval('seq_ordenes_compra'),
          numero VARCHAR, id_proveedor BIGINT, fecha TIMESTAMP, estado VARCHAR,
          total DECIMAL(12,2), metodo_pago VARCHAR DEFAULT 'caja'
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
        CREATE TABLE almacenes (
          id_almacen BIGINT PRIMARY KEY, nombre VARCHAR, direccion VARCHAR,
          macro_zona VARCHAR, activo BOOLEAN DEFAULT true
        );
        INSERT INTO almacenes VALUES (1, 'Central', 'HQ', 'americas', true);
        CREATE TABLE fact_compras (
          id_compra BIGINT PRIMARY KEY, id_oc BIGINT, id_producto BIGINT,
          cantidad DECIMAL(12,4), costo DECIMAL(12,2), fecha TIMESTAMP
        );
        CREATE TABLE plan_cuentas (
          id_cuenta BIGINT PRIMARY KEY, codigo VARCHAR, nombre VARCHAR, tipo VARCHAR
        );
        CREATE TABLE asientos_contables (
          id_asiento BIGINT PRIMARY KEY, numero VARCHAR, fecha TIMESTAMP, descripcion VARCHAR,
          id_pedido BIGINT, id_factura BIGINT, id_oc BIGINT, total DECIMAL(12,2)
        );
        CREATE TABLE asiento_lineas (
          id_linea BIGINT PRIMARY KEY, id_asiento BIGINT, id_cuenta BIGINT,
          debe DECIMAL(12,2), haber DECIMAL(12,2)
        );
        """
    )
    c.execute("INSERT INTO dim_item_type VALUES (1, 'Snacks', 10, 6)")
    c.execute(
        "INSERT INTO dim_producto (nombre_producto, id_item_type, precio_unitario, precio_mayorista) "
        "VALUES ('Prod A', 1, 10, 8)"
    )
    cuenta_id = 0
    for codigo, nombre, tipo in [
        ("1101", "Caja", "activo"),
        ("1201", "Cuentas por cobrar", "activo"),
        ("1301", "Inventario", "activo"),
        ("2002", "Cuentas por pagar", "pasivo"),
        ("3001", "Pagos externos", "pasivo"),
        ("4101", "Ingresos", "resultado"),
    ]:
        cuenta_id += 1
        c.execute("INSERT INTO plan_cuentas VALUES (?, ?, ?, ?)", [cuenta_id, codigo, nombre, tipo])
    yield c
    c.close()


def _crear_aprobar(conn, cantidad=30, costo=6.0, metodo="caja"):
    prov = proveedor_service.crear_proveedor(conn, razon_social="ACME", ruc=None, id_country=None)
    orden = compras_service.crear_orden_compra(
        conn,
        id_proveedor=prov["id_proveedor"],
        items=[{"id_producto": 1, "cantidad": cantidad, "costo_unitario": costo}],
        metodo_pago=metodo,
    )
    compras_service.cambiar_estado_oc(conn, orden["id_oc"], "aprobada")
    return orden


def _asiento_por_desc(conn, desc):
    return conn.execute(
        "SELECT id_asiento, id_pedido, id_oc, total FROM asientos_contables WHERE descripcion = ?",
        [desc],
    ).fetchone()


def _lineas_asiento(conn, id_asiento):
    return conn.execute(
        """
        SELECT pc.codigo, CAST(al.debe AS DOUBLE), CAST(al.haber AS DOUBLE)
        FROM asiento_lineas al JOIN plan_cuentas pc ON pc.id_cuenta = al.id_cuenta
        WHERE al.id_asiento = ?
        """,
        [id_asiento],
    ).fetchall()


# ---------------------------------------------------------------------------
# Método de pago
# ---------------------------------------------------------------------------

def test_metodo_pago_se_guarda(conn):
    orden = _crear_aprobar(conn, metodo="externo")
    det = compras_service.obtener_orden(conn, orden["id_oc"])
    assert det["metodo_pago"] == "externo"


def test_metodo_pago_invalido(conn):
    prov = proveedor_service.crear_proveedor(conn, razon_social="ACME", ruc=None, id_country=None)
    with pytest.raises(ValueError, match="Método de pago inválido"):
        compras_service.crear_orden_compra(
            conn, id_proveedor=prov["id_proveedor"],
            items=[{"id_producto": 1, "cantidad": 1, "costo_unitario": 1}],
            metodo_pago="nada",
        )


# ---------------------------------------------------------------------------
# Recepción parcial
# ---------------------------------------------------------------------------

def test_recepcion_parcial_estado_y_stock(conn):
    orden = _crear_aprobar(conn, cantidad=60, costo=5.0)
    r1 = compras_service.recibir_orden(
        conn, id_oc=orden["id_oc"], id_almacen=1, id_usuario=None,
        recibos=[{"id_detalle": orden["items"][0]["id_detalle"], "cantidad": 10, "observacion": "mitad llegó tarde"}],
    )
    assert r1["orden"]["estado"] == "parcialmente_recibida"
    assert r1["orden"]["items"][0]["pendiente"] == 50
    assert inventario_service.obtener_stock(conn, 1)["disponible"] == 10
    assert compras_service.listar_recepciones(conn)[0]["estado"] == "parcial"

    r2 = compras_service.recibir_orden(conn, id_oc=orden["id_oc"], id_almacen=1, id_usuario=None)
    assert r2["orden"]["estado"] == "recibida"
    assert r2["orden"]["items"][0]["pendiente"] == 0
    assert inventario_service.obtener_stock(conn, 1)["disponible"] == 60
    assert compras_service.listar_recepciones(conn)[0]["estado"] == "completa"


def test_recepcion_completa_en_una_sola_vez(conn):
    orden = _crear_aprobar(conn, cantidad=11, costo=1.0)
    compras_service.recibir_orden(conn, id_oc=orden["id_oc"], id_almacen=1, id_usuario=None)
    assert compras_service.listar_recepciones(conn)[0]["estado"] == "completa"


def test_recepcion_no_puede_exceder_pendiente(conn):
    orden = _crear_aprobar(conn, cantidad=20)
    with pytest.raises(ValueError, match="Cantidad inválida"):
        compras_service.recibir_orden(
            conn, id_oc=orden["id_oc"], id_almacen=1, id_usuario=None,
            recibos=[{"id_detalle": orden["items"][0]["id_detalle"], "cantidad": 25}],
        )


def test_recepcion_requiere_estado_aprobada(conn):
    prov = proveedor_service.crear_proveedor(conn, razon_social="ACME", ruc=None, id_country=None)
    orden = compras_service.crear_orden_compra(
        conn, id_proveedor=prov["id_proveedor"],
        items=[{"id_producto": 1, "cantidad": 5, "costo_unitario": 2.0}],
    )
    with pytest.raises(ValueError, match="Solo se puede recibir"):
        compras_service.recibir_orden(conn, id_oc=orden["id_oc"], id_almacen=1, id_usuario=None)


# ---------------------------------------------------------------------------
# Transiciones
# ---------------------------------------------------------------------------

def test_transiciones_invalidas(conn):
    orden = _crear_aprobar(conn, cantidad=5, metodo="caja")
    with pytest.raises(ValueError, match="Usa el endpoint de recepción"):
        compras_service.cambiar_estado_oc(conn, orden["id_oc"], "recibida")
    with pytest.raises(ValueError, match="Transición inválida"):
        compras_service.cambiar_estado_oc(conn, orden["id_oc"], "borrador")


# ---------------------------------------------------------------------------
# Asientos por método de pago
# ---------------------------------------------------------------------------

def test_asientos_metodo_caja(conn):
    orden = _crear_aprobar(conn, cantidad=10, costo=5.0, metodo="caja")
    id_recepcion = compras_service.recibir_orden(conn, id_oc=orden["id_oc"], id_almacen=1, id_usuario=None)["id_recepcion"]
    compra = _asiento_por_desc(conn, f"compra:R{id_recepcion} OC {orden['numero']}")
    assert compra is not None
    assert compra[2] == orden["id_oc"]
    lineas_compra = _lineas_asiento(conn, compra[0])
    assert ("1301", 50.0, 0.0) in lineas_compra
    assert ("2002", 0.0, 50.0) in lineas_compra

    pago = _asiento_por_desc(conn, f"pago_oc:R{id_recepcion} OC {orden['numero']}")
    assert pago is not None
    lineas_pago = _lineas_asiento(conn, pago[0])
    assert ("2002", 50.0, 0.0) in lineas_pago
    assert ("1101", 0.0, 50.0) in lineas_pago


def test_asientos_metodo_externo(conn):
    orden = _crear_aprobar(conn, cantidad=10, costo=5.0, metodo="externo")
    id_recepcion = compras_service.recibir_orden(conn, id_oc=orden["id_oc"], id_almacen=1, id_usuario=None)["id_recepcion"]
    pago = _asiento_por_desc(conn, f"pago_oc:R{id_recepcion} OC {orden['numero']}")
    assert pago is not None
    lineas = _lineas_asiento(conn, pago[0])
    assert ("3001", 0.0, 50.0) in lineas
    assert ("1101", 0.0, 50.0) not in lineas


def test_asientos_credito_no_genera_pago(conn):
    orden = _crear_aprobar(conn, cantidad=10, costo=5.0, metodo="credito")
    id_recepcion = compras_service.recibir_orden(conn, id_oc=orden["id_oc"], id_almacen=1, id_usuario=None)["id_recepcion"]
    assert _asiento_por_desc(conn, f"compra:R{id_recepcion} OC {orden['numero']}") is not None
    assert _asiento_por_desc(conn, f"pago_oc:R{id_recepcion} OC {orden['numero']}") is None


# ---------------------------------------------------------------------------
# Cuentas por pagar
# ---------------------------------------------------------------------------

def test_cuentas_por_pagar_caja_liquida(conn):
    orden = _crear_aprobar(conn, cantidad=40, costo=2.0, metodo="caja")
    compras_service.recibir_orden(conn, id_oc=orden["id_oc"], id_almacen=1, id_usuario=None)
    resumen = compras_service.cuentas_por_pagar(conn)
    assert resumen["total_pendiente"] == 0.0
    fila = resumen["proveedores"][0]
    assert fila["recibido"] == 80.0
    assert fila["pagado"] == 80.0
    assert fila["pendiente"] == 0.0


def test_cuentas_por_pagar_credito_abierta(conn):
    orden = _crear_aprobar(conn, cantidad=10, costo=2.0, metodo="credito")
    compras_service.recibir_orden(conn, id_oc=orden["id_oc"], id_almacen=1, id_usuario=None)
    resumen = compras_service.cuentas_por_pagar(conn)
    fila = resumen["proveedores"][0]
    assert fila["recibido"] == 20.0
    assert fila["pagado"] == 0.0
    assert fila["pendiente"] == 20.0
    assert resumen["total_pendiente"] == 20.0


# ---------------------------------------------------------------------------
# Historial de recepciones
# ---------------------------------------------------------------------------

def test_listar_recepciones_agrupa(conn):
    orden = _crear_aprobar(conn, cantidad=20, costo=3.0)
    compras_service.recibir_orden(
        conn, id_oc=orden["id_oc"], id_almacen=1, id_usuario=None,
        recibos=[{"id_detalle": orden["items"][0]["id_detalle"], "cantidad": 8, "observacion": "daño parcial"}],
    )
    recepciones = compras_service.listar_recepciones(conn)
    assert len(recepciones) == 1
    rec = recepciones[0]
    assert rec["numero_oc"] == orden["numero"]
    assert rec["n_items"] == 1
    assert rec["items"][0]["cantidad"] == 8
    assert rec["items"][0]["observacion"] == "daño parcial"
    assert rec["total"] == 24.0