# Data Model: Sistema Operativo Completo GlobalTradeSA

Modelo unificado en DuckDB (`db/globtrade.duckdb`). ~82 tablas físicas + vistas, en 13 módulos. DDL implementado en `shared/database/init_sistema.py` (idempotente, `CREATE TABLE IF NOT EXISTS`, secuencias `CREATE SEQUENCE IF NOT EXISTS`).

Convenciones:
- PK entera con `SEQUENCE` + `nextval` (compatibilidad Windows/DuckDB).
- Montos `DECIMAL(12,2)`; costos/cantidades `DECIMAL(12,4)` donde aplique.
- Marcas de tiempo `TIMESTAMP DEFAULT current_timestamp`.
- Soft-delete con `activo BOOLEAN` en maestras.
- FKs lógicas (DuckDB no siempre aplica FK); integridad garantizada en la capa de servicio.

---

## M01 — Seguridad (6 tablas)

- **roles**: `id_rol` PK, `nombre` UNIQUE (`admin`,`vendedor`,`almacen`,`cliente`), `descripcion`.
- **permisos**: `id_permiso` PK, `codigo` UNIQUE (`productos.crear`, `pedidos.aprobar`, ...), `descripcion`.
- **rol_permiso**: `id_rol`, `id_permiso` (N:M).
- **usuarios**: `id_usuario` PK, `email` UNIQUE, `password_hash`, `nombre`, `activo`, `fecha_registro`. (Evoluciona la tabla actual.)
- **usuario_rol**: `id_usuario`, `id_rol` (N:M).
- **auditoria_log**: `id_log` PK, `id_usuario`, `entidad`, `entidad_id`, `accion`, `valor_anterior`, `valor_nuevo`, `fecha`.
- **configuracion_sistema**: `clave` PK, `valor`, `descripcion` (IVA%, mínimo mayorista, moneda default, series).

## M02 — Maestras (8 tablas)

- **dim_region**: `id_region` PK, `region` UNIQUE. (Existe.)
- **dim_country**: `id_country` PK, `country`, `id_region`. (Existe.)
- **dim_sales_channel**: `id_channel` PK, `sales_channel` UNIQUE. (Existe.)
- **dim_order_priority**: `id_priority` PK, `order_priority` UNIQUE. (Existe.)
- **monedas**: `id_moneda` PK, `codigo` UNIQUE (USD/PEN/EUR), `simbolo`, `nombre`.
- **tipos_cambio**: `id_tc` PK, `id_moneda`, `fecha`, `tasa`.
- **zonas_envio**: `id_zona` PK, `nombre`, `costo_base`.
- **calendario_operativo**: `fecha` PK, `es_habil`, `descripcion`.

## M03 — Catálogo / PIM (11 tablas)

- **categorias**: `id_categoria` PK, `nombre`, `slug` UNIQUE, `descripcion`, `id_categoria_padre` (nullable), `imagen_path`, `activo`, `id_item_type` (mapeo al histórico). Sin precio.
- **marcas**: `id_marca` PK, `nombre` UNIQUE, `activo`.
- **unidades_medida**: `id_unidad` PK, `nombre` (unidad/caja/pallet), `factor_conversion`.
- **productos**: `id_producto` PK, `sku` UNIQUE, `nombre`, `descripcion`, `id_categoria`, `id_marca`, `id_unidad`, `costo_estandar`, `activo`. (Evoluciona `dim_producto`.)
- **producto_categorias**: `id_producto`, `id_categoria` (N:M; categoría principal en `productos.id_categoria`).
- **producto_variantes**: `id_variante` PK, `id_producto`, `nombre` (500ml/1L/pack x12), `sku_variante`, `factor`.
- **atributos_definicion**: `id_atributo` PK, `nombre` (orgánico, refrigerado), `tipo`.
- **producto_atributos**: `id_producto`, `id_atributo`, `valor`.
- **producto_imagenes**: `id_imagen` PK, `id_producto`, `imagen_path`, `es_principal`, `orden`.
- **listas_precios**: `id_lista` PK, `nombre` (público, mayorista, distribuidor), `id_moneda`, `activo`.
- **lista_precio_detalle**: `id_detalle` PK, `id_lista`, `id_producto`, `precio`, `cantidad_minima`.

## M04 — Compras (7 tablas)

- **proveedores**: `id_proveedor` PK, `razon_social`, `ruc`, `id_country`, `condiciones_pago`, `activo`.
- **proveedor_contactos**: `id_contacto` PK, `id_proveedor`, `nombre`, `email`, `telefono`.
- **ordenes_compra**: `id_oc` PK, `numero`, `id_proveedor`, `fecha`, `estado` (`borrador`/`aprobada`/`recibida`/`cancelada`), `total`.
- **orden_compra_detalle**: `id_detalle` PK, `id_oc`, `id_producto`, `cantidad`, `costo_unitario`, `subtotal`.
- **recepciones_compra**: `id_recepcion` PK, `id_oc`, `fecha`, `id_almacen`, `estado`.
- **recepcion_compra_detalle**: `id_detalle` PK, `id_recepcion`, `id_producto`, `cantidad_recibida`, `id_lote`.
- **devoluciones_proveedor**: `id_devolucion` PK, `id_oc`, `fecha`, `motivo`, `total`.

## M05 — Inventario (9 tablas)

- **almacenes**: `id_almacen` PK, `nombre`, `direccion`, `activo`.
- **ubicaciones_almacen**: `id_ubicacion` PK, `id_almacen`, `codigo` (pasillo/estante).
- **stock_almacen**: `id_stock` PK, `id_producto`, `id_almacen`, `cantidad_disponible`, `cantidad_reservada`. UNIQUE(`id_producto`,`id_almacen`).
- **lotes_inventario**: `id_lote` PK, `id_producto`, `codigo_lote`, `fecha_vencimiento`, `cantidad`.
- **movimientos_inventario**: `id_movimiento` PK, `tipo` (`entrada`/`salida`/`ajuste`/`transferencia`), `fecha`, `referencia`, `id_usuario`.
- **movimiento_inventario_detalle**: `id_detalle` PK, `id_movimiento`, `id_producto`, `id_almacen`, `id_lote`, `cantidad`.
- **reservas_stock**: `id_reserva` PK, `id_pedido`, `id_producto`, `id_almacen`, `cantidad`, `estado` (`activa`/`liberada`/`consumida`).
- **transferencias_almacen**: `id_transferencia` PK, `id_almacen_origen`, `id_almacen_destino`, `fecha`, `estado`.
- **alertas_stock**: `id_alerta` PK, `id_producto`, `id_almacen`, `umbral_minimo`, `activa`.

## M06 — CRM (8 tablas)

- **clientes**: `id_cliente` PK, `id_usuario`, `nombre_empresa`, `ruc`, `id_country`, `telefono`, `activo`. (Evoluciona `dim_cliente`.)
- **cliente_contactos**: `id_contacto` PK, `id_cliente`, `nombre`, `cargo`, `email`, `telefono`.
- **cliente_direcciones**: `id_direccion` PK, `id_cliente`, `tipo` (`fiscal`/`entrega`/`facturacion`), `direccion`, `ciudad`, `id_country`, `predeterminada`.
- **grupos_cliente**: `id_grupo` PK, `nombre` (minorista/mayorista/distribuidor), `id_lista` (lista de precios asociada).
- **cliente_grupo**: `id_cliente`, `id_grupo` (N:M).
- **condiciones_credito**: `id_condicion` PK, `id_cliente`, `dias_pago`, `limite_credito`, `bloqueado`.
- **cuenta_corriente_cliente**: `id_cliente` PK, `saldo`.
- **movimientos_cxc**: `id_movimiento` PK, `id_cliente`, `tipo` (`cargo`/`abono`), `id_factura` o `id_pago`, `monto`, `fecha`.

## M07 — Ventas (13 tablas)

- **cotizaciones**: `id_cotizacion` PK, `numero`, `id_cliente`, `fecha`, `estado`, `total`, `validez`.
- **cotizacion_detalle**: `id_detalle` PK, `id_cotizacion`, `id_producto`, `cantidad`, `precio`, `subtotal`.
- **carritos**: `id_carrito` PK, `id_cliente`, `estado` (`activo`/`convertido`/`abandonado`), `fecha`. UNIQUE por cliente activo.
- **carrito_items**: `id_item` PK, `id_carrito`, `id_producto`, `cantidad`, `precio_congelado`, `subtotal`.
- **pedidos**: `id_pedido` PK, `numero`, `id_cliente`, `id_direccion_entrega`, `id_country`, `id_channel`, `id_priority`, `fecha_pedido`, `estado`, `subtotal`, `impuesto_monto`, `total`, `notas`.
- **pedido_detalle**: `id_detalle` PK, `id_pedido`, `id_producto`, `cantidad`, `precio_unitario`, `costo_unitario`, `subtotal`.
- **pedido_estados_historial**: `id_historial` PK, `id_pedido`, `estado_anterior`, `estado_nuevo`, `id_usuario`, `fecha`.
- **facturas_venta**: `id_factura` PK, `numero`, `id_pedido`, `id_cliente`, `fecha`, `subtotal`, `impuesto_monto`, `total`, `estado`.
- **factura_venta_detalle**: `id_detalle` PK, `id_factura`, `id_producto`, `cantidad`, `precio_unitario`, `subtotal`.
- **envios**: `id_envio` PK, `id_pedido`, `id_transportista`, `fecha_despacho`, `estado`, `id_zona`.
- **envio_detalle**: `id_detalle` PK, `id_envio`, `id_producto`, `cantidad`, `id_lote`.
- **guias_remision**: `id_guia` PK, `numero`, `id_envio`, `fecha`.
- **devoluciones_cliente**: `id_devolucion` PK, `id_pedido`, `fecha`, `motivo`, `total`, `estado`.

### Máquina de estados del pedido

`borrador → pendiente_pago → pagado → preparando → enviado → entregado`; con `cancelado` alcanzable desde `pendiente_pago`, `pagado` o `preparando`. Transiciones inválidas rechazadas por el servicio; cada cambio registra fila en `pedido_estados_historial`.

## M08 — Tesorería (5 tablas)

- **metodos_pago**: `id_metodo` PK, `nombre` (`simulado`/`transferencia`/`credito`), `activo`.
- **pagos**: `id_pago` PK, `numero`, `id_pedido`, `id_factura` (nullable), `id_metodo`, `monto`, `estado` (`pendiente`/`aprobado`/`rechazado`), `referencia`, `fecha`.
- **cuentas_bancarias**: `id_cuenta` PK, `nombre` (Caja/Banco), `saldo`.
- **movimientos_tesoreria**: `id_movimiento` PK, `id_cuenta`, `tipo` (`ingreso`/`egreso`), `monto`, `id_pago`, `fecha`.
- **conciliaciones_pago**: `id_conciliacion` PK, `id_pago`, `monto_esperado`, `monto_recibido`, `estado`.

## M09 — Contabilidad mínima (3 tablas + vista)

- **plan_cuentas**: `id_cuenta` PK, `codigo` UNIQUE, `nombre`, `tipo` (`activo`/`pasivo`/`ingreso`/`costo`). Semilla: Caja, Cuentas por cobrar, Ingresos por ventas, Costo de ventas, Inventario.
- **asientos_contables**: `id_asiento` PK, `numero`, `fecha`, `descripcion`, `id_pedido` (nullable), `id_factura` (nullable), `total`.
- **asiento_lineas**: `id_linea` PK, `id_asiento`, `id_cuenta`, `debe`, `haber`.
- **vista_resumen_financiero** (VIEW): ingresos, costos y margen del periodo agregando `asiento_lineas` por tipo de cuenta.

## M10 — Logística (4 tablas)

- **transportistas**: `id_transportista` PK, `nombre`, `activo`.
- **tarifas_envio**: `id_tarifa` PK, `id_zona`, `peso_max`, `costo`.
- **rutas_envio**: `id_ruta` PK, `nombre`, `id_zona`.
- **tracking_eventos**: `id_evento` PK, `id_envio`, `estado` (`recolectado`/`en_transito`/`entregado`), `fecha`, `descripcion`.

## M11 — Analytics (6 tablas + vistas)

- **fact_ventas**: existente, EXTENDIDA con `id_producto` (nullable) y `origen` (`historico`/`portal`). Mantiene `order_id` UNIQUE.
- **fact_compras**: `id_compra` PK, `id_oc`, `id_producto`, `cantidad`, `costo`, `fecha`.
- **dim_tiempo**: `fecha` PK, `anio`, `mes`, `trimestre`, `dia_semana` (opcional para reportes).
- **ventas** (VIEW): existente, extendida con JOIN opcional a `productos` para nombre SKU.
- **etl_jobs**: `id_job` PK, `tipo`, `estado`, `fecha_inicio`, `fecha_fin`.
- **etl_job_logs**: `id_log` PK, `id_job`, `mensaje`, `fecha`.
- **vista_rentabilidad_producto** (VIEW): margen por SKU (ingreso − costo).
- **vista_stock_valorizado** (VIEW): stock × costo por producto/almacén.

## M12 — Portal / marketing (4 tablas)

- **banners_portal**: `id_banner` PK, `titulo`, `imagen_path`, `enlace`, `activo`, `orden`.
- **promociones**: `id_promocion` PK, `nombre`, `descuento_pct`, `fecha_inicio`, `fecha_fin`, `activa`.
- **promocion_productos**: `id_promocion`, `id_producto`.
- **wishlist_items**: `id_item` PK, `id_cliente`, `id_producto`, `fecha`.

## M13 — Comprobantes y reportes (2 tablas)

- **comprobantes**: `id_comprobante` PK, `tipo` (`cotizacion`/`pedido`/`factura`/`comprobante_pago`/`guia_remision`/`orden_compra`/`nota_credito`), `serie`, `numero`, `entidad_tipo`, `entidad_id`, `pdf_path`, `fecha_generacion`, `id_usuario`.
- **comprobante_series**: `id_serie` PK, `tipo`, `serie`, `anio`, `ultimo_numero`. (Numeración correlativa; incremento atómico.)

Los reportes exportables (ventas, inventario valorizado, pedidos por estado, clientes/CxC, rentabilidad, resumen financiero) se generan on-demand desde las vistas/tablas anteriores; no requieren tabla propia salvo el registro opcional en `comprobantes`.

---

## Conteo por módulo

| Módulo | Tablas |
|--------|--------|
| M01 | 7 |
| M02 | 8 |
| M03 | 11 |
| M04 | 7 |
| M05 | 9 |
| M06 | 8 |
| M07 | 13 |
| M08 | 5 |
| M09 | 3 (+1 vista) |
| M10 | 4 |
| M11 | 6 (+3 vistas) |
| M12 | 4 |
| M13 | 2 |
| **Total** | **~87 tablas + vistas** |

## Reglas de datos transversales

- Toda inicialización y semilla es idempotente.
- `fact_ventas.order_id` UNIQUE evita duplicar ventas al integrar pedidos.
- El stock (`stock_almacen`) nunca queda negativo; reservas y descuentos son atómicos por servicio.
- Las contraseñas se guardan con hash; nunca en texto plano.
- Series de comprobantes incrementan de forma atómica para evitar números repetidos.
