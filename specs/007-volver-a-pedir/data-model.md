# Data Model: Portal B2B — Volver a pedir

**Feature**: `007-volver-a-pedir` | **Date**: 2026-08-29

## Overview

La recompra **no introduce entidades persistentes nuevas**. Lee un pedido histórico y escribe en el carrito activo existente. El resultado estructurado (`agregados`, `omitidos`, `ajustados`) vive en la respuesta API y en feedback UI transitorio.

## Entidades lógicas

### Pedido (fuente)

| Campo relevante | Uso en recompra |
|-----------------|-----------------|
| `id_pedido` | Identificador en URL |
| `id_cliente` | Validación de ownership |
| `estado` | Debe ∈ `{ pagado, preparando, enviado, entregado }` |
| Líneas vía `pedido_detalle` | `id_producto`, `cantidad` por línea |

### Línea de pedido (`pedido_detalle`)

| Campo | Regla |
|-------|-------|
| `id_producto` | FK a `dim_producto` |
| `cantidad` | Cantidad objetivo a replicar |
| `precio_unitario` | Solo lectura histórica; **no** se copia al carrito |

### Carrito activo (`carritos` + `carrito_items`)

| Regla | Detalle |
|-------|---------|
| Un carrito `activo` por cliente | Reutiliza `_carrito_o_crear()` |
| Merge por producto | Si `id_producto` ya existe en carrito, sumar cantidades (cap por stock) |
| Precio congelado | Recalculado con reglas vigentes al escribir |

### Producto (`dim_producto`)

| Condición | Acción recompra |
|-----------|-----------------|
| `activo = false` o fila ausente | Omitir; motivo `no_disponible` |
| Stock zona = 0 | Omitir; motivo `sin_stock` |
| Stock zona < cantidad deseada | Agregar parcial; motivo `stock_parcial` |

### Resumen de recompra (transitorio)

Objeto de respuesta API, no tabla:

```text
ReordenResumen
├── agregados[]   → { id_producto, nombre_producto, cantidad_agregada }
├── omitidos[]    → { id_producto, nombre_producto?, cantidad_solicitada, motivo }
├── ajustados[]   → { id_producto, nombre_producto, cantidad_solicitada, cantidad_agregada, motivo }
└── n_agregados   → int (conteo líneas con cantidad > 0 agregada)
```

## Tablas DuckDB impactadas

| Tabla | Operación | Notas |
|-------|-----------|-------|
| `pedidos` | READ | Filtro `id_cliente`, `estado` |
| `pedido_detalle` | READ | Líneas del pedido |
| `dim_producto` | READ | Activo, nombre, precios |
| `carritos` | READ/WRITE | Crear activo si no existe |
| `carrito_items` | WRITE | INSERT o UPDATE por producto |
| Inventario/stock vía `red_bodegas` | READ | Stock neto por zona cliente |

**Sin migraciones**: no se altera DDL.

## Reglas de estado

### Estados elegibles para recompra

```text
pagado → preparando → enviado → entregado
         ↑____________↑___________↑
         (todos elegibles para «Volver a pedir»)
```

### Estados NO elegibles

- `borrador`, `pendiente_pago`, `cancelado`

### Transiciones

Ninguna transición de pedido ocurre en esta feature. Solo mutación del carrito.

## Validaciones

| ID | Regla |
|----|-------|
| V-701 | `id_pedido` pertenece a `id_cliente` autenticado |
| V-702 | `pedido.estado` ∈ estados elegibles |
| V-703 | No hay otro pedido `pendiente_pago` del cliente (regla carrito existente) |
| V-704 | `cantidad_solicitada` ≥ 1 por línea; líneas con cantidad 0 se ignoran |
| V-705 | Cantidad final en carrito ≤ stock disponible en zona |
| V-706 | Transacción atómica: todo el lote de líneas commit o rollback |

## Relaciones (lectura)

```text
dim_cliente 1──* pedidos 1──* pedido_detalle *──1 dim_producto
dim_cliente 1──* carritos 1──* carrito_items *──1 dim_producto
```

## Impacto en specs previas

- **003**: Extiende Mis pedidos y carrito; no modifica checkout/pago.
- **004/001**: Stock e inventario ya gobernados por `red_bodegas`; sin cambio de contrato admin.
