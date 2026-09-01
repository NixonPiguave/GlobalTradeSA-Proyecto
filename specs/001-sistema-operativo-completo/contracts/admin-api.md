# Contratos API — Panel administrativo (`:8000`)

Prefijo base: `/api`. Autenticación: JWT con rol `admin` (o roles con permiso). Errores: JSON `{ "detail": "mensaje" }` con código HTTP apropiado.

## Autenticación y seguridad (M01)

- `POST /api/auth/login` → `{ email, password }` ⇒ `{ access_token, rol }`. Error genérico en credenciales inválidas.
- `GET /api/auth/me` ⇒ `{ id_usuario, email, nombre, rol }`.
- `GET /api/roles` ⇒ lista de roles y permisos (solo admin).
- `GET /api/auditoria?entidad=&desde=&hasta=` ⇒ registros de auditoría paginados.

## Catálogo (M03)

- `GET /api/categorias` ⇒ lista (incluye inactivas para admin).
- `POST /api/categorias` → `{ nombre, descripcion, id_categoria_padre?, id_item_type? }` ⇒ categoría creada.
- `PUT /api/categorias/{id}` → campos editables.
- `DELETE /api/categorias/{id}` ⇒ soft-delete (`activo=false`).
- `POST /api/categorias/{id}/imagen` (multipart) ⇒ guarda archivo, retorna `imagen_path`.
- `GET /api/productos?categoria=&busqueda=&pagina=&activo=` ⇒ paginado.
- `POST /api/productos` → `{ sku, nombre, descripcion, id_categoria, id_marca, id_unidad, costo_estandar }`.
- `PUT /api/productos/{id}` ; `DELETE /api/productos/{id}` (soft-delete).
- `POST /api/productos/{id}/imagenes` (multipart) ⇒ agrega a `producto_imagenes`.
- `GET/POST/PUT /api/marcas`, `/api/unidades` ⇒ CRUD maestras de catálogo.
- `GET/POST/PUT /api/listas-precios` y `POST /api/listas-precios/{id}/detalle` → `{ id_producto, precio, cantidad_minima }`.

## Compras (M04)

- `GET/POST/PUT /api/proveedores` ⇒ CRUD.
- `GET /api/ordenes-compra?estado=` ; `POST /api/ordenes-compra` → `{ id_proveedor, lineas:[{id_producto,cantidad,costo_unitario}] }`.
- `POST /api/ordenes-compra/{id}/aprobar`.
- `POST /api/ordenes-compra/{id}/recepcion` → `{ id_almacen, lineas:[{id_producto,cantidad_recibida,codigo_lote,fecha_vencimiento}] }` ⇒ incrementa stock + movimiento.

## Inventario (M05)

- `GET /api/inventario/stock?almacen=&producto=` ⇒ stock por producto/almacén.
- `POST /api/inventario/ajuste` → `{ id_producto, id_almacen, cantidad, motivo }` ⇒ movimiento tipo `ajuste`.
- `POST /api/inventario/transferencia` → `{ origen, destino, lineas }`.
- `GET /api/inventario/alertas` ⇒ productos bajo umbral.
- `GET/POST /api/almacenes`.

## Clientes / CRM (M06)

- `GET /api/clientes?busqueda=&pagina=` ; `GET /api/clientes/{id}` ⇒ datos, contactos, direcciones, historial de pedidos, saldo CxC.
- `GET /api/clientes/{id}/cxc` ⇒ movimientos de cuenta por cobrar.

## Pedidos (M07)

- `GET /api/pedidos?estado=&cliente=&pagina=` ⇒ paginado.
- `GET /api/pedidos/{id}` ⇒ cabecera, detalle, historial de estados, pagos.
- `POST /api/pedidos/{id}/estado` → `{ estado_nuevo }` ⇒ valida transición, registra historial. Al pasar a `pagado`/`enviado` dispara efectos (factura, reserva/descuento stock, integración analítica, asiento).
- `POST /api/pedidos/{id}/factura` ⇒ genera factura y su comprobante.

## Tesorería (M08)

- `GET /api/pagos?estado=` ; `GET /api/cuentas-bancarias` ; `GET /api/tesoreria/movimientos`.

## Contabilidad mínima (M09)

- `GET /api/contabilidad/asientos?desde=&hasta=` ⇒ asientos y líneas.
- `GET /api/contabilidad/resumen?desde=&hasta=` ⇒ `{ ingresos, costos, margen }` (vista_resumen_financiero).

## Analytics (M11)

- `GET /api/dashboard/kpis?desde=&hasta=&region=&origen=` ⇒ KPIs (soporta filtro `origen=historico|portal`).
- `GET /api/dashboard/graficas?...` ⇒ series para Chart.js.
- `POST /api/integracion/pedidos` ⇒ integra pedidos confirmados pendientes a `fact_ventas` (idempotente).

## Respuestas comunes

- Paginado: `{ items: [...], total, pagina, por_pagina }`.
- Creación: `201` con entidad; validación fallida: `422`; permiso denegado: `403`; no encontrado: `404`.
