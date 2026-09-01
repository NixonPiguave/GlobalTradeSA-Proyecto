"""Smoke test rápido de generación PDF."""
from shared.database.connection import connect
from shared.pdf import comprobante_service
from shared.services.factura_service import crear_factura_desde_pedido

conn = connect()
r = conn.execute(
    """
    SELECT id_pedido FROM pedidos
    WHERE estado IN ('pagado','preparando','enviado','entregado')
    ORDER BY id_pedido DESC LIMIT 1
    """
).fetchone()
if not r:
    print("SKIP: sin pedidos pagados")
else:
    id_p = int(r[0])
    f = crear_factura_desde_pedido(conn, id_pedido=id_p)
    m1 = comprobante_service.generar_pdf(conn, tipo="pedido", entidad_id=id_p)
    m2 = comprobante_service.generar_pdf(conn, tipo="factura", entidad_id=f["id_factura"])
    print("OK pedido", m1["numero"], m1["pdf_path"])
    print("OK factura", m2["numero"])
