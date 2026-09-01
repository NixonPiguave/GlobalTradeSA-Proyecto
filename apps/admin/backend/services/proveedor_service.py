"""
services/proveedor_service.py — CRUD de proveedores.
"""

from __future__ import annotations

import re
from typing import Any, Optional

import duckdb

from shared.database.ids import siguiente_id

from shared.services.red_bodegas import macro_de_region, macro_label
_RUC_RE = re.compile(r"^\d{8,13}$")


def _norm_razon(razon_social: str) -> str:
    s = " ".join(str(razon_social or "").split())
    if len(s) < 2 or len(s) > 160:
        raise ValueError("Razón social: entre 2 y 160 caracteres.")
    return s


def _norm_ruc(ruc: Optional[str]) -> Optional[str]:
    if ruc is None:
        return None
    s = str(ruc).strip().replace(" ", "").replace("-", "")
    if not s:
        return None
    if not _RUC_RE.match(s):
        raise ValueError("RUC inválido: use solo dígitos (8 a 13 caracteres).")
    return s


def _assert_unicos(
    conn: duckdb.DuckDBPyConnection,
    *,
    razon_social: str,
    ruc: Optional[str],
    excluir_id: Optional[int] = None,
) -> None:
    excluir = int(excluir_id) if excluir_id is not None else None
    params: list[Any] = [razon_social]
    sql = "SELECT razon_social FROM proveedores WHERE lower(trim(razon_social)) = lower(trim(?))"
    if excluir is not None:
        sql += " AND id_proveedor <> ?"
        params.append(excluir)
    dup = conn.execute(sql, params).fetchone()
    if dup:
        raise ValueError(
            f"Ya existe un proveedor con la razón social «{dup[0]}». "
            "Elija otro nombre o edite el registro existente."
        )
    if ruc:
        params_r: list[Any] = [ruc]
        sql_r = "SELECT razon_social FROM proveedores WHERE ruc = ?"
        if excluir is not None:
            sql_r += " AND id_proveedor <> ?"
            params_r.append(excluir)
        dup_r = conn.execute(sql_r, params_r).fetchone()
        if dup_r:
            raise ValueError(
                f"El RUC {ruc} ya está asignado a «{dup_r[0]}». "
                "Use un RUC distinto o deje el campo vacío si no aplica."
            )


def listar_proveedores(
    conn: duckdb.DuckDBPyConnection,
    *,
    incluir_inactivos: bool = False,
    q: Optional[str] = None,
) -> list[dict[str, Any]]:
    condiciones: list[str] = []
    params: list[Any] = []
    if not incluir_inactivos:
        condiciones.append("p.activo = true")
    if q:
        condiciones.append("(p.razon_social ILIKE ? OR p.ruc ILIKE ?)")
        params.extend([f"%{q}%", f"%{q}%"])
    where = f"WHERE {' AND '.join(condiciones)}" if condiciones else ""
    rows = conn.execute(
        f"""
        SELECT p.id_proveedor, p.razon_social, p.ruc, p.id_country, c.country, c.id_region, p.activo,
               (SELECT COUNT(*) FROM ordenes_compra oc WHERE oc.id_proveedor = p.id_proveedor) AS n_ordenes
        FROM proveedores p
        LEFT JOIN dim_country c ON c.id_country = p.id_country
        {where}
        ORDER BY c.id_region NULLS LAST, p.razon_social
        """,
        params,
    ).fetchall()
    return [
        {
            "id_proveedor": int(r[0]),
            "razon_social": r[1],
            "ruc": r[2],
            "id_country": int(r[3]) if r[3] is not None else None,
            "pais": r[4],
            "id_region": int(r[5]) if r[5] is not None else None,
            "macro_zona": macro_de_region(int(r[5])) if r[5] is not None else None,
            "macro_label": macro_label(macro_de_region(int(r[5]))) if r[5] is not None else None,
            "activo": bool(r[6]),
            "n_ordenes": int(r[7]),
        }
        for r in rows
    ]


def obtener_proveedor(conn: duckdb.DuckDBPyConnection, id_proveedor: int) -> Optional[dict[str, Any]]:
    r = conn.execute(
        """
        SELECT p.id_proveedor, p.razon_social, p.ruc, p.id_country, c.country, c.id_region, p.activo
        FROM proveedores p
        LEFT JOIN dim_country c ON c.id_country = p.id_country
        WHERE p.id_proveedor = ?
        """,
        [id_proveedor],
    ).fetchone()
    if not r:
        return None
    id_region = int(r[5]) if r[5] is not None else None
    macro = macro_de_region(id_region)
    return {
        "id_proveedor": int(r[0]),
        "razon_social": r[1],
        "ruc": r[2],
        "id_country": int(r[3]) if r[3] is not None else None,
        "pais": r[4],
        "id_region": id_region,
        "macro_zona": macro,
        "macro_label": macro_label(macro),
        "activo": bool(r[6]),
    }


def crear_proveedor(
    conn: duckdb.DuckDBPyConnection,
    *,
    razon_social: str,
    ruc: Optional[str],
    id_country: Optional[int],
) -> dict[str, Any]:
    razon = _norm_razon(razon_social)
    ruc_n = _norm_ruc(ruc)
    _assert_unicos(conn, razon_social=razon, ruc=ruc_n)
    id_proveedor = siguiente_id(conn, "proveedores")
    conn.execute(
        """
        INSERT INTO proveedores (id_proveedor, razon_social, ruc, id_country, activo)
        VALUES (?, ?, ?, ?, true)
        """,
        [id_proveedor, razon, ruc_n, id_country],
    )
    return obtener_proveedor(conn, id_proveedor)


def actualizar_proveedor(
    conn: duckdb.DuckDBPyConnection, id_proveedor: int, cambios: dict[str, Any]
) -> Optional[dict[str, Any]]:
    actual = obtener_proveedor(conn, id_proveedor)
    if not actual:
        return None
    clean: dict[str, Any] = {}
    if "razon_social" in cambios and cambios["razon_social"] is not None:
        clean["razon_social"] = _norm_razon(cambios["razon_social"])
    if "ruc" in cambios:
        clean["ruc"] = _norm_ruc(cambios["ruc"])
    if "id_country" in cambios:
        clean["id_country"] = cambios["id_country"]
    if "activo" in cambios and cambios["activo"] is not None:
        clean["activo"] = bool(cambios["activo"])

    razon = clean.get("razon_social", actual["razon_social"])
    ruc_n = clean["ruc"] if "ruc" in clean else actual["ruc"]
    _assert_unicos(conn, razon_social=razon, ruc=ruc_n, excluir_id=id_proveedor)

    if clean:
        sets = [f"{k} = ?" for k in clean]
        conn.execute(
            f"UPDATE proveedores SET {', '.join(sets)} WHERE id_proveedor = ?",
            [*clean.values(), id_proveedor],
        )
    return obtener_proveedor(conn, id_proveedor)


def eliminar_proveedor(conn: duckdb.DuckDBPyConnection, id_proveedor: int) -> None:
    """Elimina un proveedor. Lanza ValueError si tiene órdenes de compra asociadas."""
    if not obtener_proveedor(conn, id_proveedor):
        raise KeyError("Proveedor no encontrado.")
    n = int(
        conn.execute(
            "SELECT COUNT(*) FROM ordenes_compra oc WHERE oc.id_proveedor = ?",
            [id_proveedor],
        ).fetchone()[0]
    )
    if n > 0:
        raise ValueError(
            f"No se puede eliminar el proveedor porque tiene {n} orden(es) de compra. "
            "Puede desactivarlo para dejar de usarlo."
        )
    conn.execute("DELETE FROM proveedores WHERE id_proveedor = ?", [id_proveedor])
