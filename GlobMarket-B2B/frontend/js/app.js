/* GlobMarket B2B — frontend JS (sin frameworks) */

const API_BASE = ''; // mismo origen (FastAPI sirve frontend)
const TOKEN_KEY = 'globmarket_token';

/** Traducción visual de nombres (BD puede quedar en inglés). */
const NOMBRE_PRODUCTO_ES = {
  'Organic Baby Cereal — Oat & Banana': 'Cereal infantil orgánico — avena y plátano',
  'Baby Fruit Purée Pouches — Apple & Pear': 'Pouches de puré de fruta — manzana y pera',
  'Infant Formula — Premium Milk Powder': 'Fórmula infantil premium en polvo',
  'Sparkling Water — Lime (24-pack)': 'Agua con gas sabor lima (caja x24)',
  'Cold Brew Coffee — Original (12-pack)': 'Café cold brew original (caja x12)',
  'Orange Juice — 1L (12-pack)': 'Jugo de naranja 1 L (caja x12)',
  'Whole Grain Oats — 1kg': 'Avena integral 1 kg',
  'Corn Flakes — Family Pack': 'Hojuelas de maíz — pack familiar',
  'Granola — Nuts & Honey': 'Granola con frutos secos y miel',
  'Basic Cotton T-Shirts — 12 units': 'Camisetas de algodón básicas (12 u.)',
  'Workwear Polo Shirts — 10 units': 'Polos de trabajo resistentes (10 u.)',
  'Eco Cotton Hoodies — 6 units': 'Sudaderas de algodón ecológico (6 u.)',
  'Moisturizing Face Cream — 50ml (24 units)': 'Crema hidratante facial 50 ml (24 u.)',
  'Lip Balm — Shea Butter (48 units)': 'Bálsamo labial karité (48 u.)',
  'Micellar Water — 400ml (12 units)': 'Agua micelar 400 ml (12 u.)',
  'Fresh Apples — Premium (20kg crate)': 'Manzanas premium (caja 20 kg)',
  'Bananas — Export Grade (18kg box)': 'Banano grado exportación (caja 18 kg)',
  'Oranges — Valencia (15kg box)': 'Naranjas Valencia (caja 15 kg)',
  'Dish Soap — Citrus (12 units)': 'Detergente lavaloza cítrico (12 u.)',
  'Laundry Detergent — 3L (6 units)': 'Detergente líquido ropa 3 L (6 u.)',
  'Paper Towels — 12 rolls': 'Toallas de papel (12 rollos)',
  'Frozen Beef Strips — 10kg': 'Tiras de res congeladas 10 kg',
  'Chicken Breast — Frozen (10kg)': 'Pechuga de pollo congelada 10 kg',
  'Pork Ribs — Frozen (12kg)': 'Costillas de cerdo congeladas 12 kg',
  'A4 Copy Paper — 5 reams': 'Papel bond A4 (5 resmas)',
  'Ballpoint Pens — 100 units': 'Bolígrafos (100 u.)',
  'Desk Notebooks — 50 units': 'Cuadernos de escritorio (50 u.)',
  'Shampoo — Daily Care (12 units)': 'Shampoo uso diario (12 u.)',
  'Toothpaste — Mint (24 units)': 'Pasta dental menta (24 u.)',
  'Hand Soap — Aloe (24 units)': 'Jabón de manos aloe (24 u.)',
  'Mixed Nuts — 1kg (10 units)': 'Mix de frutos secos 1 kg (10 u.)',
  'Potato Chips — Sea Salt (24 units)': 'Papas fritas sal de mar (24 u.)',
  'Protein Bars — Chocolate (24 units)': 'Barras proteicas chocolate (24 u.)',
  'Frozen Mixed Vegetables — 10kg': 'Verduras mixtas congeladas 10 kg',
  'Tomatoes — Roma (15kg box)': 'Tomates Roma (caja 15 kg)',
  'Onions — Yellow (20kg sack)': 'Cebolla amarilla (saco 20 kg)',
};

function nombreProductoEs(nombre) {
  return NOMBRE_PRODUCTO_ES[nombre] || nombre;
}

/** Badge de categoría con color distinto por tipo (clave = nombre en español del API). */
const ESTILO_BADGE_CATEGORIA = {
  'Alimentos para bebé': 'bg-rose-100 text-rose-800 border-rose-200',
  Bebidas: 'bg-sky-100 text-sky-800 border-sky-200',
  Cereales: 'bg-amber-100 text-amber-900 border-amber-200',
  Ropa: 'bg-violet-100 text-violet-800 border-violet-200',
  Cosméticos: 'bg-pink-100 text-pink-800 border-pink-200',
  Frutas: 'bg-orange-100 text-orange-800 border-orange-200',
  Hogar: 'bg-teal-100 text-teal-800 border-teal-200',
  Carnes: 'bg-red-100 text-red-800 border-red-200',
  'Suministros de oficina': 'bg-slate-100 text-slate-800 border-slate-300',
  'Cuidado personal': 'bg-cyan-100 text-cyan-900 border-cyan-200',
  Snacks: 'bg-yellow-100 text-yellow-900 border-yellow-200',
  Verduras: 'bg-lime-100 text-lime-900 border-lime-200',
};

const ESTILO_BADGE_CATEGORIA_FALLBACK = [
  'bg-indigo-100 text-indigo-800 border-indigo-200',
  'bg-fuchsia-100 text-fuchsia-800 border-fuchsia-200',
  'bg-emerald-100 text-emerald-800 border-emerald-200',
];

function claseBadgeCategoria(producto) {
  const nombre = producto.categoria;
  if (ESTILO_BADGE_CATEGORIA[nombre]) return ESTILO_BADGE_CATEGORIA[nombre];
  const idx = Math.max(0, (Number(producto.id_item_type) || 1) - 1) % ESTILO_BADGE_CATEGORIA_FALLBACK.length;
  return ESTILO_BADGE_CATEGORIA_FALLBACK[idx];
}

function htmlBadgeCategoria(producto) {
  const cls = claseBadgeCategoria(producto);
  return `<span class="inline-flex items-center px-2 py-0.5 rounded-lg border text-xs font-semibold ${cls}">${escapeHtml(producto.categoria)}</span>`;
}

const HTML_IMAGEN_NO_DISPONIBLE = `
  <div class="flex flex-col items-center justify-center gap-2 text-slate-500 p-4 text-center">
    <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16Z"/></svg>
    <div class="text-sm font-semibold">Imagen no disponible</div>
  </div>`;

/** Si falla Unsplash en BD, intenta respaldo único por producto antes del placeholder. */
function gmImagenFallback(img) {
  const fb = img.getAttribute('data-fallback');
  if (!img.dataset.intentoRespaldo && fb) {
    img.dataset.intentoRespaldo = '1';
    img.src = fb;
    return;
  }
  img.style.display = 'none';
  const cont = img.parentElement;
  if (cont) {
    cont.classList.add('flex', 'items-center', 'justify-center');
    cont.innerHTML = HTML_IMAGEN_NO_DISPONIBLE;
  }
}
window.gmImagenFallback = gmImagenFallback;

function etiquetaImagenProducto(p, className) {
  const src = escapeHtml(p.imagen_url || '');
  const alt = escapeHtml(nombreProductoEs(p.nombre_producto));
  const fb = `https://picsum.photos/seed/globmarket-${p.id_producto}/900/600`;
  return `<img src="${src}" alt="${alt}" loading="lazy" class="${className}" data-fallback="${fb}" onerror="gmImagenFallback(this)">`;
}

const CLASE_BTN_FILTRO =
  'w-full text-left px-4 py-3 rounded-xl border transition text-sm font-semibold';
const CLASE_BTN_FILTRO_ACTIVO =
  'border-2 border-blue-600 bg-blue-600 text-white shadow-md';
const CLASE_BTN_FILTRO_INACTIVO =
  'border-slate-200 bg-white text-slate-800 hover:border-blue-300 hover:bg-blue-50';

function qs(sel, el = document) {
  return el.querySelector(sel);
}
function qsa(sel, el = document) {
  return Array.from(el.querySelectorAll(sel));
}

function getToken() {
  return localStorage.getItem(TOKEN_KEY);
}
function setToken(token) {
  if (!token) localStorage.removeItem(TOKEN_KEY);
  else localStorage.setItem(TOKEN_KEY, token);
}

function formatUsd(value) {
  try {
    return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format(value);
  } catch {
    return `$${Number(value).toFixed(2)}`;
  }
}

function showToast(type, message) {
  const container = qs('#toast-container');
  if (!container) return;

  const bg = type === 'success' ? 'bg-emerald-600' : type === 'error' ? 'bg-rose-600' : 'bg-slate-800';
  const el = document.createElement('div');
  el.className = `${bg} text-white px-4 py-3 rounded-xl shadow-lg border border-white/10 max-w-md`;
  el.innerHTML = `
    <div class="flex gap-3 items-start">
      <div class="flex-1 text-sm leading-5">${escapeHtml(message)}</div>
      <button class="text-white/80 hover:text-white transition" aria-label="Cerrar">✕</button>
    </div>
  `;
  qs('button', el).addEventListener('click', () => el.remove());
  container.appendChild(el);
  setTimeout(() => el.remove(), 4500);
}

/** Mensaje de retroalimentacion en linea dentro de un formulario.
 *  type: 'error' | 'success' | 'info'. Sin message => se oculta. */
function setInlineMessage(id, type, message) {
  const el = document.getElementById(id);
  if (!el) return;
  if (!message) {
    el.className = 'hidden';
    el.textContent = '';
    return;
  }
  const estilos = {
    error: 'border-rose-200 bg-rose-50 text-rose-700',
    success: 'border-emerald-200 bg-emerald-50 text-emerald-700',
    info: 'border-slate-200 bg-slate-50 text-slate-700',
  };
  const icono = { error: 'alert-circle', success: 'check-circle-2', info: 'info' }[type] || 'info';
  el.className = `flex items-start gap-2 rounded-xl border px-4 py-3 text-sm ${estilos[type] || estilos.info}`;
  el.innerHTML = `<i data-lucide="${icono}" class="h-4 w-4 mt-0.5 shrink-0"></i><span>${escapeHtml(message)}</span>`;
  if (window.lucide) window.lucide.createIcons();
}

function escapeHtml(str) {
  return String(str)
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#039;');
}

async function apiFetch(path, { method = 'GET', body, auth = false } = {}) {
  const headers = { 'Content-Type': 'application/json' };
  if (auth) {
    const token = getToken();
    if (token) headers.Authorization = `Bearer ${token}`;
  }

  const resp = await fetch(`${API_BASE}${path}`, {
    method,
    headers,
    body: body ? JSON.stringify(body) : undefined,
  });

  const text = await resp.text();
  let data = null;
  try {
    data = text ? JSON.parse(text) : null;
  } catch {
    data = null;
  }

  if (!resp.ok) {
    throw new Error(extraerMensajeError(data, resp.status));
  }
  return data;
}

/** Normaliza el "detail" de FastAPI a un texto legible.
 *  Puede venir como string (HTTPException), lista (errores 422) u objeto. */
function extraerMensajeError(data, status) {
  const d = data?.detail;
  if (typeof d === 'string') return d;
  if (Array.isArray(d)) {
    const partes = d
      .map((e) => (e && (e.msg || e.message)) || (typeof e === 'string' ? e : ''))
      .filter(Boolean);
    if (partes.length) return partes.join(' · ');
  }
  if (d && typeof d === 'object') {
    if (typeof d.message === 'string') return d.message;
  }
  if (typeof data?.message === 'string') return data.message;
  return `Error HTTP ${status}`;
}

function setButtonLoading(btn, isLoading, loadingLabel = 'Cargando...') {
  if (!btn) return;
  btn.disabled = !!isLoading;
  btn.dataset.originalLabel ??= btn.textContent;
  btn.textContent = isLoading ? loadingLabel : btn.dataset.originalLabel;
  btn.classList.toggle('opacity-70', !!isLoading);
  btn.classList.toggle('cursor-not-allowed', !!isLoading);
}

function initHeaderAuth() {
  const token = getToken();
  const loginBtn = qs('[data-nav-login]');
  const regBtn = qs('[data-nav-registro]');
  const logoutBtn = qs('[data-nav-logout]');

  if (!loginBtn || !regBtn || !logoutBtn) return;
  if (token) {
    loginBtn.classList.add('hidden');
    regBtn.classList.add('hidden');
    logoutBtn.classList.remove('hidden');
    logoutBtn.addEventListener('click', () => {
      setToken(null);
      showToast('success', 'Sesión cerrada.');
      window.location.href = '/';
    });
  } else {
    logoutBtn.classList.add('hidden');
    loginBtn.classList.remove('hidden');
    regBtn.classList.remove('hidden');
  }
}

async function loadCategoriasInto(el) {
  const data = await apiFetch('/api/productos/categorias');
  el.innerHTML = data
    .map(
      (c) => `
      <a href="/pages/catalogo.html?cat=${encodeURIComponent(c.id_item_type)}"
         class="gm-card group rounded-xl border border-slate-200 bg-white p-4 hover:border-blue-200 hover:shadow-md transition">
        <div class="flex items-center gap-3">
          <div class="h-10 w-10 rounded-xl bg-slate-50 border border-slate-200 flex items-center justify-center">
            <i data-lucide="package" class="h-5 w-5 text-blue-600"></i>
          </div>
          <div class="min-w-0">
            <div class="text-sm font-semibold text-slate-900 truncate">${escapeHtml(c.item_type)}</div>
            <div class="text-xs text-slate-500">Mayorista internacional</div>
          </div>
        </div>
      </a>
    `
    )
    .join('');

  if (window.lucide) window.lucide.createIcons();
}

function getQueryParam(name) {
  const url = new URL(window.location.href);
  return url.searchParams.get(name);
}

async function initLanding() {
  const grid = qs('#categorias-grid');
  if (!grid) return;
  const skeleton = Array.from({ length: 12 })
    .map(
      () => `
      <div class="rounded-xl border border-slate-200 bg-white p-4 animate-pulse">
        <div class="h-10 w-10 rounded-xl bg-slate-100"></div>
        <div class="mt-3 h-4 w-2/3 bg-slate-100 rounded"></div>
        <div class="mt-2 h-3 w-1/2 bg-slate-100 rounded"></div>
      </div>
    `
    )
    .join('');
  grid.innerHTML = skeleton;

  try {
    await loadCategoriasInto(grid);
  } catch (e) {
    grid.innerHTML = `
      <div class="col-span-full rounded-xl border border-rose-200 bg-rose-50 p-4 text-rose-700">
        No se pudieron cargar las categorías. Intenta nuevamente.
      </div>
    `;
  }
}

async function initCatalogo() {
  const sidebar = qs('#categorias-sidebar');
  const grid = qs('#productos-grid');
  const pager = qs('#productos-pager');
  if (!sidebar || !grid || !pager) return;

  const cat = getQueryParam('cat');
  let selectedCat = cat ? Number(cat) : null;
  let page = Number(getQueryParam('page') || '1');

  function updateUrl() {
    const url = new URL(window.location.href);
    if (selectedCat) url.searchParams.set('cat', String(selectedCat));
    else url.searchParams.delete('cat');
    url.searchParams.set('page', String(page));
    window.history.replaceState({}, '', url.toString());
  }

  sidebar.innerHTML = `
    <div class="animate-pulse space-y-3">
      ${Array.from({ length: 10 })
        .map(() => `<div class="h-10 rounded-xl bg-slate-100"></div>`)
        .join('')}
    </div>
  `;
  grid.innerHTML = `
    ${Array.from({ length: 12 })
      .map(
        () => `
        <div class="rounded-2xl border border-slate-200 bg-white overflow-hidden animate-pulse">
          <div class="h-44 bg-slate-100"></div>
          <div class="p-4">
            <div class="h-4 bg-slate-100 rounded w-3/4"></div>
            <div class="mt-2 h-3 bg-slate-100 rounded w-1/2"></div>
            <div class="mt-4 h-9 bg-slate-100 rounded"></div>
          </div>
        </div>
      `
      )
      .join('')}
  `;

  let cats = [];

  function renderSidebar() {
    if (!cats.length) return;
    const btnAllActive = selectedCat == null;
    sidebar.innerHTML = `
      <button data-cat="all" type="button" class="${CLASE_BTN_FILTRO} ${btnAllActive ? CLASE_BTN_FILTRO_ACTIVO : CLASE_BTN_FILTRO_INACTIVO}">
        Todas las categorías
      </button>
      <div class="mt-3 space-y-2">
        ${cats
          .map((c) => {
            const active = selectedCat != null && Number(selectedCat) === Number(c.id_item_type);
            return `
              <button data-cat="${c.id_item_type}" type="button" class="${CLASE_BTN_FILTRO} ${active ? CLASE_BTN_FILTRO_ACTIVO : CLASE_BTN_FILTRO_INACTIVO}">
                <span class="truncate block">${escapeHtml(c.item_type)}</span>
              </button>
            `;
          })
          .join('')}
      </div>
    `;

    qsa('button[data-cat]', sidebar).forEach((btn) => {
      btn.addEventListener('click', () => {
        const v = btn.dataset.cat;
        selectedCat = v === 'all' ? null : Number(v);
        page = 1;
        updateUrl();
        renderSidebar();
        render();
      });
    });
  }

  try {
    cats = await apiFetch('/api/productos/categorias');
    renderSidebar();
  } catch {
    sidebar.innerHTML = `
      <div class="rounded-xl border border-rose-200 bg-rose-50 p-4 text-rose-700">
        Error cargando categorías.
      </div>
    `;
  }

  async function render() {
    grid.innerHTML = `
      ${Array.from({ length: 12 })
        .map(
          () => `
          <div class="rounded-2xl border border-slate-200 bg-white overflow-hidden animate-pulse">
            <div class="h-44 bg-slate-100"></div>
            <div class="p-4">
              <div class="h-4 bg-slate-100 rounded w-3/4"></div>
              <div class="mt-2 h-3 bg-slate-100 rounded w-1/2"></div>
              <div class="mt-4 h-9 bg-slate-100 rounded"></div>
            </div>
          </div>
        `
        )
        .join('')}
    `;
    pager.innerHTML = '';

    try {
      const params = new URLSearchParams();
      params.set('page', String(page));
      params.set('page_size', '12');
      if (selectedCat) params.set('id_item_type', String(selectedCat));

      const data = await apiFetch(`/api/productos?${params.toString()}`);

      if (!data.items.length) {
        grid.innerHTML = `
          <div class="col-span-full rounded-2xl border border-slate-200 bg-white p-6">
            <div class="text-slate-900 font-semibold">No hay productos para este filtro.</div>
            <div class="text-sm text-slate-600 mt-1">Prueba otra categoría o vuelve a ver el catálogo completo.</div>
          </div>
        `;
        return;
      }

      grid.innerHTML = data.items
        .map(
          (p) => `
          <div class="gm-card group rounded-2xl border border-slate-200 bg-white overflow-hidden hover:border-blue-200 hover:shadow-md transition">
            <a href="/pages/producto.html?id=${encodeURIComponent(p.id_producto)}" class="block">
              <div class="h-44 bg-slate-50 overflow-hidden">
                ${etiquetaImagenProducto(p, 'h-full w-full object-cover group-hover:scale-[1.02] transition duration-200')}
              </div>
              <div class="p-4">
                <div class="mb-2">${htmlBadgeCategoria(p)}</div>
                <div class="text-sm font-semibold text-slate-900 line-clamp-2 min-h-[2.5rem]">${escapeHtml(nombreProductoEs(p.nombre_producto))}</div>
                <div class="mt-3 flex items-end justify-between gap-3">
                  <div>
                    <div class="text-xs text-slate-500">Mayorista</div>
                    <div class="text-base font-bold text-slate-900">${formatUsd(p.precio_mayorista)}</div>
                  </div>
                  <span class="inline-flex items-center gap-2 text-sm font-semibold text-blue-700">
                    Ver detalle
                    <i data-lucide="arrow-right" class="h-4 w-4"></i>
                  </span>
                </div>
              </div>
            </a>
          </div>
        `
        )
        .join('');

      pager.innerHTML = `
        <div class="flex items-center justify-between gap-3">
          <button id="prev-page" class="px-4 py-2 rounded-xl border border-slate-200 bg-white hover:border-blue-200 transition ${
            data.page <= 1 ? 'opacity-50 cursor-not-allowed' : ''
          }" ${data.page <= 1 ? 'disabled' : ''}>Anterior</button>
          <div class="text-sm text-slate-600">Página <span class="font-semibold text-slate-900">${data.page}</span> de <span class="font-semibold text-slate-900">${data.total_pages}</span></div>
          <button id="next-page" class="px-4 py-2 rounded-xl border border-slate-200 bg-white hover:border-blue-200 transition ${
            data.page >= data.total_pages ? 'opacity-50 cursor-not-allowed' : ''
          }" ${data.page >= data.total_pages ? 'disabled' : ''}>Siguiente</button>
        </div>
      `;

      qs('#prev-page', pager)?.addEventListener('click', () => {
        page = Math.max(1, page - 1);
        updateUrl();
        render();
      });
      qs('#next-page', pager)?.addEventListener('click', () => {
        page = page + 1;
        updateUrl();
        render();
      });

      if (window.lucide) window.lucide.createIcons();
    } catch (e) {
      grid.innerHTML = `
        <div class="col-span-full rounded-2xl border border-rose-200 bg-rose-50 p-6 text-rose-700">
          Error cargando productos: ${escapeHtml(e.message)}
        </div>
      `;
    }
  }

  updateUrl();
  render();
}

async function initProducto() {
  const wrap = qs('#producto-wrap');
  if (!wrap) return;
  const id = getQueryParam('id');
  if (!id) {
    wrap.innerHTML = `<div class="rounded-2xl border border-rose-200 bg-rose-50 p-6 text-rose-700">Falta el id del producto.</div>`;
    return;
  }

  wrap.innerHTML = `
    <div class="grid lg:grid-cols-2 gap-8">
      <div class="rounded-2xl border border-slate-200 bg-white overflow-hidden animate-pulse h-[420px]"></div>
      <div class="space-y-4">
        <div class="h-5 w-1/3 bg-slate-100 rounded animate-pulse"></div>
        <div class="h-7 w-3/4 bg-slate-100 rounded animate-pulse"></div>
        <div class="h-16 w-full bg-slate-100 rounded animate-pulse"></div>
        <div class="h-10 w-2/3 bg-slate-100 rounded animate-pulse"></div>
        <div class="h-12 w-full bg-slate-100 rounded animate-pulse"></div>
      </div>
    </div>
  `;

  try {
    const p = await apiFetch(`/api/productos/${encodeURIComponent(id)}`);
    const minQty = 10;

    wrap.innerHTML = `
      <div class="grid lg:grid-cols-2 gap-10 items-start">
        <div class="rounded-2xl border border-slate-200 bg-white overflow-hidden">
          <div class="bg-slate-50">
            ${etiquetaImagenProducto(p, 'h-[420px] w-full object-cover')}
          </div>
        </div>

        <div>
          <div class="inline-flex items-center gap-2">
            ${htmlBadgeCategoria(p)}
          </div>

          <h1 class="mt-3 text-3xl font-extrabold text-slate-900 tracking-tight">${escapeHtml(nombreProductoEs(p.nombre_producto))}</h1>
          <p class="mt-3 text-slate-600 leading-6">${escapeHtml(p.descripcion || 'Sin descripción disponible.')}</p>

          <div class="mt-6 grid sm:grid-cols-2 gap-4">
            <div class="rounded-2xl border border-slate-200 bg-white p-4">
              <div class="text-xs text-slate-500">Precio unitario</div>
              <div class="mt-1 text-2xl font-extrabold text-slate-900">${formatUsd(p.precio_unitario)}</div>
            </div>
            <div class="rounded-2xl border border-blue-200 bg-blue-50 p-4">
              <div class="text-xs text-blue-700">Precio mayorista</div>
              <div class="mt-1 text-2xl font-extrabold text-slate-900">${formatUsd(p.precio_mayorista)}</div>
            </div>
          </div>

          <div class="mt-6 rounded-2xl border border-slate-200 bg-white p-4">
            <div class="flex items-center justify-between gap-3">
              <div>
                <div class="text-sm font-semibold text-slate-900">Cantidad (mínimo mayorista)</div>
                <div class="text-xs text-slate-500">Mínimo recomendado: ${minQty} unidades</div>
              </div>
              <div class="flex items-center gap-2">
                <button id="qty-minus" class="h-10 w-10 rounded-xl border border-slate-200 bg-white hover:border-blue-200 transition">−</button>
                <input id="qty" type="number" min="${minQty}" value="${minQty}" class="h-10 w-20 rounded-xl border border-slate-200 bg-white px-3 text-center focus:outline-none focus:ring-2 focus:ring-blue-200">
                <button id="qty-plus" class="h-10 w-10 rounded-xl border border-slate-200 bg-white hover:border-blue-200 transition">+</button>
              </div>
            </div>
            <button id="add-cart" class="gm-press mt-4 w-full rounded-xl bg-blue-600 text-white px-4 py-3 font-semibold hover:bg-blue-700 transition">
              Agregar al carrito
            </button>
          </div>
        </div>
      </div>

      <div class="mt-12">
        <div class="flex items-center justify-between">
          <h2 class="text-xl font-extrabold text-slate-900">Relacionados</h2>
          <a href="/pages/catalogo.html?cat=${encodeURIComponent(p.id_item_type)}" class="text-sm font-semibold text-blue-700 hover:text-blue-800 transition">Ver categoría</a>
        </div>
        <div id="relacionados" class="mt-5 grid sm:grid-cols-2 lg:grid-cols-4 gap-4"></div>
      </div>
    `;

    qs('#qty-minus')?.addEventListener('click', () => {
      const input = qs('#qty');
      const v = Math.max(minQty, Number(input.value || minQty) - 1);
      input.value = String(v);
    });
    qs('#qty-plus')?.addEventListener('click', () => {
      const input = qs('#qty');
      const v = Number(input.value || minQty) + 1;
      input.value = String(v);
    });
    qs('#add-cart')?.addEventListener('click', () => {
      const qty = Number(qs('#qty')?.value || minQty);
      showToast('success', `Se agregaron ${qty} unidades a tu solicitud.`);
    });

    const relEl = qs('#relacionados');
    try {
      const params = new URLSearchParams({ id_item_type: String(p.id_item_type), page: '1', page_size: '4' });
      const rel = await apiFetch(`/api/productos?${params.toString()}`);
      const items = rel.items.filter((x) => x.id_producto !== p.id_producto);
      relEl.innerHTML = items
        .slice(0, 4)
        .map(
          (r) => `
          <a href="/pages/producto.html?id=${encodeURIComponent(r.id_producto)}" class="gm-card group rounded-2xl border border-slate-200 bg-white overflow-hidden hover:border-blue-200 hover:shadow-md transition">
            <div class="h-32 bg-slate-50 overflow-hidden">
              ${etiquetaImagenProducto(r, 'h-full w-full object-cover group-hover:scale-[1.02] transition duration-200')}
            </div>
            <div class="p-3">
              <div class="mb-1">${htmlBadgeCategoria(r)}</div>
              <div class="mt-1 text-sm font-semibold text-slate-900 line-clamp-2 min-h-[2.5rem]">${escapeHtml(nombreProductoEs(r.nombre_producto))}</div>
              <div class="mt-2 text-sm font-extrabold text-slate-900">${formatUsd(r.precio_mayorista)}</div>
            </div>
          </a>
        `
        )
        .join('');
    } catch {
      relEl.innerHTML = `<div class="col-span-full rounded-2xl border border-slate-200 bg-white p-4 text-sm text-slate-600">No se pudieron cargar relacionados.</div>`;
    }

    if (window.lucide) window.lucide.createIcons();
  } catch (e) {
    wrap.innerHTML = `<div class="rounded-2xl border border-rose-200 bg-rose-50 p-6 text-rose-700">Error cargando producto: ${escapeHtml(e.message)}</div>`;
  }
}

function initLogin() {
  const form = qs('#login-form');
  if (!form) return;
  const btn = qs('#login-submit');

  form.addEventListener('submit', async (ev) => {
    ev.preventDefault();
    setInlineMessage('login-msg', null);
    const email = qs('#email')?.value?.trim();
    const password = qs('#password')?.value;
    if (!email || !password) {
      setInlineMessage('login-msg', 'error', 'Completa tu email y contraseña.');
      showToast('error', 'Completa email y contraseña.');
      return;
    }

    setButtonLoading(btn, true, 'Ingresando...');
    try {
      const data = await apiFetch('/api/auth/login', { method: 'POST', body: { email, password } });
      setToken(data.access_token);
      setInlineMessage('login-msg', 'success', 'Sesión iniciada. Redirigiendo al catálogo...');
      showToast('success', 'Bienvenido a GlobMarket B2B.');
      window.location.href = '/pages/catalogo.html';
    } catch (e) {
      const msg = /401|credenciales|invalid|incorrect/i.test(e.message)
        ? 'Email o contraseña incorrectos. Verifica tus datos e inténtalo de nuevo.'
        : e.message;
      setInlineMessage('login-msg', 'error', msg);
      showToast('error', msg);
    } finally {
      setButtonLoading(btn, false);
    }
  });
}

function initRegistro() {
  const form = qs('#registro-form');
  if (!form) return;
  const btn = qs('#registro-submit');

  form.addEventListener('submit', async (ev) => {
    ev.preventDefault();
    const payload = {
      nombre_empresa: qs('#nombre_empresa')?.value?.trim(),
      email: qs('#email')?.value?.trim(),
      password: qs('#password')?.value,
      pais: qs('#pais')?.value?.trim(),
      telefono: qs('#telefono')?.value?.trim() || null,
      direccion: qs('#direccion')?.value?.trim() || null,
    };

    setInlineMessage('registro-msg', null);
    if (!payload.nombre_empresa || !payload.email || !payload.password || !payload.pais) {
      setInlineMessage('registro-msg', 'error', 'Completa los campos obligatorios marcados con *.');
      showToast('error', 'Completa los campos obligatorios.');
      return;
    }
    if (payload.password.length < 8) {
      setInlineMessage('registro-msg', 'error', 'La contraseña debe tener al menos 8 caracteres.');
      return;
    }

    setButtonLoading(btn, true, 'Creando cuenta...');
    try {
      await apiFetch('/api/auth/registro', { method: 'POST', body: payload });
      setInlineMessage('registro-msg', 'success', 'Cuenta creada correctamente. Redirigiendo al inicio de sesión...');
      showToast('success', 'Cuenta creada. Ahora puedes iniciar sesión.');
      setTimeout(() => (window.location.href = '/pages/login.html'), 900);
    } catch (e) {
      const msg = /existe|already|registrad/i.test(e.message)
        ? 'Ese email ya está registrado. Inicia sesión o usa otro correo.'
        : e.message;
      setInlineMessage('registro-msg', 'error', msg);
      showToast('error', msg);
    } finally {
      setButtonLoading(btn, false);
    }
  });
}

/** En escritorio (>=1024px) el panel de filtros siempre va desplegado;
 *  en movil queda colapsable con <summary>. */
function initFiltrosResponsive() {
  const det = document.getElementById('filtros');
  if (!det) return;
  const mq = window.matchMedia('(min-width: 1024px)');
  // En escritorio el panel va desplegado; en movil arranca colapsado.
  const apply = () => {
    det.open = mq.matches;
  };
  apply();
  mq.addEventListener('change', apply);
  if (window.lucide) window.lucide.createIcons();
}

document.addEventListener('DOMContentLoaded', () => {
  initHeaderAuth();
  initFiltrosResponsive();
  initLanding();
  initCatalogo();
  initProducto();
  initLogin();
  initRegistro();
});

