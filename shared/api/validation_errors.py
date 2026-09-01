"""
validation_errors.py — Traduce errores de validación Pydantic/FastAPI a español.

Usado por los manejadores globales de excepciones del admin y del portal B2B.
"""

from __future__ import annotations

import re
from typing import Any

# Etiquetas legibles para campos frecuentes en body/query/path
FIELD_LABELS: dict[str, str] = {
    "nombre_producto": "Nombre del producto",
    "nombre_empresa": "Nombre de empresa",
    "razon_social": "Razón social",
    "descripcion": "Descripción",
    "id_producto": "Producto",
    "id_proveedor": "Proveedor",
    "id_item_type": "Categoría",
    "id_marca": "Marca",
    "id_linea": "Línea",
    "id_almacen": "Almacén",
    "id_cliente": "Cliente",
    "id_pedido": "Pedido",
    "id_lista": "Lista de precios",
    "id_catalogo": "Catálogo",
    "id_grupo": "Grupo comercial",
    "id_country": "País",
    "id_transportista": "Transportista",
    "precio_unitario": "Precio unitario",
    "precio_mayorista": "Precio mayorista",
    "precio": "Precio",
    "costo_unitario": "Costo unitario",
    "cantidad": "Cantidad",
    "cantidad_minima": "Cantidad mínima",
    "stock_minimo": "Stock mínimo",
    "umbral_minimo": "Umbral mínimo",
    "motivo": "Motivo",
    "metodo_pago": "Método de pago",
    "email": "Correo electrónico",
    "password": "Contraseña",
    "password_actual": "Contraseña actual",
    "password_nueva": "Nueva contraseña",
    "pais": "País",
    "telefono": "Teléfono",
    "direccion": "Dirección",
    "direccion_entrega": "Dirección de entrega",
    "ciudad": "Ciudad",
    "notas": "Notas",
    "ruc": "RUC",
    "sku": "SKU",
    "items": "Ítems",
    "recibos": "Recibos",
    "metodo": "Método de pago",
    "referencia": "Referencia",
    "ultimos_digitos": "Últimos dígitos",
    "descuento_pct": "Descuento (%)",
    "descuento_aplica_a": "Descuento aplica a",
    "fecha_rebaja_hasta": "Vigencia del descuento",
    "page": "Página",
    "page_size": "Tamaño de página",
    "sort_by": "Columna de orden",
    "sort_order": "Orden",
    "date_from": "Fecha desde",
    "date_to": "Fecha hasta",
    "activo": "Estado activo",
    "nombre": "Nombre",
    "valor": "Valor",
}

# Traducciones de mensajes comunes de Pydantic v2
_MSG_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"^Field required$", re.I), "Este campo es obligatorio."),
    (re.compile(r"^Input should be a valid integer$", re.I), "Debe ser un número entero."),
    (re.compile(r"^Input should be a valid number$", re.I), "Debe ser un número."),
    (re.compile(r"^Input should be a valid string$", re.I), "Debe ser texto."),
    (re.compile(r"^Input should be a valid boolean$", re.I), "Debe ser verdadero o falso."),
    (re.compile(r"^Input should be a valid email address$", re.I), "Correo electrónico inválido."),
    (re.compile(r"^String should have at least (\d+) characters?$", re.I), r"Mínimo \1 caracteres."),
    (re.compile(r"^String should have at most (\d+) characters?$", re.I), r"Máximo \1 caracteres."),
    (re.compile(r"^String should match pattern", re.I), "Formato inválido."),
    (re.compile(r"^Input should be greater than (\S+)$", re.I), r"Debe ser mayor que \1."),
    (re.compile(r"^Input should be greater than or equal to (\S+)$", re.I), r"Debe ser mayor o igual a \1."),
    (re.compile(r"^Input should be less than or equal to (\S+)$", re.I), r"Debe ser menor o igual a \1."),
    (re.compile(r"^Input should not equal (\S+)$", re.I), r"No puede ser igual a \1."),
    (re.compile(r"^List should have at least (\d+) item", re.I), r"Debe incluir al menos \1 elemento(s)."),
    (re.compile(r"^JSON decode error", re.I), "El cuerpo de la solicitud no es JSON válido."),
    (re.compile(r"^value is not a valid", re.I), "Valor inválido."),
]


def field_label(loc: list[Any]) -> str:
    """Devuelve etiqueta legible del último segmento relevante de loc."""
    skip = {"body", "query", "path", "header", "cookie"}
    name = None
    for part in reversed(loc):
        if isinstance(part, str) and part not in skip:
            name = part
            break
        if isinstance(part, int):
            return f"Ítem {part + 1}"
    if not name:
        return "Campo"
    return FIELD_LABELS.get(name, name.replace("_", " ").capitalize())


def translate_pydantic_msg(msg: str, err_type: str = "") -> str:
    """Traduce un mensaje de Pydantic al español cuando es posible."""
    text = (msg or "").strip()
    if not text:
        return "Valor inválido."

    lower = text.lower()
    if "email address" in lower or err_type in {"value_error", "string_type"} and "email" in lower:
        return "Correo electrónico inválido."

    # ValueError personalizados del dominio suelen venir ya en español
    if err_type in {"value_error", "assertion_error"} and any(
        ch in text for ch in "áéíóúñÁÉÍÓÚÑ"
    ):
        return text

    for pattern, replacement in _MSG_PATTERNS:
        m = pattern.match(text)
        if m:
            return pattern.sub(replacement, text)

    # Mensajes ValueError en inglés de Pydantic con prefijo
    if text.startswith("Value error, "):
        inner = text[len("Value error, ") :]
        if any(ch in inner for ch in "áéíóúñÁÉÍÓÚÑ"):
            return inner
        return inner

    return text


def format_validation_errors(errors: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Normaliza la lista de errores de Pydantic para la respuesta JSON.

    Cada entrada incluye loc, type, msg (original), msg_es (traducido) y label.
    """
    formatted: list[dict[str, Any]] = []
    for err in errors:
        loc = list(err.get("loc", []))
        msg = str(err.get("msg", ""))
        err_type = str(err.get("type", ""))
        label = field_label(loc)
        msg_es = translate_pydantic_msg(msg, err_type)
        if label and label != "Campo" and not msg_es.lower().startswith(label.lower()):
            msg_es = f"{label}: {msg_es}"
        formatted.append(
            {
                "loc": loc,
                "type": err_type,
                "msg": msg,
                "msg_es": msg_es,
                "label": label,
            }
        )
    return formatted


def validation_summary(errors: list[dict[str, Any]], max_items: int = 3) -> str:
    """Resumen corto en español para mostrar en UI."""
    if not errors:
        return "Error de validación en los datos enviados."
    parts = []
    for err in errors[:max_items]:
        parts.append(str(err.get("msg_es") or err.get("msg") or "Valor inválido."))
    extra = len(errors) - max_items
    if extra > 0:
        parts.append(f"y {extra} error(es) más")
    return " · ".join(parts)
