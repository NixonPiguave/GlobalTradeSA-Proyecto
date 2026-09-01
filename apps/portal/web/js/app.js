/* GlobMarket B2B — frontend JS (sin frameworks) */

const API_BASE = ''; // mismo origen (FastAPI sirve frontend)
const TOKEN_KEY = 'globmarket_token';

/** Valida teléfono (7–15 dígitos; el + y espacios no cuentan). */
function validarTelefono(tel) {
  if (tel == null || String(tel).trim() === '') return { ok: true, value: null };
  const t = String(tel).trim();
  if (t.length > 20) {
    return { ok: false, msg: 'Teléfono demasiado largo.' };
  }
  if (!/^[\d\s+\-().]+$/.test(t)) {
    return { ok: false, msg: 'Teléfono inválido.' };
  }
  const digits = t.replace(/\D/g, '');
  if (digits.length < 7 || digits.length > 15) {
    return { ok: false, msg: 'Ingresa un teléfono válido (7 a 15 dígitos).' };
  }
  return { ok: true, value: t };
}

/** Marca una notificación como leída; opcionalmente navega al enlace. */
async function followNotifLink(link, idNotif, onAfterMark) {
  const id = Number(idNotif);
  if (Number.isFinite(id) && id > 0) {
    try {
      await apiFetch(`/api/cuenta/notificaciones/${id}/leida`, { method: 'POST', auth: true });
      if (typeof onAfterMark === 'function') await onAfterMark(id);
    } catch (e) {
      if (typeof showToast === 'function') showToast('error', e.message || 'No se pudo marcar el aviso');
      return;
    }
  }
  if (link) {
    window.location.href = link.startsWith('/') ? link : `/${link.replace(/^\//, '')}`;
  }
}

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

/** Si falla la imagen del producto, muestra placeholder (sin picsum genérico). */
function gmImagenFallback(img) {
  img.style.display = 'none';
  const cont = img.parentElement;
  if (cont) {
    cont.classList.add('flex', 'items-center', 'justify-center');
    cont.innerHTML = HTML_IMAGEN_NO_DISPONIBLE;
  }
}
window.gmImagenFallback = gmImagenFallback;

function urlImagenProducto(url) {
  if (!url) return '';
  const s = String(url).trim();
  if (/^https?:\/\//i.test(s) || s.startsWith('/')) return s;
  return `/media/${s.replace(/^\/+/, '')}`;
}

function etiquetaImagenProducto(p, className) {
  const src = escapeHtml(urlImagenProducto(p.imagen_url || ''));
  const alt = escapeHtml(nombreProductoEs(p.nombre_producto));
  if (!src) {
    return `<div class="${className} flex items-center justify-center bg-slate-50">${HTML_IMAGEN_NO_DISPONIBLE}</div>`;
  }
  return `<img src="${src}" alt="${alt}" loading="lazy" class="${className}" onerror="gmImagenFallback(this)">`;
}

const CLASE_BTN_FILTRO =
  'w-full text-left px-3 py-2 rounded-lg border transition text-xs font-semibold';
const CLASE_BTN_FILTRO_ACTIVO =
  'border-violet-200 bg-violet-50 text-violet-900';
const CLASE_BTN_FILTRO_INACTIVO =
  'border-slate-200 bg-white/80 text-slate-700 hover:border-violet-200 hover:bg-violet-50/50';

const GM_PRECIO_MAX = 100;

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

/** Páginas públicas donde no debe forzarse redirect ni UI autenticada. */
function isPublicAuthPage() {
  const path = (window.location.pathname || '').toLowerCase();
  return path.includes('/pages/login') || path.includes('/pages/registro');
}

/** Limpia sesión local (incluye claves legacy). */
function clearSession() {
  setToken(null);
  try {
    localStorage.removeItem('gm_token');
    localStorage.removeItem('gt_token');
  } catch (_) { /* noop */ }
}

function redirectToLogin() {
  if (isPublicAuthPage()) return;
  window.location.href = '/pages/login.html';
}

const FX = { USD: 1, EUR: 0.92, PEN: 3.75, MXN: 17.2 };
let gmPrefs = { moneda_preferida: 'USD', notif_pedidos: true, notif_promociones: true, notif_stock: false };
try { window.gmPrefs = gmPrefs; } catch (_) { /* noop */ }

const LABELS_ES = {
  catalog: 'Productos',
  cart: 'Carrito',
  orders: 'Pedidos',
  account: 'Perfil',
  favorites: 'Favoritos',
  catalogs: 'Catálogos',
  logout: 'Salir',
  search: 'Buscar',
  outOfStock: 'Sin stock',
  lowStock: 'Poco stock',
  inStock: 'En stock',
  currencyNote: 'Precios mostrados en',
};

function t(key) {
  return LABELS_ES[key] || key;
}

function formatUsd(value) {
  const cur = (gmPrefs.moneda_preferida || 'USD').toUpperCase();
  const rate = FX[cur] || 1;
  const converted = Number(value) * rate;
  const locale = { USD: 'es-CL', EUR: 'es-ES', PEN: 'es-PE', MXN: 'es-MX' }[cur] || 'es-CL';
  try {
    return new Intl.NumberFormat(locale, {
      style: 'currency', currency: cur,
    }).format(converted);
  } catch {
    return `${cur} ${converted.toFixed(2)}`;
  }
}

function applyPreferenciasUI() {
  document.documentElement.lang = 'es';
  const chip = document.getElementById('gm-prefs-chip');
  if (chip) {
    chip.textContent = `${t('currencyNote')} ${gmPrefs.moneda_preferida || 'USD'}`;
    chip.hidden = false;
  }
}

async function loadPreferencias() {
  if (!getToken() || isPublicAuthPage()) return;
  try {
    const p = await apiFetch('/api/cuenta/preferencias', { auth: true });
    gmPrefs = { ...gmPrefs, ...p };
    try { window.gmPrefs = gmPrefs; } catch (_) { /* noop */ }
    applyPreferenciasUI();
  } catch (_) { /* opcional */ }
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
    if (!token) {
      redirectToLogin();
      throw new Error('Sesión expirada. Inicia sesión de nuevo.');
    }
    headers.Authorization = `Bearer ${token}`;
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

  if (resp.status === 401 && auth) {
    clearSession();
    redirectToLogin();
    throw new Error('Sesión expirada. Inicia sesión de nuevo.');
  }

  if (!resp.ok) {
    throw new Error(extraerMensajeError(data, resp.status));
  }
  return data;
}

/** Normaliza el "detail" de FastAPI a un texto legible.
 *  Puede venir como string (HTTPException), lista (errores 422) u objeto. */
function extraerMensajeError(data, status) {
  if (!data || typeof data !== 'object') return `Error HTTP ${status}`;

  if (typeof data.message === 'string' && data.message) {
    const d = data.detail;
    if (Array.isArray(d) && d.length) {
      const partes = d
        .map((e) => e?.msg_es || e?.msg || e?.message)
        .filter(Boolean);
      if (partes.length) return partes.join(' · ');
    }
    return data.message;
  }

  const d = data.detail;
  if (typeof d === 'string') return d;
  if (Array.isArray(d)) {
    const partes = d
      .map((e) => e?.msg_es || e?.msg || e?.message || (typeof e === 'string' ? e : ''))
      .filter(Boolean);
    if (partes.length) return partes.join(' · ');
  }
  if (d && typeof d === 'object') {
    if (typeof d.message === 'string') return d.message;
  }
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

function currentPortalPage() {
  const path = (window.location.pathname || '/').toLowerCase();
  if (path.includes('catalogo_paquete') || path.includes('/pages/catalogos')) return 'catalogos';
  if (path.includes('/pages/catalogo') || path.includes('/pages/producto')) return 'productos';
  if (path.includes('favoritos')) return 'favoritos';
  if (path.includes('mis-pedidos')) return 'pedidos';
  if (path.includes('perfil')) return 'perfil';
  if (path.includes('checkout')) return 'carrito';
  if (path.includes('login')) return 'login';
  if (path.includes('registro')) return 'registro';
  return 'home';
}

function ensurePortalChrome(brand = null) {
  const logged = !!getToken() && !isPublicAuthPage();
  const page = currentPortalPage();
  const logoHtml = brand?.logo_url
    ? `<img src="${escapeHtml(brand.logo_url)}" alt="Logo">`
    : `<span class="font-extrabold text-sm">GM</span>`;
  const nombre = brand?.nombre || 'GlobMarket B2B';
  const q0 = new URL(window.location.href).searchParams.get('q') || '';

  const link = (href, key, label, cta = false) => {
    const active = page === key ? 'gm-nav-active' : 'gm-nav-ghost';
    const cls = cta ? 'gm-nav-cta' : active;
    return `<a href="${href}" class="${cls} inline-flex items-center transition">${label}</a>`;
  };

  const guestLinks = `
    ${link('/pages/catalogo.html', 'productos', t('catalog'))}
    ${link('/pages/catalogos.html', 'catalogos', t('catalogs'))}
    ${link('/pages/login.html', 'login', 'Entrar')}
    ${link('/pages/registro.html', 'registro', 'Crear cuenta', true)}
  `;
  const authLinks = `
    ${link('/pages/catalogo.html', 'productos', t('catalog'))}
    ${link('/pages/catalogos.html', 'catalogos', t('catalogs'))}
    ${link('/pages/favoritos.html', 'favoritos', t('favorites'))}
    ${link('/pages/perfil.html', 'perfil', t('account'))}
    ${link('/pages/mis-pedidos.html', 'pedidos', t('orders'))}
    <div class="gm-notif-wrap relative">
      <button type="button" id="gm-notif-bell" class="gm-nav-ghost gm-notif-bell relative inline-flex items-center justify-center" title="Notificaciones" aria-label="Notificaciones">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" aria-hidden="true">
          <path d="M12 3a5.5 5.5 0 0 0-5.5 5.5v1.2c0 1.4-.4 2.7-1.2 3.8L4 15.5h16l-1.3-2c-.8-1.1-1.2-2.4-1.2-3.8V8.5A5.5 5.5 0 0 0 12 3Z" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round"/>
          <path d="M9.5 18.2a2.6 2.6 0 0 0 5 0" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/>
        </svg>
        <span id="gm-notif-count" class="gm-notif-dot" hidden></span>
      </button>
      <div id="gm-notif-panel" class="gm-notif-panel" role="dialog" aria-label="Notificaciones" hidden>
        <div class="gm-notif-head">
          <strong>Notificaciones</strong>
          <button type="button" id="gm-notif-leer" class="text-xs font-semibold text-blue-700">Marcar leídas</button>
        </div>
        <div id="gm-notif-list" class="gm-notif-list"><p class="gm-notif-empty">Sin avisos por ahora.</p></div>
      </div>
    </div>
    <button type="button" id="gm-cart-btn" class="gm-nav-ghost relative inline-flex items-center gap-2">
      ${t('cart')}
      <span id="gm-cart-badge" class="hidden absolute -top-2 -right-2 h-5 min-w-[1.25rem] px-1 rounded-full text-xs font-bold flex items-center justify-center">0</span>
    </button>
    <button type="button" data-nav-logout class="gm-nav-ghost">${t('logout')}</button>
  `;

  const html = `
    <div class="border-b border-slate-100 bg-slate-50">
      <div class="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8 py-1.5 text-[11px] text-slate-500 flex justify-between gap-3">
        <span>Portal de ventas · GLOBTRADE S.A.</span>
        <span id="gm-prefs-chip" hidden></span>
        <span>Desde 1 unidad · precio mayorista al alcanzar MOQ</span>
      </div>
    </div>
    <div class="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
      <div class="flex flex-wrap items-center gap-3 py-3">
        <a href="/" class="flex items-center gap-2.5 min-w-0 shrink-0">
          <div class="gm-logo-box h-9 w-9 rounded-lg flex items-center justify-center shrink-0">${logoHtml}</div>
          <div class="leading-tight min-w-0">
            <div class="gm-brand-title font-extrabold tracking-tight truncate">${escapeHtml(nombre)}</div>
            <div class="gm-brand-sub text-[11px] truncate">Portal de ventas</div>
          </div>
        </a>
        <form id="gm-global-search" class="gm-search-bar flex-1 min-w-[200px] order-3 sm:order-none w-full sm:w-auto" action="/pages/catalogo.html" method="get">
          <input name="q" type="search" value="${escapeHtml(q0)}" placeholder="Buscar por nombre de producto..." aria-label="Buscar productos" />
          <button type="submit">Buscar</button>
        </form>
        <nav class="flex items-center gap-1 ml-auto flex-wrap justify-end" aria-label="Principal">
          ${logged ? authLinks : guestLinks}
        </nav>
      </div>
    </div>`;

  let header = document.querySelector('body > header');
  if (!header) {
    header = document.createElement('header');
    document.body.prepend(header);
  }
  header.className = 'gm-header sticky top-0 z-40';
  header.innerHTML = html;

  header.querySelector('[data-nav-logout]')?.addEventListener('click', () => {
    clearSession();
    showToast('success', 'Sesión cerrada.');
    window.location.href = '/';
  });
  if (logged) initNotificacionesPortal();
}

function initNotificacionesPortal() {
  const bell = document.getElementById('gm-notif-bell');
  const panel = document.getElementById('gm-notif-panel');
  const list = document.getElementById('gm-notif-list');
  const countEl = document.getElementById('gm-notif-count');
  if (!bell || !panel || !list || bell.dataset.bound === '1') return;
  bell.dataset.bound = '1';

  list.addEventListener('click', (e) => {
    const item = e.target.closest('.gm-notif-item[data-id]');
    if (!item) return;
    e.preventDefault();
    e.stopPropagation();
    const link = item.dataset.link || '';
    void followNotifLink(link, item.dataset.id, async () => {
      if (!link) await refresh();
    });
  });
  list.addEventListener('keydown', (e) => {
    const item = e.target.closest('.gm-notif-item[data-id]');
    if (!item || (e.key !== 'Enter' && e.key !== ' ')) return;
    e.preventDefault();
    const link = item.dataset.link || '';
    void followNotifLink(link, item.dataset.id, async () => {
      if (!link) await refresh();
    });
  });

  async function refresh() {
    try {
      const data = await apiFetch('/api/cuenta/notificaciones', { auth: true });
      const n = Number(data.no_leidas || 0);
      if (countEl) {
        if (n > 0) {
          countEl.hidden = false;
          countEl.textContent = n > 99 ? '99+' : String(n);
        } else {
          countEl.textContent = '';
          countEl.hidden = true;
        }
      }
      const items = data.items || [];
      list.innerHTML = items.length
        ? items.map((it) => `
          <div class="gm-notif-item ${it.leida ? '' : 'unread'} gm-notif-click"
               data-id="${it.id_notif}" data-link="${escapeHtml(it.link || '')}" role="button" tabindex="0">
            <strong>${escapeHtml(it.titulo || '')}</strong>
            <div>${escapeHtml(it.cuerpo || '')}</div>
            <div class="meta">${escapeHtml(String(it.fecha || '').slice(0, 16).replace('T', ' '))}${it.link ? ' · Ver detalle →' : ''}</div>
          </div>`).join('')
        : '<p class="gm-notif-empty">Sin avisos por ahora.</p>';
    } catch (_) { /* opcional */ }
  }

  bell.addEventListener('click', (e) => {
    e.stopPropagation();
    const open = panel.hasAttribute('hidden');
    if (open) {
      panel.removeAttribute('hidden');
      panel.classList.add('open');
      void refresh();
    } else {
      panel.setAttribute('hidden', '');
      panel.classList.remove('open');
    }
  });
  document.addEventListener('click', () => {
    panel.setAttribute('hidden', '');
    panel.classList.remove('open');
  });
  panel.addEventListener('click', (e) => e.stopPropagation());
  document.getElementById('gm-notif-leer')?.addEventListener('click', async () => {
    try {
      await apiFetch('/api/cuenta/notificaciones/leer-todas', { method: 'POST', auth: true });
      void refresh();
    } catch (e) {
      showToast('error', e.message || 'No se pudieron marcar');
    }
  });
  void refresh();
  if (!window.__gmNotifTimer) {
    window.__gmNotifTimer = setInterval(() => {
      if (document.visibilityState === 'visible' && getToken()) void refresh();
    }, 60000);
  }
}

async function loadBranding() {
  try {
    return await apiFetch('/api/marketing/branding');
  } catch {
    return null;
  }
}

function initHeaderAuth() {
  // La navegación completa la arma ensurePortalChrome (evita botones que “desaparecen”).
  void loadBranding().then((brand) => {
    ensurePortalChrome(brand);
    if (window.GlobMarketCart?.refreshNav) window.GlobMarketCart.refreshNav();
  });
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
  if (!grid && !qs('#gm-carrusel')) return;

  // Marketing: promos + banners + carrusel de productos
  try {
    const home = await apiFetch('/api/marketing/home');
    renderHomePromos(home?.promociones || []);
    renderHomeBanners(home?.banners || []);
    renderHomeCarrusel(home?.carrusel || []);
  } catch {
    /* marketing opcional */
  }

  if (!grid) return;
  const skeleton = Array.from({ length: 8 })
    .map(
      () => `
      <div class="gm-card p-4 animate-pulse">
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

function renderHomePromos(promos) {
  const wrap = qs('#marketing-promos');
  const chips = qs('#promo-chips');
  if (!wrap || !chips) return;
  if (!promos.length) {
    wrap.classList.add('hidden');
    return;
  }
  wrap.classList.remove('hidden');
  chips.innerHTML = promos
    .map(
      (p) => `
      <span class="gm-promo-chip">
        <strong>${escapeHtml(p.nombre)}</strong>
        <span class="gm-promo-pct">−${Number(p.descuento_pct || 0).toFixed(0)}%</span>
      </span>`
    )
    .join('');
}

function renderHomeBanners(banners) {
  const sec = qs('#gm-banners');
  const grid = qs('#gm-banners-grid');
  if (!sec || !grid) return;
  const usable = (banners || []).filter((b) => b.imagen_url || b.titulo);
  if (!usable.length) {
    sec.classList.add('hidden');
    return;
  }
  sec.classList.remove('hidden');
  grid.innerHTML = usable
    .map(
      (b) => `
      <a href="${escapeHtml(b.enlace || '/pages/catalogo.html')}" class="gm-banner-tile">
        ${b.imagen_url ? `<img src="${escapeHtml(b.imagen_url)}" alt="" loading="lazy">` : ''}
        <div class="gm-banner-caption">${escapeHtml(b.titulo || '')}</div>
      </a>`
    )
    .join('');
}

function renderHomeCarrusel(items) {
  const track = qs('#gm-carrusel-track');
  const dots = qs('#gm-carrusel-dots');
  const root = qs('#gm-carrusel');
  if (!track || !root) return;
  const list = items || [];
  if (!list.length) {
    track.innerHTML = `
      <div class="gm-carrusel-slide gm-carrusel-empty">
        <div class="text-sm font-semibold" style="color:#3d4f6f">Configura el carrusel en Marketing digital</div>
        <div class="text-xs text-slate-500 mt-1">Admin → Comercial → Marketing digital → Carrusel inicio</div>
      </div>`;
    qs('#gm-car-prev')?.classList.add('hidden');
    qs('#gm-car-next')?.classList.add('hidden');
    if (dots) dots.innerHTML = '';
    return;
  }

  const logged = !!getToken();
  track.innerHTML = list
    .map((p, i) => {
      const precio = p.precio_rebajado != null ? p.precio_rebajado : p.precio_mayorista;
      const dto = Number(p.descuento_pct || 0);
      return `
        <a class="gm-carrusel-slide ${i === 0 ? 'is-active' : ''}" href="/pages/producto.html?id=${encodeURIComponent(p.id_producto)}" data-slide="${i}">
          <div class="gm-carrusel-img">${etiquetaImagenProducto(p, 'h-full w-full object-cover')}</div>
          <div class="gm-carrusel-body">
            <div class="gm-carrusel-meta">${escapeHtml(p.marca || '—')} · ${escapeHtml(p.linea || '—')}</div>
            <div class="gm-carrusel-title">${escapeHtml(nombreProductoEs(p.nombre_producto))}</div>
            <div class="gm-carrusel-price">
              ${logged ? formatUsd(precio) : 'Inicia sesión'}
              ${dto > 0 ? `<span class="gm-dto-badge">−${dto.toFixed(0)}%</span>` : ''}
            </div>
          </div>
        </a>`;
    })
    .join('');

  if (dots) {
    dots.innerHTML = list
      .map((_, i) => `<button type="button" class="gm-dot ${i === 0 ? 'is-active' : ''}" data-dot="${i}" aria-label="Slide ${i + 1}"></button>`)
      .join('');
  }

  let idx = 0;
  const go = (n) => {
    idx = (n + list.length) % list.length;
    track.querySelectorAll('.gm-carrusel-slide').forEach((el, i) => el.classList.toggle('is-active', i === idx));
    dots?.querySelectorAll('.gm-dot').forEach((el, i) => el.classList.toggle('is-active', i === idx));
  };

  qs('#gm-car-prev')?.addEventListener('click', () => go(idx - 1));
  qs('#gm-car-next')?.addEventListener('click', () => go(idx + 1));
  dots?.querySelectorAll('.gm-dot').forEach((d) => d.addEventListener('click', () => go(Number(d.dataset.dot))));

  const showNav = list.length > 1;
  qs('#gm-car-prev')?.classList.toggle('hidden', !showNav);
  qs('#gm-car-next')?.classList.toggle('hidden', !showNav);

  if (list.length > 1) {
    clearInterval(window.__gmCarTimer);
    window.__gmCarTimer = setInterval(() => go(idx + 1), 4500);
  }
}

/** Cinta informativa: bodega/macro-zona desde la que se sirve al cliente.
 *  El stock y el "agotado" del catálogo se calculan sobre esa red, no sobre el total global. */
function renderAvisoZona(data) {
  const grid = qs('#productos-grid');
  if (!grid || !grid.parentElement) return;
  let el = qs('#gm-aviso-zona');
  if (!data || !data.zona_label) { if (el) el.remove(); return; }
  if (!el) {
    el = document.createElement('div');
    el.id = 'gm-aviso-zona';
    el.className = 'col-span-full mb-4 flex flex-wrap items-center gap-2 rounded-xl border border-blue-200 bg-blue-50 px-4 py-3 text-sm text-blue-900';
    grid.parentElement.insertBefore(el, grid);
  }
  const bodega = data.bodega_asignada ? ` · Bodega ${escapeHtml(String(data.bodega_asignada))}` : '';
  el.innerHTML = `
    <i data-lucide="map-pin" class="h-4 w-4 shrink-0"></i>
    <span>Disponibilidad para <strong>${escapeHtml(String(data.zona_label))}</strong>${bodega}. Los productos sin stock en tu red aparecen como agotados.</span>`;
  if (window.lucide) window.lucide.createIcons();
}

async function initCatalogo() {
  const sidebar = qs('#categorias-sidebar');
  const grid = qs('#productos-grid');
  const pager = qs('#productos-pager');
  if (!sidebar || !grid || !pager) return;

  let favProductos = new Set();

  async function cargarFavProductos() {
    if (!getToken()) { favProductos = new Set(); return; }
    try {
      const items = await apiFetch('/api/wishlist', { auth: true });
      favProductos = new Set((items || []).map((i) => Number(i.id_producto)));
    } catch { favProductos = new Set(); }
  }

  function botonFavoritoProducto(idProducto) {
    const activo = favProductos.has(Number(idProducto));
    return `<button type="button" data-wish="${idProducto}" aria-pressed="${activo}"
      title="${activo ? 'Quitar de favoritos' : 'Guardar en favoritos'}"
      class="inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-lg border border-slate-200 bg-white text-lg leading-none transition hover:border-rose-200 hover:text-rose-500 ${activo ? 'text-rose-600' : 'text-slate-400'}">
      ${activo ? '&#9829;' : '&#9825;'}
    </button>`;
  }

  const cat = getQueryParam('cat');
  let selectedCat = cat ? Number(cat) : null;
  let selectedMarca = getQueryParam('marca') ? Number(getQueryParam('marca')) : null;
  let selectedLinea = getQueryParam('linea') ? Number(getQueryParam('linea')) : null;
  let precioMin = getQueryParam('pmin') ? Number(getQueryParam('pmin')) : null;
  let precioMax = getQueryParam('pmax') ? Number(getQueryParam('pmax')) : null;
  let page = Number(getQueryParam('page') || '1');
  let searchTerm = (getQueryParam('q') || '').trim();

  const searchInput = qs('#cat-q') || qs('#gm-global-search input[name="q"]');
  if (searchInput && searchTerm) searchInput.value = searchTerm;

  function updateUrl() {
    const url = new URL(window.location.href);
    if (selectedCat) url.searchParams.set('cat', String(selectedCat));
    else url.searchParams.delete('cat');
    if (selectedMarca) url.searchParams.set('marca', String(selectedMarca));
    else url.searchParams.delete('marca');
    if (selectedLinea) url.searchParams.set('linea', String(selectedLinea));
    else url.searchParams.delete('linea');
    if (precioMin != null && !Number.isNaN(precioMin) && precioMin > 0) url.searchParams.set('pmin', String(precioMin));
    else url.searchParams.delete('pmin');
    if (precioMax != null && !Number.isNaN(precioMax) && precioMax < GM_PRECIO_MAX) url.searchParams.set('pmax', String(precioMax));
    else url.searchParams.delete('pmax');
    if (searchTerm) url.searchParams.set('q', searchTerm);
    else url.searchParams.delete('q');
    url.searchParams.set('page', String(page));
    window.history.replaceState({}, '', url.toString());
  }

  qs('#cat-buscar')?.addEventListener('submit', (e) => {
    e.preventDefault();
    searchTerm = (searchInput?.value || '').trim();
    page = 1;
    updateUrl();
    render();
  });

  sidebar.innerHTML = `
    <div class="animate-pulse space-y-3 p-3">
      ${Array.from({ length: 6 }).map(() => `<div class="h-8 rounded-lg bg-slate-100"></div>`).join('')}
    </div>
  `;
  grid.innerHTML = `
    ${Array.from({ length: 9 })
      .map(
        () => `
        <div class="gm-card overflow-hidden animate-pulse">
          <div class="h-40 bg-slate-100"></div>
          <div class="p-3.5">
            <div class="h-4 bg-slate-100 rounded w-3/4"></div>
            <div class="mt-2 h-3 bg-slate-100 rounded w-1/2"></div>
            <div class="mt-4 h-8 bg-slate-100 rounded"></div>
          </div>
        </div>
      `
      )
      .join('')}
  `;

  let cats = [];

  function syncPriceLabels(a, b) {
    const la = qs('#lbl-pmin', sidebar);
    const lb = qs('#lbl-pmax', sidebar);
    if (la) la.textContent = `$${Number(a).toFixed(0)}`;
    if (lb) lb.textContent = Number(b) >= GM_PRECIO_MAX ? `$${GM_PRECIO_MAX}+` : `$${Number(b).toFixed(0)}`;
  }

  function renderSidebar() {
    if (!cats.length) return;
    const btnAllActive = selectedCat == null;
    const marcasHtml = (window.__gmMarcas || [])
      .map((m) => `<option value="${m.id_marca}" ${selectedMarca === Number(m.id_marca) ? 'selected' : ''}>${escapeHtml(m.nombre)}</option>`)
      .join('');
    const lineasHtml = (window.__gmLineas || [])
      .map((l) => `<option value="${l.id_linea}" ${selectedLinea === Number(l.id_linea) ? 'selected' : ''}>${escapeHtml(l.nombre)}</option>`)
      .join('');
    const pminVal = precioMin != null && !Number.isNaN(precioMin) ? Math.min(precioMin, GM_PRECIO_MAX) : 0;
    const pmaxVal = precioMax != null && !Number.isNaN(precioMax) ? Math.min(precioMax, GM_PRECIO_MAX) : GM_PRECIO_MAX;

    sidebar.innerHTML = `
      <div class="gm-filter-panel">
        <div class="text-sm font-bold mb-2" style="color:#3d4f6f">Afinar catálogo</div>
        <label>Marca</label>
        <select id="filtro-marca">
          <option value="">Todas</option>${marcasHtml}
        </select>
        <label>Línea</label>
        <select id="filtro-linea">
          <option value="">Todas</option>${lineasHtml}
        </select>
        <label>Rango de precio</label>
        <div class="gm-price-range">
          <div class="gm-price-labels">
            <span id="lbl-pmin">$${pminVal}</span>
            <span id="lbl-pmax">${pmaxVal >= GM_PRECIO_MAX ? '$' + GM_PRECIO_MAX + '+' : '$' + pmaxVal}</span>
          </div>
          <div class="gm-range-track">
            <input type="range" id="filtro-pmin" min="0" max="${GM_PRECIO_MAX}" step="1" value="${pminVal}" aria-label="Precio mínimo" />
            <input type="range" id="filtro-pmax" min="0" max="${GM_PRECIO_MAX}" step="1" value="${pmaxVal}" aria-label="Precio máximo" />
          </div>
        </div>
        <button type="button" id="filtro-aplicar" class="w-full">Aplicar</button>
        <button type="button" id="filtro-limpiar" class="w-full">Limpiar</button>
      </div>
      <div class="px-3 mt-2 text-xs font-bold uppercase tracking-wide text-slate-500 mb-1.5">Categorías</div>
      <div class="px-2 pb-3 space-y-1">
        <button data-cat="all" type="button" class="${CLASE_BTN_FILTRO} ${btnAllActive ? CLASE_BTN_FILTRO_ACTIVO : CLASE_BTN_FILTRO_INACTIVO}">
          Todas
        </button>
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

    const rMin = qs('#filtro-pmin', sidebar);
    const rMax = qs('#filtro-pmax', sidebar);
    const clampRanges = () => {
      let a = Number(rMin.value);
      let b = Number(rMax.value);
      if (a > b) { const t = a; a = b; b = t; rMin.value = a; rMax.value = b; }
      syncPriceLabels(a, b);
    };
    rMin?.addEventListener('input', clampRanges);
    rMax?.addEventListener('input', clampRanges);

    const applyFilters = () => {
      const headerQ = qs('#gm-global-search input[name="q"]');
      searchTerm = (headerQ?.value || searchInput?.value || '').trim();
      const m = qs('#filtro-marca', sidebar)?.value;
      const l = qs('#filtro-linea', sidebar)?.value;
      let a = Number(rMin?.value ?? 0);
      let b = Number(rMax?.value ?? GM_PRECIO_MAX);
      if (a > b) { const t = a; a = b; b = t; }
      selectedMarca = m ? Number(m) : null;
      selectedLinea = l ? Number(l) : null;
      precioMin = a > 0 ? a : null;
      precioMax = b < GM_PRECIO_MAX ? b : null;
      page = 1;
      updateUrl();
      render();
    };
    qs('#filtro-aplicar', sidebar)?.addEventListener('click', applyFilters);
    qs('#filtro-limpiar', sidebar)?.addEventListener('click', () => {
      selectedMarca = null; selectedLinea = null; precioMin = null; precioMax = null; searchTerm = ''; selectedCat = null;
      const headerQ = qs('#gm-global-search input[name="q"]');
      if (headerQ) headerQ.value = '';
      if (searchInput) searchInput.value = '';
      page = 1; updateUrl(); renderSidebar(); render();
    });

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
    try {
      window.__gmMarcas = await apiFetch('/api/productos/marcas');
      window.__gmLineas = await apiFetch('/api/productos/lineas');
    } catch { window.__gmMarcas = []; window.__gmLineas = []; }
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
      if (getToken()) await cargarFavProductos();
      const params = new URLSearchParams();
      params.set('page', String(page));
      params.set('page_size', '12');
      if (selectedCat) params.set('id_item_type', String(selectedCat));
      if (selectedMarca) params.set('id_marca', String(selectedMarca));
      if (selectedLinea) params.set('id_linea', String(selectedLinea));
      if (precioMin != null && !Number.isNaN(precioMin)) params.set('precio_min', String(precioMin));
      if (precioMax != null && !Number.isNaN(precioMax)) params.set('precio_max', String(precioMax));
      if (searchTerm) params.set('q', searchTerm);

      const data = await apiFetch(`/api/productos?${params.toString()}`, { auth: !!getToken() });
      renderAvisoZona(data);

      if (!data.items.length) {
        grid.innerHTML = `
          <div class="col-span-full rounded-2xl border border-slate-200 bg-white p-6">
            <div class="text-slate-900 font-semibold">No hay productos para este filtro.</div>
            <div class="text-sm text-slate-600 mt-1">Prueba otra categoría, marca o línea.</div>
          </div>
        `;
        return;
      }

      const logged = !!getToken();
      const zonaLabel = data.zona_label || '';
      grid.innerHTML = data.items
        .map(
          (p) => {
            const st = p.estado_stock || (Number(p.stock_disponible) <= 0 ? 'sin_stock' : (Number(p.stock_disponible) <= Number(p.stock_minimo || 10) ? 'poco_stock' : 'ok'));
            const badge = st === 'sin_stock'
              ? `<span class="absolute top-2 left-2 z-10 rounded-md bg-rose-600 text-white text-[10px] font-bold px-2 py-1 uppercase tracking-wide">Agotado${zonaLabel ? ' · ' + escapeHtml(zonaLabel) : ''}</span>`
              : st === 'poco_stock'
                ? '<span class="absolute top-2 left-2 z-10 rounded-md bg-amber-500 text-white text-[10px] font-bold px-2 py-1 uppercase tracking-wide">Poco stock</span>'
                : '';
            return `
          <div class="gm-card group rounded-xl border border-slate-200 bg-white overflow-hidden hover:border-amber-300 hover:shadow-md transition ${st === 'sin_stock' ? 'opacity-90' : ''}">
            <a href="/pages/producto.html?id=${encodeURIComponent(p.id_producto)}" class="block relative">
              ${badge}
              <div class="h-40 bg-slate-50 overflow-hidden">
                ${etiquetaImagenProducto(p, 'h-full w-full object-cover group-hover:scale-[1.02] transition duration-200')}
              </div>
              <div class="p-3.5">
                <div class="mb-1.5 flex flex-wrap gap-1 text-[10px] font-semibold uppercase tracking-wide text-slate-500">
                  <span class="px-1.5 py-0.5 rounded bg-slate-100">${escapeHtml(p.marca || '—')}</span>
                  <span class="px-1.5 py-0.5 rounded bg-slate-100">${escapeHtml(p.linea || '—')}</span>
                </div>
                <div class="text-sm font-semibold text-slate-900 line-clamp-2 min-h-[2.4rem]">${escapeHtml(nombreProductoEs(p.nombre_producto))}</div>
                <div class="mt-2 flex items-end justify-between gap-2">
                  <div>
                    <div class="text-[11px] text-slate-500">${logged ? 'Precio mayorista' : 'Inicia sesión para precio'}</div>
                    <div class="text-sm font-bold text-slate-900">${logged && p.precio_mayorista != null ? formatUsd(p.precio_rebajado != null ? p.precio_rebajado : p.precio_mayorista) : formatUsd(p.precio_unitario || 0)}</div>
                    ${!logged ? '<div class="text-[10px] text-amber-700 font-medium">Precio público · inicia sesión para mayorista</div>' : ''}
                    ${logged && Number(p.descuento_pct || 0) > 0 ? `<div class="text-[11px] font-semibold text-emerald-700">−${Number(p.descuento_pct).toFixed(0)}% vs mayorista · <span class="line-through text-slate-400 font-normal">${formatUsd(p.precio_mayorista)}</span></div>` : ''}
                  </div>
                  <span class="text-xs font-semibold text-slate-600">Mayorista ≥ ${escapeHtml(String(p.moq || 10))}</span>
                </div>
              </div>
            </a>
            <div class="px-3.5 pb-3.5 flex gap-2 items-center">
              <a href="/pages/producto.html?id=${encodeURIComponent(p.id_producto)}" class="flex-1 text-center text-xs font-semibold py-2 rounded-lg bg-slate-800 text-white">Ver</a>
              ${logged ? botonFavoritoProducto(p.id_producto) : ''}
            </div>
          </div>
        `;
          }
        )
        .join('');

      grid.querySelectorAll('[data-wish]').forEach((b) => {
        b.addEventListener('click', async (ev) => {
          ev.preventDefault();
          ev.stopPropagation();
          const id = Number(b.dataset.wish);
          const activo = b.getAttribute('aria-pressed') === 'true';
          try {
            if (activo) {
              await apiFetch(`/api/wishlist/${id}`, { method: 'DELETE', auth: true });
              favProductos.delete(id);
              b.innerHTML = '&#9825;';
              b.classList.remove('text-rose-600');
              b.classList.add('text-slate-400');
              b.setAttribute('aria-pressed', 'false');
              b.title = 'Guardar en favoritos';
              showToast('success', 'Quitado de favoritos');
            } else {
              await apiFetch('/api/wishlist', { method: 'POST', auth: true, body: { id_producto: id } });
              favProductos.add(id);
              b.innerHTML = '&#9829;';
              b.classList.remove('text-slate-400');
              b.classList.add('text-rose-600');
              b.setAttribute('aria-pressed', 'true');
              b.title = 'Quitar de favoritos';
              showToast('success', 'Guardado en favoritos');
            }
          } catch (err) {
            showToast('error', err.message);
          }
        });
      });
      const totalPages = data.total_pages || 1;
      const cur = data.page || 1;
      const windowPages = (() => {
        if (totalPages <= 7) return Array.from({ length: totalPages }, (_, i) => i + 1);
        const set = new Set([1, totalPages, cur, cur - 1, cur + 1]);
        const sorted = [...set].filter((p) => p >= 1 && p <= totalPages).sort((a, b) => a - b);
        const out = [];
        let prev = 0;
        sorted.forEach((p) => { if (prev && p - prev > 1) out.push('…'); out.push(p); prev = p; });
        return out;
      })();
      pager.innerHTML = `
        <div class="flex flex-wrap items-center justify-center gap-2">
          <button id="first-page" class="px-3 py-2 rounded-xl border border-slate-200 bg-white text-sm font-semibold ${cur <= 1 ? 'opacity-40 cursor-not-allowed' : ''}" ${cur <= 1 ? 'disabled' : ''} title="Primera">«</button>
          <button id="prev-page" class="px-3 py-2 rounded-xl border border-slate-200 bg-white text-sm font-semibold ${cur <= 1 ? 'opacity-40 cursor-not-allowed' : ''}" ${cur <= 1 ? 'disabled' : ''}>‹</button>
          ${windowPages.map((p) => p === '…'
            ? '<span class="px-1 text-slate-400">…</span>'
            : `<button type="button" data-goto="${p}" class="min-w-[2.5rem] px-3 py-2 rounded-xl text-sm font-semibold ${p === cur ? 'bg-slate-900 text-white' : 'border border-slate-200 bg-white hover:border-blue-200'}">${p}</button>`
          ).join('')}
          <button id="next-page" class="px-3 py-2 rounded-xl border border-slate-200 bg-white text-sm font-semibold ${cur >= totalPages ? 'opacity-40 cursor-not-allowed' : ''}" ${cur >= totalPages ? 'disabled' : ''}>›</button>
          <button id="last-page" class="px-3 py-2 rounded-xl border border-slate-200 bg-white text-sm font-semibold ${cur >= totalPages ? 'opacity-40 cursor-not-allowed' : ''}" ${cur >= totalPages ? 'disabled' : ''} title="Última">»</button>
          <span class="text-sm text-slate-500 ml-2">Página ${cur} de ${totalPages}</span>
        </div>
      `;

      qs('#first-page', pager)?.addEventListener('click', () => { page = 1; updateUrl(); render(); });
      qs('#prev-page', pager)?.addEventListener('click', () => { page = Math.max(1, page - 1); updateUrl(); render(); });
      qs('#next-page', pager)?.addEventListener('click', () => { page = Math.min(totalPages, page + 1); updateUrl(); render(); });
      qs('#last-page', pager)?.addEventListener('click', () => { page = totalPages; updateUrl(); render(); });
      pager.querySelectorAll('[data-goto]').forEach((b) => b.addEventListener('click', () => {
        page = Number(b.dataset.goto); updateUrl(); render();
      }));

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
    const p = await apiFetch(`/api/productos/${encodeURIComponent(id)}`, { auth: !!getToken() });
    const logged = !!getToken();
    const minQty = p.moq || 10;
    const stock = p.stock_disponible;
    const estado = p.estado_stock || (stock == null ? null : stock <= 0 ? 'sin_stock' : (p.stock_minimo != null && stock <= p.stock_minimo ? 'poco_stock' : 'ok'));
    const zonaSufijo = p.zona_label ? ` en ${p.zona_label}` : '';
    const stockLabel = estado === 'sin_stock' ? `Agotado${zonaSufijo}` : estado === 'poco_stock' ? `Poco stock${zonaSufijo}` : stock == null ? 'Consultar disponibilidad' : `En stock${zonaSufijo}`;
    const stockClass = estado === 'sin_stock' ? 'bg-rose-100 text-rose-800' : estado === 'poco_stock' ? 'bg-amber-100 text-amber-900' : stock == null ? 'bg-slate-100 text-slate-700' : 'bg-emerald-100 text-emerald-800';
    const sinStock = estado === 'sin_stock' || (stock != null && stock <= 0);
    const dtoPct = Number(p.descuento_pct || 0);
    const aplica = String(p.descuento_aplica_a || 'mayorista').toLowerCase();
    const precioMayoristaLista = logged ? Number(p.precio_mayorista || 0) : 0;
    const precioRetailLista = Number(p.precio_unitario || 0);
    const aplicaMayorista = dtoPct > 0 && (aplica === 'mayorista' || aplica === 'ambos');
    const aplicaRetail = dtoPct > 0 && (aplica === 'retail' || aplica === 'ambos');
    const precioMayorista = aplicaMayorista
      ? ((p.precio_rebajado != null && Number(p.precio_rebajado) > 0)
        ? Number(p.precio_rebajado)
        : +(precioMayoristaLista * (1 - dtoPct / 100)).toFixed(2))
      : precioMayoristaLista;
    const precioRetail = aplicaRetail
      ? +(precioRetailLista * (1 - dtoPct / 100)).toFixed(2)
      : precioRetailLista;
    const tieneDtoProducto = aplicaMayorista || aplicaRetail;
    const ahorroVolumen = p.ahorro_pct
      ? `−${p.ahorro_pct}%`
      : (precioRetailLista > 0 && precioMayoristaLista < precioRetailLista
        ? `−${(((1 - precioMayoristaLista / precioRetailLista) * 100)).toFixed(1)}%`
        : '—');

    const precioParaCantidad = (qty) => {
      const q = Math.max(1, Number(qty) || 1);
      return q >= minQty ? precioMayorista : precioRetail;
    };

    wrap.innerHTML = `
      <nav class="text-sm text-slate-500 flex flex-wrap items-center gap-2">
        <a href="/" class="hover:text-blue-700 transition">Inicio</a>
        <span>/</span>
        <a href="/pages/catalogo.html" class="hover:text-blue-700 transition">Productos</a>
        <span>/</span>
        <a href="/pages/catalogo.html?cat=${encodeURIComponent(p.id_item_type)}" class="hover:text-blue-700 transition">${escapeHtml(p.categoria)}</a>
        <span>/</span>
        <span class="text-slate-800 font-medium">${escapeHtml(nombreProductoEs(p.nombre_producto))}</span>
      </nav>

      <div class="mt-6 grid lg:grid-cols-[1.1fr_0.9fr] gap-10 items-start">
        <div>
          <div class="rounded-2xl border border-slate-200 bg-white overflow-hidden shadow-sm">
            <div class="bg-gradient-to-b from-slate-50 to-white p-6">
              ${etiquetaImagenProducto(p, 'h-[460px] w-full object-contain')}
            </div>
          </div>

          <div class="mt-6 grid grid-cols-3 gap-3">
            <div class="rounded-xl border border-slate-200 bg-white p-4 text-center">
              <div class="text-xs font-semibold text-slate-500 uppercase tracking-wide">SKU</div>
              <div class="mt-1 font-mono text-sm font-bold text-slate-900">${escapeHtml(p.sku || `GM-${p.id_producto}`)}</div>
            </div>
            <div class="rounded-xl border border-slate-200 bg-white p-4 text-center">
              <div class="text-xs font-semibold text-slate-500 uppercase tracking-wide">Categoría</div>
              <div class="mt-1 text-sm font-bold text-slate-900">${escapeHtml(p.categoria)}</div>
            </div>
            <div class="rounded-xl border border-slate-200 bg-white p-4 text-center">
              <div class="text-xs font-semibold text-slate-500 uppercase tracking-wide">MOQ</div>
              <div class="mt-1 text-sm font-bold text-slate-900">${minQty} uds.</div>
            </div>
          </div>
        </div>

        <div class="lg:sticky lg:top-24 space-y-5">
          <div>
            ${htmlBadgeCategoria(p)}
            <span class="ml-2 inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-semibold ${stockClass}">${stockLabel}${stock != null ? ` · ${Math.floor(stock)} uds.` : ''}</span>
            ${tieneDtoProducto ? `<span class="ml-2 inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-bold bg-emerald-100 text-emerald-800">−${dtoPct.toFixed(0)}% ${aplica === 'ambos' ? 'ambos' : aplica}</span>` : ''}
            <h1 class="mt-3 text-3xl font-extrabold text-slate-900 tracking-tight leading-tight">${escapeHtml(nombreProductoEs(p.nombre_producto))}</h1>
            <p class="mt-2 text-slate-600 leading-relaxed">${escapeHtml(p.descripcion || 'Producto mayorista para distribución B2B.')}</p>
          </div>

          <div class="rounded-2xl border border-slate-200 bg-white overflow-hidden shadow-sm">
            <div class="px-5 py-3 bg-slate-50 border-b border-slate-200 text-xs font-bold uppercase tracking-wide text-slate-500">Precios por volumen</div>
            ${logged ? '' : '<p class="px-5 py-2 text-xs text-amber-800 bg-amber-50 border-b border-amber-100">Precio público visible. <a href="/pages/login.html" class="underline font-semibold">Inicia sesión</a> para ver precio mayorista B2B.</p>'}
            <table class="w-full text-sm">
              <thead><tr class="border-b border-slate-100 text-left text-slate-500">
                <th class="px-5 py-3 font-semibold">Tramo</th><th class="px-5 py-3 font-semibold">Precio/u</th><th class="px-5 py-3 font-semibold">Ahorro</th>
              </tr></thead>
              <tbody>
                <tr id="tier-retail" class="border-b border-slate-50 bg-blue-50/60"><td class="px-5 py-3 font-semibold">Retail (&lt; ${minQty} uds.)</td><td class="px-5 py-3 font-semibold">${formatUsd(precioRetail)}${aplicaRetail ? ` <span class="ml-1 text-xs font-normal text-slate-400 line-through">${formatUsd(precioRetailLista)}</span>` : ''}</td><td class="px-5 py-3 ${aplicaRetail ? 'font-semibold text-emerald-700' : 'text-slate-400'}">${aplicaRetail ? `−${dtoPct.toFixed(0)}% dto` : '—'}</td></tr>
                <tr id="tier-mayorista"><td class="px-5 py-3">Mayorista (≥ ${minQty} uds.)</td><td class="px-5 py-3 font-extrabold text-blue-700">${logged ? `${formatUsd(precioMayorista)}${aplicaMayorista ? ` <span class="ml-1 text-xs font-normal text-slate-400 line-through">${formatUsd(precioMayoristaLista)}</span>` : ''}` : '—'}</td><td class="px-5 py-3 font-semibold text-emerald-700">${logged ? (aplicaMayorista ? `−${dtoPct.toFixed(0)}% dto` : ahorroVolumen) : '—'}</td></tr>
              </tbody>
            </table>
          </div>

          <div class="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
            <div class="flex items-center justify-between gap-4">
              <div>
                <div class="text-xs text-slate-500 uppercase font-semibold">Cantidad</div>
                <div class="text-xs text-slate-400">Desde 1 ud. · mayorista desde ${minQty} uds.</div>
              </div>
              <div class="flex items-center gap-2">
                <button id="qty-minus" type="button" class="h-11 w-11 rounded-xl border border-slate-200 bg-white hover:border-blue-300 transition font-bold">−</button>
                <input id="qty" type="number" inputmode="numeric" min="1" max="100000" step="1" value="1" class="h-11 w-24 rounded-xl border border-slate-200 bg-white px-3 text-center font-semibold focus:outline-none focus:ring-2 focus:ring-blue-200">
                <button id="qty-plus" type="button" class="h-11 w-11 rounded-xl border border-slate-200 bg-white hover:border-blue-300 transition font-bold">+</button>
              </div>
            </div>
            <div class="mt-4 flex items-end justify-between border-t border-slate-100 pt-4">
              <div>
                <div class="text-xs text-slate-500">Subtotal estimado</div>
                <div id="precio-aplicado" class="text-xs text-slate-500 mt-0.5">${formatUsd(precioRetail)}/u · retail</div>
                <div id="subtotal" class="text-2xl font-extrabold text-slate-900">${formatUsd(precioRetail)}</div>
              </div>
              <button id="add-cart" type="button" ${sinStock ? 'disabled' : ''} class="gm-press rounded-xl ${sinStock ? 'bg-slate-300 cursor-not-allowed' : 'bg-blue-600 hover:bg-blue-700'} text-white px-6 py-3 font-semibold transition shadow-sm">
                ${sinStock ? 'Sin stock' : 'Agregar al carrito'}
              </button>
            </div>
          </div>

          <div class="grid sm:grid-cols-3 gap-3 text-center text-xs text-slate-600">
            <div class="rounded-xl border border-slate-200 bg-white p-3"><div class="font-bold text-slate-800">Envío B2B</div><div class="mt-1">Nacional e internacional</div></div>
            <div class="rounded-xl border border-slate-200 bg-white p-3"><div class="font-bold text-slate-800">Facturación</div><div class="mt-1">Comprobante al pagar</div></div>
            <div class="rounded-xl border border-slate-200 bg-white p-3"><div class="font-bold text-slate-800">Soporte</div><div class="mt-1">Ejecutivo de cuenta</div></div>
          </div>
        </div>
      </div>

      <div class="mt-12 rounded-2xl border border-slate-200 bg-white shadow-sm overflow-hidden">
        <div class="flex border-b border-slate-200" role="tablist">
          <button type="button" class="prod-tab active px-6 py-4 text-sm font-semibold text-blue-700 border-b-2 border-blue-600" data-tab="desc">Descripción</button>
          <button type="button" class="prod-tab px-6 py-4 text-sm font-semibold text-slate-600 hover:text-slate-900" data-tab="specs">Especificaciones</button>
          <button type="button" class="prod-tab px-6 py-4 text-sm font-semibold text-slate-600 hover:text-slate-900" data-tab="ship">Envío y logística</button>
        </div>
        <div id="tab-desc" class="prod-tab-panel p-6 text-slate-700 leading-7">${escapeHtml(p.descripcion || 'Producto mayorista GLOBTRADE. Ideal para reabastecimiento periódico con condiciones B2B.')}</div>
        <div id="tab-specs" class="prod-tab-panel hidden p-6">
          <table class="w-full max-w-xl text-sm">
            <tbody class="divide-y divide-slate-100">
              <tr><td class="py-2 pr-4 text-slate-500 w-40">SKU</td><td class="py-2 font-mono font-semibold">${escapeHtml(p.sku || '')}</td></tr>
              <tr><td class="py-2 pr-4 text-slate-500">Categoría</td><td class="py-2">${escapeHtml(p.categoria)}</td></tr>
              <tr><td class="py-2 pr-4 text-slate-500">Precio lista</td><td class="py-2">${formatUsd(precioRetail)}</td></tr>
              <tr><td class="py-2 pr-4 text-slate-500">Precio mayorista</td><td class="py-2 font-semibold text-blue-700">${formatUsd(precioMayorista)}${tieneDtoProducto ? ` <span class="text-slate-400 line-through font-normal">${formatUsd(precioMayoristaLista)}</span>` : ''}</td></tr>
              ${tieneDtoProducto ? `<tr><td class="py-2 pr-4 text-slate-500">Descuento producto</td><td class="py-2 font-semibold text-emerald-700">−${dtoPct.toFixed(0)}%</td></tr>` : ''}
              <tr><td class="py-2 pr-4 text-slate-500">Tramo mayorista</td><td class="py-2">desde ${minQty} unidades</td></tr>
              <tr><td class="py-2 pr-4 text-slate-500">Disponibilidad</td><td class="py-2">${stock != null ? `${Math.floor(stock)} unidades en almacén principal` : 'Según inventario'}</td></tr>
            </tbody>
          </table>
        </div>
        <div id="tab-ship" class="prod-tab-panel hidden p-6 text-slate-700 leading-7 space-y-3">
          <p>Despacho desde almacén central. Plazos estimados: Lima 2–3 días hábiles; provincias 5–7 días.</p>
          <p>Envío internacional disponible bajo cotización. Los costos de flete se calculan en checkout según zona.</p>
          <p class="text-sm text-slate-500">Pedidos mayoristas pueden consolidarse en pallet para optimizar flete.</p>
        </div>
      </div>

      <div class="mt-12">
        <div class="flex items-center justify-between">
          <h2 class="text-xl font-extrabold text-slate-900">Productos relacionados</h2>
          <a href="/pages/catalogo.html?cat=${encodeURIComponent(p.id_item_type)}" class="text-sm font-semibold text-blue-700 hover:text-blue-800 transition">Ver toda la categoría →</a>
        </div>
        <div id="relacionados" class="mt-5 grid sm:grid-cols-2 lg:grid-cols-4 gap-4"></div>
      </div>
    `;

    const updateSubtotal = () => {
      const qty = Math.max(1, Number(qs('#qty')?.value || 1));
      const precio = precioParaCantidad(qty);
      const esMayorista = qty >= minQty;
      const el = qs('#subtotal');
      const hint = qs('#precio-aplicado');
      if (el) el.textContent = formatUsd(precio * qty);
      if (hint) {
        const etiqueta = esMayorista
          ? (tieneDtoProducto ? 'mayorista con dto' : 'mayorista')
          : 'retail';
        hint.textContent = `${formatUsd(precio)}/u · ${etiqueta}`;
      }
      const retailRow = qs('#tier-retail');
      const mayorRow = qs('#tier-mayorista');
      retailRow?.classList.toggle('bg-blue-50/60', !esMayorista);
      retailRow?.querySelector('td')?.classList.toggle('font-semibold', !esMayorista);
      mayorRow?.classList.toggle('bg-blue-50/60', esMayorista);
      mayorRow?.querySelector('td')?.classList.toggle('font-semibold', esMayorista);
    };

    const esCantidadValida = (v) => {
      const n = Number(v);
      return v !== '' && Number.isInteger(n) && n >= 1 && n <= 100000;
    };

    qs('#qty')?.addEventListener('keydown', (e) => {
      if (e.key.length === 1 && !/[0-9]/.test(e.key)) e.preventDefault();
    });

    qs('#qty')?.addEventListener('paste', (e) => {
      e.preventDefault();
      const pegado = (e.clipboardData || window.clipboardData).getData('text').replace(/[^0-9]/g, '');
      if (pegado) {
        const input = qs('#qty');
        input.value = pegado;
        updateSubtotal();
      }
    });

    qs('#qty')?.addEventListener('input', () => {
      const input = qs('#qty');
      const v = input.value.trim();
      if (v && !/^[0-9]+$/.test(v)) input.value = v.replace(/[^0-9]/g, '');
      updateSubtotal();
    });

    qs('#qty-minus')?.addEventListener('click', () => {
      const input = qs('#qty');
      input.value = String(Math.max(1, Number(input.value || 1) - 1));
      updateSubtotal();
    });
    qs('#qty-plus')?.addEventListener('click', () => {
      const input = qs('#qty');
      input.value = String((Number(input.value || 0) || 0) + 1);
      updateSubtotal();
    });

    wrap.querySelectorAll('.prod-tab').forEach((tab) => {
      tab.addEventListener('click', () => {
        wrap.querySelectorAll('.prod-tab').forEach((t) => {
          t.classList.remove('active', 'text-blue-700', 'border-blue-600');
          t.classList.add('text-slate-600');
          t.style.borderBottom = '';
        });
        tab.classList.add('active', 'text-blue-700');
        tab.style.borderBottom = '2px solid rgb(37 99 235)';
        ['desc', 'specs', 'ship'].forEach((id) => {
          const panel = qs(`#tab-${id}`);
          if (panel) panel.classList.toggle('hidden', tab.dataset.tab !== id);
        });
      });
    });

    qs('#add-cart')?.addEventListener('click', async () => {
      if (sinStock) {
        showToast('error', 'Sin stock: no se puede comprar este producto hasta reponer inventario.');
        return;
      }
      const input = qs('#qty');
      const valor = input?.value ?? '';
      if (!esCantidadValida(valor)) {
        showToast('error', 'Ingresa una cantidad válida: número entero entre 1 y 100.000.');
        input?.focus();
        return;
      }
      const qty = Number(valor);
      if (stock != null && qty > stock) {
        showToast('error', `Solo hay ${Math.floor(stock)} unidades disponibles.`);
        return;
      }
      if (!window.gmCarrito) {
        showToast('error', 'No se pudo cargar el carrito. Recarga la página.');
        return;
      }
      await window.gmCarrito.agregar(p.id_producto, qty);
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
      const data = await apiFetch('/api/auth/login', {
        method: 'POST',
        body: { email: email.toLowerCase(), password },
      });
      setToken(data.access_token);
      setInlineMessage('login-msg', 'success', 'Sesión iniciada. Redirigiendo a productos...');
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

async function listarPaisesSelect(selector, valorSeleccionado = '') {
  const el = qs(selector);
  if (!el) return;
  try {
    const paises = await apiFetch('/api/catalogo/paises');
    el.innerHTML = '<option value="">Selecciona un país...</option>' + (paises || [])
      .map((p) => `<option value="${escapeHtml(p.country)}" ${String(p.country) === String(valorSeleccionado) ? 'selected' : ''}>${escapeHtml(p.country)}</option>`)
      .join('');
  } catch {
    el.innerHTML = '<option value="">Selecciona un país...</option>';
  }
}

function initRegistro() {
  const form = qs('#registro-form');
  if (!form) return;
  const btn = qs('#registro-submit');
  listarPaisesSelect('#pais');

  form.addEventListener('submit', async (ev) => {
    ev.preventDefault();
    const telCheck = validarTelefono(qs('#telefono')?.value);
    if (!telCheck.ok) {
      setInlineMessage('registro-msg', 'error', telCheck.msg);
      showToast('error', telCheck.msg);
      return;
    }
    const payload = {
      nombre_empresa: qs('#nombre_empresa')?.value?.trim(),
      email: qs('#email')?.value?.trim(),
      password: qs('#password')?.value,
      pais: qs('#pais')?.value?.trim(),
      telefono: telCheck.value,
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
  // Login/registro primero: no dependen de branding ni preferencias.
  initLogin();
  initRegistro();
  void loadPreferencias().finally(() => {
    initHeaderAuth();
    applyPreferenciasUI();
    initFiltrosResponsive();
    initLanding();
    initCatalogo();
    initProducto();
    setInterval(() => {
      if (document.visibilityState !== 'visible') return;
      void loadPreferencias();
    }, 120000);
  });
});

