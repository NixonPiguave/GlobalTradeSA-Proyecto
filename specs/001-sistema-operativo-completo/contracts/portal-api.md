# Contratos API — Portal de ventas B2B (`:8001`)

Prefijo base: `/api`. Autenticación: JWT de cliente (rol `cliente`). El catálogo público no requiere token; precios mayoristas y carrito sí.

## Autenticación (M01/M06)

- `POST /api/auth/registro` → `{ email, password, nombre_empresa, ruc, pais, telefono }` ⇒ crea usuario (rol cliente) + cliente. Error si email duplicado.
- `POST /api/auth/login` → `{ email, password }` ⇒ `{ access_token }`. Error genérico si inválido.
- `GET /api/auth/me` ⇒ perfil de empresa autenticado.

## Catálogo público (M03/M12)

- `GET /api/categorias` ⇒ solo categorías activas con productos.
- `GET /api/productos?categoria=&busqueda=&pagina=` ⇒ solo productos activos; precio público visible siempre, precio mayorista solo si autenticado.
- `GET /api/productos/{id}` ⇒ detalle con imágenes, atributos, precios y cantidad mínima mayorista.
- `GET /api/banners` ; `GET /api/promociones` ⇒ contenido de marketing activo.

## Carrito (M07)

- `GET /api/carrito` ⇒ carrito activo del cliente con items y totales.
- `POST /api/carrito/items` → `{ id_producto, cantidad }` ⇒ agrega/actualiza con precio congelado de lista mayorista.
- `PUT /api/carrito/items/{id}` → `{ cantidad }` ; `DELETE /api/carrito/items/{id}`.
- `DELETE /api/carrito` ⇒ vacía el carrito.

## Checkout y pago simulado (M07/M08)

- `POST /api/checkout/validar` ⇒ valida stock y cantidad mínima mayorista; retorna resumen o errores por línea.
- `POST /api/checkout/confirmar` → `{ id_direccion_entrega, notas? }` ⇒ crea pedido en `pendiente_pago`, retorna `id_pedido` y total.
- `POST /api/pagos/simular` → `{ id_pedido }` ⇒ registra pago `aprobado`, avanza pedido a `pagado`, dispara efectos (factura, reserva/descuento stock, integración analítica, asiento) y vacía el carrito.

## Perfil y direcciones (M06)

- `GET/PUT /api/perfil` ⇒ datos de empresa.
- `GET/POST/PUT/DELETE /api/perfil/direcciones` ⇒ CRUD de direcciones.
- `GET/POST/DELETE /api/wishlist` ⇒ favoritos.

## Mis pedidos (M07/M13)

- `GET /api/pedidos` ⇒ pedidos del cliente con estado, total, fecha (lista).
- `GET /api/pedidos/{id}` ⇒ detalle + línea de tiempo de estados.
- `POST /api/pedidos/{id}/volver-a-pedir` ⇒ replica líneas elegibles al carrito activo; respuesta con `resumen` (agregados/omitidos/ajustados) y `carrito`. Requiere pedido en estado `pagado`, `preparando`, `enviado` o `entregado`. HTTP 422 si ninguna línea se agregó.
- Descarga de comprobantes vía contratos de comprobantes (ver `comprobantes-reportes-api.md`).

## Reglas de validación

- Cantidad mínima mayorista por producto obligatoria antes de confirmar.
- Stock disponible verificado en `validar` y de nuevo (atómico) en `pagos/simular`.
- Un cliente solo ve y opera sus propios carritos, pedidos, direcciones y comprobantes.
