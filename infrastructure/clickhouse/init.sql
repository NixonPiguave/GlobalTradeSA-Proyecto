CREATE DATABASE IF NOT EXISTS globtrade_dwh;

CREATE TABLE IF NOT EXISTS globtrade_dwh.dwh_ventas (
    order_date Date,
    country String,
    region String,
    item_type String,
    nombre_producto String,
    linea String,
    marca String,
    sales_channel String,
    origen String,
    order_id Int64,
    units_sold Int64,
    total_revenue Float64,
    total_cost Float64,
    total_profit Float64
) ENGINE = MergeTree()
PARTITION BY toYear(order_date)
ORDER BY (order_date, country, item_type);

CREATE TABLE IF NOT EXISTS globtrade_dwh.dwh_compras (
    fecha Date,
    proveedor String,
    numero String,
    estado String,
    total_compra Float64
) ENGINE = MergeTree()
PARTITION BY toYear(fecha)
ORDER BY (fecha, proveedor);

CREATE TABLE IF NOT EXISTS globtrade_dwh.dwh_clientes (
    nombre_cliente String,
    pais String,
    total_comprado Float64,
    total_pagado Float64,
    cxc Float64
) ENGINE = MergeTree()
ORDER BY (total_comprado, nombre_cliente);

CREATE TABLE IF NOT EXISTS globtrade_dwh.dwh_proveedores (
    proveedor String,
    pais String,
    total_comprado Float64,
    num_oc Int32
) ENGINE = MergeTree()
ORDER BY (total_comprado, proveedor);

CREATE TABLE IF NOT EXISTS globtrade_dwh.dwh_geografia (
    country String,
    region String,
    total_revenue Float64,
    units_sold Int64,
    num_pedidos Int32
) ENGINE = MergeTree()
ORDER BY (total_revenue, country);

CREATE TABLE IF NOT EXISTS globtrade_dwh.dwh_inventario (
    producto String,
    categoria String,
    almacen String,
    id_almacen Int32,
    stock Float64,
    costo_unit Float64,
    valor Float64
) ENGINE = MergeTree()
ORDER BY (producto, id_almacen);

CREATE TABLE IF NOT EXISTS globtrade_dwh.dwh_stock_bajo (
    producto String,
    almacen String,
    disponible Float64,
    umbral Float64,
    deficit Float64
) ENGINE = MergeTree()
ORDER BY (deficit, producto);

CREATE TABLE IF NOT EXISTS globtrade_dwh.dwh_pedidos_estado (
    estado String,
    cantidad Int32,
    monto_total Float64
) ENGINE = MergeTree()
ORDER BY (cantidad, estado);

CREATE TABLE IF NOT EXISTS globtrade_dwh.dwh_pedidos_pendientes (
    numero String,
    cliente String,
    estado String,
    monto Float64,
    fecha Date,
    sin_envio UInt8
) ENGINE = MergeTree()
ORDER BY (fecha, numero);

CREATE TABLE IF NOT EXISTS globtrade_dwh.dwh_movimientos (
    fecha DateTime,
    tipo String,
    producto String,
    almacen String,
    cantidad Float64,
    referencia String
) ENGINE = MergeTree()
PARTITION BY toYear(fecha)
ORDER BY (fecha, producto);

CREATE TABLE IF NOT EXISTS globtrade_dwh.dwh_recepciones (
    id_recepcion Int64,
    oc_numero String,
    proveedor String,
    fecha Date,
    estado String,
    lineas Int32,
    valor_recibido Float64
) ENGINE = MergeTree()
PARTITION BY toYear(fecha)
ORDER BY (fecha, id_recepcion);

CREATE TABLE IF NOT EXISTS globtrade_dwh.dwh_finanzas (
    codigo String,
    nombre String,
    tipo String,
    debe Float64,
    haber Float64,
    saldo Float64
) ENGINE = MergeTree()
ORDER BY (codigo);

CREATE TABLE IF NOT EXISTS globtrade_dwh.dwh_tesoreria (
    metrica String,
    valor String
) ENGINE = MergeTree()
ORDER BY metrica;

CREATE TABLE IF NOT EXISTS globtrade_dwh.dwh_cuentas_por_pagar (
    proveedor String,
    ruc String,
    comprado Float64,
    recibido Float64,
    pagado Float64,
    pendiente Float64
) ENGINE = MergeTree()
ORDER BY (pendiente, proveedor);

CREATE TABLE IF NOT EXISTS globtrade_dwh.etl_sync_meta (
    tabla String,
    filas UInt64,
    synced_at DateTime DEFAULT now()
) ENGINE = ReplacingMergeTree(synced_at)
ORDER BY tabla;
