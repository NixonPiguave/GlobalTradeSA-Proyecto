"""Tests para shared/api/db_errors.py"""

from __future__ import annotations

from shared.api.db_errors import codigo_http_bd, es_error_bd, mensaje_error_bd


def test_corrupcion_metadata():
    exc = Exception("INTERNAL Error: Failed to load metadata pointer")
    assert es_error_bd(exc)
    assert codigo_http_bd(exc) == 503
    msg = mensaje_error_bd(exc)
    assert "base de datos" in msg.lower()


def test_constraint_unique():
    exc = Exception("Constraint Error: UNIQUE constraint failed")
    assert codigo_http_bd(exc) == 409


def test_error_generico_bd():
    exc = Exception("Catalog Error: Table with name pedidos does not exist")
    assert es_error_bd(exc)
    assert "tabla" in mensaje_error_bd(exc).lower() or "base de datos" in mensaje_error_bd(exc).lower()
