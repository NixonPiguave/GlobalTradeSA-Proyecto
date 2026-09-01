/* global api, toast, PAGES, uiModal, uiConfirm, API, GTChart, openPdfBlob */
PAGES.estrategia = { title: 'Estrategia e IA', load: loadEstrategiaPage };

const estState = {
  nivel: 'estrategico',
  tab: 'vision',
  objetivos: [],
  expansion: null,
  proyeccion: null,
  riesgos: [],
  panel: null,
};

function escE(s) {
  return String(s == null ? '' : s).replace(/[&<>"']/g, (c) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
  }[c]));
}

const NIVEL_CLS = {
  critico: 'badge badge-danger',
  alto: 'badge badge-warning',
  medio: 'badge badge-info',
  bajo: 'badge badge-success',
};
const ESTADO_CLS = {
  cumplido: 'badge badge-success',
  en_curso: 'badge badge-info',
  en_riesgo: 'badge badge-danger',
};
const ESTADO_TXT = { cumplido: 'Cumplido', en_curso: 'En curso', en_riesgo: 'En riesgo' };
const METRICA_TXT = {
  ingresos: 'Ingresos (USD)', profit: 'Profit (USD)', margen_pct: 'Margen bruto (%)',
  unidades: 'Unidades vendidas', paises: 'Países atendidos', clientes: 'Clientes mayoristas',
};
const NIVEL_META = {
  estrategico: { label: 'Estratégico', hint: 'Horizonte 12–36 meses · inversión y expansión' },
  tactico: { label: 'Táctico', hint: 'Horizonte 90 días · prioridades del trimestre' },
  operativo: { label: 'Operativo', hint: 'Horizonte semanal · alertas y ejecución' },
};

function fmtMoneda(v) {
  return '$' + Number(v || 0).toLocaleString('es-PE', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}
function fmtE(v) {
  return Number(v || 0).toLocaleString('es-PE', { maximumFractionDigits: 2 });
}
function fmtValor(tipo, v) {
  return tipo === 'margen_pct' ? fmtE(v) + '%' : fmtE(v);
}

function cardObjetivo(o) {
  const pct = Math.min(100, Math.max(0, Number(o.avance_pct) || 0));
  const tono = o.estado === 'cumplido' ? 'ok' : o.estado === 'en_riesgo' ? 'risk' : 'run';
  return `
    <div class="card est-obj-card">
      <div class="card-title">${escE(o.nombre)}
        <span class="${ESTADO_CLS[o.estado] || 'badge'}">${ESTADO_TXT[o.estado] || o.estado}</span>
      </div>
      <p class="meta">${METRICA_TXT[o.tipo_metrica] || o.tipo_metrica} · meta ${fmtValor(o.tipo_metrica, o.meta_numerica)}${o.periodo ? ' · ' + escE(o.periodo) : ''}</p>
      <div class="est-progress" data-tone="${tono}">
        <div class="est-progress-ring" style="--p:${pct}"><span>${fmtE(pct)}%</span></div>
        <div class="est-progress-bars">
          <div class="prog"><div class="prog-fill tone-${tono}" style="width:${pct}%"></div></div>
          <p class="meta">Actual: <strong>${fmtValor(o.tipo_metrica, o.valor_actual)}</strong></p>
        </div>
      </div>
      ${o.descripcion ? `<p class="meta">${escE(o.descripcion)}</p>` : ''}
      <div class="est-card-actions">
        <button class="btn btn-secondary btn-sm" data-obj-edit="${o.id_objetivo}">Editar</button>
        <button class="btn btn-danger btn-sm" data-obj-del="${o.id_objetivo}">Eliminar</button>
      </div>
    </div>`;
}

function modalObjetivo(estado, obj) {
  const tipos = Object.entries(METRICA_TXT).map(([k, v]) => ({ value: k, label: v }));
  uiModal({
    modo: estado === 'crear' ? 'Agregar' : 'Actualizar',
    tituloExtra: estado === 'crear' ? 'objetivo estratégico' : 'objetivo',
    campos: [
      { key: 'nombre', label: 'Nombre del objetivo', value: obj?.nombre || '', required: true },
      { key: 'tipo_metrica', label: 'Métrica', type: 'select', value: obj?.tipo_metrica || 'ingresos', options: tipos },
      { key: 'meta_numerica', label: 'Meta numérica', type: 'number', step: 'any', value: obj?.meta_numerica ?? '', required: true },
      { key: 'descripcion', label: 'Descripción', type: 'textarea', value: obj?.descripcion || '' },
      { key: 'periodo', label: 'Período', value: obj?.periodo || '' },
      { key: 'orden', label: 'Orden', type: 'number', value: obj?.orden ?? 0 },
    ],
    onAceptar: async (values) => {
      const body = {
        nombre: values.nombre,
        tipo_metrica: values.tipo_metrica,
        meta_numerica: parseFloat(values.meta_numerica),
        descripcion: values.descripcion,
        periodo: values.periodo,
        orden: parseInt(values.orden, 10) || 0,
      };
      await api(estado === 'crear' ? '/estrategia/objetivos' : `/estrategia/objetivos/${obj.id_objetivo}`, {
        method: estado === 'crear' ? 'POST' : 'PUT',
        body,
      });
      toast(estado === 'crear' ? 'Objetivo creado.' : 'Objetivo actualizado.');
      await loadEstrategiaPage();
    },
  });
}

function modalRiesgo(estado, riesgo, objetivos) {
  const opts = [{ value: '', label: '— Sin vínculo —' }].concat(
    (objetivos || []).map((o) => ({ value: String(o.id_objetivo), label: o.nombre }))
  );
  uiModal({
    modo: estado === 'crear' ? 'Agregar' : 'Actualizar',
    tituloExtra: 'riesgo estratégico',
    campos: [
      { key: 'nombre', label: 'Nombre del riesgo', value: riesgo?.nombre || '', required: true },
      { key: 'probabilidad', label: 'Probabilidad (1-5)', type: 'number', min: 1, max: 5, value: riesgo?.probabilidad ?? 3 },
      { key: 'impacto', label: 'Impacto (1-5)', type: 'number', min: 1, max: 5, value: riesgo?.impacto ?? 3 },
      { key: 'descripcion', label: 'Descripción', type: 'textarea', value: riesgo?.descripcion || '' },
      { key: 'mitigacion', label: 'Mitigación', type: 'textarea', value: riesgo?.mitigacion || '' },
      { key: 'id_objetivo', label: 'Vinculado a objetivo', type: 'select', value: riesgo?.id_objetivo ? String(riesgo.id_objetivo) : '', options: opts },
    ],
    onAceptar: async (values) => {
      const body = {
        nombre: values.nombre,
        probabilidad: parseInt(values.probabilidad, 10),
        impacto: parseInt(values.impacto, 10),
        descripcion: values.descripcion,
        mitigacion: values.mitigacion,
        id_objetivo: values.id_objetivo || null,
      };
      await api(estado === 'crear' ? '/estrategia/riesgos' : `/estrategia/riesgos/${riesgo.id_riesgo}`, {
        method: estado === 'crear' ? 'POST' : 'PUT',
        body,
      });
      toast(estado === 'crear' ? 'Riesgo creado.' : 'Riesgo actualizado.');
      await loadEstrategiaPage();
    },
  });
}

/** Inline markdown → HTML (tras escapar). */
function mdInline(s) {
  let t = escE(s);
  t = t.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
  t = t.replace(/__(.+?)__/g, '<strong>$1</strong>');
  t = t.replace(/(^|[^*\w])\*(?!\s)(.+?)(?!\s)\*(?!\*)/g, '$1<em>$2</em>');
  t = t.replace(/`([^`]+)`/g, '<code>$1</code>');
  return t;
}

/** Markdown ligero → HTML (títulos, listas, tablas, hr, párrafos). */
function mdToHtml(texto) {
  const raw = String(texto || '').replace(/\r\n/g, '\n').trim();
  if (!raw) return '';
  const lines = raw.split('\n');
  const out = [];
  let i = 0;

  const flushParas = (buf) => {
    const t = buf.join(' ').trim();
    if (t) out.push(`<p>${mdInline(t)}</p>`);
    buf.length = 0;
  };

  while (i < lines.length) {
    const line = lines[i];
    const trimmed = line.trim();

    if (!trimmed) {
      i += 1;
      continue;
    }
    if (/^(-{3,}|\*{3,}|_{3,})$/.test(trimmed)) {
      out.push('<hr class="est-ia-hr">');
      i += 1;
      continue;
    }
    const h = trimmed.match(/^(#{1,4})\s+(.+)$/);
    if (h) {
      const lvl = Math.min(h[1].length + 2, 5);
      out.push(`<h${lvl} class="est-ia-h">${mdInline(h[2].replace(/^\d+[.)]\s*/, ''))}</h${lvl}>`);
      i += 1;
      continue;
    }
    // Tabla markdown
    if (trimmed.includes('|') && i + 1 < lines.length && /^\s*\|?[\s-:|]+\|?\s*$/.test(lines[i + 1])) {
      const rows = [];
      while (i < lines.length && lines[i].trim().includes('|')) {
        const cells = lines[i].trim().replace(/^\|/, '').replace(/\|$/, '').split('|').map((c) => c.trim());
        if (!/^[\s-:|]+$/.test(lines[i].trim())) rows.push(cells);
        i += 1;
        if (i < lines.length && !lines[i].trim().includes('|')) break;
      }
      if (rows.length) {
        const head = rows[0];
        const body = rows.slice(1);
        out.push('<div class="est-ia-table-wrap"><table class="est-ia-table"><thead><tr>'
          + head.map((c) => `<th>${mdInline(c)}</th>`).join('')
          + '</tr></thead><tbody>'
          + body.map((r) => `<tr>${r.map((c) => `<td>${mdInline(c)}</td>`).join('')}</tr>`).join('')
          + '</tbody></table></div>');
      }
      continue;
    }
    // Lista
    if (/^[-*•]\s+/.test(trimmed) || /^\d+[.)]\s+/.test(trimmed)) {
      const ordered = /^\d+[.)]\s+/.test(trimmed);
      const items = [];
      while (i < lines.length) {
        const t = lines[i].trim();
        if (!t) { i += 1; break; }
        const m = t.match(/^[-*•]\s+(.+)$/) || t.match(/^\d+[.)]\s+(.+)$/);
        if (!m) break;
        items.push(`<li>${mdInline(m[1])}</li>`);
        i += 1;
      }
      out.push(ordered ? `<ol class="est-ia-list">${items.join('')}</ol>` : `<ul class="est-ia-list">${items.join('')}</ul>`);
      continue;
    }
    // Párrafo (agrupa líneas consecutivas)
    const buf = [];
    while (i < lines.length) {
      const t = lines[i].trim();
      if (!t || /^#{1,4}\s/.test(t) || /^[-*•]\s+/.test(t) || /^\d+[.)]\s+/.test(t)
        || /^(-{3,}|\*{3,})$/.test(t) || t.includes('|')) break;
      buf.push(t);
      i += 1;
    }
    flushParas(buf);
  }
  return out.join('\n');
}

/** Limpia portada markdown y parte en secciones. */
function parseEstIATexto(texto) {
  let raw = String(texto || '').replace(/\r\n/g, '\n').trim();
  if (!raw) return [];

  // Quitar thinking / razonamiento interno
  raw = raw.replace(/<(think|thinking|reasoning|redacted_thinking|reflection)\b[^>]*>[\s\S]*?<\/\1>/gi, '');
  raw = raw.replace(/<\/?think\b[^>]*>/gi, '');
  if (/analyze user input|role:\s*|do not invent|extract key data/i.test(raw)) {
    const parts = raw.split(/(?=\n#{1,4}\s|\n\*\*[A-ZÁÉÍÓÚ])/);
    const useful = parts.filter((p) =>
      /resumen|panorama|cuadro|oportunidad|proyec|riesgo|decisi|priorid|mercado|alerta|acci[oó]n|estado operativo/i.test(p));
    if (useful.length) raw = useful.join('\n');
  }

  // Quitar título / fecha de portada
  raw = raw
    .replace(/^\s*\*\*[^*\n]+\*\*\s*\n?/, '')
    .replace(/^\s*\*[^*\n]+\*\s*\n?/, '')
    .replace(/^\s*---+\s*\n?/, '');

  const keys = [
    'Resumen ejecutivo', 'Resumen', 'Cuadro de mando', 'Oportunidades de mercado',
    'Proyección', 'Riesgos estratégicos', 'Riesgos estrategicos', 'Riesgos a vigilar', 'Riesgos',
    'Decisiones recomendadas', 'Panorama del período', 'Panorama del periodo',
    'Prioridades del trimestre', 'Mercados a impulsar', 'Plan de 90 días', 'Plan de 90 dias',
    'Estado operativo', 'Alertas', 'Desempeño por mercado', 'Desempeño por mercado/categoría',
    'Desempeno por mercado', 'Acciones de la semana', 'Análisis', 'Analisis',
  ];
  const keyAlt = keys.map((k) => k.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')).join('|');

  const re = new RegExp(
    `(?:^|\\n)\\s{0,3}(?:#{1,4}\\s+)?(?:\\d+[.)]\\s*)?(?:\\*\\*)?(${keyAlt})(?:\\*\\*)?\\s*[:.]?\\s*`,
    'gi',
  );
  const matches = [];
  let match;
  while ((match = re.exec(raw)) !== null) {
    matches.push({
      title: match[1].replace(/\s+/g, ' ').trim(),
      index: match.index,
      end: match.index + match[0].length,
    });
  }

  if (!matches.length) {
    const reH = /(?:^|\n)\s{0,3}#{1,4}\s+(?:\d+[.)]\s*)?([^\n]+)/g;
    while ((match = reH.exec(raw)) !== null) {
      matches.push({
        title: match[1].replace(/\*+/g, '').trim(),
        index: match.index,
        end: match.index + match[0].length,
      });
    }
  }

  if (!matches.length) return [{ title: 'Informe', body: raw }];

  const blocks = matches.map((m, idx) => {
    const end = idx + 1 < matches.length ? matches[idx + 1].index : raw.length;
    return { title: m.title, body: raw.slice(m.end, end).trim() };
  }).filter((b) => b.body && !/analyze user input|role:\s*|extract key data|max\s*\d+\s*words/i.test(b.body));

  const preface = raw.slice(0, matches[0].index).trim();
  if (preface && !/^[-*#|\s]+$/.test(preface) && !/analyze user input|role:\s*|extract key data/i.test(preface)) {
    blocks.unshift({ title: 'Contexto', body: preface });
  }
  return blocks.length ? blocks : [{ title: 'Informe', body: raw }];
}

function renderEstIACard(res) {
  const bloques = parseEstIATexto(res.texto);
  const nivelKey = res.nivel || estState.nivel;
  const nivelLabel = res.nivel_label || NIVEL_META[nivelKey]?.label || nivelKey;
  const kpis = res.kpis || [];
  return `
    <div class="card rep-ia-card est-ia-card">
      <div class="rep-ia-head">
        <div>
          <div class="card-title" style="margin:0">Informe con IA</div>
          <p class="meta" style="margin:.35rem 0 0">
            Enfoque ${escE(nivelLabel)}
            · modelo ${escE(res.modelo || '—')}
            ${res.tokens ? ` · ${escE(res.tokens)} tokens` : ''}
          </p>
        </div>
        <span class="rep-ia-badge">${escE(nivelLabel)}</span>
      </div>
      ${kpis.length ? `
        <div class="rep-ia-kpis">
          <div class="kpi-grid est-ia-kpis">
            ${kpis.slice(0, 4).map((k) => `
              <div class="kpi-card compact">
                <div class="label">${escE(k.label)}</div>
                <div class="value">${typeof k.value === 'number' && /ingreso/i.test(k.label)
                  ? fmtMoneda(k.value)
                  : escE(k.value)}</div>
              </div>`).join('')}
          </div>
        </div>` : ''}
      <div class="rep-ia-grid est-ia-grid">
        ${bloques.map((b) => `
          <div class="rep-ia-block est-ia-block">
            <h4>${escE(b.title)}</h4>
            <div class="est-ia-body">${mdToHtml(b.body)}</div>
          </div>`).join('')}
      </div>
    </div>`;
}

function opcionesPorNivel() {
  const { objetivos, expansion, proyeccion, riesgos } = estState;
  const enRiesgo = (objetivos || []).filter((o) => o.estado === 'en_riesgo');
  const criticos = (riesgos || []).filter((r) => r.nivel === 'critico' || r.nivel === 'alto');
  const top = (expansion?.recomendados || [])[0];
  const conc = (expansion?.concentracion_paises || [])[0];

  if (estState.nivel === 'operativo') {
    return [
      {
        tono: 'risk',
        titulo: 'Alertas activas',
        texto: criticos.length
          ? `${criticos.length} riesgo(s) alto/crítico requieren seguimiento esta semana.`
          : 'Sin riesgos altos. Revisar objetivos en curso.',
        cta: 'Ver riesgos', tab: 'riesgos',
      },
      {
        tono: enRiesgo.length ? 'risk' : 'ok',
        titulo: 'OKR en riesgo',
        texto: enRiesgo.length
          ? enRiesgo.slice(0, 2).map((o) => o.nombre).join(' · ')
          : 'Ningún objetivo en riesgo este período.',
        cta: 'Cuadro de mando', tab: 'okr',
      },
      {
        tono: 'run',
        titulo: 'Acción de la semana',
        texto: top
          ? `Priorizar pipeline comercial en ${top.pais} (score ${fmtE(top.score)}).`
          : 'Validar backlog de oportunidades de mercado.',
        cta: 'Expansión', tab: 'expansion',
      },
    ];
  }

  if (estState.nivel === 'tactico') {
    return [
      {
        tono: 'run',
        titulo: 'Foco del trimestre',
        texto: top
          ? `Impulsar ${top.pais}: margen ${fmtE(top.margen_pct)}% · ${escE(top.razon || '')}`
          : 'Definir 3 mercados prioritarios del trimestre.',
        cta: 'Ver mercados', tab: 'expansion',
      },
      {
        tono: 'ok',
        titulo: 'Trayectoria de ingresos',
        texto: `Proyección anual ${fmtMoneda(proyeccion?.ingresos_proyectados_anio)} (${fmtE(proyeccion?.crecimiento_anual_pct)}% vs último año).`,
        cta: 'Proyección', tab: 'proyeccion',
      },
      {
        tono: criticos.length ? 'risk' : 'run',
        titulo: 'Mitigaciones 90 días',
        texto: criticos.length
          ? `Atacar: ${criticos.slice(0, 2).map((r) => r.nombre).join(' · ')}`
          : 'Mantener monitoreo de riesgos medios y actualizar mitigaciones.',
        cta: 'Matriz', tab: 'riesgos',
      },
    ];
  }

  return [
    {
      tono: 'ok',
      titulo: 'Expansión de mercado',
      texto: top
        ? `Mercado recomendado: ${top.pais} (score ${fmtE(top.score)}). ${escE(top.razon || '')}`
        : 'Analizar nuevos mercados con score de expansión.',
      cta: 'Explorar', tab: 'expansion',
    },
    {
      tono: conc && conc.participacion_pct > 35 ? 'risk' : 'run',
      titulo: 'Diversificación',
      texto: conc
        ? `Concentración: ${conc.pais} aporta ${fmtE(conc.participacion_pct)}% de ingresos.`
        : 'Revisar concentración geográfica del portafolio.',
      cta: 'Ver detalle', tab: 'expansion',
    },
    {
      tono: 'run',
      titulo: 'Inversión / portafolio',
      texto: `Crecimiento proyectado ${fmtE(proyeccion?.crecimiento_anual_pct)}% · ${objetivos.filter((o) => o.estado === 'cumplido').length}/${objetivos.length} OKR cumplidos.`,
      cta: 'OKR', tab: 'okr',
    },
  ];
}

function htmlOpciones() {
  return `
    <div class="est-opciones">
      ${opcionesPorNivel().map((o) => `
        <button type="button" class="est-opcion" data-tone="${o.tono}" data-goto="${o.tab}">
          <span class="est-opcion-label">${escE(o.titulo)}</span>
          <span class="est-opcion-text">${escE(o.texto)}</span>
          <span class="est-opcion-cta">${escE(o.cta)} →</span>
        </button>`).join('')}
    </div>`;
}

function htmlTabsModulo() {
  const tabs = [
    { id: 'vision', label: 'Visión' },
    { id: 'okr', label: 'Cuadro de mando' },
    { id: 'expansion', label: 'Expansión' },
    { id: 'proyeccion', label: 'Proyección' },
    { id: 'riesgos', label: 'Riesgos' },
    { id: 'ia', label: 'Informe IA' },
  ];
  return `
    <div class="est-tabs" role="tablist">
      ${tabs.map((t) => `
        <button type="button" class="est-tab${estState.tab === t.id ? ' active' : ''}" data-est-tab="${t.id}">${t.label}</button>
      `).join('')}
    </div>`;
}

function panelVision() {
  const motor = estState.panel?.motor || 'DuckDB';
  const chOk = !!estState.panel?.clickhouse?.disponible;
  return `
    <div class="est-panel" data-panel="vision">
      ${htmlOpciones()}
      <div class="est-charts-grid">
        <div class="card chart-panel">
          <div class="card-title">Ingresos real vs proyectado</div>
          <div class="chart-wrap tall"><canvas id="est-chart-proy"></canvas></div>
        </div>
        <div class="card chart-panel">
          <div class="card-title">Ventas por país
            <span class="badge ${chOk ? 'badge-success' : 'badge-info'}">${escE(motor)}</span>
          </div>
          <div class="chart-wrap"><canvas id="est-chart-pais"></canvas></div>
        </div>
        <div class="card chart-panel">
          <div class="card-title">Mix por línea de producto</div>
          <div class="chart-wrap"><canvas id="est-chart-linea"></canvas></div>
        </div>
        <div class="card chart-panel">
          <div class="card-title">Matriz de riesgos (prob. × impacto)</div>
          <div class="chart-wrap"><canvas id="est-chart-riesgo"></canvas></div>
        </div>
      </div>
    </div>`;
}

function panelOkr() {
  const objs = estState.objetivos || [];
  return `
    <div class="est-panel" data-panel="okr">
      <div class="card" style="grid-column:1/-1">
        <div class="card-title">Cuadro de mando — objetivos estratégicos
          <button type="button" class="btn btn-primary btn-sm" id="est-obj-add">+ Nuevo objetivo</button>
        </div>
        <div class="est-okr-grid" id="est-objetivos">
          ${objs.length ? objs.map(cardObjetivo).join('') : '<p class="meta">Sin objetivos. Crea el primero.</p>'}
        </div>
        <div class="card chart-panel" style="margin-top:1rem">
          <div class="card-title">Avance OKR</div>
          <div class="chart-wrap"><canvas id="est-chart-okr"></canvas></div>
        </div>
      </div>
    </div>`;
}

function panelExpansion() {
  const ex = estState.expansion || {};
  const recs = ex.recomendados || [];
  return `
    <div class="est-panel" data-panel="expansion">
      <div class="est-charts-grid">
        <div class="card chart-panel">
          <div class="card-title">Concentración por país</div>
          <div class="chart-wrap"><canvas id="est-chart-conc-pais"></canvas></div>
        </div>
        <div class="card chart-panel">
          <div class="card-title">Concentración por categoría</div>
          <div class="chart-wrap"><canvas id="est-chart-conc-cat"></canvas></div>
        </div>
      </div>
      <div class="card" style="margin-top:1rem">
        <div class="card-title">Mercados recomendados
          <span class="meta">${fmtE(ex.total_paises)} países · crecimiento ${fmtE(ex.crecimiento_global_pct)}%</span>
        </div>
        <div class="est-rec-grid">
          ${recs.map((r, i) => `
            <div class="est-rec-card" data-rank="${i + 1}">
              <div class="est-rec-rank">#${i + 1}</div>
              <div>
                <strong>${escE(r.pais)}</strong>
                <p class="meta">Score ${fmtE(r.score)} · margen ${fmtE(r.margen_pct)}%</p>
                <p class="meta">${escE(r.razon || '')}</p>
              </div>
            </div>`).join('') || '<p class="meta">Sin recomendaciones.</p>'}
        </div>
      </div>
    </div>`;
}

function panelProyeccion() {
  const p = estState.proyeccion || { serie: [] };
  return `
    <div class="est-panel" data-panel="proyeccion">
      <div class="card chart-panel">
        <div class="card-title">Proyección de ventas (12 meses)
          <button type="button" class="btn btn-secondary btn-sm" id="est-pdf">PDF proyección</button>
        </div>
        <div class="chart-wrap tall"><canvas id="est-chart-proy-full"></canvas></div>
        <p class="meta">Pendiente mensual ${fmtMoneda(p.pendiente_mensual)} · ventana ${fmtE(p.ventana_meses)} meses${p.tramo_desde ? ` · tramo ${escE(p.tramo_desde)} → ${escE(p.tramo_hasta)}` : ''}</p>
        ${p._error ? `<p class="meta" style="color:var(--loss)">${escE(p._error)}</p>` : ''}
      </div>
      <div class="card" style="margin-top:1rem">
        <table class="table-erp">
          <thead><tr><th>Mes</th><th>Tipo</th><th style="text-align:right">Ingresos (USD)</th></tr></thead>
          <tbody>${(p.serie || []).map((s) => `
            <tr>
              <td>${escE(s.mes)}</td>
              <td><span class="${s.tipo === 'proyectado' ? 'badge badge-info' : 'badge'}">${s.tipo === 'proyectado' ? 'Proyectado' : 'Real'}</span></td>
              <td style="text-align:right">${fmtMoneda(s.ingresos)}</td>
            </tr>`).join('')}</tbody>
        </table>
      </div>
    </div>`;
}

function panelRiesgos() {
  const riesgos = estState.riesgos || [];
  return `
    <div class="est-panel" data-panel="riesgos">
      <div class="est-charts-grid">
        <div class="card chart-panel">
          <div class="card-title">Mapa de calor (prob. × impacto)</div>
          <div class="chart-wrap"><canvas id="est-chart-riesgo-full"></canvas></div>
        </div>
        <div class="card">
          <div class="card-title">Resumen por nivel</div>
          <div id="est-riesgo-resumen" class="est-riesgo-resumen"></div>
        </div>
      </div>
      <div class="card" style="margin-top:1rem">
        <div class="card-title">Matriz de riesgos
          <button type="button" class="btn btn-primary btn-sm" id="est-rg-add">+ Nuevo riesgo</button>
        </div>
        <table class="table-erp">
          <thead><tr><th>Riesgo</th><th>Prob.</th><th>Impacto</th><th>Nivel</th><th>Mitigación</th><th>Objetivo</th><th></th></tr></thead>
          <tbody>${riesgos.map((r) => `
            <tr>
              <td><strong>${escE(r.nombre)}</strong><div class="meta">${escE(r.descripcion || '')}</div></td>
              <td>${r.probabilidad}/5</td><td>${r.impacto}/5</td>
              <td><span class="${NIVEL_CLS[r.nivel] || 'badge'}">${String(r.nivel || '').toUpperCase()}</span></td>
              <td class="meta">${escE(r.mitigacion || '—')}</td>
              <td class="meta">${escE(r.objetivo_nombre || '—')}</td>
              <td>
                <button class="btn btn-secondary btn-sm" data-rg-edit="${r.id_riesgo}">Editar</button>
                <button class="btn btn-danger btn-sm" data-rg-del="${r.id_riesgo}">Eliminar</button>
              </td>
            </tr>`).join('') || '<tr><td colspan="7" class="meta">Sin riesgos registrados.</td></tr>'}
          </tbody>
        </table>
      </div>
    </div>`;
}

function panelIA() {
  const meta = NIVEL_META[estState.nivel];
  return `
    <div class="est-panel" data-panel="ia">
      <div class="card est-ia-toolbar">
        <div>
          <div class="card-title" style="margin:0">Informe integral con IA</div>
          <p class="meta">${escE(meta.hint)}</p>
        </div>
        <button type="button" class="btn btn-primary" id="est-ia">
          <span class="btn-label">Generar informe ${escE(meta.label)}</span>
        </button>
      </div>
      <div id="est-ia-resultado"></div>
    </div>`;
}

function renderShell() {
  const cont = document.getElementById('vista-estrategia');
  if (!cont) return;
  const { objetivos, expansion, proyeccion } = estState;
  const meta = NIVEL_META[estState.nivel];
  const motor = estState.panel?.motor || '—';

  const panels = {
    vision: panelVision,
    okr: panelOkr,
    expansion: panelExpansion,
    proyeccion: panelProyeccion,
    riesgos: panelRiesgos,
    ia: panelIA,
  };

  cont.innerHTML = `
    <div class="est-shell">
      <div class="est-nivel-bar">
        ${Object.entries(NIVEL_META).map(([k, v]) => `
          <button type="button" class="est-nivel${estState.nivel === k ? ' active' : ''}" data-nivel="${k}">
            <strong>${v.label}</strong>
            <span>${v.hint.split('·')[0].trim()}</span>
          </button>`).join('')}
        <span class="est-motor-pill" title="Fuente analítica">Motor: ${escE(motor)}</span>
      </div>
      <p class="meta est-nivel-hint">${escE(meta.hint)}</p>

      <div class="filters est-kpis">
        <div class="kpi-card"><div class="label">Ingresos</div><div class="value">${fmtMoneda(proyeccion?.ingresos_ultimo_anio)}</div><div class="kpi-hint">Últimos 12 meses</div></div>
        <div class="kpi-card"><div class="label">Proyección 12 meses</div><div class="value">${fmtMoneda(proyeccion?.ingresos_proyectados_anio)}</div><div class="kpi-hint">Regresión · ${fmtE(proyeccion?.crecimiento_anual_pct)}% anual</div></div>
        <div class="kpi-card"><div class="label">Mercados</div><div class="value">${fmtE(expansion?.total_paises)}</div><div class="kpi-hint">Países · ${fmtE(expansion?.crecimiento_global_pct)}% trimestre</div></div>
        <div class="kpi-card"><div class="label">OKR</div><div class="value">${objetivos.filter((o) => o.estado === 'cumplido').length}/${objetivos.length}</div><div class="kpi-hint">Cumplidos</div></div>
      </div>

      ${htmlTabsModulo()}
      <div id="est-tab-body">${(panels[estState.tab] || panelVision)()}</div>
    </div>`;

  bindShellEvents();
  requestAnimationFrame(() => paintChartsForTab(estState.tab));
}

function bindShellEvents() {
  document.querySelectorAll('[data-nivel]').forEach((btn) => {
    btn.addEventListener('click', () => {
      estState.nivel = btn.dataset.nivel;
      if (estState.tab === 'vision' || estState.tab === 'ia') renderShell();
      else {
        document.querySelectorAll('[data-nivel]').forEach((b) => b.classList.toggle('active', b.dataset.nivel === estState.nivel));
        const hint = document.querySelector('.est-nivel-hint');
        if (hint) hint.textContent = NIVEL_META[estState.nivel].hint;
        const visionOpts = document.querySelector('.est-opciones');
        if (visionOpts) visionOpts.outerHTML = htmlOpciones();
        document.querySelectorAll('[data-goto]').forEach((b) => {
          b.addEventListener('click', () => { estState.tab = b.dataset.goto; renderShell(); });
        });
      }
    });
  });

  document.querySelectorAll('[data-est-tab]').forEach((btn) => {
    btn.addEventListener('click', () => {
      estState.tab = btn.dataset.estTab;
      renderShell();
    });
  });

  document.querySelectorAll('[data-goto]').forEach((btn) => {
    btn.addEventListener('click', () => {
      estState.tab = btn.dataset.goto;
      renderShell();
    });
  });

  document.getElementById('est-obj-add')?.addEventListener('click', () => modalObjetivo('crear', null));
  document.querySelectorAll('[data-obj-edit]').forEach((b) => b.addEventListener('click', () => {
    modalObjetivo('editar', estState.objetivos.find((o) => o.id_objetivo === parseInt(b.dataset.objEdit, 10)));
  }));
  document.querySelectorAll('[data-obj-del]').forEach((b) => b.addEventListener('click', () => {
    const id = parseInt(b.dataset.objDel, 10);
    uiConfirm({
      mensaje: '¿Eliminar este objetivo estratégico?',
      onConfirm: async () => {
        await api(`/estrategia/objetivos/${id}`, { method: 'DELETE' });
        toast('Objetivo eliminado.');
        await loadEstrategiaPage();
      },
    });
  }));

  document.getElementById('est-rg-add')?.addEventListener('click', () => modalRiesgo('crear', null, estState.objetivos));
  document.querySelectorAll('[data-rg-edit]').forEach((b) => b.addEventListener('click', () => {
    modalRiesgo('editar', estState.riesgos.find((r) => r.id_riesgo === parseInt(b.dataset.rgEdit, 10)), estState.objetivos);
  }));
  document.querySelectorAll('[data-rg-del]').forEach((b) => b.addEventListener('click', () => {
    const id = parseInt(b.dataset.rgDel, 10);
    uiConfirm({
      mensaje: '¿Eliminar este riesgo estratégico?',
      onConfirm: async () => {
        await api(`/estrategia/riesgos/${id}`, { method: 'DELETE' });
        toast('Riesgo eliminado.');
        await loadEstrategiaPage();
      },
    });
  }));

  document.getElementById('est-pdf')?.addEventListener('click', async () => {
    try {
      const token = localStorage.getItem('globtrade-admin-token');
      const headers = token ? { Authorization: `Bearer ${token}` } : {};
      const res = await fetch(`${API}/estrategia/proyeccion?meses=12&formato=pdf&_t=${Date.now()}`, { headers });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || 'No se pudo generar el PDF');
      }
      const blob = await res.blob();
      if (typeof openPdfBlob === 'function') openPdfBlob(blob, 'proyeccion_ventas.pdf');
      else window.open(URL.createObjectURL(new Blob([blob], { type: 'application/pdf' })), '_blank');
      toast('PDF de proyección abierto.');
    } catch (e) {
      toast(e.message || 'No se pudo descargar el PDF.', 'error');
    }
  });

  document.getElementById('est-ia')?.addEventListener('click', async (ev) => {
    const boton = ev.currentTarget;
    const label = boton.querySelector('.btn-label') || boton;
    boton.disabled = true;
    label.textContent = 'Generando…';
    const slot = document.getElementById('est-ia-resultado');
    if (slot) slot.innerHTML = '<p class="meta">Analizando el sistema estratégico…</p>';
    try {
      const res = await api(`/estrategia/informe-ia?nivel=${encodeURIComponent(estState.nivel)}&_t=${Date.now()}`);
      if (res.estado === 'sin_configurar') {
        toast(res.detalle || 'IA sin configurar.', 'error');
        if (slot) slot.innerHTML = `<p class="meta" style="color:var(--loss)">${escE(res.detalle || 'IA sin configurar')}</p>`;
        return;
      }
      if (slot) slot.innerHTML = renderEstIACard(res);
      toast(`Informe ${NIVEL_META[estState.nivel].label} generado.`);
    } catch (e) {
      toast(e.message || 'No se pudo generar el informe.', 'error');
      if (slot) slot.innerHTML = `<p class="meta" style="color:var(--loss)">${escE(e.message || 'Error')}</p>`;
    } finally {
      boton.disabled = false;
      label.textContent = `Generar informe ${NIVEL_META[estState.nivel].label}`;
    }
  });
}

function paintProyeccionChart(canvasId) {
  if (typeof GTChart === 'undefined') return;
  const serie = estState.proyeccion?.serie || [];
  if (!serie.length) return;
  const labels = serie.map((s) => s.mes);
  const real = serie.map((s) => (s.tipo === 'real' ? s.ingresos : null));
  const proy = serie.map((s) => (s.tipo === 'proyectado' ? s.ingresos : null));
  // Continuidad visual: último real también en proyectado como ancla
  const lastRealIdx = real.map((v, i) => (v != null ? i : -1)).filter((i) => i >= 0).pop();
  if (lastRealIdx != null && lastRealIdx >= 0) proy[lastRealIdx] = real[lastRealIdx];
  GTChart.renderDualLine(canvasId, labels, real, proy, { labelA: 'Real', labelB: 'Proyectado' });
}

function paintRiesgoScatter(canvasId) {
  if (typeof GTChart === 'undefined') return;
  const pts = (estState.riesgos || []).map((r) => ({
    x: Number(r.probabilidad) || 0,
    y: Number(r.impacto) || 0,
  }));
  if (!pts.length) return;
  GTChart.renderScatter(canvasId, pts);
}

function paintChartsForTab(tab) {
  if (typeof GTChart === 'undefined') return;
  const panel = estState.panel || {};
  const paises = panel.ventas_por_pais || [];
  const lineas = panel.ventas_por_linea || [];
  const concP = estState.expansion?.concentracion_paises || [];
  const concC = estState.expansion?.concentracion_productos || [];

  if (tab === 'vision') {
    paintProyeccionChart('est-chart-proy');
    if (paises.length) {
      GTChart.renderSmart(
        'est-chart-pais',
        paises.map((p) => p.country || p.pais),
        paises.map((p) => p.total_revenue || p.ingresos || 0),
        { horizontal: true },
      );
    }
    if (lineas.length) {
      GTChart.renderSmart(
        'est-chart-linea',
        lineas.map((l) => l.linea || l.tipo),
        lineas.map((l) => l.total_revenue || l.ingresos || 0),
        { prefer: lineas.length <= 6 ? 'donut' : 'bar' },
      );
    }
    paintRiesgoScatter('est-chart-riesgo');
  }

  if (tab === 'okr') {
    const objs = estState.objetivos || [];
    if (objs.length) {
      GTChart.renderBar(
        'est-chart-okr',
        objs.map((o) => String(o.nombre).slice(0, 22)),
        objs.map((o) => Number(o.avance_pct) || 0),
        { horizontal: true },
      );
    }
  }

  if (tab === 'expansion') {
    if (concP.length) {
      GTChart.renderDonut(
        'est-chart-conc-pais',
        concP.map((p) => p.pais),
        concP.map((p) => p.participacion_pct || p.ingresos || 0),
      );
    }
    if (concC.length) {
      GTChart.renderDonut(
        'est-chart-conc-cat',
        concC.map((p) => p.tipo || p.categoria),
        concC.map((p) => p.participacion_pct || p.ingresos || 0),
      );
    }
  }

  if (tab === 'proyeccion') paintProyeccionChart('est-chart-proy-full');

  if (tab === 'riesgos') {
    paintRiesgoScatter('est-chart-riesgo-full');
    const box = document.getElementById('est-riesgo-resumen');
    if (box) {
      const counts = { critico: 0, alto: 0, medio: 0, bajo: 0 };
      (estState.riesgos || []).forEach((r) => { counts[r.nivel] = (counts[r.nivel] || 0) + 1; });
      box.innerHTML = Object.entries(counts).map(([k, n]) => `
        <div class="est-riesgo-pill">
          <span class="${NIVEL_CLS[k] || 'badge'}">${k.toUpperCase()}</span>
          <strong>${n}</strong>
        </div>`).join('');
    }
  }
}

async function loadEstrategiaPage() {
  const cont = document.getElementById('vista-estrategia');
  if (!cont) return;
  cont.innerHTML = '<div class="meta">Cargando módulo de estrategia…</div>';

  try {
    const [objetivos, expansion, riesgos, panel] = await Promise.all([
      api('/estrategia/objetivos'),
      api('/estrategia/expansion'),
      api('/estrategia/riesgos'),
      api('/estrategia/panel-analitico').catch(() => ({ motor: 'DuckDB', ventas_por_pais: [], ventas_por_linea: [] })),
    ]);
    estState.objetivos = objetivos || [];
    estState.expansion = expansion;
    estState.riesgos = riesgos || [];
    estState.panel = panel;
    estState.proyeccion = null;
    try {
      estState.proyeccion = await api('/estrategia/proyeccion?meses=12');
    } catch (pe) {
      estState.proyeccion = {
        serie: [],
        ingresos_ultimo_anio: 0,
        ingresos_proyectados_anio: 0,
        crecimiento_anual_pct: 0,
        _error: pe.message || 'No se pudo calcular la proyección',
      };
    }
    renderShell();
    if (estState.proyeccion?._error) {
      toast(estState.proyeccion._error, 'error');
    }
  } catch (e) {
    cont.innerHTML = `<div class="card"><p class="meta" style="color:var(--loss)">${escE(e.message || 'No se pudo cargar Estrategia')}</p>
      <button type="button" class="btn btn-primary btn-sm" id="est-retry">Reintentar</button></div>`;
    document.getElementById('est-retry')?.addEventListener('click', () => void loadEstrategiaPage());
    if (e?.name === 'AbortError' || /signal is aborted|aborted without reason/i.test(String(e?.message || ''))) return;
    throw e;
  }
}
