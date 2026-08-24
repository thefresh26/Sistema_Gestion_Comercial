const COLOR_HEX = { SAE: '#1a5bbf', FRV: '#c77700' };
const NOMBRES_MES = ['', 'Enero', 'Febrero', 'Marzo', 'Abril', 'Mayo', 'Junio',
  'Julio', 'Agosto', 'Septiembre', 'Octubre', 'Noviembre', 'Diciembre'];

let datosCompletos = [];
const sistemasOcultos = new Set();   // sistemas apagados por clic en la leyenda
let anioFiltro = 'todos';            // 'todos' o un año específico
let mesFiltro = 'todos';             // 'todos' o un mes específico (1-12)
let vista = 'anio';                  // 'anio' (agrupa por año) o 'mes' (por año y mes)
let medidaFiltro = 'folio';          // 'folio' o 'unidad' — solo aplica a SAE; FRV siempre usa 'total'

function fmtMoneda(n){
  return new Intl.NumberFormat('es-CO', { style:'currency', currency:'COP', maximumFractionDigits:0 }).format(n);
}
function fmtNumero(n){
  return new Intl.NumberFormat('es-CO').format(n);
}
function fmtPct(n){
  return new Intl.NumberFormat('es-CO', { maximumFractionDigits: 1 }).format(n) + '%';
}

const tooltip = document.getElementById('tooltip');
function mostrarTooltip(ev, texto){
  tooltip.textContent = texto;
  tooltip.style.left = ev.clientX + 'px';
  tooltip.style.top = (ev.clientY - 10) + 'px';
  tooltip.classList.add('visible');
}
function ocultarTooltip(){ tooltip.classList.remove('visible'); }

function datosFiltrados(){
  return datosCompletos.filter(f =>
    !sistemasOcultos.has(f.sistema) &&
    (anioFiltro === 'todos' || String(f.anio) === String(anioFiltro)) &&
    (mesFiltro === 'todos' || String(f.mes) === String(mesFiltro)) &&
    // FRV no distingue folio/unidad (siempre 'total'); SAE respeta el toggle.
    (f.medida === 'total' || f.medida === medidaFiltro)
  );
}

// Agrupa las filas filtradas según la vista activa: sumadas por año, o
// desagregadas por año+mes.
function filasAgrupadas(filas){
  if (vista === 'anio'){
    const acc = new Map();
    filas.forEach(f => {
      const clave = `${f.anio}|${f.sistema}`;
      if (!acc.has(clave)){
        acc.set(clave, { anio: f.anio, mes: null, sistema: f.sistema, medida: f.medida, cantidad: 0, valor_total: 0, es_acumulado_historico: false });
      }
      const grupo = acc.get(clave);
      grupo.cantidad += f.cantidad;
      grupo.valor_total += Number(f.valor_total);
      if (f.es_acumulado_historico) grupo.es_acumulado_historico = true;
    });
    return [...acc.values()];
  }
  // vista === 'mes': cada fila ya viene desagregada por año+mes.
  return filas;
}

function etiquetaGrupo(fila){
  if (fila.mes){
    const historico = fila.es_acumulado_historico ? ' (acumulado histórico FRV)' : '';
    return `${NOMBRES_MES[fila.mes]} ${fila.anio}${historico}`;
  }
  return fila.es_acumulado_historico ? `${fila.anio} (acumulado histórico FRV)` : String(fila.anio);
}

function construirLeyenda(el){
  el.innerHTML = '';
  ['SAE', 'FRV'].forEach(sistema => {
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = sistemasOcultos.has(sistema) ? 'oculto' : '';
    btn.innerHTML = `<span class="sw" style="background:${COLOR_HEX[sistema]}"></span>${sistema}`;
    btn.title = sistemasOcultos.has(sistema) ? `Mostrar ${sistema}` : `Ocultar ${sistema}`;
    btn.addEventListener('click', () => {
      if (sistemasOcultos.has(sistema)) sistemasOcultos.delete(sistema);
      else sistemasOcultos.add(sistema);
      renderizarTodo();
    });
    el.appendChild(btn);
  });
}

function construirBarras(contenedor, filasCrudas, campo, formateador){
  contenedor.innerHTML = '';
  const filas = filasAgrupadas(filasCrudas);
  if (filas.length === 0){
    contenedor.innerHTML = '<p style="color:var(--muted);font-size:13px;">No hay datos para el filtro seleccionado.</p>';
    return;
  }
  // Orden cronológico: por año y, si aplica, por mes.
  const gruposOrdenados = [...new Set(filas.map(f => `${f.anio}|${f.mes || 0}`))]
    .sort((a, b) => {
      const [aAnio, aMes] = a.split('|').map(Number);
      const [bAnio, bMes] = b.split('|').map(Number);
      return aAnio - bAnio || aMes - bMes;
    });
  const maxValor = Math.max(1, ...filas.map(f => f[campo]));

  gruposOrdenados.forEach(claveGrupo => {
    const [anio, mesNum] = claveGrupo.split('|').map(Number);
    const filasGrupo = filas.filter(f => f.anio === anio && (f.mes || 0) === mesNum);
    if (!filasGrupo.length) return;

    const grupo = document.createElement('div');
    grupo.className = 'chart-grupo-anio';
    grupo.innerHTML = `<div class="anio-label">${etiquetaGrupo(filasGrupo[0])}</div>`;

    ['SAE', 'FRV'].forEach(sistema => {
      const fila = filasGrupo.find(f => f.sistema === sistema);
      if (!fila) return;
      const valor = fila[campo];
      const pct = Math.max(2, Math.round((valor / maxValor) * 100));

      const filaEl = document.createElement('div');
      filaEl.className = 'barra-fila';
      filaEl.innerHTML = `
        <div class="barra-sistema">${sistema}</div>
        <div class="barra-pista">
          <div class="barra-fill" style="width:${pct}%; background:${COLOR_HEX[sistema]};"></div>
        </div>
        <div class="barra-valor">${formateador(valor)}</div>
      `;
      const fill = filaEl.querySelector('.barra-fill');
      const etiquetaTip = fila.mes ? `${NOMBRES_MES[fila.mes]} ${fila.anio}` : String(fila.anio);
      fill.addEventListener('mousemove', ev => mostrarTooltip(ev, `${sistema} · ${etiquetaTip}: ${formateador(valor)}`));
      fill.addEventListener('mouseleave', ocultarTooltip);
      grupo.appendChild(filaEl);
    });

    contenedor.appendChild(grupo);
  });
}

// ── Donut de distribución SAE vs FRV para el período filtrado ──────────
function construirDonut(filas){
  const cont = document.getElementById('donut-chart');
  if (!cont) return;
  cont.innerHTML = '';

  const totales = { SAE: 0, FRV: 0 };
  filas.forEach(f => { totales[f.sistema] += f.cantidad; });
  const total = totales.SAE + totales.FRV;

  if (total === 0){
    cont.innerHTML = '<p style="color:var(--muted);font-size:13px;">No hay datos para el filtro seleccionado.</p>';
    return;
  }

  const pctSAE = (totales.SAE / total) * 100;
  const pctFRV = (totales.FRV / total) * 100;

  const R = 60, C = 2 * Math.PI * R, GAP = total && totales.SAE && totales.FRV ? 3 : 0;
  const largoSAE = Math.max(0, (pctSAE / 100) * C - GAP);
  const largoFRV = Math.max(0, (pctFRV / 100) * C - GAP);
  const offsetFRV = (pctSAE / 100) * C;

  const wrap = document.createElement('div');
  wrap.className = 'donut-wrap';
  wrap.innerHTML = `
    <svg viewBox="0 0 140 140" class="donut-svg" role="img" aria-label="Distribución SAE ${fmtPct(pctSAE)}, FRV ${fmtPct(pctFRV)}">
      <circle cx="70" cy="70" r="${R}" fill="none" stroke="var(--off)" stroke-width="20"></circle>
      ${totales.SAE ? `<circle class="donut-seg" cx="70" cy="70" r="${R}" fill="none" stroke="${COLOR_HEX.SAE}" stroke-width="20"
        stroke-dasharray="${largoSAE} ${C - largoSAE}" stroke-dashoffset="0" transform="rotate(-90 70 70)"></circle>` : ''}
      ${totales.FRV ? `<circle class="donut-seg" cx="70" cy="70" r="${R}" fill="none" stroke="${COLOR_HEX.FRV}" stroke-width="20"
        stroke-dasharray="${largoFRV} ${C - largoFRV}" stroke-dashoffset="${-offsetFRV}" transform="rotate(-90 70 70)"></circle>` : ''}
    </svg>
    <div class="donut-centro">
      <div class="donut-total">${fmtNumero(total)}</div>
      <div class="donut-total-sub">vendidos</div>
    </div>
  `;
  cont.appendChild(wrap);

  const detalle = document.getElementById('donut-detalle');
  detalle.innerHTML = ['SAE', 'FRV'].filter(s => !sistemasOcultos.has(s)).map(s => `
    <div class="donut-fila">
      <span class="dot" style="background:${COLOR_HEX[s]}"></span>
      <span class="donut-fila-nombre">${s}</span>
      <span class="donut-fila-valor">${fmtNumero(totales[s])} · ${fmtPct(total ? (totales[s]/total)*100 : 0)}</span>
    </div>
  `).join('');
}

function construirStatTiles(filas){
  const totales = { SAE: { cantidad:0, valor_total:0 }, FRV: { cantidad:0, valor_total:0 } };
  filas.forEach(f => {
    totales[f.sistema].cantidad += f.cantidad;
    totales[f.sistema].valor_total += Number(f.valor_total);
  });

  const etiquetaMedida = medidaFiltro === 'unidad' ? 'unidades' : 'folios';
  const grid = document.getElementById('stat-grid');
  grid.innerHTML = `
    <div class="stat-tile ${sistemasOcultos.has('SAE') ? 'oculto' : ''}">
      <div class="stat-label"><span class="dot" style="background:${COLOR_HEX.SAE}"></span>SAE · Vendidos</div>
      <div class="stat-value">${fmtNumero(totales.SAE.cantidad)}</div>
      <div class="stat-sub">${etiquetaMedida}</div>
    </div>
    <div class="stat-tile ${sistemasOcultos.has('SAE') ? 'oculto' : ''}">
      <div class="stat-label"><span class="dot" style="background:${COLOR_HEX.SAE}"></span>SAE · Valor vendido</div>
      <div class="stat-value" style="font-size:19px;">${fmtMoneda(totales.SAE.valor_total)}</div>
      <div class="stat-sub">acumulado</div>
    </div>
    <div class="stat-tile ${sistemasOcultos.has('FRV') ? 'oculto' : ''}">
      <div class="stat-label"><span class="dot" style="background:${COLOR_HEX.FRV}"></span>FRV · Vendidos</div>
      <div class="stat-value">${fmtNumero(totales.FRV.cantidad)}</div>
      <div class="stat-sub">bienes</div>
    </div>
    <div class="stat-tile ${sistemasOcultos.has('FRV') ? 'oculto' : ''}">
      <div class="stat-label"><span class="dot" style="background:${COLOR_HEX.FRV}"></span>FRV · Valor vendido</div>
      <div class="stat-value" style="font-size:19px;">${fmtMoneda(totales.FRV.valor_total)}</div>
      <div class="stat-sub">acumulado</div>
    </div>
  `;
}

function construirTabla(filasCrudas){
  const filas = filasAgrupadas(filasCrudas);
  const body = document.getElementById('tabla-body');
  body.innerHTML = filas
    .slice()
    .sort((a,b) => a.anio - b.anio || (a.mes||0) - (b.mes||0) || a.sistema.localeCompare(b.sistema))
    .map(f => {
      const color = f.sistema === 'SAE' ? 'var(--serie-sae)' : 'var(--serie-frv)';
      const medidaTexto = f.medida === 'total' ? 'Bienes (FRV)' : (f.medida === 'unidad' ? 'Unidades' : 'Folios');
      return `
      <tr>
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
  const filas = datosFiltrados();
  construirStatTiles(filas.length ? filas : datosCompletos.filter(f => !sistemasOcultos.has(f.sistema)));
  construirLeyenda(document.getElementById('legend-cantidad'));
  construirLeyenda(document.getElementById('legend-valor'));
  construirBarras(document.getElementById('chart-cantidad'), filas, 'cantidad', fmtNumero);
  construirBarras(document.getElementById('chart-valor'), filas, 'valor_total', fmtMoneda);
  construirDonut(filas);
  construirTabla(filas);
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
  document.getElementById('btn-toggle-tabla').textContent = visible ? 'Ver tabla' : 'Ocultar tabla';
});

document.getElementById('filtro-anio').addEventListener('change', (ev) => {
  anioFiltro = ev.target.value;
  renderizarTodo();
});

document.getElementById('filtro-mes').addEventListener('change', (ev) => {
  mesFiltro = ev.target.value;
  renderizarTodo();
});

document.getElementById('vista-toggle').addEventListener('click', (ev) => {
  const btn = ev.target.closest('.vista-btn');
  if (!btn) return;
  vista = btn.dataset.vista;
  document.querySelectorAll('#vista-toggle .vista-btn').forEach(b => b.classList.toggle('activo', b === btn));
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
