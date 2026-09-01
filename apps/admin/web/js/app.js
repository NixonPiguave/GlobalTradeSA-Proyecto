const API = '/api';
let charts = window.charts || {};
window.charts = charts;
let filterCache = null;

/* Permisos de módulo del usuario actual (se cargan desde /api/auth/me).
   null = aún no cargado; array = códigos permitidos. */
let permisosUsuario = null;
const pagePermiso = {};

/** Permisos por página (fallback si el menú aún no está renderizado). */
const PAGE_PERM_DEFAULT = {
  dashboard: 'mod.dashboard',
  analitica: 'mod.dashboard',
  estrategia: 'mod.estrategia',
  pedidos: 'mod.operaciones',
  ventas: 'mod.ventas',
  clientes: 'mod.clientes',
  catalogo: 'mod.catalogo',
  marketing: 'mod.marketing',
  inventario: 'mod.inventario',
  compras: 'mod.compras',
  logistica: 'mod.logistica',
  finanzas: 'mod.finanzas',
  operaciones: 'mod.operaciones',
  reportes: 'mod.reportes',
  rentabilidad: 'mod.ventas',
  configuracion: 'mod.gobierno',
  usuarios: 'mod.gobierno',
  auditoria: 'mod.gobierno',
  regiones: 'mod.catalogo',
  paises: 'mod.catalogo',
  'tipos-producto': 'mod.catalogo',
  canales: 'mod.catalogo',
  prioridades: 'mod.catalogo',
  generador: 'mod.reportes',
};

const PAGES = {
  dashboard: { title: 'Panel ejecutivo', load: loadDashboard },
  analitica: { title: 'Inteligencia de datos', load: loadAnaliticaPage },
  pedidos: { title: 'Pedidos' },
  catalogo: { title: 'Catálogo' },
  inventario: { title: 'Inventario' },
  compras: { title: 'Compras' },
  clientes: { title: 'Clientes' },
  finanzas: { title: 'Finanzas' },
  reportes: { title: 'Centro de informes' },
  ventas: { title: 'Ventas históricas', load: loadVentasPage },
  regiones: { title: 'Regiones', maestra: 'regiones', fields: ['region'] },
  paises: { title: 'Países', maestra: 'paises', fields: ['country', 'id_region'] },
  'tipos-producto': { title: 'Categorías · precios base', maestra: 'tipos-producto', fields: ['item_type', 'unit_price', 'unit_cost'] },
  canales: { title: 'Canales', maestra: 'canales', fields: ['sales_channel'] },
  prioridades: { title: 'Prioridades', maestra: 'prioridades', fields: ['order_priority', 'descripcion'] },
  generador: { title: 'Generador / ETL' },
};

const fmtMoney = (n) => new Intl.NumberFormat('es-CL', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 }).format(n || 0);
const fmtMoneyDec = (n) => new Intl.NumberFormat('es-CL', { style: 'currency', currency: 'USD', minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(n || 0);
const fmtNum = (n) => new Intl.NumberFormat('es-CL').format(n || 0);
const fmtPct = (n) => (n == null ? '—' : `${Number(n).toFixed(2)}%`);

function formatApiError(err, statusText) {
  if (!err || typeof err !== 'object') return statusText || 'Error de API';

  // Respuesta estándar { code, message, detail }
  if (typeof err.message === 'string' && err.message && err.message !== statusText) {
    const detail = err.detail;
    if (Array.isArray(detail) && detail.length) {
      const partes = detail
        .map((e) => e?.msg_es || e?.msg || e?.message)
        .filter(Boolean);
      if (partes.length) return partes.join(' · ');
    }
    return err.message;
  }

  const detail = err.detail;
  if (typeof detail === 'string') return detail;
  if (detail?.message) {
    const fields = detail.fields;
    if (Array.isArray(fields) && fields.length) {
      return `${detail.message}: ${fields.join(', ')}`;
    }
    return detail.message;
  }
  if (Array.isArray(detail) && detail.length) {
    const partes = detail
      .map((e) => e?.msg_es || e?.msg || e?.message || (typeof e === 'string' ? e : ''))
      .filter(Boolean);
    if (partes.length) return partes.join(' · ');
  }
  return err.message || statusText || 'Error de API';
}

const _inflight = new Set();
let _jobAbort = null;
let _jobActive = false;
let pageAbort = new AbortController();

function isAbortError(e) {
  if (!e) return false;
  if (e.name === 'AbortError') return true;
  const msg = String(e.message || e || '');
  return /signal is aborted|aborted without reason|The operation was aborted/i.test(msg);
}

function safeToastError(e, fallback) {
  if (isAbortError(e)) return;
  const msg = (e && e.message) || fallback;
  if (msg) toast(msg, 'error');
}

function _linkAbort(parent, child) {
  if (!parent) return;
  if (parent.aborted) {
    child.abort();
    return;
  }
  parent.addEventListener('abort', () => child.abort(), { once: true });
}

function resetPageAbort() {
  pageAbort.abort();
  pageAbort = new AbortController();
}

function abortAllNetworkWork() {
  try { cancelDashboardLoad(); } catch (_) { /* noop */ }
  try { cancelBackgroundRequests(); } catch (_) { /* noop */ }
  for (const ac of [..._inflight]) {
    if (ac === _jobAbort) continue;
    try { ac.abort(); } catch (_) { /* noop */ }
  }
  for (const ac of [..._inflight]) {
    if (ac === _jobAbort) continue;
    _inflight.delete(ac);
  }
}

async function waitForNetworkIdle(maxMs = 2000) {
  const t0 = Date.now();
  while (_inflight.size > (_jobAbort ? 1 : 0) && Date.now() - t0 < maxMs) {
    await new Promise((r) => setTimeout(r, 40));
  }
}

async function api(path, opts = {}) {
  let url = `${API}${path}`;
  if (opts.cache === 'no-store') {
    url += `${path.includes('?') ? '&' : '?'}_t=${Date.now()}`;
  }
  const ac = new AbortController();
  _linkAbort(pageAbort.signal, ac);
  _linkAbort(opts.signal, ac);
  _inflight.add(ac);
  const { cache, signal, body, ...fetchOpts } = opts;
  const headers = { ...(fetchOpts.headers || {}) };
  if (body != null && typeof body === 'object' && !(body instanceof FormData) && !(body instanceof Blob)) {
    fetchOpts.body = JSON.stringify(body);
    if (!headers['Content-Type']) headers['Content-Type'] = 'application/json';
  } else if (body != null) {
    fetchOpts.body = body;
    if (typeof body === 'string') {
      const trimmed = body.trim();
      if ((trimmed.startsWith('{') || trimmed.startsWith('[')) && !headers['Content-Type']) {
        headers['Content-Type'] = 'application/json';
      }
    }
  }
  fetchOpts.headers = headers;
  let res;
  try {
    res = await fetch(url, { ...fetchOpts, signal: ac.signal });
  } catch (e) {
    if (e?.name === 'AbortError') throw e;
    throw e;
  } finally {
    _inflight.delete(ac);
  }
  const queryTimeMs = res.headers.get('X-Query-Time-Ms');
  if (!res.ok) {
    const err = await res.json().catch(() => ({ message: res.statusText }));
    throw new Error(formatApiError(err, res.statusText));
  }
  const ct = res.headers.get('content-type') || '';
  let payload = ct.includes('application/json') ? await res.json() : await res.text();
  if (payload && typeof payload === 'object') {
    payload._queryTimeMs = queryTimeMs != null ? parseInt(queryTimeMs, 10) : null;
  }
  return payload;
}

function setQueryTime(elId, payload) {
  const el = document.getElementById(elId);
  if (el && payload?._queryTimeMs != null) {
    el.textContent = `Consulta: ${payload._queryTimeMs} ms`;
  }
}

function toast(msg, type = 'success') {
  const el = document.getElementById('toast');
  if (!el) return;
  el.className = 'toast';
  void el.offsetWidth;
  el.textContent = msg;
  el.className = `toast show ${type}`;
  setTimeout(() => el.classList.remove('show'), 6000);
}

function fillSelect(id, items, valueKey, labelKey, emptyLabel = 'Todos') {
  const sel = document.getElementById(id);
  if (!sel) return;
  const prev = sel.value;
  sel.innerHTML = `<option value="">${emptyLabel}</option>` +
    items.map((it) => `<option value="${it[valueKey]}">${it[labelKey]}</option>`).join('');
  if (prev && [...sel.options].some((o) => o.value === prev)) sel.value = prev;
}

/** Fecha local Ecuador (America/Guayaquil) en YYYY-MM-DD */
function todayEc() {
  return new Date().toLocaleDateString('en-CA', { timeZone: 'America/Guayaquil' });
}

function capDateInputs(root = document) {
  const max = todayEc();
  root.querySelectorAll('input[type="date"]').forEach((el) => {
    if (!el.max || el.max > max) el.max = max;
  });
}

function validateDateRange(desdeId, hastaId) {
  const max = todayEc();
  const desde = document.getElementById(desdeId)?.value;
  const hasta = document.getElementById(hastaId)?.value;
  if (hasta && hasta > max) {
    toast('La fecha «hasta» no puede ser posterior a hoy.', 'error');
    return false;
  }
  if (desde && desde > max) {
    toast('La fecha «desde» no puede ser posterior a hoy.', 'error');
    return false;
  }
  if (desde && hasta && desde > hasta) {
    toast('«Desde» no puede ser posterior a «Hasta».', 'error');
    return false;
  }
  return true;
}

let _filtersInflight = null;
let bgAbort = new AbortController();

/** Libera peticiones en curso (filtros, ventas, maestras). */
function cancelBackgroundRequests() {
  bgAbort.abort();
  bgAbort = new AbortController();
  _filtersInflight = null;
}

function bgSignal() {
  return bgAbort.signal;
}

async function ensureFilters() {
  if (filterCache) { fillDashRegion(); return filterCache; }
  const signal = bgSignal();
  if (!_filtersInflight) {
    _filtersInflight = (async () => {
      const pack = await api('/maestras/filtros', { signal });
      if (signal.aborted) throw new DOMException('Aborted', 'AbortError');
      filterCache = {
        regiones: pack.regiones || [],
        paises: pack.paises || [],
        tipos: pack.tipos || [],
        canales: pack.canales || [],
        prioridades: pack.prioridades || [],
      };
      fillDashRegion();
      return filterCache;
    })().finally(() => { _filtersInflight = null; });
  }
  return _filtersInflight;
}

function fillDashRegion() {
  fillSelect('dash-region', filterCache?.regiones || [], 'region', 'region', 'Todas');
}

function updateCountrySelect() {
  const paises = getVentasPaisesFiltrados();
  const hidden = document.getElementById('v-country');
  if (hidden?.value && !paises.some((p) => p.country === hidden.value)) {
    hidden.value = '';
    const q = document.getElementById('v-country-q');
    if (q) q.value = '';
  }
  ventasFilterSS.country?.refresh(paises);
}

let ventasFilterSS = { region: null, country: null };

function getVentasPaisesFiltrados() {
  let paises = filterCache?.paises || [];
  const regionVal = document.getElementById('v-region')?.value;
  if (regionVal) {
    const reg = filterCache?.regiones?.find((r) => r.region === regionVal);
    if (reg) paises = paises.filter((p) => p.id_region === reg.id_region);
  }
  return paises;
}

function bindSearchSelectFilter(cfg) {
  const hidden = document.getElementById(cfg.hiddenId);
  const input = document.getElementById(cfg.inputId);
  const list = document.getElementById(cfg.listId);
  if (!hidden || !input || !list) return null;

  let items = cfg.items || [];

  const pick = (value, label) => {
    hidden.value = value;
    input.value = label || '';
    list.hidden = true;
    hidden.dispatchEvent(new Event('change', { bubbles: true }));
    if (cfg.onPick) cfg.onPick(value, label);
  };

  const matchQuery = (label, ql) => {
    const lab = String(label).toLowerCase();
    if (!ql) return true;
    if (lab.includes(ql) || lab.startsWith(ql)) return true;
    const words = lab.split(/\s+/).filter(Boolean);
    if (words.some((w) => w.startsWith(ql))) return true;
    const initials = words.map((w) => w[0] || '').join('');
    return initials.startsWith(ql);
  };

  const render = (q) => {
    const ql = q.trim().toLowerCase();
    let opts = items;
    if (ql) {
      opts = items.filter((it) => matchQuery(it[cfg.labelKey], ql));
    }
    const slice = opts.slice(0, cfg.maxResults || 50);
    list.innerHTML = [
      `<button type="button" class="ui-ss-opt" data-v="" data-l="">Todos</button>`,
      ...slice.map((it) => {
        const v = String(it[cfg.valueKey]);
        const l = String(it[cfg.labelKey]);
        return `<button type="button" class="ui-ss-opt" data-v="${esc(v)}" data-l="${esc(l)}">${esc(l)}</button>`;
      }),
    ].join('');
    list.hidden = false;
  };

  input.addEventListener('focus', () => render(input.value));
  input.addEventListener('input', () => render(input.value));
  input.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') list.hidden = true;
    if (e.key === 'Enter') {
      e.preventDefault();
      list.querySelector('.ui-ss-opt')?.click();
    }
  });
  list.addEventListener('click', (e) => {
    const btn = e.target.closest('.ui-ss-opt');
    if (!btn) return;
    pick(btn.dataset.v || '', btn.dataset.l || '');
  });
  document.addEventListener('click', (e) => {
    if (!e.target.closest(`#${cfg.listId}`) && e.target !== input) list.hidden = true;
  });

  return {
    refresh(newItems) {
      items = newItems || items;
      const it = items.find((x) => String(x[cfg.valueKey]) === String(hidden.value));
      if (it) input.value = it[cfg.labelKey];
      else if (!hidden.value) input.value = '';
    },
  };
}

function wireVentasSearchFilters() {
  if (!filterCache) return;
  if (ventasFilterSS.region) {
    ventasFilterSS.region.refresh(filterCache.regiones || []);
    ventasFilterSS.country?.refresh(getVentasPaisesFiltrados());
    return;
  }
  ventasFilterSS.region = bindSearchSelectFilter({
    hiddenId: 'v-region',
    inputId: 'v-region-q',
    listId: 'v-region-list',
    items: filterCache.regiones || [],
    valueKey: 'region',
    labelKey: 'region',
    onPick: () => updateCountrySelect(),
  });
  ventasFilterSS.country = bindSearchSelectFilter({
    hiddenId: 'v-country',
    inputId: 'v-country-q',
    listId: 'v-country-list',
    items: getVentasPaisesFiltrados(),
    valueKey: 'country',
    labelKey: 'country',
  });
}

let activePage = 'dashboard';
let dashboardAbort = null;

function cancelDashboardLoad() {
  if (dashboardAbort) {
    dashboardAbort.abort();
    dashboardAbort = null;
  }
}

function pageSignal() {
  return undefined;
}

function pageFromUrl() {
  const p = new URLSearchParams(window.location.search).get('page');
  return p && PAGES[p] ? p : null;
}

function syncPageUrl(page) {
  const url = new URL(window.location.href);
  if (!page || page === 'dashboard') {
    url.searchParams.delete('page');
  } else {
    url.searchParams.set('page', page);
  }
  const next = url.pathname + url.search + url.hash;
  const cur = window.location.pathname + window.location.search + window.location.hash;
  if (next !== cur) history.replaceState({ page }, '', next);
}

function buildPagePermiso() {
  Object.keys(pagePermiso).forEach((k) => delete pagePermiso[k]);
  Object.assign(pagePermiso, PAGE_PERM_DEFAULT);
  document.querySelectorAll('.nav-item[data-page][data-perm]').forEach((b) => {
    pagePermiso[b.dataset.page] = b.dataset.perm;
  });
}

async function cargarPermisosUsuario() {
  permisosUsuario = null;
  try {
    const me = await api('/auth/me');
    permisosUsuario = Array.isArray(me.permisos) ? me.permisos : [];
    const prev = window.adminAuth?.user?.() || {};
    window.adminAuth?.save(window.adminAuth.token(), {
      email: me.email || prev.email,
      rol: me.rol || prev.rol,
      permisos: permisosUsuario,
    });
    aplicarNavPermisos(me.rol === 'admin');
    return me;
  } catch (e) {
    permisosUsuario = [];
    aplicarNavPermisos(false);
    return null;
  }
}

function aplicarNavPermisos(esAdmin) {
  document.querySelectorAll('.nav-item[data-perm]').forEach((b) => {
    const perm = b.dataset.perm;
    b.hidden = !esAdmin && !(permisosUsuario || []).includes(perm);
  });
  document.querySelectorAll('.topnav-group').forEach((g) => {
    const visibles = [...g.querySelectorAll('.nav-item')].filter((b) => !b.hidden);
    g.hidden = visibles.length === 0;
  });
  bindNavItems();
}

function mayAcceder(page) {
  const perm = pagePermiso[page];
  if (!perm) return true;
  const u = window.adminAuth?.user?.();
  if (u && u.rol === 'admin') return true;
  if (permisosUsuario === null) {
    const cached = u?.permisos;
    if (Array.isArray(cached)) return cached.includes(perm);
    return false;
  }
  return permisosUsuario.includes(perm);
}

function paginaInicio() {
  return primeraPaginaPermitida();
}

function primeraPaginaPermitida() {
  const u = window.adminAuth?.user?.();
  if (u && u.rol === 'admin') return 'dashboard';
  const orden = [
    'dashboard', 'analitica', 'estrategia',
    'pedidos', 'ventas', 'clientes', 'catalogo', 'marketing',
    'inventario', 'compras', 'logistica', 'finanzas', 'operaciones',
    'reportes', 'rentabilidad',
    'configuracion', 'usuarios', 'auditoria',
    'regiones', 'paises', 'tipos-producto', 'canales', 'prioridades', 'generador',
  ];
  for (const p of orden) {
    if (PAGES[p] && mayAcceder(p)) return p;
  }
  const any = Object.keys(PAGES).find((p) => mayAcceder(p));
  return any || 'dashboard';
}

function showPage(page) {
  if (!page || !PAGES[page]) {
    toast('Módulo no disponible. Recargue la página (Ctrl+F5).', 'error');
    return;
  }
  if (!mayAcceder(page)) {
    // No mostrar toast de permiso: el menú ya oculta lo no autorizado
    page = primeraPaginaPermitida();
  }
  if (!_jobActive) resetPageAbort();
  activePage = page;
  document.querySelectorAll('.nav-item').forEach((b) => {
    b.classList.toggle('active', b.dataset.page === page);
  });
  document.querySelectorAll('.page').forEach((p) => {
    p.classList.toggle('active', p.id === `page-${page}`);
  });
  const titleEl = document.getElementById('page-title');
  if (titleEl) titleEl.textContent = PAGES[page].title;
  const crumb = document.getElementById('breadcrumb');
  if (crumb) {
    const grupo = {
      dashboard: 'Dirección', analitica: 'Dirección', estrategia: 'Dirección',
      pedidos: 'Comercial', ventas: 'Comercial', clientes: 'Comercial', catalogo: 'Comercial', marketing: 'Comercial',
      inventario: 'Operaciones', compras: 'Operaciones', logistica: 'Operaciones', finanzas: 'Operaciones', operaciones: 'Operaciones',
      reportes: 'Informes', rentabilidad: 'Informes',
    }[page] || 'Sistema';
    crumb.textContent = grupo;
  }
  document.getElementById('topnav')?.classList.remove('open');
  syncPageUrl(page);
  const mark = document.getElementById('ch-watermark');
  if (mark) mark.hidden = page !== 'analitica';
}

async function loadAnaliticaPage() {
  capDateInputs(document.getElementById('page-analitica'));
  const host = document.getElementById('vista-analitica');
  if (!host) return;
  const desde = document.getElementById('ana-from')?.value || '';
  const hasta = document.getElementById('ana-to')?.value || '';
  // Destruir charts previos antes de recrear canvas (evita canvas “muertos” al reentrar)
  ['ana-proveedores', 'ana-clientes', 'ana-paises', 'ana-lineas', 'ana-pedidos', 'ana-margen'].forEach((id) => {
    try { GTChart.destroy(id); } catch (_) { /* noop */ }
  });
  host.innerHTML = `
    ${GTChart.chartPanelHtml('ana-proveedores', 'Top proveedores por compra', 300)}
    ${GTChart.chartPanelHtml('ana-clientes', 'Top clientes por venta', 300)}
    ${GTChart.chartPanelHtml('ana-paises', 'Ventas por país', 300)}
    ${GTChart.chartPanelHtml('ana-lineas', 'Ventas por línea de producto', 300)}
    ${GTChart.chartPanelHtml('ana-pedidos', 'Pedidos por estado', 260)}
    ${GTChart.chartPanelHtml('ana-margen', 'Margen por categoría', 300)}
  `;
  const opts = { desde, hasta };
  // Secuencial: evita saturar DuckDB/CH al reentrar tras abortar la visita anterior
  const jobs = [
    ['ranking-proveedores', 'ana-proveedores'],
    ['ranking-clientes', 'ana-clientes'],
    ['ventas-por-pais', 'ana-paises'],
    ['ventas-por-linea', 'ana-lineas'],
    ['pedidos-por-estado', 'ana-pedidos'],
    ['margen-por-categoria', 'ana-margen'],
  ];
  for (const [vista, canvasId] of jobs) {
    if (activePage !== 'analitica') return;
    await GTChart.loadAnalyticsChart(vista, canvasId, opts);
  }
  if (activePage === 'analitica') await refreshClickHouseWatermark();
}

async function refreshClickHouseWatermark() {
  const mark = document.getElementById('ch-watermark');
  const badge = document.getElementById('ana-ch-badge');
  try {
    const st = await api('/analytics/estado');
    const ok = !!st?.disponible;
    const synced = st?.tablas
      ? Object.values(st.tablas).map((t) => t?.synced_at).filter(Boolean).sort().pop()
      : null;
    const label = ok
      ? `ClickHouse · ${synced ? String(synced).slice(0, 16).replace('T', ' ') : 'sync OK'}`
      : 'ClickHouse offline';
    if (mark) {
      mark.hidden = false;
      mark.textContent = label;
      mark.dataset.offline = ok ? '0' : '1';
    }
    if (badge) badge.textContent = ok ? `Motor: ClickHouse` : 'Motor: no disponible';
  } catch {
    if (mark) {
      mark.hidden = false;
      mark.textContent = 'ClickHouse offline';
      mark.dataset.offline = '1';
    }
  }
}

/** Carga datos de la página (la UI ya cambió con showPage). */
async function loadPageData(page) {
  // Durante un job largo (ETL) igual permitimos navegar: solo avisamos.
  if (_jobActive) {
    toast('Hay una operación en curso; los datos pueden tardar en refrescar.', 'success');
  }
  if (!mayAcceder(page)) return;
  const cfg = PAGES[page];
  if (!cfg) return;
  if (page === 'generador') {
    initGenerador();
    return;
  }
  if (cfg.load) await cfg.load();
  else if (cfg.maestra) await loadMaestra(cfg.maestra, cfg.fields);
}

let _navToken = 0;

async function navigate(page) {
  if (!page || !PAGES[page]) return;
  const token = ++_navToken;
  showPage(page);
  const target = activePage;
  const pageEl = document.getElementById(`page-${target}`);
  pageEl?.classList.add('page-loading');
  try {
    await loadPageData(target);
    if (token !== _navToken) return;
    if (pageEl && activePage === target) {
      pageEl.dataset.loaded = '1';
      pageEl.classList.remove('page-loading');
    }
  } catch (e) {
    if (token !== _navToken) return;
    pageEl?.classList.remove('page-loading');
    safeToastError(e);
  }
}

function bindNavItems() {
  document.querySelectorAll('.nav-item').forEach((btn) => {
    if (btn.dataset.navBound) return;
    btn.dataset.navBound = '1';
    btn.addEventListener('click', (e) => {
      e.preventDefault();
      e.stopPropagation();
      const page = btn.dataset.page;
      if (!page) return;
      document.querySelectorAll('.topnav-group.open').forEach((g) => g.classList.remove('open'));
      void navigate(page);
    });
  });
}
const SIDEBAR_KEY = 'globtrade-sidebar-collapsed';

document.getElementById('menu-toggle')?.addEventListener('click', () => {
  document.getElementById('topnav')?.classList.toggle('open');
});

document.getElementById('topbar-home')?.addEventListener('click', (e) => {
  e.preventDefault();
  navigate(paginaInicio());
});

document.querySelectorAll('[data-goto]').forEach((el) => {
  el.addEventListener('click', () => navigate(el.dataset.goto));
});

document.getElementById('dash-sync-ch')?.addEventListener('click', async () => {
  try {
    const res = await api('/dashboard/sync-clickhouse', { method: 'POST' });
    toast(res.publicado ? 'Almacén analítico actualizado.' : (res.motivo || 'Sync no disponible'), res.publicado ? 'success' : 'error');
    await loadDashboard();
  } catch (e) {
    toast(e.message, 'error');
  }
});

document.getElementById('ana-apply')?.addEventListener('click', () => {
  if (!validateDateRange('ana-from', 'ana-to')) return;
  void loadAnaliticaPage();
});
document.getElementById('ana-clear')?.addEventListener('click', () => {
  ['ana-from', 'ana-to'].forEach((id) => { const el = document.getElementById(id); if (el) el.value = ''; });
  capDateInputs(document.getElementById('page-analitica'));
  void loadAnaliticaPage();
});

const THEME_CHART = {
  dark: {
    text: '#94a3b8',
    grid: '#334155',
    blue: 'rgba(59, 130, 246, 0.75)',
    green: 'rgba(16, 185, 129, 0.75)',
    lineBorder: '#3b82f6',
    lineFill: 'rgba(59, 130, 246, 0.15)',
    palette: ['#3b82f6', '#10b981', '#f59e0b', '#8b5cf6', '#ef4444'],
  },
  light: {
    text: '#5a6b85',
    grid: '#d4dce8',
    blue: 'rgba(91, 127, 214, 0.88)',
    green: 'rgba(13, 148, 136, 0.85)',
    lineBorder: '#5b7fd6',
    lineFill: 'rgba(91, 127, 214, 0.2)',
    palette: ['#8ba8e8', '#6ec9b8', '#e8b86d', '#b8a0e8', '#e89595'],
  },
};

let CHART_COLORS = { ...THEME_CHART.light };

function getCurrentTheme() {
  return 'light';
}

function syncChartColors() {
  CHART_COLORS = { ...THEME_CHART[getCurrentTheme()] };
}

function updateThemeToggleUI(theme) {
  document.querySelectorAll('[data-theme-pick]').forEach((btn) => {
    const active = btn.dataset.themePick === theme;
    btn.setAttribute('aria-pressed', active ? 'true' : 'false');
  });
}

function setTheme(theme) {
  const next = theme === 'light' ? 'light' : 'dark';
  document.documentElement.setAttribute('data-theme', next);
  localStorage.setItem('globtrade-theme', next);
  syncChartColors();
  updateThemeToggleUI(next);
  if (document.getElementById('page-dashboard')?.classList.contains('active')) {
    loadDashboard();
  }
}

function initTheme() {
  const theme = getCurrentTheme();
  syncChartColors();
  updateThemeToggleUI(theme);
  document.querySelectorAll('[data-theme-pick]').forEach((btn) => {
    btn.addEventListener('click', () => setTheme(btn.dataset.themePick));
  });
}

function destroyChart(id) {
  if (charts[id]) { charts[id].destroy(); delete charts[id]; }
}

function baseScales() {
  return {
    x: { ticks: { color: CHART_COLORS.text }, grid: { color: CHART_COLORS.grid } },
    y: { ticks: { color: CHART_COLORS.text }, grid: { color: CHART_COLORS.grid } },
  };
}

async function loadDashboard() {
  capDateInputs(document.getElementById('page-dashboard'));
  if (!validateDateRange('dash-from', 'dash-to')) return;
  cancelDashboardLoad();
  const ac = new AbortController();
  dashboardAbort = ac;
  const { signal } = ac;

  const q = new URLSearchParams();
  const from = document.getElementById('dash-from')?.value;
  const to = document.getElementById('dash-to')?.value;
  const region = document.getElementById('dash-region')?.value;
  const origen = document.getElementById('dash-origen')?.value;
  if (from) q.set('fecha_inicio', from);
  if (to) q.set('fecha_fin', to);
  if (region) q.set('region', region);
  if (origen) q.set('origen', origen);

  try {
    try {
      await ensureFilters();
    } catch (e) {
      console.warn('Filtros maestros no disponibles:', e);
    }
    if (signal.aborted || activePage !== 'dashboard') return;

    const kpis = await api(`/dashboard/kpis?${q}`, { signal });
    if (signal.aborted || activePage !== 'dashboard') return;

    const margen = kpis.total_revenue > 0 ? (kpis.total_profit / kpis.total_revenue) * 100 : 0;
    document.getElementById('kpi-revenue').textContent = fmtMoney(kpis.total_revenue);
    document.getElementById('kpi-profit').textContent = fmtMoney(kpis.total_profit);
    document.getElementById('kpi-profit').className = `value ${kpis.total_profit >= 0 ? 'profit' : 'loss'}`;
    document.getElementById('kpi-margin').textContent = fmtPct(margen);
    document.getElementById('kpi-units').textContent = fmtNum(kpis.units_sold);

    try {
      const ops = await api('/dashboard/operaciones', { signal });
      document.getElementById('kpi-pedidos').textContent = fmtNum(ops?.pedidos_activos ?? ops?.total_pedidos ?? 0);
    } catch (_) {
      document.getElementById('kpi-pedidos').textContent = '—';
    }

    try {
      const ch = await api('/analytics/estado', { signal });
      const el = document.getElementById('kpi-clickhouse');
      if (el) {
        el.textContent = ch.disponible
          ? `${(ch.tablas || []).length} tablas · ${fmtNum(ch.total_filas)} filas`
          : 'No conectado';
      }
    } catch (_) {
      document.getElementById('kpi-clickhouse').textContent = '—';
    }

    setQueryTime('dash-query-time', kpis);
    loadEtlExtra(signal);

    try {
      const [chartsData, topPaises] = await Promise.all([
        api(`/dashboard/charts?${q}`, { signal }),
        api(`/dashboard/top-paises?${q}`, { signal }),
      ]);
      if (signal.aborted || activePage !== 'dashboard') return;
      renderBarChart('chart-region', (chartsData.por_region || []).slice(0, 8));
      renderBarChart('chart-canal', chartsData.por_canal || []);
      renderHorizontalBar('chart-item', (chartsData.por_item_type || []).slice(0, 8));
      const tbody = document.getElementById('top-paises-body');
      if (tbody) {
        const rows = Array.isArray(topPaises) ? topPaises : (topPaises?.items || topPaises?.paises || []);
        tbody.innerHTML = rows.length
          ? rows.slice(0, 5).map((r) => {
              const profit = Number(r.total_profit ?? r.profit ?? 0);
              const rev = Number(r.total_revenue ?? r.ingresos ?? 0);
              const margen = rev > 0 ? (profit / rev) * 100 : 0;
              return `<tr>
                <td>${esc(r.country || r.pais || '—')}</td>
                <td>${esc(r.region || '—')}</td>
                <td class="num">${fmtMoney(profit)}</td>
                <td class="num">${fmtMoney(rev)}</td>
                <td class="num">${fmtPct(margen)}</td>
              </tr>`;
            }).join('')
          : '<tr><td colspan="5" class="meta">Sin datos para el filtro actual</td></tr>';
      }
    } catch (chartErr) {
      if (chartErr?.name === 'AbortError') return;
      console.warn('Dashboard charts:', chartErr);
    }
  } catch (e) {
    if (e?.name === 'AbortError') return;
    toast(e.message, 'error');
  } finally {
    if (dashboardAbort === ac) dashboardAbort = null;
  }
}

async function loadEtlExtra(signal) {
  const el = document.getElementById('etl-extra');
  if (!el) return;
  try {
    const [data, ch] = await Promise.all([
      api('/dashboard/etl-estado', { signal }),
      api('/analytics/estado', { signal }).catch(() => ({ disponible: false })),
    ]);
    const kpis = (data.kpis || []).map((r) => {
      const etiqueta = String(r.kpi).replace(/_/g, ' ');
      const valor = (r.unidad === '%' ? fmtPct : fmtMoney)(r.valor);
      return `${etiqueta}: <b>${valor}</b>`;
    });
    const ultima = (data.ultimas_ejecuciones || [])[0];
    const fmtSincro = (v) => {
      if (!v) return '—';
      const d = /^\d{4}-\d{2}-\d{2}/.test(String(v))
        ? new Date(String(v).replace(' ', 'T'))
        : new Date(Number(v) * 1000);
      return isNaN(d.getTime()) ? String(v) : d.toLocaleString('es-PE');
    };
    el.innerHTML = `
      <div class="kpi-card"><div class="label">Última sincronización</div>
        <div class="value" style="font-size:.9rem">${fmtSincro(ultima?.inicio)}</div></div>
      <div class="kpi-card"><div class="label">Etapa / tiempo</div>
        <div class="value" style="font-size:.9rem">${esc(ultima ? `${ultima.etapa} · ${ultima.tiempo_s}s` : '—')}</div></div>
      <div class="kpi-card"><div class="label">Filas fact_ventas</div>
        <div class="value" style="font-size:.9rem">${fmtNum(data.filas_fact_ventas)}</div></div>
      <div class="kpi-card"><div class="label">Tablas analíticas</div>
        <div class="value" style="font-size:.9rem">${(data.tablas_analiticas || []).length}</div></div>
      <div class="kpi-card"><div class="label">ClickHouse</div>
        <div class="value" style="font-size:.9rem">${ch.disponible ? `${fmtNum(ch.total_filas)} filas` : 'Offline'}</div></div>
      <p class="query-time" style="grid-column:1/-1">KPIs persistidos por el ETL: ${kpis.join(' · ') || '—'}</p>`;
  } catch (e) {
    if (e?.name === 'AbortError') return;
    el.innerHTML = '<p class="query-time">Información ETL no disponible</p>';
  }
}

function renderBarChart(id, rows) {
  const ctx = document.getElementById(id);
  if (!ctx || typeof Chart === 'undefined') return;
  const data = rows || [];
  destroyChart(id);
  charts[id] = new Chart(ctx, {
    type: 'bar',
    data: {
      labels: data.map((d) => d.label),
      datasets: [{ data: data.map((d) => d.total_revenue), backgroundColor: CHART_COLORS.blue, borderRadius: 6 }],
    },
    options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false } }, scales: baseScales() },
  });
}

function renderRevenueProfitChart(id, rows) {
  const ctx = document.getElementById(id);
  if (!ctx || typeof Chart === 'undefined') return;
  const data = rows || [];
  destroyChart(id);
  charts[id] = new Chart(ctx, {
    type: 'bar',
    data: {
      labels: data.map((d) => d.label),
      datasets: [
        { label: 'Ingresos', data: data.map((d) => d.total_revenue), backgroundColor: CHART_COLORS.blue, borderRadius: 4 },
        { label: 'Profit', data: data.map((d) => d.total_profit), backgroundColor: CHART_COLORS.green, borderRadius: 4 },
      ],
    },
    options: {
      responsive: true, maintainAspectRatio: false,
      plugins: { legend: { labels: { color: CHART_COLORS.text } } },
      scales: baseScales(),
    },
  });
}

function renderLineChart(id, rows) {
  const ctx = document.getElementById(id);
  if (!ctx || typeof Chart === 'undefined') return;
  const data = rows || [];
  destroyChart(id);
  charts[id] = new Chart(ctx, {
    type: 'line',
    data: {
      labels: data.map((d) => d.label),
      datasets: [{
        label: 'Ingresos',
        data: data.map((d) => d.total_revenue),
        borderColor: CHART_COLORS.lineBorder,
        backgroundColor: CHART_COLORS.lineFill,
        fill: true,
        tension: 0.3,
      }],
    },
    options: {
      responsive: true, maintainAspectRatio: false,
      plugins: { legend: { display: false } },
      scales: baseScales(),
    },
  });
}

function renderDoughnutChart(id, rows) {
  const ctx = document.getElementById(id);
  if (!ctx || typeof Chart === 'undefined') return;
  const data = rows || [];
  destroyChart(id);
  const colors = CHART_COLORS.palette;
  charts[id] = new Chart(ctx, {
    type: 'doughnut',
    data: {
      labels: data.map((d) => d.label),
      datasets: [{
        data: data.map((d) => d.total_revenue),
        backgroundColor: data.map((_, i) => colors[i % colors.length]),
      }],
    },
    options: {
      responsive: true, maintainAspectRatio: false,
      plugins: { legend: { position: 'right', labels: { color: CHART_COLORS.text } } },
    },
  });
}

function renderHorizontalBar(id, rows) {
  const ctx = document.getElementById(id);
  if (!ctx || typeof Chart === 'undefined') return;
  const data = rows || [];
  destroyChart(id);
  charts[id] = new Chart(ctx, {
    type: 'bar',
    data: {
      labels: data.map((d) => d.label),
      datasets: [{ data: data.map((d) => d.total_revenue), backgroundColor: CHART_COLORS.blue, borderRadius: 4 }],
    },
    options: {
      indexAxis: 'y',
      responsive: true, maintainAspectRatio: false,
      plugins: { legend: { display: false } },
      scales: baseScales(),
    },
  });
}

let ventasState = { page: 1, page_size: 50, total_pages: 1 };
let vistaVentas = null;

const VENTAS_COLS = [
  { key: 'id_venta', label: 'ID', align: 'col-id' },
  { key: 'order_id', label: 'Order ID', align: 'center' },
  { key: 'country', label: 'País', align: 'center' },
  { key: 'item_type', label: 'Producto', align: 'center' },
  { key: 'order_date', label: 'F. pedido', align: 'center' },
  { key: 'units_sold', label: 'Unidades', align: 'num', render: (r) => fmtNum(r.units_sold) },
  { key: 'total_revenue', label: 'Ingresos', align: 'num', render: (r) => fmtMoney(r.total_revenue) },
  { key: 'total_profit', label: 'Profit', align: 'num', render: (r) => `<span class="text-profit">${fmtMoney(r.total_profit)}</span>` },
];

function bindFilterCombobox(hiddenId, inputId, listId, items, valueKey, labelKey) {
  const hidden = document.getElementById(hiddenId);
  const input = document.getElementById(inputId);
  const list = document.getElementById(listId);
  if (!hidden || !input || !list) return;
  list.innerHTML = items.map((it) =>
    `<option value="${String(it[labelKey]).replace(/&/g, '&amp;').replace(/"/g, '&quot;')}">`
  ).join('');
  const syncFromInput = () => {
    const q = input.value.trim();
    const qLower = q.toLowerCase();
    const match = items.find((it) => String(it[labelKey]).toLowerCase() === qLower)
      || items.find((it) => String(it[labelKey]).toLowerCase().includes(qLower));
    hidden.value = match ? match[valueKey] : (q ? q : '');
  };
  input.addEventListener('input', syncFromInput);
  input.addEventListener('change', syncFromInput);
  hidden.addEventListener('change', () => {
    const it = items.find((x) => String(x[valueKey]) === String(hidden.value));
    if (it) input.value = it[labelKey];
  });
}

function fillVentasFiltros() {
  if (!filterCache) return;
  wireVentasSearchFilters();
  if (filterCache.tipos?.length) {
    bindFilterCombobox('v-item_type', 'v-item_type-q', 'v-item_type-list', filterCache.tipos, 'item_type', 'item_type');
  }
  fillSelect('v-sales_channel', filterCache.canales, 'sales_channel', 'sales_channel');
  fillSelect('v-order_priority', filterCache.prioridades, 'order_priority', 'order_priority');
  updateCountrySelect();
  capDateInputs(document.getElementById('vista-ventas'));
}

async function crearVistaVentas() {
  const cont = document.getElementById('vista-ventas');
  if (!cont) return null;
  if (vistaVentas) return vistaVentas;
  await ensureFilters();
  vistaVentas = createDataView(cont, {
    state: ventasState,
    autoLoad: false,
    filtrosClass: 'dv-filters-grid dv-filters-ventas',
    botonesInline: true,
    buscar: { id: 'v-q', placeholder: 'Order ID, país, región o producto...' },
    filtrosHtml: `
      <div class="field field-region ui-search-select"><label>Región</label>
        <input type="hidden" id="v-region" value="" data-dv-auto>
        <input type="search" class="ui-ss-input" id="v-region-q" placeholder="Buscar región…" autocomplete="off">
        <div class="ui-ss-list" id="v-region-list" hidden></div>
      </div>
      <div class="field field-pais ui-search-select"><label>País</label>
        <input type="hidden" id="v-country" value="" data-dv-auto>
        <input type="search" class="ui-ss-input" id="v-country-q" placeholder="Buscar país (ej. EC)…" autocomplete="off">
        <div class="ui-ss-list" id="v-country-list" hidden></div>
      </div>
      <div class="field field-product ui-filter-combo"><label>Producto</label>
        <input type="hidden" id="v-item_type" value="">
        <input type="search" id="v-item_type-q" list="v-item_type-list" placeholder="Buscar producto…" autocomplete="off">
        <datalist id="v-item_type-list"></datalist>
      </div>
      <div class="field field-canal"><label>Canal</label><select id="v-sales_channel" data-dv-auto><option value="">Todos</option></select></div>
      <div class="field field-prioridad"><label>Prioridad</label><select id="v-order_priority" data-dv-auto><option value="">Todos</option></select></div>
      <div class="field field-desde"><label>Desde</label><input type="date" id="v-from" data-dv-auto></div>
      <div class="field field-hasta"><label>Hasta</label><input type="date" id="v-to" data-dv-auto></div>`,
    botones: [
      { id: 'ventas-export', label: 'Exportar CSV', clase: 'btn-secondary', fn: exportarVentasCSV },
    ],
    columnas: VENTAS_COLS,
    totalId: 'ventas-total',
    cargar: async (st) => {
      const q = new URLSearchParams({ page: st.page, page_size: st.page_size, sort_by: 'order_id', sort_order: 'desc' });
      ['region', 'country', 'item_type', 'sales_channel', 'order_priority'].forEach((f) => {
        const v = document.getElementById(`v-${f}`)?.value;
        if (v) q.set(f, v);
      });
      const from = document.getElementById('v-from')?.value;
      const to = document.getElementById('v-to')?.value;
      if (from) q.set('fecha_inicio', from);
      if (to) q.set('fecha_fin', to);
      const qtext = document.getElementById('v-q')?.value?.trim();
      if (qtext) q.set('q', qtext);
      const res = await api(`/ventas?${q}`, { cache: 'no-store' });
      paintVentasTotal(res?.total ?? 0);
      return res;
    },
    resumen: (r) => `<div class="detail-grid">
      <div><strong>Order ID:</strong> ${esc(r.order_id)}</div>
      <div><strong>Producto:</strong> ${esc(r.item_type)}</div>
      <div><strong>País:</strong> ${esc(r.country)} (${esc(r.region)})</div>
      <div><strong>Canal:</strong> ${esc(r.sales_channel)}</div>
      <div><strong>Prioridad:</strong> ${esc(r.order_priority)}</div>
      <div><strong>F. pedido:</strong> ${esc(r.order_date)}</div>
      <div><strong>F. envío:</strong> ${esc(r.ship_date)}</div>
      <div><strong>Unidades:</strong> ${fmtNum(r.units_sold)}</div>
      <div><strong>Ingresos:</strong> ${fmtMoney(r.total_revenue)}</div>
      <div><strong>Costo total:</strong> ${fmtMoney(r.total_cost)}</div>
      <div><strong>Profit:</strong> <span class="text-profit">${fmtMoney(r.total_profit)}</span></div>
    </div>`,
    titulo: (r) => `Venta #${r.id_venta}`,
    key: (r) => r.id_venta,
    acciones: {
      ver: async (r) => {
        const full = await api(`/ventas/${r.id_venta}`);
        uiModal({
          modo: 'Detalle',
          tituloExtra: `Venta #${full.id_venta}`,
          ancho: 'md',
          textoAceptar: 'Cerrar',
          campos: [{ type: 'html', key: 'info', value: `
            <div class="detail-grid">
              <div><strong>ID:</strong> ${full.id_venta}</div>
              <div><strong>Order ID:</strong> ${esc(full.order_id)}</div>
              <div><strong>Región:</strong> ${esc(full.region)}</div>
              <div><strong>País:</strong> ${esc(full.country)}</div>
              <div><strong>Producto:</strong> ${esc(full.item_type)}</div>
              <div><strong>Canal:</strong> ${esc(full.sales_channel)}</div>
              <div><strong>Prioridad:</strong> ${esc(full.order_priority)}</div>
              <div><strong>F. pedido:</strong> ${esc(full.order_date)}</div>
              <div><strong>F. envío:</strong> ${esc(full.ship_date)}</div>
              <div><strong>Unidades:</strong> ${fmtNum(full.units_sold)}</div>
              <div><strong>P. unitario:</strong> ${fmtMoneyDec(full.unit_price)}</div>
              <div><strong>C. unitario:</strong> ${fmtMoneyDec(full.unit_cost)}</div>
              <div><strong>Ingresos:</strong> ${fmtMoney(full.total_revenue)}</div>
              <div><strong>Costo total:</strong> ${fmtMoney(full.total_cost)}</div>
              <div><strong>Profit:</strong> <span class="text-profit">${fmtMoney(full.total_profit)}</span></div>
            </div>` }],
        });
      },
    },
    vacio: 'Sin registros',
  });
  fillVentasFiltros();
  document.getElementById('v-region')?.addEventListener('change', () => {
    updateCountrySelect();
    ventasState.page = 1;
    if (vistaVentas) void vistaVentas.recargar();
  });
  document.getElementById('v-country')?.addEventListener('change', () => {
    ventasState.page = 1;
    if (vistaVentas) void vistaVentas.recargar();
  });
  return vistaVentas;
}

/** Abre un PDF en pestaña nueva (ver / imprimir / guardar). CSV sigue forzando descarga. */
function openPdfBlob(blob, filename = 'documento.pdf') {
  const pdf = new Blob([blob], { type: 'application/pdf' });
  const url = URL.createObjectURL(pdf);
  const win = window.open(url, '_blank', 'noopener');
  if (!win) {
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    a.remove();
    toast('Permite ventanas emergentes para previsualizar el PDF', 'error');
  }
  setTimeout(() => URL.revokeObjectURL(url), 120000);
}

function downloadBlobFile(blob, filename) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

let _reporteEnCurso = false;
async function downloadReport(nombre, formato, params = {}) {
  if (_reporteEnCurso) {
    toast('Ya se está generando un reporte; espera a que termine', 'error');
    return;
  }
  _reporteEnCurso = true;
  const t0 = performance.now();
  const toastEl = document.getElementById('toast');
  let hideTimer = null;
  const showProgreso = () => {
    if (!toastEl) return;
    clearTimeout(hideTimer);
    toastEl.className = 'toast';
    void toastEl.offsetWidth;
    toastEl.textContent =
      `Generando «${nombre}» (${formato.toUpperCase()})… ${((performance.now() - t0) / 1000).toFixed(0)} s`;
    toastEl.className = 'toast show';
  };
  showProgreso();
  const timer = setInterval(showProgreso, 3000);
  try {
    const q = new URLSearchParams({ formato });
    Object.entries(params).forEach(([k, v]) => { if (v != null && v !== '') q.set(k, v); });
    const res = await fetch(`${API}/reportes/${nombre}?${q}`);
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || 'No se pudo generar el reporte');
    }
    const blob = await res.blob();
    const cd = res.headers.get('Content-Disposition') || '';
    const match = cd.match(/filename="?([^";]+)"?/);
    const filename = match ? match[1] : `${nombre}.${formato}`;
    const isPdf = String(formato).toLowerCase() === 'pdf' || String(filename).toLowerCase().endsWith('.pdf');
    if (isPdf) openPdfBlob(blob, filename);
    else downloadBlobFile(blob, filename);
    const secs = (performance.now() - t0) / 1000;
    const size = blob.size >= 1048576
      ? `${(blob.size / 1048576).toFixed(1)} MB`
      : `${Math.max(1, Math.round(blob.size / 1024))} KB`;
    toast(isPdf
      ? `«${nombre}» abierto · ${secs.toFixed(1)} s · ${size}`
      : `«${nombre}» listo · ${secs.toFixed(1)} s · ${size} · ${filename}`);
  } finally {
    clearInterval(timer);
    clearTimeout(hideTimer);
    _reporteEnCurso = false;
  }
}

function exportarVentasCSV() {
  const q = new URLSearchParams();
  ['region', 'country', 'item_type', 'sales_channel', 'order_priority'].forEach((f) => {
    const v = document.getElementById(`v-${f}`)?.value;
    if (v) q.set(f, v);
  });
  const from = document.getElementById('v-from')?.value;
  const to = document.getElementById('v-to')?.value;
  const qtext = document.getElementById('v-q')?.value?.trim();
  if (from) q.set('fecha_inicio', from);
  if (to) q.set('fecha_fin', to);
  if (qtext) q.set('q', qtext);
  window.open(`${API}/ventas/export?${q}`, '_blank');
}

async function loadVentasPage() {
  await crearVistaVentas();
  if (activePage !== 'ventas') return;
  await loadVentas();
}

async function fetchVentasTotal(signal) {
  const res = await api('/ventas?page=1&page_size=1&sort_by=id_venta&sort_order=desc', {
    cache: 'no-store',
    signal: signal || bgSignal(),
  });
  return res?.total ?? 0;
}

function paintVentasTotal(total) {
  const n = fmtNum(total);
  const main = document.getElementById('ventas-total');
  const gen = document.getElementById('gen-ventas-total');
  if (main) main.textContent = n;
  if (gen) gen.textContent = n;
}

async function refreshVentasTotalInUI() {
  try {
    paintVentasTotal(await fetchVentasTotal());
  } catch (e) {
    if (e?.message) toast(e.message, 'error');
  }
}

async function refreshAfterVentasMutation() {
  await refreshVentasTotalInUI();
  if (activePage === 'ventas') await loadVentas();
  else if (activePage === 'dashboard') await loadDashboard();
}

async function loadVentas() {
  if (!vistaVentas) await crearVistaVentas();
  if (!vistaVentas) return;
  await vistaVentas.recargar();
}

const maestraState = {};
const PK = { regiones: 'id_region', paises: 'id_country', 'tipos-producto': 'id_item_type', canales: 'id_channel', prioridades: 'id_priority' };
/** Maestras analíticas de solo lectura (seed del dataset). */
const MAESTRAS_READONLY = new Set(['regiones', 'paises', 'canales']);
let vistasMaestras = {};

const MAESTRA_LABELS = {
  region: 'Región',
  country: 'País',
  id_region: 'Región',
  macro_zona: 'Macro-zona',
  item_type: 'Categoría / tipo de producto',
  unit_price: 'Precio unitario',
  unit_cost: 'Costo unitario',
  sales_channel: 'Canal de venta',
  order_priority: 'Código',
  descripcion: 'Significado',
};

const MAESTRA_MACRO_BY_REGION = {
  1: 'apac', 2: 'apac', 3: 'americas', 4: 'emea', 5: 'emea', 6: 'americas', 7: 'emea', 8: 'americas',
};
const MAESTRA_ZONA_CORTA = { americas: 'Américas', emea: 'EMEA', apac: 'APAC' };
const PRIORIDAD_HINTS = {
  C: 'Crítica — máxima urgencia',
  H: 'Alta — prioridad elevada',
  M: 'Media — plazo estándar',
  L: 'Baja — puede demorarse',
};

function maestraMacroDeRegion(idRegion) {
  if (idRegion == null || idRegion === '') return null;
  return MAESTRA_MACRO_BY_REGION[Number(idRegion)] || null;
}

function maestraNombreRegion(idRegion) {
  if (idRegion == null) return '—';
  return filterCache?.regiones?.find((r) => Number(r.id_region) === Number(idRegion))?.region || `#${idRegion}`;
}

function maestraZonaLabel(idRegion) {
  const m = maestraMacroDeRegion(idRegion);
  return m ? (MAESTRA_ZONA_CORTA[m] || m) : '—';
}

function buildMaestraFiltros(tabla) {
  if (tabla === 'paises') {
    const regOpts = (filterCache?.regiones || [])
      .map((r) => `<option value="${r.id_region}">${esc(r.region)}</option>`).join('');
    return `
      <div class="field"><label>Región</label>
        <select id="paises-region" data-dv-auto title="Filtrar por región analítica">
          <option value="">Todas</option>${regOpts}
        </select>
      </div>
      <div class="field"><label>Macro-zona</label>
        <select id="paises-macro" data-dv-auto title="Américas, EMEA o APAC">
          <option value="">Todas</option>
          <option value="americas">Américas</option>
          <option value="emea">EMEA</option>
          <option value="apac">APAC</option>
        </select>
      </div>`;
  }
  if (tabla === 'regiones') {
    return `
      <div class="field"><label>Macro-zona</label>
        <select id="regiones-macro" data-dv-auto>
          <option value="">Todas</option>
          <option value="americas">Américas</option>
          <option value="emea">EMEA</option>
          <option value="apac">APAC</option>
        </select>
      </div>`;
  }
  if (tabla === 'tipos-producto') {
    return `
      <div class="field"><label>Precio mín.</label>
        <input type="number" id="tipos-pmin" data-dv-auto step="0.01" min="0" placeholder="0"></div>
      <div class="field"><label>Precio máx.</label>
        <input type="number" id="tipos-pmax" data-dv-auto step="0.01" min="0" placeholder="Sin tope"></div>`;
  }
  return '';
}

function maestraCols(tabla, fields) {
  const pk = PK[tabla];
  const idCol = { key: pk, label: 'ID', align: 'center', render: (r) => esc(r[pk]) };

  if (tabla === 'regiones') {
    return [
      idCol,
      { key: 'region', label: 'Región', render: (r) => esc(r.region) },
      { key: 'macro_zona', label: 'Macro-zona', render: (r) => esc(maestraZonaLabel(r.id_region)) },
    ];
  }
  if (tabla === 'paises') {
    return [
      idCol,
      { key: 'country', label: 'País', render: (r) => esc(r.country) },
      { key: 'id_region', label: 'Región', render: (r) => esc(maestraNombreRegion(r.id_region)) },
      { key: 'macro_zona', label: 'Macro-zona', render: (r) => esc(maestraZonaLabel(r.id_region)) },
    ];
  }
  if (tabla === 'prioridades') {
    return [
      idCol,
      { key: 'order_priority', label: 'Código', align: 'center', render: (r) => `<strong>${esc(r.order_priority)}</strong>` },
      {
        key: 'descripcion', label: 'Significado',
        render: (r) => esc(r.descripcion || PRIORIDAD_HINTS[r.order_priority] || '—'),
      },
    ];
  }
  if (tabla === 'tipos-producto') {
    return [
      idCol,
      { key: 'item_type', label: 'Categoría / tipo', render: (r) => esc(r.item_type) },
      { key: 'unit_price', label: 'Precio', align: 'num', render: (r) => fmtMoneyDec(r.unit_price) },
      { key: 'unit_cost', label: 'Costo', align: 'num', render: (r) => fmtMoneyDec(r.unit_cost) },
      {
        key: 'margen', label: 'Margen', align: 'num',
        render: (r) => {
          const p = Number(r.unit_price);
          const c = Number(r.unit_cost);
          if (!p || p <= 0) return '—';
          return `${(((p - c) / p) * 100).toFixed(1)}%`;
        },
      },
    ];
  }
  if (tabla === 'canales') {
    return [idCol, { key: 'sales_channel', label: 'Canal', render: (r) => esc(r.sales_channel) }];
  }
  const def = (c) => ({
    key: c,
    label: MAESTRA_LABELS[c] || c,
    align: c.startsWith('id_') ? 'center' : (c === 'unit_price' || c === 'unit_cost') ? 'num' : '',
    render: (r) => (c === 'unit_price' || c === 'unit_cost') ? fmtMoneyDec(r[c]) : esc(r[c] ?? ''),
  });
  return [idCol, ...fields.filter((f) => f !== pk).map(def)];
}

function maestraResumen(tabla, fields, pk, row) {
  const partes = [`<div><strong>ID:</strong> ${esc(row[pk])}</div>`];
  fields.forEach((c) => {
    let val = row[c];
    if (c === 'id_region') val = maestraNombreRegion(row.id_region);
    else if (c === 'unit_price' || c === 'unit_cost') val = fmtMoneyDec(row[c]);
    else if (c === 'descripcion' && !val) val = PRIORIDAD_HINTS[row.order_priority] || '—';
    else val = val ?? '—';
    partes.push(`<div><strong>${esc(MAESTRA_LABELS[c] || c)}:</strong> ${typeof val === 'string' && c !== 'id_region' ? esc(val) : val}</div>`);
  });
  if (tabla === 'paises' || tabla === 'regiones') {
    partes.push(`<div><strong>Macro-zona:</strong> ${esc(maestraZonaLabel(row.id_region))}</div>`);
  }
  if (tabla === 'tipos-producto') {
    const p = Number(row.unit_price);
    const c = Number(row.unit_cost);
    if (p > 0 && c >= 0) {
      partes.push(`<div><strong>Margen bruto:</strong> ${(((p - c) / p) * 100).toFixed(1)}%</div>`);
    }
  }
  return `<div class="detail-grid">${partes.join('')}</div>`;
}

async function crearVistaMaestra(tabla) {
  const cont = document.getElementById(`vista-${tabla}`);
  if (!cont) return null;
  if (vistasMaestras[tabla]) return vistasMaestras[tabla];
  if (tabla === 'paises' || tabla === 'regiones') await ensureFilters();
  const fields = PAGES[tabla].fields;
  const pk = PK[tabla];
  const st = maestraState[tabla] = maestraState[tabla] || { page: 1, page_size: 25, search: '', total_pages: 1 };
  vistasMaestras[tabla] = createDataView(cont, {
    state: st,
    autoLoad: false,
    buscar: { id: `${tabla}-q`, placeholder: tabla === 'paises' ? 'Nombre del país...' : 'Buscar...' },
    filtrosHtml: buildMaestraFiltros(tabla),
    columnas: maestraCols(tabla, fields),
    cargar: async (s) => {
      if (tabla === 'paises' || tabla === 'regiones') await ensureFilters();
      const q = new URLSearchParams({ page: s.page, page_size: s.page_size });
      const txt = document.getElementById(`${tabla}-q`)?.value?.trim();
      if (txt) q.set('search', txt);
      if (tabla === 'paises') {
        const idReg = document.getElementById('paises-region')?.value;
        const macro = document.getElementById('paises-macro')?.value;
        if (idReg) q.set('id_region', idReg);
        else if (macro) q.set('macro_zona', macro);
      }
      const res = await api(`/maestras/${tabla}/?${q}`);
      let items = res.data || [];
      if (tabla === 'regiones') {
        const macro = document.getElementById('regiones-macro')?.value;
        if (macro) items = items.filter((r) => maestraMacroDeRegion(r.id_region) === macro);
      }
      if (tabla === 'tipos-producto') {
        const pmin = Number(document.getElementById('tipos-pmin')?.value);
        const pmax = Number(document.getElementById('tipos-pmax')?.value);
        if (Number.isFinite(pmin) && pmin > 0) items = items.filter((r) => Number(r.unit_price) >= pmin);
        if (Number.isFinite(pmax) && pmax > 0) items = items.filter((r) => Number(r.unit_price) <= pmax);
      }
      return {
        items,
        total: tabla === 'regiones' || tabla === 'tipos-producto' ? items.length : (res.total ?? items.length),
        page: res.page,
        total_pages: res.total_pages,
      };
    },
    resumen: (r) => maestraResumen(tabla, fields, pk, r),
    titulo: (r) => `${PAGES[tabla].title} #${r[pk]}`,
    key: (r) => r[pk],
    acciones: MAESTRAS_READONLY.has(tabla) ? {
      modificar: null,
      eliminar: null,
      agregar: null,
    } : {
      agregar: () => void abrirModalMaestra(tabla),
      modificar: (row) => void abrirModalMaestra(tabla, row[pk]),
      eliminar: async (row) => {
        await api(`/maestras/${tabla}/${row[pk]}/`, { method: 'DELETE' });
        filterCache = null;
        toast('Registro eliminado');
        await loadMaestra(tabla, fields);
      },
    },
    vacio: 'Sin registros',
    onAfterRender: (el) => {
      if (tabla !== 'paises') return;
      const reg = el.querySelector('#paises-region');
      const macro = el.querySelector('#paises-macro');
      reg?.addEventListener('change', () => { if (reg.value && macro) macro.value = ''; });
      macro?.addEventListener('change', () => { if (macro.value && reg) reg.value = ''; });
    },
  });
  return vistasMaestras[tabla];
}

async function loadMaestra(tabla, fields) {
  const v = await crearVistaMaestra(tabla);
  if (v) await v.recargar();
}

function maestraCampos(tabla, fields, row) {
  return fields.map((f) => {
    const label = MAESTRA_LABELS[f] || f;
    if (tabla === 'paises' && f === 'id_region') {
      return {
        key: f, label, type: 'select', value: row?.[f] ?? '', required: true,
        options: [{ value: '', label: '— Selecciona región —' }].concat(
          (filterCache?.regiones || []).map((r) => ({
            value: r.id_region,
            label: `${r.region} (${maestraZonaLabel(r.id_region)})`,
          })),
        ),
      };
    }
    if (tabla === 'prioridades' && f === 'order_priority') {
      const cod = String(row?.order_priority || '').toUpperCase();
      return {
        key: f, label, type: 'text', maxlength: 1, required: true,
        value: cod,
        placeholder: 'C, H, M o L',
        hint: 'Una letra: C=Crítica, H=Alta, M=Media, L=Baja',
      };
    }
    if (tabla === 'prioridades' && f === 'descripcion') {
      const cod = String(row?.order_priority || '').toUpperCase();
      return {
        key: f, label, type: 'text', maxlength: 160,
        value: row?.descripcion || PRIORIDAD_HINTS[cod] || '',
        placeholder: 'Qué significa esta prioridad en operaciones',
      };
    }
    const numeric = ['unit_price', 'unit_cost'].includes(f);
    return {
      key: f, label, type: numeric ? 'number' : 'text', step: numeric ? '0.01' : undefined,
      min: numeric ? 0.01 : undefined, value: row?.[f] ?? '', required: true,
      hint: f === 'unit_cost' ? 'Debe ser menor o igual al precio unitario' : undefined,
    };
  }).concat(
    tabla === 'paises' ? [{
      key: 'zona_prev', type: 'html',
      value: `<p class="meta"><strong>Macro-zona:</strong> ${esc(maestraZonaLabel(row?.id_region) || '—')} (se calcula de la región)</p>`,
    }] : [],
  );
}

function validarMaestraForm(tabla, v) {
  if (tabla === 'paises') {
    const pais = (v.country || '').trim();
    if (pais.length < 2) { toast('El país debe tener al menos 2 caracteres', 'error'); return false; }
    if (!v.id_region) { toast('Selecciona la región del país', 'error'); return false; }
  }
  if (tabla === 'prioridades') {
    const cod = (v.order_priority || '').trim().toUpperCase();
    if (!/^[A-Z]$/.test(cod)) { toast('La prioridad debe ser una sola letra (A-Z)', 'error'); return false; }
  }
  if (tabla === 'tipos-producto') {
    const price = Number(v.unit_price);
    const cost = Number(v.unit_cost);
    if (!Number.isFinite(price) || price <= 0) { toast('Precio unitario inválido', 'error'); return false; }
    if (!Number.isFinite(cost) || cost <= 0) { toast('Costo unitario inválido', 'error'); return false; }
    if (cost > price) { toast('El costo no puede superar el precio', 'error'); return false; }
  }
  if (tabla === 'regiones' || tabla === 'canales') {
    const txt = (v[tabla === 'regiones' ? 'region' : 'sales_channel'] || '').trim();
    if (txt.length < 2) { toast('El nombre debe tener al menos 2 caracteres', 'error'); return false; }
  }
  return true;
}

async function abrirModalMaestra(tabla, id = null) {
  if (tabla === 'paises' || tabla === 'regiones') await ensureFilters();
  const fields = PAGES[tabla].fields;
  const row = id ? await api(`/maestras/${tabla}/${id}/`) : null;
  uiModal({
    modo: id ? 'Actualizar' : 'Agregar',
    tituloExtra: PAGES[tabla].title,
    ancho: tabla === 'tipos-producto' || tabla === 'paises' ? 'md' : 'sm',
    campos: maestraCampos(tabla, fields, row),
    onReady: () => {
      if (tabla !== 'paises') return;
      const sel = document.getElementById('uf-id_region');
      const upd = () => {
        const hint = document.querySelector('#uf-zona_prev .meta, #uf-zona_prev');
        if (hint) {
          hint.innerHTML = `<strong>Macro-zona:</strong> ${esc(maestraZonaLabel(sel?.value) || '—')} (automática según región)`;
        }
      };
      sel?.addEventListener('change', upd);
    },
    onAceptar: async (v) => {
      if (!validarMaestraForm(tabla, v)) return false;
      const body = {};
      fields.forEach((f) => {
        const val = v[f];
        if (f === 'order_priority') body[f] = String(val || '').trim().toUpperCase();
        else if (['unit_price', 'unit_cost', 'id_region'].includes(f)) body[f] = Number(val);
        else body[f] = typeof val === 'string' ? val.trim() : val;
      });
      if (tabla === 'prioridades' && v.descripcion != null) body.descripcion = String(v.descripcion).trim();
      if (id) {
        await api(`/maestras/${tabla}/${id}/`, { method: 'PUT', body });
      } else {
        await api(`/maestras/${tabla}/`, { method: 'POST', body });
      }
      filterCache = null;
      toast('Guardado');
      await loadMaestra(tabla, fields);
    },
  });
}

function formatGenResult(res) {
  const n = res.registros ?? res.inserted ?? 0;
  const t = res.tiempo_segundos ?? 0;
  const rps = res.registros_por_segundo ?? (t > 0 ? n / t : 0);
  return `✅ ${fmtNum(n)} registros en ${t.toLocaleString('es-CL', { minimumFractionDigits: 3, maximumFractionDigits: 3 })} s (${Number(rps).toLocaleString('es-CL', { maximumFractionDigits: 0 })} reg/s)`;
}

function setGenButtonLoading(btnId, loading, idleLabel) {
  const btn = document.getElementById(btnId);
  if (!btn) return;
  const spinner = btn.querySelector('.btn-spinner');
  const label = btn.querySelector('.btn-label');
  btn.disabled = loading;
  if (spinner) spinner.hidden = !loading;
  if (label) label.textContent = loading ? `${idleLabel}…` : idleLabel;
}

function paintGenResult(outId, text, success) {
  const el = document.getElementById(outId);
  if (!el) return;
  el.className = success ? 'gen-result success' : 'gen-result';
  el.textContent = text;
}

let _jobProgressTimer = null;

function startJobProgress(outId, runningLabel) {
  const t0 = Date.now();
  const tick = () => {
    const s = Math.floor((Date.now() - t0) / 1000);
    paintGenResult(outId, `${runningLabel}… ${s}s (operación larga, no cierres la pestaña)`, false);
  };
  tick();
  _jobProgressTimer = setInterval(tick, 1000);
}

function stopJobProgress() {
  if (_jobProgressTimer) {
    clearInterval(_jobProgressTimer);
    _jobProgressTimer = null;
  }
}

function shouldGoToVentasAfterGen() {
  return document.getElementById('gen-goto-ventas')?.checked !== false;
}

function hideGenOpOverlay() {
  const overlay = document.getElementById('gen-op-overlay');
  if (!overlay) return;
  overlay.hidden = true;
}

function showGenOpOverlay(msg, success, { canViewVentas = false } = {}) {
  const overlay = document.getElementById('gen-op-overlay');
  const card = document.getElementById('gen-op-card');
  const message = document.getElementById('gen-op-message');
  const btnVentas = document.getElementById('gen-op-ventas');
  if (!overlay || !card || !message) return;

  message.textContent = msg;
  card.className = `gen-op-card ${success ? 'success' : 'error'}`;
  if (btnVentas) btnVentas.hidden = !canViewVentas;
  overlay.hidden = false;
}

function showGeneradorSuccess(outId, msg, data) {
  const n = data?.registros ?? data?.inserted ?? 0;
  paintGenResult(outId, msg, true);
  showGenOpOverlay(msg, true, { canViewVentas: n > 0 });
  toast(msg, 'success');
}

/** Tras generar/importar: ir a Ventas al instante si el checkbox está activo. */
async function finishGeneradorPostSuccess(data) {
  const goVentas = shouldGoToVentasAfterGen();

  try {
    if (goVentas) {
      hideGenOpOverlay();
      ventasState.page = 1;
      if (data?.total_ventas != null) paintVentasTotal(data.total_ventas);
      showPage('ventas');
      await loadVentasPage();
      return;
    }
    if (data?.total_ventas != null) paintVentasTotal(data.total_ventas);
    if (activePage === 'generador') {
      const el = document.getElementById('gen-ventas-total');
      if (el && data?.total_ventas != null) el.textContent = fmtNum(data.total_ventas);
    }
    if (activePage === 'dashboard') void loadDashboard();
    if (activePage === 'ventas') {
      ventasState.page = 1;
      await loadVentas();
    }
  } catch (e) {
    if (e?.name !== 'AbortError' && e?.message) toast(e.message, 'error');
  }
}

function initGenerador() {
  const cb = document.getElementById('gen-goto-ventas');
  if (cb) {
    const saved = localStorage.getItem('globtrade-goto-ventas');
    if (saved !== null) cb.checked = saved === '1';
  }
  void refreshVentasTotalInUI();
}

async function runGeneradorJob(outId, btnId, idleLabel, path, runningLabel) {
  setGenButtonLoading(btnId, true, runningLabel);
  hideGenOpOverlay();
  _jobActive = true;
  resetPageAbort();
  abortAllNetworkWork();
  await waitForNetworkIdle(2000);
  startJobProgress(outId, runningLabel);
  const jobAc = new AbortController();
  _jobAbort = jobAc;
  _inflight.add(jobAc);
  try {
    const res = await fetch(`${API}${path}`, {
      method: 'POST',
      cache: 'no-store',
      signal: jobAc.signal,
    });
    const ct = res.headers.get('content-type') || '';
    const data = ct.includes('application/json') ? await res.json() : {};
    if (!res.ok) throw new Error(formatApiError(data, res.statusText));
    const msg = formatGenResult(data);
    showGeneradorSuccess(outId, msg, data);
    if (data?.total_ventas != null) paintVentasTotal(data.total_ventas);
    await finishGeneradorPostSuccess(data);
    return data;
  } catch (e) {
    if (e?.name !== 'AbortError') {
      paintGenResult(outId, e.message, false);
      showGenOpOverlay(e.message, false, { canViewVentas: false });
      toast(e.message, 'error');
    }
  } finally {
    stopJobProgress();
    _inflight.delete(jobAc);
    if (_jobAbort === jobAc) _jobAbort = null;
    _jobActive = false;
    setGenButtonLoading(btnId, false, idleLabel);
  }
}

async function runGenerador() {
  const btn = document.getElementById('gen-btn');
  if (btn?.disabled) return;
  const cantidad = Number(document.getElementById('gen-cantidad').value) || 100000;
  if (cantidad > 1_000_000) {
    toast('El máximo permitido es 1.000.000 registros', 'error');
    return;
  }
  await runGeneradorJob(
    'gen-result', 'gen-btn', 'Generar ventas',
    `/generador/generar?cantidad=${cantidad}`, 'Generando',
  );
}

async function runImportParquet() {
  const btn = document.getElementById('import-parquet-btn');
  if (btn?.disabled) return;
  await runGeneradorJob(
    'import-result', 'import-parquet-btn', 'Importar ventas.parquet',
    '/etl/importar-parquet', 'Importando',
  );
}

async function runEtlCsvUpload() {
  const btn = document.getElementById('etl-csv-btn');
  const input = document.getElementById('etl-csv-file');
  const out = document.getElementById('etl-csv-result');
  const file = input?.files?.[0];
  if (!file) { toast('Selecciona un archivo CSV', 'error'); return; }
  if (btn?.disabled) return;
  setGenButtonLoading('etl-csv-btn', true, 'Cargando…');
  if (out) out.textContent = '';
  try {
    const fd = new FormData();
    fd.append('file', file);
    const token = localStorage.getItem('gt_token');
    const res = await fetch('/api/etl/upload', {
      method: 'POST',
      headers: token ? { Authorization: `Bearer ${token}` } : {},
      body: fd,
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.detail || data.message || res.statusText);
    const msg = `Insertados: ${data.inserted ?? 0}, rechazados: ${data.rejected ?? 0}`;
    if (out) out.textContent = msg;
    toast('CSV procesado');
    if (document.getElementById('gen-goto-ventas')?.checked) navigate('ventas');
  } catch (e) {
    toast(e.message, 'error');
    if (out) out.textContent = e.message;
  } finally {
    setGenButtonLoading('etl-csv-btn', false);
  }
}

document.getElementById('etl-csv-btn')?.addEventListener('click', () => void runEtlCsvUpload());

/* Truncate modal */
const truncateOverlay = document.getElementById('truncate-overlay');
const truncateInput = document.getElementById('truncate-confirm');
const truncateOk = document.getElementById('truncate-ok');

document.getElementById('truncate-cancel')?.addEventListener('click', () => truncateOverlay.classList.remove('open'));
truncateInput?.addEventListener('input', () => {
  truncateOk.disabled = truncateInput.value.trim() !== 'CONFIRMAR';
});
truncateOk?.addEventListener('click', async () => {
  if (truncateInput.value.trim() !== 'CONFIRMAR') return;
  truncateOk.disabled = true;
  try {
    cancelBackgroundRequests();
    resetPageAbort();
    const res = await api('/ventas/truncate?confirm=true', { method: 'DELETE' });
    truncateOverlay.classList.remove('open');
    ventasState.page = 1;
    if (vistaVentas) await vistaVentas.recargar();
    paintVentasTotal(0);
    toast(`Eliminados ${fmtNum(res.eliminados)} registros. Ve a Generador / ETL para importar de nuevo.`);
  } catch (e) {
    toast(e.message, 'error');
  } finally {
    truncateOk.disabled = false;
  }
});

document.getElementById('dash-apply')?.addEventListener('click', () => {
  if (!validateDateRange('dash-from', 'dash-to')) return;
  void loadDashboard();
});
document.getElementById('dash-clear')?.addEventListener('click', () => {
  ['dash-from', 'dash-to', 'dash-region', 'dash-origen'].forEach((id) => {
    const el = document.getElementById(id);
    if (el) el.value = '';
  });
  capDateInputs(document.getElementById('page-dashboard'));
  void loadDashboard();
});
document.getElementById('dash-reintegrar')?.addEventListener('click', async () => {
  try {
    const res = await api('/dashboard/reintegrar-pedidos', { method: 'POST' });
    toast(`Reintegración: ${res.insertadas} líneas nuevas (${res.procesados} pedidos revisados)`);
    await loadDashboard();
  } catch (e) {
    toast(e.message, 'error');
  }
});
document.getElementById('gen-btn')?.addEventListener('click', runGenerador);
document.getElementById('import-parquet-btn')?.addEventListener('click', runImportParquet);
document.getElementById('gen-goto-ventas')?.addEventListener('change', (e) => {
  localStorage.setItem('globtrade-goto-ventas', e.target.checked ? '1' : '0');
});
document.getElementById('gen-op-close')?.addEventListener('click', hideGenOpOverlay);
document.getElementById('gen-op-ventas')?.addEventListener('click', () => {
  hideGenOpOverlay();
  ventasState.page = 1;
  navigate('ventas');
});
document.getElementById('gen-op-overlay')?.addEventListener('click', (e) => {
  if (e.target.id === 'gen-op-overlay') hideGenOpOverlay();
});

async function applyBrandLogo() {
  try {
    const brand = await api('/configuracion/branding');
    const mark = document.querySelector('.topnav-brand .brand-mark');
    if (!mark) return;
    if (brand?.logo_url) {
      mark.innerHTML = `<img src="${brand.logo_url}" alt="Logo">`;
    }
  } catch {
    /* logo opcional */
  }
}

async function bootApp(initialPage) {
  initTheme();
  if (typeof initTopNav === 'function') initTopNav();
  bindNavItems();
  buildPagePermiso();
  void applyBrandLogo();
  setInterval(() => {
    if (document.visibilityState !== 'visible') return;
    void applyBrandLogo();
  }, 120000);
  let page = (initialPage && PAGES[initialPage]) ? initialPage : (pageFromUrl() || 'dashboard');
  await cargarPermisosUsuario();
  if (!mayAcceder(page) || !PAGES[page]) {
    page = primeraPaginaPermitida();
  }
  showPage(page);
  initNotificacionesUI();
  void ensureFilters().catch(() => {});
  void loadPageData(page).catch((err) => safeToastError(err));
}

/** Navega según el enlace de una notificación del ERP. */
function followAdminNotifLink(link) {
  if (!link) return false;
  if (link.startsWith('/?page=')) {
    const page = new URLSearchParams(link.split('?')[1] || '').get('page');
    if (page && PAGES[page] && mayAcceder(page)) {
      navigate(page);
      return true;
    }
  }
  const portalPath = link.startsWith('/pages/') ? link : null;
  if (portalPath) {
    if (/catalogo|producto|favoritos|paquete/.test(portalPath)) {
      if (PAGES.catalogo) {
        navigate('catalogo');
        return true;
      }
    }
    if (/mis-pedidos|pedido/.test(portalPath)) {
      if (PAGES.pedidos) {
        navigate('pedidos');
        return true;
      }
    }
    const portalOrigin = window.location.origin.replace(':8000', ':8001');
    window.open(`${portalOrigin}${portalPath}`, '_blank', 'noopener');
    return true;
  }
  if (link.startsWith('http')) {
    window.open(link, '_blank', 'noopener');
    return true;
  }
  return false;
}

function initNotificacionesUI() {
  const bell = document.getElementById('notif-bell');
  const panel = document.getElementById('notif-panel');
  const list = document.getElementById('notif-list');
  const countEl = document.getElementById('notif-count');
  if (!bell || !panel || !list) return;

  const TIPO_META = {
    stock: { label: 'Stock', cls: 'stock' },
    compra: { label: 'Compras', cls: 'compra' },
    pedido: { label: 'Pedidos', cls: 'pedido' },
    logistica: { label: 'Logística', cls: 'logistica' },
    info: { label: 'Aviso', cls: 'info' },
  };

  function fmtFechaNotif(f) {
    const s = String(f || '').replace('T', ' ');
    return s.slice(0, 16);
  }

  async function refresh() {
    try {
      const data = await api('/notificaciones?limit=40', { cache: 'no-store' });
      const n = Number(data.no_leidas || 0);
      if (countEl) {
        if (n > 0) {
          countEl.hidden = false;
          countEl.removeAttribute('hidden');
          countEl.textContent = n > 99 ? '99+' : String(n);
        } else {
          countEl.textContent = '';
          countEl.hidden = true;
          countEl.setAttribute('hidden', '');
        }
      }
      const items = data.items || [];
      list.innerHTML = items.length
        ? items.map((it) => {
          const meta = TIPO_META[it.tipo] || TIPO_META.info;
          return `
          <div class="notif-item ${it.leida ? '' : 'unread'}${it.link ? ' notif-clickable' : ''}" data-id="${it.id_notif}" data-link="${esc(it.link || '')}">
            <div class="notif-item-top">
              <span class="notif-chip notif-chip-${meta.cls}">${meta.label}</span>
              <button type="button" class="notif-dismiss" data-dismiss="${it.id_notif}" title="Quitar">×</button>
            </div>
            <strong>${esc(it.titulo)}</strong>
            <div class="notif-body">${esc(it.cuerpo || '')}</div>
            <div class="meta">${esc(fmtFechaNotif(it.fecha))}${it.link ? ' · Ir →' : ''}</div>
          </div>`;
        }).join('')
        : `<div class="notif-empty-state">
            <p class="notif-empty">Bandeja vacía</p>
            <p class="meta">Aquí verás stock bajo, órdenes aprobadas, compras y cambios de pedidos.</p>
          </div>`;
    } catch (e) {
      if (!isAbortError(e)) { /* silencioso */ }
    }
  }

  bell.addEventListener('click', (e) => {
    e.stopPropagation();
    panel.classList.toggle('open');
    if (panel.classList.contains('open')) void refresh();
  });
  document.addEventListener('click', () => panel.classList.remove('open'));
  panel.addEventListener('click', (e) => e.stopPropagation());

  document.getElementById('notif-leer-todas')?.addEventListener('click', async () => {
    try {
      await api('/notificaciones/leer-todas', { method: 'POST' });
      void refresh();
    } catch (e) { safeToastError(e); }
  });
  document.getElementById('notif-limpiar')?.addEventListener('click', async () => {
    try {
      await api('/notificaciones/limpiar', { method: 'POST' });
      toast('Bandeja liberada');
      void refresh();
    } catch (e) { safeToastError(e); }
  });

  list.addEventListener('click', async (e) => {
    const dismiss = e.target.closest('[data-dismiss]');
    if (dismiss) {
      e.stopPropagation();
      try {
        await api(`/notificaciones/${dismiss.dataset.dismiss}`, { method: 'DELETE' });
        void refresh();
      } catch (err) { safeToastError(err); }
      return;
    }
    const item = e.target.closest('.notif-item[data-id]');
    if (!item) return;
    try {
      await api(`/notificaciones/${item.dataset.id}/leida`, { method: 'POST' });
      const link = item.dataset.link;
      if (link && followAdminNotifLink(link)) {
        panel.classList.remove('open');
      }
      void refresh();
    } catch (err) { safeToastError(err); }
  });

  void refresh();
  setInterval(() => { if (document.visibilityState === 'visible') void refresh(); }, 45000);
}

window.addEventListener('popstate', (ev) => {
  const page = ev.state?.page || pageFromUrl() || 'dashboard';
  if (page && PAGES[page]) navigate(page);
});

window.addEventListener('error', (ev) => {
  const msg = String(ev.message || '');
  if (/aborted|script error/i.test(msg)) return;
  console.error(ev.error || ev.message);
  toast(`Error: ${ev.message}`, 'error');
});

window.addEventListener('unhandledrejection', (ev) => {
  if (isAbortError(ev.reason)) {
    ev.preventDefault();
    return;
  }
});
