/* nav.js — Barra superior GlobalTrade: menús por dominio (sin Operativo/Táctico/Estratégico) */
(function () {
  const NAV = [
    {
      label: 'Dirección',
      items: [
        { page: 'dashboard', perm: 'mod.dashboard', label: 'Panel ejecutivo' },
        { page: 'analitica', perm: 'mod.dashboard', label: 'Inteligencia de datos' },
        { page: 'estrategia', perm: 'mod.estrategia', label: 'Estrategia e IA' },
      ],
    },
    {
      label: 'Comercial',
      items: [
        { page: 'pedidos', perm: 'mod.operaciones', label: 'Pedidos' },
        { page: 'ventas', perm: 'mod.ventas', label: 'Ventas históricas' },
        { page: 'clientes', perm: 'mod.clientes', label: 'Clientes' },
        { page: 'catalogo', perm: 'mod.catalogo', label: 'Catálogo' },
        { page: 'marketing', perm: 'mod.marketing', label: 'Marketing digital' },
      ],
    },
    {
      label: 'Operaciones',
      items: [
        { page: 'inventario', perm: 'mod.inventario', label: 'Inventario' },
        { page: 'compras', perm: 'mod.compras', label: 'Compras' },
        { page: 'logistica', perm: 'mod.logistica', label: 'Logística' },
        { page: 'finanzas', perm: 'mod.finanzas', label: 'Finanzas' },
        { page: 'operaciones', perm: 'mod.operaciones', label: 'Centro operaciones' },
      ],
    },
    {
      label: 'Informes',
      items: [
        { page: 'reportes', perm: 'mod.reportes', label: 'Centro de informes' },
        { page: 'rentabilidad', perm: 'mod.ventas', label: 'Rentabilidad' },
      ],
    },
    {
      label: 'Sistema',
      items: [
        { page: 'configuracion', perm: 'mod.gobierno', label: 'Configuración' },
        { page: 'usuarios', perm: 'mod.gobierno', label: 'Usuarios y roles' },
        { page: 'auditoria', perm: 'mod.gobierno', label: 'Auditoría' },
        { page: 'regiones', perm: 'mod.catalogo', label: 'Regiones' },
        { page: 'paises', perm: 'mod.catalogo', label: 'Países' },
        { page: 'tipos-producto', perm: 'mod.catalogo', label: 'Categorías maestras' },
        { page: 'canales', perm: 'mod.catalogo', label: 'Canales' },
        { page: 'prioridades', perm: 'mod.catalogo', label: 'Prioridades' },
        { page: 'generador', perm: 'mod.reportes', label: 'Generador / ETL' },
      ],
    },
  ];

  function esc(s) {
    return String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  }

  function renderTopNav() {
    const host = document.getElementById('topnav-menus');
    if (!host) return;
    host.innerHTML = NAV.map((g) => `
      <div class="topnav-group">
        <button type="button" class="topnav-trigger" aria-haspopup="true">${esc(g.label)}</button>
        <div class="topnav-dropdown" role="menu">
          ${g.items.map((it) => `
            <button type="button" class="nav-item" data-page="${esc(it.page)}" data-perm="${esc(it.perm)}" role="menuitem">${esc(it.label)}</button>
          `).join('')}
        </div>
      </div>`).join('');

    document.querySelectorAll('.topnav-trigger').forEach((btn) => {
      btn.addEventListener('click', (e) => {
        e.stopPropagation();
        const group = btn.closest('.topnav-group');
        const open = group.classList.contains('open');
        document.querySelectorAll('.topnav-group.open').forEach((g) => g.classList.remove('open'));
        if (!open) group.classList.add('open');
      });
    });
    document.addEventListener('click', () => {
      document.querySelectorAll('.topnav-group.open').forEach((g) => g.classList.remove('open'));
    });
    const toggle = document.getElementById('menu-toggle');
    const topnav = document.getElementById('topnav');
    toggle?.addEventListener('click', (e) => {
      e.stopPropagation();
      topnav?.classList.toggle('open');
    });
  }

  window.initTopNav = renderTopNav;
})();
