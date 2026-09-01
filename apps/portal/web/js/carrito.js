/* GlobMarket B2B — carrito (drawer global + API). Requiere app.js cargado antes. */
/* global qs, getToken, apiFetch, showToast, formatUsd, escapeHtml, nombreProductoEs */

(function () {
  let carrito = null;
  let drawerAbierto = false;

  async function cargarCarrito() {
    if (!getToken() || isPublicAuthPage()) return null;
    try {
      carrito = await apiFetch('/api/carrito', { auth: true });
    } catch {
      carrito = null;
    }
    actualizarBadge();
    return carrito;
  }

  function actualizarBadge() {
    const badge = document.getElementById('gm-cart-badge');
    if (!badge) return;
    const n = carrito?.n_items || 0;
    badge.textContent = String(n);
    badge.classList.toggle('hidden', n === 0);
  }

  function inyectarBotonCarrito() {
    // El chrome unificado ya incluye Carrito / Perfil / Mis pedidos.
    // Solo engancha el click del botón si existe.
    if (!getToken()) return;
    const btn = document.getElementById('gm-cart-btn');
    if (!btn || btn.dataset.bound === '1') return;
    btn.dataset.bound = '1';
    btn.addEventListener('click', toggleDrawer);
    if (window.lucide) window.lucide.createIcons();
  }

  function refreshNav() {
    inyectarBotonCarrito();
    void cargarCarrito();
  }

  function crearDrawer() {
    if (document.getElementById('gm-drawer')) return;
    const el = document.createElement('div');
    el.id = 'gm-drawer';
    el.className = 'fixed inset-0 z-50 hidden';
    el.innerHTML = `
      <div id="gm-drawer-bg" class="absolute inset-0 bg-slate-900/40 backdrop-blur-[2px]"></div>
      <aside class="absolute right-0 top-0 h-full w-full max-w-md bg-white shadow-2xl flex flex-col translate-x-full transition-transform duration-200" id="gm-drawer-panel">
        <div class="flex items-center justify-between px-5 py-4 border-b border-slate-200">
          <div class="text-lg font-extrabold text-slate-900">Tu carrito</div>
          <button id="gm-drawer-close" class="h-9 w-9 rounded-xl border border-slate-200 hover:border-blue-200 transition">✕</button>
        </div>
        <div id="gm-drawer-items" class="flex-1 overflow-y-auto px-5 py-4 space-y-3"></div>
        <div class="border-t border-slate-200 px-5 py-4 space-y-2">
          <div class="flex items-center justify-between text-sm text-slate-600">
            <span>Subtotal</span>
            <span id="gm-drawer-subtotal" class="font-semibold text-slate-900">$0.00</span>
          </div>
          <div id="gm-drawer-desc-row" class="hidden flex items-center justify-between text-sm text-emerald-700">
            <span>Descuento</span>
            <span id="gm-drawer-descuento" class="font-semibold">−$0.00</span>
          </div>
          <div class="flex items-center justify-between text-sm text-slate-600">
            <span>Total estimado (con IVA)</span>
            <span id="gm-drawer-total" class="text-xl font-extrabold text-slate-900">$0.00</span>
          </div>
          <a href="/pages/checkout.html" id="gm-drawer-checkout"
             class="mt-2 block w-full text-center rounded-xl bg-blue-600 text-white px-4 py-3 font-semibold hover:bg-blue-700 transition">
            Ir al checkout
          </a>
          <button type="button" id="gm-drawer-vaciar"
             class="w-full text-center rounded-xl border border-slate-200 text-slate-600 px-4 py-2 text-sm font-semibold hover:border-rose-200 hover:text-rose-700 transition">
            Vaciar carrito
          </button>
        </div>
      </aside>`;
    document.body.appendChild(el);
    el.querySelector('#gm-drawer-bg').addEventListener('click', toggleDrawer);
    el.querySelector('#gm-drawer-close').addEventListener('click', toggleDrawer);
    el.querySelector('#gm-drawer-vaciar')?.addEventListener('click', async () => {
      if (!carrito?.items?.length) return;
      try {
        carrito = await apiFetch('/api/carrito', { method: 'DELETE', auth: true });
        actualizarBadge();
        renderDrawer();
        showToast('success', 'Carrito vaciado');
      } catch (e) {
        showToast('error', e.message);
      }
    });
  }

  function renderDrawer() {
    const cont = document.getElementById('gm-drawer-items');
    const totalEl = document.getElementById('gm-drawer-total');
    const checkoutBtn = document.getElementById('gm-drawer-checkout');
    if (!cont) return;
    const items = carrito?.items || [];
    if (!items.length) {
      cont.innerHTML = `
        <div class="text-center py-16 text-slate-500">
          <div class="font-semibold text-slate-700">Tu carrito está vacío</div>
          <a href="/pages/catalogo.html" class="mt-3 inline-block text-sm font-semibold text-blue-700">Explorar productos →</a>
        </div>`;
    } else {
      cont.innerHTML = items.map((i) => `
        <div class="rounded-2xl border border-slate-200 p-3 flex gap-3 items-center">
          <div class="h-14 w-14 rounded-xl bg-slate-50 border border-slate-200 overflow-hidden shrink-0">
            ${i.imagen_url ? `<img src="${escapeHtml(i.imagen_url)}" class="h-full w-full object-cover" onerror="this.style.display='none'">` : ''}
          </div>
          <div class="flex-1 min-w-0">
            <div class="text-sm font-semibold text-slate-900 truncate">${escapeHtml(nombreProductoEs(i.nombre_producto))}</div>
            <div class="text-xs text-slate-500">${formatUsd(i.precio)} c/u · subtotal ${formatUsd(i.subtotal)}</div>
            <div class="mt-1 flex items-center gap-2">
              <button class="h-7 w-7 rounded-lg border border-slate-200 hover:border-blue-200" data-gm-menos="${i.id_item}" data-cant="${i.cantidad}">−</button>
              <span class="text-sm font-bold w-8 text-center">${i.cantidad}</span>
              <button class="h-7 w-7 rounded-lg border border-slate-200 hover:border-blue-200" data-gm-mas="${i.id_item}" data-cant="${i.cantidad}">+</button>
              <button class="ml-auto text-xs text-rose-600 font-semibold hover:text-rose-700" data-gm-quitar="${i.id_item}">Quitar</button>
            </div>
          </div>
        </div>`).join('');
      cont.querySelectorAll('[data-gm-menos]').forEach((b) => b.addEventListener('click', () => cambiarCantidad(Number(b.dataset.gmMenos), Number(b.dataset.cant) - 1)));
      cont.querySelectorAll('[data-gm-mas]').forEach((b) => b.addEventListener('click', () => cambiarCantidad(Number(b.dataset.gmMas), Number(b.dataset.cant) + 1)));
      cont.querySelectorAll('[data-gm-quitar]').forEach((b) => b.addEventListener('click', () => cambiarCantidad(Number(b.dataset.gmQuitar), 0)));
    }
    const subtotalEl = document.getElementById('gm-drawer-subtotal');
    const descRow = document.getElementById('gm-drawer-desc-row');
    const descEl = document.getElementById('gm-drawer-descuento');
    if (subtotalEl) subtotalEl.textContent = formatUsd(carrito?.subtotal ?? carrito?.total ?? 0);
    const desc = carrito?.descuento_monto || 0;
    if (descRow && descEl) {
      if (desc > 0) {
        descRow.classList.remove('hidden');
        descRow.classList.add('flex');
        descEl.textContent = `−${formatUsd(desc)}`;
      } else {
        descRow.classList.add('hidden');
        descRow.classList.remove('flex');
      }
    }
    if (totalEl) totalEl.textContent = formatUsd(carrito?.total_con_iva ?? carrito?.total ?? 0);
    if (checkoutBtn) checkoutBtn.classList.toggle('pointer-events-none', !items.length);
    if (checkoutBtn) checkoutBtn.classList.toggle('opacity-50', !items.length);
  }

  async function cambiarCantidad(idItem, cantidad) {
    try {
      const item = (carrito?.items || []).find((i) => i.id_item === idItem);
      const stock = item?.stock_disponible;
      if (stock != null && cantidad > stock) {
        showToast('error', `Stock insuficiente: disponibles ${String(stock)} unidades.`);
        return;
      }
      if (cantidad > 100000) {
        showToast('error', 'La cantidad máxima por producto es 100.000.');
        return;
      }
      carrito = await apiFetch(`/api/carrito/items/${idItem}`, { method: 'PUT', auth: true, body: { cantidad: Math.max(0, cantidad) } });
      actualizarBadge();
      renderDrawer();
    } catch (e) {
      showToast('error', e.message);
    }
  }

  async function toggleDrawer() {
    crearDrawer();
    const wrap = document.getElementById('gm-drawer');
    const panel = document.getElementById('gm-drawer-panel');
    drawerAbierto = !drawerAbierto;
    if (drawerAbierto) {
      wrap.classList.remove('hidden');
      await cargarCarrito();
      renderDrawer();
      requestAnimationFrame(() => panel.classList.remove('translate-x-full'));
    } else {
      panel.classList.add('translate-x-full');
      setTimeout(() => wrap.classList.add('hidden'), 200);
    }
  }

  async function agregar(idProducto, cantidad) {
    if (!getToken()) {
      showToast('info', 'Inicia sesión para agregar productos al carrito.');
      setTimeout(() => { window.location.href = '/pages/login.html'; }, 800);
      return false;
    }
    try {
      carrito = await apiFetch('/api/carrito/items', { method: 'POST', auth: true, body: { id_producto: idProducto, cantidad } });
      actualizarBadge();
      showToast('success', `Agregado al carrito (${cantidad} u.).`);
      if (drawerAbierto) renderDrawer();
      return true;
    } catch (e) {
      showToast('error', e.message);
      return false;
    }
  }

  function mostrarToastsReorden() {
    const raw = sessionStorage.getItem('gm-reorden-resumen');
    if (!raw) return;
    sessionStorage.removeItem('gm-reorden-resumen');
    try {
      const resumen = JSON.parse(raw);
      (resumen.omitidos || []).forEach((o) => {
        const nombre = o.nombre_producto || `Producto #${o.id_producto}`;
        const motivo = o.motivo === 'sin_stock' ? 'sin stock en tu zona' : 'no disponible';
        showToast('warning', `${nombre}: omitido (${motivo}).`);
      });
      (resumen.ajustados || []).forEach((a) => {
        const nombre = a.nombre_producto || `Producto #${a.id_producto}`;
        showToast('info', `${nombre}: cantidad ajustada a ${a.cantidad_agregada} u. por stock.`);
      });
    } catch (_) { /* noop */ }
  }

  async function abrirDrawerSiParametro() {
    const params = new URLSearchParams(window.location.search);
    if (params.get('carrito') !== '1') return;
    mostrarToastsReorden();
    history.replaceState({}, '', window.location.pathname);
    crearDrawer();
    const wrap = document.getElementById('gm-drawer');
    const panel = document.getElementById('gm-drawer-panel');
    if (!wrap || !panel) return;
    drawerAbierto = true;
    wrap.classList.remove('hidden');
    await cargarCarrito();
    renderDrawer();
    requestAnimationFrame(() => panel.classList.remove('translate-x-full'));
  }

  window.gmCarrito = { agregar, cargarCarrito, toggleDrawer, refreshNav, get datos() { return carrito; } };
  window.GlobMarketCart = window.gmCarrito;

  document.addEventListener('DOMContentLoaded', () => {
    // Puede correr antes o después del chrome; refreshNav es idempotente.
    setTimeout(refreshNav, 50);
    setTimeout(refreshNav, 400);
    void abrirDrawerSiParametro();
  });
})();
