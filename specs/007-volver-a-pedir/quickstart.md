# Quickstart / Validación: Volver a pedir (007)

**Feature**: [`spec.md`](spec.md) | **Contrato**: [`contracts/reorden-api.md`](contracts/reorden-api.md)

## Prerrequisitos

- Portal B2B en marcha: `http://localhost:8001`
- Cliente demo con al menos un pedido en estado `entregado` (o completar flujo spec 003)
- Credenciales de cliente B2B (registro o seed)

### Arranque

```powershell
docker compose -f infrastructure/compose/docker-compose.yml up -d
# o
python run.py
```

---

## Escenario 1 — Recompra exitosa (P1)

1. Login en `http://localhost:8001/pages/login.html`.
2. Ir a **Mis pedidos** → abrir un pedido en estado **Entregado** (o Pagado/Enviado).
3. Verificar que aparece el botón **Volver a pedir**.
4. Clic en **Volver a pedir**.
5. **Esperado**:
   - Redirección a catálogo con drawer del carrito abierto.
   - Toast de éxito; productos del pedido visibles en el carrito.
   - Precios actuales (no necesariamente iguales al pedido histórico).

---

## Escenario 2 — Botón oculto en estados no elegibles (P1)

1. Abrir detalle de pedido **Pendiente de pago** o **Cancelado**.
2. **Esperado**: no hay botón «Volver a pedir».

---

## Escenario 3 — Omisión por producto inactivo (P1)

**Preparación** (admin `:8000` o SQL): desactivar un producto presente en un pedido entregado del cliente.

1. Volver a pedir ese pedido.
2. **Esperado**:
   - Líneas disponibles en carrito.
   - Toast/aviso listando producto omitido por no disponible.

---

## Escenario 4 — Stock parcial (P2)

**Preparación**: reducir stock del producto por debajo de la cantidad del pedido original (sin llegar a cero).

1. Volver a pedir.
2. **Esperado**:
   - Cantidad en carrito = stock disponible (menor que pedido original).
   - Aviso de cantidad ajustada por stock.

---

## Escenario 5 — Checkout sin regresión (P1)

1. Tras recompra exitosa, desde el drawer ir a **checkout**.
2. Completar los 3 pasos y pago simulado.
3. **Esperado**: nuevo pedido creado; flujo idéntico a spec 003.

---

## Verificación API (PowerShell)

Obtener token:

```powershell
$login = Invoke-RestMethod -Method POST -Uri "http://localhost:8001/api/auth/login" `
  -ContentType "application/json" -Body '{"email":"cliente@demo.com","password":"demo1234"}'
$headers = @{ Authorization = "Bearer $($login.access_token)" }
```

Listar pedidos y recomprar (ajustar `ID_PEDIDO`):

```powershell
$pedidos = Invoke-RestMethod -Uri "http://localhost:8001/api/pedidos" -Headers $headers
$id = $pedidos[0].id_pedido
Invoke-RestMethod -Method POST -Uri "http://localhost:8001/api/pedidos/$id/volver-a-pedir" -Headers $headers
```

**Esperado**: JSON con `resumen` y `carrito`; HTTP 200 si hubo agregados, 422 si ninguno.

---

## Verificación pytest

```powershell
cd apps/portal
pytest gmbackend/tests/test_volver_a_pedir.py -v
```

Casos mínimos del test (a implementar en `/speckit-implement`):

- Recompra feliz → items en carrito
- Producto inactivo → omitido
- Estado no elegible → 422
- Pedido ajeno → 404

---

## Verificación datos (opcional)

```powershell
python -c "
import duckdb
c = duckdb.connect('db/globtrade.duckdb', read_only=True)
print(c.execute('''
  SELECT ci.id_producto, ci.cantidad, ci.precio_congelado
  FROM carrito_items ci
  JOIN carritos ca ON ca.id_carrito = ci.id_carrito
  WHERE ca.estado = 'activo'
  ORDER BY ci.id_item DESC LIMIT 10
''').fetchdf())
"
```

**Esperado**: filas coherentes con la última recompra; stock no negativo en inventario.

---

## Checklist rápido

- [ ] Botón visible solo en estados elegibles
- [ ] Recompra agrega líneas al carrito
- [ ] Omisiones y ajustes informados al usuario
- [ ] Sin cambios en checkout/pago simulado
- [ ] pytest verde
- [ ] Portal `:8001` sigue operativo
