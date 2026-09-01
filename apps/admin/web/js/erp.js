/*
 * erp.js — Páginas ERP del panel: pedidos, catálogo, inventario, compras y clientes.
 * Se apoya en los helpers globales de app.js (api, toast, PAGES, navigate) y en
 * el motor de vistas de views.js (createDataView, createTabsView, uiModal).
 */
/* global api, toast, PAGES, createDataView, createTabsView, uiModal, uiConfirm, uiModalCerrar, wireSimplePager, refreshSimplePager */

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const erpMoney = (n) => '$' + Number(n || 0).toLocaleString('es-PE', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const fmtQty = (n) => Number(n || 0).toLocaleString('es-PE');
const esc = (s) => String(s == null ? '' : s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

function erpDebounce(fn, ms = 280) {
  let t;
  return (...args) => { clearTimeout(t); t = setTimeout(() => fn(...args), ms); };
}

/** Opciones para combos buscables de productos (API paginada + filtro q). */
async function buscarProductosOpciones(q = '', limit = 50, { priorizarStockBajo = false } = {}) {
  const params = new URLSearchParams({ page: '1', page_size: String(Math.min(limit, 100)), incluir_inactivos: 'true' });
  if (q) params.set('q', q);
  const res = await api(`/catalogo/productos?${params}`);
  let items = res.items || [];
  if (priorizarStockBajo) {
    items = items.slice().sort((a, b) => {
      const aLow = Number(a.stock ?? 0) <= Number(a.stock_minimo ?? 10) ? 0 : 1;
      const bLow = Number(b.stock ?? 0) <= Number(b.stock_minimo ?? 10) ? 0 : 1;
      if (aLow !== bLow) return aLow - bLow;
      const stockDiff = Number(a.stock ?? 0) - Number(b.stock ?? 0);
      if (stockDiff !== 0) return stockDiff;
      return String(a.nombre_producto).localeCompare(String(b.nombre_producto), 'es');
    });
  }
  return items.map((p) => {
    const stock = Number(p.stock ?? 0);
    const min = Number(p.stock_minimo ?? 10);
    const bajo = stock <= min;
    const stockTag = bajo ? ` · stock ${fmtQty(stock)} ⚠` : ` · stock ${fmtQty(stock)}`;
    return {
      value: p.id_producto,
      label: `${p.nombre_producto}${p.sku ? ` [${p.sku}]` : ''}${stockTag} · ${erpMoney(p.precio_mayorista)}`,
      raw: p,
      stock_bajo: bajo,
    };
  });
}

function buscarProductosCompraOpciones(q = '') {
  return buscarProductosOpciones(q, 100, { priorizarStockBajo: true });
}

/** Combo buscable de producto embebido en HTML custom (p. ej. modal de paquetes). */
function initProductoSearchPicker({ wrap, hidden, input, list, onPick, excludeIds = [] }) {
  if (!wrap || !hidden || !input || !list) return;
  const getExclude = () => {
    const ex = typeof excludeIds === 'function' ? excludeIds() : excludeIds;
    return new Set((ex || []).map(Number));
  };
  const load = erpDebounce(async () => {
    const q = input.value.trim();
    const opts = (await buscarProductosOpciones(q, 50)).filter((o) => !getExclude().has(Number(o.value)));
    list.innerHTML = opts.length
      ? opts.map((o) => `<button type="button" class="ui-ss-opt" data-v="${o.value}" data-l="${esc(o.label)}">${esc(o.label)}</button>`).join('')
      : '<p class="meta ui-ss-empty">Sin resultados</p>';
    list.hidden = false;
    list.querySelectorAll('.ui-ss-opt').forEach((btn) => {
      const o = opts.find((x) => String(x.value) === btn.dataset.v);
      if (o?.raw) btn._raw = o.raw;
    });
  }, 250);
  input.addEventListener('input', () => void load());
  input.addEventListener('focus', () => void load());
  list.addEventListener('click', (e) => {
    const b = e.target.closest('.ui-ss-opt');
    if (!b) return;
    hidden.value = b.dataset.v;
    input.value = b.dataset.l || '';
    list.hidden = true;
    if (onPick) onPick(b._raw || { id_producto: Number(b.dataset.v), nombre_producto: b.dataset.l });
  });
  document.addEventListener('click', (e) => {
    if (!wrap.contains(e.target)) list.hidden = true;
  });
}

async function downloadComprobante(tipo, entidadId, label) {
  const res = await fetch(`/api/comprobantes/${tipo}/${entidadId}/pdf`);
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || 'No se pudo abrir el PDF');
  }
  const blob = await res.blob();
  const filename = `${label || tipo}.pdf`;
  if (typeof openPdfBlob === 'function') {
    openPdfBlob(blob, filename);
  } else {
    const url = URL.createObjectURL(new Blob([blob], { type: 'application/pdf' }));
    window.open(url, '_blank', 'noopener');
  }
}

const ESTADO_LABEL = {
  pendiente_pago: 'Pendiente de pago', pagado: 'Pagado', preparando: 'Preparando',
  enviado: 'Enviado', entregado: 'Entregado', cancelado: 'Cancelado', borrador: 'Borrador',
  aprobada: 'Aprobada', recibida: 'Recibida', parcialmente_recibida: 'Recibida parcial', cancelada: 'Cancelada',
  en_transito: 'En tránsito', en_hub: 'En centro de distribución', incidencia: 'Incidencia',
};

const ENVIO_DESC_SUGERIDA = {
  en_transito: 'En tránsito hacia el cliente',
  en_hub: 'Paquete en centro de distribución regional',
  entregado: 'Paquete entregado al destinatario',
  incidencia: 'Incidencia reportada en el envío',
};
const badge = (estado) => `<span class="badge badge-${esc(estado)}">${esc(ESTADO_LABEL[estado] || estado)}</span>`;

// ---------------------------------------------------------------------------
// Catálogo (pestañas: Productos | Categorías)
// ---------------------------------------------------------------------------

let catCategorias = [];
let catMarcas = [];
let catLineas = [];
let vistasCatalogo = {};

async function loadCatalogo() {
  if (!vistasCatalogo.productos) {
    const paneles = createTabsView('vista-catalogo', [
      { id: 'productos', label: 'Productos' },
      { id: 'categorias', label: 'Categorías' },
      { id: 'marcas', label: 'Marcas y líneas' },
      { id: 'precios', label: 'Listas de precios' },
      { id: 'catalogos', label: 'Paquetes' },
    ]);
    vistasCatalogo.productos = crearVistaProductos(paneles.productos);
    vistasCatalogo.categorias = crearVistaCategorias(paneles.categorias);
    vistasCatalogo.marcas = crearVistaMarcasLineas(paneles.marcas);
    vistasCatalogo.precios = crearVistaListasPrecios(paneles.precios);
    vistasCatalogo.catalogos = crearVistaCatalogos(paneles.catalogos);
  }
  await Promise.all([
    vistasCatalogo.productos.recargar(),
    vistasCatalogo.categorias.recargar(),
    vistasCatalogo.marcas.recargar(),
    vistasCatalogo.precios?.recargar(),
    vistasCatalogo.catalogos.recargar(),
  ]);
}

function crearVistaProductos(cont) {
  const st = { page: 1, page_size: 15, total_pages: 1 };
  return createDataView(cont, {
    state: st,
    autoLoad: false,
    buscar: { id: 'cat-q', placeholder: 'Nombre del producto...' },
    filtrosHtml: `
      <div class="field"><label>Categoría</label><select id="cat-filtro-categoria" data-dv-auto><option value="">Todas</option></select></div>
      <div class="field"><label>Precio desde</label><input type="number" id="cat-pmin" min="0" step="0.01" placeholder="0" data-dv-auto></div>
      <div class="field"><label>Precio hasta</label><input type="number" id="cat-pmax" min="0" step="0.01" placeholder="9999" data-dv-auto></div>
      <div class="field"><label>Portal</label>
        <select id="cat-activo" data-dv-auto>
          <option value="">Todos</option>
          <option value="1">Activos</option>
          <option value="0">Inactivos</option>
        </select>
      </div>`,
    columnas: [
      { key: 'imagen', label: 'Imagen', align: 'center', render: (p) => p.imagen_url ? `<img class="thumb" src="${esc(p.imagen_url.startsWith('http') || p.imagen_url.startsWith('/') ? p.imagen_url : '/media/' + p.imagen_url)}" alt="">` : '—' },
      { key: 'nombre_producto', label: 'Producto' },
      { key: 'categoria', label: 'Categoría' },
      { key: 'marca', label: 'Marca', render: (p) => esc(p.marca || '—') },
      { key: 'linea', label: 'Línea', render: (p) => esc(p.linea || '—') },
      { key: 'precio_unitario', label: 'P. unitario', align: 'num', render: (p) => erpMoney(p.precio_unitario) },
      { key: 'precio_mayorista', label: 'P. mayorista', align: 'num', render: (p) => erpMoney(p.precio_mayorista) },
      { key: 'descuento_pct', label: 'Dto %', align: 'num', render: (p) => badgeDescuento(p.descuento_pct, p.fecha_rebaja_hasta) },
      { key: 'stock', label: 'Stock', align: 'num', render: (p) => fmtQty(p.stock) },
      { key: 'activo', label: 'Portal', align: 'center', render: (p) => `
        <label class="gt-toggle" title="${p.activo ? 'Activo en portal' : 'Oculto del portal'}">
          <input type="checkbox" data-toggle-producto="${p.id_producto}" ${p.activo ? 'checked' : ''}>
          <span class="gt-toggle-slider"></span>
        </label>` },
    ],
    cargar: async (s) => {
      const sel = document.getElementById('cat-filtro-categoria');
      if (sel && !sel.dataset.cargado) {
        const cats = await api('/catalogo/categorias?incluir_inactivas=true');
        sel.innerHTML = '<option value="">Todas</option>' + cats
          .filter((c) => c.activo)
          .map((c) => `<option value="${c.id_item_type}">${esc(c.nombre)}</option>`).join('');
        sel.dataset.cargado = '1';
      }
      const params = new URLSearchParams({ page: s.page, page_size: s.page_size, incluir_inactivos: 'true' });
      const q = document.getElementById('cat-q')?.value?.trim();
      const idc = sel?.value;
      const pmin = document.getElementById('cat-pmin')?.value;
      const pmax = document.getElementById('cat-pmax')?.value;
      const act = document.getElementById('cat-activo')?.value;
      if (q) params.set('q', q);
      if (idc) params.set('id_item_type', idc);
      if (pmin !== '' && pmin != null) params.set('precio_min', pmin);
      if (pmax !== '' && pmax != null) params.set('precio_max', pmax);
      if (act !== '' && act != null) params.set('activo', act);
      return api(`/catalogo/productos?${params}`);
    },
    onAfterRender: (host) => {
      host.querySelectorAll('[data-toggle-producto]').forEach((inp) => {
        inp.addEventListener('change', async () => {
          const id = Number(inp.dataset.toggleProducto);
          try {
            await api(`/catalogo/productos/${id}/activo`, { method: 'POST', body: { activo: inp.checked } });
            toast(inp.checked ? 'Producto activado en portal' : 'Producto desactivado del portal');
            await vistasCatalogo.productos.recargar();
          } catch (e) {
            inp.checked = !inp.checked;
            toast(e.message || 'No se pudo cambiar el estado', 'error');
          }
        });
      });
    },
    filas: (res) => res.items || [],
    total: (res) => res.total_items ?? 0,
    filaClase: (p) => p.activo ? '' : 'row-inactive',
    resumen: (p) => {
      const dto = Number(p.descuento_pct || 0);
      const final = dto > 0
        ? Number(p.precio_mayorista) * (1 - dto / 100)
        : Number(p.precio_mayorista);
      return `<div class="detail-grid">
      <div><strong>Categoría:</strong> ${esc(p.categoria || '—')}</div>
      <div><strong>Marca / línea:</strong> ${esc(p.marca || '—')} · ${esc(p.linea || '—')}</div>
      <div><strong>P. unitario:</strong> ${erpMoney(p.precio_unitario)}</div>
      <div><strong>P. mayorista:</strong> ${erpMoney(p.precio_mayorista)}</div>
      <div><strong>Descuento:</strong> ${dto > 0 ? `${dto.toFixed(0)}% → ${erpMoney(final)}` : 'Sin rebaja'}</div>
      <div><strong>Stock:</strong> ${fmtQty(p.stock)}</div>
      <div><strong>Portal:</strong> ${p.activo ? 'Visible' : 'Oculto'} (usa el interruptor de la tabla)</div>
    </div>`;
    },
    titulo: (p) => p.nombre_producto,
    key: (p) => p.id_producto,
    acciones: {
      agregar: () => void openProductoModal(),
      modificar: (row) => void openProductoModal(row.id_producto),
      eliminar: async (row) => {
        const res = await api(`/catalogo/productos/${row.id_producto}`, { method: 'DELETE' });
        return res?.modo === 'eliminado'
          ? `Producto «${row.nombre_producto}» eliminado definitivamente`
          : `Producto «${row.nombre_producto}» desactivado (tiene historial: ventas, pedidos u órdenes)`;
      },
    },
    extras: (p) => [
      { label: 'Stock por bodega', clase: 'btn-secondary', enFila: true, opensModal: true, fn: () => void verStockPorBodega(p) },
    ],
    bloqueadas: { eliminar: 'Sin historial comercial: se elimina (limpia stock). Con historial: se desactiva.' },
    puedeEliminar: (p) => p.activo !== false,
    // Sin extras: Editar/Eliminar en tabla; portal con toggle.
    vacio: 'Sin productos',
  });
}

async function recargarCatalogo() {
  if (!vistasCatalogo.productos) return;
  await Promise.all([
    vistasCatalogo.productos.recargar(),
    vistasCatalogo.categorias.recargar(),
    vistasCatalogo.marcas.recargar(),
    vistasCatalogo.precios?.recargar(),
    vistasCatalogo.catalogos.recargar(),
  ]);
}

function crearVistaListasPrecios(cont) {
  return createDataView(cont, {
    autoLoad: false,
    pageSize: 15,
    buscar: { id: 'prec-list-q', placeholder: 'Buscar lista...' },
    filtrosHtml: `
      <div class="field"><label>Estado</label>
        <select id="prec-list-activa" data-dv-auto>
          <option value="">Todas</option>
          <option value="1">Activas</option>
          <option value="0">Inactivas</option>
        </select>
      </div>`,
    columnas: [
      { key: 'nombre', label: 'Lista' },
      { key: 'moneda', label: 'Moneda', render: (r) => esc(r.moneda || '—') },
      { key: 'n_precios', label: 'Precios fijados', align: 'num' },
      { key: 'activo', label: 'Activa', align: 'center', render: (r) => r.activo ? badge('activa') : badge('inactiva') },
    ],
    cargar: async () => {
      const items = await api('/catalogo/listas-precios');
      const q = document.getElementById('prec-list-q')?.value?.trim().toLowerCase();
      const activa = document.getElementById('prec-list-activa')?.value;
      let filtradas = items;
      if (q) filtradas = filtradas.filter((r) => String(r.nombre || '').toLowerCase().includes(q));
      if (activa === '1') filtradas = filtradas.filter((r) => r.activo);
      if (activa === '0') filtradas = filtradas.filter((r) => !r.activo);
      return { items: filtradas, total: filtradas.length };
    },
    titulo: (r) => r.nombre,
    key: (r) => r.id_lista,
    acciones: {
      ver: (row) => void abrirDetalleListaPrecios(row),
      agregar: null,
      modificar: null,
      eliminar: null,
    },
    vacio: 'Sin listas de precios configuradas',
  });
}

async function abrirDetalleListaPrecios(lista) {
  let precios = [];
  const cargar = async (q = '') => {
    const params = new URLSearchParams();
    if (q) params.set('q', q);
    precios = await api(`/catalogo/listas-precios/${lista.id_lista}/precios?${params}`);
    const tbody = document.getElementById('lista-prec-tbody');
    const meta = document.getElementById('lista-prec-meta');
    if (meta) meta.textContent = `${precios.length} precio(s) mostrado(s)`;
    if (!tbody) return;
    tbody.innerHTML = precios.length
      ? precios.map((p) => `
        <tr>
          <td>${esc(p.producto)}${p.sku ? ` <span class="meta">[${esc(p.sku)}]</span>` : ''}</td>
          <td class="num">${erpMoney(p.precio)}</td>
          <td class="row-actions"><button type="button" class="act-btn act-del" data-del-prec="${p.id_detalle}">Quitar</button></td>
        </tr>`).join('')
      : '<tr><td colspan="3" class="meta">Sin precios para este filtro.</td></tr>';
    tbody.querySelectorAll('[data-del-prec]').forEach((btn) => {
      btn.addEventListener('click', async () => {
        try {
          await api(`/catalogo/precios/${btn.dataset.delPrec}`, { method: 'DELETE' });
          toast('Precio eliminado');
          await cargar(document.getElementById('lista-prec-q')?.value?.trim() || '');
          await vistasCatalogo.precios?.recargar();
        } catch (e) { toast(e.message || 'No se pudo eliminar', 'error'); }
      });
    });
  };

  uiModal({
    modo: 'Detalle',
    tituloExtra: lista.nombre,
    ancho: 'lg',
    textoAceptar: 'Cerrar',
    campos: [{
      type: 'html',
      key: 'body',
      value: `
        <p class="meta"><strong>¿Para qué sirve?</strong> Las listas definen tarifas B2B por segmento de cliente. El MOQ mayorista se configura en <em>Configuración → MOQ_MAYORISTA</em>, no aquí.</p>
        <p class="meta">Lista «${esc(lista.nombre)}» · moneda ${esc(lista.moneda || 'USD')} · ${lista.n_precios || 0} precio(s) configurado(s).</p>
        <div class="lista-prec-toolbar">
          <div class="field"><label>Buscar producto</label>
            <input type="search" id="lista-prec-q" placeholder="Nombre o código…" autocomplete="off">
          </div>
          <button type="button" class="btn btn-primary btn-sm" id="lista-prec-buscar">Buscar</button>
          <button type="button" class="btn btn-secondary btn-sm" id="lista-prec-limpiar">Limpiar</button>
          <button type="button" class="btn btn-primary btn-sm" id="lista-prec-fijar">Fijar precio</button>
        </div>
        <p class="meta" id="lista-prec-meta"></p>
        <div class="table-wrap" style="max-height:280px;overflow:auto">
          <table class="table-erp"><thead><tr>
            <th>Producto</th><th class="num">Precio</th><th class="col-actions">Acción</th>
          </tr></thead><tbody id="lista-prec-tbody"></tbody></table>
        </div>`,
    }],
    onReady: () => {
      const qInp = document.getElementById('lista-prec-q');
      document.getElementById('lista-prec-buscar')?.addEventListener('click', () => void cargar(qInp?.value?.trim() || ''));
      document.getElementById('lista-prec-limpiar')?.addEventListener('click', () => {
        if (qInp) qInp.value = '';
        void cargar('');
      });
      qInp?.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') void cargar(qInp.value.trim());
      });
      document.getElementById('lista-prec-fijar')?.addEventListener('click', () => {
        uiModalCerrar();
        void abrirFijarPrecioLista(lista);
      });
      void cargar('');
    },
  });
}

async function abrirFijarPrecioLista(lista) {
  uiModal({
    modo: 'Precio',
    tituloExtra: lista.nombre,
    campos: [
      {
        key: 'id_producto',
        label: 'Producto',
        type: 'search-select',
        value: '',
        searchPlaceholder: 'Buscar por nombre o código…',
        searchFn: (q) => buscarProductosOpciones(q, 50),
      },
      { key: 'precio', label: 'Precio USD', type: 'number', step: '0.01', min: 0, value: '' },
    ],
    onAceptar: async (v) => {
      const precio = Number(v.precio);
      if (!(precio > 0)) { toast('Precio inválido', 'error'); return false; }
      if (!v.id_producto) { toast('Selecciona un producto', 'error'); return false; }
      await api('/catalogo/precios', {
        method: 'POST',
        body: {
          id_lista: lista.id_lista,
          id_producto: Number(v.id_producto),
          precio,
        },
      });
      toast('Precio guardado');
      await vistasCatalogo.precios?.recargar();
    },
  });
}

function crearVistaCategorias(cont) {
  const st = { page: 1, page_size: 15, total_pages: 1 };
  return createDataView(cont, {
    state: st,
    autoLoad: false,
    buscar: { id: 'catc-q', placeholder: 'Buscar categoría...' },
    filtrosHtml: `
      <div class="field"><label>Estado</label>
        <select id="catc-activa" data-dv-auto>
          <option value="">Todas</option>
          <option value="1">Activas</option>
          <option value="0">Inactivas</option>
        </select>
      </div>`,
    columnas: [
      { key: 'nombre', label: 'Nombre' },
      { key: 'slug', label: 'Slug' },
      { key: 'n_productos', label: 'Productos', align: 'num' },
      { key: 'descuento_pct', label: 'Descuento', align: 'num', render: (c) => badgeDescuento(c.descuento_pct, c.descuento_hasta) },
      { key: 'activo', label: 'Activa', align: 'center', render: (c) => `
        <label class="gt-toggle" title="${c.activo ? 'Activa' : 'Inactiva'}">
          <input type="checkbox" data-toggle-cat="${c.id_categoria}" ${c.activo ? 'checked' : ''}>
          <span class="gt-toggle-slider"></span>
        </label>` },
    ],
    cargar: async (s) => {
      catCategorias = await api('/catalogo/categorias?incluir_inactivas=true');
      const q = document.getElementById('catc-q')?.value?.trim().toLowerCase();
      const activa = document.getElementById('catc-activa')?.value;
      let filtradas = q ? catCategorias.filter((c) => c.nombre.toLowerCase().includes(q)) : catCategorias;
      if (activa === '1') filtradas = filtradas.filter((c) => c.activo);
      if (activa === '0') filtradas = filtradas.filter((c) => !c.activo);
      return { items: filtradas, total: filtradas.length };
    },
    onAfterRender: (host) => {
      host.querySelectorAll('[data-toggle-cat]').forEach((inp) => {
        inp.addEventListener('change', async () => {
          const id = Number(inp.dataset.toggleCat);
          try {
            await api(`/catalogo/categorias/${id}/activo`, { method: 'POST', body: { activo: inp.checked } });
            toast(inp.checked ? 'Categoría activada' : 'Categoría desactivada');
            await vistasCatalogo.categorias.recargar();
          } catch (e) {
            inp.checked = !inp.checked;
            toast(e.message || 'No se pudo cambiar', 'error');
          }
        });
      });
    },
    filaClase: (c) => c.activo ? '' : 'row-inactive',
    resumen: (c) => `<div class="detail-grid">
      <div><strong>Slug:</strong> ${esc(c.slug || '—')}</div>
      <div><strong>Productos:</strong> ${c.n_productos}</div>
      <div><strong>Descuento de categoría:</strong> ${Number(c.descuento_pct || 0) > 0 ? `${Number(c.descuento_pct)}%` : 'sin descuento'}</div>
      <div><strong>Vigente hasta:</strong> ${esc(c.descuento_hasta || 'sin fecha límite')}</div>
      <div><strong>Motivo:</strong> ${esc(c.descuento_motivo || '—')}</div>
      <div><strong>Activa:</strong> ${c.activo ? 'Sí' : 'No'} (interruptor en tabla)</div>
    </div>`,
    titulo: (c) => c.nombre,
    key: (c) => c.id_categoria,
    extras: (c) => [
      {
        label: 'Descuento de categoría', labelCorto: 'Dto', clase: 'btn-secondary', enFila: true, opensModal: true,
        fn: () => void abrirDescuentoCategoria(c),
      },
    ],
    acciones: {
      agregar: () => void openCategoriaModal(),
      modificar: (row) => void openCategoriaModal(row.id_categoria),
      eliminar: async (row) => {
        const res = await api(`/catalogo/categorias/${row.id_categoria}`, { method: 'DELETE' });
        return res?.modo === 'eliminada'
          ? `Categoría «${row.nombre}» eliminada`
          : `Categoría «${row.nombre}» desactivada (aún tiene productos vinculados)`;
      },
    },
    bloqueadas: { eliminar: 'Sin productos: se elimina del todo. Con productos: solo se desactiva.' },
    vacio: 'Sin categorías',
  });
}

function crearVistaMarcasLineas(cont) {
  cont.innerHTML = `
    <div class="catalogo-doble-vista">
      <h3 class="section-subtitle" style="margin:0 0 .75rem">Marcas</h3>
      <div id="vista-marcas-inner"></div>
      <h3 class="section-subtitle" style="margin:1.75rem 0 .35rem">Líneas de producto</h3>
      <p class="meta" style="margin:0 0 .75rem">Agrupan variantes bajo una marca (ej. «Línea Industrial» de «Andino Tools»). Asígnalas al crear o editar un producto.</p>
      <div id="vista-lineas-inner"></div>
    </div>`;
  const vm = crearVistaMarcas(cont.querySelector('#vista-marcas-inner'));
  const vl = crearVistaLineas(cont.querySelector('#vista-lineas-inner'));
  return {
    recargar: async () => {
      await vm.recargar();
      await vl.recargar();
    },
  };
}

function crearVistaMarcas(cont) {
  const st = { page: 1, page_size: 15, total_pages: 1 };
  return createDataView(cont, {
    state: st,
    autoLoad: false,
    buscar: { id: 'catm-q', placeholder: 'Buscar marca...' },
    columnas: [
      { key: 'nombre', label: 'Nombre' },
      { key: 'activo', label: 'Activa', align: 'center', render: (m) => `
        <label class="gt-toggle" title="${m.activo ? 'Activa' : 'Inactiva'}">
          <input type="checkbox" data-toggle-marca="${m.id_marca}" ${m.activo ? 'checked' : ''}>
          <span class="gt-toggle-slider"></span>
        </label>` },
    ],
    cargar: async () => {
      catMarcas = await api('/catalogo/marcas?incluir_inactivas=true');
      const q = document.getElementById('catm-q')?.value?.trim().toLowerCase();
      const filtradas = q ? catMarcas.filter((m) => m.nombre.toLowerCase().includes(q)) : catMarcas;
      return { items: filtradas, total: filtradas.length };
    },
    onAfterRender: (host) => {
      host.querySelectorAll('[data-toggle-marca]').forEach((inp) => {
        inp.addEventListener('change', async () => {
          const id = Number(inp.dataset.toggleMarca);
          const marca = catMarcas.find((m) => m.id_marca === id);
          if (!marca) return;
          try {
            await api(`/catalogo/marcas/${id}`, { method: 'PUT', body: { activo: inp.checked } });
            toast(inp.checked ? 'Marca activada' : 'Marca desactivada');
            await vistasCatalogo.marcas.recargar();
          } catch (e) {
            inp.checked = !inp.checked;
            toast(e.message || 'No se pudo cambiar', 'error');
          }
        });
      });
    },
    filaClase: (m) => m.activo ? '' : 'row-inactive',
    resumen: (m) => `<div class="detail-grid">
      <div><strong>Estado:</strong> ${m.activo ? 'Activa' : 'Inactiva'}</div>
      <div><strong>Uso:</strong> disponible al crear o editar productos</div>
    </div>`,
    titulo: (m) => m.nombre,
    key: (m) => m.id_marca,
    acciones: {
      agregar: () => void openMarcaModal(),
      modificar: (row) => void openMarcaModal(row.id_marca),
    },
    vacio: 'Sin marcas — crea la primera para clasificar productos',
  });
}

function crearVistaLineas(cont) {
  const st = { page: 1, page_size: 15, total_pages: 1 };
  return createDataView(cont, {
    state: st,
    autoLoad: false,
    buscar: { id: 'catl-q', placeholder: 'Buscar línea...' },
    columnas: [
      { key: 'nombre', label: 'Nombre' },
      { key: 'marca', label: 'Marca', render: (l) => esc(l.marca || '—') },
      { key: 'descripcion', label: 'Descripción', render: (l) => esc(l.descripcion || '—') },
      { key: 'activo', label: 'Activa', align: 'center', render: (l) => `
        <label class="gt-toggle" title="${l.activo ? 'Activa' : 'Inactiva'}">
          <input type="checkbox" data-toggle-linea="${l.id_linea}" ${l.activo ? 'checked' : ''}>
          <span class="gt-toggle-slider"></span>
        </label>` },
    ],
    cargar: async () => {
      catLineas = await api('/catalogo/lineas?incluir_inactivas=true');
      const q = document.getElementById('catl-q')?.value?.trim().toLowerCase();
      const filtradas = q
        ? catLineas.filter((l) => (l.nombre + ' ' + (l.marca || '')).toLowerCase().includes(q))
        : catLineas;
      return { items: filtradas, total: filtradas.length };
    },
    onAfterRender: (host) => {
      host.querySelectorAll('[data-toggle-linea]').forEach((inp) => {
        inp.addEventListener('change', async () => {
          const id = Number(inp.dataset.toggleLinea);
          const linea = catLineas.find((l) => l.id_linea === id);
          if (!linea) return;
          try {
            await api(`/catalogo/lineas/${id}`, { method: 'PUT', body: { activo: inp.checked } });
            toast(inp.checked ? 'Línea activada' : 'Línea desactivada');
            await vistasCatalogo.marcas.recargar();
          } catch (e) {
            inp.checked = !inp.checked;
            toast(e.message || 'No se pudo cambiar', 'error');
          }
        });
      });
    },
    filaClase: (l) => l.activo ? '' : 'row-inactive',
    resumen: (l) => `<div class="detail-grid">
      <div><strong>Marca:</strong> ${esc(l.marca || 'Sin marca')}</div>
      <div><strong>Descripción:</strong> ${esc(l.descripcion || '—')}</div>
      <div><strong>Estado:</strong> ${l.activo ? 'Activa' : 'Inactiva'}</div>
    </div>`,
    titulo: (l) => l.nombre,
    key: (l) => l.id_linea,
    acciones: {
      agregar: () => void openLineaModal(),
      modificar: (row) => void openLineaModal(row.id_linea),
    },
    vacio: 'Sin líneas — crea una vinculada a una marca',
  });
}

function openMarcaModal(idMarca) {
  const marca = idMarca ? catMarcas.find((m) => m.id_marca === idMarca) : null;
  uiModal({
    modo: marca ? 'Actualizar' : 'Agregar',
    tituloExtra: marca ? marca.nombre : 'Nueva marca',
    ancho: 'md',
    campos: [
      { key: 'nombre', label: 'Nombre', value: marca?.nombre || '', maxlength: 80 },
      ...(marca ? [{ key: 'activo', label: 'Activa', type: 'checkbox', value: marca.activo }] : []),
    ],
    onAceptar: async (v) => {
      if (!v.nombre || v.nombre.trim().length < 2) { toast('Nombre inválido (mín. 2 caracteres)', 'error'); return false; }
      const body = { nombre: v.nombre.trim() };
      if (marca) body.activo = !!v.activo;
      if (marca) {
        await api(`/catalogo/marcas/${marca.id_marca}`, { method: 'PUT', body });
        toast('Marca actualizada');
      } else {
        await api('/catalogo/marcas', { method: 'POST', body });
        toast('Marca creada');
      }
      await vistasCatalogo.marcas.recargar();
      return true;
    },
  });
}

async function openLineaModal(idLinea) {
  const linea = idLinea ? catLineas.find((l) => l.id_linea === idLinea) : null;
  if (!catMarcas.length) catMarcas = await api('/catalogo/marcas?incluir_inactivas=true');
  const optsMarca = [{ value: '', label: 'Sin marca' }]
    .concat(catMarcas.filter((m) => m.activo).map((m) => ({ value: String(m.id_marca), label: m.nombre })));
  uiModal({
    modo: linea ? 'Actualizar' : 'Agregar',
    tituloExtra: linea ? linea.nombre : 'Nueva línea',
    ancho: 'md',
    campos: [
      { key: 'nombre', label: 'Nombre', value: linea?.nombre || '', maxlength: 80 },
      {
        key: 'id_marca', label: 'Marca (opcional)', type: 'select',
        options: optsMarca,
        value: linea?.id_marca != null ? String(linea.id_marca) : '',
      },
      { key: 'descripcion', label: 'Descripción', type: 'textarea', value: linea?.descripcion || '', maxlength: 200 },
      ...(linea ? [{ key: 'activo', label: 'Activa', type: 'checkbox', value: linea.activo }] : []),
    ],
    onAceptar: async (v) => {
      if (!v.nombre || v.nombre.trim().length < 2) { toast('Nombre inválido (mín. 2 caracteres)', 'error'); return false; }
      const body = {
        nombre: v.nombre.trim(),
        id_marca: v.id_marca ? Number(v.id_marca) : null,
        descripcion: v.descripcion?.trim() || null,
      };
      if (linea) body.activo = !!v.activo;
      if (linea) {
        await api(`/catalogo/lineas/${linea.id_linea}`, { method: 'PUT', body });
        toast('Línea actualizada');
      } else {
        await api('/catalogo/lineas', { method: 'POST', body });
        toast('Línea creada');
      }
      await vistasCatalogo.marcas.recargar();
      return true;
    },
  });
}

function badgeDescuento(pct, hasta) {
  const n = Number(pct || 0);
  if (n <= 0) return '<span class="meta">—</span>';
  const vencido = hasta && new Date(hasta) < new Date(new Date().toDateString());
  if (vencido) return `<span class="badge badge-cancelado">${n}% vencido</span>`;
  return `<span class="badge badge-success">-${n}%</span>`;
}

const CAMPOS_VIGENCIA_DESCUENTO = (valores) => [
  {
    key: 'descuento_hasta', label: 'Vigente hasta (opcional)', type: 'date',
    value: valores.descuento_hasta || '',
  },
  {
    key: 'descuento_motivo', label: 'Mensaje para el cliente (opcional)',
    placeholder: 'Ej. Liquidación de temporada', maxlength: 200,
    value: valores.descuento_motivo || '',
  },
  {
    key: 'avisar_clientes', label: 'Avisar a los clientes del portal',
    type: 'checkbox', value: true,
  },
];

async function abrirDescuentoCategoria(categoria) {
  uiModal({
    modo: 'Descuento', tituloExtra: `Categoría ${categoria.nombre}`, ancho: 'md',
    campos: [
      {
        key: 'info', type: 'html',
        value: `<p class="meta">Aplica a los ${categoria.n_productos} productos de la categoría. Si un producto ya tiene su propio descuento, el cliente recibe el mayor de los dos (nunca se suman).</p>`,
      },
      {
        key: 'descuento_pct', label: 'Descuento (%)', type: 'number',
        min: 0, max: 90, step: 0.5, value: categoria.descuento_pct || 0,
      },
      {
        key: 'descuento_aplica_a', label: 'Aplica a', type: 'select',
        options: [
          { value: 'mayorista', label: 'Solo precio mayorista' },
          { value: 'retail', label: 'Solo precio unitario' },
          { value: 'ambos', label: 'Ambos precios' },
        ],
        value: categoria.descuento_aplica_a || 'mayorista',
      },
      ...CAMPOS_VIGENCIA_DESCUENTO(categoria),
    ],
    textoAceptar: 'Publicar descuento',
    onAceptar: async (v) => {
      const pct = Number(v.descuento_pct);
      if (!Number.isFinite(pct) || pct < 0 || pct > 90) { toast('El descuento debe estar entre 0 y 90%', 'error'); return false; }
      const r = await api(`/catalogo/categorias/${categoria.id_categoria}`, {
        method: 'PUT',
        body: {
          descuento_pct: pct,
          descuento_aplica_a: v.descuento_aplica_a,
          descuento_hasta: v.descuento_hasta || null,
          descuento_motivo: (v.descuento_motivo || '').trim() || null,
          avisar_clientes: !!v.avisar_clientes,
        },
      });
      toast(pct > 0
        ? `Descuento del ${pct}% aplicado a «${r.nombre}»${v.avisar_clientes ? ' y avisado a los clientes' : ''}`
        : `Descuento retirado de «${r.nombre}»`);
      await vistasCatalogo.categorias.recargar();
    },
  });
}

async function abrirDescuentoPaquete(catalogo) {
  uiModal({
    modo: 'Descuento', tituloExtra: `Paquete ${catalogo.nombre}`, ancho: 'md',
    campos: [
      {
        key: 'info', type: 'html',
        value: '<p class="meta">Se aplica solo al comprar el paquete y es adicional al descuento de producto o categoría: premia llevar el bundle completo.</p>',
      },
      {
        key: 'descuento_pct', label: 'Descuento del paquete (%)', type: 'number',
        min: 0, max: 90, step: 0.5, value: catalogo.descuento_pct || 0,
      },
      ...CAMPOS_VIGENCIA_DESCUENTO(catalogo),
    ],
    textoAceptar: 'Publicar descuento',
    onAceptar: async (v) => {
      const pct = Number(v.descuento_pct);
      if (!Number.isFinite(pct) || pct < 0 || pct > 90) { toast('El descuento debe estar entre 0 y 90%', 'error'); return false; }
      const r = await api(`/catalogo/catalogos/${catalogo.id_catalogo}`, {
        method: 'PUT',
        body: {
          descuento_pct: pct,
          descuento_hasta: v.descuento_hasta || null,
          descuento_motivo: (v.descuento_motivo || '').trim() || null,
          avisar_clientes: !!v.avisar_clientes,
        },
      });
      toast(pct > 0
        ? `Descuento del ${pct}% aplicado al paquete «${r.nombre}»${v.avisar_clientes ? ' y avisado a los clientes' : ''}`
        : `Descuento retirado del paquete «${r.nombre}»`);
      await vistasCatalogo.catalogos.recargar();
    },
  });
}

// ---------------------------------------------------------------------------
// Catálogos / paquetes configurables
// ---------------------------------------------------------------------------

let catCatalogos = [];

function crearVistaCatalogos(cont) {
  const st = { page: 1, page_size: 15, total_pages: 1 };
  return createDataView(cont, {
    state: st,
    autoLoad: false,
    buscar: { id: 'catcat-q', placeholder: 'Buscar catálogo...' },
    columnas: [
      { key: 'nombre', label: 'Nombre' },
      { key: 'categoria', label: 'Categoría' },
      { key: 'n_productos', label: 'Productos', align: 'num' },
      { key: 'precio_total', label: 'Precio base', align: 'num', render: (c) => erpMoney(c.precio_total) },
      { key: 'descuento_pct', label: 'Descuento', align: 'num', render: (c) => badgeDescuento(c.descuento_pct, c.descuento_hasta) },
      { key: 'precio_total_final', label: 'Precio final', align: 'num', render: (c) => erpMoney(c.precio_total_final ?? c.precio_total) },
      { key: 'activo', label: 'Activo', align: 'center', render: (c) => `
        <label class="gt-toggle" title="${c.activo ? 'Activo' : 'Inactivo'}">
          <input type="checkbox" data-toggle-pack="${c.id_catalogo}" ${c.activo ? 'checked' : ''}>
          <span class="gt-toggle-slider"></span>
        </label>` },
    ],
    cargar: async (s) => {
      catCatalogos = await api('/catalogo/catalogos?incluir_inactivas=true');
      const q = document.getElementById('catcat-q')?.value?.trim().toLowerCase();
      const flt = q ? catCatalogos.filter((c) => (c.nombre || '').toLowerCase().includes(q)) : catCatalogos;
      return { items: flt, total: flt.length };
    },
    onAfterRender: (host) => {
      host.querySelectorAll('[data-toggle-pack]').forEach((inp) => {
        inp.addEventListener('change', async () => {
          const id = Number(inp.dataset.togglePack);
          try {
            await api(`/catalogo/catalogos/${id}/activo`, { method: 'POST', body: { activo: inp.checked } });
            toast(inp.checked ? 'Catálogo activado' : 'Catálogo desactivado');
            await vistasCatalogo.catalogos.recargar();
          } catch (e) {
            inp.checked = !inp.checked;
            toast(e.message || 'No se pudo cambiar', 'error');
          }
        });
      });
    },
    filaClase: (c) => c.activo ? '' : 'row-inactive',
    resumen: (c) => `<div class="detail-grid">
      <div><strong>Categoría:</strong> ${dvEsc(c.categoria || '—')}</div>
      <div><strong>Productos:</strong> ${c.n_productos}</div>
      <div><strong>Precio total base:</strong> ${erpMoney(c.precio_total)}</div>
      <div><strong>Descuento del paquete:</strong> ${Number(c.descuento_pct || 0) > 0 ? `${Number(c.descuento_pct)}%` : 'sin descuento'}</div>
      <div><strong>Precio con descuento:</strong> ${erpMoney(c.precio_total_final ?? c.precio_total)}</div>
      <div><strong>Vigente hasta:</strong> ${dvEsc(c.descuento_hasta || 'sin fecha límite')}</div>
      <div><strong>Activo:</strong> ${c.activo ? 'Sí' : 'No'} (interruptor en tabla)</div>
    </div>`,
    titulo: (c) => c.nombre,
    key: (c) => c.id_catalogo,
    extras: (c) => [
      {
        label: 'Descuento del paquete', labelCorto: 'Dto', clase: 'btn-secondary', enFila: true, opensModal: true,
        fn: () => void abrirDescuentoPaquete(c),
      },
    ],
    acciones: {
      agregar: () => void openCatalogoModal(),
      modificar: (row) => void openCatalogoModal(row.id_catalogo),
      eliminar: async (row) => {
        const r = await api(`/catalogo/catalogos/${row.id_catalogo}`, { method: 'DELETE' });
        if (r?.modo === 'desactivado') {
          return `Catálogo «${row.nombre}» desactivado (tenía productos; no se borró en duro)`;
        }
        return `Catálogo «${row.nombre}» eliminado`;
      },
    },
    bloqueadas: { eliminar: 'Si el catálogo tiene productos, se desactiva. Vacío = se elimina. Los productos sueltos siguen en el portal.' },
    vacio: 'Sin catálogos',
  });
}

async function openCatalogoModal(idCatalogo) {
  const existente = idCatalogo ? (catCatalogos.find((c) => c.id_catalogo === idCatalogo) || null) : null;
  const detalle = idCatalogo ? await api(`/catalogo/catalogos/${idCatalogo}`) : null;
  const prodCache = new Map();
  const cats = catCategorias.length
    ? catCategorias
    : await api('/catalogo/categorias?incluir_inactivas=true').catch(() => []);

  const filas = detalle ? detalle.productos.map((pr) => ({
    id_producto: pr.id_producto,
    nombre_producto: pr.nombre_producto,
    cantidad_base: pr.cantidad_base,
    precio_unitario: pr.precio_unitario,
    imagen_url: pr.imagen_url,
    nuevo: false,
  })) : [];

  const renderFilas = (ov) => {
    const cont = ov.querySelector('.cat-filas');
    cont.innerHTML = filas.length
      ? filas.map((f, i) => `
          <div class="cat-fila" data-i="${i}">
            <span class="cat-p-img">${f.imagen_url ? `<img src="${f.imagen_url.startsWith('http') || f.imagen_url.startsWith('/') ? f.imagen_url : '/media/' + f.imagen_url}" alt="">` : ''}</span>
            <span class="cat-p-nombre" title="${dvEsc(f.nombre_producto)}">${dvEsc(f.nombre_producto)}</span>
            <span class="cat-p-base">Base: ${f.cantidad_base}</span>
            <span class="cat-p-precio">${erpMoney(f.precio_unitario)}</span>
            <button type="button" class="btn btn-danger btn-xs" data-quitar="${i}">Quitar</button>
          </div>`).join('')
      : '<p class="meta">Sin productos. Agrega productos al catálogo en el bloque de abajo.</p>';
      actualizarPreview(ov);
  };

  const actualizarPreview = (ov) => {
    const img = ov.querySelector('#cat-add-preview');
    const pid = Number(ov.querySelector('#cat-add-prod')?.value || 0);
    const prod = prodCache.get(pid);
    if (!img) return;
    const url = prod?.imagen_url;
    img.innerHTML = url
      ? `<img src="${url.startsWith('http') || url.startsWith('/') ? url : '/media/' + url}" alt="">`
      : '<span>Sin imagen</span>';
  };

  const agregarFila = (ov) => {
    const pid = Number(ov.querySelector('#cat-add-prod')?.value || 0);
    if (!pid) { toast('Busca y selecciona un producto', 'error'); return; }
    if (filas.some((f) => f.id_producto === pid)) { toast('Ese producto ya está en el paquete', 'error'); return; }
    const prod = prodCache.get(pid);
    const cant = Math.max(1, Number(ov.querySelector('#cat-add-cant')?.value || 10)) || 1;
    const precioRaw = ov.querySelector('#cat-add-precio')?.value?.trim();
    const precio = precioRaw ? Number(precioRaw) : (Number(prod?.precio_mayorista) || 0);
    if (!(precio > 0)) { toast('Precio inválido', 'error'); return; }
    filas.push({
      id_producto: pid,
      nombre_producto: prod?.nombre_producto || `Producto #${pid}`,
      cantidad_base: Math.min(100000, cant),
      precio_unitario: precio,
      imagen_url: prod?.imagen_url,
      nuevo: true,
    });
    renderFilas(ov);
  };

  const descuentoBase = detalle || existente || {};

  const guardar = async (v) => {
    const nombre = String(v.nombre || '').trim();
    if (nombre.length < 2) { toast('Nombre inválido', 'error'); return false; }
    const idItemType = v.id_item_type ? Number(v.id_item_type) : null;
    const dtoPct = Math.min(90, Math.max(0, Number(v.descuento_pct) || 0));
    if (!Number.isFinite(dtoPct)) { toast('Descuento inválido (0–90%)', 'error'); return false; }
    let id = existente ? existente.id_catalogo : null;
    if (!id) {
      const creado = await api('/catalogo/catalogos', {
        method: 'POST',
        body: { nombre, descripcion: v.descripcion || null, id_item_type: idItemType, activo: true },
      });
      id = creado.id_catalogo;
    }
      const body = {
      nombre,
      descripcion: v.descripcion || null,
      id_item_type: idItemType,
      activo: existente ? !!v.activo : true,
      descuento_pct: dtoPct,
      descuento_hasta: v.descuento_hasta || null,
      descuento_motivo: (v.descuento_motivo || '').trim() || null,
      avisar_clientes: !!v.avisar_clientes && dtoPct > 0,
    };
    await api(`/catalogo/catalogos/${id}`, { method: 'PUT', body });
    for (const f of filas) {
      const itemBody = {
        cantidad_base: Math.min(100000, Math.max(1, Number(f.cantidad_base) || 1)),
        precio_unitario: Number(f.precio_unitario) || null,
      };
      if (f.nuevo) {
        itemBody.id_producto = f.id_producto;
        await api(`/catalogo/catalogos/${id}/productos`, { method: 'POST', body: itemBody });
      } else {
        await api(`/catalogo/catalogos/${id}/productos/${f.id_producto}`, { method: 'PUT', body: itemBody });
      }
    }
    if (detalle) {
      const idsFila = filas.map((f) => f.id_producto);
      for (const pr of detalle.productos) {
        if (!idsFila.includes(pr.id_producto)) {
          await api(`/catalogo/catalogos/${id}/productos/${pr.id_producto}`, { method: 'DELETE' });
        }
      }
    }
    toast(existente
      ? (dtoPct > 0 ? `Paquete actualizado con ${dtoPct}% de descuento` : 'Paquete actualizado')
      : 'Paquete creado');
    await recargarCatalogo();
    return true;
  };

  uiModal({
    modo: existente ? 'Actualizar' : 'Agregar',
    tituloExtra: existente ? existente.nombre : 'Nuevo catálogo',
    ancho: 'lg',
    campos: [
      { key: 'nombre', label: 'Nombre del catálogo', value: existente?.nombre || '' },
      { key: 'descripcion', label: 'Descripción', type: 'textarea', value: existente?.descripcion || '' },
      {
        key: 'id_item_type', label: 'Categoría', type: 'select', value: existente?.id_item_type ?? '',
        options: cats.filter((c) => c.activo).map((c) => ({ value: c.id_item_type, label: c.nombre })),
      },
      ...(existente ? [{ key: 'activo', label: 'Activo', type: 'checkbox', value: existente.activo }] : []),
      {
        key: 'descuento_info', type: 'html',
        value: '<p class="meta" style="margin:0"><strong>Descuento del paquete</strong> — premia comprar el bundle completo. Es adicional al descuento de producto o categoría (no se suman entre sí; se aplica el mayor).</p>',
      },
      {
        key: 'descuento_pct', label: 'Descuento (%)', type: 'number',
        min: 0, max: 90, step: 0.5, value: descuentoBase.descuento_pct || 0,
      },
      ...CAMPOS_VIGENCIA_DESCUENTO(descuentoBase),
      { type: 'html', key: 'config', value: `
        <div class="field" style="grid-column:1/-1">
          <label>Productos del catálogo</label>
          <div class="cat-filas"></div>
        </div>
        <div class="field" style="grid-column:1/-1">
          <label>Agregar producto al catálogo</label>
          <div class="cat-agregar">
            <div id="cat-add-preview" class="cat-preview"></div>
            <div class="ui-search-select cat-ss-prod" style="flex:2;min-width:220px">
              <input type="hidden" id="cat-add-prod" value="">
              <input type="search" class="ui-ss-input" id="cat-add-prod-q" placeholder="Buscar producto por nombre…" autocomplete="off">
              <div class="ui-ss-list" id="cat-add-prod-list" hidden></div>
            </div>
            <input type="number" id="cat-add-cant" min="1" max="100000" step="1" value="10" title="Cantidad por defecto">
            <input type="number" id="cat-add-precio" min="0.01" step="0.01" placeholder="Precio/u (vacío = mayorista)" title="Precio por unidad">
            <button type="button" class="btn btn-primary" id="cat-add-btn">+ Agregar</button>
          </div>
          <span class="field-hint">El comprador podrá ajustar estas cantidades en el portal; el precio se recalcula solo.</span>
        </div>` },
    ],
    onReady: (ov) => {
      renderFilas(ov);
      initProductoSearchPicker({
        wrap: ov.querySelector('.cat-ss-prod'),
        hidden: ov.querySelector('#cat-add-prod'),
        input: ov.querySelector('#cat-add-prod-q'),
        list: ov.querySelector('#cat-add-prod-list'),
        excludeIds: () => filas.map((f) => f.id_producto),
        onPick: (p) => {
          if (p?.id_producto) prodCache.set(Number(p.id_producto), p);
          actualizarPreview(ov);
        },
      });
      ov.querySelector('#cat-add-btn').addEventListener('click', () => agregarFila(ov));
      ov.querySelector('.cat-filas').addEventListener('click', (e) => {
        const b = e.target.closest('[data-quitar]');
        if (!b) return;
        filas.splice(Number(b.dataset.quitar), 1);
        renderFilas(ov);
      });
    },
    onAceptar: guardar,
  });
}

async function subirImagen(file) {
  const fd = new FormData();
  fd.append('file', file);
  const res = await fetch('/api/catalogo/imagenes', { method: 'POST', body: fd });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.detail || 'No se pudo subir la imagen.');
  return data.ruta;
}

function openCategoriaModal(idCategoria) {
  const cat = idCategoria ? catCategorias.find((c) => c.id_categoria === idCategoria) : null;
  uiModal({
    modo: cat ? 'Actualizar' : 'Agregar',
    tituloExtra: cat ? cat.nombre : 'Nueva categoría',
    ancho: cat ? 'lg' : 'md',
    campos: [
      { key: 'nombre', label: 'Nombre', value: cat?.nombre || '' },
      { key: 'descripcion', label: 'Descripción', type: 'textarea', value: cat?.descripcion || '' },
      ...(cat ? [{ key: 'activo', label: 'Activa', type: 'checkbox', value: cat.activo }] : []),
      ...(cat ? [
        {
          key: 'descuento_info', type: 'html',
          value: '<p class="meta" style="margin:0"><strong>Descuento de categoría</strong> — aplica a todos los productos de la familia. Si un producto tiene su propio descuento, el cliente recibe el mayor (no se suman).</p>',
        },
        {
          key: 'descuento_pct', label: 'Descuento (%)', type: 'number',
          min: 0, max: 90, step: 0.5, value: cat.descuento_pct || 0,
        },
        {
          key: 'descuento_aplica_a', label: 'Aplica a', type: 'select',
          options: [
            { value: 'mayorista', label: 'Solo precio mayorista' },
            { value: 'retail', label: 'Solo precio unitario' },
            { value: 'ambos', label: 'Ambos precios' },
          ],
          value: cat.descuento_aplica_a || 'mayorista',
        },
        ...CAMPOS_VIGENCIA_DESCUENTO(cat),
      ] : []),
    ],
    onAceptar: async (v) => {
      if (!v.nombre || v.nombre.trim().length < 2) { toast('Nombre inválido', 'error'); return false; }
      const dtoPct = Math.min(90, Math.max(0, Number(v.descuento_pct) || 0));
      if (cat && !Number.isFinite(dtoPct)) { toast('Descuento inválido (0–90%)', 'error'); return false; }
      const body = {
        nombre: v.nombre.trim(),
        descripcion: v.descripcion || null,
      };
      if (cat) {
        body.activo = !!v.activo;
        body.descuento_pct = dtoPct;
        body.descuento_aplica_a = v.descuento_aplica_a || 'mayorista';
        body.descuento_hasta = v.descuento_hasta || null;
        body.descuento_motivo = (v.descuento_motivo || '').trim() || null;
        body.avisar_clientes = !!v.avisar_clientes && dtoPct > 0;
        await api(`/catalogo/categorias/${cat.id_categoria}`, { method: 'PUT', body });
        toast(dtoPct > 0 ? `Categoría actualizada con ${dtoPct}% de descuento` : 'Categoría actualizada');
      } else {
        await api('/catalogo/categorias', { method: 'POST', body });
        toast('Categoría creada');
      }
      await recargarCatalogo();
    },
  });
}

async function openProductoModal(idProducto) {
  const prod = idProducto ? await api(`/catalogo/productos/${idProducto}`) : null;
  const cats = await api('/catalogo/categorias?incluir_inactivas=true');
  const opciones = cats.filter((c) => c.activo).map((c) => ({ value: c.id_item_type, label: c.nombre }));
  let marcas = [], lineas = [];
  try {
    marcas = await api('/catalogo/marcas').catch(() => []);
  } catch (_) { marcas = []; }
  try {
    lineas = await api('/catalogo/lineas').catch(() => []);
  } catch (_) { lineas = []; }
  if (!Array.isArray(marcas)) marcas = [];
  if (!Array.isArray(lineas)) lineas = [];
  const optMarcas = [{ value: '', label: '— Sin marca —' }, ...marcas.map((m) => ({ value: m.id_marca, label: m.nombre }))];
  const marcaInicial = prod?.id_marca || '';
  const lineasActivas = lineas.filter((l) => l.activo !== false);
  const lineasFiltradas = marcaInicial
    ? lineasActivas.filter((l) => Number(l.id_marca) === Number(marcaInicial))
    : [];
  const optLineas = [
    { value: '', label: marcaInicial ? '— Selecciona línea —' : '— Primero elige una marca —' },
    ...lineasFiltradas.map((l) => ({ value: l.id_linea, label: l.nombre })),
  ];
  uiModal({
    modo: prod ? 'Actualizar' : 'Agregar',
    tituloExtra: prod ? prod.nombre_producto : 'Nuevo producto',
    campos: [
      { key: 'nombre_producto', label: 'Nombre', value: prod?.nombre_producto || '' },
      { key: 'id_item_type', label: 'Categoría', type: 'select', options: opciones, value: prod?.id_item_type },
      { key: 'id_marca', label: 'Marca', type: 'select', options: optMarcas, value: prod?.id_marca || '' },
      { key: 'id_linea', label: 'Línea de producto', type: 'select', options: optLineas, value: prod?.id_linea || '' },
      {
        key: 'sku',
        label: 'Código interno',
        value: prod?.sku || '',
        disabled: !prod,
        placeholder: prod ? '' : 'Se asigna al guardar (ej. GM-000042)',
        hint: prod
          ? 'Identificador único del producto en inventario y reportes'
          : 'Se genera automáticamente al crear el producto',
      },
      { key: 'precio_unitario', label: 'Precio unitario', type: 'number', step: '0.01', min: 0, value: prod?.precio_unitario ?? '' },
      { key: 'precio_mayorista', label: 'Precio mayorista', type: 'number', step: '0.01', min: 0, value: prod?.precio_mayorista ?? '' },
      {
        key: 'descuento_pct',
        label: 'Descuento / rebaja (%)',
        type: 'number',
        step: '1',
        min: 0,
        max: 100,
        value: prod?.descuento_pct ?? 0,
      },
      {
        key: 'descuento_aplica_a',
        label: 'Aplicar descuento a',
        type: 'select',
        options: [
          { value: 'mayorista', label: 'Solo mayorista' },
          { value: 'retail', label: 'Solo retail (lista)' },
          { value: 'ambos', label: 'Ambos precios' },
        ],
        value: prod?.descuento_aplica_a || 'mayorista',
      },
      {
        key: 'dto_help',
        type: 'html',
        value: '<p class="meta">El % se aplica según la opción. <strong>Mayorista</strong> = precio B2B; <strong>Retail</strong> = precio lista; <strong>Ambos</strong> = los dos.</p>',
      },
      ...CAMPOS_VIGENCIA_DESCUENTO({
        descuento_hasta: prod?.fecha_rebaja_hasta,
        descuento_motivo: prod?.descuento_motivo,
      }),
      ...(prod ? [] : [{
        key: 'stock_info',
        type: 'html',
        value: '<p class="meta"><strong>Stock inicial = 0.</strong> El producto sale «Sin stock» en el portal hasta que ingreses mercancía con una <em>orden de compra</em> o ajuste de inventario.</p>',
      }]),
      {
        key: 'stock_minimo',
        label: 'Stock mínimo (aviso «Poco stock»)',
        type: 'number',
        min: 0,
        value: prod?.stock_minimo ?? 10,
      },
      { key: 'descripcion', label: 'Descripción', type: 'textarea', value: prod?.descripcion || '' },
      { key: 'imagen', label: 'Imagen (JPG/PNG/WEBP, máx 5MB)', type: 'file' },
      ...(prod ? [{ key: 'activo', label: 'Activo en portal', type: 'checkbox', value: prod.activo }] : []),
    ],
    onReady: (ov) => {
      const selMarca = ov.querySelector('#uf-id_marca');
      const selLinea = ov.querySelector('#uf-id_linea');
      if (!selMarca || !selLinea) return;
      const actualizarLineas = () => {
        const idMarca = selMarca.value;
        const prev = selLinea.value;
        const filtradas = idMarca
          ? lineasActivas.filter((l) => Number(l.id_marca) === Number(idMarca))
          : [];
        selLinea.innerHTML = [
          { value: '', label: idMarca ? '— Selecciona línea —' : '— Primero elige una marca —' },
          ...filtradas.map((l) => ({ value: l.id_linea, label: l.nombre })),
        ].map((o) => `<option value="${esc(o.value)}">${esc(o.label)}</option>`).join('');
        if (prev && filtradas.some((l) => String(l.id_linea) === String(prev))) {
          selLinea.value = prev;
        } else if (filtradas.length === 1) {
          selLinea.value = String(filtradas[0].id_linea);
        } else {
          selLinea.value = '';
        }
        selLinea.disabled = !idMarca;
      };
      selMarca.addEventListener('change', actualizarLineas);
      actualizarLineas();
    },
    onAceptar: async (v) => {
      const mayorista = Number(v.precio_mayorista);
      const unitario = Number(v.precio_unitario);
      const dto = Math.min(100, Math.max(0, Number(v.descuento_pct || 0)));
      const aplica = v.descuento_aplica_a || 'mayorista';
      const body = {
        nombre_producto: v.nombre_producto?.trim(),
        sku: prod ? (v.sku?.trim() || null) : null,
        id_item_type: Number(v.id_item_type),
        id_marca: v.id_marca ? Number(v.id_marca) : null,
        id_linea: v.id_linea ? Number(v.id_linea) : null,
        precio_unitario: unitario,
        precio_mayorista: mayorista,
        descuento_pct: dto,
        descuento_aplica_a: aplica,
        fecha_rebaja_hasta: v.descuento_hasta || null,
        descuento_motivo: (v.descuento_motivo || '').trim() || null,
        avisar_clientes: !!v.avisar_clientes && dto > 0,
        precio_rebajado: (dto > 0 && (aplica === 'mayorista' || aplica === 'ambos'))
          ? Number((mayorista * (1 - dto / 100)).toFixed(2))
          : null,
        descripcion: v.descripcion || null,
        stock_minimo: Math.max(0, Number(v.stock_minimo ?? 10)),
      };
      if (!body.nombre_producto || !body.id_item_type || !(body.precio_unitario > 0) || !(body.precio_mayorista > 0)) {
        toast('Completa nombre, categoría y precios válidos', 'error');
        return false;
      }
      if (body.id_marca && !body.id_linea) {
        const lineasMarca = lineasActivas.filter((l) => Number(l.id_marca) === Number(body.id_marca));
        if (lineasMarca.length) {
          toast('Selecciona la línea de producto para la marca indicada', 'error');
          return false;
        }
      }
      if (v.imagen) body.imagen_url = await subirImagen(v.imagen);
      if (prod) {
        body.activo = !!v.activo;
        await api(`/catalogo/productos/${prod.id_producto}`, { method: 'PUT', body });
        toast('Producto actualizado');
      } else {
        body.stock_inicial = 0;
        await api('/catalogo/productos', { method: 'POST', body });
        toast('Producto creado (stock 0 — genera una OC para venderlo)');
      }
      await recargarCatalogo();
    },
  });
}

// ---------------------------------------------------------------------------
// Inventario
// ---------------------------------------------------------------------------

let vistaInventario = null;

async function loadInventario() {
  if (!vistaInventario) vistaInventario = crearVistaInventario();
  if (!window.__invKardexBound) {
    window.__invKardexBound = true;
    document.getElementById('inv-kardex-filtro')?.addEventListener('change', () => void renderMovimientos());
  }
  await Promise.all([vistaInventario.recargar(), renderMovimientos()]);
}

let __bodegasCache = null;

async function cargarBodegas({ refrescar = false } = {}) {
  if (!__bodegasCache || refrescar) {
    try { __bodegasCache = await api('/logistica/almacenes'); }
    catch (e) {
      __bodegasCache = [];
      toast(e.message || 'No se pudieron cargar las bodegas (¿permiso de logística?)', 'error');
    }
  }
  return __bodegasCache;
}

const ZONA_CORTA = { americas: 'Américas', emea: 'EMEA', apac: 'APAC' };
const MACRO_BY_REGION = {
  1: 'apac', 2: 'apac', 3: 'americas', 4: 'emea', 5: 'emea', 6: 'americas', 7: 'emea', 8: 'americas',
};

function macroDeRegion(idRegion) {
  if (idRegion == null || idRegion === '') return null;
  return MACRO_BY_REGION[Number(idRegion)] || null;
}

/** Macro-zona del proveedor: API o país en maestras (dim_country → región). */
function macroZonaProveedor(p) {
  if (!p) return null;
  if (p.macro_zona) return p.macro_zona;
  let idRegion = p.id_region;
  if (idRegion == null && p.id_country != null && filterCache?.paises) {
    idRegion = filterCache.paises.find((x) => Number(x.id_country) === Number(p.id_country))?.id_region;
  }
  return macroDeRegion(idRegion);
}

function zonaProveedor(p) {
  if (!p) return null;
  if (p.macro_label) return p.macro_label;
  const macro = macroZonaProveedor(p);
  return macro ? (ZONA_CORTA[macro] || macro) : null;
}

function textoZonaProveedor(idCountry) {
  if (!idCountry) {
    return 'La macro-zona se asigna sola al elegir el país (Américas, EMEA o APAC). No hace falta un campo aparte.';
  }
  const pais = filterCache?.paises?.find((x) => String(x.id_country) === String(idCountry));
  if (!pais) return 'País no encontrado en el catálogo maestro.';
  const macro = macroDeRegion(pais.id_region);
  const zona = macro ? ZONA_CORTA[macro] : null;
  const region = filterCache?.regiones?.find((r) => r.id_region === pais.id_region)?.region;
  if (!zona) {
    return `${pais.country}: sin macro-zona (revise la región en Maestras → Países).`;
  }
  return `${pais.country} → ${zona}${region ? ` · ${region}` : ''}. Las recepciones sugerirán el hub de esta zona.`;
}

function opcionesPaisesProveedor() {
  const paises = (filterCache?.paises || []).slice().sort((a, b) => {
    const za = macroDeRegion(a.id_region) || 'zzz';
    const zb = macroDeRegion(b.id_region) || 'zzz';
    return za.localeCompare(zb) || String(a.country).localeCompare(String(b.country));
  });
  return paises.map((p) => {
    const z = macroDeRegion(p.id_region);
    const suf = z ? ` — ${ZONA_CORTA[z]}` : '';
    return { value: p.id_country, label: `${p.country}${suf}` };
  });
}

function opcionesBodegas(bodegas, { etiquetaStock = null } = {}) {
  return bodegas.map((b) => {
    const zona = ZONA_CORTA[b.macro_zona] || 'sin zona';
    const rol = b.es_hub ? 'hub' : 'satélite';
    const extra = etiquetaStock ? ` · ${etiquetaStock(b)}` : '';
    return { value: b.id_almacen, label: `${b.nombre} — ${zona}, ${rol}${extra}` };
  });
}

function crearVistaInventario() {
  const st = { page: 1, page_size: 20, total_pages: 1 };
  return createDataView('vista-inventario', {
    state: st,
    autoLoad: false,
    buscar: { id: 'inv-q', placeholder: 'Producto...' },
    filtrosHtml: `
      <label class="gen-goto-ventas-wrap"><input type="checkbox" id="inv-solo-bajo" data-dv-auto> Solo stock bajo o zona agotada</label>
      <div class="field inv-zona-field"><label>Macro-zona</label>
      <select id="inv-zona" class="inv-zona-select" data-dv-auto title="Ver disponibilidad de una macro-zona">
        <option value="">Toda la red</option>
        <option value="americas">Américas</option>
        <option value="emea">EMEA</option>
        <option value="apac">APAC</option>
      </select></div>`,
    botones: [
      {
        id: 'inv-red', label: 'Red de bodegas', clase: 'btn-secondary',
        fn: () => void verPanoramaRed(),
      },
      {
        id: 'inv-reabastecer', label: 'Reabastecer red', clase: 'btn-secondary',
        fn: () => void reabastecerRed(),
      },
    ],
    columnas: [
      { key: 'nombre_producto', label: 'Producto' },
      { key: 'categoria', label: 'Categoría' },
      { key: 'disponible', label: 'Total red', align: 'num', render: (s) => fmtQty(s.disponible) },
      { key: 'stock_americas', label: 'Américas', align: 'num', render: (s) => celdaZona(s.stock_americas) },
      { key: 'stock_emea', label: 'EMEA', align: 'num', render: (s) => celdaZona(s.stock_emea) },
      { key: 'stock_apac', label: 'APAC', align: 'num', render: (s) => celdaZona(s.stock_apac) },
      { key: 'umbral_minimo', label: 'Umbral', align: 'num', render: (s) => fmtQty(s.umbral_minimo) },
      { key: 'estado', label: 'Estado', render: (s) => {
        if (s.bajo_stock) return '<span class="badge badge-cancelado">Stock bajo</span>';
        if ((s.zonas_agotadas || []).length) return '<span class="badge badge-warning">Zona agotada</span>';
        return '<span class="badge badge-entregado">OK</span>';
      } },
    ],
    cargar: async (s) => {
      const params = new URLSearchParams();
      const q = document.getElementById('inv-q')?.value?.trim();
      const soloBajo = document.getElementById('inv-solo-bajo')?.checked;
      const zona = document.getElementById('inv-zona')?.value;
      if (q) params.set('q', q);
      if (soloBajo) params.set('solo_bajo', 'true');
      if (zona) params.set('macro_zona', zona);
      const stock = await api(`/inventario/stock?${params}`);
      const alertas = await api('/inventario/alertas');
      const chip = document.getElementById('inv-alertas-chip');
      if (chip) chip.textContent = `${alertas.length} alertas`;
      return { items: stock, total: stock.length };
    },
    filaClase: (s) => s.bajo_stock ? 'row-alert' : '',
    resumen: (s) => `<div class="detail-grid">
      <div><strong>Categoría:</strong> ${esc(s.categoria || '—')}</div>
      <div><strong>Total en la red:</strong> ${fmtQty(s.disponible)}</div>
      <div><strong>Américas:</strong> ${fmtQty(s.stock_americas || 0)}</div>
      <div><strong>EMEA:</strong> ${fmtQty(s.stock_emea || 0)}</div>
      <div><strong>APAC:</strong> ${fmtQty(s.stock_apac || 0)}</div>
      <div><strong>Reservada:</strong> ${fmtQty(s.reservada)}</div>
      <div><strong>Umbral mínimo:</strong> ${fmtQty(s.umbral_minimo)}</div>
      <div><strong>Zonas sin stock:</strong> ${(s.zonas_agotadas || []).length ? esc((s.zonas_agotadas || []).join(', ')) : 'ninguna'}</div>
    </div>`,
    titulo: (s) => s.nombre_producto,
    key: (s) => s.id_producto,
    acciones: { agregar: null, modificar: null, eliminar: null },
    bloqueadas: {
      agregar: 'El stock se crea automáticamente con el producto en Catálogo.',
      modificar: 'Usa «Ajustar stock» o «Fijar umbral» del panel.',
      eliminar: 'El stock no se elimina; el historial queda registrado.',
    },
    extras: (s) => [
      { label: 'Ajustar stock', clase: 'btn-primary', opensModal: true, fn: () => abrirAjusteStock(s) },
      { label: 'Por bodega', clase: 'btn-secondary', opensModal: true, fn: () => void verStockPorBodega(s) },
      { label: 'Transferir', clase: 'btn-secondary', opensModal: true, fn: () => void abrirTransferencia(s) },
      { label: 'Fijar umbral', clase: 'btn-secondary', opensModal: true, fn: () => abrirUmbralStock(s) },
      {
        label: 'Ver kardex', clase: 'btn-secondary', opensModal: true,
        fn: () => {
          const sel = document.getElementById('inv-kardex-filtro');
          if (sel) {
            if (![...sel.options].some((o) => String(o.value) === String(s.id_producto))) {
              sel.add(new Option(s.nombre_producto, s.id_producto));
            }
            sel.value = String(s.id_producto);
            document.getElementById('inv-mov-body')?.scrollIntoView({ behavior: 'smooth', block: 'center' });
            void renderMovimientos();
          }
        },
      },
    ],
    vacio: 'Sin productos',
  });
}

function celdaZona(valor) {
  const n = Number(valor || 0);
  if (n <= 0) return '<span class="badge badge-cancelado">Agotado</span>';
  return fmtQty(n);
}

async function verPanoramaRed() {
  let data;
  try { data = await api('/inventario/red'); }
  catch (e) { toast(e.message || 'No se pudo cargar la red', 'error'); return; }

  const zonas = (data.zonas || []).map((z) => `
    <tr>
      <td>${esc(z.macro_label)}</td>
      <td class="num">${z.n_bodegas}</td>
      <td class="num">${fmtQty(z.unidades)}</td>
      <td class="num">${z.productos_agotados}</td>
      <td class="num">${z.cobertura_pct}%</td>
    </tr>`).join('');

  const bodegas = (data.bodegas || []).map((b) => `
    <tr class="${b.activo ? '' : 'row-inactive'}">
      <td>${esc(b.codigo || '—')}</td>
      <td>${esc(b.nombre)}</td>
      <td>${esc(b.macro_label || '—')}</td>
      <td>${b.es_hub ? '<span class="badge badge-success">Hub</span>' : '<span class="meta">Satélite</span>'}</td>
      <td class="num">${fmtQty(b.unidades)}</td>
      <td class="num">${b.cobertura_pct}%</td>
      <td>${b.vacia ? '<span class="badge badge-cancelado">Vacía</span>' : '<span class="badge badge-entregado">Operativa</span>'}</td>
    </tr>`).join('');

  const politica = data.cross_zona
    ? 'Se permite servir un pedido desde otra macro-zona si la del cliente no tiene stock.'
    : 'Cada cliente se atiende solo con las bodegas de su macro-zona: sin stock local, el producto aparece agotado.';

  uiModal({
    modo: 'Red', tituloExtra: 'Red de distribución', ancho: 'xl', textoAceptar: 'Cerrar',
    campos: [{
      key: 'red', type: 'html',
      value: `
        <p class="meta">${esc(politica)}</p>
        <h4>Cobertura por macro-zona</h4>
        <div class="table-wrap"><table><thead><tr>
          <th>Zona</th><th class="num">Bodegas</th><th class="num">Unidades</th>
          <th class="num">Productos agotados</th><th class="num">Cobertura</th>
        </tr></thead><tbody>${zonas}</tbody></table></div>
        <h4>Bodegas</h4>
        <div class="table-wrap inv-red-tabla"><table><thead><tr>
          <th>Código</th><th>Bodega</th><th>Zona</th><th>Rol</th>
          <th class="num">Unidades</th><th class="num">Cobertura</th><th>Estado</th>
        </tr></thead><tbody>${bodegas}</tbody></table></div>`,
    }],
  });
}

async function reabastecerRed() {
  uiModal({
    modo: 'Reabastecer', tituloExtra: 'Surtir bodegas de la red', ancho: 'md',
    campos: [
      {
        key: 'info', type: 'html',
        value: '<p class="meta">Carga inventario en las bodegas que no alcanzan su objetivo (hub y satélite se configuran en Ajustes). Evita que los clientes de una zona vean productos agotados por bodegas vacías.</p>',
      },
      {
        key: 'alcance', label: 'Alcance', type: 'select',
        options: [
          { value: 'vacias', label: 'Solo productos sin stock en la bodega (recomendado)' },
          { value: 'todas', label: 'Completar todas las líneas hasta el objetivo' },
        ],
        value: 'vacias',
      },
    ],
    textoAceptar: 'Reabastecer',
    onAceptar: async (v) => {
      const soloVacias = v.alcance !== 'todas';
      const r = await api(`/inventario/red/reabastecer?solo_vacias=${soloVacias}`, { method: 'POST' });
      toast(r.lineas
        ? `Reabastecidas ${r.bodegas} bodegas: ${fmtQty(r.unidades)} unidades en ${r.lineas} líneas`
        : 'Todas las bodegas ya cubrían su objetivo');
      __bodegasCache = null;
      await vistaInventario?.recargar();
    },
  });
}

async function verStockPorBodega(producto) {
  let data;
  try { data = await api(`/inventario/stock/${producto.id_producto}/bodegas`); }
  catch (e) { toast(e.message || 'No se pudo cargar el desglose', 'error'); return; }

  const filas = (data.bodegas || []).length
    ? data.bodegas.map((b) => `
        <tr>
          <td>${esc(b.almacen)}</td>
          <td>${esc(b.macro_label || '—')}</td>
          <td>${b.es_hub ? '<span class="badge badge-success">Hub</span>' : '<span class="meta">Satélite</span>'}</td>
          <td class="num">${fmtQty(b.disponible)}</td>
          <td class="num">${fmtQty(b.reservado)}</td>
          <td class="num">${celdaZona(b.neto)}</td>
        </tr>`).join('')
    : '<tr><td colspan="6" class="meta">Este producto no tiene inventario asignado en ninguna bodega.</td></tr>';

  const zona = data.por_zona || {};
  uiModal({
    modo: 'Inventario', tituloExtra: producto.nombre_producto, ancho: 'lg', textoAceptar: 'Cerrar',
    campos: [{
      key: 'tabla', type: 'html',
      value: `
        <div class="detail-grid">
          <div><strong>Américas:</strong> ${fmtQty(zona.americas || 0)}</div>
          <div><strong>EMEA:</strong> ${fmtQty(zona.emea || 0)}</div>
          <div><strong>APAC:</strong> ${fmtQty(zona.apac || 0)}</div>
        </div>
        <div class="table-wrap" style="max-height:320px;overflow:auto"><table><thead><tr>
          <th>Bodega</th><th>Zona</th><th>Rol</th>
          <th class="num">Disponible</th><th class="num">Reservado</th><th class="num">Neto</th>
        </tr></thead><tbody>${filas}</tbody></table></div>`,
    }],
  });
}

async function abrirTransferencia(producto) {
  const bodegas = await cargarBodegas({ refrescar: true });
  if (bodegas.length < 2) { toast('Necesitas al menos dos bodegas activas', 'error'); return; }

  let desglose = [];
  try {
    const data = await api(`/inventario/stock/${producto.id_producto}/bodegas`);
    desglose = data.bodegas || [];
  } catch { /* el detalle es informativo */ }
  const disponiblePor = new Map(desglose.map((d) => [d.id_almacen, d.neto]));
  const conStock = opcionesBodegas(bodegas, {
    etiquetaStock: (b) => `${fmtQty(disponiblePor.get(b.id_almacen) || 0)} u.`,
  });
  const origenPorDefecto = bodegas
    .slice()
    .sort((a, b) => (disponiblePor.get(b.id_almacen) || 0) - (disponiblePor.get(a.id_almacen) || 0))[0];
  const destinoPorDefecto = bodegas.find((b) => (disponiblePor.get(b.id_almacen) || 0) <= 0)
    || bodegas.find((b) => b.id_almacen !== origenPorDefecto?.id_almacen);

  uiModal({
    modo: 'Transferir', tituloExtra: producto.nombre_producto, ancho: 'md',
    campos: [
      {
        key: 'origen', label: 'Bodega de origen', type: 'select',
        options: conStock, value: origenPorDefecto?.id_almacen ?? '',
      },
      {
        key: 'destino', label: 'Bodega de destino', type: 'select',
        options: conStock, value: destinoPorDefecto?.id_almacen ?? '',
      },
      { key: 'cantidad', label: 'Cantidad a transferir', type: 'number', min: 1, step: 1, value: 50 },
    ],
    textoAceptar: 'Transferir',
    onAceptar: async (v) => {
      const origen = Number(v.origen);
      const destino = Number(v.destino);
      const cantidad = Number(v.cantidad);
      if (!origen || !destino) { toast('Selecciona bodega de origen y destino', 'error'); return false; }
      if (origen === destino) { toast('El origen y el destino deben ser distintos', 'error'); return false; }
      if (!Number.isFinite(cantidad) || cantidad <= 0) { toast('Cantidad inválida', 'error'); return false; }
      await api('/inventario/transferencias', {
        method: 'POST',
        body: {
          id_producto: producto.id_producto,
          id_almacen_origen: origen,
          id_almacen_destino: destino,
          cantidad,
        },
      });
      toast(`Transferidas ${fmtQty(cantidad)} unidades`);
      __bodegasCache = null;
      await vistaInventario?.recargar();
    },
  });
}

async function renderMovimientos() {
  const sel = document.getElementById('inv-kardex-filtro');
  if (sel && sel.options.length <= 1) {
    try {
      const stock = await api('/inventario/stock?page_size=500');
      (stock || []).forEach((s) => sel.add(new Option(s.nombre_producto, s.id_producto)));
    } catch (e) { /* el filtro queda vacío */ }
  }
  const param = sel && sel.value ? `?limit=120&id_producto=${encodeURIComponent(sel.value)}` : '?limit=120';
  const movimientos = await api(`/inventario/movimientos${param}`);
  const tbody = document.getElementById('inv-mov-body');
  if (!tbody) return;
  tbody.innerHTML = movimientos.map((m) => `
    <tr>
      <td class="num">${m.id_movimiento}</td><td>${esc(m.tipo)}</td><td>${esc(m.producto || '—')}</td>
      <td class="num">${m.cantidad != null ? fmtQty(m.cantidad) : '—'}</td>
      <td>${esc(m.referencia || '')}</td><td>${esc((m.fecha || '').slice(0, 19))}</td>
    </tr>`).join('') || '<tr><td colspan="6">Sin movimientos</td></tr>';
}

function abrirAjusteStock(s) {
  uiModal({
    modo: 'Ajustar stock', tituloExtra: s.nombre_producto,
    campos: [
      { key: 'cantidad', label: 'Cantidad (+ entrada / - salida)', type: 'number', step: '1', value: 0,
        hint: 'Usa un solo signo: por ejemplo 50 para entrada o -50 para salida.' },
      { key: 'motivo', label: 'Motivo', value: '' },
    ],
    onAceptar: async (v) => {
      const cantidad = Number(v.cantidad);
      if (!Number.isFinite(cantidad) || cantidad === 0) {
        toast('Cantidad inválida: debe ser un número distinto de 0', 'error');
        return false;
      }
      if (!v.motivo || v.motivo.trim().length < 3) {
        toast('Indica un motivo de al menos 3 caracteres', 'error');
        return false;
      }
      await api('/inventario/ajustes', {
        method: 'POST', body: { id_producto: s.id_producto, cantidad, motivo: v.motivo.trim() },
      });
      toast('Stock ajustado');
      await vistaInventario.recargar();
    },
  });
}

function abrirUmbralStock(s) {
  uiModal({
    modo: 'Fijar umbral', tituloExtra: s.nombre_producto,
    campos: [{ key: 'umbral', label: 'Umbral mínimo', type: 'number', min: 0, value: s.umbral_minimo ?? 10 }],
    onAceptar: async (v) => {
      await api('/inventario/alertas', {
        method: 'POST', body: { id_producto: s.id_producto, umbral_minimo: Number(v.umbral) },
      });
      toast('Alerta configurada');
      await vistaInventario.recargar();
    },
  });
}

// ---------------------------------------------------------------------------
// Compras (pestañas: Proveedores | Órdenes de compra)
// ---------------------------------------------------------------------------

let cmpProveedores = [];
let vistasCompras = {};

async function loadCompras() {
  if (!vistasCompras.proveedores) {
    const tabs = [
      { id: 'proveedores', label: 'Proveedores' },
      { id: 'ordenes', label: 'Órdenes de compra' },
      { id: 'recepciones', label: 'Recepciones' },
      { id: 'cuentas', label: 'Cuentas por pagar' },
    ];
    const paneles = createTabsView('vista-compras', tabs);
    cmpTabsEl = document.getElementById('vista-compras');
    vistasCompras.proveedores = crearVistaProveedores(paneles.proveedores);
    vistasCompras.ordenes = crearVistaOC(paneles.ordenes);
    vistasCompras.recepciones = crearVistaRecepciones(paneles.recepciones);
    vistasCompras.cuentas = crearVistaCuentasXPagar(paneles.cuentas);
    const tabLoad = {
      proveedores: () => vistasCompras.proveedores.recargar(),
      ordenes: () => vistasCompras.ordenes.recargar(),
      recepciones: () => vistasCompras.recepciones.recargar(),
      cuentas: () => vistasCompras.cuentas.recargar(),
    };
    tabs.forEach((t) => { t.onActivo = () => { void tabLoad[t.id](); }; });
  }
  await vistasCompras.proveedores.recargar();
  await vistasCompras.ordenes.recargar();
}

function etiquetaProveedor(p) {
  const z = zonaProveedor(p);
  return z ? `${p.razon_social} (${z})` : p.razon_social;
}

function opcionesProveedores(lista) {
  return lista.slice().sort((a, b) => {
    const za = macroZonaProveedor(a) || 'zzz';
    const zb = macroZonaProveedor(b) || 'zzz';
    return za.localeCompare(zb) || String(a.razon_social).localeCompare(String(b.razon_social));
  }).map((p) => ({ value: p.id_proveedor, label: etiquetaProveedor(p) }));
}

let cmpTabsEl = null;
function activarTabCompras(id) {
  const tab = (cmpTabsEl || document.getElementById('vista-compras'))?.querySelector(`[data-tab="${id}"]`);
  if (tab && !tab.classList.contains('active')) tab.click();
  else if (vistasCompras[id]?.recargar) void vistasCompras[id].recargar();
}

function crearVistaProveedores(cont) {
  const st = { page: 1, page_size: 20, total_pages: 1 };
  return createDataView(cont, {
    state: st,
    autoLoad: false,
    buscar: { id: 'cmp-prov-q', placeholder: 'Razón social o RUC...' },
    filtrosHtml: `
      <div class="field"><label>Zona</label>
        <select id="cmp-prov-zona" data-dv-auto title="Filtrar por macro-zona de abastecimiento">
          <option value="">Todas</option>
          <option value="americas">Américas</option>
          <option value="emea">EMEA</option>
          <option value="apac">APAC</option>
        </select>
      </div>`,
    columnas: [
      { key: 'razon_social', label: 'Razón social' },
      { key: 'ruc', label: 'RUC', render: (p) => esc(p.ruc || '—') },
      { key: 'pais', label: 'País', render: (p) => esc(p.pais || '—') },
      { key: 'macro_zona', label: 'Zona', render: (p) => {
        const z = zonaProveedor(p);
        return z ? esc(z) : '<span class="meta">—</span>';
      } },
      { key: 'n_ordenes', label: 'Órdenes', align: 'num' },
      { key: 'activo', label: 'Activo', align: 'center', render: (p) => p.activo ? 'Sí' : 'No' },
    ],
    cargar: async (s) => {
      await ensureFilters();
      const params = new URLSearchParams({ incluir_inactivos: 'true' });
      const q = document.getElementById('cmp-prov-q')?.value?.trim();
      const zona = document.getElementById('cmp-prov-zona')?.value;
      if (q) params.set('q', q);
      cmpProveedores = await api(`/compras/proveedores?${params}`);
      let items = cmpProveedores;
      if (zona) items = items.filter((p) => macroZonaProveedor(p) === zona);
      return { items, total: items.length };
    },
    filaClase: (p) => p.activo ? '' : 'row-inactive',
    resumen: (p) => `<div class="detail-grid">
      <div><strong>RUC:</strong> ${esc(p.ruc || '—')}</div>
      <div><strong>País:</strong> ${esc(p.pais || '—')}</div>
      <div><strong>Zona de abastecimiento:</strong> ${esc(zonaProveedor(p) || '—')}</div>
      <div><strong>Órdenes de compra:</strong> ${p.n_ordenes}</div>
      <div><strong>Estado:</strong> ${p.activo ? 'Activo' : 'Inactivo'}</div>
    </div>`,
    titulo: (p) => p.razon_social,
    key: (p) => p.id_proveedor,
    acciones: {
      agregar: () => void openProveedorModal(),
      modificar: (row) => void openProveedorModal(row),
      eliminar: async (row) => {
        await api(`/compras/proveedores/${row.id_proveedor}`, { method: 'DELETE' });
        toast('Proveedor eliminado');
      },
    },
    bloqueadas: { eliminar: 'Solo se eliminan proveedores sin órdenes de compra; si está en uso, desactívelo.' },
    vacio: 'Sin proveedores',
  });
}

async function openProveedorModal(prov = null) {
  await ensureFilters();
  const idActual = prov?.id_proveedor != null ? Number(prov.id_proveedor) : null;

  function conflictoProveedor({ razon_social, ruc }) {
    const razon = (razon_social || '').trim().replace(/\s+/g, ' ').toLowerCase();
    const rucNorm = (ruc || '').trim().replace(/[\s-]/g, '');
    for (const p of cmpProveedores) {
      if (idActual != null && Number(p.id_proveedor) === idActual) continue;
      if (razon && String(p.razon_social || '').trim().toLowerCase() === razon) {
        return `La razón social «${p.razon_social}» ya está registrada (proveedor #${p.id_proveedor}).`;
      }
      if (rucNorm && String(p.ruc || '').replace(/[\s-]/g, '') === rucNorm) {
        return `El RUC ${rucNorm} ya lo usa «${p.razon_social}». Debe ser único por proveedor.`;
      }
    }
    return null;
  }

  uiModal({
    modo: prov ? 'Actualizar' : 'Agregar',
    tituloExtra: prov ? prov.razon_social : 'Nuevo proveedor',
    campos: [
      { key: 'razon_social', label: 'Razón social', value: prov?.razon_social || '', maxlength: 160, required: true, placeholder: '2–160 caracteres' },
      { key: 'ruc', label: 'RUC / NIT', value: prov?.ruc || '', maxlength: 13, pattern: '\\d{8,13}', inputmode: 'numeric', placeholder: 'Solo dígitos, 8–13', title: 'Solo dígitos (8 a 13). Sin guiones ni asteriscos.', hint: 'Opcional. Debe ser único: no puede repetirse en otro proveedor.' },
      {
        key: 'id_country', label: 'País', type: 'select', value: prov?.id_country ?? '',
        options: [{ value: '', label: '— Selecciona —' }, ...opcionesPaisesProveedor()],
      },
      {
        key: 'zona_preview', type: 'html',
        value: `<p class="meta"><strong>Zona de abastecimiento:</strong> <span id="prov-zona-preview">${esc(textoZonaProveedor(prov?.id_country))}</span></p>`,
      },
    ],
    onReady: () => {
      document.getElementById('uf-id_country')?.addEventListener('change', (e) => {
        const el = document.getElementById('prov-zona-preview');
        if (el) el.textContent = textoZonaProveedor(e.target.value);
      });
    },
    onAceptar: async (v) => {
      const razon_social = (v.razon_social || '').trim().replace(/\s+/g, ' ');
      if (razon_social.length < 2 || razon_social.length > 160) {
        toast('Razón social: entre 2 y 160 caracteres', 'error');
        return false;
      }
      let ruc = (v.ruc || '').trim().replace(/[\s-]/g, '');
      if (ruc) {
        if (!/^\d{8,13}$/.test(ruc)) {
          toast('RUC inválido: solo dígitos (8 a 13 caracteres)', 'error');
          return false;
        }
      } else {
        ruc = null;
      }
      const body = { razon_social, ruc, id_country: v.id_country ? Number(v.id_country) : null };
      const conflicto = conflictoProveedor(body);
      if (conflicto) { toast(conflicto, 'error'); return false; }
      try {
      if (prov) {
          await api(`/compras/proveedores/${idActual}`, {
            method: 'PUT',
            body,
          });
        toast('Proveedor actualizado');
      } else {
          await api('/compras/proveedores', { method: 'POST', body });
        toast('Proveedor creado');
      }
      await vistasCompras.proveedores.recargar();
      } catch (e) {
        toast(e.message || 'No se pudo guardar el proveedor', 'error');
        return false;
      }
    },
  });
}

function crearVistaOC(cont) {
  const st = { page: 1, page_size: 20, total_pages: 1 };
  return createDataView(cont, {
    state: st,
    autoLoad: false,
    buscar: { id: 'cmp-oc-q', placeholder: 'Número o proveedor...' },
    filtrosHtml: `
      <div class="field"><label>Desde</label><input type="date" id="cmp-oc-desde" data-dv-auto></div>
      <div class="field"><label>Hasta</label><input type="date" id="cmp-oc-hasta" data-dv-auto></div>
      <div class="field"><label>Estado</label><select id="cmp-oc-estado" data-dv-auto>
      <option value="">Todos</option>
      <option value="borrador">Borrador</option>
      <option value="aprobada">Aprobada</option>
      <option value="parcialmente_recibida">Recibida parcial</option>
      <option value="recibida">Recibida</option>
      <option value="cancelada">Cancelada</option>
    </select></div>`,
    columnas: [
      { key: 'numero', label: 'Número' },
      { key: 'proveedor', label: 'Proveedor' },
      { key: 'fecha', label: 'Fecha', render: (o) => esc((o.fecha || '').slice(0, 19)) },
      { key: 'estado', label: 'Estado', render: (o) => badge(o.estado) },
      { key: 'metodo', label: 'Método', render: (o) => esc(METODO_PAGO_LABEL[o.metodo_pago] || o.metodo_pago || 'Caja') },
      { key: 'total', label: 'Total', align: 'num', render: (o) => erpMoney(o.total) },
    ],
    cargar: async (s) => {
      const params = new URLSearchParams();
      const estado = document.getElementById('cmp-oc-estado')?.value;
      if (estado) params.set('estado', estado);
      let ordenes = await api(`/compras/ordenes?${params}`);
      const desde = document.getElementById('cmp-oc-desde')?.value;
      const hasta = document.getElementById('cmp-oc-hasta')?.value;
      const q = document.getElementById('cmp-oc-q')?.value?.trim().toLowerCase();
      if (desde) ordenes = ordenes.filter((o) => (o.fecha || '').slice(0, 10) >= desde);
      if (hasta) ordenes = ordenes.filter((o) => (o.fecha || '').slice(0, 10) <= hasta);
      if (q) {
        ordenes = ordenes.filter((o) =>
          String(o.numero || '').toLowerCase().includes(q)
          || String(o.proveedor || '').toLowerCase().includes(q));
      }
      return { items: ordenes, total: ordenes.length };
    },
    resumen: (o) => `<div class="detail-grid">
      <div><strong>Proveedor:</strong> ${esc(o.proveedor)}</div>
      <div><strong>Fecha:</strong> ${esc((o.fecha || '').slice(0, 19))}</div>
      <div><strong>Estado:</strong> ${badge(o.estado)}</div>
      <div><strong>Método de pago:</strong> ${esc(METODO_PAGO_LABEL[o.metodo_pago] || o.metodo_pago || 'Caja')}</div>
      <div><strong>Total:</strong> ${erpMoney(o.total)}</div>
    </div>`,
    titulo: (o) => o.numero,
    key: (o) => o.id_oc,
    acciones: {
      agregar: () => void openOCModal(),
      modificar: null,
      eliminar: null,
    },
    bloqueadas: {
      modificar: 'Las órdenes de compra no se modifican; se cancelan o se reciben.',
      eliminar: 'Las órdenes de compra no se eliminan.',
    },
    extras: (o) => {
      const x = [];
      if (o.estado === 'borrador') {
        x.push({
          label: 'Aprobar orden', clase: 'btn-primary',
          fn: async () => {
            await api(`/compras/ordenes/${o.id_oc}/estado?estado=aprobada`, { method: 'POST' });
            toast('Orden aprobada');
          },
        });
      }
      if (['aprobada', 'parcialmente_recibida'].includes(o.estado)) {
        x.push({
          label: 'Recibir (total o parcial)', labelCorto: 'Recibir', clase: 'btn-success', enFila: true, opensModal: true,
          fn: () => openRecibirOCModal(o),
        });
      }
      if (['aprobada', 'parcialmente_recibida', 'recibida'].includes(o.estado)) {
        x.push({
          label: 'Ver recepciones', clase: 'btn-secondary', opensModal: true,
          fn: () => { activarTabCompras('recepciones'); },
        });
      }
      if (['borrador', 'aprobada'].includes(o.estado)) {
        x.push({
          label: 'Cancelar orden', clase: 'btn-danger',
          fn: () => uiConfirm({
            titulo: '¿Cancelar la orden?',
            mensaje: 'La orden quedará en estado cancelada.',
            textoAceptar: 'Cancelar',
            onConfirm: async () => {
              await api(`/compras/ordenes/${o.id_oc}/estado?estado=cancelada`, { method: 'POST' });
              toast('Orden cancelada');
            },
          }),
        });
      }
      x.push({
        label: 'Descargar PDF', clase: 'btn-secondary',
        fn: async () => {
          const res = await fetch(`/api/compras/ordenes/${o.id_oc}/pdf`);
          if (!res.ok) {
            const err = await res.json().catch(() => ({}));
            throw new Error(err.detail || 'No se pudo abrir el PDF');
          }
          const blob = await res.blob();
          const filename = `${o.numero || 'OC'}.pdf`;
          if (typeof openPdfBlob === 'function') openPdfBlob(blob, filename);
          else window.open(URL.createObjectURL(blob), '_blank', 'noopener');
          toast('PDF descargado');
        },
      });
      return x;
    },
    vacio: 'Sin órdenes',
    onAfterRender: (host) => {
      host.querySelector('.dv-toolbar-filters')?.classList.add('cmp-filters');
    },
  });
}

async function openOCModal() {
  const activos = cmpProveedores.filter((p) => p.activo);
  if (!activos.length) { toast('Crea un proveedor primero', 'error'); return; }

  async function aplicarCostoSugerido() {
    const idProducto = document.getElementById('uf-id_producto')?.value;
    const idProveedor = document.getElementById('uf-id_proveedor')?.value;
    const costoInput = document.getElementById('uf-costo_unitario');
    const hint = document.getElementById('uf-hint-costo_unitario');
    if (!idProducto || !costoInput) return;
    costoInput.placeholder = 'Cargando…';
    try {
      const params = new URLSearchParams({ id_producto: idProducto });
      if (idProveedor) params.set('id_proveedor', idProveedor);
      const sug = await api(`/compras/costo-sugerido?${params}`);
      costoInput.value = Number(sug.costo_unitario || 0).toFixed(2);
      costoInput.placeholder = '';
      if (hint) hint.textContent = `${sug.origen_label || 'Sugerido del catálogo'}. Puedes ajustarlo si hubo negociación.`;
    } catch (e) {
      costoInput.placeholder = '0.00';
      if (hint) hint.textContent = 'No se pudo obtener el costo sugerido.';
    }
  }

  uiModal({
    modo: 'Agregar', tituloExtra: 'Nueva orden de compra', ancho: 'lg',
    campos: [
      {
        key: 'info', type: 'html',
        value: '<p class="meta">Elige un proveedor de la misma macro-zona donde recibirás la mercancía. Al recibir, se sugerirá el hub de esa zona.</p>',
      },
      { key: 'id_proveedor', label: 'Proveedor', type: 'select', options: opcionesProveedores(activos) },
      {
        key: 'id_producto', label: 'Producto', type: 'search-select', value: '',
        searchPlaceholder: 'Buscar producto (stock bajo primero)…',
        searchFn: (q) => buscarProductosCompraOpciones(q),
      },
      { key: 'cantidad', label: 'Cantidad', type: 'number', min: 1, value: 10 },
      { key: 'costo_unitario', label: 'Costo unitario', type: 'number', step: '0.01', min: 0.01, value: '', placeholder: '…', hint: 'Se sugiere desde el precio del producto en catálogo.' },
      {
        key: 'metodo_pago', label: 'Método de pago', type: 'select',
        value: 'caja',
        options: [
          { value: 'caja', label: 'Caja — se descuenta al recibir' },
          { value: 'externo', label: 'Pago externo — sale de Pagos externos' },
          { value: 'credito', label: 'Crédito — queda como Cuenta por pagar' },
        ],
      },
    ],
    onAceptar: async (v) => {
      const costo = Number(v.costo_unitario);
      if (!v.id_producto) { toast('Selecciona un producto', 'error'); return false; }
      if (!costo || costo <= 0) { toast('Indica un costo unitario válido', 'error'); return false; }
      await api('/compras/ordenes', {
        method: 'POST', body: {
          id_proveedor: Number(v.id_proveedor),
          items: [{ id_producto: Number(v.id_producto), cantidad: Number(v.cantidad), costo_unitario: costo }],
          metodo_pago: v.metodo_pago || 'caja',
        },
      });
      toast('Orden de compra creada (borrador)');
      await vistasCompras.ordenes.recargar();
    },
    onReady: () => {
      document.getElementById('uf-id_producto')?.addEventListener('change', aplicarCostoSugerido);
      document.getElementById('uf-id_proveedor')?.addEventListener('change', aplicarCostoSugerido);
    },
  });
}

const METODO_PAGO_LABEL = { caja: 'Caja', externo: 'Pago externo', credito: 'Crédito' };

const PHONE_PREFIXES = [
  { value: '+593', label: '🇪🇨 Ecuador +593' },
  { value: '+51', label: '🇵🇪 Perú +51' },
  { value: '+57', label: '🇨🇴 Colombia +57' },
  { value: '+52', label: '🇲🇽 México +52' },
  { value: '+54', label: '🇦🇷 Argentina +54' },
  { value: '+56', label: '🇨🇱 Chile +56' },
  { value: '+1', label: '🇺🇸 USA +1' },
  { value: '+34', label: '🇪🇸 España +34' },
];

function splitTelefono(tel) {
  const t = String(tel || '').trim();
  if (!t) return { pref: '+593', num: '' };
  const pref = PHONE_PREFIXES.map((p) => p.value).sort((a, b) => b.length - a.length)
    .find((p) => t.startsWith(p)) || '+593';
  return { pref, num: t.startsWith(pref) ? t.slice(pref.length).replace(/\D/g, '') : t.replace(/\D/g, '') };
}

function joinTelefono(pref, num) {
  const n = String(num || '').replace(/\D/g, '');
  if (!n) return null;
  return `${pref || '+593'}${n}`;
}

async function openRecibirOCModal(o) {
  let det;
  try { det = await api(`/compras/ordenes/${o.id_oc}`); } catch (e) { toast('No se pudo cargar la orden', 'error'); return; }
  const items = (det.items || []).filter((it) => it.pendiente > 0);
  if (!items.length) { toast('No hay ítems pendientes por recibir', 'error'); return; }

  const bodegas = await cargarBodegas({ refrescar: true });
  if (!bodegas.length) { toast('No hay bodegas activas para recibir mercancía', 'error'); return; }
  const idSugerido = det.id_almacen_sugerido;
  const hubPorDefecto = bodegas.find((b) => b.id_almacen === idSugerido)
    || bodegas.find((b) => b.es_hub && b.macro_zona === det.proveedor_macro_zona)
    || bodegas.find((b) => b.es_hub)
    || bodegas[0];
  const zonaHint = det.proveedor_macro_label
    ? `Proveedor de ${det.proveedor_macro_label}. Se sugiere recibir en ${det.bodega_recepcion_sugerida || hubPorDefecto.nombre}.`
    : 'Selecciona la bodega donde ingresa el stock.';

  const campos = [{
    key: 'info', type: 'html', value: `<p class="meta">${esc(zonaHint)}</p>`,
  }, {
    key: 'id_almacen', label: 'Bodega de destino', type: 'select', full: true,
    options: opcionesBodegas(bodegas, { etiquetaStock: (b) => `${fmtQty(b.stock_total)} u.` }),
    value: hubPorDefecto.id_almacen,
  }];
  items.forEach((it) => {
    campos.push({
      key: `hdr_${it.id_detalle}`,
      type: 'html',
      value: `<div class="ui-oc-receive-hdr"><strong>${esc(it.producto)}</strong> <span class="meta">· pendiente ${fmtQty(it.pendiente)} u.</span></div>`,
    });
    campos.push({
      key: `cant_${it.id_detalle}`,
      label: 'Cantidad a recibir',
      type: 'number', min: 0, max: it.pendiente, step: 1, value: it.pendiente,
    });
    campos.push({
      key: `obs_${it.id_detalle}`,
      label: 'Observación (merma o diferencia)',
      placeholder: 'Opcional si recibes el total; obligatoria si es parcial',
      full: true,
    });
  });
  uiModal({
    modo: 'Recibir', tituloExtra: `${det.numero} — ${det.proveedor} · Método: ${METODO_PAGO_LABEL[det.metodo_pago] || det.metodo_pago}`,
    ancho: 'md',
    gridClass: 'form-grid-oc-receive',
    campos,
    textoAceptar: 'Registrar recepción',
    onAceptar: async (v) => {
      const recibos = [];
      for (const it of items) {
        const cantidad = Number(v[`cant_${it.id_detalle}`] ?? 0);
        if (!Number.isFinite(cantidad) || cantidad < 0 || cantidad > it.pendiente) {
          toast(`Cantidad inválida en «${it.producto}» (0 a ${fmtQty(it.pendiente)})`, 'error');
          return false;
        }
        const observacion = (v[`obs_${it.id_detalle}`] || '').trim();
        if (!observacion && cantidad > 0 && cantidad < it.pendiente) {
          toast(`Si reduces «${it.producto}» a ${fmtQty(cantidad)}, agrega la observación (motivo de la diferencia)`, 'error');
          return false;
        }
        if (cantidad > 0) recibos.push({ id_detalle: it.id_detalle, cantidad, observacion: observacion || null });
      }
      if (!recibos.length) { toast('Indica al menos una cantidad mayor a 0', 'error'); return false; }
      const idAlmacen = Number(v.id_almacen);
      if (!idAlmacen) { toast('Selecciona la bodega de destino', 'error'); return false; }
      await api(`/compras/ordenes/${o.id_oc}/recibir`, {
        method: 'POST', body: { id_almacen: idAlmacen, recibos },
      });
      const bodega = bodegas.find((b) => b.id_almacen === idAlmacen);
      toast(`Recepción registrada en ${bodega ? bodega.nombre : 'la bodega'}: stock y cuentas actualizados`);
      __bodegasCache = null;
      await vistasCompras.ordenes.recargar();
      await vistasCompras.recepciones.recargar();
      await vistasCompras.cuentas.recargar();
    },
  });
}

async function openRecibirMercanciaPicker() {
  let ordenes = await api('/compras/ordenes');
  const pendientes = (ordenes || []).filter((o) => ['aprobada', 'parcialmente_recibida'].includes(o.estado));
  if (!pendientes.length) {
    toast('No hay órdenes aprobadas pendientes de recepción. Aprueba una OC en la pestaña «Órdenes de compra».', 'error');
    return;
  }
  uiModal({
    modo: 'Recibir',
    tituloExtra: 'Seleccionar orden de compra',
    textoAceptar: 'Continuar',
    campos: [{
      key: 'id_oc',
      label: 'Orden pendiente por recibir',
      type: 'select',
      required: true,
      options: pendientes.map((o) => ({
        value: String(o.id_oc),
        label: `${o.numero} — ${o.proveedor} · ${erpMoney(o.total)}`,
      })),
    }],
    onAceptar: async (v) => {
      const oc = pendientes.find((o) => String(o.id_oc) === String(v.id_oc));
      if (!oc) {
        toast('Selecciona una orden válida', 'error');
        return false;
      }
      await openRecibirOCModal(oc);
    },
  });
}

function crearVistaRecepciones(cont) {
  const st = { page: 1, page_size: 20, total_pages: 1 };
  return createDataView(cont, {
    state: st,
    autoLoad: false,
    botones: [
      { id: 'rec-recibir', label: 'Recibir mercancía', clase: 'btn-success', fn: () => void openRecibirMercanciaPicker() },
    ],
    columnas: [
      { key: 'id_recepcion', label: 'Recepc. Nº', align: 'center' },
      { key: 'numero_oc', label: 'Orden' },
      { key: 'proveedor', label: 'Proveedor' },
      { key: 'bodega', label: 'Bodega destino' },
      { key: 'fecha', label: 'Fecha', render: (r) => esc((r.fecha || '').slice(0, 19)) },
      { key: 'tipo', label: 'Tipo', render: (r) => r.estado === 'parcial' ? '<span class="badge badge-parcialmente_recibida">Parcial</span>' : '<span class="badge badge-recibida">Completa</span>' },
      { key: 'n_items', label: 'Ítems', align: 'num' },
      { key: 'total', label: 'Total', align: 'num', render: (r) => erpMoney(r.total) },
    ],
    cargar: async () => {
      const rec = await api('/compras/recepciones?limit=200');
      return { items: rec, total: rec.length };
    },
    resumen: (r) => `<div class="detail-grid">
      <div><strong>Orden:</strong> ${esc(r.numero_oc || '—')}</div>
      <div><strong>Proveedor:</strong> ${esc(r.proveedor || '—')}</div>
      <div><strong>Bodega destino:</strong> ${esc(r.bodega || '—')}</div>
      <div><strong>Fecha:</strong> ${esc((r.fecha || '').slice(0, 19))}</div>
      <div><strong>Tipo:</strong> ${r.estado === 'parcial' ? 'Parcial' : 'Completa'}</div>
      <div><strong>Ítems:</strong> ${r.n_items || 0}</div>
      <div><strong>Total:</strong> ${erpMoney(r.total)}</div>
    </div>`,
    titulo: (r) => `Recepción #${r.id_recepcion}`,
    key: (r) => r.id_recepcion,
    acciones: { agregar: null, modificar: null, eliminar: null },
    bloqueadas: {
      agregar: 'Use «Recibir mercancía» para registrar una recepción desde una orden aprobada.',
      modificar: 'Las recepciones no se modifican.',
      eliminar: 'Las recepciones no se eliminan.',
    },
    vacio: 'Sin recepciones registradas',
  });
}

function crearVistaCuentasXPagar(cont) {
  const st = { page: 1, page_size: 20, total_pages: 1 };
  return createDataView(cont, {
    state: st,
    autoLoad: false,
    filtrosHtml: `
      <label class="gen-goto-ventas-wrap"><input type="checkbox" id="cmp-cxp-solo" data-dv-auto> Solo con saldo pendiente</label>
      <p class="meta" id="cmp-cxp-resumen" style="flex:1 1 100%;margin:0"></p>`,
    columnas: [
      { key: 'razon_social', label: 'Proveedor' },
      { key: 'comprado', label: 'Comprado', align: 'num', render: (c) => erpMoney(c.comprado) },
      { key: 'recibido', label: 'Recibido', align: 'num', render: (c) => erpMoney(c.recibido) },
      { key: 'pagado', label: 'Pagado', align: 'num', render: (c) => erpMoney(c.pagado) },
      { key: 'pendiente', label: 'Pendiente', align: 'num', render: (c) => erpMoney(c.pendiente) },
    ],
    cargar: async () => {
      const res = await api('/compras/cuentas-por-pagar');
      let items = res.proveedores || [];
      if (document.getElementById('cmp-cxp-solo')?.checked) {
        items = items.filter((c) => Number(c.pendiente) > 0);
      }
      const chip = document.getElementById('cmp-cxp-resumen');
      if (chip) {
        chip.textContent = items.length
          ? `Total pendiente: ${erpMoney(res.total_pendiente)} · ${items.length} proveedor(es)`
          : 'Sin deuda pendiente a proveedores (las compras al contado se liquidan al recibir).';
      }
      return { items, total: items.length };
    },
    resumen: (r) => `<div class="detail-grid">
      <div><strong>Comprado:</strong> ${erpMoney(r.comprado)}</div>
      <div><strong>Recibido:</strong> ${erpMoney(r.recibido)}</div>
      <div><strong>Pagado:</strong> ${erpMoney(r.pagado)}</div>
      <div><strong>Pendiente por pagar:</strong> ${erpMoney(r.pendiente)}</div>
    </div>`,
    titulo: (r) => r.razon_social,
    key: (r) => r.id_proveedor,
    acciones: { agregar: null, modificar: null, eliminar: null },
    bloqueadas: { agregar: 'Saldo por proveedor según recepciones y pagos.', modificar: 'Sólo lectura; los pagos se generan con la recepción de la orden.', eliminar: 'Registro contable.' },
    vacio: 'Sin cuentas por pagar',
  });
}

// ---------------------------------------------------------------------------
// Pedidos B2B (se mantiene su detalle propio)
// ---------------------------------------------------------------------------

const pedState = { page: 1, page_size: 15, total_pages: 1 };

async function loadPedidosERP() {
  const params = new URLSearchParams({ page: pedState.page, page_size: pedState.page_size });
  const estado = document.getElementById('ped-estado')?.value;
  const q = document.getElementById('ped-q')?.value;
  if (estado) params.set('estado', estado);
  if (q) params.set('q', q);
  const res = await api(`/pedidos?${params}`);
  const tbody = document.getElementById('ped-body');
  tbody.innerHTML = (res.items || []).map((p) => `
    <tr>
      <td>${esc(p.numero || p.id_pedido)}</td>
      <td>${esc(p.empresa)}</td>
      <td>${esc((p.fecha || '').slice(0, 19))}</td>
      <td>${badge(p.estado)}</td>
      <td class="num center">${p.n_items}</td>
      <td class="num">${erpMoney(p.total)}</td>
      <td class="row-actions"><div class="row-act"><button type="button" class="act-btn act-view" data-ped-ver="${p.id_pedido}">Ver</button></div></td>
    </tr>`).join('') || '<tr><td colspan="7">Sin pedidos</td></tr>';
  document.getElementById('ped-total').textContent = res.total_items ?? 0;
  pedState.total_pages = res.total_pages || 1;
  refreshSimplePager(document.getElementById('ped-pager'), pedState);
  tbody.querySelectorAll('[data-ped-ver]').forEach((b) => b.addEventListener('click', () => verPedido(Number(b.dataset.pedVer))));
}

async function cambiarEstadoPedido(idPedido, estado, extra = {}) {
  await api(`/pedidos/${idPedido}/estado`, {
    method: 'POST',
    body: { estado, ...extra },
  });
  toast('Estado actualizado');
  await Promise.all([loadPedidosERP(), verPedido(idPedido)]);
}

async function marcarPedidoEnviado(idPedido, p) {
  let opts;
  try {
    opts = await api(`/logistica/pedidos/${idPedido}/opciones-envio`);
  } catch (e) {
    toast(e.message || 'Sin opciones de envío', 'error');
    return;
  }
  const activos = (opts.transportistas || []).filter((t) => t.activo !== false);
  if (!activos.length) {
    toast(opts.mensaje || 'No hay transportistas para el país del cliente', 'error');
    return;
  }
  const preselect = p.envio?.id_transportista && activos.some((t) => t.id_transportista === p.envio.id_transportista)
    ? p.envio.id_transportista
    : activos[0].id_transportista;
  uiModal({
    modo: 'Despachar',
    tituloExtra: `Pedido ${p.numero || idPedido}`,
    campos: [
      {
        key: 'info',
        type: 'html',
        value: `<p class="meta">Destino <strong>${esc(opts.pais || p.pais || '—')}</strong> → ${esc(opts.macro_label || '—')}. Solo transportistas de esa macro-zona.</p>`,
      },
      {
        key: 'id_transportista',
        label: 'Transportista',
        type: 'select',
        options: activos.map((t) => ({ value: t.id_transportista, label: t.nombre })),
        value: preselect,
      },
    ],
    textoAceptar: 'Confirmar envío',
    onAceptar: async (v) => {
      await api(`/pedidos/${idPedido}/estado`, {
        method: 'POST',
        body: { estado: 'enviado', id_transportista: Number(v.id_transportista) },
      });
      toast('Pedido enviado — transportista asignado');
      await Promise.all([loadPedidosERP(), verPedido(idPedido)]);
    },
  });
}

async function verPedido(idPedido) {
  const p = await api(`/pedidos/${idPedido}`);
  document.getElementById('ped-detalle-card').hidden = false;
  document.getElementById('ped-detalle-numero').textContent = p.numero || p.id_pedido;
  const cont = document.getElementById('ped-detalle');
  cont.innerHTML = `
    <div class="detail-grid">
      <div><strong>Empresa:</strong> ${esc(p.empresa)} (${esc(p.pais || '—')})</div>
      <div><strong>Estado:</strong> ${badge(p.estado)}</div>
      <div><strong>Subtotal:</strong> ${erpMoney(p.subtotal)}</div>
      <div><strong>Impuesto:</strong> ${erpMoney(p.impuesto)}</div>
      ${p.costo_envio > 0 ? `<div><strong>Envío:</strong> ${erpMoney(p.costo_envio)}</div>` : ''}
      <div><strong>Total:</strong> ${erpMoney(p.total)}</div>
      <div><strong>Notas:</strong> ${esc(p.notas || '—')}</div>
    </div>
    <div class="table-wrap"><table>
      <thead><tr><th>Producto</th><th class="num center">Cantidad</th><th class="num">P. unitario</th><th class="num">Subtotal</th></tr></thead>
      <tbody>${p.items.map((i) => `<tr><td>${esc(i.producto)}</td><td class="num center">${i.cantidad}</td><td class="num">${erpMoney(i.precio_unitario)}</td><td class="num">${erpMoney(i.subtotal)}</td></tr>`).join('')}</tbody>
    </table></div>
    <h4>Línea de tiempo</h4>
    <ul class="timeline">
      ${p.historial.map((h) => `<li><span class="tl-fecha">${esc((h.fecha || '').slice(0, 19))}</span> ${esc(h.estado_anterior || 'creación')} → <strong>${esc(ESTADO_LABEL[h.estado_nuevo] || h.estado_nuevo)}</strong>${h.usuario ? ` · ${esc(h.usuario)}` : ''}</li>`).join('')}
    </ul>
    ${p.pagos.length ? `<h4>Pagos</h4><ul>${p.pagos.map((pg) => `<li>${esc(pg.numero)} · ${erpMoney(pg.monto)} · ${esc(pg.estado)}</li>`).join('')}</ul>` : ''}
    ${p.estado !== 'pendiente_pago' && p.estado !== 'cancelado' ? `
      <div class="modal-actions" style="justify-content:flex-start;flex-wrap:wrap;gap:8px;margin-top:12px">
        <button class="btn btn-secondary btn-sm" data-pdf-pedido>PDF Pedido</button>
        ${p.factura ? `<button class="btn btn-secondary btn-sm" data-pdf-factura>PDF Factura</button>` : ''}
        ${p.pagos[0] ? `<button class="btn btn-secondary btn-sm" data-pdf-pago>PDF Pago</button>` : ''}
        ${['pagado', 'preparando', 'enviado', 'entregado'].includes(p.estado) ? `<button class="btn btn-secondary btn-sm" data-ped-asientos>Generar asientos</button>` : ''}
      </div>` : ''}
    ${p.envio ? `
      <h4>Logística</h4>
      <div class="detail-grid">
        <div><strong>Transportista:</strong> ${esc(p.envio.transportista || '—')}</div>
        <div><strong>Estado envío:</strong> ${badge(p.envio.estado || '—')}</div>
      </div>
      ${p.envio.eventos?.length ? `<ul class="timeline">${p.envio.eventos.map((e) => `<li>${esc((e.fecha || '').slice(0, 19))} · <strong>${esc(e.estado)}</strong> — ${esc(e.descripcion || '')}</li>`).join('')}</ul>` : ''}` : ''}
    ${p.transiciones_posibles.length ? `
      <div class="modal-actions" style="justify-content:flex-start">
        ${p.transiciones_posibles.map((t) => `<button class="btn ${t === 'cancelado' ? 'btn-danger' : 'btn-primary'} btn-sm" data-ped-trans="${esc(t)}">Marcar: ${esc(ESTADO_LABEL[t] || t)}</button>`).join(' ')}
      </div>` : ''}
  `;
  cont.querySelectorAll('[data-ped-trans]').forEach((b) => b.addEventListener('click', async () => {
    const nuevoEstado = b.dataset.pedTrans;
    if (nuevoEstado === 'cancelado' && !confirm('¿Cancelar el pedido?')) return;
    if (nuevoEstado === 'enviado') {
      await marcarPedidoEnviado(idPedido, p);
      return;
    }
    await cambiarEstadoPedido(idPedido, nuevoEstado);
  }));
  cont.querySelector('[data-pdf-pedido]')?.addEventListener('click', async () => {
    try { await downloadComprobante('pedido', idPedido, p.numero); toast('PDF descargado'); }
    catch (e) { toast(e.message, 'error'); }
  });
  cont.querySelector('[data-pdf-factura]')?.addEventListener('click', async () => {
    if (!p.factura) return;
    try { await downloadComprobante('factura', p.factura.id_factura, p.factura.numero); toast('PDF descargado'); }
    catch (e) { toast(e.message, 'error'); }
  });
  cont.querySelector('[data-pdf-pago]')?.addEventListener('click', async () => {
    if (!p.pagos[0]) return;
    try { await downloadComprobante('comprobante_pago', p.pagos[0].id_pago, p.pagos[0].numero); toast('PDF descargado'); }
    catch (e) { toast(e.message, 'error'); }
  });
  cont.querySelector('[data-ped-asientos]')?.addEventListener('click', async () => {
    try {
      const r = await api(`/contabilidad/pedidos/${idPedido}/asientos`, { method: 'POST' });
      toast(r.mensaje || 'Asientos generados');
    } catch (e) { toast(e.message, 'error'); }
  });
  cont.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}

// ---------------------------------------------------------------------------
// Clientes
// ---------------------------------------------------------------------------

let vistaClientes = null;
let cliFichaId = null;
let cliGruposCache = null;

async function ensureCliGrupos() {
  if (cliGruposCache) return cliGruposCache;
  cliGruposCache = await api('/clientes/grupos');
  return cliGruposCache;
}

function cliGrupoOptions(grupos, selectedId) {
  const sel = selectedId != null ? String(selectedId) : '';
  return [
    { value: '', label: 'Sin grupo — lista Público (por defecto)' },
    ...(grupos || []).map((g) => ({
      value: String(g.id_grupo),
      label: `${g.nombre}${g.lista_precio ? ` → ${g.lista_precio}` : ''}`,
      selected: sel === String(g.id_grupo),
    })),
  ];
}

async function loadClientesERP() {
  if (!vistaClientes) vistaClientes = crearVistaClientes();
  await vistaClientes.recargar();
}

function crearVistaClientes() {
  const st = { page: 1, page_size: 20, total_pages: 1 };
  return createDataView('vista-clientes', {
    state: st,
    autoLoad: false,
    buscar: { id: 'cli-q', placeholder: 'Empresa o email...' },
    columnas: [
      { key: 'nombre_empresa', label: 'Empresa' },
      { key: 'lista_precio', label: 'Lista', render: (c) => esc(c.lista_precio || 'Público') },
      { key: 'pais', label: 'País', render: (c) => esc(c.pais || '—') },
      { key: 'email', label: 'Email', render: (c) => esc(c.email || '—') },
      { key: 'n_pedidos', label: 'Pedidos', align: 'num' },
      { key: 'total_comprado', label: 'Total comprado', align: 'num', render: (c) => erpMoney(c.total_comprado) },
      { key: 'activo', label: 'Activo', align: 'center', render: (c) => `
        <label class="gt-toggle" title="${c.activo ? 'Activo' : 'Inactivo'}">
          <input type="checkbox" data-toggle-cli="${c.id_cliente}" ${c.activo ? 'checked' : ''}>
          <span class="gt-toggle-slider"></span>
        </label>` },
    ],
    cargar: async (s) => {
      const q = document.getElementById('cli-q')?.value?.trim();
      const res = await api(`/clientes${q ? `?q=${encodeURIComponent(q)}` : ''}`);
      return { items: res, total: res.length };
    },
    onAfterRender: (host) => {
      host.querySelectorAll('[data-toggle-cli]').forEach((inp) => {
        inp.addEventListener('change', async () => {
          const id = Number(inp.dataset.toggleCli);
          try {
            await api(`/clientes/${id}/activo`, { method: 'POST', body: { activo: inp.checked } });
            toast(inp.checked ? 'Cliente activado' : 'Cliente desactivado');
            await vistaClientes.recargar();
          } catch (e) {
            inp.checked = !inp.checked;
            toast(e.message || 'No se pudo cambiar', 'error');
          }
        });
      });
    },
    filaClase: (c) => c.activo ? '' : 'row-inactive',
    resumen: (c) => `<div class="detail-grid">
      <div><strong>Lista de precios:</strong> ${esc(c.lista_precio || 'Público')}${c.grupo ? ` <span class="meta">(${esc(c.grupo)})</span>` : ''}</div>
      <div><strong>País:</strong> ${esc(c.pais || '—')}</div>
      <div><strong>Email:</strong> ${esc(c.email || '—')}</div>
      <div><strong>Pedidos:</strong> ${c.n_pedidos}</div>
      <div><strong>Total comprado:</strong> ${erpMoney(c.total_comprado)}</div>
      <div><strong>Estado:</strong> ${c.activo ? 'Activo' : 'Inactivo'} (interruptor en tabla)</div>
    </div>`,
    titulo: (c) => c.nombre_empresa,
    key: (c) => c.id_cliente,
    acciones: {
      agregar: null,
      modificar: (row) => void openClienteModal(row.id_cliente),
      eliminar: null,
    },
    bloqueadas: {
      agregar: 'Los clientes se registran ellos mismos en el portal B2B (:8001).',
      eliminar: 'El cliente tiene historial (pedidos y CxC); no se elimina.',
    },
    extras: (c) => [
      { label: 'Ver ficha (CxC e historial)', clase: 'btn-secondary', opensModal: true, fn: () => void verCliente(c.id_cliente) },
    ],
    vacio: 'Sin clientes',
  });
}

async function openClienteModal(idCliente) {
  await ensureFilters();
  const [c, grupos] = await Promise.all([api(`/clientes/${idCliente}`), ensureCliGrupos()]);
  const telParts = splitTelefono(c.telefono);
  uiModal({
    modo: 'Actualizar',
    tituloExtra: c.nombre_empresa,
    campos: [
      { key: 'nombre_empresa', label: 'Nombre de empresa', value: c.nombre_empresa || '' },
      { key: 'pais', label: 'País', type: 'select', value: c.pais || '', options: [{ value: '', label: '— Selecciona un país —' }, ...(filterCache?.paises || []).map((p) => ({ value: p.country, label: p.country }))] },
      { key: 'telefono_pref', label: 'Prefijo país', type: 'select', value: telParts.pref, options: PHONE_PREFIXES },
      { key: 'telefono_num', label: 'Teléfono (sin prefijo)', value: telParts.num, inputmode: 'numeric', placeholder: '999999999', maxlength: 12 },
      { key: 'direccion', label: 'Dirección', value: c.direccion || '' },
      {
        key: 'id_grupo',
        label: 'Grupo comercial / lista de precios',
        type: 'select',
        value: c.id_grupo != null ? String(c.id_grupo) : '',
        options: cliGrupoOptions(grupos, c.id_grupo),
      },
      {
        key: 'info',
        type: 'html',
        value: `<p class="meta">Email de acceso: <strong>${esc(c.email || '—')}</strong> (no se cambia desde aquí).<br>
          El grupo define qué tarifa ve el cliente en el portal B2B (precio mayorista y cantidad mínima por producto).</p>`,
      },
    ],
    onAceptar: async (v) => {
      const nombre = (v.nombre_empresa || '').trim();
      const pais = (v.pais || '').trim();
      if (nombre.length < 2) { toast('Nombre de empresa inválido', 'error'); return false; }
      if (!pais) { toast('Selecciona un país', 'error'); return false; }
      const idGrupo = (v.id_grupo || '').trim();
      await api(`/clientes/${idCliente}`, {
        method: 'PUT',
        body: {
          nombre_empresa: nombre,
          pais,
          telefono: joinTelefono(v.telefono_pref, v.telefono_num),
          direccion: (v.direccion || '').trim() || null,
        },
      });
      await api(`/clientes/${idCliente}/grupo`, {
        method: 'PUT',
        body: { id_grupo: idGrupo ? Number(idGrupo) : null },
      });
      toast('Datos del cliente actualizados');
      if (vistaClientes) await vistaClientes.recargar();
      if (cliFichaId === idCliente) await verCliente(idCliente);
    },
  });
}

async function verCliente(idCliente) {
  cliFichaId = idCliente;
  const c = await api(`/clientes/${idCliente}`);
  uiModal({
    modo: 'Ficha',
    tituloExtra: c.nombre_empresa,
    ancho: 'lg',
    campos: [{
      key: 'ficha',
      type: 'html',
      value: `
        <div style="display:flex;justify-content:flex-end;margin-bottom:.5rem">
          <button type="button" class="btn btn-secondary btn-sm" id="cli-ficha-edit">Editar datos</button>
        </div>
        <div class="detail-grid">
          <div><strong>Email:</strong> ${esc(c.email || '—')}</div>
          <div><strong>Lista de precios:</strong> ${esc(c.lista_precio || 'Público')}</div>
          <div><strong>Grupo comercial:</strong> ${esc(c.grupo || 'Sin grupo (Público por defecto)')}</div>
          <div><strong>País:</strong> ${esc(c.pais || '—')}</div>
          <div><strong>Teléfono:</strong> ${esc(c.telefono || '—')}</div>
          <div><strong>Dirección:</strong> ${esc(c.direccion || '—')}</div>
          <div><strong>Registro:</strong> ${esc((c.fecha_registro || '').slice(0, 19))}</div>
          <div><strong>Estado:</strong> ${c.activo ? 'Activo' : 'Inactivo'}</div>
        </div>
        <div class="kpi-grid" style="margin:1rem 0">
          <div class="kpi-card"><div class="label">Facturado</div><div class="value">${erpMoney(c.cxc.facturado)}</div></div>
          <div class="kpi-card"><div class="label">Pagado</div><div class="value profit">${erpMoney(c.cxc.pagado)}</div></div>
          <div class="kpi-card"><div class="label">Saldo CxC</div><div class="value ${c.cxc.saldo > 0 ? 'loss' : ''}">${erpMoney(c.cxc.saldo)}</div></div>
        </div>
        <h4>Historial de pedidos</h4>
        <div class="table-wrap"><table class="table-erp">
          <thead><tr><th>Número</th><th>Fecha</th><th>Estado</th><th>Total</th></tr></thead>
          <tbody>${c.pedidos.map((p) => `<tr><td>${esc(p.numero || p.id_pedido)}</td><td>${esc((p.fecha || '').slice(0, 19))}</td><td>${badge(p.estado)}</td><td>${erpMoney(p.total)}</td></tr>`).join('') || '<tr><td colspan="4">Sin pedidos</td></tr>'}</tbody>
        </table></div>`,
    }],
    onReady: (ov) => {
      ov.querySelector('#cli-ficha-edit')?.addEventListener('click', () => {
        uiModalCerrar();
        void openClienteModal(idCliente);
      });
    },
  });
}

// ---------------------------------------------------------------------------
// Finanzas
// ---------------------------------------------------------------------------

async function loadFinanzas(sync = false) {
  if (sync) {
    try {
      const r = await api('/contabilidad/sincronizar', { method: 'POST' });
      if (r.creados > 0) toast(`${r.creados} asiento(s) generado(s) desde pedidos pagados`);
    } catch (e) {
      toast(e.message || 'No se pudo sincronizar', 'error');
    }
  }
  const [resumen, asientos] = await Promise.all([
    api('/contabilidad/resumen'),
    api('/contabilidad/asientos?page=1&page_size=15'),
  ]);
  document.getElementById('fin-asientos-total').textContent = resumen.n_asientos;
  const kpis = document.getElementById('fin-kpis');
  const porCodigo = Object.fromEntries((resumen.cuentas || []).map((c) => [c.codigo, c]));
  const caja = porCodigo['1101']?.saldo || 0;
  const cxc = porCodigo['1201']?.saldo || 0;
  const cxp = porCodigo['2002']?.saldo || 0;
  const pagosExt = porCodigo['3001']?.saldo || 0;
  const ingresos = (porCodigo['4101']?.saldo || 0) + (porCodigo['4102']?.saldo || 0);
  const ivaDebito = porCodigo['2101']?.saldo || 0;
  const costo = porCodigo['5101']?.saldo || 0;
  const inventario = porCodigo['1301']?.saldo || 0;
  const utilidad = ingresos - costo;
  kpis.innerHTML = `
    <div class="kpi-card"><div class="label">Caja (1101)</div><div class="value ${caja < 0 ? 'loss' : 'profit'}">${erpMoney(caja)}</div><div class="kpi-hint">${caja < 0 ? 'Descuadrada — Regularizar' : 'Disponible'}</div></div>
    <div class="kpi-card"><div class="label">CxC (1201)</div><div class="value ${cxc > 0 ? 'loss' : ''}">${erpMoney(cxc)}</div><div class="kpi-hint">Por cobrar a clientes</div></div>
    <div class="kpi-card"><div class="label">Inventario (1301)</div><div class="value">${erpMoney(inventario)}</div><div class="kpi-hint">Valor en almacén</div></div>
    <div class="kpi-card"><div class="label">CxP (2002)</div><div class="value">${erpMoney(cxp)}</div><div class="kpi-hint">Por pagar a proveedores</div></div>
    <div class="kpi-card"><div class="label">IVA débito (2101)</div><div class="value">${erpMoney(ivaDebito)}</div><div class="kpi-hint">IVA de ventas</div></div>
    <div class="kpi-card"><div class="label">Ingresos netos</div><div class="value profit">${erpMoney(ingresos)}</div><div class="kpi-hint">4101 + 4102</div></div>
    <div class="kpi-card"><div class="label">Costo ventas (5101)</div><div class="value">${erpMoney(costo)}</div><div class="kpi-hint">COGS</div></div>
    <div class="kpi-card"><div class="label">Utilidad bruta</div><div class="value ${utilidad >= 0 ? 'profit' : 'loss'}">${erpMoney(utilidad)}</div><div class="kpi-hint">Ingresos − costo</div></div>
    <div class="kpi-card"><div class="label">Pagos externos (3001)</div><div class="value">${erpMoney(pagosExt)}</div><div class="kpi-hint">Financiamiento compras</div></div>
    <div class="kpi-card"><div class="label">Asientos</div><div class="value">${resumen.n_asientos}</div><div class="kpi-hint">Libro diario</div></div>`;
  document.getElementById('fin-cuentas-body').innerHTML = (resumen.cuentas || []).map((c) => `
    <tr><td class="mono">${esc(c.codigo)}</td><td>${esc(c.nombre)}</td><td><span class="badge badge-${esc(c.tipo)}">${esc(c.tipo)}</span></td>
    <td class="num">${erpMoney(c.debe)}</td><td class="num">${erpMoney(c.haber)}</td>
    <td class="num fin-saldo">${erpMoney(c.saldo)}</td></tr>`).join('') || '<tr><td colspan="6">Sin movimientos contables</td></tr>';
  document.getElementById('fin-asientos-body').innerHTML = (asientos.items || []).map((a) => `
    <tr><td class="mono">${esc(a.numero)}</td><td>${esc((a.fecha || '').slice(0, 16).replace('T', ' '))}</td><td>${esc(a.descripcion)}</td>
    <td class="num">${erpMoney(a.total)}</td><td class="num">${a.id_pedido ? `#${a.id_pedido}` : '—'}</td></tr>`).join('') || '<tr><td colspan="5">Sin asientos</td></tr>';
}

// ---------------------------------------------------------------------------
// Rentabilidad
// ---------------------------------------------------------------------------

const rentState = { page: 1, total_pages: 1 };

async function loadRentabilidad() {
  const dim = document.getElementById('rent-dim')?.value || 'producto';
  const from = document.getElementById('rent-from')?.value || '';
  const to = document.getElementById('rent-to')?.value || '';
  const params = new URLSearchParams({ dimension: dim, page: String(rentState.page), page_size: '50' });
  if (from) params.set('date_from', from);
  if (to) params.set('date_to', to);
  const res = await api(`/rentabilidad?${params}`);
  rentState.total_pages = res.total_pages || 1;
  refreshSimplePager(document.getElementById('rent-pager'), rentState);
  const rows = res.data || [];
  const summary = res.summary || {};
  const totRev = summary.total_revenue ?? rows.reduce((s, r) => s + (r.total_revenue || 0), 0);
  const totProfit = summary.total_profit ?? rows.reduce((s, r) => s + (r.total_profit || 0), 0);
  const margen = summary.margen_pct != null
    ? Number(summary.margen_pct).toFixed(1)
    : (totRev ? ((totProfit / totRev) * 100).toFixed(1) : '—');
  document.getElementById('rent-kpis').innerHTML = `
    <div class="kpi-card"><div class="label">Ingresos (total)</div><div class="value">${erpMoney(totRev)}</div></div>
    <div class="kpi-card"><div class="label">Profit (total)</div><div class="value profit">${erpMoney(totProfit)}</div></div>
    <div class="kpi-card"><div class="label">Margen global</div><div class="value">${margen}%</div></div>
    <div class="kpi-card"><div class="label">Filas / página</div><div class="value">${rows.length} / ${summary.filas ?? '—'}</div></div>`;
  const cls = (c) => ({ alto: 'badge badge-pagado', medio: 'badge badge-preparando', bajo: 'badge badge-cancelado' }[c] || 'badge');
  document.getElementById('rent-body').innerHTML = rows.map((r) => `
    <tr>
      <td>${esc(r.dimension)}</td>
      <td class="num">${erpMoney(r.total_revenue)}</td>
      <td class="num">${erpMoney(r.total_cost)}</td>
      <td class="num profit">${erpMoney(r.total_profit)}</td>
      <td class="num center">${r.margen_pct != null ? `${r.margen_pct}%` : '—'}</td>
      <td class="center">${r.clasificacion_margen ? `<span class="${cls(r.clasificacion_margen)}">${esc(r.clasificacion_margen)}</span>` : '—'}</td>
    </tr>`).join('') || '<tr><td colspan="6">Sin datos para los filtros seleccionados.</td></tr>';
}

// ---------------------------------------------------------------------------
// Logística (pestañas: Pedidos para despacho | Transportistas | Zonas | Almacenes)
// ---------------------------------------------------------------------------

let vistasLogistica = {};
let logTransportistasCache = [];

async function loadLogistica() {
  if (!vistasLogistica.despacho) {
    const paneles = createTabsView('vista-logistica', [
      { id: 'despacho', label: 'Pedidos para despacho' },
      { id: 'transportistas', label: 'Transportistas' },
      { id: 'zonas', label: 'Zonas y tarifas' },
      { id: 'almacenes', label: 'Almacenes' },
    ]);
    vistasLogistica.despacho = crearVistaDespacho(paneles.despacho);
    vistasLogistica.transportistas = crearVistaTransportistas(paneles.transportistas);
    vistasLogistica.zonas = crearVistaZonas(paneles.zonas);
    vistasLogistica.almacenes = crearVistaAlmacenes(paneles.almacenes);
  }
  await Promise.all([
    vistasLogistica.despacho.recargar(),
    vistasLogistica.transportistas.recargar(),
    vistasLogistica.zonas.recargar(),
    vistasLogistica.almacenes.recargar(),
  ]);
}

function crearVistaDespacho(cont) {
  const st = { page: 1, page_size: 20, total_pages: 1 };
  return createDataView(cont, {
    state: st,
    autoLoad: false,
    columnas: [
      { key: 'id_pedido', label: 'ID', align: 'center' },
      { key: 'numero', label: 'Nº pedido' },
      { key: 'empresa', label: 'Cliente' },
      { key: 'pais', label: 'País', render: (p) => esc(p.pais || '—') },
      { key: 'macro_label', label: 'Macro-zona', render: (p) => esc(p.macro_label || p.macro_zona || '—') },
      { key: 'estado_pedido', label: 'Estado pedido', render: (p) => badge(p.estado_pedido) },
      { key: 'envio', label: 'Envío', render: (p) => p.tiene_envio ? badge(p.estado_envio) : '<span class="meta">Sin envío</span>' },
      { key: 'transportista', label: 'Transportista', render: (p) => esc(p.transportista || '—') },
    ],
    cargar: async () => {
      const pedidos = await api('/logistica/pedidos');
      return { items: pedidos, total: pedidos.length };
    },
    resumen: (p) => `<div class="detail-grid">
      <div><strong>Cliente:</strong> ${esc(p.empresa)}</div>
      <div><strong>País / región:</strong> ${esc(p.pais || '—')} · ${esc(p.region || '—')}</div>
      <div><strong>Macro-zona:</strong> ${esc(p.macro_label || p.macro_zona || '—')}</div>
      <div><strong>Estado:</strong> ${badge(p.estado_pedido)}</div>
      <div><strong>Envío:</strong> ${p.tiene_envio ? badge(p.estado_envio) : '—'}</div>
      <div><strong>Transportista:</strong> ${esc(p.transportista || '—')}</div>
    </div>`,
    titulo: (p) => `Pedido ${p.numero}`,
    key: (p) => p.id_pedido,
    acciones: {
      agregar: null,
      modificar: null,
      eliminar: null,
      verLabel: (p) => (p.tiene_envio ? 'Tracking' : 'Despachar'),
      ver: async (p) => {
        if (p.tiene_envio) await mostrarEnvioPedido(p.id_pedido);
        else await abrirCrearEnvio(p.id_pedido);
      },
    },
    bloqueadas: {
      agregar: 'Usa Despachar en la fila del pedido pagado.',
      modificar: 'Usa Despachar o Tracking en la fila.',
      eliminar: 'Los envíos no se eliminan.',
    },
    extras: (p) => {
      const acc = [];
      if (p.tiene_envio && p.id_envio) {
          acc.push({
            label: 'Descargar guía de remisión', clase: 'btn-secondary',
            fn: async () => { try { await downloadComprobante('guia_remision', p.id_envio, `GRE-${p.id_envio}`); toast('Guía PDF descargada'); } catch (e) { toast(e.message, 'error'); } },
          });
      }
      return acc;
    },
    vacio: 'No hay pedidos pagados o en despacho',
  });
}

function crearVistaTransportistas(cont) {
  const st = { page: 1, page_size: 15, total_pages: 1 };
  return createDataView(cont, {
    state: st,
    autoLoad: false,
    columnas: [
      { key: 'id_transportista', label: 'ID', align: 'center' },
      { key: 'nombre', label: 'Nombre' },
      { key: 'macro_label', label: 'Macro-zona', render: (t) => esc(t.macro_label || t.macro_zona || '—') },
      { key: 'region', label: 'Hub región', render: (t) => esc(t.region || '—') },
      { key: 'activo', label: 'Activo', align: 'center', render: (t) => `
        <label class="gt-toggle" title="${t.activo ? 'Activo' : 'Inactivo'}">
          <input type="checkbox" data-toggle-trans="${t.id_transportista}" ${t.activo ? 'checked' : ''}>
          <span class="gt-toggle-slider"></span>
        </label>` },
    ],
    cargar: async () => {
      const trans = await api('/logistica/transportistas');
      logTransportistasCache = trans;
      return { items: trans, total: trans.length };
    },
    onAfterRender: (root) => {
      root.querySelectorAll('[data-toggle-trans]').forEach((inp) => {
        inp.addEventListener('change', async () => {
          const id = Number(inp.dataset.toggleTrans);
          try {
            await api(`/logistica/transportistas/${id}/activo`, {
              method: 'POST', body: { activo: inp.checked },
            });
            toast(inp.checked ? 'Transportista activado' : 'Transportista desactivado');
            await vistasLogistica.transportistas.recargar();
          } catch (e) {
            inp.checked = !inp.checked;
            toast(e.message || 'No se pudo cambiar', 'error');
          }
        });
      });
    },
    filaClase: (t) => t.activo ? '' : 'row-inactive',
    resumen: (t) => `<div class="detail-grid">
      <div><strong>Macro-zona:</strong> ${esc(t.macro_label || t.macro_zona || '—')}</div>
      <div><strong>Hub:</strong> ${esc(t.region || '—')}</div>
      <div><strong>Estado:</strong> ${t.activo ? 'Activo' : 'Inactivo'} (interruptor en tabla)</div>
    </div>`,
    titulo: (t) => t.nombre,
    key: (t) => t.id_transportista,
    acciones: {
      agregar: () => void abrirModalTransportista(),
      modificar: (row) => void abrirModalTransportista(row),
      eliminar: async (row) => {
        await api(`/logistica/transportistas/${row.id_transportista}`, { method: 'DELETE' });
        toast('Transportista eliminado');
      },
    },
    bloqueadas: { eliminar: 'Solo se eliminan transportistas sin envíos; si está en uso, desactívelo.' },
    vacio: 'Sin transportistas',
  });
}

function abrirModalTransportista(row = null) {
  const macroOpts = [
    { value: 'americas', label: 'Américas (Norte / Centro / Sur)' },
    { value: 'emea', label: 'EMEA (Europa / MENA / África)' },
    { value: 'apac', label: 'APAC (Asia / Oceanía)' },
  ];
  uiModal({
    modo: row ? 'Actualizar' : 'Agregar',
    tituloExtra: 'Transportista',
    campos: [
      { key: 'nombre', label: 'Nombre', value: row?.nombre || '', maxlength: 80, required: true },
      { key: 'macro_zona', label: 'Macro-zona operativa *', type: 'select', options: macroOpts, value: row?.macro_zona || 'americas', required: true },
    ],
    onAceptar: async (v) => {
      const nombre = (v.nombre || '').trim();
      if (nombre.length < 2) { toast('Nombre inválido', 'error'); return false; }
      const macro_zona = (v.macro_zona || '').trim() || null;
      if (!macro_zona) { toast('Seleccione macro-zona', 'error'); return false; }
      const body = { nombre, macro_zona };
      if (row) {
        await api(`/logistica/transportistas/${row.id_transportista}`, { method: 'PUT', body });
        toast('Transportista actualizado');
      } else {
        await api('/logistica/transportistas', { method: 'POST', body });
        toast('Transportista creado');
      }
      await vistasLogistica.transportistas.recargar();
    },
  });
}

function crearVistaZonas(cont) {
  const st = { page: 1, page_size: 20, total_pages: 1 };
  return createDataView(cont, {
    state: st,
    autoLoad: false,
    columnas: [
      { key: 'zona', label: 'Zona' },
      { key: 'macro_label', label: 'Macro-zona', render: (r) => esc(r.macro_label || r.macro_zona || '—') },
      { key: 'costo_base', label: 'Costo base', align: 'num', render: (r) => r.costo_base != null ? erpMoney(r.costo_base) : '' },
      { key: 'peso_max', label: 'Peso máx.', align: 'num', render: (r) => r.peso_max ?? '—' },
      { key: 'tarifa', label: 'Tarifa', align: 'num', render: (r) => r.tarifa != null ? erpMoney(r.tarifa) : '' },
    ],
    cargar: async () => {
      const zonas = await api('/logistica/zonas');
      const filas = zonas.flatMap((z) => {
        const tarifas = (z.tarifas && z.tarifas.length) ? z.tarifas : [{ peso_max: null, costo: null, id_tarifa: null }];
        return tarifas.map((t) => ({
          id: `t-${t.id_tarifa ?? `${z.id_zona}-s`}`,
          id_zona: z.id_zona,
          id_tarifa: t.id_tarifa,
          zona: z.nombre,
          macro_zona: z.macro_zona,
          macro_label: z.macro_label,
          costo_base: z.costo_base,
          peso_max: t.peso_max ?? '—',
          tarifa: t.costo,
        }));
      });
      return { items: filas, total: filas.length };
    },
    resumen: (r) => `<div class="detail-grid">
      <div><strong>Zona:</strong> ${esc(r.zona || '—')}</div>
      <div><strong>Costo base:</strong> ${r.costo_base != null ? erpMoney(r.costo_base) : '—'}</div>
      <div><strong>Peso máx.:</strong> ${r.peso_max ?? '—'}</div>
      <div><strong>Tarifa:</strong> ${r.tarifa != null ? erpMoney(r.tarifa) : '—'}</div>
    </div>`,
    titulo: (r) => r.zona || 'Tarifa de envío',
    key: (r) => r.id,
    acciones: {
      agregar: () => void openZonaModal(),
      modificar: (row) => openZonaModal({ ...row, zona: row.zona }),
      eliminar: async (row) => {
        await api(`/logistica/zonas/${row.id_zona}`, { method: 'DELETE' });
        toast('Zona eliminada');
      },
    },
    bloqueadas: { eliminar: 'Se elimina la zona solo si no está usada por envíos.' },
    extras: (r) => {
      const opts = [{ label: 'Agregar tarifa', clase: 'btn-secondary', opensModal: true, fn: () => openTarifaModal(r.id_zona, null) }];
      if (r.id_tarifa != null) {
        opts.push({ label: 'Editar tarifa', clase: 'btn-primary', opensModal: true, fn: () => openTarifaModal(r.id_zona, { id_tarifa: r.id_tarifa, peso_max: r.peso_max, costo: r.tarifa }) });
        opts.push({ label: 'Eliminar tarifa', clase: 'btn-danger', fn: async () => {
          await api(`/logistica/tarifas/${r.id_tarifa}`, { method: 'DELETE' });
          toast('Tarifa eliminada');
        } });
      }
      return opts;
    },
    vacio: 'Sin zonas configuradas',
  });
}

function openZonaModal(zona = null) {
  const macroOpts = [
    { value: 'americas', label: 'Américas' },
    { value: 'emea', label: 'EMEA' },
    { value: 'apac', label: 'APAC' },
  ];
  uiModal({
    modo: zona ? 'Actualizar' : 'Agregar',
    tituloExtra: zona ? zona.zona : 'Nueva zona de envío',
    campos: [
      { key: 'nombre', label: 'Nombre', value: zona?.zona || '', maxlength: 80 },
      { key: 'macro_zona', label: 'Macro-zona *', type: 'select', options: macroOpts, value: zona?.macro_zona || 'americas' },
      { key: 'costo_base', label: 'Costo base (USD)', type: 'number', step: '0.5', min: 0, value: zona?.costo_base ?? 0 },
    ],
    onAceptar: async (v) => {
      const nombre = (v.nombre || '').trim();
      if (nombre.length < 2) { toast('Nombre de zona inválido', 'error'); return false; }
      const body = { nombre, costo_base: Number(v.costo_base) || 0, macro_zona: v.macro_zona || null };
      if (zona) {
        await api(`/logistica/zonas/${zona.id_zona}`, { method: 'PUT', body });
        toast('Zona actualizada');
      } else {
        await api('/logistica/zonas', { method: 'POST', body });
        toast('Zona creada');
      }
      await vistasLogistica.zonas.recargar();
    },
  });
}

function openTarifaModal(idZona, tarifa = null) {
  uiModal({
    modo: tarifa ? 'Actualizar' : 'Agregar',
    tituloExtra: `Tarifa de envío (zona #${idZona})`,
    campos: [
      { key: 'peso_max', label: 'Peso máximo (kg)', type: 'number', step: '0.5', min: 0.1, value: tarifa?.peso_max ?? 5 },
      { key: 'costo', label: 'Costo (USD)', type: 'number', step: '0.5', min: 0, value: tarifa?.costo ?? 0 },
    ],
    onAceptar: async (v) => {
      const body = { id_zona: idZona, peso_max: Number(v.peso_max), costo: Number(v.costo) };
      if (tarifa) {
        await api(`/logistica/tarifas/${tarifa.id_tarifa}`, { method: 'PUT', body });
        toast('Tarifa actualizada');
      } else {
        await api('/logistica/tarifas', { method: 'POST', body });
        toast('Tarifa creada');
      }
      await vistasLogistica.zonas.recargar();
    },
  });
}

function crearVistaAlmacenes(cont) {
  const st = { page: 1, page_size: 15, total_pages: 1 };
  return createDataView(cont, {
    state: st,
    autoLoad: false,
    columnas: [
      { key: 'codigo', label: 'Código', align: 'center', render: (a) => esc(a.codigo || '—') },
      { key: 'nombre', label: 'Almacén / bodega' },
      { key: 'macro_zona', label: 'Macro-zona', render: (a) => esc(ZONA_CORTA[a.macro_zona] || '—') },
      { key: 'es_hub', label: 'Rol', align: 'center', render: (a) => a.es_hub
        ? '<span class="badge badge-success">Hub regional</span>'
        : '<span class="meta">Satélite</span>' },
      { key: 'region', label: 'Región', render: (a) => esc(a.region || '—') },
      { key: 'skus', label: 'SKUs', align: 'num', render: (a) => fmtQty(a.skus || 0) },
      { key: 'stock_total', label: 'Stock total', align: 'num', render: (a) => {
        const n = Number(a.stock_total || 0);
        return n > 0 ? fmtQty(n) : '<span class="badge badge-cancelado">Vacía</span>';
      } },
      { key: 'alertas_stock', label: 'Alertas', align: 'center', render: (a) => {
        const n = Number(a.alertas_stock || 0);
        return n > 0 ? `<span class="badge badge-warning">${n}</span>` : '<span class="meta">0</span>';
      } },
      { key: 'activo', label: 'Activo', align: 'center', render: (a) => `
        <label class="gt-toggle" title="${a.activo ? 'Activo' : 'Inactivo'}">
          <input type="checkbox" data-toggle-alm="${a.id_almacen}" ${a.activo ? 'checked' : ''}>
          <span class="gt-toggle-slider"></span>
        </label>` },
    ],
    cargar: async () => {
      const alm = await api('/logistica/almacenes');
      return { items: alm, total: alm.length };
    },
    onAfterRender: (root) => {
      root.querySelectorAll('[data-toggle-alm]').forEach((inp) => {
        inp.addEventListener('change', async () => {
          const id = Number(inp.dataset.toggleAlm);
          try {
            await api(`/logistica/almacenes/${id}/activo`, {
              method: 'POST', body: { activo: inp.checked },
            });
            toast(inp.checked ? 'Almacén activado' : 'Almacén desactivado');
            await vistasLogistica.almacenes.recargar();
          } catch (e) {
            inp.checked = !inp.checked;
            toast(e.message || 'No se pudo cambiar', 'error');
          }
        });
      });
    },
    filaClase: (a) => a.activo ? '' : 'row-inactive',
    resumen: (a) => `<div class="detail-grid">
      <div><strong>Código:</strong> ${esc(a.codigo || '—')}</div>
      <div><strong>Macro-zona:</strong> ${esc(a.macro_label || '—')}</div>
      <div><strong>Rol en la red:</strong> ${esc(a.rol || (a.es_hub ? 'Hub regional' : 'Bodega satélite'))}</div>
      <div><strong>Región:</strong> ${esc(a.region || '—')}</div>
      <div><strong>Dirección:</strong> ${esc(a.direccion || '—')}</div>
      <div><strong>SKUs con stock:</strong> ${fmtQty(a.skus || 0)}</div>
      <div><strong>Stock total:</strong> ${fmtQty(a.stock_total)}</div>
      <div><strong>Alertas stock:</strong> ${fmtQty(a.alertas_stock || 0)}</div>
      <div><strong>Atiende a:</strong> clientes de ${esc(a.macro_label || 'su región')}</div>
      <div><strong>Estado:</strong> ${a.activo ? 'Activo' : 'Inactivo'} (interruptor en tabla)</div>
    </div>`,
    titulo: (a) => a.nombre,
    key: (a) => a.id_almacen,
    acciones: {
      agregar: () => abrirModalAlmacen(),
      modificar: (row) => abrirModalAlmacen(row),
      eliminar: async (row) => {
        await api(`/logistica/almacenes/${row.id_almacen}`, { method: 'DELETE' });
        toast('Almacén eliminado');
      },
    },
    extras: (a) => [{
      label: 'Ver inventario',
      clase: 'btn-secondary',
      opensModal: true,
      fn: () => void verStockAlmacen(a.id_almacen, a.nombre),
    }],
    bloqueadas: { eliminar: 'Solo se eliminan almacenes sin stock; si está en uso, desactívelo.' },
    vacio: 'Sin almacenes configurados',
  });
}

async function verStockAlmacen(idAlmacen, nombre) {
  try {
    const data = await api(`/logistica/almacenes/${idAlmacen}/stock`);
    const items = data.items || [];
    const filas = items.length
      ? items.map((it) => `
          <tr class="${it.bajo ? 'row-inactive' : ''}">
            <td>${esc(it.producto)}</td>
            <td class="num">${fmtQty(it.disponible)}</td>
            <td class="num">${fmtQty(it.reservada)}</td>
            <td class="num">${fmtQty(it.umbral)}</td>
            <td>${it.bajo ? '<span class="badge badge-warning">Bajo</span>' : '<span class="badge badge-success">OK</span>'}</td>
          </tr>`).join('')
      : '<tr><td colspan="5" class="meta">Sin movimientos de stock en esta bodega.</td></tr>';
    uiModal({
      modo: 'Inventario',
      tituloExtra: nombre || `Almacén #${idAlmacen}`,
      ancho: 'lg',
      textoAceptar: 'Cerrar',
      campos: [{
        key: 'tabla',
        type: 'html',
        value: `<div class="table-wrap" style="max-height:360px;overflow:auto">
          <table><thead><tr>
            <th>Producto</th><th class="num">Disponible</th><th class="num">Reservada</th><th class="num">Umbral</th><th>Estado</th>
          </tr></thead><tbody>${filas}</tbody></table></div>`,
      }],
    });
  } catch (e) {
    toast(e.message || 'No se pudo cargar el inventario', 'error');
  }
}

function abrirModalAlmacen(row = null) {
  const regionOpts = (filterCache?.regiones || []).map((r) => ({ value: r.id_region, label: r.region }));
  uiModal({
    modo: row ? 'Actualizar' : 'Agregar',
    tituloExtra: 'Almacén',
    campos: [
      { key: 'nombre', label: 'Nombre del almacén', value: row?.nombre || '' },
      { key: 'id_region', label: 'Región (define la macro-zona que atenderá)', type: 'select', options: [{ value: '', label: '— Sin región —' }, ...regionOpts], value: row?.id_region ?? '' },
      { key: 'direccion', label: 'Dirección', value: row?.direccion || '' },
      ...(row ? [] : [{
        key: 'nota', type: 'html',
        value: '<p class="meta">La bodega nueva se surte automáticamente con el objetivo de inventario satélite, para que los clientes de su zona no vean productos agotados.</p>',
      }]),
    ],
    onAceptar: async (v) => {
      const nombre = (v.nombre || '').trim();
      if (nombre.length < 2) { toast('Nombre de almacén inválido', 'error'); return false; }
      const body = { nombre, direccion: (v.direccion || '').trim() || null, id_region: v.id_region === '' || v.id_region == null ? null : Number(v.id_region) };
      if (row) {
        await api(`/logistica/almacenes/${row.id_almacen}`, { method: 'PUT', body });
        toast('Almacén actualizado');
      } else {
        const creado = await api('/logistica/almacenes', { method: 'POST', body });
        const surtido = creado?.surtido_inicial;
        toast(surtido?.lineas
          ? `Bodega creada y surtida con ${fmtQty(surtido.unidades)} unidades en ${surtido.lineas} productos`
          : 'Almacén creado');
      }
      __bodegasCache = null;
      await vistasLogistica.almacenes.recargar();
    },
  });
}

async function mostrarEnvioPedido(idPedido) {
  try {
    const envio = await api(`/logistica/pedidos/${idPedido}/envio`);
    const trans = envio.transiciones_posibles || [];
    uiModal({
      modo: 'Tracking',
      tituloExtra: `Envío del pedido #${idPedido}`,
      ancho: 'lg',
      textoAceptar: 'Cerrar',
      campos: [{
        key: 'info',
        type: 'html',
        value: `
          <div class="detail-grid">
            <div><strong>Estado:</strong> ${badge(envio.estado)}</div>
            <div><strong>Transportista:</strong> ${esc(envio.transportista || '—')}</div>
          </div>
          <h4 style="margin-top:1rem">Historial de tracking</h4>
          <div class="table-wrap"><table class="table-erp"><thead><tr><th>Estado</th><th>Fecha</th><th>Descripción</th></tr></thead>
          <tbody>${(envio.eventos || []).map((e) => `<tr><td>${badge(e.estado)}</td><td>${esc((e.fecha || '').slice(0, 19))}</td><td>${esc(e.descripcion || '—')}</td></tr>`).join('') || '<tr><td colspan="3">Sin eventos</td></tr>'}</tbody></table></div>
          ${trans.length ? `<div class="filters" style="margin-top:1rem">
            <div class="field"><label>Siguiente estado</label><select id="track-estado"></select></div>
            <div class="field field-search"><label>Descripción</label><input id="track-desc" placeholder="Se completa automáticamente"></div>
            <button type="button" class="btn btn-primary" id="track-add">Registrar evento</button>
          </div>` : '<p class="meta" style="margin-top:1rem">Envío completado — no hay más transiciones.</p>'}`,
      }],
      onReady: () => {
        const sel = document.getElementById('track-estado');
        const desc = document.getElementById('track-desc');
        if (sel) {
          sel.innerHTML = trans.map((e) => `<option value="${esc(e)}">${esc(ESTADO_LABEL[e] || e)}</option>`).join('');
          sel.value = envio.siguiente_estado || trans[0];
          if (desc) desc.value = ENVIO_DESC_SUGERIDA[sel.value] || envio.descripcion_sugerida || '';
          sel.onchange = () => { if (desc) desc.value = ENVIO_DESC_SUGERIDA[sel.value] || ''; };
        }
        document.getElementById('track-add')?.addEventListener('click', async () => {
          const estado = sel?.value;
          if (!estado) { toast('No hay transición disponible', 'error'); return; }
          try {
            await api(`/logistica/envios/${envio.id_envio}/evento`, {
              method: 'POST', body: { estado, descripcion: desc?.value.trim() || null },
            });
            toast('Evento registrado');
            uiModalCerrar();
            await vistasLogistica.despacho?.recargar?.();
          } catch (e) {
            toast(e.message || 'No se pudo registrar el evento', 'error');
          }
        });
      },
    });
  } catch (e) {
    toast(e.message || 'Sin envío para este pedido', 'error');
  }
}

async function abrirCrearEnvio(idPedido) {
  let opts;
  try {
    opts = await api(`/logistica/pedidos/${idPedido}/opciones-envio`);
  } catch (e) {
    toast(e.message || 'No se pudieron cargar opciones de envío', 'error');
    return;
  }
  const activos = (opts.transportistas || []).filter((t) => t.activo !== false);
  if (!activos.length) {
    toast(opts.mensaje || 'No hay transportistas para el país de entrega del cliente', 'error');
    return;
  }
  const zonas = opts.zonas || [];
  uiModal({
    modo: 'Despachar',
    tituloExtra: `Pedido #${idPedido}`,
    campos: [
      {
        key: 'info',
        type: 'html',
        value: `<p class="meta">Destino: <strong>${esc(opts.pais || '—')}</strong> · ${esc(opts.region || '—')}<br>
          Macro-zona: <strong>${esc(opts.macro_label || opts.macro_zona || '—')}</strong><br>
          Solo se listan transportistas de esa macro-zona.</p>`,
      },
      {
        key: 'id_transportista',
        label: 'Transportista',
        type: 'select',
        options: activos.map((t) => ({
          value: t.id_transportista,
          label: `${t.nombre}${t.macro_label ? ' · ' + t.macro_label : ''}`,
        })),
        value: activos[0].id_transportista,
      },
      ...(zonas.length ? [{
        key: 'id_zona',
        label: 'Zona / tarifa',
        type: 'select',
        options: zonas.map((z) => ({
          value: z.id_zona,
          label: `${z.nombre} (base ${erpMoney(z.costo_base)})`,
        })),
        value: zonas[0].id_zona,
      }] : []),
    ],
    textoAceptar: 'Despachar pedido',
    onAceptar: async (v) => {
      const body = { id_transportista: Number(v.id_transportista) };
      if (v.id_zona) body.id_zona = Number(v.id_zona);
      await api(`/logistica/pedidos/${idPedido}/envio`, {
        method: 'POST', body,
      });
      toast('Pedido despachado — verás «Enviado» en Pedidos B2B');
      await vistasLogistica.despacho?.recargar?.();
    },
  });
}

// ---------------------------------------------------------------------------
// Configuración del sistema
// ---------------------------------------------------------------------------

function renderCfgLogoPreview(ruta) {
  const wrap = document.getElementById('cfg-logo-preview');
  const clearBtn = document.getElementById('cfg-logo-clear');
  if (!wrap) return;
  if (ruta) {
    wrap.innerHTML = `<img src="/media/${esc(ruta)}" alt="Logo empresa" class="cfg-logo-img">`;
    if (clearBtn) clearBtn.hidden = false;
  } else {
    wrap.innerHTML = '<span class="meta">Sin logo configurado</span>';
    if (clearBtn) clearBtn.hidden = true;
  }
}

async function subirLogoEmpresa(file) {
  const fd = new FormData();
  fd.append('file', file);
  const res = await fetch('/api/configuracion/logo', { method: 'POST', body: fd });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.detail || 'No se pudo subir el logo.');
  return data.ruta;
}

let vistaConfiguracion = null;

async function loadConfiguracion() {
  const items = await api('/configuracion');
  const logoCfg = items.find((c) => c.clave === 'EMPRESA_LOGO');
  renderCfgLogoPreview(logoCfg?.valor || '');
  await loadCfgIa();
  if (!vistaConfiguracion) vistaConfiguracion = crearVistaConfiguracion();
  await vistaConfiguracion.recargar();
}

async function loadCfgIa() {
  const keyEl = document.getElementById('cfg-ia-key');
  const urlEl = document.getElementById('cfg-ia-url');
  const modelEl = document.getElementById('cfg-ia-model');
  const hintEl = document.getElementById('cfg-ia-key-hint');
  const statusEl = document.getElementById('cfg-ia-status');
  if (!keyEl || !urlEl || !modelEl) return;
  try {
    const cfg = await api('/configuracion/ia');
    keyEl.value = '';
    keyEl.placeholder = cfg.api_key_configured ? 'Dejar vacío para mantener la clave actual' : 'gsk_… o sk-…';
    urlEl.value = cfg.base_url || '';
    modelEl.value = cfg.model || '';
    if (hintEl) {
      hintEl.textContent = cfg.api_key_configured
        ? `Clave guardada: ${cfg.api_key_masked || '••••••••'} (${cfg.fuente === 'base_datos' ? 'panel' : 'entorno'})`
        : 'Sin clave configurada. También puedes usar IA_API_KEY en .env.';
    }
    if (statusEl && !statusEl.dataset.busy) statusEl.textContent = '';
  } catch (e) {
    if (statusEl) statusEl.textContent = e.message || 'No se pudo cargar la configuración IA.';
  }
}

async function guardarCfgIa() {
  const keyEl = document.getElementById('cfg-ia-key');
  const urlEl = document.getElementById('cfg-ia-url');
  const modelEl = document.getElementById('cfg-ia-model');
  const statusEl = document.getElementById('cfg-ia-status');
  const body = {
    base_url: (urlEl?.value || '').trim(),
    model: (modelEl?.value || '').trim(),
  };
  const nuevaClave = (keyEl?.value || '').trim();
  if (nuevaClave) body.api_key = nuevaClave;
  if (statusEl) { statusEl.dataset.busy = '1'; statusEl.textContent = 'Guardando…'; }
  try {
    const res = await api('/configuracion/ia', {
      method: 'PUT',
      body,
    });
    if (keyEl) keyEl.value = '';
    toast('Configuración IA guardada');
    await loadCfgIa();
    if (statusEl) statusEl.textContent = res.api_key_configured
      ? `Listo. Clave ${res.api_key_masked || 'configurada'}.`
      : 'Guardado. Aún falta la API key.';
  } catch (e) {
    if (statusEl) statusEl.textContent = e.message || 'No se pudo guardar.';
    toast(e.message || 'Error al guardar IA', 'error');
  } finally {
    if (statusEl) delete statusEl.dataset.busy;
  }
}

function crearVistaConfiguracion() {
  const st = { page: 1, page_size: 20, total_pages: 1 };
  return createDataView('vista-configuracion', {
    state: st,
    autoLoad: false,
    buscar: { id: 'cfg-q', placeholder: 'Clave o descripción...' },
    columnas: [
      { key: 'clave', label: 'Clave', render: (c) => `<code>${esc(c.clave)}</code>` },
      { key: 'valor', label: 'Valor', render: (c) => esc(c.valor) },
      { key: 'descripcion', label: 'Descripción', render: (c) => esc(c.descripcion || '') },
    ],
    cargar: async () => {
      const items = (await api('/configuracion')).filter((c) => c.clave !== 'EMPRESA_LOGO' && !String(c.clave || '').startsWith('IA_'));
      const q = document.getElementById('cfg-q')?.value?.trim().toLowerCase();
      const filtradas = q ? items.filter((c) => `${c.clave} ${c.descripcion || ''}`.toLowerCase().includes(q)) : items;
      return { items: filtradas, total: filtradas.length };
    },
    resumen: (c) => `<div class="detail-grid">
      <div><strong>Descripción:</strong> ${esc(c.descripcion || '—')}</div>
      <div><strong>Valor:</strong> <code>${esc(c.valor)}</code></div>
    </div>`,
    titulo: (c) => c.clave,
    key: (c) => c.clave,
    acciones: {
      agregar: null,
      modificar: (row) => {
        uiModal({
          modo: 'Actualizar',
          tituloExtra: row.clave,
          campos: [
            { key: 'valor', label: row.clave, value: row.valor },
            { key: 'info', type: 'html', value: `<p class="meta">${esc(row.descripcion || '')}</p>` },
          ],
          onAceptar: async (v) => {
            await api(`/configuracion/${encodeURIComponent(row.clave)}`, {
              method: 'PUT', body: { valor: v.valor },
            });
            toast('Parámetro actualizado');
            await vistaConfiguracion.recargar();
          },
        });
      },
      eliminar: null,
    },
    bloqueadas: {
      agregar: 'Los parámetros los define el sistema.',
      eliminar: 'Los parámetros no se eliminan; solo se modifican.',
    },
    vacio: 'Sin parámetros',
  });
}

// ---------------------------------------------------------------------------
// Auditoría
// ---------------------------------------------------------------------------

let audState = { page: 1, page_size: 50, total_pages: 1 };

async function loadAuditoria() {
  await initAuditoriaFiltros();
  if (!validateDateRange('aud-desde', 'aud-hasta')) return;
  const q = new URLSearchParams();
  const entidad = document.getElementById('aud-entidad')?.value || '';
  const accion = document.getElementById('aud-accion')?.value || '';
  const email = document.getElementById('aud-email')?.value?.trim() || '';
  const entidadId = document.getElementById('aud-entidad-id')?.value || '';
  const desde = document.getElementById('aud-desde')?.value || '';
  const hasta = document.getElementById('aud-hasta')?.value || '';
  const texto = document.getElementById('aud-q')?.value?.trim() || '';
  audState.page_size = Number(document.getElementById('aud-limit')?.value || 50);
  if (entidad) q.set('entidad', entidad);
  if (accion) q.set('accion', accion);
  if (email) q.set('email', email);
  if (entidadId) q.set('entidad_id', entidadId);
  if (desde) q.set('desde', desde);
  if (hasta) q.set('hasta', hasta);
  if (texto) q.set('q', texto);
  q.set('limit', String(audState.page_size));
  q.set('page', String(audState.page));
  const res = await api(`/auditoria?${q}`);
  const rows = res.items || res;
  audState.total_pages = res.total_pages || 1;
  const count = document.getElementById('aud-count');
  if (count) count.textContent = `(${res.total ?? rows.length} evento${(res.total ?? rows.length) === 1 ? '' : 's'})`;
  const trunc = (s, n = 80) => {
    const t = String(s || '').trim();
    if (!t) return '—';
    return t.length > n ? `${esc(t.slice(0, n))}…` : esc(t);
  };
  document.getElementById('aud-body').innerHTML = rows.map((a) => {
    const detalle = a.valor_nuevo || a.valor_anterior || '';
    return `
    <tr>
      <td>${esc((a.fecha || '').slice(0, 19).replace('T', ' '))}</td>
      <td>${esc(a.email || '—')}</td>
      <td>${esc(a.entidad)}</td>
      <td class="col-id center">${a.entidad_id ?? '—'}</td>
      <td><code>${esc(a.accion)}</code></td>
      <td class="meta" title="${esc(detalle)}">${trunc(detalle, 90)}</td>
    </tr>`;
  }).join('') || '<tr><td colspan="6">Sin registros de auditoría.</td></tr>';
  const pager = document.getElementById('aud-pager');
  if (pager) {
    pager.innerHTML = `
      <button type="button" class="pager-btn" id="aud-prev" ${audState.page <= 1 ? 'disabled' : ''}>‹ Anterior</button>
      <span class="meta">Página ${audState.page} / ${audState.total_pages}</span>
      <button type="button" class="pager-btn" id="aud-next" ${audState.page >= audState.total_pages ? 'disabled' : ''}>Siguiente ›</button>`;
    document.getElementById('aud-prev')?.addEventListener('click', () => { if (audState.page > 1) { audState.page--; void loadAuditoria(); } });
    document.getElementById('aud-next')?.addEventListener('click', () => { if (audState.page < audState.total_pages) { audState.page++; void loadAuditoria(); } });
  }
}

async function initAuditoriaFiltros() {
  const selE = document.getElementById('aud-entidad');
  const selA = document.getElementById('aud-accion');
  if (!selE || selE.dataset.ready === '1') return;
  try {
    const cat = await api('/auditoria/filtros');
    const entidades = cat.entidades?.length
      ? cat.entidades
      : ['producto', 'pedido', 'inventario', 'cliente', 'objetivo', 'riesgo', 'usuario', 'rol'];
    selE.innerHTML = `<option value="">Todas</option>${entidades.map((e) => `<option value="${esc(e)}">${esc(e)}</option>`).join('')}`;
    if (selA) {
      selA.innerHTML = `<option value="">Todas</option>${(cat.acciones || []).map((a) => `<option value="${esc(a)}">${esc(a)}</option>`).join('')}`;
    }
    selE.dataset.ready = '1';
  } catch (_) {
    selE.innerHTML = `<option value="">Todas</option>
      <option value="producto">producto</option><option value="pedido">pedido</option>
      <option value="inventario">inventario</option><option value="cliente">cliente</option>`;
    selE.dataset.ready = '1';
  }
}

// ---------------------------------------------------------------------------
// Marketing portal B2B (pestañas: Banners | Promociones)
// ---------------------------------------------------------------------------

let vistasMarketing = {};

async function loadMarketing() {
  if (!vistasMarketing.banners) {
    const paneles = createTabsView('vista-marketing', [
      { id: 'banners', label: 'Banners' },
      { id: 'promociones', label: 'Promociones' },
      { id: 'carrusel', label: 'Carrusel inicio', onActivo: (el) => void renderCarruselPanel(el) },
    ]);
    vistasMarketing.banners = crearVistaBanners(paneles.banners);
    vistasMarketing.promociones = crearVistaPromos(paneles.promociones);
    vistasMarketing.carruselEl = paneles.carrusel;
  }
  await Promise.all([
    vistasMarketing.banners.recargar(),
    vistasMarketing.promociones.recargar(),
  ]);
  if (vistasMarketing.carruselEl) await renderCarruselPanel(vistasMarketing.carruselEl);
}

async function renderCarruselPanel(cont) {
  if (!cont) return;
  cont.innerHTML = '<p class="meta">Cargando productos del carrusel…</p>';
  try {
    const data = await api('/marketing/carrusel');
    const productos = data.productos || [];
    const ids = new Set(data.ids || []);
    cont.innerHTML = `
      <div class="card" style="margin:0">
        <div class="card-title">Productos en el carrusel del portal</div>
        <p class="meta">Marca hasta 12 productos. Si no eliges ninguno, el portal muestra automáticamente destacados (con descuento primero). Un solo producto = un slide.</p>
        <div class="mkt-carrusel-grid" style="display:grid;grid-template-columns:repeat(auto-fill,minmax(220px,1fr));gap:.5rem;max-height:420px;overflow:auto;margin:0.75rem 0">
          ${productos.map((p) => `
            <label class="mkt-carrusel-item" style="display:flex;gap:.5rem;align-items:flex-start;padding:.55rem;border:1px solid var(--border);border-radius:10px;background:#fffcfe;cursor:pointer;font-size:.8rem">
              <input type="checkbox" data-car-id="${p.id_producto}" ${ids.has(p.id_producto) ? 'checked' : ''} ${p.activo ? '' : 'disabled'}>
              <span><strong>${esc(p.nombre_producto)}</strong><br><span class="meta">#${p.id_producto}${p.activo ? '' : ' · inactivo'}</span></span>
            </label>`).join('') || '<p class="meta">Sin productos en catálogo.</p>'}
        </div>
        <button type="button" class="btn btn-primary" id="mkt-carrusel-save">Guardar carrusel</button>
      </div>`;
    cont.querySelector('#mkt-carrusel-save')?.addEventListener('click', async () => {
      const selected = [...cont.querySelectorAll('[data-car-id]:checked')].map((el) => Number(el.dataset.carId));
      await api('/marketing/carrusel', { method: 'PUT', body: { ids: selected } });
      toast(`Carrusel actualizado (${selected.length} producto${selected.length === 1 ? '' : 's'})`);
    });
  } catch (e) {
    cont.innerHTML = `<p class="meta" style="color:var(--loss)">${esc(e.message || 'Error')}</p>`;
  }
}

async function recargarMarketing() {
  if (!vistasMarketing.banners) return;
  await Promise.all([
    vistasMarketing.banners.recargar(),
    vistasMarketing.promociones.recargar(),
  ]);
}

function crearVistaBanners(cont) {
  const st = { page: 1, page_size: 15, total_pages: 1 };
  return createDataView(cont, {
    state: st,
    autoLoad: false,
    columnas: [
      { key: 'orden', label: 'Orden', align: 'num' },
      {
        key: 'preview', label: 'Vista', align: 'center',
        render: (b) => b.imagen_path
          ? `<img class="thumb" src="${esc((b.imagen_url || ('/media/' + b.imagen_path)))}" alt="" style="width:56px;height:36px;object-fit:cover;border-radius:6px">`
          : '—',
      },
      { key: 'titulo', label: 'Título' },
      { key: 'enlace', label: 'Enlace', render: (b) => b.enlace ? `<code>${esc(b.enlace)}</code>` : '—' },
      { key: 'activo', label: 'Visible', align: 'center', render: (b) => `
        <label class="gt-toggle" title="${b.activo ? 'Visible' : 'Oculto'}">
          <input type="checkbox" data-toggle-banner="${b.id_banner}" ${b.activo ? 'checked' : ''}>
          <span class="gt-toggle-slider"></span>
        </label>` },
    ],
    cargar: async () => {
      const banners = await api('/marketing/banners');
      return { items: banners, total: banners.length };
    },
    onAfterRender: (host) => {
      host.querySelectorAll('[data-toggle-banner]').forEach((inp) => {
        inp.addEventListener('change', async () => {
          const id = Number(inp.dataset.toggleBanner);
          const row = (await api('/marketing/banners')).find((b) => b.id_banner === id);
          if (!row) return;
          try {
            await api(`/marketing/banners/${id}`, {
              method: 'PUT',
              body: {
                titulo: row.titulo,
                imagen_path: row.imagen_path,
                enlace: row.enlace,
                orden: row.orden,
                activo: inp.checked,
              },
            });
            toast(inp.checked ? 'Banner visible en portal' : 'Banner oculto');
            await vistasMarketing.banners.recargar();
          } catch (e) {
            inp.checked = !inp.checked;
            toast(e.message || 'Error', 'error');
          }
        });
      });
    },
    filaClase: (b) => b.activo ? '' : 'row-inactive',
    resumen: (b) => `<div class="detail-grid">
      <div><strong>Orden:</strong> ${b.orden}</div>
      <div><strong>Enlace:</strong> ${esc(b.enlace || '—')}</div>
      <div><strong>Visible:</strong> ${b.activo ? 'Sí' : 'No'}</div>
      ${b.imagen_path ? `<div><img src="${esc(b.imagen_url || ('/media/' + b.imagen_path))}" alt="" style="max-width:100%;border-radius:10px;margin-top:.35rem"></div>` : ''}
    </div>`,
    titulo: (b) => b.titulo,
    key: (b) => b.id_banner,
    acciones: {
      agregar: () => void openBannerModal(),
      modificar: (row) => void openBannerModal(row),
      eliminar: async (row) => {
        await api(`/marketing/banners/${row.id_banner}`, { method: 'DELETE' });
        toast('Banner eliminado');
      },
    },
    vacio: 'Sin banners. Crea uno para la landing del portal.',
  });
}

function crearVistaPromos(cont) {
  const st = { page: 1, page_size: 15, total_pages: 1 };
  return createDataView(cont, {
    state: st,
    autoLoad: false,
    columnas: [
      { key: 'nombre', label: 'Nombre' },
      { key: 'descuento_pct', label: 'Descuento', align: 'num', render: (p) => `${Number(p.descuento_pct).toFixed(0)}%` },
      { key: 'fecha_inicio', label: 'Inicio', render: (p) => esc(p.fecha_inicio || '—') },
      { key: 'fecha_fin', label: 'Fin', render: (p) => esc(p.fecha_fin || '—') },
      { key: 'activa', label: 'Activa', align: 'center', render: (p) => `
        <label class="gt-toggle" title="${p.activa ? 'Activa' : 'Inactiva'}">
          <input type="checkbox" data-toggle-promo="${p.id_promocion}" ${p.activa ? 'checked' : ''}>
          <span class="gt-toggle-slider"></span>
        </label>` },
    ],
    cargar: async () => {
      const promos = await api('/marketing/promociones');
      return { items: promos, total: promos.length };
    },
    onAfterRender: (host) => {
      host.querySelectorAll('[data-toggle-promo]').forEach((inp) => {
        inp.addEventListener('change', async () => {
          const id = Number(inp.dataset.togglePromo);
          const row = (await api('/marketing/promociones')).find((p) => p.id_promocion === id);
          if (!row) return;
          try {
            await api(`/marketing/promociones/${id}`, {
              method: 'PUT',
              body: {
                nombre: row.nombre,
                descuento_pct: row.descuento_pct,
                fecha_inicio: row.fecha_inicio,
                fecha_fin: row.fecha_fin,
                activa: inp.checked,
              },
            });
            toast(inp.checked ? 'Promoción activa en portal' : 'Promoción desactivada');
            await vistasMarketing.promociones.recargar();
          } catch (e) {
            inp.checked = !inp.checked;
            toast(e.message || 'Error', 'error');
          }
        });
      });
    },
    filaClase: (p) => p.activa ? '' : 'row-inactive',
    resumen: (p) => `<div class="detail-grid">
      <div><strong>Descuento:</strong> ${Number(p.descuento_pct).toFixed(0)}%</div>
      <div><strong>Vigencia:</strong> ${esc(p.fecha_inicio || '—')} → ${esc(p.fecha_fin || '—')}</div>
      <div><strong>Activa:</strong> ${p.activa ? 'Sí' : 'No'}</div>
    </div>`,
    titulo: (p) => p.nombre,
    key: (p) => p.id_promocion,
    acciones: {
      agregar: () => void openPromoModal(),
      modificar: (row) => void openPromoModal(row),
      eliminar: async (row) => {
        await api(`/marketing/promociones/${row.id_promocion}`, { method: 'DELETE' });
        toast('Promoción eliminada');
      },
    },
    vacio: 'Sin promociones. Crea p.ej. «Bienvenida» con % de descuento.',
  });
}

async function subirImagenBanner(file) {
  const fd = new FormData();
  fd.append('file', file);
  const res = await fetch('/api/marketing/banners/imagen', { method: 'POST', body: fd });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.detail || 'No se pudo subir la imagen.');
  return data.ruta;
}

function openBannerModal(existing) {
  const isEdit = Boolean(existing?.id_banner);
  uiModal({
    modo: isEdit ? 'Actualizar' : 'Agregar',
    tituloExtra: 'Banner del portal',
    campos: [
      { key: 'titulo', label: 'Título', value: existing?.titulo || '' },
      { key: 'imagen', label: 'Imagen (JPG/PNG/WEBP)', type: 'file' },
      ...(existing?.imagen_path ? [{ key: 'prev', type: 'html', value: `<p class="meta">Actual: <code>${esc(existing.imagen_path)}</code></p>` }] : []),
      { key: 'enlace', label: 'Enlace', value: existing?.enlace || '/pages/catalogo.html' },
      { key: 'orden', label: 'Orden', type: 'number', value: existing?.orden ?? 1 },
      { key: 'activo', label: 'Visible en portal', type: 'checkbox', value: existing?.activo !== false },
    ],
    onAceptar: async (v) => {
      let imagen_path = existing?.imagen_path || null;
      if (v.imagen) imagen_path = await subirImagenBanner(v.imagen);
      const body = {
        titulo: v.titulo?.trim(),
        imagen_path,
        enlace: v.enlace?.trim() || null,
        orden: Number(v.orden || 0),
        activo: !!v.activo,
      };
      if (!body.titulo) { toast('Título requerido', 'error'); return false; }
      if (isEdit) {
        await api(`/marketing/banners/${existing.id_banner}`, { method: 'PUT', body });
        toast('Banner actualizado');
      } else {
        await api('/marketing/banners', { method: 'POST', body });
        toast('Banner creado');
      }
      await recargarMarketing();
    },
  });
}

function openPromoModal(existing) {
  const isEdit = Boolean(existing?.id_promocion);
  const hoy = new Date().toISOString().slice(0, 10);
  uiModal({
    modo: isEdit ? 'Actualizar' : 'Agregar',
    tituloExtra: isEdit ? existing.nombre : 'Nueva promoción',
    campos: [
      { key: 'nombre', label: 'Nombre', value: existing?.nombre || '' },
      { key: 'descuento_pct', label: 'Descuento (%)', type: 'number', step: '0.1', min: 0, value: existing?.descuento_pct ?? 10 },
      { key: 'fecha_inicio', label: 'Fecha inicio', type: 'date', value: (existing?.fecha_inicio || hoy).slice(0, 10) },
      { key: 'fecha_fin', label: 'Fecha fin', type: 'date', value: (existing?.fecha_fin || hoy).slice(0, 10) },
      { key: 'activa', label: 'Activa en portal', type: 'checkbox', value: existing?.activa !== false },
    ],
    onAceptar: async (v) => {
      const body = {
        nombre: v.nombre.trim(),
        descuento_pct: Number(v.descuento_pct || 0),
        fecha_inicio: v.fecha_inicio,
        fecha_fin: v.fecha_fin,
        activa: !!v.activa,
      };
      if (!body.nombre) { toast('Nombre requerido', 'error'); return false; }
      if (isEdit) {
        await api(`/marketing/promociones/${existing.id_promocion}`, { method: 'PUT', body });
        toast('Promoción actualizada');
      } else {
        await api('/marketing/promociones', { method: 'POST', body });
        toast('Promoción creada');
      }
      await recargarMarketing();
    },
  });
}

// ---------------------------------------------------------------------------
// Operaciones
// ---------------------------------------------------------------------------

async function loadOperaciones() {
  let data;
  try { data = await api('/dashboard/operaciones'); } catch (e) { toast(e.message || 'No se pudo cargar el panel', 'error'); return; }
  const k = data.kpis || {};
  const money = (v) => erpMoney(v);
  const kpiCard = (label, value, hint = '', extra = '') =>
    `<div class="kpi-card"><div class="label">${esc(label)}</div><div class="value ${extra}">${value}</div>${hint ? `<div class="kpi-hint">${esc(hint)}</div>` : ''}</div>`;
  document.getElementById('oper-kpis').innerHTML = [
    kpiCard('OC por aprobar', esc(k.oc_por_aprobar ?? 0), 'Órdenes en borrador'),
    kpiCard('OC por recibir', esc(k.oc_por_recibir ?? 0), 'Aprobadas o parciales'),
    kpiCard('Recepciones parciales', esc(k.oc_recibidas_parciales ?? 0), ''),
    kpiCard('Stock bajo', esc(k.stock_bajo ?? 0), '', (k.stock_bajo || 0) > 0 ? 'loss' : ''),
    kpiCard('Pedidos operativos', esc(k.pedidos_operativos ?? 0), ''),
    kpiCard('Sin despachar', esc(k.pedidos_sin_despachar ?? 0), ''),
    kpiCard('Caja (1101)', money(k.caja), 'Saldo disponible', (k.caja || 0) < 0 ? 'loss' : ''),
    kpiCard('Cuentas por pagar', money(k.cuentas_por_pagar), 'A proveedores'),
    kpiCard('Compras del mes', money(k.compras_del_periodo), ''),
    kpiCard('Ventas del mes', money(k.ventas_del_periodo), ''),
  ].join('');

  const alertas = data.alertas_stock || [];
  document.getElementById('op-stock-body').innerHTML = alertas.map((a) => `
    <tr><td>${esc(a.producto)}</td><td class="num">${fmtQty(a.disponible)}</td><td class="num">${fmtQty(a.umbral_minimo)}</td></tr>
  `).join('') || '<tr><td colspan="3">Sin alertas de stock</td></tr>';

  const ped = data.pedidos || [];
  document.getElementById('op-pedidos-body').innerHTML = ped.map((p) => `
    <tr><td>${esc(p.numero ?? p.id_pedido)}</td><td>${esc(p.empresa || '')}</td><td>${badge(p.estado_pedido)}</td>
    <td>${p.tiene_envio ? badge(p.estado_envio) : '<span class="meta">Sin envío</span>'}</td><td>${esc(p.transportista || '—')}</td></tr>
  `).join('') || '<tr><td colspan="5">Sin pedidos</td></tr>';
}

// ---------------------------------------------------------------------------
// Registro de páginas y eventos
// ---------------------------------------------------------------------------

PAGES.pedidos = { title: 'Pedidos', load: loadPedidosERP };
PAGES.catalogo = { title: 'Catálogo', load: loadCatalogo };
PAGES.inventario = { title: 'Inventario', load: loadInventario };
PAGES.compras = { title: 'Compras', load: loadCompras };
PAGES.operaciones = { title: 'Operaciones', load: loadOperaciones };
PAGES.clientes = { title: 'Clientes', load: loadClientesERP };
PAGES.marketing = { title: 'Marketing portal', load: loadMarketing };
PAGES.rentabilidad = { title: 'Rentabilidad', load: loadRentabilidad };
PAGES.logistica = { title: 'Logística', load: loadLogistica };
PAGES.configuracion = { title: 'Configuración', load: loadConfiguracion };
PAGES.auditoria = { title: 'Auditoría', load: loadAuditoria };
PAGES.finanzas = { title: 'Finanzas', load: loadFinanzas };

document.getElementById('rent-search')?.addEventListener('click', () => { rentState.page = 1; loadRentabilidad(); });
wireSimplePager(document.getElementById('rent-pager'), rentState, loadRentabilidad);

document.getElementById('ped-search')?.addEventListener('click', () => { pedState.page = 1; loadPedidosERP(); });
document.getElementById('ped-q')?.addEventListener('keydown', (e) => { if (e.key === 'Enter') { pedState.page = 1; loadPedidosERP(); } });
document.getElementById('ped-estado')?.addEventListener('change', () => { pedState.page = 1; loadPedidosERP(); });
wireSimplePager(document.getElementById('ped-pager'), pedState, loadPedidosERP);

document.getElementById('aud-search')?.addEventListener('click', () => { audState.page = 1; void loadAuditoria(); });
document.getElementById('aud-clear')?.addEventListener('click', () => {
  audState.page = 1;
  ['aud-entidad', 'aud-accion', 'aud-email', 'aud-entidad-id', 'aud-desde', 'aud-hasta', 'aud-q'].forEach((id) => {
    const el = document.getElementById(id);
    if (el) el.value = '';
  });
  const lim = document.getElementById('aud-limit');
  if (lim) lim.value = '50';
  capDateInputs(document.getElementById('page-auditoria'));
  void loadAuditoria();
});

document.getElementById('fin-refresh')?.addEventListener('click', () => loadFinanzas(true));
document.getElementById('fin-regularizar-caja')?.addEventListener('click', async () => {
  if (!confirm('¿Regularizar Caja (1101) a $0?\nSe creará un asiento de aporte/retiro contra Pagos externos (3001).')) return;
  try {
    const r = await api('/contabilidad/regularizar-caja?saldo_objetivo=0&nota=Regularizaci%C3%B3n%20manual%20desde%20Finanzas', { method: 'POST' });
    if (r.ajustado) toast(`Caja ajustada: ${erpMoney(r.saldo_anterior)} → ${erpMoney(r.saldo_nuevo)}`);
    else toast(r.detalle || 'Sin cambios');
    await loadFinanzas(false);
  } catch (e) {
    toast(e.message || 'No se pudo regularizar', 'error');
  }
});

document.getElementById('cfg-logo-upload')?.addEventListener('click', () => {
  document.getElementById('cfg-logo-file')?.click();
});
document.getElementById('cfg-logo-file')?.addEventListener('change', async (e) => {
  const file = e.target.files?.[0];
  e.target.value = '';
  if (!file) return;
  try {
    const ruta = await subirLogoEmpresa(file);
    renderCfgLogoPreview(ruta);
    if (typeof applyBrandLogo === 'function') await applyBrandLogo();
    toast('Logo actualizado — visible en el panel y PDF');
  } catch (err) {
    toast(err.message || 'Error al subir logo', 'error');
  }
});
document.getElementById('cfg-logo-clear')?.addEventListener('click', async () => {
  if (!confirm('¿Quitar el logo de los comprobantes?')) return;
  try {
    await api('/configuracion/logo', { method: 'DELETE' });
    renderCfgLogoPreview('');
    toast('Logo eliminado');
    loadConfiguracion();
  } catch (err) {
    toast(err.message || 'Error', 'error');
  }
});

document.getElementById('cfg-save-ia')?.addEventListener('click', () => { void guardarCfgIa(); });

document.getElementById('cfg-test-ia')?.addEventListener('click', async () => {
  const el = document.getElementById('cfg-ia-status');
  const btn = document.getElementById('cfg-test-ia');
  if (btn) btn.disabled = true;
  if (el) { el.dataset.busy = '1'; el.textContent = 'Probando conexión…'; }
  try {
    const res = await api('/configuracion/test-ia', { method: 'POST' });
    if (res.estado === 'ok') {
      if (el) el.innerHTML = `Conexión OK · modelo <code>${esc(res.modelo || '')}</code>`;
      toast('IA conectada correctamente');
    } else if (res.estado === 'sin_configurar') {
      if (el) el.textContent = res.detalle || 'IA sin configurar';
      toast(res.detalle || 'IA sin configurar', 'error');
    } else {
      if (el) el.textContent = res.detalle || 'Error de conexión IA';
      toast(res.detalle || 'Error IA', 'error');
    }
  } catch (e) {
    if (el) el.textContent = e.message || 'Error';
    toast(e.message, 'error');
  } finally {
    if (el) delete el.dataset.busy;
    if (btn) btn.disabled = false;
  }
});

bootApp();
