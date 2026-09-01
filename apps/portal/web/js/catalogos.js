/* js/catalogos.js — Listado de catálogos/paquetes comprables (página catalogos.html). */
(function () {
  let favoritos = new Set();

  function autenticado() {
    return !!getToken();
  }

  async function cargarFavoritos() {
    if (!autenticado()) return new Set();
    try {
      const ids = await apiFetch('/api/wishlist/catalogos/ids', { auth: true });
      return new Set((Array.isArray(ids) ? ids : []).map(Number));
    } catch {
      return new Set();
    }
  }

  function botonFavorito(c) {
    if (!autenticado()) return '';
    const activo = favoritos.has(Number(c.id_catalogo));
    return `
      <button type="button" data-fav-paquete="${c.id_catalogo}" aria-pressed="${activo}"
              title="${activo ? 'Quitar de favoritos' : 'Guardar en favoritos'}"
              class="absolute top-3 left-3 inline-flex h-9 w-9 items-center justify-center rounded-full border border-slate-200 bg-white/95 text-lg leading-none shadow-sm transition hover:scale-105 ${activo ? 'text-rose-600' : 'text-slate-400'}">
        ${activo ? '&#9829;' : '&#9825;'}
      </button>`;
  }

  function bloquePrecio(c) {
    const dto = Number(c.descuento_pct || 0);
    const base = Number(c.precio_total_base || 0);
    const final = Number(c.precio_total_final ?? base);
    if (dto <= 0 || final >= base) {
      return `
        <div class="text-xs text-slate-500">Desde</div>
        <div class="text-xl font-extrabold text-slate-900">${formatUsd(base)}</div>`;
    }
    return `
      <div class="text-xs text-slate-500">Desde</div>
      <div class="flex items-baseline gap-2">
        <span class="text-xl font-extrabold text-emerald-700">${formatUsd(final)}</span>
        <span class="text-sm text-slate-400 line-through">${formatUsd(base)}</span>
      </div>`;
  }

  function tarjeta(c) {
    const imgs = (Array.isArray(c.imagenes) ? c.imagenes : [c.imagen_url]).filter(Boolean);
    const nImg = Math.min(imgs.length, 4);
    const collage = nImg >= 2
      ? `<div class="grid grid-cols-2 h-full">
          ${imgs.slice(0, 4).map((src, i) => `
            <img src="${escapeHtml(src)}" alt="${escapeHtml(String(c.nombre || 'Catálogo'))}" loading="lazy"
                 class="h-full w-full object-cover ${i % 2 === 0 ? 'pr-px' : 'pl-px'} ${i < 2 ? 'pb-px' : 'pt-px'}">`).join('')}
        </div>`
      : (imgs.length === 1
          ? `<img src="${escapeHtml(imgs[0])}" alt="${escapeHtml(String(c.nombre || 'Catálogo'))}" class="h-full w-full object-cover group-hover:scale-[1.02] transition duration-200">`
          : `<div class="h-full w-full flex items-center justify-center text-blue-700 text-3xl font-extrabold">${String(c.nombre || 'C').charAt(0).toUpperCase()}</div>`);

    const dto = Number(c.descuento_pct || 0);
    const cintaDto = dto > 0
      ? `<span class="absolute bottom-3 left-3 inline-flex items-center rounded-full bg-rose-600 px-3 py-1 text-xs font-bold text-white">-${dto}% paquete</span>`
      : '';
    const agotados = Number(c.n_agotados || 0);
    const avisoStock = agotados > 0
      ? `<p class="mt-2 text-xs font-medium text-amber-700">${agotados} ${agotados === 1 ? 'producto agotado' : 'productos agotados'} en tu zona de entrega</p>`
      : '';

    return `
      <div class="gm-card group relative rounded-2xl border border-slate-200 bg-white overflow-hidden flex flex-col hover:border-blue-200 hover:shadow-md transition">
        <div class="h-36 bg-slate-50 overflow-hidden relative">
          ${collage}
          ${botonFavorito(c)}
          <span class="absolute top-3 right-3 inline-flex items-center rounded-full bg-emerald-500/95 px-3 py-1 text-xs font-semibold text-white">${c.n_productos} productos</span>
          ${cintaDto}
        </div>
        <div class="p-5 flex flex-col flex-1">
          <h3 class="text-lg font-extrabold text-slate-900 leading-tight">${escapeHtml(String(c.nombre || 'Catálogo'))}</h3>
          <p class="mt-1 text-sm text-slate-600 line-clamp-2 ${c.descripcion ? '' : 'hidden'}">${escapeHtml(String(c.descripcion || ''))}</p>
          ${c.descuento_motivo && dto > 0 ? `<p class="mt-2 text-xs font-semibold text-rose-700">${escapeHtml(String(c.descuento_motivo))}</p>` : ''}
          ${avisoStock}
          <div class="mt-auto pt-4 flex items-end justify-between">
            <div>${bloquePrecio(c)}</div>
            <a href="/pages/catalogo_paquete.html?id=${c.id_catalogo}"
               class="rounded-xl bg-blue-600 text-white px-4 py-2 text-sm font-semibold group-hover:bg-blue-700 transition">Configurar →</a>
          </div>
        </div>
      </div>`;
  }

  function enlazarFavoritos(grid, catalogos) {
    grid.querySelectorAll('[data-fav-paquete]').forEach((btn) => {
      btn.addEventListener('click', async (ev) => {
        ev.preventDefault();
        const id = Number(btn.dataset.favPaquete);
        const activo = favoritos.has(id);
        btn.disabled = true;
        try {
          if (activo) {
            await apiFetch(`/api/wishlist/catalogos/${id}`, { method: 'DELETE', auth: true });
            favoritos.delete(id);
            showToast('success', 'Paquete quitado de favoritos');
          } else {
            await apiFetch('/api/wishlist/catalogos', {
              method: 'POST',
              auth: true,
              body: { id_catalogo: id },
            });
            favoritos.add(id);
            showToast('success', 'Paquete guardado en favoritos');
          }
          pintar(grid, catalogos);
        } catch (e) {
          showToast('error', e.message || 'No se pudo actualizar favoritos');
        } finally {
          btn.disabled = false;
        }
      });
    });
  }

  function pintar(grid, catalogos) {
    grid.innerHTML = catalogos.map(tarjeta).join('');
    enlazarFavoritos(grid, catalogos);
  }

  async function render() {
    const grid = document.getElementById('catalogos-grid');
    const errEl = document.getElementById('catalogos-error');
    if (!grid) return;

    grid.innerHTML = Array.from({ length: 6 })
      .map(() => `
        <div class="gm-card rounded-2xl border border-slate-200 bg-white overflow-hidden animate-pulse">
          <div class="h-36 bg-slate-100"></div>
          <div class="p-5 space-y-3">
            <div class="h-5 w-2/3 bg-slate-100 rounded"></div>
            <div class="h-4 w-full bg-slate-100 rounded"></div>
            <div class="h-8 w-1/3 bg-slate-100 rounded"></div>
          </div>
        </div>`)
      .join('');
    if (errEl) errEl.classList.add('hidden');

    try {
      const catalogos = await apiFetch('/api/catalogos', { auth: autenticado() });
      favoritos = await cargarFavoritos();
      if (!Array.isArray(catalogos) || catalogos.length === 0) {
        grid.innerHTML = '<p class="col-span-full rounded-2xl border border-slate-200 bg-white p-5 text-sm text-slate-500">Aún no hay catálogos configurados.</p>';
        return;
      }
      pintar(grid, catalogos);
    } catch (e) {
      console.error('catalogos.render', e);
      if (errEl) {
        errEl.textContent = e.message || 'No se pudieron cargar los catálogos. Recarga la página (Ctrl+F5).';
        errEl.classList.remove('hidden');
      }
      grid.innerHTML = '';
    }
  }

  document.addEventListener('DOMContentLoaded', render);
})();
