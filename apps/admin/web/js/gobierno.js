/*
 * gobierno.js — Página "Usuarios y roles": gobierno de acceso configurable.
 * Dos pestañas: Usuarios (CRUD) y Roles y permisos (matriz rol → módulos).
 * Requiere el permiso mod.gobierno (backend lo exige en /api/gobierno).
 */
/* global api, toast, PAGES, createDataView, createTabsView, uiModal, uiConfirm, esc, badge */

PAGES.usuarios = { title: 'Usuarios y roles', load: loadGobierno };

let gobTabs = null;
let vistaUsuarios = null;
let gobRoles = null;
let gobPermisosCache = null;
let gobRegionesCache = null;

const gobRolOpts = () => (gobRoles || [])
  .filter((r) => r.nombre !== 'cliente')
  .map((r) => ({ value: r.nombre, label: `${r.nombre}${r.protegido ? ' (protegido)' : ''}` }));

async function gobRegionOpts() {
  if (gobRegionesCache) return gobRegionesCache;
  const filtros = await api('/maestras/filtros');
  gobRegionesCache = (filtros?.regiones || []).map((r) => ({ value: r.id_region, label: r.region }));
  return gobRegionesCache;
}

async function gobCargarCatalogos() {
  if (gobRoles && gobPermisosCache) return;
  const [roles, permisos] = await Promise.all([
    api('/gobierno/roles'),
    api('/gobierno/permisos'),
  ]);
  gobRoles = roles || [];
  gobPermisosCache = permisos || [];
}

async function loadGobierno() {
  await gobCargarCatalogos();
  if (!gobTabs) {
    gobTabs = createTabsView('vista-gobierno', [
      { id: 'usuarios', label: 'Usuarios', onActivo: () => { if (vistaUsuarios) void vistaUsuarios.recargar(); } },
      { id: 'roles', label: 'Roles y permisos', onActivo: () => void renderRolesPanel(gobTabs.roles) },
    ]);
    vistaUsuarios = crearVistaUsuarios(gobTabs.usuarios);
  }
  if (vistaUsuarios) await vistaUsuarios.recargar();
}

// ---------------------------------------------------------------------------
// Usuarios
// ---------------------------------------------------------------------------

function crearVistaUsuarios(cont) {
  const st = { page: 1, page_size: 20 };
  return createDataView(cont, {
    state: st,
    autoLoad: false,
    buscar: { id: 'gob-q', placeholder: 'Email o nombre...' },
    filtrosHtml: `
      <div class="field"><label>Rol</label>
        <select id="gob-filtro-rol" data-dv-auto>
          <option value="">Todos</option>
          ${gobRolOpts().map((o) => `<option value="${esc(o.value)}">${esc(o.label)}</option>`).join('')}
        </select>
      </div>
      <div class="field"><label>Estado</label>
        <select id="gob-filtro-activo" data-dv-auto>
          <option value="">Todos</option>
          <option value="1">Activos</option>
          <option value="0">Inactivos</option>
        </select>
      </div>
      <button type="button" class="btn btn-primary" id="gob-reactivar" data-dv-silencioso style="display:none"></button>`,
    columnas: [
      { key: 'id_usuario', label: 'ID', align: 'num' },
      { key: 'email', label: 'Email' },
      { key: 'nombre', label: 'Nombre' },
      { key: 'rol', label: 'Rol' },
      { key: 'region', label: 'Región', render: (u) => esc(u.region || '—') },
      { key: 'activo', label: 'Estado', align: 'center', render: (u) => u.activo ? '<span class="badge badge-activo">Activo</span>' : '<span class="badge badge-inactivo">Inactivo</span>' },
    ],
    cargar: async (s) => {
      const params = new URLSearchParams({ limit: '200' });
      const q = document.getElementById('gob-q')?.value?.trim();
      const rol = document.getElementById('gob-filtro-rol')?.value;
      const activo = document.getElementById('gob-filtro-activo')?.value;
      if (q) params.set('q', q);
      if (rol) params.set('rol', rol);
      if (activo !== '') params.set('activo', activo);
      return api(`/gobierno/usuarios?${params}`);
    },
    filas: (res) => res,
    total: (res) => (res || []).length,
    filaClase: (r) => (r.activo ? '' : 'row-inactive'),
    titulo: (r) => r.email,
    resumen: (r) => `<div class="detail-grid">
      <div><strong>Nombre:</strong> ${esc(r.nombre || '—')}</div>
      <div><strong>Rol:</strong> ${esc(r.rol)}</div>
      <div><strong>Región:</strong> ${esc(r.region || '—')}</div>
      <div><strong>Estado:</strong> ${r.activo ? 'Activo' : 'Inactivo'}</div>
      <div><strong>Registro:</strong> ${esc(r.fecha_registro || '—')}</div>
    </div><p class="meta">El rol activa/desactiva acciones de este usuario. El usuario debe volver a iniciar sesión para ver los cambios.</p>`,
    key: (r) => r.id_usuario,
    vacio: 'Sin usuarios con esos criterios',
    acciones: {
      agregar: () => abrirModalUsuario(null),
      modificar: (row) => abrirModalUsuario(row),
      eliminar: async (row) => {
        const res = await api(`/gobierno/usuarios/${row.id_usuario}`, { method: 'DELETE' });
        return res.activo === false ? 'Usuario desactivado' : 'Usuario procesado';
      },
    },
    puedeEliminar: (row) => row.rol !== 'admin' && row.activo !== false,
    extras: (row) => row.activo ? [] : [{ label: 'Reactivar', clase: 'btn-success', opensModal: true, fn: () => abrirModalUsuario(row, true) }],
  });
}

async function abrirModalUsuario(row, soloReactivar) {
  await gobCargarCatalogos();
  const regionOpts = await gobRegionOpts();
  const esNuevo = !row;
  if (soloReactivar && row) {
    return uiConfirm({
      titulo: 'Reactivar usuario',
      mensaje: `¿Reactivar el acceso de <strong>${esc(row.email)}</strong>?`,
      textoAceptar: 'Reactivar',
      onConfirm: async () => {
        await api(`/gobierno/usuarios/${row.id_usuario}`, { method: 'PUT', body: { activo: true } });
        toast('Usuario reactivado');
        vistaUsuarios?.recargar();
      },
    });
  }
  uiModal({
    modo: esNuevo ? 'Agregar' : 'Actualizar',
    tituloExtra: esNuevo ? 'Usuario del panel' : row.email,
    ancho: 'md',
    textoAceptar: esNuevo ? 'Crear usuario' : 'Guardar cambios',
    campos: [
      ...(esNuevo ? [
        { key: 'email', label: 'Email', type: 'email', required: true, placeholder: 'nombre@empresa.com' },
        { key: 'password', label: 'Contraseña (mín. 6 caracteres)', type: 'password', required: true },
      ] : []),
      ...(!esNuevo ? [
        { key: 'emailv', type: 'html', value: `<input type="hidden" value="${esc(row.email)}">` },
        { key: 'password', label: 'Nueva contraseña (dejar vacío para no cambiar)', type: 'password' },
      ] : []),
      { key: 'nombre', label: 'Nombre completo', value: row?.nombre || '' },
      { key: 'rol', label: 'Rol', type: 'select', options: gobRolOpts(), value: row?.rol || '' },
      { key: 'id_region', label: 'Región (opcional)', type: 'select', options: [{ value: '', label: '— Sin región —' }, ...regionOpts], value: row?.id_region ?? '' },
      ...(esNuevo ? [] : [{ key: 'activo', label: 'Usuario activo', type: 'checkbox', value: row.activo }]),
    ],
    onAceptar: async (values) => {
      const id_region = values.id_region === '' || values.id_region == null ? null : Number(values.id_region);
      if (esNuevo) {
        await api('/gobierno/usuarios', { method: 'POST', body: {
          email: values.email,
          password: values.password,
          rol: values.rol,
          nombre: values.nombre || '',
          id_region,
        } });
        toast('Usuario creado');
      } else {
        const body = { rol: values.rol, id_region };
        if (values.nombre != null && String(values.nombre).trim() !== '') body.nombre = values.nombre.trim();
        if (values.password) body.password = values.password;
        if (values.activo !== undefined) body.activo = values.activo;
        await api(`/gobierno/usuarios/${row.id_usuario}`, { method: 'PUT', body });
        toast('Usuario actualizado');
      }
      await vistaUsuarios?.recargar();
    },
  });
}

// ---------------------------------------------------------------------------
// Roles y permisos
// ---------------------------------------------------------------------------

// Orden y etiquetas unificadas para la matriz de permisos
const GOB_GRUPO_ORDEN = ['Dirección', 'Comercial', 'Informes', 'Operaciones', 'Sistema', 'Otros'];
const GOB_GRUPO_ALIAS = {
  'Comercial / Informes': 'Informes',
  'Comercial / Sistema': 'Sistema',
};

function gobAgruparPermisos(permisos) {
  const map = new Map();
  (permisos || []).forEach((p) => {
    const label = GOB_GRUPO_ALIAS[p.grupo] || p.grupo || 'Otros';
    if (!map.has(label)) map.set(label, []);
    map.get(label).push(p);
  });
  return GOB_GRUPO_ORDEN
    .filter((g) => map.has(g))
    .map((label) => ({ label, items: map.get(label) }))
    .concat(
      [...map.keys()]
        .filter((g) => !GOB_GRUPO_ORDEN.includes(g))
        .map((label) => ({ label, items: map.get(label) })),
    );
}

function wireGobPermToggles(root) {
  root?.querySelectorAll('.gob-perm-row input[type="checkbox"]').forEach((inp) => {
    inp.addEventListener('change', () => {
      inp.closest('.gob-perm-row')?.classList.toggle('on', inp.checked);
      const card = inp.closest('.gob-rol-card');
      const total = card?.querySelectorAll('.gob-perm-row input[type="checkbox"]').length || 0;
      const on = card?.querySelectorAll('.gob-perm-row input[type="checkbox"]:checked').length || 0;
      const badge = card?.querySelector('[data-gob-count]');
      if (badge) badge.textContent = `${on}/${total}`;
      const bar = card?.querySelector('[data-gob-bar]');
      if (bar && total) bar.style.width = `${Math.round((on / total) * 100)}%`;
    });
  });
}

async function renderRolesPanel(cont) {
  const [roles, permisos] = await Promise.all([
    api('/gobierno/roles'),
    api('/gobierno/permisos'),
  ]);
  gobRoles = roles;
  gobPermisosCache = permisos;
  cont.innerHTML = `
    <div class="gob-roles-toolbar card">
      <div class="gob-roles-intro">
        <div class="card-title">Roles del panel</div>
        <p class="meta">Activa los módulos del menú que puede ver cada rol. Los cambios aplican al volver a iniciar sesión.</p>
      </div>
      <button type="button" class="btn btn-success" id="gob-nuevo-rol">+ Nuevo rol</button>
    </div>
    <div class="gob-roles-layout" id="gob-roles-lista">${renderRolesList(roles, permisos)}</div>`;
  cont.querySelector('#gob-nuevo-rol').addEventListener('click', abrirModalNuevoRol);
  wireGobPermToggles(cont);
}

function renderRolesList(roles, permisos) {
  const staff = roles.filter((r) => r.nombre !== 'cliente');
  const grupos = gobAgruparPermisos(permisos);
  const totalPerms = permisos.length;

  const permisosHtml = (rolId, assigned) => grupos.map((g) => `
      <section class="gob-perm-grupo">
        <h5 class="gob-perm-grupo-titulo">${esc(g.label)}</h5>
        <div class="gob-perm-matrix">
          ${g.items.map((p) => {
            const on = assigned.has(p.codigo);
            const hint = p.paginas || '';
            return `<label class="gob-perm-row${on ? ' on' : ''}" title="${esc(hint)}">
              <input type="checkbox" data-rol-perm="${rolId}" data-codigo="${esc(p.codigo)}" ${on ? 'checked' : ''}>
              <span class="gob-perm-row-body">
                <span class="gob-perm-name">${esc(p.label || p.codigo.replace(/^mod\./, ''))}</span>
                ${hint ? `<span class="gob-perm-hint">${esc(hint)}</span>` : ''}
              </span>
            </label>`;
          }).join('')}
        </div>
      </section>`).join('');

  return staff.map((rol) => {
    if (rol.protegido) {
      return `<article class="gob-rol-card gob-rol-protegido">
        <header class="gob-rol-head">
          <div class="gob-rol-title-wrap">
            <h4 class="gob-rol-nombre">${esc(rol.nombre)}</h4>
            <span class="badge badge-admin">Acceso total</span>
          </div>
          <p class="gob-rol-meta">${esc(rol.descripcion || 'Administrador')} · ${rol.usuarios} usuario(s)</p>
        </header>
        <p class="gob-rol-nota">Todos los módulos (${totalPerms}) sin restricción.</p>
      </article>`;
    }
    const assigned = new Set(rol.permisos || []);
    const nOn = assigned.size;
    const pct = totalPerms ? Math.round((nOn / totalPerms) * 100) : 0;
    return `<article class="gob-rol-card" data-rol="${rol.id_rol}">
      <header class="gob-rol-head">
        <div class="gob-rol-title-wrap">
          <h4 class="gob-rol-nombre">${esc(rol.nombre)}</h4>
          <span class="gob-rol-count" data-gob-count>${nOn}/${totalPerms}</span>
        </div>
        <p class="gob-rol-meta">${esc(rol.descripcion || 'Sin descripción')} · ${rol.usuarios} usuario(s)</p>
        <div class="gob-rol-progress" aria-hidden="true"><span data-gob-bar style="width:${pct}%"></span></div>
        <div class="gob-rol-acciones">
          <button type="button" class="btn btn-ghost btn-sm" data-goact="editar" data-id="${rol.id_rol}">Editar</button>
          <button type="button" class="btn btn-ghost btn-sm gob-btn-danger" data-goact="eliminar" data-id="${rol.id_rol}" ${rol.usuarios ? 'disabled title="En uso"' : ''}>Eliminar</button>
        </div>
      </header>
      <div class="gob-rol-body">${permisosHtml(rol.id_rol, assigned)}</div>
      <footer class="gob-rol-foot">
        <button type="button" class="btn btn-success btn-sm" data-goact="guardar" data-id="${rol.id_rol}">Guardar permisos</button>
        <span class="meta gob-rol-msg" data-mensaje="${rol.id_rol}"></span>
      </footer>
    </article>`;
  }).join('');
}

function abrirModalNuevoRol() {
  uiModal({
    modo: 'Agregar',
    tituloExtra: 'Nuevo rol',
    textoAceptar: 'Crear rol',
    campos: [
      { key: 'nombre', label: 'Nombre del rol (sin espacios)', required: true, placeholder: 'ej: gerente' },
      { key: 'descripcion', label: 'Descripción', type: 'textarea' },
    ],
    onAceptar: async (values) => {
      await api('/gobierno/roles', { method: 'POST', body: { nombre: values.nombre.trim(), descripcion: values.descripcion } });
      toast('Rol creado');
      renderRolesPanel(gobTabs.roles);
    },
  });
}

function abrirModalEditarRol(rol) {
  uiModal({
    modo: 'Actualizar',
    tituloExtra: rol.nombre,
    textoAceptar: 'Guardar',
    campos: [
      { key: 'nombre', label: 'Nombre', value: rol.nombre },
      { key: 'descripcion', label: 'Descripción', type: 'textarea', value: rol.descripcion || '' },
    ],
    onAceptar: async (values) => {
      await api(`/gobierno/roles/${rol.id_rol}`, { method: 'PUT', body: { nombre: values.nombre.trim(), descripcion: values.descripcion } });
      toast('Rol actualizado');
      renderRolesPanel(gobTabs.roles);
    },
  });
}

// ---------------------------------------------------------------------------
// Eventos
// ---------------------------------------------------------------------------

document.addEventListener('click', async (e) => {
  const btn = e.target.closest('[data-goact]');
  if (!btn) return;
  const act = btn.dataset.goact;
  const id = Number(btn.dataset.id);
  const cont = gobTabs?.roles;
  if (!cont || !cont.isConnected) return;
  if (act === 'guardar') {
    const cks = cont.querySelectorAll(`input[data-rol-perm="${id}"]`);
    const codigos = [...cks].filter((c) => c.checked).map((c) => c.dataset.codigo);
    const btnG = btn;
    btnG.disabled = true;
    try {
      const res = await api(`/gobierno/roles/${id}/permisos`, { method: 'PUT', body: { permisos: codigos } });
      const msg = cont.querySelector(`[data-mensaje="${id}"]`);
      if (msg) msg.textContent = `${res.actualizados} permisos asignados`;
      toast('Permisos guardados');
    } finally {
      btnG.disabled = false;
    }
    renderRolesPanel(cont);
    return;
  }
  if (act === 'editar') {
    const rol = gobRoles.find((r) => r.id_rol === id);
    if (rol) abrirModalEditarRol(rol);
  }
  if (act === 'eliminar') {
    const rol = gobRoles.find((r) => r.id_rol === id);
    if (!rol || rol.usuarios > 0) return;
    uiConfirm({
      titulo: 'Eliminar rol',
      mensaje: `¿Eliminar el rol <strong>${esc(rol.nombre)}</strong>? Si algún usuario lo usa, no se podrá eliminar.`,
      textoAceptar: 'Eliminar rol',
      onConfirm: async () => {
        await api(`/gobierno/roles/${id}`, { method: 'DELETE' });
        toast('Rol eliminado');
        renderRoles();
      },
    });
  }
});

async function renderRoles() {
  if (gobTabs?.roles) await renderRolesPanel(gobTabs.roles);
}