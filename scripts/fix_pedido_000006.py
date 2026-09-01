"""Diagnóstico PED-000006 + integración fact_ventas + vista ventas."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "apps" / "admin"))
sys.path.insert(0, str(ROOT / "apps" / "portal"))

import duckdb
from shared.database.connection import resolve_duckdb_path
from shared.services.integracion_ventas_service import integrar_pedido, reintegrar_pedidos_pendientes
from backend.services.rentabilidad_service import get_rentabilidad_producto

PED_NUM = "PED-000006"
PRODUCT_HINT = "Helado"


def refresh_ventas_view(conn) -> None:
    conn.execute(
        """
        CREATE OR REPLACE VIEW ventas AS
        SELECT
          dr.region, dc.country, dit.item_type, dsc.sales_channel, dop.order_priority,
          fv.order_date, fv.order_id, fv.ship_date, fv.units_sold,
          fv.unit_price, fv.unit_cost, fv.total_revenue, fv.total_cost, fv.total_profit,
          fv.id_venta, fv.id_producto, fv.origen,
          dp.nombre_producto,
          COALESCE(dp.nombre_producto, dit.item_type) AS dimension_producto
        FROM fact_ventas fv
        JOIN dim_region dr ON dr.id_region = fv.id_region
        JOIN dim_country dc ON dc.id_country = fv.id_country
        JOIN dim_item_type dit ON dit.id_item_type = fv.id_item_type
        JOIN dim_sales_channel dsc ON dsc.id_channel = fv.id_channel
        JOIN dim_order_priority dop ON dop.id_priority = fv.id_priority
        LEFT JOIN dim_producto dp ON dp.id_producto = fv.id_producto
        """
    )


def main() -> None:
    db = resolve_duckdb_path()
    conn = duckdb.connect(str(db))
    try:
        refresh_ventas_view(conn)

        ped = conn.execute(
            """
            SELECT p.id_pedido, p.numero, p.estado, CAST(p.fecha_pedido AS DATE)
            FROM pedidos p WHERE p.numero = ?
            """,
            [PED_NUM],
        ).fetchone()
        print("=== PEDIDO ===")
        print(ped or "NO ENCONTRADO")

        if ped:
            id_pedido = int(ped[0])
            det = conn.execute(
                """
                SELECT d.cantidad, d.precio_unitario, d.subtotal, pr.nombre_producto, pr.id_producto
                FROM pedido_detalle d
                JOIN dim_producto pr ON pr.id_producto = d.id_producto
                WHERE d.id_pedido = ?
                """,
                [id_pedido],
            ).fetchall()
            print("=== DETALLE ===")
            for row in det:
                print(row)

            pago = conn.execute(
                "SELECT id_pago, estado, monto FROM pagos WHERE id_pedido = ?", [id_pedido]
            ).fetchone()
            print("=== PAGO ===", pago)

            fv_before = conn.execute(
                """
                SELECT COUNT(*) FROM fact_ventas fv
                JOIN dim_producto pr ON pr.id_producto = fv.id_producto
                WHERE pr.nombre_producto ILIKE ? AND fv.origen = 'portal'
                """,
                [f"%{PRODUCT_HINT}%"],
            ).fetchone()
            print("=== fact_ventas helado (antes) count ===", fv_before[0] if fv_before else 0)
            fv_rows = conn.execute(
                """
                SELECT fv.id_venta, fv.order_id, fv.origen, fv.order_date,
                       fv.total_revenue, fv.total_profit, pr.nombre_producto
                FROM fact_ventas fv
                LEFT JOIN dim_producto pr ON pr.id_producto = fv.id_producto
                WHERE fv.order_id >= 10000000000
                ORDER BY fv.id_venta DESC LIMIT 20
                """
            ).fetchall()
            print("=== fact_ventas portal (antes reintegrar) ===")
            for r in fv_rows:
                if r[6] and PRODUCT_HINT.lower() in str(r[6]).lower():
                    print(" *", r)
            helado = [r for r in fv_rows if r[6] and PRODUCT_HINT.lower() in str(r[6]).lower()]
            if not helado:
                print("(sin filas de helado aún)")

            print("=== REINTEGRAR ===")
            r1 = integrar_pedido(conn, id_pedido=id_pedido)
            print("integrar_pedido:", r1)

            from shared.services.integracion_ventas_service import order_id_linea
            for (idd,) in conn.execute(
                "SELECT id_detalle FROM pedido_detalle WHERE id_pedido = ?", [id_pedido]
            ).fetchall():
                oid = order_id_linea(id_pedido, int(idd))
                row = conn.execute(
                    """
                    SELECT fv.id_venta, fv.order_id, fv.id_producto, fv.total_revenue,
                           fv.total_profit, fv.origen, pr.nombre_producto
                    FROM fact_ventas fv
                    LEFT JOIN dim_producto pr ON pr.id_producto = fv.id_producto
                    WHERE fv.order_id = ?
                    """,
                    [oid],
                ).fetchone()
                print(f"=== fact_ventas order_id={oid} ===", row)

            r2 = reintegrar_pedidos_pendientes(conn)
            print("reintegrar global insertadas:", r2.get("insertadas"))

            fv_after = conn.execute(
                """
                SELECT fv.id_venta, fv.order_id, fv.origen, fv.order_date,
                       fv.total_revenue, fv.total_profit, pr.nombre_producto
                FROM fact_ventas fv
                LEFT JOIN dim_producto pr ON pr.id_producto = fv.id_producto
                WHERE pr.nombre_producto ILIKE ?
                ORDER BY fv.id_venta DESC
                """,
                [f"%{PRODUCT_HINT}%"],
            ).fetchall()
            print("=== fact_ventas helado (después) ===")
            print(fv_after or "NINGUNA")

            rows = get_rentabilidad_producto(conn)
            match = [r for r in rows if PRODUCT_HINT.lower() in r["dimension"].lower()
                     or "helado" in r["dimension"].lower()]
            print("=== RENTABILIDAD (helado) ===")
            for r in match[:5]:
                print(r)
            if not match:
                print("Top 5 rentabilidad:")
                for r in rows[:5]:
                    print(r)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
