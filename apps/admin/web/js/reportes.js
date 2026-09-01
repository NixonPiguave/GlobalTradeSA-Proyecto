/* js/reportes.js — Catálogo, filtros, vista, gráficos, resumen IA y export PDF/CSV.
   Requiere permiso mod.reportes (backend). */

const REP_FILTRO_DEFS = [
  { key: 'desde', label: 'Desde', type: 'date' },
  { key: 'hasta', label: 'Hasta', type: 'date' },
  { key: 'region', label: 'Región', type: 'select', dinamico: 'regiones' },
  { key: 'country', label: 'País', type: 'select', dinamico: 'paises' },
  { key: 'sales_channel', label: 'Canal', type: 'select', opciones: ['Online', 'Offline'] },
  { key: 'origen', label: 'Origen', type: 'select', opciones: ['historico', 'portal'] },
  { key: 'estado', label: 'Estado', type: 'text' },
  { key: 'producto', label: 'Producto', type: 'text' },
  { key: 'almacen', label: 'Almacén', type: 'number' },
  { key: 'limite', label: 'Filas máx.', type: 'number' },
];

const REP_OPCIONES_DINAMICAS = {
  regiones: () => (filterCache?.regiones || []).map((r) => r.region),
  paises: () => (filterCache?.paises || []).map((p) => p.country),
};

/** Nivel IA automático según tipo de informe (sin selector en UI). */
function nivelIAParaReporte(nombre) {
  const n = String(nombre || '');
  if (['informe-operativo', 'stock-bajo', 'kardex', 'recepciones', 'pedidos-por-estado', 'inventario-valorizado', 'compras'].includes(n)) {
    return 'operativo';
  }
  if (['informe-gerencial', 'informe-financiero', 'resumen-financiero', 'rentabilidad-producto'].includes(n)) {
    return 'estrategico';
  }
  return 'tactico';
}

const reportesState = { catalogo: null, nombre: null, ultimoVista: null, panel: 'simples' };

function escRep(s) {
  return String(s == null ? '' : s).replace(/[&<>"']/g, (c) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
  }[c]));
}

function filtrosReporteHtml(filtros) {
  return REP_FILTRO_DEFS.filter((d) => filtros.includes(d.key)).map((d) => {
    const opciones = d.opciones || (d.dinamico ? (REP_OPCIONES_DINAMICAS[d.dinamico]?.() || []) : []);
    const input = opciones.length
      ? `<select id="rep-f-${d.key}"><option value="">Todos</option>${opciones.map((o) => `<option value="${escRep(o)}">${escRep(o)}</option>`).join('')}</select>`
      : `<input id="rep-f-${d.key}" type="${d.type}" placeholder="">`;
    return `<div class="field"><label>${d.label}</label>${input}</div>`;
  }).join('');
}

function leerFiltrosReporte() {
  const q = new URLSearchParams();
  REP_FILTRO_DEFS.forEach((d) => {
    const el = document.getElementById(`rep-f-${d.key}`);
    if (el && el.value.trim() !== '') q.set(d.key, el.value.trim());
  });
  return q;
}

function validateRepFechas() {
  if (typeof capDateInputs === 'function') capDateInputs(document.getElementById('rep-trabajo'));
  if (typeof validateDateRange === 'function') {
    return validateDateRange('rep-f-desde', 'rep-f-hasta');
  }
  return true;
}

function renderReportesKpis(kpis) {
  if (!Array.isArray(kpis) || !kpis.length) return '';
  return `<div class="kpi-grid rep-kpi-grid">${kpis.map((k) => `
    <div class="kpi-card"><div class="label">${escRep(k.label)}</div><div class="value">${escRep(k.value)}</div></div>
  `).join('')}</div>`;
}

/** Solo graficar secciones con sentido visual (evita ruido en resúmenes/detalle). */
function sectionShouldChart(titulo) {
  const t = String(titulo || '');
  if (/detalle|resumen del período|resumen del periodo|nota|filtro/i.test(t)) return false;
  return /por\s+pa[ií]s|por\s+mes|por\s+canal|por\s+regi|por\s+estado|por\s+tipo|por\s+proveedor|top\s*\d*|productos|ingresos|rentabilidad|clientes|proveedores|stock|env[ií]os|movimientos|prioridad|origen|tesorer|cuenta|balance|compras|canal/i.test(t)
    || !t;
}

function renderReporteTabla(seccion, opts = {}) {
  const headers = seccion.headers || [];
  const rows = seccion.rows || [];
  if (!rows.length) return '<p class="meta">Sin datos para los filtros indicados.</p>';
  const limit = opts.collapsedLimit ?? 8;
  const sid = opts.sectionId || `sec-${Math.random().toString(36).slice(2, 8)}`;
  const needsCollapse = rows.length > limit;
  const visible = needsCollapse ? rows.slice(0, limit) : rows;
  const hidden = needsCollapse ? rows.slice(limit) : [];
  const filaHtml = (r) => `<tr>${r.map((c) => `<td>${escRep(c)}</td>`).join('')}</tr>`;
  return `
    <div class="table-wrap rep-table-wrap" data-sec="${escRep(sid)}">
      <table>
        <thead><tr>${headers.map((h) => `<th>${escRep(h)}</th>`).join('')}</tr></thead>
        <tbody>${visible.map(filaHtml).join('')}</tbody>
        ${hidden.length ? `<tbody class="rep-more-rows hidden">${hidden.map(filaHtml).join('')}</tbody>` : ''}
      </table>
    </div>
    ${needsCollapse ? `
      <div class="rep-collapse-bar">
        <button type="button" class="btn btn-secondary btn-sm rep-toggle-more" data-sec="${escRep(sid)}" data-expanded="0">
          Ver más (${hidden.length} filas)
        </button>
        <span class="meta">Mostrando ${limit} de ${rows.length}</span>
      </div>` : ''}
    ${seccion.totales ? `<p class="meta" style="margin-top:.6rem">Totales: ${escRep(seccion.totales)}</p>` : ''}`;
}

function chartForSection(sec, chartIdxRef) {
  if (!sec.rows?.length || !sec.headers?.length) return '';
  if (!sectionShouldChart(sec.titulo || sec.nombre || '')) return '';
  const id = `rep-chart-${chartIdxRef.i++}`;
  setTimeout(() => {
    if (typeof GTChart?.chartFromTable === 'function') {
      GTChart.chartFromTable(id, sec.headers, sec.rows, { limit: 12 });
    }
  }, 0);
  return `<div class="chart-wrap rep-chart" style="height:260px;margin-top:.75rem"><canvas id="${id}"></canvas></div>`;
}

function renderReporteResultado(datos) {
  const cont = document.getElementById('rep-resultado');
  if (!cont) return;
  reportesState.ultimoVista = datos;
  const chartIdx = { i: 0 };
  let cuerpo = '';

  if (datos.tipo === 'compuesto') {
    const secciones = datos.secciones || [];
    // Módulos: KPIs arriba; gráficos destacados; tablas por pestaña/acordeón
    const conChart = secciones.filter((s) => sectionShouldChart(s.titulo));
    const sinChart = secciones.filter((s) => !sectionShouldChart(s.titulo));

    const chartsHtml = conChart.slice(0, 4).map((sec, i) => `
      <div class="card rep-module-card">
        <div class="card-title">${escRep(sec.titulo || 'Gráfico')}</div>
        ${chartForSection(sec, chartIdx)}
        ${renderReporteTabla(sec, { sectionId: `rep-c${i}`, collapsedLimit: 6 })}
      </div>`).join('');

    const tabsHtml = sinChart.length ? `
      <div class="card rep-modules" style="grid-column:1/-1">
        <div class="card-title">Detalle por módulo</div>
        <div class="rep-tabs" role="tablist">
          ${sinChart.map((sec, i) => `
            <button type="button" class="rep-tab ${i === 0 ? 'active' : ''}" data-rep-tab="${i}" role="tab">
              ${escRep((sec.titulo || `Módulo ${i + 1}`).slice(0, 40))}
            </button>`).join('')}
        </div>
        ${sinChart.map((sec, i) => `
          <div class="rep-tab-panel ${i === 0 ? '' : 'hidden'}" data-rep-panel="${i}">
            <p class="meta">${escRep(sec.nota || datos.subtitulo || '')}</p>
            ${renderReporteTabla(sec, { sectionId: `rep-t${i}`, collapsedLimit: 10 })}
          </div>`).join('')}
      </div>` : '';

    cuerpo = `
      <div class="rep-charts-grid">${chartsHtml}</div>
      ${tabsHtml}
      ${!conChart.length && !sinChart.length ? '<p class="meta">Sin secciones.</p>' : ''}`;
  } else {
    const canChart = !!(datos.headers?.length && datos.rows?.length);
    const chartId = 'rep-chart-main';
    cuerpo = `
      <div class="card rep-simple-card" style="grid-column:1/-1">
        <div class="card-title">${escRep(datos.titulo)}</div>
        <p class="meta">${escRep(datos.subtitulo)}${datos._queryTimeMs != null ? ` · consulta ${datos._queryTimeMs} ms` : ''}</p>
        ${canChart ? `<div class="chart-wrap rep-chart tall" style="height:300px;margin:.75rem 0 1rem"><canvas id="${chartId}"></canvas></div>` : ''}
        ${renderReporteTabla(datos, { sectionId: 'rep-main', collapsedLimit: 12 })}
      </div>`;
    if (canChart) {
      setTimeout(() => {
        if (typeof GTChart?.chartFromTable === 'function') {
          const ok = GTChart.chartFromTable(chartId, datos.headers, datos.rows, { limit: 14 });
          if (!ok && sectionShouldChart(datos.titulo)) {
            GTChart.chartFromTable(chartId, datos.headers, datos.rows, { limit: 14 });
          }
        }
      }, 0);
    }
  }

  cont.innerHTML = `
    <div class="rep-motor-bar">
      <span class="rep-motor-badge rep-motor-${escRep((datos.motor || 'DuckDB').toLowerCase())}">
        ${escRep(datos.motor || 'DuckDB')}${datos.orquestacion ? ` · ${escRep(datos.orquestacion)}` : ''}
      </span>
      ${datos._queryTimeMs != null ? `<span class="meta">Consulta ${datos._queryTimeMs} ms</span>` : ''}
    </div>
    <div id="rep-ia-slot"></div>
    ${renderReportesKpis(datos.kpis)}
    ${cuerpo}`;

  cont.querySelectorAll('.rep-toggle-more').forEach((btn) => {
    btn.addEventListener('click', () => {
      const wrap = cont.querySelector(`.rep-table-wrap[data-sec="${btn.dataset.sec}"]`);
      const more = wrap?.querySelector('.rep-more-rows');
      if (!more) return;
      const expanded = btn.dataset.expanded === '1';
      more.classList.toggle('hidden', expanded);
      btn.dataset.expanded = expanded ? '0' : '1';
      const totalHidden = more.querySelectorAll('tr').length;
      btn.textContent = expanded ? `Ver más (${totalHidden} filas)` : 'Ver menos';
      const meta = btn.parentElement?.querySelector('.meta');
      if (meta) {
        const shown = wrap.querySelectorAll('tbody > tr').length;
        meta.textContent = expanded
          ? `Mostrando ${shown - totalHidden} de ${shown}`
          : `Mostrando todas (${shown})`;
      }
    });
  });

  cont.querySelectorAll('[data-rep-tab]').forEach((tab) => {
    tab.addEventListener('click', () => {
      const idx = tab.dataset.repTab;
      cont.querySelectorAll('[data-rep-tab]').forEach((t) => t.classList.toggle('active', t.dataset.repTab === idx));
      cont.querySelectorAll('[data-rep-panel]').forEach((p) => {
        p.classList.toggle('hidden', p.dataset.repPanel !== idx);
      });
    });
  });

  const tiempo = document.getElementById('rep-tiempo');
  if (tiempo && datos._queryTimeMs != null) tiempo.textContent = `Consulta: ${datos._queryTimeMs} ms`;
}

/** Quita think/razonamiento, metadatos del modelo y basura del prompt. */
function sanitizarTextoIA(texto) {
  let t = String(texto || '');
  t = t.replace(/<(think|thinking|reasoning|redacted_thinking|reflection)\b[^>]*>[\s\S]*?<\/\1>/gi, '');
  t = t.replace(/<\/?think\b[^>]*>/gi, '');
  if (/analyze user input|role:\s*|do not invent|max\s*\d+\s*words/i.test(t)) {
    const parts = t.split(/(?=\n#{1,4}\s|\n\*\*[A-ZÁÉÍÓÚ])/);
    const useful = parts.filter((p) =>
      /resumen|panorama|cuadro|oportunidad|proyec|riesgo|decisi|priorid|mercado|alerta|acci[oó]n|hallazgo|recomend/i.test(p));
    if (useful.length) t = useful.join('\n');
  }
  t = t.replace(/(?:^|\n)\s*(?:Constraints?|Data [Pp]rovided|Key [Dd]ata [Pp]oints|Draft|JSON)[:\s][\s\S]*?(?=\n\n|\n#{1,4}\s|\n\*\*|$)/gi, '\n');
  t = t.split('\n').filter((line) => {
    const l = line.trim();
    if (!l) return true;
    if (/^~?\d+\s*\.?$/.test(l)) return false;
    if (/^total:\s*~?\d+/i.test(l)) return false;
    if (/^(need to trim|let's count|slightly over)/i.test(l)) return false;
    return true;
  }).join('\n');
  return t.trim();
}

function esCuerpoIAJunk(body) {
  const b = String(body || '').trim();
  if (!b || b.length < 25) return true;
  if (/^~?\d+\s*(\.?|words?|palabras?)?$/i.test(b)) return true;
  if (/max\s*\d+\s*words|output only|do not invent|constraints|data provided|key data points|extract key|analyze user|draft:/i.test(b)) return true;
  if (/(?:^|\n)\s*[-*]\s*max\s*\d+\s*words/i.test(b)) return true;
  const first = b.split('\n')[0].trim();
  if (/^(total|need to|let's count|slightly over)/i.test(first)) return true;
  return false;
}

function puntuarBloqueIA(body) {
  const b = String(body || '').trim();
  let score = b.length;
  if (/^(?:[-*•]\s+|\d+[.)]\s+)/m.test(b)) score += 80;
  if (/\$[\d,.]+|[\d,.]+\s*%/.test(b)) score += 40;
  if (/constraints|data provided|key data points|max\s*\d+\s*words/i.test(b)) score -= 500;
  return score;
}

function consolidarBloquesIA(bloques) {
  const map = new Map();
  for (const b of bloques) {
    if (esCuerpoIAJunk(b.body)) continue;
    const canon = tituloIACanonico(b.title);
    const prev = map.get(canon);
    const score = puntuarBloqueIA(b.body);
    if (!prev || score > prev.score) map.set(canon, { title: canon, body: b.body, score });
  }
  const orden = [
    'Resumen', 'Panorama estratégico', 'Ejecución', 'Hallazgos', 'Oportunidades',
    'Alertas operativas', 'Riesgos', 'Recomendaciones', 'Acciones inmediatas', 'Decisiones recomendadas',
  ];
  const out = [];
  for (const k of orden) {
    if (map.has(k)) {
      const { title, body } = map.get(k);
      out.push({ title, body });
      map.delete(k);
    }
  }
  for (const { title, body } of map.values()) out.push({ title, body });
  return out;
}

function tituloIACanonico(title) {
  const t = String(title || '').trim().toLowerCase().normalize('NFD').replace(/\p{M}/gu, '');
  if (t === 'resumen' || t === 'resumen ejecutivo') return 'Resumen';
  if (t.startsWith('panorama')) return 'Panorama estratégico';
  if (t.startsWith('hallazgo')) return 'Hallazgos';
  if (t.startsWith('riesgo')) return 'Riesgos';
  if (t.startsWith('recomendacion')) return 'Recomendaciones';
  if (t.startsWith('oportunidad')) return 'Oportunidades';
  if (t.startsWith('alerta')) return 'Alertas operativas';
  if (t.startsWith('accion') || t.startsWith('acci')) return 'Acciones inmediatas';
  if (t.startsWith('decision')) return 'Decisiones recomendadas';
  if (t.startsWith('ejecucion')) return 'Ejecución';
  return String(title || '').trim().replace(/\*+/g, '');
}

function rolLayoutBloqueIA(title) {
  const t = tituloIACanonico(title).toLowerCase();
  if (t === 'resumen' || t.includes('panorama') || t.includes('ejecuci')) return 'lead';
  if (['hallazgos', 'riesgos', 'recomendaciones', 'oportunidades', 'alertas operativas', 'acciones inmediatas', 'decisiones recomendadas'].includes(t)) {
    return 'pillar';
  }
  return 'default';
}

function mdInlineRep(s) {
  let t = escRep(s);
  t = t.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
  t = t.replace(/(^|[^*\w])\*(?!\s)(.+?)(?!\s)\*(?!\*)/g, '$1<em>$2</em>');
  return t;
}

function mdBodyRep(texto) {
  const raw = String(texto || '').replace(/\r\n/g, '\n').trim();
  if (!raw) return '';
  const lines = raw.split('\n');
  const out = [];
  let i = 0;
  while (i < lines.length) {
    const trimmed = lines[i].trim();
    if (!trimmed) { i += 1; continue; }
    if (/^(-{3,}|\*{3,})$/.test(trimmed)) { out.push('<hr class="est-ia-hr">'); i += 1; continue; }
    if (trimmed.includes('|') && i + 1 < lines.length && /^\s*\|?[\s-:|]+\|?\s*$/.test(lines[i + 1])) {
      const rows = [];
      while (i < lines.length && lines[i].trim().includes('|')) {
        const cells = lines[i].trim().replace(/^\|/, '').replace(/\|$/, '').split('|').map((c) => c.trim());
        if (!/^[\s-:|]+$/.test(lines[i].trim())) rows.push(cells);
        i += 1;
        if (i < lines.length && !lines[i].trim().includes('|')) break;
      }
      if (rows.length) {
        out.push('<div class="est-ia-table-wrap"><table class="est-ia-table"><thead><tr>'
          + rows[0].map((c) => `<th>${mdInlineRep(c)}</th>`).join('')
          + '</tr></thead><tbody>'
          + rows.slice(1).map((r) => `<tr>${r.map((c) => `<td>${mdInlineRep(c)}</td>`).join('')}</tr>`).join('')
          + '</tbody></table></div>');
      }
      continue;
    }
    if (/^[-*•]\s+/.test(trimmed) || /^\d+[.)]\s+/.test(trimmed)) {
      const items = [];
      while (i < lines.length) {
        const t = lines[i].trim();
        if (!t) { i += 1; break; }
        const m = t.match(/^[-*•]\s+(.+)$/) || t.match(/^\d+[.)]\s+(.+)$/);
        if (!m) break;
        items.push(`<li>${mdInlineRep(m[1])}</li>`);
        i += 1;
      }
      out.push(`<ul class="est-ia-list">${items.join('')}</ul>`);
      continue;
    }
    const buf = [];
    while (i < lines.length) {
      const t = lines[i].trim();
      if (!t || /^#{1,4}\s/.test(t) || /^[-*•]\s+/.test(t) || /^\d+[.)]\s+/.test(t)
        || /^(-{3,}|\*{3,})$/.test(t) || t.includes('|')) break;
      buf.push(t.replace(/^#{1,4}\s+/, ''));
      i += 1;
    }
    if (buf.length) out.push(`<p>${mdInlineRep(buf.join(' '))}</p>`);
  }
  return out.join('\n');
}

/** Parsea el texto IA en bloques por títulos de sección. */
function parseIATexto(texto) {
  let raw = sanitizarTextoIA(texto);
  if (!raw) return [];
  raw = raw.replace(/^\s*\*\*[^*\n]+\*\*\s*\n?/, '').replace(/^\s*---+\s*\n?/, '');
  const keys = [
    'Resumen ejecutivo', 'Panorama estratégico', 'Panorama estrategico',
    'Oportunidades de mercado', 'Riesgos estratégicos', 'Riesgos estrategicos',
    'Alertas operativas', 'Acciones inmediatas', 'Decisiones recomendadas',
    'Resumen', 'Ejecución', 'Ejecucion', 'Hallazgos', 'Riesgos', 'Recomendaciones',
  ];
  const keyAlt = keys.map((k) => k.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')).join('|');
  const re = new RegExp(
    `(?:^|\\n)\\s{0,3}(?:#{1,4}\\s+)?(?:\\d+[.)]\\s*)?(?:\\*\\*)?(${keyAlt})(?:\\*\\*)?\\s*[:.]?\\s*`,
    'gi',
  );
  const matches = [];
  let match;
  while ((match = re.exec(raw)) !== null) {
    matches.push({ title: match[1], index: match.index, end: match.index + match[0].length });
  }
  if (!matches.length) {
    const reH = /(?:^|\n)\s{0,3}#{1,4}\s+(?:\d+[.)]\s*)?([^\n]+)/g;
    while ((match = reH.exec(raw)) !== null) {
      matches.push({ title: match[1].replace(/\*+/g, '').trim(), index: match.index, end: match.index + match[0].length });
    }
  }
  if (!matches.length) return [{ title: 'Análisis', body: raw }];
  const bloques = matches.map((m, i) => {
    const end = i + 1 < matches.length ? matches[i + 1].index : raw.length;
    return { title: m.title, body: raw.slice(m.end, end).trim() };
  }).filter((b) => b.body && !esCuerpoIAJunk(b.body));
  return consolidarBloquesIA(bloques.length ? bloques : [{ title: 'Análisis', body: raw }]);
}

function htmlBloqueIA(b, extraClass = '') {
  return `
    <div class="rep-ia-block est-ia-block ${extraClass}">
      <h4>${escRep(b.title)}</h4>
      <div class="est-ia-body">${mdBodyRep(b.body)}</div>
    </div>`;
}

function renderIAResumenCard(res) {
  const bloques = parseIATexto(res.texto);
  const nivelKey = res.nivel || 'tactico';
  const nivelLabel = res.nivel_label
    || { operativo: 'Operativo', tactico: 'Táctico', estrategico: 'Estratégico' }[nivelKey]
    || nivelKey;
  const kpis = (res.kpis && res.kpis.length) ? res.kpis : (reportesState.ultimoVista?.kpis || []);
  const leads = bloques.filter((b) => rolLayoutBloqueIA(b.title) === 'lead');
  const pillars = bloques.filter((b) => rolLayoutBloqueIA(b.title) === 'pillar');
  const otros = bloques.filter((b) => rolLayoutBloqueIA(b.title) === 'default');
  const fallback = bloques.length
    ? ''
    : `<div class="rep-ia-row rep-ia-row--lead">${htmlBloqueIA({ title: 'Informe', body: sanitizarTextoIA(res.texto) || 'Sin contenido útil.' }, 'rep-ia-block--lead')}</div>`;

  return `
    <div class="card rep-ia-card" style="grid-column:1/-1">
      <div class="rep-ia-head">
        <div>
          <div class="card-title" style="margin:0">Análisis con IA</div>
          <p class="meta" style="margin:.35rem 0 0">
            Enfoque ${escRep(nivelLabel || '')}
            · modelo ${escRep(res.modelo || '—')}
            ${res.tokens ? ` · ${escRep(res.tokens)} tokens` : ''}
          </p>
        </div>
        <span class="rep-ia-badge">${escRep(nivelLabel || 'IA')}</span>
      </div>
      ${kpis.length ? `
        <div class="rep-ia-kpis">
          <div class="kpi-grid rep-ia-kpi-grid">
            ${kpis.slice(0, 4).map((k) => `
              <div class="kpi-card compact">
                <div class="label">${escRep(k.label)}</div>
                <div class="value">${escRep(k.value)}</div>
              </div>`).join('')}
          </div>
        </div>` : ''}
      <div class="rep-ia-sections">
        ${fallback}
        ${leads.length ? `<div class="rep-ia-row rep-ia-row--lead">${leads.map((b) => htmlBloqueIA(b, 'rep-ia-block--lead')).join('')}</div>` : ''}
        ${pillars.length ? `<div class="rep-ia-row rep-ia-row--pillars">${pillars.map((b) => htmlBloqueIA(b, 'rep-ia-block--pillar')).join('')}</div>` : ''}
        ${otros.length ? `<div class="rep-ia-row rep-ia-row--rest">${otros.map((b) => htmlBloqueIA(b)).join('')}</div>` : ''}
      </div>
    </div>`;
}

async function generarReporteVista() {
  const nombre = reportesState.nombre || document.getElementById('rep-select')?.value;
  if (!nombre) { toast('Seleccione un informe.', 'error'); return; }
  if (!validateRepFechas()) return;
  reportesState.nombre = nombre;
  const q = leerFiltrosReporte();
  q.set('_t', Date.now());
  const boton = document.getElementById('rep-generar');
  const spinner = boton?.querySelector('.btn-spinner');
  const label = boton?.querySelector('.btn-label');
  if (spinner) spinner.hidden = false;
  if (label) label.textContent = 'Generando…';
  try {
    const datos = await api(`/reportes/vista/${encodeURIComponent(nombre)}?${q}`);
    renderReporteResultado(datos);
    const n = datos.tipo === 'compuesto' ? (datos.secciones || []).length : (datos.rows || []).length;
    toast(`Informe «${datos.titulo}» generado${datos.tipo === 'compuesto' ? ` (${n} módulos)` : ` (${n} registros)`}.`);
  } catch (e) {
    toast(e.message || 'No se pudo generar el informe.', 'error');
  } finally {
    if (spinner) spinner.hidden = true;
    if (label) label.textContent = 'Generar informe';
  }
}

async function generarResumenIA() {
  const nombre = reportesState.nombre || document.getElementById('rep-select')?.value;
  if (!nombre) { toast('Seleccione un informe para el análisis IA.', 'error'); return; }
  reportesState.nombre = nombre;
  const nivel = nivelIAParaReporte(nombre);
  const q = leerFiltrosReporte();
  q.set('_t', Date.now());
  q.set('nivel', nivel);
  const boton = document.getElementById('rep-ia');
  const spinner = boton?.querySelector('.btn-spinner');
  const label = boton?.querySelector('.btn-label');
  if (spinner) spinner.hidden = false;
  if (label) label.textContent = 'Analizando…';
  try {
    if (!reportesState.ultimoVista || reportesState.nombre !== nombre) {
      await generarReporteVista();
    }
    const res = await api(`/reportes/ia/${encodeURIComponent(nombre)}?${q}`);
    if (res.estado === 'sin_configurar') {
      toast(res.detalle || 'IA sin configurar.', 'error');
      return;
    }
    const slot = document.getElementById('rep-ia-slot') || document.getElementById('rep-resultado');
    if (!slot) return;
    if (slot.id === 'rep-ia-slot') {
      slot.innerHTML = renderIAResumenCard(res);
    } else {
      const wrap = document.createElement('div');
      wrap.innerHTML = renderIAResumenCard(res);
      slot.prepend(wrap.firstElementChild);
    }
    toast('Análisis IA generado.');
  } catch (e) {
    toast(e.message || 'No se pudo generar el análisis IA.', 'error');
  } finally {
    if (spinner) spinner.hidden = true;
    if (label) label.textContent = 'Resumen con IA';
  }
}

async function exportarReporteVista(formato) {
  const nombre = reportesState.nombre || document.getElementById('rep-select')?.value;
  if (!nombre) { toast('Seleccione un informe.', 'error'); return; }
  if (!validateRepFechas()) return;
  reportesState.nombre = nombre;
  const params = {};
  leerFiltrosReporte().forEach((v, k) => { if (v) params[k] = v; });
  try {
    if (typeof downloadReport === 'function') {
      await downloadReport(nombre, formato, params);
      return;
    }
    const q = leerFiltrosReporte();
    q.set('formato', formato);
    const res = await fetch(`${API}/reportes/${encodeURIComponent(nombre)}?${q}`);
    if (!res.ok) {
      const err = await res.json().catch(() => ({ message: res.statusText }));
      throw new Error(err?.detail || err?.message || 'Error al exportar');
    }
    const blob = await res.blob();
    const filename = `${nombre.replace('-', '_')}.${formato}`;
    if (String(formato).toLowerCase() === 'pdf') {
      if (typeof openPdfBlob === 'function') openPdfBlob(blob, filename);
      else window.open(URL.createObjectURL(new Blob([blob], { type: 'application/pdf' })), '_blank');
    } else {
      const a = document.createElement('a');
      a.href = URL.createObjectURL(blob);
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(a.href);
    }
    toast(String(formato).toLowerCase() === 'pdf' ? 'PDF abierto en nueva pestaña.' : `Exportado en ${formato.toUpperCase()}.`);
  } catch (e) {
    toast(e.message || 'No se pudo exportar.', 'error');
  }
}

function fmtFechaRep(iso) {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return escRep(iso);
  return d.toLocaleString('es-CL', { dateStyle: 'short', timeStyle: 'short' });
}

function fmtBytesRep(n) {
  if (n == null) return '—';
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / (1024 * 1024)).toFixed(2)} MB`;
}

async function descargarProgramado(id, archivo) {
  try {
    const res = await fetch(`${API}/reportes/programados/${id}/descargar`);
    if (!res.ok) {
      const err = await res.json().catch(() => ({ message: res.statusText }));
      throw new Error(err?.detail || err?.message || 'Error al descargar');
    }
    const blob = await res.blob();
    const archivoNombre = archivo || 'reporte.pdf';
    if (String(archivoNombre).toLowerCase().endsWith('.pdf') && typeof openPdfBlob === 'function') {
      openPdfBlob(blob, archivoNombre);
    } else {
      const a = document.createElement('a');
      a.href = URL.createObjectURL(blob);
      a.download = archivoNombre;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(a.href);
    }
  } catch (e) {
    toast(e.message || 'No se pudo descargar.', 'error');
  }
}

async function cargarReportesProgramados() {
  const cont = document.getElementById('rep-programados');
  if (!cont) return;
  cont.innerHTML = 'Cargando…';
  try {
    const res = await api('/reportes/programados');
    const lista = res.reportes || [];
    if (!lista.length) {
      cont.innerHTML = 'Aún no hay entregas. El DAG <code>etl_04_reportes_dag</code> corre cada noche a las 02:30.';
      return;
    }
    const filas = lista.slice(0, 50).map((r) => `
      <tr>
        <td>${fmtFechaRep(r.fecha)}</td>
        <td class="mono">${escRep(r.archivo)}</td>
        <td class="num center">${r.formato.toUpperCase()}</td>
        <td>${escRep(r.estado)}${r.estado !== 'ok' ? ` <span class="meta">${escRep(r.detalle)}</span>` : ''}</td>
        <td class="num">${r.duracion_ms != null ? `${r.duracion_ms} ms` : '—'}</td>
        <td class="num">${fmtBytesRep(r.bytes)}</td>
        <td class="col-actions center">
          ${r.estado === 'ok' ? `<button type="button" class="btn btn-primary btn-sm" data-prog-id="${r.id}" data-prog-archivo="${escRep(r.archivo)}">Descargar</button>` : '—'}
        </td>
      </tr>`).join('');
    cont.innerHTML = `<div class="table-wrap" style="max-height:320px;overflow:auto">
      <table><thead><tr>
        <th>Fecha</th><th>Archivo</th><th>Formato</th><th>Estado</th><th class="num">Duración</th><th class="num">Tamaño</th><th class="col-actions center">Acción</th>
      </tr></thead><tbody>${filas}</tbody></table></div>`;
    cont.querySelectorAll('[data-prog-id]').forEach((b) => {
      b.addEventListener('click', () => descargarProgramado(b.dataset.progId, b.dataset.progArchivo));
    });
  } catch (e) {
    cont.innerHTML = `No se pudo cargar: ${escRep(e.message)}`;
  }
}

function actualizarSeleccionReporte() {
  const sel = document.getElementById('rep-select');
  const nombre = sel ? sel.value : reportesState.nombre;
  reportesState.nombre = nombre || null;
  const r = (reportesState.catalogo || []).find((x) => x.id === nombre);
  const desc = document.getElementById('rep-desc');
  if (desc) {
    if (!r) {
      desc.textContent = 'Seleccione un informe de la lista.';
    } else {
      const tipo = r.tipo === 'compuesto'
        ? 'informe compuesto (varios módulos + gráficos)'
        : 'informe simple (tabla + gráfico)';
      const nivel = nivelIAParaReporte(r.id);
      const nivelTxt = { operativo: 'operativo', tactico: 'táctico', estrategico: 'estratégico' }[nivel];
      desc.textContent = `${r.descripcion} · ${tipo}. Resumen IA: enfoque ${nivelTxt}.`;
    }
  }
  const filasEl = document.getElementById('rep-filtros-row');
  if (filasEl) filasEl.innerHTML = r ? filtrosReporteHtml(r.filtros || []) : '';
  if (typeof capDateInputs === 'function') capDateInputs(document.getElementById('rep-trabajo'));
  document.querySelectorAll('.rep-pick').forEach((b) => {
    b.classList.toggle('active', b.dataset.id === nombre);
  });
}

function catalogoPorTipo(tipo) {
  const cat = reportesState.catalogo || [];
  if (tipo === 'compuesto') return cat.filter((r) => r.tipo === 'compuesto');
  return cat.filter((r) => r.tipo !== 'compuesto');
}

function htmlCatalogoPicks(tipo) {
  const items = catalogoPorTipo(tipo);
  if (!items.length) return '<p class="meta">No hay informes en esta categoría.</p>';
  return `<div class="rep-catalog-grid">${items.map((r) => `
    <button type="button" class="rep-pick${reportesState.nombre === r.id ? ' active' : ''}" data-id="${escRep(r.id)}">
      <strong>${escRep(r.titulo)}</strong>
      <span>${escRep((r.descripcion || '').slice(0, 110))}${(r.descripcion || '').length > 110 ? '…' : ''}</span>
      <em>${r.tipo === 'compuesto' ? 'Compuesto' : 'Simple'}</em>
    </button>`).join('')}</div>`;
}

function mostrarPanelReportes(panel) {
  reportesState.panel = panel;
  document.querySelectorAll('[data-rep-main]').forEach((b) => {
    b.classList.toggle('active', b.dataset.repMain === panel);
  });
  document.querySelectorAll('[data-rep-panel-main]').forEach((p) => {
    p.classList.toggle('hidden', p.dataset.repPanelMain !== panel);
  });
  const trabajo = document.getElementById('rep-trabajo');
  if (trabajo) trabajo.classList.toggle('hidden', panel === 'programados');
  if (panel === 'programados') cargarReportesProgramados();
}

function enlazarCatalogoPicks(root) {
  root.querySelectorAll('.rep-pick').forEach((btn) => {
    btn.addEventListener('click', () => {
      reportesState.nombre = btn.dataset.id;
      const sel = document.getElementById('rep-select');
      if (sel) {
        sel.value = btn.dataset.id;
        // sync hidden select for existing handlers
      }
      actualizarSeleccionReporte();
    });
  });
}

async function loadReportesPage() {
  const cont = document.getElementById('vista-reportes');
  if (!cont) return;

  if (!reportesState.catalogo) {
    try {
      const res = await api('/reportes/');
      reportesState.catalogo = res.reportes || [];
    } catch (e) {
      cont.innerHTML = `<div class="card"><p class="meta" style="color:var(--loss)">No se pudo cargar el catálogo: ${escRep(e.message)}</p></div>`;
      return;
    }
  }

  if (cont.dataset.loaded !== '1') cont.dataset.loaded = '1';

  const panel = reportesState.panel || 'simples';
  cont.innerHTML = `
    <div class="rep-shell">
      <div class="rep-main-tabs" role="tablist">
        <button type="button" class="rep-main-tab${panel === 'simples' ? ' active' : ''}" data-rep-main="simples">Informes simples</button>
        <button type="button" class="rep-main-tab${panel === 'compuestos' ? ' active' : ''}" data-rep-main="compuestos">Informes compuestos</button>
        <button type="button" class="rep-main-tab${panel === 'programados' ? ' active' : ''}" data-rep-main="programados">Entregas programadas</button>
      </div>

      <div class="rep-panel-main${panel === 'simples' ? '' : ' hidden'}" data-rep-panel-main="simples">
        <div class="card">
          <div class="card-title">Informes simples</div>
          <p class="meta">Una tabla con KPIs y gráfico cuando los datos lo permiten.</p>
          ${htmlCatalogoPicks('simple')}
        </div>
      </div>

      <div class="rep-panel-main${panel === 'compuestos' ? '' : ' hidden'}" data-rep-panel-main="compuestos">
        <div class="card">
          <div class="card-title">Informes compuestos</div>
          <p class="meta">Varios módulos (gráficos + tablas) en un solo documento ejecutivo.</p>
          ${htmlCatalogoPicks('compuesto')}
        </div>
      </div>

      <div class="rep-panel-main${panel === 'programados' ? '' : ' hidden'}" data-rep-panel-main="programados">
        <div class="card" style="grid-column:1/-1">
          <div class="card-title">Entregas del DAG nocturno
            <button type="button" class="btn btn-secondary btn-sm" id="rep-prog-refresh">Actualizar</button>
          </div>
          <p class="meta">Artefactos generados por <code>etl_04_reportes_dag</code> (02:30).</p>
          <div id="rep-programados" class="meta">Cargando…</div>
        </div>
      </div>

      <div id="rep-trabajo" class="${panel === 'programados' ? 'hidden' : ''}">
        <select id="rep-select" hidden>
          <option value="">—</option>
          ${(reportesState.catalogo || []).map((r) => `<option value="${escRep(r.id)}">${escRep(r.titulo)}</option>`).join('')}
        </select>
        <div class="filters rep-filtros">
          <div id="rep-filtros-row" style="display:contents"></div>
          <button type="button" class="btn btn-primary" id="rep-generar">
            <span class="btn-spinner loader" hidden aria-hidden="true"></span><span class="btn-label">Generar informe</span>
          </button>
          <button type="button" class="btn btn-secondary" id="rep-limpiar">Limpiar filtros</button>
          <button type="button" class="btn btn-secondary" id="rep-ia" title="El enfoque IA se elige automáticamente según el informe">
            <span class="btn-spinner loader" hidden aria-hidden="true"></span><span class="btn-label">Resumen con IA</span>
          </button>
          <button type="button" class="btn btn-secondary" id="rep-pdf">PDF</button>
          <button type="button" class="btn btn-secondary" id="rep-csv">CSV</button>
        </div>
        <div class="card">
          <div class="card-title">Informe seleccionado</div>
          <p class="meta" id="rep-desc">Seleccione un informe arriba.</p>
          <p class="meta" id="rep-tiempo"></p>
        </div>
        <div id="rep-resultado" class="rep-resultado-grid"></div>
      </div>
    </div>`;

  document.querySelectorAll('[data-rep-main]').forEach((btn) => {
    btn.addEventListener('click', () => mostrarPanelReportes(btn.dataset.repMain));
  });
  enlazarCatalogoPicks(cont);
  document.getElementById('rep-generar')?.addEventListener('click', generarReporteVista);
  document.getElementById('rep-limpiar')?.addEventListener('click', () => {
    document.querySelectorAll('#rep-trabajo .rep-filtros input, #rep-trabajo .rep-filtros select').forEach((el) => { el.value = ''; });
    if (typeof capDateInputs === 'function') capDateInputs(document.getElementById('rep-trabajo'));
    reportesState.ultimoVista = null;
    const res = document.getElementById('rep-resultado');
    if (res) res.innerHTML = '';
  });
  document.getElementById('rep-ia')?.addEventListener('click', generarResumenIA);
  document.getElementById('rep-pdf')?.addEventListener('click', () => exportarReporteVista('pdf'));
  document.getElementById('rep-csv')?.addEventListener('click', () => exportarReporteVista('csv'));
  document.getElementById('rep-prog-refresh')?.addEventListener('click', cargarReportesProgramados);

  const sel = document.getElementById('rep-select');
  if (sel && reportesState.nombre) sel.value = reportesState.nombre;
  actualizarSeleccionReporte();
  if (panel === 'programados') cargarReportesProgramados();
  else if (reportesState.nombre && reportesState.ultimoVista) {
    renderReporteResultado(reportesState.ultimoVista);
  }
  void ensureFilters().catch((e) => console.warn('Filtros maestros no disponibles:', e));
}

PAGES.reportes = { title: 'Centro de informes', load: loadReportesPage };
