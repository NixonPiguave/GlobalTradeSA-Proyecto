/* js/paquete.js — Configuración de catálogo (página catalogo_paquete.html). */
(function () {
  const MOQ = 10;
  const MAX = 100000;

  let productos = [];
  let cantidades = {}; // id_producto -> cantidad
  let paquete = null;
  let esFavorito = false;

  function leerId() {
    const params = new URLSearchParams(window.location.search);
    return Number(params.get('id') || 0);
  }

  /** Con MOQ cumplido se usa el precio mayorista ya rebajado (producto/categoría + paquete). */
  function precioEfectivo(p, cantidad) {
    const may = Number(p.precio_final != null ? p.precio_final : p.precio_mayorista) || 0;
    const retail = Number(p.precio_retail) || 0;
    return cantidad >= MOQ ? may : retail;
  }

  function recalcular() {
    let total = 0;
    let nItems = 0;
    let nUnidades = 0;
    const rows = document.querySelectorAll('[data-row]');
    rows.forEach((row) => {
      const id = Number(row.dataset.row);
      const qty = Number(cantidades[id] || 0);
      const p = productos.find((x) => x.id_producto === id);
      if (!p) return;
      const precio = precioEfectivo(p, qty);
      const subtotal = qty * precio;
      row.querySelector('[data-subtotal]').textContent = formatUsd(subtotal);
      row.querySelector('[data-precio-aplicado]').textContent = `${formatUsd(precio)}/u${qty >= MOQ ? ' · mayorista' : ''}`;
      total += subtotal;
      if (qty > 0) { nItems += 1; nUnidades += qty; }
    });
    const elTotal = document.getElementById('paq-total');
    const elResumen = document.getElementById('paq-resumen');
    if (elTotal) elTotal.textContent = formatUsd(total);
    if (elResumen) elResumen.textContent = nItems > 0
      ? `${nItems} producto${nItems === 1 ? '' : 's'} · ${nUnidades} unidades`
      : 'Sin productos seleccionados';
  }

  function render() {
    const lista = document.getElementById('paquete-lista');
    if (!lista) return;
    if (!productos.length) {
      lista.innerHTML = '<p class="rounded-2xl border border-slate-200 bg-white p-5 text-sm text-slate-500">Este catálogo no tiene productos configurados.</p>';
      recalcular();
      return;
    }
    const zona = paquete?.zona_label ? ` en ${paquete.zona_label}` : '';
    lista.innerHTML = productos
      .map((p) => {
        const qty = Number(cantidades[p.id_producto] || 0);
        const stock = Math.floor(p.stock_disponible || 0);
        const agotado = stock <= 0;
        const excede = qty > 0 && stock > 0 && qty > stock;
        const base = Number(p.precio_mayorista) || 0;
        const final = Number(p.precio_final != null ? p.precio_final : base) || 0;
        const rebaja = final < base
          ? ` <span class="text-slate-400 line-through font-normal">${formatUsd(base)}</span>`
          : '';
        return `
          <div data-row="${p.id_producto}" class="rounded-2xl border bg-white p-4 flex flex-wrap items-center gap-4 ${excede || agotado ? 'border-rose-300' : 'border-slate-200'}">
            <div class="h-16 w-16 rounded-xl bg-slate-50 overflow-hidden flex-shrink-0">
              ${etiquetaImagenProducto(p, 'h-full w-full object-cover')}
            </div>
            <div class="flex-1 min-w-[10rem]">
              <div class="font-bold text-slate-900 leading-tight">${escapeHtml(nombreProductoEs(p.nombre_producto))}</div>
              <div class="text-xs mt-0.5 ${agotado ? 'font-semibold text-rose-600' : 'text-slate-500'}">${agotado ? `Agotado${zona}` : `Stock: ${stock} uds.${zona}`}</div>
              <div data-precio-aplicado class="text-xs font-semibold text-blue-700 mt-0.5">${formatUsd(qty >= MOQ ? final : (Number(p.precio_retail) || 0))}/u${qty >= MOQ ? ' · mayorista' : ''}${qty >= MOQ ? rebaja : ''}</div>
            </div>
            <div class="flex items-center gap-2">
              <button type="button" data-menos="${p.id_producto}" class="h-10 w-10 rounded-xl border border-slate-200 bg-white hover:border-blue-300 transition font-bold text-lg leading-none">−</button>
              <input
                type="number" inputmode="numeric" min="0" max="${MAX}" step="1"
                data-cant="${p.id_producto}" value="${qty}"
                class="h-10 w-20 rounded-xl border border-slate-200 bg-white px-2 text-center font-bold focus:outline-none focus:ring-2 focus:ring-blue-200"
              />
              <button type="button" data-mas="${p.id_producto}" class="h-10 w-10 rounded-xl border border-slate-200 bg-white hover:border-blue-300 transition font-bold text-lg leading-none">+</button>
            </div>
            <div class="w-32 text-right">
              <div class="text-xs text-slate-500">Subtotal</div>
              <div data-subtotal class="text-lg font-extrabold text-slate-900">${formatUsd(qty * precioEfectivo(p, qty))}</div>
            </div>
          </div>
        `;
      })
      .join('');
  }

  function bind() {
    document.querySelectorAll('[data-cant]').forEach((input) => {
      const id = Number(input.dataset.cant);

      input.addEventListener('keydown', (e) => {
        if (e.key.length === 1 && !/[0-9]/.test(e.key)) e.preventDefault();
      });
      input.addEventListener('paste', (e) => {
        e.preventDefault();
        const peg = (e.clipboardData || window.clipboardData).getData('text').replace(/[^0-9]/g, '');
        if (peg) { cantidades[id] = Math.min(MAX, Number(peg)); input.value = String(cantidades[id]); recalcular(); }
      });
      input.addEventListener('change', () => {
        const v = input.value.trim();
        if (v === '' || !/^[0-9]+$/.test(v)) {
          cantidades[id] = 0;
          input.value = '0';
        } else {
          cantidades[id] = Math.min(MAX, Number(v));
          input.value = String(cantidades[id]);
        }
        actualizarFilaStock(id);
        recalcular();
      });
    });

    document.querySelectorAll('[data-mas]').forEach((btn) => {
      btn.addEventListener('click', () => {
        const id = Number(btn.dataset.mas);
        cantidades[id] = Math.min(MAX, (Number(cantidades[id] || 0) || 0) + 1);
        const input = document.querySelector(`[data-cant="${id}"]`);
        if (input) input.value = String(cantidades[id]);
        actualizarFilaStock(id);
        recalcular();
      });
    });

    document.querySelectorAll('[data-menos]').forEach((btn) => {
      btn.addEventListener('click', () => {
        const id = Number(btn.dataset.menos);
        cantidades[id] = Math.max(0, (Number(cantidades[id] || 0) || 0) - 1);
        const input = document.querySelector(`[data-cant="${id}"]`);
        if (input) input.value = String(cantidades[id]);
        actualizarFilaStock(id);
        recalcular();
      });
    });
  }

  function actualizarFilaStock(id) {
    const row = document.querySelector(`[data-row="${id}"]`);
    if (!row) return;
    const p = productos.find((x) => x.id_producto === id);
    const qty = Number(cantidades[id] || 0);
    const excede = qty > 0 && p.stock_disponible > 0 && qty > p.stock_disponible;
    row.classList.toggle('border-rose-300', excede || p.stock_disponible <= 0);
  }

  /** Cabecera del paquete: descuento vigente, zona de entrega y botón de favorito. */
  function renderCabecera() {
    const cont = document.getElementById('paq-meta');
    if (!cont || !paquete) return;
    const dto = Number(paquete.descuento_pct || 0);
    const piezas = [];
    if (dto > 0) {
      piezas.push(`<span class="inline-flex items-center rounded-full bg-rose-600 px-3 py-1 text-xs font-bold text-white">-${dto}% en el paquete</span>`);
      if (paquete.descuento_motivo) {
        piezas.push(`<span class="text-xs font-semibold text-rose-700">${escapeHtml(String(paquete.descuento_motivo))}</span>`);
      }
      if (paquete.descuento_hasta) {
        piezas.push(`<span class="text-xs text-slate-500">Vigente hasta ${escapeHtml(String(paquete.descuento_hasta))}</span>`);
      }
    }
    if (paquete.zona_label) {
      const bodega = paquete.bodega_asignada ? ` · ${escapeHtml(String(paquete.bodega_asignada))}` : '';
      piezas.push(`<span class="inline-flex items-center gap-1 rounded-full border border-blue-200 bg-blue-50 px-3 py-1 text-xs font-semibold text-blue-800">Entrega desde ${escapeHtml(String(paquete.zona_label))}${bodega}</span>`);
    }
    if (getToken()) {
      piezas.push(`<button type="button" id="paq-fav" aria-pressed="${esFavorito}"
        class="inline-flex items-center gap-1.5 rounded-full border px-3 py-1 text-xs font-semibold transition ${esFavorito ? 'border-rose-200 bg-rose-50 text-rose-700' : 'border-slate-200 bg-white text-slate-600 hover:border-rose-200'}">
        <span class="text-base leading-none">${esFavorito ? '&#9829;' : '&#9825;'}</span>${esFavorito ? 'En favoritos' : 'Guardar paquete'}
      </button>`);
    }
    cont.innerHTML = piezas.join('');
    cont.classList.toggle('hidden', piezas.length === 0);
    document.getElementById('paq-fav')?.addEventListener('click', alternarFavorito);
  }

  async function alternarFavorito() {
    const id = leerId();
    const btn = document.getElementById('paq-fav');
    if (btn) btn.disabled = true;
    try {
      if (esFavorito) {
        await apiFetch(`/api/wishlist/catalogos/${id}`, { method: 'DELETE', auth: true });
        esFavorito = false;
        showToast('success', 'Paquete quitado de favoritos');
      } else {
        await apiFetch('/api/wishlist/catalogos', { method: 'POST', auth: true, body: { id_catalogo: id } });
        esFavorito = true;
        showToast('success', 'Paquete guardado en favoritos');
      }
      renderCabecera();
    } catch (e) {
      showToast('error', e.message || 'No se pudo actualizar favoritos');
      if (btn) btn.disabled = false;
    }
  }

  async function cargarFavorito(id) {
    if (!getToken()) return false;
    try {
      const ids = await apiFetch('/api/wishlist/catalogos/ids', { auth: true });
      return (Array.isArray(ids) ? ids : []).map(Number).includes(Number(id));
    } catch {
      return false;
    }
  }

  async function cargar() {
    const id = leerId();
    const errEl = document.getElementById('paquete-error');
    const head = document.getElementById('paquete-head');
    if (!id) {
      if (errEl) { errEl.textContent = 'Falta el identificador del catálogo.'; errEl.classList.remove('hidden'); }
      return;
    }
    try {
      const [catalogo, fav] = await Promise.all([
        apiFetch(`/api/catalogos/${id}`, { auth: !!getToken() }),
        cargarFavorito(id),
      ]);
      paquete = catalogo;
      esFavorito = fav;
      productos = (catalogo.productos || []).filter((p) => p.activo !== false);
      productos.forEach((p) => { cantidades[p.id_producto] = Number(p.cantidad_base || 0); });
      document.getElementById('paq-nombre').textContent = String(catalogo.nombre || 'Catálogo');
      document.getElementById('paq-descripcion').textContent = String(catalogo.descripcion || '');
      renderCabecera();
      render();
      bind();
      recalcular();
    } catch (e) {
      if (errEl) { errEl.textContent = e.message; errEl.classList.remove('hidden'); }
      if (head) head.style.display = 'none';
    }
  }

  function reset() {
    productos.forEach((p) => { cantidades[p.id_producto] = Number(p.cantidad_base || 0); });
    render();
    bind();
    recalcular();
  }

  async function agregar() {
    const items = productos
      .map((p) => ({ id_producto: p.id_producto, cantidad: Number(cantidades[p.id_producto] || 0) }))
      .filter((i) => i.cantidad > 0);
    if (items.length === 0) {
      showToast('error', 'Configura al menos un producto con cantidad mayor a 0.');
      return;
    }
    if (!getToken()) {
      showToast('error', 'Inicia sesión para agregar el catálogo al carrito.');
      setTimeout(() => { window.location.href = '/pages/login.html'; }, 900);
      return;
    }
    const btn = document.getElementById('paq-add');
    const original = btn ? btn.textContent : '';
    if (btn) { btn.disabled = true; btn.textContent = 'Agregando…'; }
    try {
      const idCatalogo = leerId();
      await apiFetch('/api/carrito/paquete', { method: 'POST', auth: true, body: { id_catalogo: idCatalogo, items } });
      showToast('success', 'Catálogo configurado agregado al carrito.');
      if (window.gmCarrito && typeof window.gmCarrito.cargarCarrito === 'function') {
        window.gmCarrito.cargarCarrito();
      }
    } catch (e) {
      showToast('error', e.message);
    } finally {
      if (btn) { btn.disabled = false; btn.textContent = original; }
    }
  }

  document.addEventListener('DOMContentLoaded', () => {
    const addBtn = document.getElementById('paq-add');
    addBtn?.addEventListener('click', agregar);
    document.getElementById('paq-reset')?.addEventListener('click', reset);
    cargar();
  });
})();