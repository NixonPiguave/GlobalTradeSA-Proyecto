# GlobalTrade S.A. — Monorepo operativo

ERP analítico + portal B2B mayorista en un solo runtime DuckDB compartido.

| Servicio | Puerto | Código |
|----------|--------|--------|
| Panel administrativo | 8000 | `apps/admin/backend` + `apps/admin/web` |
| Portal B2B | 8001 | `apps/portal/gmbackend` + `apps/portal/web` |
| Base de datos | — | `db/globtrade.duckdb` *(local, no versionada)* |
| Inicialización | — | `shared/database/init_sistema.py` |

## Arranque rápido

```powershell
copy .env.example .env
# Edita .env: JWT_SECRET (obligatorio) e IA_API_KEY (opcional, solo para módulo IA)
pip install -r apps/admin/requirements.txt -r apps/portal/requirements.txt
$env:PYTHONPATH="."
$env:DUCKDB_PATH="db/globtrade.duckdb"
python shared/database/init_sistema.py
python run.py
```

> **Seguridad:** `.env` y `db/globtrade.duckdb` no se suben a Git. Tras clonar, copia `.env.example` → `.env` y ejecuta `init_sistema.py` para crear la base local.

- **Admin**: http://localhost:8000  
- **Portal**: http://localhost:8001  

Guía completa: [`docs/quickstart.md`](docs/quickstart.md)

## Cuentas demo

| Rol | Email | Contraseña |
|-----|-------|------------|
| Admin | `admin@globmarket.com` | `12345678` |
| Vendedor | `vendedor@globmarket.com` | `12345678` |
| Almacén | `almacen@globmarket.com` | `12345678` |
| Gerente (informes) | `gerente@globmarket.com` | `12345678` |
| Cliente Walmart | `compras@walmart.com` | `12345678` |
| Cliente Carrefour | `procurement@carrefour.com` | `12345678` |
| Cliente Costco | `sourcing@costco.com` | `12345678` |
| Otros clientes B2B | *(cualquier email registrado)* | `12345678` |

## Funcionalidad por parte

### Parte 2 — Núcleo operativo
- Auth JWT admin, catálogo CRUD, inventario/compras, pedidos ERP
- Portal: carrito, checkout 3 pasos, pago simulado, mis pedidos

### Parte 3 — Cierre (implementado)
- **PDFs**: comprobantes pedido/factura/pago/OC (Jinja2 + ReportLab)
- **Reportes**: ventas, inventario, pedidos, CxC, rentabilidad (PDF/CSV)
- **Analytics**: pedidos portal → `fact_ventas` idempotente; dashboard con filtro **origen**
- **Contabilidad**: asientos automáticos venta/costo/cobro; sección **Finanzas**
- **Logística**: transportistas, envíos y tracking al marcar pedido enviado
- **Marketing portal**: banners y promociones en el landing

## Tests

```powershell
$env:PYTHONPATH=".;apps/admin;apps/portal"
python -m pytest apps/admin/backend/tests apps/portal/gmbackend/tests -q
python -m pytest apps/admin/backend/tests/test_smoke.py -q
```

## Docker

```powershell
docker compose -f docker-compose.unified.yml up --build -d
```

## Estructura

```
apps/admin/          Panel ERP + analytics
apps/portal/         Portal B2B
shared/database/     Init DuckDB
shared/pdf/          Generador PDF
shared/services/     Factura, integración ventas, contabilidad
shared/templates/    HTML comprobantes y reportes
specs/001-.../       Spec Kit activa
docs/                quickstart, modelo-datos
```

## Especificación

Feature Spec Kit: `specs/001-sistema-operativo-completo/`  
Modelo de datos: [`docs/modelo-datos.md`](docs/modelo-datos.md)
