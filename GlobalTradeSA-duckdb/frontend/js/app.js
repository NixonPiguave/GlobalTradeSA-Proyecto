const API = '/api';
let charts = {};
let filterCache = null;

const PAGES = {
  dashboard: { title: 'Dashboard Ejecutivo', load: loadDashboard },
  ventas: { title: 'Ventas', load: loadVentasPage },
  regiones: { title: 'Regiones', maestra: 'regiones', fields: ['region'] },
  paises: { title: 'Países', maestra: 'paises', fields: ['country', 'id_region'] },
  'tipos-producto': { title: 'Tipos de Producto', maestra: 'tipos-producto', fields: ['item_type', 'unit_price', 'unit_cost'] },
  canales: { title: 'Canales', maestra: 'canales', fields: ['sales_channel'] },
  prioridades: { title: 'Prioridades', maestra: 'prioridades', fields: ['order_priority'] },
  generador: { title: 'Generador / ETL' },
};

const fmtMoney = (n) => new Intl.NumberFormat('es-CL', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 }).format(n || 0);
const fmtMoneyDec = (n) => new Intl.NumberFormat('es-CL', { style: 'currency', currency: 'USD', minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(n || 0);
const fmtNum = (n) => new Intl.NumberFormat('es-CL').format(n || 0);
const fmtPct = (n) => (n == null ? '—' : `${Number(n).toFixed(2)}%`);

function formatApiError(err, statusText) {
  const detail = err?.detail;
  if (typeof detail === 'string') return detail;
  if (detail?.message) {
    const fields = detail.fields;
    if (Array.isArray(fields) && fields.length) {
      return `${detail.message}: ${fields.join(', ')}`;
    }
    return detail.message;
  }
  if (Array.isArray(detail) && detail[0]?.msg) return detail[0].msg;
  return err?.message || statusText || 'Error de API';
}

const _inflight = new Set();
let _jobAbort = null;
let _jobActive = false;
let pageAbort = new AbortController();

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
  const { cache, signal, ...fetchOpts } = opts;
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
  sel.innerHTML = `<option value="">${emptyLabel}</option>` +
    items.map((it) => `<option value="${it[valueKey]}">${it[labelKey]}</option>`).join('');
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
  if (filterCache) return filterCache;
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
      fillSelect('v-region', filterCache.regiones, 'region', 'region');
      fillSelect('v-item_type', filterCache.tipos, 'item_type', 'item_type');
      fillSelect('v-sales_channel', filterCache.canales, 'sales_channel', 'sales_channel');
      fillSelect('v-order_priority', filterCache.prioridades, 'order_priority', 'order_priority');
      fillSelect('dash-region', filterCache.regiones, 'region', 'region', 'Todas');
      updateCountrySelect();
      return filterCache;
    })().finally(() => { _filtersInflight = null; });
  }
  return _filtersInflight;
}

function updateCountrySelect() {
  const regionName = document.getElementById('v-region')?.value;
  let paises = filterCache?.paises || [];
  if (regionName) {
    const reg = filterCache.regiones.find((r) => r.region === regionName);
    if (reg) paises = paises.filter((p) => p.id_region === reg.id_region);
  }
  fillSelect('v-country', paises, 'country', 'country');
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

function showPage(page) {
  if (!page || !PAGES[page]) return;
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
  document.getElementById('sidebar')?.classList.remove('open');
}

/** Carga datos de la página (la UI ya cambió con showPage). */
async function loadPageData(page) {
  if (_jobActive) return;
  const cfg = PAGES[page];
  if (!cfg) return;
  if (page === 'generador') {
    initGenerador();
    return;
  }
  if (cfg.load) await cfg.load();
  else if (cfg.maestra) await loadMaestra(cfg.maestra, cfg.fields);
}

async function navigate(page) {
  if (!page || !PAGES[page]) return;
  showPage(page);
  try {
    await loadPageData(page);
  } catch (e) {
    if (e?.name !== 'AbortError' && e?.message) toast(e.message, 'error');
  }
}

document.querySelectorAll('.nav-item').forEach((btn) => {
  btn.addEventListener('click', (e) => {
    e.preventDefault();
    const page = btn.dataset.page;
    if (!page) return;
    showPage(page);
    void loadPageData(page).catch((err) => {
      if (err?.name !== 'AbortError' && err?.message) toast(err.message, 'error');
    });
  });
});
const SIDEBAR_KEY = 'globtrade-sidebar-collapsed';

(function initSidebarState() {
  if (localStorage.getItem(SIDEBAR_KEY) === '1') {
    document.body.classList.add('sidebar-collapsed');
  }
})();

document.getElementById('menu-toggle')?.addEventListener('click', () => {
  const isMobile = window.matchMedia('(max-width: 900px)').matches;
  if (isMobile) {
    document.getElementById('sidebar').classList.toggle('open');
  } else {
    const collapsed = document.body.classList.toggle('sidebar-collapsed');
    localStorage.setItem(SIDEBAR_KEY, collapsed ? '1' : '0');
  }
});
document.getElementById('v-region')?.addEventListener('change', updateCountrySelect);

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

let CHART_COLORS = { ...THEME_CHART.dark };

function getCurrentTheme() {
  const t = document.documentElement.getAttribute('data-theme');
  return t === 'light' ? 'light' : 'dark';
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
  cancelDashboardLoad();
  const ac = new AbortController();
  dashboardAbort = ac;
  const { signal } = ac;

  const q = new URLSearchParams();
  const from = document.getElementById('dash-from')?.value;
  const to = document.getElementById('dash-to')?.value;
  const region = document.getElementById('dash-region')?.value;
  if (from) q.set('fecha_inicio', from);
  if (to) q.set('fecha_fin', to);
  if (region) q.set('region', region);

  try {
    await ensureFilters();
    if (signal.aborted || activePage !== 'dashboard') return;

    const kpis = await api(`/dashboard/kpis?${q}`, { signal });
    if (signal.aborted || activePage !== 'dashboard') return;

    const margen = kpis.total_revenue > 0 ? (kpis.total_profit / kpis.total_revenue) * 100 : 0;
    document.getElementById('kpi-revenue').textContent = fmtMoney(kpis.total_revenue);
    document.getElementById('kpi-profit').textContent = fmtMoney(kpis.total_profit);
    document.getElementById('kpi-profit').className = `value ${kpis.total_profit >= 0 ? 'profit' : 'loss'}`;
    document.getElementById('kpi-margin').textContent = fmtPct(margen);
    document.getElementById('kpi-units').textContent = fmtNum(kpis.units_sold);

    const [chartsData, top] = await Promise.all([
      api(`/dashboard/charts?${q}`, { signal }),
      api(`/dashboard/top-paises?${q}`, { signal }),
    ]);
    if (signal.aborted || activePage !== 'dashboard') return;

    renderBarChart('chart-region', chartsData.por_region);
    renderBarChart('chart-canal', chartsData.por_canal);
    renderBarChart('chart-item', chartsData.por_item_type);
    renderRevenueProfitChart('chart-rp-product', chartsData.producto_revenue_profit || []);
    renderLineChart('chart-mes', chartsData.ventas_por_mes || []);
    renderDoughnutChart('chart-dona-canal', chartsData.por_canal || []);
    renderHorizontalBar('chart-top10-pais', chartsData.top10_paises_revenue || []);

    document.querySelector('#top-paises-body').innerHTML = (top || []).map((r) => `
      <tr>
        <td title="${r.country}">${r.country}</td>
        <td title="${r.region}">${r.region}</td>
        <td class="num text-profit">${fmtMoney(r.total_profit)}</td>
        <td class="num">${fmtMoney(r.total_revenue)}</td>
        <td class="num">${fmtPct(r.margen_pct)}</td>
      </tr>`).join('') || '<tr><td colspan="5">Sin datos</td></tr>';

    setQueryTime('dash-query-time', chartsData);
  } catch (e) {
    if (e?.name === 'AbortError') return;
    toast(e.message, 'error');
  } finally {
    if (dashboardAbort === ac) dashboardAbort = null;
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

let ventasState = { page: 1, page_size: 50 };

function renderVentasTable(res) {
  const tbody = document.querySelector('#ventas-body');
  if (!tbody) return;
  const rows = res?.data || [];
  tbody.innerHTML = rows.length ? rows.map((r) => `
      <tr>
        <td class="num">${r.id_venta}</td>
        <td>${r.order_id}</td><td>${r.region}</td><td>${r.country}</td>
        <td>${r.item_type}</td><td>${r.sales_channel}</td><td>${r.order_priority}</td>
        <td>${r.order_date}</td><td>${r.ship_date}</td>
        <td class="num">${fmtNum(r.units_sold)}</td>
        <td class="num">${fmtMoneyDec(r.unit_price)}</td>
        <td class="num">${fmtMoneyDec(r.unit_cost)}</td>
        <td class="num">${fmtMoney(r.total_revenue)}</td>
        <td class="num">${fmtMoney(r.total_cost)}</td>
        <td class="num text-profit">${fmtMoney(r.total_profit)}</td>
        <td>
          <button class="btn btn-secondary" data-venta-edit="${r.id_venta}">Editar</button>
          <button class="btn btn-danger" data-venta-del="${r.id_venta}">Eliminar</button>
        </td>
      </tr>`).join('') : '<tr><td colspan="16">Sin registros</td></tr>';
  tbody.querySelectorAll('[data-venta-edit]').forEach((b) =>
    b.addEventListener('click', () => openVentaModal(Number(b.dataset.ventaEdit))));
  tbody.querySelectorAll('[data-venta-del]').forEach((b) =>
    b.addEventListener('click', () => deleteVenta(Number(b.dataset.ventaDel))));
  const totalEl = document.getElementById('ventas-total');
  const pageEl = document.getElementById('ventas-page-info');
  if (totalEl) totalEl.textContent = fmtNum(res?.total ?? 0);
  if (pageEl) pageEl.textContent = `Página ${res?.page ?? ventasState.page}`;
  setQueryTime('ventas-query-time', res);
}

function clearVentasTable() {
  renderVentasTable({ data: [], total: 0, page: 1 });
}

async function loadVentasPage() {
  await ensureFilters();
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
  const q = new URLSearchParams({
    page: ventasState.page,
    page_size: ventasState.page_size,
    sort_by: 'order_id',
    sort_order: 'desc',
  });
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
  if (activePage !== 'ventas') return;
  renderVentasTable(res);
  paintVentasTotal(res?.total ?? 0);
}

const maestraState = {};
const PK = { regiones: 'id_region', paises: 'id_country', 'tipos-producto': 'id_item_type', canales: 'id_channel', prioridades: 'id_priority' };

async function loadMaestra(tabla, fields) {
  if (!maestraState[tabla]) maestraState[tabla] = { page: 1, page_size: 25, search: '' };
  const st = maestraState[tabla];
  const q = new URLSearchParams({ page: st.page, page_size: st.page_size });
  if (st.search) q.set('search', st.search);

  try {
    const res = await api(`/maestras/${tabla}/?${q}`);
    const pk = PK[tabla];
    const cols = [pk, ...fields];
    document.querySelector(`#maestra-${tabla}-head`).innerHTML =
      cols.map((c) => `<th>${c}</th>`).join('') + '<th></th>';
    const tbody = document.querySelector(`#maestra-${tabla}-body`);
    tbody.innerHTML = (res.data || []).map((row) => `
      <tr>${cols.map((c) => `<td>${row[c] ?? ''}</td>`).join('')}
        <td>
          <button class="btn btn-secondary" data-edit="${tabla}" data-id="${row[pk]}">Editar</button>
          <button class="btn btn-danger" data-del="${tabla}" data-id="${row[pk]}">Eliminar</button>
        </td></tr>`).join('') || `<tr><td colspan="${cols.length + 1}">Sin registros</td></tr>`;
    document.querySelector(`#maestra-${tabla}-total`).textContent = fmtNum(res.total);
    setQueryTime(`maestra-${tabla}-time`, res);
    tbody.querySelectorAll('[data-edit]').forEach((b) =>
      b.addEventListener('click', () => { void openMaestraModal(tabla, fields, b.dataset.id); }));
    tbody.querySelectorAll('[data-del]').forEach((b) =>
      b.addEventListener('click', () => deleteMaestra(tabla, b.dataset.id)));
  } catch (e) {
    toast(e.message, 'error');
  }
}

function updateVentaModalCountries() {
  const regionName = document.getElementById('vf-region')?.value;
  let paises = filterCache?.paises || [];
  if (regionName) {
    const reg = filterCache.regiones.find((r) => r.region === regionName);
    if (reg) paises = paises.filter((p) => p.id_region === reg.id_region);
  }
  const sel = document.getElementById('vf-country');
  if (!sel) return;
  const current = sel.value;
  sel.innerHTML = '<option value="">—</option>' +
    paises.map((p) => `<option value="${p.country}">${p.country}</option>`).join('');
  if ([...sel.options].some((o) => o.value === current)) sel.value = current;
}

const MAESTRA_LABELS = {
  region: 'Región',
  country: 'País',
  id_region: 'Región',
  item_type: 'Tipo de producto',
  unit_price: 'Precio unitario',
  unit_cost: 'Costo unitario',
  sales_channel: 'Canal',
  order_priority: 'Prioridad',
};

function getVentaUnitRates() {
  const item = document.getElementById('vf-item_type')?.value;
  const tipo = filterCache?.tipos?.find((t) => t.item_type === item);
  if (!tipo) return null;
  return { unit_price: Number(tipo.unit_price), unit_cost: Number(tipo.unit_cost) };
}

function refreshVentaPricingPreview() {
  const rates = getVentaUnitRates();
  const units = Math.max(0, Number(document.getElementById('vf-units_sold')?.value) || 0);
  const upEl = document.getElementById('vf-preview-unit-price');
  const ucEl = document.getElementById('vf-preview-unit-cost');
  const revEl = document.getElementById('vf-preview-revenue');
  const costEl = document.getElementById('vf-preview-cost');
  const profEl = document.getElementById('vf-preview-profit');
  if (!rates) {
    [upEl, ucEl, revEl, costEl, profEl].forEach((el) => { if (el) el.textContent = '—'; });
    return;
  }
  const revenue = Math.round(rates.unit_price * units * 100) / 100;
  const cost = Math.round(rates.unit_cost * units * 100) / 100;
  const profit = Math.round((revenue - cost) * 100) / 100;
  if (upEl) upEl.textContent = fmtMoneyDec(rates.unit_price);
  if (ucEl) ucEl.textContent = fmtMoneyDec(rates.unit_cost);
  if (revEl) revEl.textContent = fmtMoney(revenue);
  if (costEl) costEl.textContent = fmtMoney(cost);
  if (profEl) {
    profEl.textContent = fmtMoney(profit);
    profEl.className = `venta-preview-value ${profit >= 0 ? 'profit' : 'loss'}`;
  }
}

async function openVentaModal(idVenta = null) {
  await ensureFilters();
  const modal = document.getElementById('modal');
  modal.dataset.mode = 'venta';
  modal.dataset.tabla = '';
  modal.dataset.id = idVenta ? String(idVenta) : '';
  document.getElementById('modal-title').textContent = idVenta ? 'Editar venta' : 'Nueva venta';
  document.getElementById('modal-form').innerHTML = `
    <div class="field"><label for="vf-order_id">Order ID</label><input id="vf-order_id" type="number" required></div>
    <div class="field"><label for="vf-region">Región</label>
      <select id="vf-region"><option value="">—</option>
        ${filterCache.regiones.map((r) => `<option value="${r.region}">${r.region}</option>`).join('')}
      </select></div>
    <div class="field"><label for="vf-country">País</label><select id="vf-country"><option value="">—</option></select></div>
    <div class="field"><label for="vf-item_type">Producto</label>
      <select id="vf-item_type"><option value="">—</option>
        ${filterCache.tipos.map((t) => `<option value="${t.item_type}">${t.item_type}</option>`).join('')}
      </select></div>
    <div class="field"><label for="vf-sales_channel">Canal</label>
      <select id="vf-sales_channel"><option value="">—</option>
        ${filterCache.canales.map((c) => `<option value="${c.sales_channel}">${c.sales_channel}</option>`).join('')}
      </select></div>
    <div class="field"><label for="vf-order_priority">Prioridad</label>
      <select id="vf-order_priority"><option value="">—</option>
        ${filterCache.prioridades.map((p) => `<option value="${p.order_priority}">${p.order_priority}</option>`).join('')}
      </select></div>
    <div class="field"><label for="vf-order_date">Fecha pedido</label><input id="vf-order_date" type="date" required></div>
    <div class="field"><label for="vf-ship_date">Fecha envío</label><input id="vf-ship_date" type="date" required></div>
    <div class="field"><label for="vf-units_sold">Unidades</label><input id="vf-units_sold" type="number" min="1" required></div>
    <div class="venta-pricing-panel">
      <p class="venta-pricing-hint">Precio y costo unitarios desde <strong>Tipos de producto</strong>; los totales se recalculan al cambiar unidades o producto.</p>
      <div class="venta-pricing-grid">
        <div><span class="venta-preview-label">Precio unit.</span><span class="venta-preview-value" id="vf-preview-unit-price">—</span></div>
        <div><span class="venta-preview-label">Costo unit.</span><span class="venta-preview-value" id="vf-preview-unit-cost">—</span></div>
        <div><span class="venta-preview-label">Ingresos</span><span class="venta-preview-value" id="vf-preview-revenue">—</span></div>
        <div><span class="venta-preview-label">Costo total</span><span class="venta-preview-value" id="vf-preview-cost">—</span></div>
        <div class="venta-pricing-wide"><span class="venta-preview-label">Profit</span><span class="venta-preview-value profit" id="vf-preview-profit">—</span></div>
      </div>
    </div>`;
  document.getElementById('vf-region')?.addEventListener('change', updateVentaModalCountries);
  document.getElementById('vf-item_type')?.addEventListener('change', refreshVentaPricingPreview);
  document.getElementById('vf-units_sold')?.addEventListener('input', refreshVentaPricingPreview);
  updateVentaModalCountries();
  if (idVenta) {
    const row = await api(`/ventas/${idVenta}`);
    document.getElementById('vf-order_id').value = row.order_id;
    document.getElementById('vf-region').value = row.region;
    updateVentaModalCountries();
    document.getElementById('vf-country').value = row.country;
    document.getElementById('vf-item_type').value = row.item_type;
    document.getElementById('vf-sales_channel').value = row.sales_channel;
    document.getElementById('vf-order_priority').value = row.order_priority;
    document.getElementById('vf-order_date').value = String(row.order_date).slice(0, 10);
    document.getElementById('vf-ship_date').value = String(row.ship_date).slice(0, 10);
    document.getElementById('vf-units_sold').value = row.units_sold;
  }
  refreshVentaPricingPreview();
  document.getElementById('modal-overlay').classList.add('open');
}

async function saveVenta() {
  const modal = document.getElementById('modal');
  const id = modal.dataset.id;
  const body = {
    order_id: Number(document.getElementById('vf-order_id').value),
    region: document.getElementById('vf-region').value,
    country: document.getElementById('vf-country').value,
    item_type: document.getElementById('vf-item_type').value,
    sales_channel: document.getElementById('vf-sales_channel').value,
    order_priority: document.getElementById('vf-order_priority').value,
    order_date: document.getElementById('vf-order_date').value,
    ship_date: document.getElementById('vf-ship_date').value,
    units_sold: Number(document.getElementById('vf-units_sold').value),
  };
  const rates = getVentaUnitRates();
  if (!rates) {
    toast('Selecciona un tipo de producto válido', 'error');
    return;
  }
  body.unit_price = rates.unit_price;
  body.unit_cost = rates.unit_cost;
  try {
    if (id) {
      await api(`/ventas/${id}`, { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
    } else {
      await api('/ventas/', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
    }
    document.getElementById('modal-overlay').classList.remove('open');
    toast('Venta guardada');
    await refreshAfterVentasMutation();
  } catch (e) {
    toast(e.message, 'error');
  }
}

async function deleteVenta(idVenta) {
  if (!confirm('¿Eliminar esta venta?')) return;
  try {
    await api(`/ventas/${idVenta}`, { method: 'DELETE' });
    toast('Venta eliminada');
    await refreshAfterVentasMutation();
  } catch (e) {
    toast(e.message, 'error');
  }
}

function maestraFieldHtml(tabla, f) {
  const label = MAESTRA_LABELS[f] || f;
  if (tabla === 'paises' && f === 'id_region') {
    const opts = (filterCache?.regiones || [])
      .map((r) => `<option value="${r.id_region}">${r.region}</option>`)
      .join('');
    return `<div class="field"><label for="mf-id_region">${label}</label>
      <select id="mf-id_region" required><option value="">— Selecciona —</option>${opts}</select></div>`;
  }
  const numeric = new Set(['unit_price', 'unit_cost']);
  const type = numeric.has(f) ? 'number' : 'text';
  return `<div class="field"><label for="mf-${f}">${label}</label>
    <input id="mf-${f}" type="${type}" step="any"></div>`;
}

async function openMaestraModal(tabla, fields, id = null) {
  if (tabla === 'paises') await ensureFilters();
  const modal = document.getElementById('modal');
  modal.dataset.mode = 'maestra';
  document.getElementById('modal-title').textContent = id ? 'Editar' : 'Nuevo';
  document.getElementById('modal-form').innerHTML = fields.map((f) => maestraFieldHtml(tabla, f)).join('');
  modal.dataset.tabla = tabla;
  modal.dataset.id = id || '';
  modal.dataset.fields = JSON.stringify(fields);
  if (id) {
    const row = await api(`/maestras/${tabla}/${id}/`);
    fields.forEach((f) => {
      const el = document.getElementById(`mf-${f}`);
      if (el) el.value = row[f] ?? '';
    });
  }
  document.getElementById('modal-overlay').classList.add('open');
}

async function saveMaestra() {
  const modal = document.getElementById('modal');
  const tabla = modal.dataset.tabla;
  const id = modal.dataset.id;
  const fields = JSON.parse(modal.dataset.fields || '[]');
  const body = {};
  fields.forEach((f) => {
    const v = document.getElementById(`mf-${f}`)?.value;
    body[f] = ['unit_price', 'unit_cost', 'id_region'].includes(f) ? Number(v) : v;
  });
  try {
    if (id) await api(`/maestras/${tabla}/${id}/`, { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
    else await api(`/maestras/${tabla}/`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
    document.getElementById('modal-overlay').classList.remove('open');
    filterCache = null;
    toast('Guardado');
    loadMaestra(tabla, fields);
  } catch (e) {
    toast(e.message, 'error');
  }
}

async function deleteMaestra(tabla, id) {
  if (!confirm('¿Eliminar?')) return;
  try {
    await api(`/maestras/${tabla}/${id}/`, { method: 'DELETE' });
    filterCache = null;
    toast('Eliminado');
    loadMaestra(tabla, PAGES[tabla].fields);
  } catch (e) {
    toast(e.message, 'error');
  }
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
  if (!cb) return;
  const saved = localStorage.getItem('globtrade-goto-ventas');
  if (saved !== null) cb.checked = saved === '1';
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

/* Truncate modal */
const truncateOverlay = document.getElementById('truncate-overlay');
const truncateInput = document.getElementById('truncate-confirm');
const truncateOk = document.getElementById('truncate-ok');

document.getElementById('ventas-truncate-btn')?.addEventListener('click', () => {
  truncateInput.value = '';
  truncateOk.disabled = true;
  truncateOverlay.classList.add('open');
});
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
    const res = await api('/ventas/truncate', { method: 'DELETE' });
    truncateOverlay.classList.remove('open');
    ventasState.page = 1;
    clearVentasTable();
    paintVentasTotal(0);
    toast(`Eliminados ${fmtNum(res.eliminados)} registros. Ve a Generador / ETL para importar de nuevo.`);
  } catch (e) {
    toast(e.message, 'error');
  } finally {
    truncateOk.disabled = false;
  }
});

document.getElementById('dash-apply')?.addEventListener('click', loadDashboard);
document.getElementById('ventas-search')?.addEventListener('click', () => { ventasState.page = 1; loadVentas(); });
document.getElementById('v-q')?.addEventListener('keydown', (e) => { if (e.key === 'Enter') { ventasState.page = 1; loadVentas(); } });
document.getElementById('ventas-prev')?.addEventListener('click', () => { if (ventasState.page > 1) { ventasState.page--; loadVentas(); } });
document.getElementById('ventas-next')?.addEventListener('click', () => { ventasState.page++; loadVentas(); });
document.getElementById('ventas-export')?.addEventListener('click', () => {
  const q = new URLSearchParams();
  ['region', 'country', 'item_type', 'sales_channel', 'order_priority'].forEach((f) => {
    const v = document.getElementById(`v-${f}`)?.value;
    if (v) q.set(f, v);
  });
  window.open(`${API}/ventas/export?${q}`, '_blank');
});
document.getElementById('modal-save')?.addEventListener('click', () => {
  const mode = document.getElementById('modal').dataset.mode;
  if (mode === 'venta') saveVenta();
  else saveMaestra();
});
document.getElementById('ventas-new')?.addEventListener('click', () => openVentaModal());
document.getElementById('modal-cancel')?.addEventListener('click', () => document.getElementById('modal-overlay').classList.remove('open'));
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

Object.keys(PAGES).forEach((key) => {
  if (!PAGES[key].maestra) return;
  document.getElementById(`${key}-search`)?.addEventListener('click', () => {
    maestraState[key] = maestraState[key] || { page: 1, page_size: 25, search: '' };
    maestraState[key].search = document.getElementById(`${key}-q`)?.value || '';
    maestraState[key].page = 1;
    loadMaestra(key, PAGES[key].fields);
  });
  document.getElementById(`${key}-new`)?.addEventListener('click', () => { void openMaestraModal(key, PAGES[key].fields); });
});

function bootApp() {
  initTheme();
  activePage = 'dashboard';
  document.getElementById('page-title').textContent = PAGES.dashboard.title;
  document.querySelector('.nav-item[data-page="dashboard"]')?.classList.add('active');
  document.querySelector('#page-dashboard')?.classList.add('active');
}

window.addEventListener('error', (ev) => {
  console.error(ev.error || ev.message);
  toast(`Error: ${ev.message}`, 'error');
});

bootApp();
