# Quickstart / Validación: GlobalTradeSA

Guía de verificación por partes. Cada checkpoint corresponde a specs del roadmap Spec Kit:

| Checkpoint | Spec(s) |
|------------|---------|
| Parte 1 — Fundación | [`001`](spec.md) |
| Parte 2 — Núcleo operativo | [`003`](../003-portal-b2b-carrito-checkout/spec.md), [`004`](../004-admin-operativo-catalogo-inventario/spec.md) |
| Parte 3 — Cierre documental | [`005`](../005-comprobantes-reportes-pdf/spec.md), [`006`](../006-analytics-contabilidad-integracion/spec.md) |
| Profesionalización | [`002`](../002-reestructuracion-profesional/spec.md) |

Cada parte tiene un checkpoint que debe pasar antes de continuar.

## Prerrequisitos

- Windows con PowerShell y Docker Desktop en ejecución.
- Repositorio en la raíz del proyecto.

## Arranque del runtime unificado

```powershell
docker compose -f infrastructure/compose/docker-compose.yml up --build -d
```

- Panel administrativo: http://localhost:8000
- Portal de ventas: http://localhost:8001

Para desarrollo local sin Docker:

```powershell
python run.py
```

---

## Checkpoint Parte 1 — Fundación

1. El contenedor levanta y ambos puertos responden HTTP 200.
2. Verificar tablas creadas en DuckDB:

```powershell
python -c "import duckdb; c=duckdb.connect('db/globtrade.duckdb'); print(len(c.execute(\"select table_name from information_schema.tables\").fetchall()), 'tablas')"
```

3. Verificar histórico cargado:

```powershell
python -c "import duckdb; c=duckdb.connect('db/globtrade.duckdb'); print(c.execute('select count(*) from fact_ventas').fetchone())"
```

Esperado: ~80+ tablas y hasta 100.000 filas históricas.

---

## Checkpoint Parte 2 — Núcleo operativo

**Admin (`:8000`)**:
1. Iniciar sesión como administrador.
2. Crear una categoría y un producto con imagen y precios.
3. Registrar un proveedor, una orden de compra y su recepción; verificar aumento de stock.

**Portal (`:8001`)**:
4. Registrar una empresa e iniciar sesión.
5. Verificar que el producto creado aparece en el catálogo.
6. Agregar al carrito, completar checkout en 3 pasos y confirmar pago simulado.
7. Verificar que el pedido aparece en "Mis pedidos" y en el panel admin.

**Datos**:
```powershell
python -c "import duckdb; c=duckdb.connect('db/globtrade.duckdb'); print(c.execute('select count(*) from pedidos').fetchone(), c.execute('select count(*) from pagos').fetchone())"
```

Esperado: flujo de compra completo funcional; stock descontado sin quedar negativo.

---

## Checkpoint Parte 3 — Cierre

1. Descargar el comprobante PDF del pedido y de la factura desde el portal y el panel.
2. Descargar un reporte de ventas en PDF y en CSV desde el panel.
3. Verificar integración analítica (sin duplicados):

```powershell
python -c "import duckdb; c=duckdb.connect('db/globtrade.duckdb'); print(c.execute(\"select origen, count(*) from fact_ventas group by origen\").fetchall())"
```

4. Verificar asientos y resumen financiero:

```powershell
python -c "import duckdb; c=duckdb.connect('db/globtrade.duckdb'); print(c.execute('select count(*) from asientos_contables').fetchone())"
```

5. Reejecutar la integración de pedidos y confirmar que el conteo de `fact_ventas` (origen `portal`) no cambia (idempotencia).

Esperado: comprobantes PDF válidos, reportes exportados, dashboard con histórico + portal, asientos generados, sin duplicados.

---

## Regresión de flujos existentes

- Login del portal, catálogo y detalle de producto funcionan.
- Dashboard analítico responde con KPIs y gráficas.
- El arranque Docker no requiere reparación manual de datos.
