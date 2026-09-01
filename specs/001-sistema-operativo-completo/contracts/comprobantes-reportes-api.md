# Contratos API — Comprobantes y reportes (M13)

Disponibles en ambas apps según permiso: el cliente accede a sus propios comprobantes; el admin a todos y a los reportes.

## Comprobantes PDF

- `GET /api/comprobantes/{tipo}/{entidad_id}/pdf` ⇒ devuelve el PDF (genera si no existe, reutiliza `pdf_path` si ya existe).
  - `tipo` ∈ `cotizacion`, `pedido`, `factura`, `comprobante_pago`, `guia_remision`, `orden_compra`, `nota_credito`.
  - Respuesta: `application/pdf` (stream) con `Content-Disposition: attachment`.
  - Autorización: cliente solo si el comprobante pertenece a su cliente; admin siempre.
- `GET /api/comprobantes?tipo=&entidad_id=` ⇒ metadatos del comprobante (`serie`, `numero`, `fecha_generacion`, `pdf_path`).

### Numeración

Cada `tipo` tiene serie por año en `comprobante_series`; el número se incrementa de forma atómica. Formato visible: `PED-2026-000001`, `FAC-2026-000001`, `PAG-2026-000001`, etc.

### Contenido mínimo por PDF

- Encabezado: nombre del negocio, tipo y número de comprobante, fecha.
- Datos del cliente/proveedor según corresponda.
- Tabla de líneas: producto, cantidad, precio, subtotal.
- Totales: subtotal, impuesto (cuando aplique), total.

## Reportes exportables (solo admin)

- `GET /api/reportes/ventas?desde=&hasta=&categoria=&region=&origen=&formato=pdf|csv`.
- `GET /api/reportes/inventario-valorizado?almacen=&formato=pdf|csv`.
- `GET /api/reportes/pedidos-por-estado?desde=&hasta=&formato=pdf|csv`.
- `GET /api/reportes/clientes-cxc?formato=pdf|csv`.
- `GET /api/reportes/rentabilidad-producto?desde=&hasta=&formato=pdf|csv`.
- `GET /api/reportes/resumen-financiero?desde=&hasta=&formato=pdf`.

Respuesta:
- `formato=pdf` ⇒ `application/pdf`.
- `formato=csv` ⇒ `text/csv` con encabezados de columna.

Cada listado del panel expone botones "Descargar PDF" y "Exportar CSV" que consumen estos endpoints con los filtros activos.
