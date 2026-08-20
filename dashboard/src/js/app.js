const COLOR_HEX = { SAE: '#1a5bbf', FRV: '#c77700' };

let datosCompletos = [];
const sistemasOcultos = new Set();   // sistemas apagados por clic en la leyenda
let anioFiltro = 'todos';            // 'todos' o un año específico

function fmtMoneda(n){
  return new Intl.NumberFormat('es-CO', { style:'currency', currency:'COP', maximumFractionDigits:0 }).format(n);
}
function fmtNumero(n){
  return new Intl.NumberFormat('es-CO').format(n);
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
    (anioFiltro === 'todos' || String(f.anio) === String(anioFiltro))
  );
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

function construirBarras(contenedor, filas, campo, formateador){
  contenedor.innerHTML = '';
  if (filas.length === 0){
    contenedor.innerHTML = '<p style="color:var(--muted);font-size:13px;">No hay datos para el filtro seleccionado.</p>';
    return;
  }
  const anios = [...new Set(filas.map(f => f.anio))].sort();
  const maxValor = Math.max(1, ...filas.map(f => f[campo]));

  anios.forEach(anio => {
    const grupo = document.createElement('div');
    grupo.className = 'chart-grupo-anio';

    const esHistorico = filas.some(f => f.anio === anio && f.es_acumulado_historico);
    const etiquetaAnio = esHistorico ? `${anio} (acumulado histórico FRV)` : String(anio);

    grupo.innerHTML = `<div class="anio-label">${etiquetaAnio}</div>`;

    ['SAE', 'FRV'].forEach(sistema => {
      const fila = filas.find(f => f.anio === anio && f.sistema === sistema);
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
      fill.addEventListener('mousemove', ev => mostrarTooltip(ev, `${sistema} · ${anio}: ${formateador(valor)}`));
      fill.addEventListener('mouseleave', ocultarTooltip);
      grupo.appendChild(filaEl);
    });

    contenedor.appendChild(grupo);
  });
}

function construirStatTiles(filas){
  const totales = { SAE: { cantidad:0, valor_total:0 }, FRV: { cantidad:0, valor_total:0 } };
  filas.forEach(f => {
    totales[f.sistema].cantidad += f.cantidad;
    totales[f.sistema].valor_total += Number(f.valor_total);
  });

  const grid = document.getElementById('stat-grid');
  grid.innerHTML = `
    <div class="stat-tile ${sistemasOcultos.has('SAE') ? 'oculto' : ''}">
      <div class="stat-label"><span class="dot" style="background:${COLOR_HEX.SAE}"></span>SAE · Vendidos</div>
      <div class="stat-value">${fmtNumero(totales.SAE.cantidad)}</div>
      <div class="stat-sub">folios / unidades</div>
    </div>
    <div class="stat-tile ${sistemasOcultos.has('SAE') ? 'oculto' : ''}">
      <div class="stat-label"><span class="dot" style="background:${COLOR_HEX.SAE}"></span>SAE · Valor vendido</div>
      <div class="stat-value" style="font-size:19px;">${fmtMoneda(totales.SAE.valor_total)}</div>
      <div class="stat-sub">acumulado</div>
    </div>
    <div class="stat-tile ${sistemasOcultos.has('FRV') ? 'oculto' : ''}">
      <div class="stat-label"><span class="dot" style="background:${COLOR_HEX.FRV}"></span>FRV · Vendidos</div>
      <div class="stat-value">${fmtNumero(totales.FRV.cantidad)}</div>
      <div class="stat-sub">folios / unidades</div>
    </div>
    <div class="stat-tile ${sistemasOcultos.has('FRV') ? 'oculto' : ''}">
      <div class="stat-label"><span class="dot" style="background:${COLOR_HEX.FRV}"></span>FRV · Valor vendido</div>
      <div class="stat-value" style="font-size:19px;">${fmtMoneda(totales.FRV.valor_total)}</div>
      <div class="stat-sub">acumulado</div>
    </div>
  `;
}

function construirTabla(filas){
  const body = document.getElementById('tabla-body');
  body.innerHTML = filas
    .slice()
    .sort((a,b) => a.anio - b.anio || a.sistema.localeCompare(b.sistema))
    .map(f => `
      <tr>
        <td>${f.sistema}</td>
        <td>${f.anio}${f.es_acumulado_historico ? ' (histórico)' : ''}</td>
        <td>${fmtNumero(f.cantidad)}</td>
        <td>${fmtMoneda(f.valor_total)}</td>
      </tr>
    `).join('');
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
  document.getElementById('btn-toggle-tabla').textContent = visible ? 'Ver como tabla' : 'Ver como gráfica';
});

document.getElementById('filtro-anio').addEventListener('change', (ev) => {
  anioFiltro = ev.target.value;
  renderizarTodo();
});

cargar();
