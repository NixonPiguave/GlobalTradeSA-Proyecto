"""
routers/catalogo.py — CRUD de categorías, productos, listas de precios e imágenes.
Protegido con roles staff; escritura registra auditoría.
"""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile

from backend.database import get_connection, notify_db_changed
from backend.middleware.authz import require_staff
from pydantic import BaseModel

from backend.models.catalogo import (
    CatalogoCreate,
    CatalogoProductoAdd,
    CatalogoProductoUpdate,
    CatalogoUpdate,
    CategoriaCreate,
    CategoriaUpdate,
    LineaCreate,
    LineaUpdate,
    MarcaCreate,
    MarcaUpdate,
    PrecioDetalle,
    ProductoCreate,
    ProductoUpdate,
)
from backend.services import catalogo_service, categoria_service, precio_service, producto_service
from backend.services.auditoria_service import registrar_auditoria
from backend.services.imagen_service import guardar_imagen

router = APIRouter()


class CambioActivo(BaseModel):
    activo: bool


@router.get("/marcas", summary="Listar marcas")
def listar_marcas(
    incluir_inactivas: bool = False,
    _: dict = Depends(require_staff),
) -> list[dict[str, Any]]:
    with get_connection() as conn:
        where = "" if incluir_inactivas else "WHERE COALESCE(activo, true) = true"
        rows = conn.execute(
            f"SELECT id_marca, nombre, activo FROM marcas {where} ORDER BY nombre"
        ).fetchall()
        return [{"id_marca": int(r[0]), "nombre": r[1], "activo": bool(r[2])} for r in rows]


@router.post("/marcas", status_code=201, summary="Crear marca")
def crear_marca(body: MarcaCreate, usuario: dict = Depends(require_staff)) -> dict[str, Any]:
    nombre = body.nombre.strip()
    with get_connection() as conn:
        dup = conn.execute(
            "SELECT 1 FROM marcas WHERE lower(nombre) = lower(?)", [nombre]
        ).fetchone()
        if dup:
            raise HTTPException(status_code=409, detail="Ya existe una marca con ese nombre.")
        nid = conn.execute("SELECT COALESCE(MAX(id_marca), 0) + 1 FROM marcas").fetchone()[0]
        conn.execute(
            "INSERT INTO marcas (id_marca, nombre, activo) VALUES (?, ?, true)",
            [int(nid), nombre],
        )
        from shared.database.migrate_reestructuracion import asegurar_lineas_marca

        asegurar_lineas_marca(conn, int(nid), nombre)
        registrar_auditoria(
            conn, id_usuario=usuario["id_usuario"], entidad="marca",
            entidad_id=int(nid), accion="crear", valor_nuevo={"nombre": nombre},
        )
        notify_db_changed(conn)
        return {"id_marca": int(nid), "nombre": nombre, "activo": True}


@router.put("/marcas/{id_marca}", summary="Actualizar marca")
def actualizar_marca(
    id_marca: int, body: MarcaUpdate, usuario: dict = Depends(require_staff)
) -> dict[str, Any]:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT nombre, activo FROM marcas WHERE id_marca = ?", [id_marca]
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Marca no encontrada.")
        nombre = body.nombre.strip() if body.nombre else row[0]
        activo = body.activo if body.activo is not None else bool(row[1])
        if body.nombre:
            dup = conn.execute(
                "SELECT 1 FROM marcas WHERE lower(nombre) = lower(?) AND id_marca <> ?",
                [nombre, id_marca],
            ).fetchone()
            if dup:
                raise HTTPException(status_code=409, detail="Ya existe otra marca con ese nombre.")
        conn.execute(
            "UPDATE marcas SET nombre = ?, activo = ? WHERE id_marca = ?",
            [nombre, activo, id_marca],
        )
        notify_db_changed(conn)
        return {"id_marca": id_marca, "nombre": nombre, "activo": activo}


@router.get("/lineas", summary="Listar líneas de producto")
def listar_lineas(
    incluir_inactivas: bool = False,
    _: dict = Depends(require_staff),
) -> list[dict[str, Any]]:
    with get_connection() as conn:
        where = "" if incluir_inactivas else "WHERE COALESCE(l.activo, true) = true"
        rows = conn.execute(
            f"""
            SELECT l.id_linea, l.nombre, l.id_marca, l.activo, l.descripcion, m.nombre
            FROM lineas_producto l
            LEFT JOIN marcas m ON m.id_marca = l.id_marca
            {where}
            ORDER BY l.nombre
            """
        ).fetchall()
        return [
            {
                "id_linea": int(r[0]),
                "nombre": r[1],
                "id_marca": int(r[2]) if r[2] is not None else None,
                "activo": bool(r[3]),
                "descripcion": r[4],
                "marca": r[5],
            }
            for r in rows
        ]


@router.post("/lineas", status_code=201, summary="Crear línea de producto")
def crear_linea(body: LineaCreate, usuario: dict = Depends(require_staff)) -> dict[str, Any]:
    nombre = body.nombre.strip()
    with get_connection() as conn:
        dup = conn.execute(
            "SELECT 1 FROM lineas_producto WHERE lower(nombre) = lower(?)", [nombre]
        ).fetchone()
        if dup:
            raise HTTPException(status_code=409, detail="Ya existe una línea con ese nombre.")
        if body.id_marca is not None:
            if not conn.execute("SELECT 1 FROM marcas WHERE id_marca = ?", [body.id_marca]).fetchone():
                raise HTTPException(status_code=422, detail="La marca indicada no existe.")
        nid = conn.execute("SELECT COALESCE(MAX(id_linea), 0) + 1 FROM lineas_producto").fetchone()[0]
        conn.execute(
            """
            INSERT INTO lineas_producto (id_linea, nombre, id_marca, activo, descripcion)
            VALUES (?, ?, ?, true, ?)
            """,
            [int(nid), nombre, body.id_marca, body.descripcion],
        )
        registrar_auditoria(
            conn, id_usuario=usuario["id_usuario"], entidad="linea",
            entidad_id=int(nid), accion="crear", valor_nuevo={"nombre": nombre},
        )
        notify_db_changed(conn)
        return {
            "id_linea": int(nid), "nombre": nombre, "id_marca": body.id_marca,
            "activo": True, "descripcion": body.descripcion,
        }


@router.put("/lineas/{id_linea}", summary="Actualizar línea")
def actualizar_linea(
    id_linea: int, body: LineaUpdate, usuario: dict = Depends(require_staff)
) -> dict[str, Any]:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT nombre, id_marca, activo, descripcion FROM lineas_producto WHERE id_linea = ?",
            [id_linea],
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Línea no encontrada.")
        nombre = body.nombre.strip() if body.nombre else row[0]
        id_marca = body.id_marca if body.id_marca is not None else row[1]
        activo = body.activo if body.activo is not None else bool(row[2])
        descripcion = body.descripcion if body.descripcion is not None else row[3]
        if body.nombre:
            dup = conn.execute(
                "SELECT 1 FROM lineas_producto WHERE lower(nombre) = lower(?) AND id_linea <> ?",
                [nombre, id_linea],
            ).fetchone()
            if dup:
                raise HTTPException(status_code=409, detail="Ya existe otra línea con ese nombre.")
        if id_marca is not None:
            if not conn.execute("SELECT 1 FROM marcas WHERE id_marca = ?", [id_marca]).fetchone():
                raise HTTPException(status_code=422, detail="La marca indicada no existe.")
        conn.execute(
            """
            UPDATE lineas_producto
            SET nombre = ?, id_marca = ?, activo = ?, descripcion = ?
            WHERE id_linea = ?
            """,
            [nombre, id_marca, activo, descripcion, id_linea],
        )
        notify_db_changed(conn)
        return {
            "id_linea": id_linea, "nombre": nombre, "id_marca": id_marca,
            "activo": activo, "descripcion": descripcion,
        }


# ---------------------------------------------------------------------------
# Categorías
# ---------------------------------------------------------------------------

@router.get("/categorias", summary="Listar categorías")
def listar_categorias(
    incluir_inactivas: bool = False,
    _: dict = Depends(require_staff),
) -> list[dict[str, Any]]:
    with get_connection() as conn:
        return categoria_service.listar_categorias(conn, incluir_inactivas=incluir_inactivas)


@router.post("/categorias", status_code=201, summary="Crear categoría")
def crear_categoria(body: CategoriaCreate, usuario: dict = Depends(require_staff)) -> dict[str, Any]:
    with get_connection() as conn:
        try:
            cat = categoria_service.crear_categoria(
                conn,
                nombre=body.nombre,
                descripcion=body.descripcion,
                imagen_path=body.imagen_path,
            )
        except ValueError as e:
            raise HTTPException(status_code=409, detail=str(e))
        registrar_auditoria(
            conn,
            id_usuario=usuario["id_usuario"],
            entidad="categoria",
            entidad_id=cat["id_categoria"],
            accion="crear",
            valor_nuevo=cat,
        )
        notify_db_changed(conn)
    return cat


@router.put("/categorias/{id_categoria}", summary="Actualizar categoría")
def actualizar_categoria(
    id_categoria: int, body: CategoriaUpdate, usuario: dict = Depends(require_staff)
) -> dict[str, Any]:
    with get_connection() as conn:
        anterior = categoria_service.obtener_categoria(conn, id_categoria)
        cat = categoria_service.actualizar_categoria(conn, id_categoria, body.model_dump(exclude_unset=True))
        if not cat:
            raise HTTPException(status_code=404, detail="Categoría no encontrada.")
        registrar_auditoria(
            conn,
            id_usuario=usuario["id_usuario"],
            entidad="categoria",
            entidad_id=id_categoria,
            accion="actualizar",
            valor_anterior=anterior,
            valor_nuevo=cat,
        )
        notify_db_changed(conn)
    return cat


@router.delete("/categorias/{id_categoria}", summary="Eliminar categoría (borra si no tiene productos; si no, la desactiva)")
def eliminar_categoria(id_categoria: int, usuario: dict = Depends(require_staff)) -> dict[str, Any]:
    with get_connection() as conn:
        anterior = categoria_service.obtener_categoria(conn, id_categoria)
        if not anterior:
            raise HTTPException(status_code=404, detail="Categoría no encontrada.")
        ok, modo = categoria_service.eliminar_categoria(conn, id_categoria)
        if not ok:
            raise HTTPException(status_code=404, detail="Categoría no encontrada.")
        registrar_auditoria(
            conn,
            id_usuario=usuario["id_usuario"],
            entidad="categoria",
            entidad_id=id_categoria,
            accion=modo,
            valor_anterior=anterior,
        )
        notify_db_changed(conn)
    return {"ok": True, "modo": modo}


@router.post("/categorias/{id_categoria}/activo", summary="Activar/desactivar categoría")
def toggle_categoria_activa(
    id_categoria: int, body: CambioActivo, usuario: dict = Depends(require_staff)
) -> dict[str, Any]:
    with get_connection() as conn:
        if not categoria_service.set_categoria_activa(conn, id_categoria, body.activo):
            raise HTTPException(status_code=404, detail="Categoría no encontrada.")
        registrar_auditoria(
            conn,
            id_usuario=usuario["id_usuario"],
            entidad="categoria",
            entidad_id=id_categoria,
            accion="activar" if body.activo else "desactivar",
        )
        notify_db_changed(conn)
    return {"ok": True, "activo": body.activo}


# ---------------------------------------------------------------------------
# Productos
# ---------------------------------------------------------------------------

@router.get("/productos", summary="Listar productos (admin)")
def listar_productos(
    id_item_type: Optional[int] = None,
    q: Optional[str] = None,
    incluir_inactivos: bool = False,
    precio_min: Optional[float] = Query(default=None, ge=0),
    precio_max: Optional[float] = Query(default=None, ge=0),
    activo: Optional[bool] = None,
    page: int = 1,
    page_size: int = 20,
    _: dict = Depends(require_staff),
) -> dict[str, Any]:
    with get_connection() as conn:
        return producto_service.listar_productos(
            conn,
            id_item_type=id_item_type,
            q=q,
            incluir_inactivos=incluir_inactivos,
            precio_min=precio_min,
            precio_max=precio_max,
            activo=activo,
            page=page,
            page_size=page_size,
        )


@router.get("/productos/{id_producto}", summary="Detalle de producto (admin)")
def obtener_producto(id_producto: int, _: dict = Depends(require_staff)) -> dict[str, Any]:
    with get_connection() as conn:
        prod = producto_service.obtener_producto(conn, id_producto)
    if not prod:
        raise HTTPException(status_code=404, detail="Producto no encontrado.")
    return prod


@router.post("/productos", status_code=201, summary="Crear producto")
def crear_producto(body: ProductoCreate, usuario: dict = Depends(require_staff)) -> dict[str, Any]:
    with get_connection() as conn:
        try:
            prod = producto_service.crear_producto(
                conn,
                nombre_producto=body.nombre_producto,
                descripcion=body.descripcion,
                id_item_type=body.id_item_type,
                precio_unitario=body.precio_unitario,
                precio_mayorista=body.precio_mayorista,
                imagen_url=body.imagen_url,
                stock_inicial=0,
                stock_minimo=body.stock_minimo,
                id_marca=body.id_marca,
                id_linea=body.id_linea,
                sku=body.sku,
                descuento_pct=body.descuento_pct,
                precio_rebajado=body.precio_rebajado,
                descuento_aplica_a=body.descuento_aplica_a,
                fecha_rebaja_hasta=body.fecha_rebaja_hasta,
                descuento_motivo=body.descuento_motivo,
            )
        except ValueError as e:
            raise HTTPException(status_code=422, detail=str(e))
        if float(body.descuento_pct or 0) > 0 and body.avisar_clientes:
            producto_service._publicar_descuento_producto(conn, prod)
        registrar_auditoria(
            conn,
            id_usuario=usuario["id_usuario"],
            entidad="producto",
            entidad_id=prod["id_producto"],
            accion="crear",
            valor_nuevo=prod,
        )
        notify_db_changed(conn)
    return prod


@router.put("/productos/{id_producto}", summary="Actualizar producto")
def actualizar_producto(
    id_producto: int, body: ProductoUpdate, usuario: dict = Depends(require_staff)
) -> dict[str, Any]:
    with get_connection() as conn:
        anterior = producto_service.obtener_producto(conn, id_producto)
        try:
            prod = producto_service.actualizar_producto(
                conn, id_producto, body.model_dump(exclude_unset=True)
            )
        except ValueError as e:
            raise HTTPException(status_code=422, detail=str(e))
        if not prod:
            raise HTTPException(status_code=404, detail="Producto no encontrado.")
        registrar_auditoria(
            conn,
            id_usuario=usuario["id_usuario"],
            entidad="producto",
            entidad_id=id_producto,
            accion="actualizar",
            valor_anterior=anterior,
            valor_nuevo=prod,
        )
        notify_db_changed(conn)
    return prod


@router.delete("/productos/{id_producto}", summary="Eliminar producto si no tiene historial; si no, lo desactiva")
def eliminar_producto(id_producto: int, usuario: dict = Depends(require_staff)) -> dict[str, Any]:
    with get_connection() as conn:
        anterior = producto_service.obtener_producto(conn, id_producto)
        ok, modo = producto_service.eliminar_producto(conn, id_producto)
        if not ok:
            raise HTTPException(status_code=404, detail="Producto no encontrado.")
        registrar_auditoria(
            conn,
            id_usuario=usuario["id_usuario"],
            entidad="producto",
            entidad_id=id_producto,
            accion=modo,
            valor_anterior=anterior,
        )
        notify_db_changed(conn)
    return {"ok": True, "modo": modo}


@router.post("/productos/{id_producto}/activo", summary="Activar/desactivar producto")
def toggle_producto_activo(
    id_producto: int, body: CambioActivo, usuario: dict = Depends(require_staff)
) -> dict[str, Any]:
    with get_connection() as conn:
        if not producto_service.set_producto_activo(conn, id_producto, body.activo):
            raise HTTPException(status_code=404, detail="Producto no encontrado.")
        registrar_auditoria(
            conn,
            id_usuario=usuario["id_usuario"],
            entidad="producto",
            entidad_id=id_producto,
            accion="activar" if body.activo else "desactivar",
        )
        notify_db_changed(conn)
    return {"ok": True, "activo": body.activo}


# ---------------------------------------------------------------------------
# Imágenes
# ---------------------------------------------------------------------------

@router.post("/imagenes", status_code=201, summary="Subir imagen de producto")
async def subir_imagen(
    file: UploadFile = File(...),
    usuario: dict = Depends(require_staff),
) -> dict[str, Any]:
    contenido = await file.read()
    try:
        ruta = guardar_imagen(contenido, file.filename or "imagen")
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    with get_connection() as conn:
        registrar_auditoria(
            conn,
            id_usuario=usuario["id_usuario"],
            entidad="imagen",
            entidad_id=None,
            accion="subir",
            valor_nuevo={"ruta": ruta},
        )
    return {"ruta": ruta, "url": f"/media/{ruta}"}


# ---------------------------------------------------------------------------
# Listas de precios
# ---------------------------------------------------------------------------

@router.get("/listas-precios", summary="Listar listas de precios")
def listar_listas(_: dict = Depends(require_staff)) -> list[dict[str, Any]]:
    with get_connection() as conn:
        return precio_service.listar_listas(conn)


@router.get("/listas-precios/{id_lista}/precios", summary="Precios configurados en una lista")
def precios_lista(
    id_lista: int,
    q: str | None = None,
    _: dict = Depends(require_staff),
) -> list[dict[str, Any]]:
    with get_connection() as conn:
        return precio_service.listar_precios_lista(conn, id_lista, q=q)


@router.get("/productos/{id_producto}/precios", summary="Precios por lista de un producto")
def precios_producto(id_producto: int, _: dict = Depends(require_staff)) -> list[dict[str, Any]]:
    with get_connection() as conn:
        return precio_service.listar_precios_producto(conn, id_producto)


@router.post("/precios", summary="Fijar precio en lista")
def fijar_precio(body: PrecioDetalle, usuario: dict = Depends(require_staff)) -> dict[str, Any]:
    with get_connection() as conn:
        try:
            detalle = precio_service.fijar_precio(
                conn,
                id_lista=body.id_lista,
                id_producto=body.id_producto,
                precio=body.precio,
                cantidad_minima=body.cantidad_minima,
            )
        except ValueError as e:
            raise HTTPException(status_code=422, detail=str(e))
        registrar_auditoria(
            conn,
            id_usuario=usuario["id_usuario"],
            entidad="precio",
            entidad_id=detalle["id_detalle"],
            accion="fijar",
            valor_nuevo=detalle,
        )
        notify_db_changed(conn)
    return detalle


@router.delete("/precios/{id_detalle}", summary="Eliminar precio de lista")
def eliminar_precio(id_detalle: int, usuario: dict = Depends(require_staff)) -> dict[str, Any]:
    with get_connection() as conn:
        if not precio_service.eliminar_precio(conn, id_detalle):
            raise HTTPException(status_code=404, detail="Precio no encontrado.")
        registrar_auditoria(
            conn,
            id_usuario=usuario["id_usuario"],
            entidad="precio",
            entidad_id=id_detalle,
            accion="eliminar",
        )
        notify_db_changed(conn)
    return {"ok": True}


# ---------------------------------------------------------------------------
# Catálogos / paquetes configurables
# ---------------------------------------------------------------------------


@router.get("/catalogos", summary="Listar catálogos/paquetes")
def listar_catalogos(
    incluir_inactivas: bool = False,
    _: dict = Depends(require_staff),
) -> list[dict[str, Any]]:
    with get_connection() as conn:
        return catalogo_service.listar_catalogos(conn, incluir_inactivas=incluir_inactivas)


@router.get("/catalogos/{id_catalogo}", summary="Detalle de catálogo con sus productos")
def obtener_catalogo_admin(
    id_catalogo: int, _: dict = Depends(require_staff)
) -> dict[str, Any]:
    with get_connection() as conn:
        catalogo = catalogo_service.obtener_catalogo(conn, id_catalogo)
    if not catalogo:
        raise HTTPException(status_code=404, detail="Catálogo no encontrado.")
    return catalogo


@router.post("/catalogos", status_code=201, summary="Crear catálogo")
def crear_catalogo(body: CatalogoCreate, usuario: dict = Depends(require_staff)) -> dict[str, Any]:
    with get_connection() as conn:
        try:
            catalogo = catalogo_service.crear_catalogo(
                conn,
                nombre=body.nombre.strip(),
                descripcion=body.descripcion,
                id_item_type=body.id_item_type,
                activo=body.activo,
            )
        except ValueError as e:
            raise HTTPException(status_code=422, detail=str(e))
        registrar_auditoria(
            conn,
            id_usuario=usuario["id_usuario"],
            entidad="catalogo",
            entidad_id=catalogo["id_catalogo"],
            accion="crear",
            valor_nuevo={"nombre": catalogo["nombre"], "id_item_type": catalogo["id_item_type"]},
        )
        notify_db_changed(conn)
    return catalogo


@router.put("/catalogos/{id_catalogo}", summary="Actualizar catálogo")
def actualizar_catalogo(
    id_catalogo: int, body: CatalogoUpdate, usuario: dict = Depends(require_staff)
) -> dict[str, Any]:
    with get_connection() as conn:
        try:
            catalogo = catalogo_service.actualizar_catalogo(
                conn,
                id_catalogo,
                nombre=body.nombre.strip() if body.nombre else None,
                descripcion=body.descripcion,
                id_item_type=body.id_item_type,
                activo=body.activo,
                descuento_pct=body.descuento_pct,
                descuento_hasta=body.descuento_hasta,
                descuento_motivo=body.descuento_motivo,
                avisar_clientes=body.avisar_clientes,
            )
        except ValueError as e:
            raise HTTPException(status_code=422, detail=str(e))
        if not catalogo:
            raise HTTPException(status_code=404, detail="Catálogo no encontrado.")
        registrar_auditoria(
            conn,
            id_usuario=usuario["id_usuario"],
            entidad="catalogo",
            entidad_id=id_catalogo,
            accion="actualizar",
            valor_nuevo={"nombre": catalogo["nombre"], "activo": catalogo["activo"]},
        )
        notify_db_changed(conn)
    return catalogo


@router.delete("/catalogos/{id_catalogo}", summary="Eliminar o desactivar catálogo")
def eliminar_catalogo(id_catalogo: int, usuario: dict = Depends(require_staff)) -> dict[str, Any]:
    with get_connection() as conn:
        ok, modo = catalogo_service.eliminar_catalogo(conn, id_catalogo)
        if not ok:
            raise HTTPException(status_code=404, detail="Catálogo no encontrado.")
        registrar_auditoria(
            conn,
            id_usuario=usuario["id_usuario"],
            entidad="catalogo",
            entidad_id=id_catalogo,
            accion="eliminar" if modo == "eliminado" else "desactivar",
            valor_nuevo={"modo": modo},
        )
        notify_db_changed(conn)
    return {"ok": True, "modo": modo}


@router.post("/catalogos/{id_catalogo}/activo", summary="Activar/desactivar catálogo")
def activar_catalogo(
    id_catalogo: int, body: CambioActivo, usuario: dict = Depends(require_staff)
) -> dict[str, Any]:
    with get_connection() as conn:
        if not catalogo_service.activar_desactivar_catalogo(conn, id_catalogo, body.activo):
            raise HTTPException(status_code=404, detail="Catálogo no encontrado.")
        registrar_auditoria(
            conn,
            id_usuario=usuario["id_usuario"],
            entidad="catalogo",
            entidad_id=id_catalogo,
            accion="activar" if body.activo else "desactivar",
        )
        notify_db_changed(conn)
    return {"ok": True, "activo": body.activo}


@router.post("/catalogos/{id_catalogo}/productos", status_code=201, summary="Agregar producto al catálogo")
def agregar_producto_catalogo(
    id_catalogo: int, body: CatalogoProductoAdd, usuario: dict = Depends(require_staff)
) -> dict[str, Any]:
    with get_connection() as conn:
        try:
            catalogo = catalogo_service.agregar_producto(
                conn,
                id_catalogo,
                id_producto=body.id_producto,
                cantidad_base=body.cantidad_base,
                precio_unitario=body.precio_unitario,
            )
        except ValueError as e:
            raise HTTPException(status_code=422, detail=str(e))
        registrar_auditoria(
            conn,
            id_usuario=usuario["id_usuario"],
            entidad="catalogo",
            entidad_id=id_catalogo,
            accion="agregar_producto",
            valor_nuevo={"id_producto": body.id_producto, "cantidad_base": body.cantidad_base},
        )
        notify_db_changed(conn)
    return catalogo


@router.put("/catalogos/{id_catalogo}/productos/{id_producto}", summary="Ajustar cantidad/precio de producto")
def actualizar_producto_catalogo(
    id_catalogo: int,
    id_producto: int,
    body: CatalogoProductoUpdate,
    usuario: dict = Depends(require_staff),
) -> dict[str, Any]:
    with get_connection() as conn:
        catalogo = catalogo_service.actualizar_producto(
            conn,
            id_catalogo,
            id_producto,
            cantidad_base=body.cantidad_base,
            precio_unitario=body.precio_unitario,
        )
        if not catalogo:
            raise HTTPException(status_code=404, detail="Producto no está en el catálogo.")
        registrar_auditoria(
            conn,
            id_usuario=usuario["id_usuario"],
            entidad="catalogo",
            entidad_id=id_catalogo,
            accion="ajustar_producto",
            valor_nuevo={"id_producto": id_producto, "cantidad_base": body.cantidad_base, "precio_unitario": body.precio_unitario},
        )
        notify_db_changed(conn)
    return catalogo


@router.delete("/catalogos/{id_catalogo}/productos/{id_producto}", summary="Quitar producto del catálogo")
def quitar_producto_catalogo(
    id_catalogo: int, id_producto: int, usuario: dict = Depends(require_staff)
) -> dict[str, Any]:
    with get_connection() as conn:
        if not catalogo_service.quitar_producto(conn, id_catalogo, id_producto):
            raise HTTPException(status_code=404, detail="Producto no está en el catálogo.")
        registrar_auditoria(
            conn,
            id_usuario=usuario["id_usuario"],
            entidad="catalogo",
            entidad_id=id_catalogo,
            accion="quitar_producto",
            valor_nuevo={"id_producto": id_producto},
        )
        notify_db_changed(conn)
    return {"ok": True}
