# Research: Sistema Operativo Completo GlobalTradeSA

Decisiones tomadas antes del diseño. Formato: Decisión / Justificación / Alternativas descartadas.

## R1 — Conservación del histórico de ventas

- **Decisión**: Cargar hasta 100.000 filas de `data/ventas.parquet` en `fact_ventas` con `id_producto = NULL` y `origen = 'historico'`. Los pedidos nuevos escriben filas con `id_producto` y `origen = 'portal'`.
- **Justificación**: El histórico representa ventas pasadas a nivel categoría (`item_type`); mantenerlo preserva el dashboard existente y da volumen realista. Añadir `id_producto` nullable evita migraciones destructivas.
- **Alternativas descartadas**: Empezar de cero (pierde el dashboard y el realismo); mantener dos tablas separadas (duplica lógica de reporting).

## R2 — Almacenamiento de imágenes

- **Decisión**: Guardar imágenes como archivos en `shared/storage/uploads/productos/` y persistir solo la ruta en `producto_imagenes.imagen_path`. Servir vía endpoint estático del admin.
- **Justificación**: DuckDB no es adecuado para binarios grandes; los archivos en volumen persisten entre reinicios y no requieren API keys.
- **Alternativas descartadas**: Cloudinary/CDN (requiere cuenta y claves, innecesario para demo); binarios en DuckDB (mal rendimiento y tamaño).

## R3 — Generación de PDF

- **Decisión**: Plantillas HTML con Jinja2 renderizadas a PDF con WeasyPrint; ReportLab como fallback si WeasyPrint no está disponible en el contenedor. PDF guardado en `shared/storage/comprobantes/` con ruta en `comprobantes.pdf_path`.
- **Justificación**: HTML/CSS permite comprobantes visualmente fieles y fáciles de mantener; guardar en disco permite regenerar y descargar.
- **Alternativas descartadas**: Generar PDF en frontend (menos control, sin registro); solo HTML sin PDF (no cumple requisito de comprobante descargable).

## R4 — Runtime y concurrencia DuckDB

- **Decisión**: Ejecutar admin y portal en un único proceso (`run.py`) dentro del contenedor unificado; DuckDB con un solo escritor.
- **Justificación**: DuckDB es single-writer por archivo; el runtime unificado ya resuelve esto y comparte datos entre ambas apps.
- **Alternativas descartadas**: Dos contenedores sobre el mismo archivo (riesgo de corrupción); bases separadas (impide compartir catálogo y ventas).

## R5 — Modelo de precios y categorías

- **Decisión**: Precio en `lista_precio_detalle` por producto y segmento (público/mayorista) con cantidad mínima; la categoría no tiene precio operativo.
- **Justificación**: Es el patrón de ERPs/marketplaces reales (SAP B1, Magento); evita ambigüedad y permite precios diferenciados B2B.
- **Alternativas descartadas**: Precio en categoría (irreal, no permite variación por producto); precio único por producto (no soporta segmentos).

## R6 — Contabilidad

- **Decisión**: Contabilidad mínima con 3 tablas (plan de cuentas, asientos, líneas) y una vista de resumen; asientos automáticos al confirmar venta y al cobrar. Impuesto como campo en factura, no módulo.
- **Justificación**: El usuario pidió explícitamente no profundizar en contabilidad; se prioriza el resto del sistema.
- **Alternativas descartadas**: Módulo contable completo (periodos, centros de costo, balances) — fuera de alcance.

## R7 — Reorganización de carpetas

- **Decisión**: Migrar a `apps/admin`, `apps/portal`, `shared/`, `infrastructure/` en la Parte 1, actualizando imports, `run.py`, Docker y configs en el mismo paso.
- **Justificación**: Estructura profesional y mantenible; hacerlo al inicio evita romper imports a mitad del proyecto.
- **Alternativas descartadas**: Renombrado gradual (deja el repo en estado inconsistente por más tiempo).

## R8 — Ejecución por partes

- **Decisión**: Una sola spec/plan/tasks; implementación en 3 partes secuenciales con checkpoints verificables.
- **Justificación**: El alcance (~82 tablas, dos apps) es grande; dividir reduce riesgo de contexto y facilita verificación.
- **Alternativas descartadas**: Todo en una sola sesión (frágil, difícil de verificar); más de 4 partes (overhead innecesario).
