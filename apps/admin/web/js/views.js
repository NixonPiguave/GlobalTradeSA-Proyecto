/*
 * views.js — Motor de vistas ERP.
 * Tabla a ancho completo · acciones en fila · detalle con «Ver» (modal).
 * Sin panel lateral por defecto (sidePanel: true solo si se pide explícitamente).
 */

const VISTAS = {};

const dvEsc = (s) => String(s == null ? '' : s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const dvMoney = (n) => '$' + Number(n || 0).toLocaleString('es-PE', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const dvNum = (n) => Number(n || 0).toLocaleString('es-PE');
const debounce = (fn, ms = 300) => {
  let t;
  return (...args) => { clearTimeout(t); t = setTimeout(() => fn(...args), ms); };
};

/** Paginación compacta reutilizable (‹ info ›). */
function wireSimplePager(root, state, onChange) {
  if (!root || root.dataset.pgBound) return;
  root.dataset.pgBound = '1';
  root.querySelector('[data-pg="prev"]')?.addEventListener('click', () => {
    if ((state.page || 1) > 1) { state.page -= 1; onChange(); }
  });
  root.querySelector('[data-pg="next"]')?.addEventListener('click', () => {
    if ((state.page || 1) < (state.total_pages || 1)) { state.page += 1; onChange(); }
  });
  root.querySelector('[data-pg="first"]')?.addEventListener('click', () => {
    if ((state.page || 1) > 1) { state.page = 1; onChange(); }
  });
  root.querySelector('[data-pg="last"]')?.addEventListener('click', () => {
    const tot = state.total_pages || 1;
    if ((state.page || 1) < tot) { state.page = tot; onChange(); }
  });
}

function refreshSimplePager(root, state) {
  if (!root) return;
  const cur = state.page || 1;
  const tot = Math.max(1, state.total_pages || 1);
  const info = root.querySelector('[data-pg="info"]');
  if (info) info.textContent = `${cur} / ${tot}`;
  root.querySelector('[data-pg="prev"]')?.toggleAttribute('disabled', cur <= 1);
  root.querySelector('[data-pg="next"]')?.toggleAttribute('disabled', cur >= tot);
  root.querySelector('[data-pg="first"]')?.toggleAttribute('disabled', cur <= 1);
  root.querySelector('[data-pg="last"]')?.toggleAttribute('disabled', cur >= tot);
}

function pagerCompactHtml(extra = '') {
  return `<nav class="pager-compact" aria-label="Paginación"${extra ? ` ${extra}` : ''}>
    <div class="pager-nav">
      <button type="button" class="pager-btn" data-pg="first" title="Primera">‹‹</button>
      <button type="button" class="pager-btn" data-pg="prev" title="Anterior">‹</button>
      <span class="pager-info" data-pg="info">1 / 1</span>
      <button type="button" class="pager-btn" data-pg="next" title="Siguiente">›</button>
      <button type="button" class="pager-btn" data-pg="last" title="Última">››</button>
    </div>
  </nav>`;
}

/* ---------------------------------------------------------------------------
 * Modal central unificado (un solo overlay para todo el panel).
 * ------------------------------------------------------------------------ */

let _uiOverlay = null;

function uiOverlayEl() {
  if (_uiOverlay && document.body.contains(_uiOverlay)) return _uiOverlay;
  _uiOverlay = document.createElement('div');
  _uiOverlay.id = 'ui-modal-overlay';
  _uiOverlay.className = 'modal-overlay';
  _uiOverlay.innerHTML = `
    <div class="modal ui-modal">
      <h3 class="ui-modal-title"></h3>
      <div class="ui-modal-body form-grid"></div>
      <div class="modal-actions ui-modal-footer">
        <button type="button" class="btn btn-secondary" data-ui="cancelar">Cancelar</button>
        <button type="button" class="btn btn-primary" data-ui="aceptar">Aceptar</button>
      </div>
    </div>`;
  document.body.appendChild(_uiOverlay);
  _uiOverlay.addEventListener('click', (e) => {
    if (e.target === _uiOverlay) uiModalCerrar();
  });
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && _uiOverlay.classList.contains('open')) uiModalCerrar();
  });
  return _uiOverlay;
}

function uiModalCerrar() {
  const ov = uiOverlayEl();
  ov.classList.remove('open');
}

/** Ejecuta un botón extra de detalle/fila con cierre y recarga coherentes. */
async function ejecutarDvExtra(x, { recargar } = {}) {
  if (!x || typeof x.fn !== 'function') return;
  const opensModal = x.opensModal === true;
  if (opensModal) uiModalCerrar();
  try {
    await x.fn();
    if (!opensModal) {
      uiModalCerrar();
      if (recargar) await recargar();
    }
  } catch (e) {
    if (e?.name === 'AbortError') return;
    toast(e.message || 'No se pudo completar la acción', 'error');
  }
}

function uiFieldHtml(f) {
  if (f.type === 'search-select' || (f.type === 'select' && ((f.options || []).length > 25 || f.searchable))) {
    const val = f.value ?? '';
    const selLabel = (f.options || []).find((o) => String(o.value) === String(val))?.label || '';
    return `<div class="field ui-search-select" style="grid-column:1/-1" data-ss-key="${dvEsc(f.key)}">
      <label>${dvEsc(f.label)}</label>
      <input type="hidden" id="uf-${f.key}" value="${dvEsc(val)}">
      <input type="search" class="ui-ss-input" id="uf-${f.key}-q"
        placeholder="${dvEsc(f.searchPlaceholder || 'Escribe para buscar…')}" autocomplete="off">
      <div class="ui-ss-selected" id="uf-${f.key}-sel">${selLabel ? dvEsc(selLabel) : '<span class="meta">— Selecciona —</span>'}</div>
      <div class="ui-ss-list" id="uf-${f.key}-list" hidden></div>
    </div>`;
  }
  if (f.type === 'select') {
    const opts = (f.options || [])
      .map((o) => `<option value="${dvEsc(o.value)}" ${String(o.value) === String(f.value ?? '') ? 'selected' : ''}>${dvEsc(o.label)}</option>`)
      .join('');
    const span = f.full ? ' style="grid-column:1/-1"' : '';
    return `<div class="field"${span}><label>${dvEsc(f.label)}</label><select id="uf-${f.key}"${f.disabled ? ' disabled' : ''}>${opts}</select></div>`;
  }
  if (f.type === 'textarea') {
    return `<div class="field" style="grid-column:1/-1"><label>${dvEsc(f.label)}</label><textarea id="uf-${f.key}" rows="3">${dvEsc(f.value ?? '')}</textarea></div>`;
  }
  if (f.type === 'checkbox') {
    return `<div class="field"><label class="dv-check"><input type="checkbox" id="uf-${f.key}" ${f.value ? 'checked' : ''}> ${dvEsc(f.label)}</label></div>`;
  }
  if (f.type === 'file') {
    return `<div class="field" style="grid-column:1/-1"><label>${dvEsc(f.label)}</label><input type="file" id="uf-${f.key}" accept="image/jpeg,image/png,image/webp"></div>`;
  }
  if (f.type === 'html') {
    return `<div class="field" style="grid-column:1/-1" id="uf-${f.key}">${f.value || ''}</div>`;
  }
  const hint = f.hint != null ? `<span class="field-hint" id="uf-hint-${f.key}">${dvEsc(f.hint)}</span>` : '';
  const t = f.type || 'text';
  const auto = t === 'password' ? 'new-password' : (t === 'email' ? 'off' : 'off');
  const span = f.full ? ' style="grid-column:1/-1"' : '';
  return `<div class="field"${span}><label>${dvEsc(f.label)}</label>
    <input type="${t}" id="uf-${f.key}" name="uf_${dvEsc(f.key)}" value="${dvEsc(f.value ?? '')}" autocomplete="${auto}" data-lpignore="true"
      ${f.step ? `step="${f.step}"` : ''} ${f.min != null ? `min="${f.min}"` : ''} ${f.max != null ? `max="${f.max}"` : ''}
      ${f.maxlength != null ? `maxlength="${f.maxlength}"` : ''} ${f.pattern ? `pattern="${dvEsc(f.pattern)}"` : ''}
      ${f.placeholder ? `placeholder="${dvEsc(f.placeholder)}"` : ''} ${f.required ? 'required' : ''} ${f.disabled ? 'disabled' : ''}
      ${f.inputmode ? `inputmode="${dvEsc(f.inputmode)}"` : ''} ${f.title ? `title="${dvEsc(f.title)}"` : ''}>${hint}</div>`;
}

function bindSearchSelectFields(campos) {
  for (const f of campos) {
    const isSearch = f.type === 'search-select' || (f.type === 'select' && ((f.options || []).length > 25 || f.searchable));
    if (!isSearch) continue;
    const hidden = document.getElementById(`uf-${f.key}`);
    const input = document.getElementById(`uf-${f.key}-q`);
    const list = document.getElementById(`uf-${f.key}-list`);
    const sel = document.getElementById(`uf-${f.key}-sel`);
    if (!hidden || !input || !list || !sel) continue;

    const pick = (value, label) => {
      hidden.value = value;
      sel.innerHTML = dvEsc(label);
      input.value = '';
      list.hidden = true;
      hidden.dispatchEvent(new Event('change', { bubbles: true }));
    };

    const render = (options) => {
      const max = f.maxResults || 50;
      const slice = options.slice(0, max);
      list.innerHTML = slice.length
        ? slice.map((o) => `<button type="button" class="ui-ss-opt" data-v="${dvEsc(o.value)}" data-l="${dvEsc(o.label)}">${dvEsc(o.label)}</button>`).join('')
        : '<p class="meta ui-ss-empty">Sin resultados. Prueba otro término.</p>';
      list.hidden = false;
    };

    const load = debounce(async () => {
      const q = input.value.trim().toLowerCase();
      let opts = [];
      if (typeof f.searchFn === 'function') {
        opts = await f.searchFn(q);
      } else {
        opts = (f.options || []).filter((o) => !q || String(o.label).toLowerCase().includes(q));
      }
      render(opts);
    }, 250);

    input.addEventListener('input', () => void load());
    input.addEventListener('focus', () => void load());
    list.addEventListener('click', (e) => {
      const b = e.target.closest('.ui-ss-opt');
      if (!b) return;
      pick(b.dataset.v, b.dataset.l);
    });
    document.addEventListener('click', (e) => {
      if (!e.target.closest(`[data-ss-key="${f.key}"]`)) list.hidden = true;
    });

    if (hidden.value && (f.options || []).length) {
      const o = f.options.find((x) => String(x.value) === String(hidden.value));
      if (o) sel.innerHTML = dvEsc(o.label);
    }
  }
}

/**
 * Abre el modal central. modos típicos: 'Agregar', 'Actualizar', 'Eliminar'.
 * onAceptar(values) -> devuelva false para mantener el modal abierto.
 */
function uiModal({ modo, tituloExtra = '', campos = [], onAceptar = null, textoAceptar = 'Aceptar', ancho = 'md', danger = false, onReady = null, gridClass = '' }) {
  const ov = uiOverlayEl();
  const modal = ov.querySelector('.ui-modal');
  modal.className = `modal ui-modal ui-modal-${ancho}${danger ? ' ui-modal-danger' : ''}`;
  ov.querySelector('.ui-modal-title').textContent = tituloExtra ? `Modo: ${modo} — ${tituloExtra}` : `Modo: ${modo}`;
  const body = ov.querySelector('.ui-modal-body');
  body.className = `ui-modal-body form-grid${ancho === 'lg' || ancho === 'xl' ? ' form-grid-lg' : ''}${gridClass ? ` ${gridClass}` : ''}`;
  body.innerHTML = campos.map(uiFieldHtml).join('');
  bindSearchSelectFields(campos);
  const cancelar = ov.querySelector('[data-ui="cancelar"]');
  const footer = ov.querySelector('.ui-modal-footer');
  const esSoloCerrar = !onAceptar || /^cerrar$/i.test(String(textoAceptar).trim());
  const esFormulario = typeof onAceptar === 'function' && !esSoloCerrar;
  if (cancelar) {
    cancelar.textContent = 'Cancelar';
    cancelar.hidden = !esFormulario;
    cancelar.classList.toggle('ui-btn-hidden', !esFormulario);
    const nuevoCancel = cancelar.cloneNode(true);
    cancelar.parentNode.replaceChild(nuevoCancel, cancelar);
    if (esFormulario) {
      nuevoCancel.addEventListener('click', () => uiModalCerrar());
    }
  }
  if (footer) footer.classList.toggle('ui-modal-footer-single', esSoloCerrar);
  const aceptar = ov.querySelector('[data-ui="aceptar"]');
  const nuevo = aceptar.cloneNode(true);
  aceptar.parentNode.replaceChild(nuevo, aceptar);
  nuevo.textContent = textoAceptar;
  nuevo.className = `btn ${danger ? 'btn-danger' : 'btn-primary'}`;
  if (onAceptar) {
    nuevo.addEventListener('click', async () => {
      const values = {};
      for (const f of campos) {
        const el = document.getElementById(`uf-${f.key}`);
        if (!el || f.type === 'html') continue;
        if (f.type === 'checkbox') values[f.key] = el.checked;
        else if (f.type === 'file') values[f.key] = el.files && el.files[0] ? el.files[0] : null;
        else if (f.type === 'number') {
          const raw = el.value;
          if (raw === '' || raw == null) values[f.key] = f.optional ? null : '';
          else {
            const n = Number(raw);
            values[f.key] = Number.isFinite(n) ? n : raw;
          }
        }
        else if (f.type === 'search-select' || (f.type === 'select' && ((f.options || []).length > 25 || f.searchable))) values[f.key] = el.value;
        else values[f.key] = el.value;
      }
      nuevo.disabled = true;
      try {
        const ok = await onAceptar(values);
        if (ok !== false) uiModalCerrar();
      } catch (e) {
        toast(e.message || 'Error al guardar', 'error');
      } finally {
        nuevo.disabled = false;
      }
    });
  } else {
    nuevo.addEventListener('click', () => uiModalCerrar());
  }
  if (typeof onReady === 'function') onReady(ov);
  ov.classList.add('open');
}

/** Confirmación. Devuelve promesa (resuelve al confirmar, rechaza si cancela). */
function uiConfirm({ titulo = 'Confirmar acción', mensaje = '', textoAceptar = 'Eliminar', onConfirm = null }) {
  return new Promise((resolve, reject) => {
    const ov = uiOverlayEl();
    const modal = ov.querySelector('.ui-modal');
    modal.className = 'modal ui-modal ui-modal-sm ui-modal-danger';
    ov.querySelector('.ui-modal-title').textContent = titulo;
    ov.querySelector('.ui-modal-body').className = 'ui-modal-body ui-confirm-body';
    ov.querySelector('.ui-modal-body').innerHTML = `<p class="ui-confirm-msg">${mensaje}</p>`;
    const cancelar = ov.querySelector('[data-ui="cancelar"]');
    const nuevoCancel = cancelar.cloneNode(true);
    cancelar.parentNode.replaceChild(nuevoCancel, cancelar);
    nuevoCancel.hidden = false;
    nuevoCancel.classList.remove('ui-btn-hidden');
    nuevoCancel.textContent = 'No, volver';
    nuevoCancel.addEventListener('click', () => {
      uiModalCerrar();
      reject(new DOMException('Cancelled', 'AbortError'));
    });
    const footer = ov.querySelector('.ui-modal-footer');
    if (footer) footer.classList.remove('ui-modal-footer-single');
    const aceptar = ov.querySelector('[data-ui="aceptar"]');
    const nuevo = aceptar.cloneNode(true);
    aceptar.parentNode.replaceChild(nuevo, aceptar);
    nuevo.textContent = textoAceptar;
    nuevo.className = 'btn btn-danger';
    nuevo.disabled = false;
    nuevo.addEventListener('click', async () => {
      nuevo.disabled = true;
      try {
        if (onConfirm) await onConfirm();
        uiModalCerrar();
        resolve();
      } catch (e) {
        toast(e.message || 'Error', 'error');
        reject(e);
      } finally {
        nuevo.disabled = false;
      }
    });
    ov.classList.add('open');
  });
}

/* ---------------------------------------------------------------------------
 * Pestañas (para páginas con dos o más entidades, ej. Catálogo: Productos/Categorías)
 * ------------------------------------------------------------------------ */

function createTabsView(contenedor, tabs) {
  const el = typeof contenedor === 'string' ? document.getElementById(contenedor) : contenedor;
  if (!el) return null;
  el.innerHTML = `
    <div class="dv-tabs">
      ${tabs.map((t, i) => `<button type="button" class="dv-tab${i === 0 ? ' active' : ''}" data-tab="${dvEsc(t.id)}">${dvEsc(t.label)}</button>`).join('')}
    </div>
    ${tabs.map((t, i) => `<div class="dv-panel" data-panel="${dvEsc(t.id)}"${i === 0 ? '' : ' hidden'}></div>`).join('')}`;
  const paneles = {};
  tabs.forEach((t) => { paneles[t.id] = el.querySelector(`[data-panel="${t.id}"]`); });
  el.querySelectorAll('.dv-tab').forEach((btn) => {
    btn.addEventListener('click', () => {
      el.querySelectorAll('.dv-tab').forEach((b) => b.classList.toggle('active', b === btn));
      el.querySelectorAll('.dv-panel').forEach((p) => { p.hidden = p.dataset.panel !== btn.dataset.tab; });
      const tab = tabs.find((t) => t.id === btn.dataset.tab);
      if (tab?.onActivo) tab.onActivo(paneles[tab.id]);
    });
  });
  const primero = tabs[0];
  if (primero?.onActivo) primero.onActivo(paneles[primero.id]);
  return paneles;
}

/* ---------------------------------------------------------------------------
 * Vista de datos unificada
 * ------------------------------------------------------------------------ */

/**
 * cfg:
 *   sidePanel    false por defecto — sin cuadro derecho; detalle con «Ver» (modal)
 *   state, buscar, filtrosHtml, botones, columnas, cargar, filas, total, totalId
 *   titulo(row), resumen(row), key(row), filaClase(row)
 *   acciones     { agregar, modificar, eliminar, ver } — ver abre modal si no hay handler
 *   extras(row)  botones dentro del modal de detalle
 *   vacio, pageSize, autoLoad
 */
function createDataView(contenedor, cfg) {
  const st = cfg.state || { page: 1, page_size: cfg.pageSize || 20, total_pages: 1 };
  st.total_pages = st.total_pages || 1;
  const el = typeof contenedor === 'string' ? document.getElementById(contenedor) : contenedor;
  if (!el) return null;

  let items = [];
  let selKey = null;
  let loadGen = 0;
  const useSide = cfg.sidePanel === true;

  const hasExtrasFn = typeof cfg.extras === 'function';
  // Ver: handler explícito, extras de flujo, o resumen sin edición inline
  const hasVer = !!(
    cfg.acciones?.ver
    || cfg.detalleModal === true
    || hasExtrasFn
    || (cfg.resumen && !cfg.acciones?.modificar)
  );
  const cols = [...(cfg.columnas || [])];
  const rowActionsEnabled = !!(cfg.acciones?.modificar || cfg.acciones?.eliminar || hasVer);
  if (rowActionsEnabled && !cols.some((c) => c.key === '__acciones')) {
    cols.push({ key: '__acciones', label: 'Acciones', align: 'col-actions' });
  }

  const filtrosClass = cfg.filtrosClass ? ` ${cfg.filtrosClass}` : '';
  const toolbarBotones = (cfg.botones || []).map((b) =>
    `<button type="button" class="btn ${b.clase || 'btn-secondary'}" id="${dvEsc(b.id)}">${dvEsc(b.label)}</button>`
  ).join('');
  const hasBotones = (cfg.botones || []).length > 0;
  const botonesInline = cfg.botonesInline === true;
  const canAgregar = !!cfg.acciones?.agregar;
  const hasFilterRow = !!(cfg.buscar || cfg.filtrosHtml || canAgregar || (hasBotones && botonesInline));
  const hasExtraRow = hasBotones && !botonesInline;
  const hasToolbar = hasFilterRow || hasExtraRow;
  const toolbarHtml = hasToolbar ? `
      <div class="dv-toolbar">
        ${hasFilterRow ? `<div class="dv-toolbar-row">
          <div class="dv-toolbar-filters dv-filters${filtrosClass}">
            ${cfg.buscar ? `<div class="field field-search dv-q-wrap"><label>Buscar</label><input class="dv-q" type="search" id="${dvEsc(cfg.buscar.id)}" name="dv_search_${dvEsc(cfg.buscar.id)}" autocomplete="off" data-lpignore="true" data-form-type="other" placeholder="${dvEsc(cfg.buscar.placeholder || 'Buscar...')}"></div>` : ''}
            ${cfg.filtrosHtml || ''}
            ${(cfg.buscar || cfg.filtrosHtml) ? `<div class="dv-toolbar-search-actions">${cfg.buscar ? '<button type="button" class="btn btn-primary" data-dv-buscar>Buscar</button>' : ''}${(cfg.buscar || cfg.filtrosHtml) ? '<button type="button" class="btn btn-secondary" data-dv-limpiar>Limpiar</button>' : ''}${botonesInline && hasBotones ? toolbarBotones : ''}</div>` : ''}
          </div>
          <div class="dv-toolbar-actions" role="toolbar" aria-label="Acciones">
            <button type="button" class="btn btn-primary dv-b-agregar">+ Nuevo</button>
          </div>
        </div>` : ''}
        ${hasExtraRow ? `<div class="dv-toolbar-extra${hasFilterRow ? '' : ' dv-toolbar-extra-only'}">${toolbarBotones}</div>` : ''}
      </div>` : '';
  el.innerHTML = `
    <div class="dv${useSide ? '' : ' dv-full'}">
      ${toolbarHtml}
      <div class="dv-body${useSide ? '' : ' dv-body-full'}">
        <div class="dv-grid card">
          <div class="card-title dv-total"><span><span id="${dvEsc(cfg.totalId || 'dv-total')}">0</span> registros</span><span class="meta">${hasVer ? 'Usa Ver para el detalle completo' : 'Acciones en cada fila'}</span></div>
          <div class="table-wrap"><table class="table-erp dv-table">
            <thead><tr>${cols.map((c) => `<th class="${c.align || ''}">${dvEsc(c.label)}</th>`).join('')}</tr></thead>
            <tbody></tbody>
          </table></div>
          <p class="query-time dv-query"></p>
          <div class="pagination dv-pagination pager-compact" data-dv-pager>
            <div class="pager-nav">
              <button type="button" class="pager-btn" data-dv-first title="Primera">‹‹</button>
              <button type="button" class="pager-btn" data-dv-prev title="Anterior">‹</button>
              <span class="pager-info dv-page-info">1 / 1</span>
              <button type="button" class="pager-btn" data-dv-next title="Siguiente">›</button>
              <button type="button" class="pager-btn" data-dv-last title="Última">››</button>
            </div>
            <div class="pager-meta">
              <label class="pager-size dv-page-size">Filas
                <select class="pager-size-sel dv-page-size-sel" data-dv-size>
                  ${[10, 15, 20, 50, 100].map((n) => `<option value="${n}" ${n === (cfg.pageSize || 20) ? 'selected' : ''}>${n}</option>`).join('')}
                </select>
              </label>
            </div>
          </div>
        </div>
        ${useSide ? `<aside class="dv-side card">
          <div class="dv-side-vacio meta">Selecciona un registro.</div>
          <div class="dv-side-contenido" hidden>
            <h4 class="dv-side-titulo"></h4>
            <div class="dv-side-resumen"></div>
            <div class="dv-extras"></div>
          </div>
        </aside>` : ''}
      </div>
    </div>`;

  const tbody = el.querySelector('tbody');
  const queryEl = el.querySelector('.dv-query');
  const totalEl = el.querySelector('#' + (cfg.totalId || 'dv-total'));
  const pageInfoEl = el.querySelector('.dv-page-info');
  const prevBtn = el.querySelector('[data-dv-prev]');
  const nextBtn = el.querySelector('[data-dv-next]');
  const firstBtn = el.querySelector('[data-dv-first]');
  const lastBtn = el.querySelector('[data-dv-last]');
  const sizeSel = el.querySelector('[data-dv-size]');
  const sideVacio = el.querySelector('.dv-side-vacio');
  const sideCont = el.querySelector('.dv-side-contenido');
  const sideTitulo = el.querySelector('.dv-side-titulo');
  const sideResumen = el.querySelector('.dv-side-resumen');
  const extrasEl = el.querySelector('.dv-extras');
  const btnAgr = el.querySelector('.dv-b-agregar');
  const toolbarActions = el.querySelector('.dv-toolbar-actions');

  (cfg.botones || []).forEach((b) => {
    el.querySelector(`#${b.id}`)?.addEventListener('click', () => void b.fn());
  });
  el.querySelector('[data-dv-buscar]')?.addEventListener('click', () => { st.page = 1; recargar(); });
  el.querySelector('.dv-q')?.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') { st.page = 1; recargar(); }
  });
  // Solo buscar al escribir el usuario (no autofill del navegador en campos password del modal)
  el.querySelector('.dv-q')?.addEventListener('input', debounce((ev) => {
    if (ev.isTrusted === false) return;
    st.page = 1;
    recargar();
  }, 450));
  el.querySelector('[data-dv-limpiar]')?.addEventListener('click', () => {
    el.querySelectorAll('.dv-filters input[type="search"], .dv-filters input[type="text"], .dv-filters input[type="date"], .dv-filters input[type="number"], .dv-filters select').forEach((ctrl) => { ctrl.value = ''; });
    el.querySelectorAll('.dv-filters .ui-search-select input[type="hidden"]').forEach((ctrl) => {
      ctrl.value = '';
      ctrl.dispatchEvent(new Event('change', { bubbles: true }));
    });
    el.querySelectorAll('.dv-filters input[type="checkbox"]').forEach((ctrl) => { ctrl.checked = false; });
    el.querySelectorAll('.dv-filters input[type="range"]').forEach((ctrl) => {
      if (ctrl.dataset.dvDefault != null) ctrl.value = ctrl.dataset.dvDefault;
    });
    st.page = 1;
    recargar();
  });
  el.querySelectorAll('[data-dv-auto]').forEach((ctrl) => {
    ctrl.addEventListener('change', () => { st.page = 1; recargar(); });
  });
  prevBtn?.addEventListener('click', () => { if (st.page > 1) { st.page--; recargar(); } });
  nextBtn?.addEventListener('click', () => { if (st.page < st.total_pages) { st.page++; recargar(); } });
  firstBtn?.addEventListener('click', () => { if (st.page > 1) { st.page = 1; recargar(); } });
  lastBtn?.addEventListener('click', () => { if (st.page < st.total_pages) { st.page = st.total_pages; recargar(); } });
  sizeSel?.addEventListener('change', () => {
    st.page_size = Number(sizeSel.value) || 20;
    st.page = 1;
    recargar();
  });

  function renderPager() {
    const total = st.total_pages || 1;
    const cur = st.page || 1;
    if (pageInfoEl) pageInfoEl.textContent = `${cur} / ${total}`;
    if (prevBtn) prevBtn.disabled = cur <= 1;
    if (nextBtn) nextBtn.disabled = cur >= total;
    if (firstBtn) firstBtn.disabled = cur <= 1;
    if (lastBtn) lastBtn.disabled = cur >= total;
  }

  tbody.addEventListener('click', (e) => {
    const act = e.target.closest('[data-act]');
    if (act) {
      e.stopPropagation();
      const key = act.closest('tr[data-key]')?.dataset.key;
      const row = items.find((r) => String(cfg.key(r)) === String(key));
      if (!row) return;
      const kind = act.dataset.act;
      if (kind === 'edit' && cfg.acciones?.modificar) void cfg.acciones.modificar(row);
      else if (kind === 'del' && cfg.acciones?.eliminar) confirmarEliminar(row);
      else if (kind === 'view') void abrirDetalle(row);
      else if (kind === 'fila-extra') {
        const fe = (cfg.extras ? cfg.extras(row) : []).filter((x) => x && x.enFila);
        const x = fe[Number(act.dataset.fei)];
        if (x) void ejecutarDvExtra(x, { recargar });
      }
      return;
    }
  });

  function syncToolbar() {
    const canAdd = !!cfg.acciones?.agregar;
    if (btnAgr) {
      btnAgr.hidden = !canAdd;
      btnAgr.disabled = !canAdd;
      btnAgr.title = canAdd ? 'Crear nuevo registro' : (cfg.bloqueadas?.agregar || '');
    }
    if (toolbarActions) toolbarActions.hidden = !canAdd;
  }

  function confirmarEliminar(row) {
    uiConfirm({
      titulo: '¿Eliminar este registro?',
      mensaje: cfg.titulo ? `Se eliminará «${dvEsc(cfg.titulo(row))}».` : 'Esta acción no se puede deshacer.',
      textoAceptar: 'Eliminar',
      onConfirm: async () => {
        const msg = await cfg.acciones.eliminar(row);
        toast(typeof msg === 'string' ? msg : 'Registro eliminado');
        recargar();
      },
    });
  }

  async function abrirDetalle(row) {
    if (cfg.acciones?.ver) {
      await cfg.acciones.ver(row);
      return;
    }
    const extras = (cfg.extras ? cfg.extras(row) : []).filter(Boolean);
    const extrasHtml = extras.length
      ? `<div class="dv-modal-extras">${extras.map((x, i) =>
        `<button type="button" class="btn ${x.clase || 'btn-secondary'} btn-sm" data-dv-ex="${i}">${dvEsc(x.label)}</button>`
      ).join('')}</div>`
      : '';
    uiModal({
      modo: 'Detalle',
      tituloExtra: cfg.titulo ? cfg.titulo(row) : 'Registro',
      ancho: 'md',
      textoAceptar: 'Cerrar',
      campos: [{
        type: 'html',
        key: 'info',
        value: `${cfg.resumen ? cfg.resumen(row) : ''}${extrasHtml}`,
      }],
      onReady: (ov) => {
        ov.querySelectorAll('[data-dv-ex]').forEach((b) => {
          b.addEventListener('click', () => {
            const x = extras[Number(b.dataset.dvEx)];
            if (!x) return;
            b.disabled = true;
            void ejecutarDvExtra(x, { recargar }).finally(() => { b.disabled = false; });
          });
        });
      },
    });
  }

  function renderAcciones(row) {
    if (!rowActionsEnabled) return '';
    const parts = [];
    const verLbl = cfg.acciones?.verLabel ? cfg.acciones.verLabel(row) : 'Ver';
    if (hasVer || cfg.acciones?.ver) {
      parts.push(`<button type="button" class="act-btn act-view" data-act="view" title="${dvEsc(verLbl)}">${dvEsc(verLbl)}</button>`);
    }
    if (cfg.acciones?.modificar) parts.push('<button type="button" class="act-btn act-edit" data-act="edit" title="Modificar">Editar</button>');
    const canDel = cfg.acciones?.eliminar && (!cfg.puedeEliminar || cfg.puedeEliminar(row));
    if (canDel) parts.push('<button type="button" class="act-btn act-del" data-act="del" title="Eliminar">Eliminar</button>');
    // Acciones de fila desde extras.enFila (ej. Despachar)
    const filaExtras = (cfg.extras ? cfg.extras(row) : []).filter((x) => x && x.enFila);
    filaExtras.forEach((x, i) => {
      const cls = (x.clase || '').includes('primary') || (x.clase || '').includes('btn-primary')
        ? 'act-btn act-view' : 'act-btn act-edit';
      parts.push(`<button type="button" class="${cls}" data-act="fila-extra" data-fei="${i}">${dvEsc(x.labelCorto || x.label)}</button>`);
    });
    if (!parts.length) return '<td class="row-actions"><span class="meta">—</span></td>';
    return `<td class="row-actions"><div class="row-act">${parts.join('')}</div></td>`;
  }

  function seleccionar(key) {
    if (!useSide) return;
    selKey = key;
    tbody.querySelectorAll('tr[data-key]').forEach((tr) => tr.classList.toggle('dv-seleccionada', tr.dataset.key === key));
    const row = items.find((r) => String(cfg.key(r)) === String(selKey)) || null;
    if (!row || !sideVacio) return;
    sideVacio.hidden = true;
    sideCont.hidden = false;
    sideTitulo.textContent = cfg.titulo ? cfg.titulo(row) : `Registro #${key}`;
    sideResumen.innerHTML = cfg.resumen ? cfg.resumen(row) : '';
    const extras = (cfg.extras ? cfg.extras(row) : []).filter(Boolean);
    extrasEl.innerHTML = extras.map((x, i) =>
      `<button type="button" class="btn ${x.clase || 'btn-secondary'} btn-sm dv-extra" data-i="${i}">${dvEsc(x.label)}</button>`
    ).join('');
    extrasEl.querySelectorAll('.dv-extra').forEach((b) => {
      b.addEventListener('click', () => {
        const x = extras[Number(b.dataset.i)];
        if (!x) return;
        b.disabled = true;
        void ejecutarDvExtra(x, { recargar }).finally(() => { b.disabled = false; });
      });
    });
  }

  btnAgr?.addEventListener('click', () => {
    if (cfg.acciones?.agregar) void cfg.acciones.agregar();
  });

  async function recargar() {
    const gen = ++loadGen;
    el.classList.add('dv-loading');
    try {
      const res = await cfg.cargar(st);
      if (gen !== loadGen) return;
      if (!res) return;
      items = (cfg.filas ? cfg.filas(res) : (res.items || res.data || res)) || [];
      if (!Array.isArray(items)) items = [];
      const total = cfg.total ? cfg.total(res) : (res.total != null ? res.total : items.length);
      st.total_pages = Math.max(1, Math.ceil((total || 0) / (st.page_size || 20)) || 1);
      if (st.page > st.total_pages) st.page = st.total_pages;
      // Paginación en cliente cuando la API no pagina (lista completa)
      const apiPaged = res && (res.items != null || res.data != null) && res.total != null;
      if (!apiPaged && items.length > (st.page_size || 20)) {
        const start = ((st.page || 1) - 1) * (st.page_size || 20);
        items = items.slice(start, start + (st.page_size || 20));
      }
      const dataCols = cols.filter((c) => c.key !== '__acciones');
      tbody.innerHTML = items.length
        ? items.map((r) => {
          const filaClase = cfg.filaClase ? cfg.filaClase(r) : '';
          const cells = dataCols.map((c) => `<td class="${c.align || ''}">${c.render ? c.render(r) : dvEsc(r[c.key] ?? '')}</td>`).join('');
          return `<tr data-key="${dvEsc(cfg.key(r))}" class="${filaClase}">${cells}${renderAcciones(r)}</tr>`;
        }).join('')
        : `<tr><td colspan="${cols.length}" class="center">${dvEsc(cfg.vacio || 'Sin registros')}</td></tr>`;
      if (totalEl) totalEl.textContent = dvNum(total);
      renderPager();
      if (queryEl && res._queryTimeMs != null) queryEl.textContent = `Consulta: ${res._queryTimeMs} ms`;
      selKey = null;
      if (sideVacio) { sideVacio.hidden = false; if (sideCont) sideCont.hidden = true; }
      syncToolbar();
      if (typeof cfg.onAfterRender === 'function') cfg.onAfterRender(el, items);
    } catch (err) {
      if (gen !== loadGen) return;
      if (err?.name === 'AbortError' || /signal is aborted|aborted without reason/i.test(String(err?.message || ''))) return;
      tbody.innerHTML = `<tr><td colspan="${cols.length}" class="center text-danger">${dvEsc(err?.message || 'Error al cargar')}</td></tr>`;
      throw err;
    } finally {
      if (gen === loadGen) el.classList.remove('dv-loading');
    }
  }

  syncToolbar();
  if (cfg.autoLoad !== false) {
    void recargar().catch((err) => {
      if (err?.name === 'AbortError' || /signal is aborted|aborted without reason/i.test(String(err?.message || ''))) return;
      if (typeof toast === 'function' && err?.message) toast(err.message, 'error');
    });
  }

  return {
    recargar,
    pagina(n) { st.page = n || 1; return recargar(); },
    st,
  };
}

/** Toggle switch reutilizable */
function uiToggle({ id, label, checked = false, onChange = null }) {
  const wrap = document.createElement('label');
  wrap.className = 'gt-toggle';
  wrap.innerHTML = `
    <input type="checkbox" id="${id}" ${checked ? 'checked' : ''}>
    <span class="gt-toggle-slider"></span>
    <span>${dvEsc(label)}</span>`;
  if (onChange) {
    wrap.querySelector('input').addEventListener('change', (e) => onChange(e.target.checked));
  }
  return wrap;
}
