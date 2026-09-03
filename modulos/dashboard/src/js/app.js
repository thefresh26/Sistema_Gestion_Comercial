const COLOR_HEX = { SAE: '#1a5bbf', FRV: '#c77700' };
const COLOR_SUAVE = { SAE: 'rgba(26,91,191,.14)', FRV: 'rgba(199,119,0,.14)' };
const NOMBRES_MES = ['', 'Enero', 'Febrero', 'Marzo', 'Abril', 'Mayo', 'Junio',
  'Julio', 'Agosto', 'Septiembre', 'Octubre', 'Noviembre', 'Diciembre'];
const NOMBRES_MES_CORTO = ['', 'Ene', 'Feb', 'Mar', 'Abr', 'May', 'Jun',
  'Jul', 'Ago', 'Sep', 'Oct', 'Nov', 'Dic'];

const REDUCIR_MOVIMIENTO = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

let datosCompletos = [];
const sistemasOcultos = new Set();   // sistemas apagados por el segmentador "Sistema"
let anioFiltro = 'todos';            // 'todos' o un año específico
let mesFiltro = 'todos';             // 'todos' o un mes específico (1-12)
let medidaFiltro = 'folio';          // 'folio' o 'unidad' — solo aplica a SAE; FRV siempre usa 'total'

const charts = {};                   // instancias Chart.js vivas, por id de canvas

function fmtMoneda(n){
  return new Intl.NumberFormat('es-CO', { style:'currency', currency:'COP', maximumFractionDigits:0 }).format(n);
}
function fmtMonedaCorta(n){
  const abs = Math.abs(n);
  if (abs >= 1e9) return (n/1e9).toFixed(1).replace(/\.0$/,'') + 'MM';
  if (abs >= 1e6) return (n/1e6).toFixed(1).replace(/\.0$/,'') + 'M';
  if (abs >= 1e3) return (n/1e3).toFixed(0) + 'k';
  return fmtNumero(n);
}
function fmtNumero(n){
  return new Intl.NumberFormat('es-CO').format(Math.round(n));
}
function fmtPct(n){
  return new Intl.NumberFormat('es-CO', { maximumFractionDigits: 1 }).format(n) + '%';
}

// ── Iconos (SVG en línea, heredan color con currentColor — sin librería de íconos) ──
const ICONOS = {
  dinero: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="9"></circle><path d="M9.5 9.5a2 2 0 0 1 2-2h1a2 2 0 1 1 0 4h-1a2 2 0 1 0 0 4h1a2 2 0 0 0 2-2"></path><path d="M12 6.5v1M12 16v1"></path></svg>',
  capas: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3 2 8l10 5 10-5-10-5Z"></path><path d="m2 13 10 5 10-5"></path><path d="m2 18 10 5 10-5"></path></svg>',
  edificio: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="4" y="3" width="9" height="18"></rect><rect x="13" y="9" width="7" height="12"></rect><path d="M7 7h1M7 11h1M7 15h1M16 12h1M16 16h1"></path></svg>',
  ticket: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M4 8a2 2 0 0 1 2-2h12a2 2 0 0 1 2 2v2a2 2 0 0 0 0 4v2a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2v-2a2 2 0 0 0 0-4V8Z"></path><path d="M13 7v10" stroke-dasharray="2 2"></path></svg>',
  historial: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 12a9 9 0 1 0 3-6.7"></path><path d="M3 4v4h4"></path><path d="M12 8v4l3 2"></path></svg>',
  tendenciaArriba: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 17 10 10l4 4 7-7"></path><path d="M15 7h6v6"></path></svg>',
  tendenciaAbajo: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 7l7 7 4-4 7 7"></path><path d="M15 17h6v-6"></path></svg>',
  bombilla: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M9 18h6M10 21h4"></path><path d="M12 3a6 6 0 0 0-4 10.4c.6.5 1 1.3 1 2.1v.5h6v-.5c0-.8.4-1.6 1-2.1A6 6 0 0 0 12 3Z"></path></svg>',
};

// ── Filtrado ─────────────────────────────────────────────────────────────
// Devuelve las filas de datosCompletos según el filtro activo, con overrides
// puntuales para las gráficas que necesitan ignorar alguno de los filtros
// globales (p. ej. una gráfica "por año" que ignora el filtro de mes).
function filasBase(opts = {}){
  const {
    ignorarAnio = false,
    ignorarMes = false,
    ignorarOcultos = false,
    ignorarMedida = false,
    incluirHistorico = true,
    soloSistemas = null,
  } = opts;
  return datosCompletos.filter(f => {
    if (!incluirHistorico && f.es_acumulado_historico) return false;
    if (!ignorarOcultos && sistemasOcultos.has(f.sistema)) return false;
    if (soloSistemas && !soloSistemas.includes(f.sistema)) return false;
    if (!ignorarAnio && anioFiltro !== 'todos' && String(f.anio) !== String(anioFiltro)) return false;
    if (!ignorarMes && mesFiltro !== 'todos' && String(f.mes) !== String(mesFiltro)) return false;
    if (!ignorarMedida && f.medida !== 'total' && f.medida !== medidaFiltro) return false;
    return true;
  });
}

function agruparPorPeriodo(filas){
  const acc = new Map();
  filas.forEach(f => {
    const clave = `${f.anio}-${f.mes}`;
    if (!acc.has(clave)){
      acc.set(clave, { anio: f.anio, mes: f.mes, SAE: { cantidad: 0, valor_total: 0 }, FRV: { cantidad: 0, valor_total: 0 } });
    }
    const g = acc.get(clave);
    g[f.sistema].cantidad += f.cantidad;
    g[f.sistema].valor_total += Number(f.valor_total);
  });
  return [...acc.values()].sort((a, b) => a.anio - b.anio || a.mes - b.mes);
}

function agruparPorAnio(filas){
  const acc = new Map();
  filas.forEach(f => {
    if (!acc.has(f.anio)){
      acc.set(f.anio, { anio: f.anio, SAE: { cantidad: 0, valor_total: 0 }, FRV: { cantidad: 0, valor_total: 0 } });
    }
    const g = acc.get(f.anio);
    g[f.sistema].cantidad += f.cantidad;
    g[f.sistema].valor_total += Number(f.valor_total);
  });
  return [...acc.values()].sort((a, b) => a.anio - b.anio);
}

// ── Análisis automático ──────────────────────────────────────────────────
function calcularVariacion(serie, campo){
  if (serie.length < 2) return null;
  const actual = serie[serie.length - 1][campo];
  const anterior = serie[serie.length - 2][campo];
  if (!anterior) return null;
  return { pct: ((actual - anterior) / anterior) * 100, actual, anterior };
}

function calcularVariacionAnual(serie, campo){
  if (serie.length < 2) return null;
  const ultimo = serie[serie.length - 1];
  const anioPasado = serie.find(p => p.anio === ultimo.anio - 1 && p.mes === ultimo.mes);
  if (!anioPasado || !anioPasado[campo]) return null;
  return { pct: ((ultimo[campo] - anioPasado[campo]) / anioPasado[campo]) * 100, actual: ultimo[campo], anterior: anioPasado[campo], anio: ultimo.anio, mes: ultimo.mes };
}

function calcularHistoricoFRV(){
  const historico = datosCompletos.filter(f => f.sistema === 'FRV' && f.es_acumulado_historico);
  const reciente = datosCompletos.filter(f => f.sistema === 'FRV' && !f.es_acumulado_historico);
  const valorHist = historico.reduce((s, f) => s + Number(f.valor_total), 0);
  const valorRec = reciente.reduce((s, f) => s + Number(f.valor_total), 0);
  const cantidadHist = historico.reduce((s, f) => s + f.cantidad, 0);
  const cantidadRec = reciente.reduce((s, f) => s + f.cantidad, 0);
  const total = valorHist + valorRec;
  return { valorHist, valorRec, cantidadHist, cantidadRec, total, pctHist: total ? (valorHist / total) * 100 : 0 };
}

function iconoTendencia(positivo){ return positivo ? ICONOS.tendenciaArriba : ICONOS.tendenciaAbajo; }

function badgeTendencia(variacion){
  if (!variacion || !isFinite(variacion.pct)){
    return `<span class="tendencia neutro">Sin datos suficientes</span>`;
  }
  const positivo = variacion.pct >= 0;
  return `<span class="tendencia ${positivo ? 'up' : 'down'}">${iconoTendencia(positivo)}${fmtPct(Math.abs(variacion.pct))}</span>`;
}

function construirInsights(){
  const el = document.getElementById('insights-banner');
  const timeline = agruparPorPeriodo(filasBase({ ignorarAnio: true, ignorarMes: true, incluirHistorico: false }))
    .map(g => ({ ...g, combinadoValor: g.SAE.valor_total + g.FRV.valor_total }));

  const mom = calcularVariacion(timeline, 'combinadoValor');
  const yoy = calcularVariacionAnual(timeline, 'combinadoValor');
  const historicoFRV = calcularHistoricoFRV();

  const tarjetas = [];

  tarjetas.push(`
    <div class="insight-card">
      <div class="insight-icon">${ICONOS.bombilla}</div>
      <p>${mom
        ? `Contra el mes anterior, el <strong>valor vendido combinado</strong> ${mom.pct >= 0 ? 'subió' : 'bajó'} <strong>${fmtPct(Math.abs(mom.pct))}</strong> (${fmtMonedaCorta(mom.anterior)} → ${fmtMonedaCorta(mom.actual)}).`
        : 'Aún no hay suficiente historial mensual para comparar contra el mes anterior.'}</p>
    </div>
  `);

  tarjetas.push(`
    <div class="insight-card">
      <div class="insight-icon">${ICONOS.historial}</div>
      <p>${yoy
        ? `Contra ${NOMBRES_MES[yoy.mes]} de ${yoy.anio - 1}, el valor vendido combinado ${yoy.pct >= 0 ? 'subió' : 'bajó'} <strong>${fmtPct(Math.abs(yoy.pct))}</strong> año contra año.`
        : 'Todavía no hay un año completo de historial para comparar año contra año.'}</p>
    </div>
  `);

  tarjetas.push(`
    <div class="insight-card acento-frv">
      <div class="insight-icon">${ICONOS.edificio}</div>
      <p>El bloque <strong>histórico acumulado de FRV</strong> representa el <strong>${fmtPct(historicoFRV.pctHist)}</strong> del valor total registrado; el resto (<strong>${fmtPct(100 - historicoFRV.pctHist)}</strong>) corresponde a ventas detectadas en tiempo real desde que se activó el panel.</p>
    </div>
  `);

  el.innerHTML = tarjetas.map((html, i) => html.replace('class="insight-card', `style="animation-delay:${i * 60}ms" class="insight-card`)).join('');
}

// ── Tarjetas KPI ─────────────────────────────────────────────────────────
function construirKPIs(){
  const filas = filasBase();
  const totales = { SAE: { cantidad: 0, valor_total: 0 }, FRV: { cantidad: 0, valor_total: 0 } };
  filas.forEach(f => {
    totales[f.sistema].cantidad += f.cantidad;
    totales[f.sistema].valor_total += Number(f.valor_total);
  });
  const valorCombinado = totales.SAE.valor_total + totales.FRV.valor_total;
  const cantidadCombinada = totales.SAE.cantidad + totales.FRV.cantidad;
  const ticketProm = cantidadCombinada ? valorCombinado / cantidadCombinada : 0;
  const pctSAE = valorCombinado ? (totales.SAE.valor_total / valorCombinado) * 100 : 0;
  const pctFRV = valorCombinado ? (totales.FRV.valor_total / valorCombinado) * 100 : 0;
  const etiquetaMedida = medidaFiltro === 'unidad' ? 'unidades' : 'folios';

  const timeline = agruparPorPeriodo(filasBase({ ignorarAnio: true, ignorarMes: true, incluirHistorico: false }))
    .map(g => ({ ...g, combinadoValor: g.SAE.valor_total + g.FRV.valor_total, combinadoCantidad: g.SAE.cantidad + g.FRV.cantidad }));
  const momValor = calcularVariacion(timeline, 'combinadoValor');
  const momCantidad = calcularVariacion(timeline, 'combinadoCantidad');

  const grid = document.getElementById('stat-grid');
  grid.innerHTML = `
    <div class="stat-tile fila-in" style="animation-delay:0ms">
      <div class="stat-icon" style="background:#e8f0fc;color:var(--blue)">${ICONOS.dinero}</div>
      <div class="stat-label">Valor total vendido</div>
      <div class="stat-value">${fmtMonedaCorta(valorCombinado)}</div>
      ${badgeTendencia(momValor)}
    </div>
    <div class="stat-tile fila-in" style="animation-delay:50ms">
      <div class="stat-icon" style="background:#e8f0fc;color:var(--blue)">${ICONOS.capas}</div>
      <div class="stat-label">${etiquetaMedida.charAt(0).toUpperCase()+etiquetaMedida.slice(1)} + bienes vendidos</div>
      <div class="stat-value">${fmtNumero(cantidadCombinada)}</div>
      ${badgeTendencia(momCantidad)}
    </div>
    <div class="stat-tile fila-in ${sistemasOcultos.has('SAE') ? 'oculto' : ''}" style="animation-delay:100ms">
      <div class="stat-icon" style="background:#e8f0fc;color:${COLOR_HEX.SAE}">${ICONOS.capas}</div>
      <div class="stat-label"><span class="dot" style="background:${COLOR_HEX.SAE}"></span>SAE · Valor vendido</div>
      <div class="stat-value" style="font-size:19px;">${fmtMonedaCorta(totales.SAE.valor_total)}</div>
      <div class="stat-sub">${fmtPct(pctSAE)} del total combinado</div>
    </div>
    <div class="stat-tile fila-in ${sistemasOcultos.has('FRV') ? 'oculto' : ''}" style="animation-delay:150ms">
      <div class="stat-icon" style="background:#fdf1e3;color:${COLOR_HEX.FRV}">${ICONOS.edificio}</div>
      <div class="stat-label"><span class="dot" style="background:${COLOR_HEX.FRV}"></span>FRV · Valor vendido</div>
      <div class="stat-value" style="font-size:19px;">${fmtMonedaCorta(totales.FRV.valor_total)}</div>
      <div class="stat-sub">${fmtPct(pctFRV)} del total combinado</div>
    </div>
    <div class="stat-tile fila-in" style="animation-delay:200ms">
      <div class="stat-icon" style="background:#eef2fb;color:var(--navy)">${ICONOS.ticket}</div>
      <div class="stat-label">Ticket promedio</div>
      <div class="stat-value" style="font-size:19px;">${fmtMonedaCorta(ticketProm)}</div>
      <div class="stat-sub">valor / ${etiquetaMedida}</div>
    </div>
    <div class="stat-tile fila-in" style="animation-delay:250ms">
      <div class="stat-icon" style="background:#fdf1e3;color:${COLOR_HEX.FRV}">${ICONOS.historial}</div>
      <div class="stat-label">FRV · Histórico vs. reciente</div>
      <div class="stat-value" style="font-size:19px;">${fmtPct(calcularHistoricoFRV().pctHist)}</div>
      <div class="stat-sub">del valor FRV es bloque histórico</div>
    </div>
  `;
}

// ── Configuración común de Chart.js ──────────────────────────────────────
if (window.Chart){
  Chart.defaults.font.family = "'Open Sans', Arial, sans-serif";
  Chart.defaults.color = '#6b7a99';
  Chart.defaults.plugins.legend.labels.usePointStyle = true;
  Chart.defaults.plugins.legend.labels.boxWidth = 8;
  Chart.defaults.plugins.legend.labels.font = { family: "'Open Sans', Arial, sans-serif", size: 12, weight: '600' };
  Chart.defaults.animation = REDUCIR_MOVIMIENTO ? false : { duration: 450, easing: 'easeOutQuart' };
  Chart.defaults.plugins.tooltip.backgroundColor = '#0d1f3c';
  Chart.defaults.plugins.tooltip.titleFont = { family: "'Montserrat', Arial, sans-serif", weight: '700' };
  Chart.defaults.plugins.tooltip.padding = 10;
  Chart.defaults.plugins.tooltip.cornerRadius = 8;
}

function crearOActualizar(id, config){
  if (charts[id]){
    charts[id].data = config.data;
    charts[id].options = config.options;
    charts[id].config.type = config.type;
    charts[id].update();
    return charts[id];
  }
  const canvas = document.getElementById(id);
  if (!canvas) return null;
  charts[id] = new Chart(canvas, config);
  return charts[id];
}

const ejeMoneda = { ticks: { callback: v => fmtMonedaCorta(v) } };
const ejeNumero = { ticks: { callback: v => fmtNumero(v) } };
const gridSuave = { color: 'rgba(13,31,60,.06)' };

// 1. Evolución mensual — valor
function graficarEvolucionValor(){
  const serie = agruparPorPeriodo(filasBase({ incluirHistorico: false }));
  const etiquetas = serie.map(g => `${NOMBRES_MES_CORTO[g.mes]} ${String(g.anio).slice(2)}`);
  crearOActualizar('chart-evolucion-valor', {
    type: 'line',
    data: {
      labels: etiquetas,
      datasets: [
        { label: 'SAE', data: serie.map(g => g.SAE.valor_total), borderColor: COLOR_HEX.SAE, backgroundColor: COLOR_SUAVE.SAE, fill: true, tension: .3, hidden: sistemasOcultos.has('SAE'), pointRadius: 2, pointHoverRadius: 5 },
        { label: 'FRV', data: serie.map(g => g.FRV.valor_total), borderColor: COLOR_HEX.FRV, backgroundColor: COLOR_SUAVE.FRV, fill: true, tension: .3, hidden: sistemasOcultos.has('FRV'), pointRadius: 2, pointHoverRadius: 5 },
      ],
    },
    options: {
      responsive: true, maintainAspectRatio: false,
      interaction: { mode: 'index', intersect: false },
      scales: { y: { ...ejeMoneda, grid: gridSuave }, x: { grid: { display: false } } },
      plugins: { tooltip: { callbacks: { label: ctx => `${ctx.dataset.label}: ${fmtMoneda(ctx.parsed.y)}` } } },
    },
  });
}

// 2. Evolución mensual — cantidad
function graficarEvolucionCantidad(){
  const serie = agruparPorPeriodo(filasBase({ incluirHistorico: false }));
  const etiquetas = serie.map(g => `${NOMBRES_MES_CORTO[g.mes]} ${String(g.anio).slice(2)}`);
  crearOActualizar('chart-evolucion-cantidad', {
    type: 'line',
    data: {
      labels: etiquetas,
      datasets: [
        { label: 'SAE', data: serie.map(g => g.SAE.cantidad), borderColor: COLOR_HEX.SAE, backgroundColor: COLOR_SUAVE.SAE, fill: true, tension: .3, hidden: sistemasOcultos.has('SAE'), pointRadius: 2, pointHoverRadius: 5 },
        { label: 'FRV', data: serie.map(g => g.FRV.cantidad), borderColor: COLOR_HEX.FRV, backgroundColor: COLOR_SUAVE.FRV, fill: true, tension: .3, hidden: sistemasOcultos.has('FRV'), pointRadius: 2, pointHoverRadius: 5 },
      ],
    },
    options: {
      responsive: true, maintainAspectRatio: false,
      interaction: { mode: 'index', intersect: false },
      scales: { y: { ...ejeNumero, grid: gridSuave }, x: { grid: { display: false } } },
      plugins: { tooltip: { callbacks: { label: ctx => `${ctx.dataset.label}: ${fmtNumero(ctx.parsed.y)}` } } },
    },
  });
}

// 3 y 4. Comparativo anual (valor / cantidad)
function graficarAnual(id, campo, formateador){
  const serie = agruparPorAnio(filasBase());
  crearOActualizar(id, {
    type: 'bar',
    data: {
      labels: serie.map(g => String(g.anio)),
      datasets: [
        { label: 'SAE', data: serie.map(g => g.SAE[campo]), backgroundColor: COLOR_HEX.SAE, borderRadius: 6, hidden: sistemasOcultos.has('SAE') },
        { label: 'FRV', data: serie.map(g => g.FRV[campo]), backgroundColor: COLOR_HEX.FRV, borderRadius: 6, hidden: sistemasOcultos.has('FRV') },
      ],
    },
    options: {
      responsive: true, maintainAspectRatio: false,
      scales: { y: { ticks: { callback: v => formateador(v) }, grid: gridSuave }, x: { grid: { display: false } } },
      plugins: { tooltip: { callbacks: { label: ctx => `${ctx.dataset.label}: ${formateador(ctx.parsed.y)}` } } },
    },
  });
}

// 5 y 6. Donas de participación
function graficarDonut(id, campo){
  const filas = filasBase();
  const totales = { SAE: 0, FRV: 0 };
  filas.forEach(f => { totales[f.sistema] += campo === 'valor_total' ? Number(f.valor_total) : f.cantidad; });
  crearOActualizar(id, {
    type: 'doughnut',
    data: {
      labels: ['SAE', 'FRV'],
      datasets: [{ data: [totales.SAE, totales.FRV], backgroundColor: [COLOR_HEX.SAE, COLOR_HEX.FRV], borderWidth: 0, hoverOffset: 6 }],
    },
    options: {
      responsive: true, maintainAspectRatio: false,
      cutout: '68%',
      plugins: {
        legend: { position: 'bottom' },
        tooltip: { callbacks: { label: ctx => {
          const total = totales.SAE + totales.FRV;
          const v = ctx.parsed;
          const pct = total ? (v/total)*100 : 0;
          return `${ctx.label}: ${campo === 'valor_total' ? fmtMoneda(v) : fmtNumero(v)} (${fmtPct(pct)})`;
        } } },
      },
    },
  });
}

// 7. SAE: folios vs unidades por año (ignora el filtro de medida y de sistema)
function graficarSaeMedida(){
  const filas = filasBase({ soloSistemas: ['SAE'], ignorarOcultos: true, ignorarMedida: true });
  const acc = new Map();
  filas.forEach(f => {
    if (!acc.has(f.anio)) acc.set(f.anio, { folio: 0, unidad: 0 });
    if (f.medida === 'folio' || f.medida === 'unidad') acc.get(f.anio)[f.medida] += f.cantidad;
  });
  const anios = [...acc.keys()].sort();
  crearOActualizar('chart-sae-medida', {
    type: 'bar',
    data: {
      labels: anios.map(String),
      datasets: [
        { label: 'Folios', data: anios.map(a => acc.get(a).folio), backgroundColor: COLOR_HEX.SAE, borderRadius: 6 },
        { label: 'Unidades', data: anios.map(a => acc.get(a).unidad), backgroundColor: '#8fb4e6', borderRadius: 6 },
      ],
    },
    options: {
      responsive: true, maintainAspectRatio: false,
      scales: { y: { ...ejeNumero, grid: gridSuave }, x: { grid: { display: false } } },
    },
  });
}

// 8. Variación % mes contra mes anterior (combinado, sin histórico)
function graficarVariacion(){
  const serie = agruparPorPeriodo(filasBase({ ignorarAnio: true, ignorarMes: true, incluirHistorico: false }))
    .map(g => ({ ...g, combinado: g.SAE.valor_total + g.FRV.valor_total }));
  const variaciones = serie.map((g, i) => {
    if (i === 0 || !serie[i-1].combinado) return null;
    return ((g.combinado - serie[i-1].combinado) / serie[i-1].combinado) * 100;
  });
  crearOActualizar('chart-variacion', {
    type: 'line',
    data: {
      labels: serie.map(g => `${NOMBRES_MES_CORTO[g.mes]} ${String(g.anio).slice(2)}`),
      datasets: [{
        label: 'Variación %', data: variaciones,
        borderColor: '#1a5bbf', backgroundColor: 'rgba(26,91,191,.12)', fill: true, tension: .25,
        pointBackgroundColor: variaciones.map(v => v == null ? '#9aa8c4' : (v >= 0 ? '#1a7f37' : '#b42318')),
        pointRadius: 3, spanGaps: true,
      }],
    },
    options: {
      responsive: true, maintainAspectRatio: false,
      scales: { y: { ticks: { callback: v => v + '%' }, grid: gridSuave }, x: { grid: { display: false } } },
      plugins: {
        legend: { display: false },
        tooltip: { callbacks: { label: ctx => ctx.parsed.y == null ? 'Sin dato previo' : `${ctx.parsed.y >= 0 ? '+' : ''}${fmtPct(ctx.parsed.y)}` } },
      },
    },
  });
}

// 9. Top 6 meses por valor vendido (barra horizontal, sin histórico)
function graficarTopMeses(){
  const serie = agruparPorPeriodo(filasBase({ incluirHistorico: false }))
    .map(g => ({ ...g, combinado: g.SAE.valor_total + g.FRV.valor_total }))
    .sort((a, b) => b.combinado - a.combinado)
    .slice(0, 6)
    .sort((a, b) => a.combinado - b.combinado);
  crearOActualizar('chart-top-meses', {
    type: 'bar',
    data: {
      labels: serie.map(g => `${NOMBRES_MES[g.mes]} ${g.anio}`),
      datasets: [{ label: 'Valor vendido', data: serie.map(g => g.combinado), backgroundColor: '#1a5bbf', borderRadius: 6 }],
    },
    options: {
      indexAxis: 'y',
      responsive: true, maintainAspectRatio: false,
      scales: { x: { ...ejeMoneda, grid: gridSuave }, y: { grid: { display: false } } },
      plugins: { legend: { display: false }, tooltip: { callbacks: { label: ctx => fmtMoneda(ctx.parsed.x) } } },
    },
  });
}

// 10. Combo valor (barra) + cantidad (línea) por año
function graficarComboAnual(){
  const serie = agruparPorAnio(filasBase())
    .map(g => ({ anio: g.anio, valor: g.SAE.valor_total + g.FRV.valor_total, cantidad: g.SAE.cantidad + g.FRV.cantidad }));
  crearOActualizar('chart-combo-anual', {
    type: 'bar',
    data: {
      labels: serie.map(g => String(g.anio)),
      datasets: [
        { type: 'bar', label: 'Valor vendido', data: serie.map(g => g.valor), backgroundColor: 'rgba(26,91,191,.75)', borderRadius: 6, yAxisID: 'y' },
        { type: 'line', label: 'Cantidad vendida', data: serie.map(g => g.cantidad), borderColor: '#c77700', backgroundColor: '#c77700', tension: .3, yAxisID: 'y1', pointRadius: 4 },
      ],
    },
    options: {
      responsive: true, maintainAspectRatio: false,
      scales: {
        y: { position: 'left', ...ejeMoneda, grid: gridSuave },
        y1: { position: 'right', ...ejeNumero, grid: { display: false } },
        x: { grid: { display: false } },
      },
    },
  });
}

// 11. FRV histórico vs. reciente
function graficarFrvHistorico(){
  const h = calcularHistoricoFRV();
  crearOActualizar('chart-frv-historico', {
    type: 'bar',
    data: {
      labels: ['Valor vendido', 'Bienes vendidos'],
      datasets: [
        { label: 'Histórico acumulado', data: [h.valorHist, h.cantidadHist], backgroundColor: '#e3b26b', borderRadius: 6 },
        { label: 'Detectado en tiempo real', data: [h.valorRec, h.cantidadRec], backgroundColor: COLOR_HEX.FRV, borderRadius: 6 },
      ],
    },
    options: {
      responsive: true, maintainAspectRatio: false,
      scales: { y: { grid: gridSuave }, x: { grid: { display: false } } },
      plugins: { tooltip: { callbacks: { label: ctx => ctx.dataIndex === 0 ? `${ctx.dataset.label}: ${fmtMoneda(ctx.parsed.y)}` : `${ctx.dataset.label}: ${fmtNumero(ctx.parsed.y)}` } } },
    },
  });
}

function construirTabla(){
  const filas = filasBase();
  const body = document.getElementById('tabla-body');
  body.innerHTML = filas
    .slice()
    .sort((a,b) => a.anio - b.anio || (a.mes||0) - (b.mes||0) || a.sistema.localeCompare(b.sistema))
    .map((f, i) => {
      const color = f.sistema === 'SAE' ? 'var(--serie-sae)' : 'var(--serie-frv)';
      const medidaTexto = f.medida === 'total' ? 'Bienes (FRV)' : (f.medida === 'unidad' ? 'Unidades' : 'Folios');
      const retraso = Math.min(i, 15) * 20;
      return `
      <tr class="fila-in" style="animation-delay:${retraso}ms">
        <td><span class="tabla-sistema" style="--col:${color}"><span class="dot"></span>${f.sistema}</span></td>
        <td>${f.anio}</td>
        <td>${f.mes ? NOMBRES_MES[f.mes] : '—'}</td>
        <td><span class="tabla-medida">${medidaTexto}</span></td>
        <td class="tabla-cantidad">${fmtNumero(f.cantidad)}</td>
        <td class="tabla-valor">${fmtMoneda(f.valor_total)}${f.es_acumulado_historico ? ' <span class="tabla-historico">histórico</span>' : ''}</td>
      </tr>
    `;
    }).join('');
}

function construirFiltroAnio(){
  const sel = document.getElementById('filtro-anio');
  const anios = [...new Set(datosCompletos.map(f => f.anio))].sort();
  const actual = sel.value;
  sel.innerHTML = '<option value="todos">Todos</option>' +
    anios.map(a => `<option value="${a}">${a}</option>`).join('');
  sel.value = anios.includes(Number(actual)) ? actual : 'todos';
}

function renderizarTodo(){
  construirInsights();
  construirKPIs();
  graficarEvolucionValor();
  graficarEvolucionCantidad();
  graficarAnual('chart-anual-valor', 'valor_total', fmtMonedaCorta);
  graficarAnual('chart-anual-cantidad', 'cantidad', fmtNumero);
  graficarDonut('chart-donut-valor', 'valor_total');
  graficarDonut('chart-donut-cantidad', 'cantidad');
  graficarSaeMedida();
  graficarVariacion();
  graficarTopMeses();
  graficarComboAnual();
  graficarFrvHistorico();
  construirTabla();
}

async function cargar(){
  try{
    const r = await fetch('/api/dashboard/resumen');
    if(!r.ok) throw new Error('Error al cargar');
    const datos = await r.json();

    document.getElementById('estado-carga').style.display = 'none';

    if(!Array.isArray(datos) || datos.length === 0){
      document.getElementById('estado-error').style.display = 'block';
      document.getElementById('estado-error').textContent =
        'Todavía no hay datos calculados. La tarea programada corre periódicamente; vuelve a intentar más tarde.';
      return;
    }

    datosCompletos = datos;
    document.getElementById('contenido').style.display = 'block';
    construirFiltroAnio();
    renderizarTodo();

  }catch(e){
    document.getElementById('estado-carga').style.display = 'none';
    const err = document.getElementById('estado-error');
    err.style.display = 'block';
    err.textContent = 'No se pudo cargar la información del dashboard.';
  }
}

document.getElementById('btn-toggle-tabla').addEventListener('click', () => {
  const wrap = document.getElementById('tabla-wrap');
  const visible = wrap.style.display !== 'none';
  wrap.style.display = visible ? 'none' : 'block';
  document.getElementById('btn-toggle-tabla').textContent = visible ? 'Ver tabla detallada' : 'Ocultar tabla';
});

document.getElementById('filtro-anio').addEventListener('change', (ev) => {
  anioFiltro = ev.target.value;
  renderizarTodo();
});

document.getElementById('filtro-mes').addEventListener('change', (ev) => {
  mesFiltro = ev.target.value;
  renderizarTodo();
});

document.getElementById('sistema-toggle').addEventListener('click', (ev) => {
  const btn = ev.target.closest('.vista-btn');
  if (!btn) return;
  const valor = btn.dataset.sistema;
  sistemasOcultos.clear();
  if (valor === 'SAE') sistemasOcultos.add('FRV');
  if (valor === 'FRV') sistemasOcultos.add('SAE');
  document.querySelectorAll('#sistema-toggle .vista-btn').forEach(b => b.classList.toggle('activo', b === btn));
  renderizarTodo();
});

document.getElementById('medida-toggle').addEventListener('click', (ev) => {
  const btn = ev.target.closest('.vista-btn');
  if (!btn) return;
  medidaFiltro = btn.dataset.medida;
  document.querySelectorAll('#medida-toggle .vista-btn').forEach(b => b.classList.toggle('activo', b === btn));
  renderizarTodo();
});

cargar();
