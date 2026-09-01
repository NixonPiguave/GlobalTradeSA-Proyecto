/* charts.js — Componentes Chart.js reutilizables (estética pastel + tipos mixtos) */
const GTChart = (() => {
  const palette = ['#7c6bb5', '#5b8fd9', '#3d9b8f', '#d4a017', '#c97b84', '#6b8cae', '#9b7bb8', '#5a9e8f'];
  const fills = palette.map((c) => c + 'cc');

  function destroy(id) {
    if (window.charts && window.charts[id]) {
      window.charts[id].destroy();
      delete window.charts[id];
    }
  }

  function moneyLike(label) {
    const s = String(label || '').toLowerCase();
    return /ingreso|costo|profit|ganancia|revenue|venta|compra|\$|usd|monto|total/.test(s);
  }

  function parseNum(v) {
    if (typeof v === 'number') return v;
    return parseFloat(String(v ?? '').replace(/[^0-9.-]/g, '')) || 0;
  }

  function baseOpts(extra = {}) {
    return {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { display: false, labels: { color: '#5a6478', boxWidth: 12 } },
        tooltip: {
          backgroundColor: 'rgba(45,52,70,.92)',
          titleFont: { size: 12 },
          bodyFont: { size: 12 },
          padding: 10,
          cornerRadius: 8,
        },
      },
      scales: {
        x: {
          ticks: { color: '#6b7280', maxRotation: 40, font: { size: 11 } },
          grid: { color: 'rgba(124,107,181,.08)', drawBorder: false },
        },
        y: {
          ticks: { color: '#6b7280', font: { size: 11 } },
          grid: { color: 'rgba(124,107,181,.1)', drawBorder: false },
        },
      },
      ...extra,
    };
  }

  function renderBar(id, labels, values, opts = {}) {
    const ctx = document.getElementById(id);
    if (!ctx || typeof Chart === 'undefined') return;
    destroy(id);
    window.charts = window.charts || {};
    const colors = labels.map((_, i) => fills[i % fills.length]);
    window.charts[id] = new Chart(ctx, {
      type: 'bar',
      data: {
        labels,
        datasets: [{
          data: values,
          backgroundColor: colors,
          borderColor: colors.map((c) => c.slice(0, 7)),
          borderWidth: 1,
          borderRadius: 10,
          maxBarThickness: opts.horizontal ? 28 : 42,
        }],
      },
      options: {
        ...baseOpts(),
        indexAxis: opts.horizontal ? 'y' : 'x',
        plugins: {
          ...baseOpts().plugins,
          legend: { display: false },
        },
      },
    });
  }

  function renderDonut(id, labels, values) {
    const ctx = document.getElementById(id);
    if (!ctx || typeof Chart === 'undefined') return;
    destroy(id);
    window.charts = window.charts || {};
    window.charts[id] = new Chart(ctx, {
      type: 'doughnut',
      data: {
        labels,
        datasets: [{
          data: values,
          backgroundColor: fills,
          borderColor: '#fff',
          borderWidth: 2,
          hoverOffset: 6,
        }],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        cutout: '58%',
        plugins: {
          legend: { position: 'right', labels: { color: '#5a6478', boxWidth: 12, padding: 12 } },
        },
      },
    });
  }

  function renderLine(id, labels, values) {
    const ctx = document.getElementById(id);
    if (!ctx || typeof Chart === 'undefined') return;
    destroy(id);
    window.charts = window.charts || {};
    window.charts[id] = new Chart(ctx, {
      type: 'line',
      data: {
        labels,
        datasets: [{
          data: values,
          borderColor: palette[0],
          backgroundColor: 'rgba(124,107,181,.18)',
          fill: true,
          tension: 0.35,
          pointRadius: 3,
          pointBackgroundColor: palette[1],
          borderWidth: 2.5,
        }],
      },
      options: baseOpts(),
    });
  }

  /** Serie dual estética (ej. real vs proyectado). */
  function renderDualLine(id, labels, seriesA, seriesB, opts = {}) {
    const ctx = document.getElementById(id);
    if (!ctx || typeof Chart === 'undefined') return;
    destroy(id);
    window.charts = window.charts || {};
    window.charts[id] = new Chart(ctx, {
      type: 'line',
      data: {
        labels,
        datasets: [
          {
            label: opts.labelA || 'Real',
            data: seriesA,
            borderColor: palette[1],
            backgroundColor: 'rgba(91,143,217,.15)',
            fill: true,
            tension: 0.35,
            pointRadius: 2.5,
            borderWidth: 2.5,
          },
          {
            label: opts.labelB || 'Proyectado',
            data: seriesB,
            borderColor: palette[3],
            backgroundColor: 'rgba(212,160,23,.12)',
            fill: true,
            tension: 0.35,
            pointRadius: 2.5,
            borderWidth: 2.5,
            borderDash: [6, 4],
          },
        ],
      },
      options: {
        ...baseOpts(),
        plugins: {
          ...baseOpts().plugins,
          legend: { display: true, position: 'top', labels: { color: '#5a6478', boxWidth: 12 } },
        },
      },
    });
  }

  function renderScatter(id, points) {
    const ctx = document.getElementById(id);
    if (!ctx || typeof Chart === 'undefined') return;
    destroy(id);
    window.charts = window.charts || {};
    window.charts[id] = new Chart(ctx, {
      type: 'scatter',
      data: {
        datasets: [{
          label: 'Margen vs ingreso',
          data: points,
          backgroundColor: palette[2],
          borderColor: palette[0],
          pointRadius: 5,
        }],
      },
      options: baseOpts(),
    });
  }

  /** Elige visualización según forma de los datos (evita barras planas mezclando escalas). */
  function renderSmart(id, labels, values, opts = {}) {
    const vals = (values || []).map(parseNum);
    const labs = labels || [];
    if (!labs.length || !vals.length) return;
    const max = Math.max(...vals.map(Math.abs), 0);
    const minPos = Math.min(...vals.filter((v) => v > 0), max || 1);
    const ratio = minPos > 0 ? max / minPos : 1;
    const n = labs.length;

    if (opts.prefer === 'donut' || (n <= 6 && ratio < 80 && !opts.forceBar)) {
      renderDonut(id, labs, vals);
      return;
    }
    if (opts.prefer === 'line' || (n >= 8 && ratio < 50)) {
      renderLine(id, labs, vals);
      return;
    }
    renderBar(id, labs, vals, { horizontal: opts.horizontal ?? (n > 6 || labs.some((l) => String(l).length > 14)) });
  }

  /**
   * Para tablas de reporte: si hay varias columnas numéricas con escalas distintas
   * (p.ej. unidades vs ingresos), grafica solo columnas monetarias o top categoría.
   */
  function chartFromTable(id, headers, rows, opts = {}) {
    if (!headers?.length || !rows?.length) return false;
    const numCols = headers
      .map((h, i) => ({ h, i, vals: rows.map((r) => parseNum(r[i])) }))
      .filter((c) => c.vals.some((v) => v !== 0));
    if (!numCols.length) return false;

    const moneyCols = numCols.filter((c) => moneyLike(c.h));
    const chosen = moneyCols.length ? moneyCols : [numCols[numCols.length - 1]];
    const labelCol = 0;
    const top = rows.slice(0, opts.limit || 12);

    if (chosen.length === 1) {
      const c = chosen[0];
      renderSmart(
        id,
        top.map((r) => String(r[labelCol]).slice(0, 28)),
        top.map((r) => parseNum(r[c.i])),
        { horizontal: true },
      );
      return true;
    }

    // Varias series monetarias → barras agrupadas pastel
    const ctx = document.getElementById(id);
    if (!ctx || typeof Chart === 'undefined') return false;
    destroy(id);
    window.charts = window.charts || {};
    window.charts[id] = new Chart(ctx, {
      type: 'bar',
      data: {
        labels: top.map((r) => String(r[labelCol]).slice(0, 22)),
        datasets: chosen.slice(0, 4).map((c, idx) => ({
          label: String(c.h),
          data: top.map((r) => parseNum(r[c.i])),
          backgroundColor: fills[idx % fills.length],
          borderRadius: 8,
          maxBarThickness: 28,
        })),
      },
      options: {
        ...baseOpts(),
        plugins: {
          ...baseOpts().plugins,
          legend: { display: true, position: 'top', labels: { color: '#5a6478', boxWidth: 12 } },
        },
      },
    });
    return true;
  }

  function chartPanelHtml(id, title, height = 280) {
    return `
      <div class="card chart-panel">
        <div class="card-title">${title}</div>
        <div class="chart-wrap" style="height:${height}px"><canvas id="${id}"></canvas></div>
      </div>`;
  }

  async function loadAnalyticsChart(vista, canvasId, opts = {}) {
    const panel = document.getElementById(canvasId)?.closest('.chart-panel');
    try {
      const q = new URLSearchParams();
      if (opts.desde) q.set('desde', opts.desde);
      if (opts.hasta) q.set('hasta', opts.hasta);
      const data = await api(`/analytics/${vista}?${q}`, { cache: 'no-store' });
      const items = data.items || [];
      if (vista === 'ranking-proveedores') {
        renderSmart(canvasId, items.map((i) => i.proveedor), items.map((i) => i.total_comprado), { horizontal: true });
      } else if (vista === 'ranking-clientes') {
        renderSmart(canvasId, items.map((i) => i.cliente), items.map((i) => i.total_comprado), { horizontal: true });
      } else if (vista === 'ventas-por-pais') {
        renderSmart(canvasId, items.map((i) => i.country), items.map((i) => i.total_revenue), { horizontal: true });
      } else if (vista === 'ventas-por-linea') {
        renderSmart(canvasId, items.map((i) => i.linea), items.map((i) => i.total_revenue), { prefer: items.length <= 6 ? 'donut' : 'bar' });
      } else if (vista === 'pedidos-por-estado') {
        renderDonut(canvasId, items.map((i) => i.estado), items.map((i) => i.cantidad));
      } else if (vista === 'margen-por-categoria') {
        renderScatter(canvasId, items.map((i) => ({ x: i.ingresos, y: i.margen_pct })));
      }
      if (panel) {
        let meta = panel.querySelector('.chart-motor');
        if (!meta) {
          meta = document.createElement('div');
          meta.className = 'chart-motor meta';
          panel.appendChild(meta);
        }
        meta.textContent = data.motor ? `Fuente: ${data.motor}` : '';
      }
      return data;
    } catch (e) {
      if (e?.name === 'AbortError') return null;
      destroy(canvasId);
      const wrap = document.getElementById(canvasId)?.parentElement;
      if (wrap) {
        wrap.innerHTML = `<p class="meta" style="padding:1rem;color:var(--loss)">${String(e.message || 'Sin datos')}</p><canvas id="${canvasId}" hidden></canvas>`;
      }
      return null;
    }
  }

  return {
    renderBar, renderDonut, renderScatter, renderLine, renderDualLine, renderSmart,
    chartFromTable, chartPanelHtml, loadAnalyticsChart, destroy, palette,
  };
})();
