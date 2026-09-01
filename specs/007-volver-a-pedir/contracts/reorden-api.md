# Contrato API — Reorden / Volver a pedir (Portal `:8001`)

**Feature**: `007-volver-a-pedir`  
**Base**: [`001/contracts/portal-api.md`](../../001-sistema-operativo-completo/contracts/portal-api.md)  
**Auth**: JWT cliente (`Authorization: Bearer <token>`)

## Endpoint

### `POST /api/pedidos/{id_pedido}/volver-a-pedir`

Replica las líneas de un pedido histórico elegible al carrito activo del cliente autenticado.

**Path params**

| Param | Tipo | Descripción |
|-------|------|-------------|
| `id_pedido` | int | ID del pedido a recomprar |

**Request body**: vacío (sin body).

**Precondiciones**

- Usuario autenticado con ficha cliente B2B.
- Pedido existe y `pedido.id_cliente` = cliente del token.
- `pedido.estado` ∈ `{ pagado, preparando, enviado, entregado }`.
- No hay pedido `pendiente_pago` bloqueando el carrito (misma regla que carrito CRUD).

**Response 200** — al menos una línea agregada

```json
{
  "id_pedido": 42,
  "numero": "PED-2026-0042",
  "resumen": {
    "agregados": [
      {
        "id_producto": 101,
        "nombre_producto": "Arroz premium 25kg",
        "cantidad_solicitada": 10,
        "cantidad_agregada": 10
      }
    ],
    "omitidos": [
      {
        "id_producto": 205,
        "nombre_producto": "Aceite girasol 1L",
        "cantidad_solicitada": 5,
        "motivo": "sin_stock"
      }
    ],
    "ajustados": [
      {
        "id_producto": 310,
        "nombre_producto": "Azúcar blanca 50kg",
        "cantidad_solicitada": 20,
        "cantidad_agregada": 12,
        "motivo": "stock_parcial"
      }
    ],
    "n_agregados": 2
  },
  "carrito": {
    "id_carrito": 7,
    "items": [],
    "subtotal": 0,
    "total": 0,
    "n_items": 0
  },
  "redirigir_carrito": true
}
```

> `carrito` sigue la forma de `GET /api/carrito` (spec 003).

**Response 422** — ninguna línea agregada

```json
{
  "detail": {
    "message": "No se pudo agregar ningún producto al carrito.",
    "resumen": {
      "agregados": [],
      "omitidos": [],
      "ajustados": [],
      "n_agregados": 0
    }
  }
}
```

**Errores**

| HTTP | Condición | `detail` |
|------|-----------|----------|
| 401 | Sin token / token inválido | Estándar auth |
| 403 | Usuario sin ficha cliente | `"La cuenta no tiene ficha de cliente B2B."` |
| 404 | Pedido inexistente o de otro cliente | `"Pedido no encontrado."` |
| 422 | Estado no elegible | `"Este pedido no permite volver a pedir (estado: cancelado)."` |
| 422 | Bloqueo por pendiente_pago | Mensaje existente del carrito |
| 422 | Cero líneas agregadas | Ver body arriba |

## Motivos de omisión/ajuste

| Código | Significado |
|--------|-------------|
| `no_disponible` | Producto inactivo o eliminado del catálogo |
| `sin_stock` | Stock cero en bodegas de la zona del cliente |
| `stock_parcial` | Se agregó menos unidades que las solicitadas por límite de stock |

## Reglas de negocio (API)

1. Precios en carrito = vigentes al momento de la recompra, no históricos del pedido.
2. Si el producto ya está en carrito, las cantidades se combinan antes de validar stock.
3. La operación es atómica: un fallo interno hace rollback de todas las líneas del lote.
4. No modifica el pedido origen ni crea pedido nuevo.
5. Idempotencia: dos POST consecutivos intencionales suman cantidades (igual que agregar desde catálogo); la UI debe prevenir doble clic accidental.

## Contrato UI (Mis pedidos)

| Elemento | Regla |
|----------|-------|
| Botón «Volver a pedir» | Visible si `estado` ∈ estados elegibles |
| Clic exitoso | Redirect `/pages/catalogo.html?carrito=1` + toasts desde `resumen` |
| Clic sin agregados | Toast error; permanece en Mis pedidos |
| Loading | Botón deshabilitado mientras POST en vuelo |

## Verificación

Ver [quickstart.md](../quickstart.md).
