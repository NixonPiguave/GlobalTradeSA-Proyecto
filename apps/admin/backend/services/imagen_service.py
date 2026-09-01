"""
services/imagen_service.py — Subida y validación de imágenes de producto.

Las imágenes se guardan en `shared/storage/uploads/productos/` y en BD solo
se persiste la ruta relativa (p.ej. `uploads/productos/mi-producto.jpg`).
"""

from __future__ import annotations

import re
import secrets
from pathlib import Path

MAX_BYTES = 5 * 1024 * 1024  # 5 MB
EXTENSIONES = {".jpg", ".jpeg", ".png", ".webp"}

# Firmas de archivo (magic numbers) para validar sin depender de Pillow.
_MAGIC = {
    b"\xff\xd8\xff": ".jpg",
    b"\x89PNG\r\n\x1a\n": ".png",
    b"RIFF": ".webp",  # RIFF....WEBP
}


def storage_root() -> Path:
    # apps/admin/backend/services -> repo root
    return Path(__file__).resolve().parent.parent.parent.parent.parent / "shared" / "storage"


def uploads_dir(subdir: str = "productos") -> Path:
    d = storage_root() / "uploads" / subdir
    d.mkdir(parents=True, exist_ok=True)
    return d


def _detectar_extension(contenido: bytes) -> str | None:
    for magic, ext in _MAGIC.items():
        if contenido.startswith(magic):
            if ext == ".webp" and contenido[8:12] != b"WEBP":
                continue
            return ext
    return None


def _slug(nombre: str) -> str:
    s = nombre.lower()
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s[:48] or "imagen"


def guardar_imagen(contenido: bytes, nombre_original: str, subdir: str = "productos") -> str:
    """Valida y guarda la imagen. Devuelve la ruta relativa para BD."""
    if not contenido:
        raise ValueError("Archivo vacío.")
    if len(contenido) > MAX_BYTES:
        raise ValueError(f"La imagen supera el límite de {MAX_BYTES // (1024 * 1024)} MB.")

    ext = _detectar_extension(contenido)
    if ext is None:
        raise ValueError("Formato no soportado. Usa JPG, PNG o WEBP.")

    base = _slug(Path(nombre_original).stem)
    nombre = f"{base}-{secrets.token_hex(4)}{ext}"
    destino = uploads_dir(subdir) / nombre
    destino.write_bytes(contenido)
    return f"uploads/{subdir}/{nombre}"


def eliminar_imagen(ruta_relativa: str) -> bool:
    """Elimina una imagen previa (solo dentro de uploads/productos)."""
    if not ruta_relativa or not ruta_relativa.startswith("uploads/"):
        return False
    destino = (storage_root() / ruta_relativa).resolve()
    uploads_root = (storage_root() / "uploads").resolve()
    if not str(destino).startswith(str(uploads_root)):
        return False
    if destino.exists():
        destino.unlink()
        return True
    return False
