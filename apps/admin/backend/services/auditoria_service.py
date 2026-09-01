"""
services/auditoria_service.py — Registro de auditoría de operaciones críticas.

Cada operación de escritura relevante (catálogo, pedidos, inventario, pagos)
debe llamar a `registrar_auditoria` dentro de la misma transacción/flujo.
"""

from __future__ import annotations

import json
from typing import Any, Optional

import duckdb

from backend.logger import get_logger

logger = get_logger(__name__)


def _serializar(valor: Any) -> Optional[str]:
    if valor is None:
        return None
    if isinstance(valor, str):
        return valor[:2000]
    try:
        return json.dumps(valor, ensure_ascii=False, default=str)[:2000]
    except Exception:
        return str(valor)[:2000]


def registrar_auditoria(
    conn: duckdb.DuckDBPyConnection,
    *,
    id_usuario: Optional[int],
    entidad: str,
    entidad_id: Optional[int],
    accion: str,
    valor_anterior: Any = None,
    valor_nuevo: Any = None,
) -> None:
    """Inserta una fila en auditoria_log. Nunca lanza: la auditoría no debe romper la operación."""
    try:
        conn.execute(
            """
            INSERT INTO auditoria_log (id_log, id_usuario, entidad, entidad_id, accion, valor_anterior, valor_nuevo, fecha)
            VALUES (
              (SELECT COALESCE(MAX(id_log), 0) + 1 FROM auditoria_log),
              ?, ?, ?, ?, ?, ?, current_timestamp
            )
            """,
            [
                id_usuario,
                entidad,
                entidad_id,
                accion,
                _serializar(valor_anterior),
                _serializar(valor_nuevo),
            ],
        )
    except duckdb.Error as exc:
        logger.warning("No se pudo registrar auditoría (%s/%s): %s", entidad, accion, exc)


def listar_auditoria(
    conn: duckdb.DuckDBPyConnection,
    *,
    entidad: Optional[str] = None,
    accion: Optional[str] = None,
    email: Optional[str] = None,
    entidad_id: Optional[int] = None,
    desde: Optional[str] = None,
    hasta: Optional[str] = None,
    q: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
) -> dict[str, Any]:
    limit = max(1, min(limit, 500))
    offset = max(0, offset)
    where: list[str] = []
    params: list[Any] = []
    if entidad:
        where.append("a.entidad = ?")
        params.append(entidad)
    if accion:
        where.append("lower(a.accion) LIKE ?")
        params.append(f"%{accion.strip().lower()}%")
    if email:
        where.append("lower(COALESCE(u.email, '')) LIKE ?")
        params.append(f"%{email.strip().lower()}%")
    if entidad_id is not None:
        where.append("a.entidad_id = ?")
        params.append(int(entidad_id))
    if desde:
        where.append("CAST(a.fecha AS DATE) >= CAST(? AS DATE)")
        params.append(desde)
    if hasta:
        where.append("CAST(a.fecha AS DATE) <= CAST(? AS DATE)")
        params.append(hasta)
    if q:
        like = f"%{q.strip().lower()}%"
        where.append(
            "(lower(COALESCE(a.accion,'')) LIKE ? OR lower(COALESCE(a.entidad,'')) LIKE ? "
            "OR lower(COALESCE(a.valor_nuevo,'')) LIKE ? OR lower(COALESCE(a.valor_anterior,'')) LIKE ? "
            "OR lower(COALESCE(u.email,'')) LIKE ?)"
        )
        params.extend([like, like, like, like, like])
    where_sql = ("WHERE " + " AND ".join(where)) if where else ""
    total_row = conn.execute(
        f"SELECT COUNT(*) FROM auditoria_log a LEFT JOIN usuarios u ON u.id_usuario = a.id_usuario {where_sql}",
        params,
    ).fetchone()
    total = int(total_row[0] or 0) if total_row else 0
    rows = conn.execute(
        f"""
        SELECT a.id_log, a.id_usuario, u.email, a.entidad, a.entidad_id,
               a.accion, a.valor_anterior, a.valor_nuevo, a.fecha
        FROM auditoria_log a
        LEFT JOIN usuarios u ON u.id_usuario = a.id_usuario
        {where_sql}
        ORDER BY a.id_log DESC
        LIMIT ? OFFSET ?
        """,
        [*params, limit, offset],
    ).fetchall()
    items = [
        {
            "id_log": int(r[0]),
            "id_usuario": int(r[1]) if r[1] is not None else None,
            "email": r[2],
            "entidad": r[3],
            "entidad_id": int(r[4]) if r[4] is not None else None,
            "accion": r[5],
            "valor_anterior": r[6],
            "valor_nuevo": r[7],
            "fecha": str(r[8]) if r[8] is not None else None,
        }
        for r in rows
    ]
    return {
        "items": items,
        "total": total,
        "limit": limit,
        "offset": offset,
        "page": (offset // limit) + 1 if limit else 1,
        "total_pages": max(1, (total + limit - 1) // limit) if limit else 1,
    }


def catalogo_filtros(conn: duckdb.DuckDBPyConnection) -> dict[str, Any]:
    entidades = [
        r[0]
        for r in conn.execute(
            "SELECT DISTINCT entidad FROM auditoria_log WHERE entidad IS NOT NULL ORDER BY 1"
        ).fetchall()
    ]
    acciones = [
        r[0]
        for r in conn.execute(
            "SELECT DISTINCT accion FROM auditoria_log WHERE accion IS NOT NULL ORDER BY 1 LIMIT 80"
        ).fetchall()
    ]
    return {"entidades": entidades, "acciones": acciones}
