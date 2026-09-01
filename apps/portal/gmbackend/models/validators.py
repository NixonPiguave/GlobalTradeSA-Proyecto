"""Validadores compartidos del portal B2B."""

from __future__ import annotations

import re
from typing import Optional


def validar_telefono_e164(valor: Optional[str]) -> Optional[str]:
    """E.164: entre 7 y 15 dígitos; permite +, espacios y separadores."""
    if valor is None or not str(valor).strip():
        return None
    t = str(valor).strip()
    if len(t) > 20:
        raise ValueError("Teléfono demasiado largo.")
    if not re.match(r"^[\d\s+\-().]+$", t):
        raise ValueError("Teléfono inválido.")
    digits = re.sub(r"\D", "", t)
    if len(digits) < 7 or len(digits) > 15:
        raise ValueError("Ingresa un teléfono válido (7 a 15 dígitos).")
    return t
