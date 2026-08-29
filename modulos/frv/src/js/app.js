let DATA = [];
let filtered = [];
let currentPage = 1;
let hayColumnaAvaluo = true;
const PAGE_SIZE = 50;

const state = { search:'', depto:'', etapa:'', foto:'', avalCat:'', avalCom:'', ext:'', anioAval:'' };

async function loadData(){
  try{
    const res = await fetch('data.json');
    DATA = await res.json();
    DATA = DATA.filter(d => (d['TIPO BIEN']||'').toUpperCase().startsWith('BIENES INMUEBLES'));
  }catch(e){
    document.getElementById('resultsCount').textContent = 'No se pudo cargar data.json — colócalo junto a este HTML.';
    return;
  }
  const primerPredio = DATA[0] || {};
  hayColumnaAvaluo = String(primerPredio['AÑO AVALÚO'] || '').trim() !== '';

  document.getElementById('thAvaluo').style.display = hayColumnaAvaluo ? '' : 'none';
  document.getElementById('filterAnioAval').style.display = hayColumnaAvaluo ? '' : 'none';
  document.getElementById('avalCatGroup').style.display = hayColumnaAvaluo ? '' : 'none';
  document.getElementById('avalComGroup').style.display = hayColumnaAvaluo ? '' : 'none';
  document.getElementById('statAvalGroup').style.display = hayColumnaAvaluo ? '' : 'none';
  document.getElementById('brandSub').textContent = hayColumnaAvaluo
    ? 'Registro de inventario · fotografías · avalúos'
    : 'Registro de inventario · fotografías';

  populateFilters();
  computeStats();
  applyFilters();
}

function populateFilters(){
  const deptos = [...new Set(DATA.map(d=>d['DEPARTAMENTO']).filter(Boolean))].sort();
  const etapas = [...new Set(DATA.map(d=>d['ETAPA GESTIÓN']).filter(Boolean))].sort();

  const selD = document.getElementById('filterDepto');
  deptos.forEach(d=>{
    const o = document.createElement('option');
    o.value = d; o.textContent = d;
    selD.appendChild(o);
  });

  const selE = document.getElementById('filterEtapa');
  etapas.forEach(e=>{
    const o = document.createElement('option');
    o.value = e; o.textContent = e.charAt(0)+e.slice(1).toLowerCase();
    selE.appendChild(o);
  });

  const anios = [...new Set(DATA.map(d=>parseInt(d['AÑO AVALÚO'], 10)).filter(a=>a>2000))].sort((a,b)=>b-a);
  const selA = document.getElementById('filterAnioAval');
  anios.forEach(a=>{
    const o = document.createElement('option');
    o.value = a; o.textContent = a;
    selA.appendChild(o);
  });
}

function computeStats(){
  document.getElementById('stat-total').textContent = DATA.length.toLocaleString('es-CO');
  const foto = DATA.filter(tieneFotoValida).length;
  const aval = DATA.filter(tieneAvaluoValido).length;
  document.getElementById('stat-foto').textContent = foto.toLocaleString('es-CO');
  document.getElementById('stat-aval').textContent = aval.toLocaleString('es-CO');
}

function isYes(v){ return (v||'').toString().trim().toUpperCase().startsWith('S'); }

function tieneAvaluoValido(d){
  const anio = parseInt(d['AÑO AVALÚO'], 10);
  return Number.isInteger(anio) && anio > 2000;
}

function tieneAvaluoComercialValido(d){
  const anio = parseInt(d['AÑO AVALÚO COMERCIAL'], 10);
  return Number.isInteger(anio) && anio > 2000;
}

function tieneFotoValida(d){
  return (parseInt(d['CANT_FOTOS_LOCAL'], 10) || 0) > 0;
}

function extintoLabel(v){
  const val = (v||'').toString().trim().toUpperCase();
  if(val === 'SI') return `<span style="color:var(--ok);font-weight:600">Sí</span>`;
  if(val === 'NO') return `<span style="color:var(--no);font-weight:600">No</span>`;
  return '';
}

function parseHa(v){
  const s = (v||'').toString().trim();
  if(s === '' || s === '—') return null;
  const n = parseFloat(s.replace(',', '.'));
  return isNaN(n) ? null : n;
}

function applyFilters(){
  const q = state.search.trim().toLowerCase();
  filtered = DATA.filter(d=>{
    if(q){
      const hay = (d['FMI']+' '+d['CÓDIGO FRV']+' '+d['NOMBRE BIEN']+' '+d['POSTULADO']).toLowerCase();
      if(!hay.includes(q)) return false;
    }
    if(state.depto && d['DEPARTAMENTO'] !== state.depto) return false;
    if(state.etapa && d['ETAPA GESTIÓN'] !== state.etapa) return false;
    if(state.foto === 'si' && !tieneFotoValida(d)) return false;
    if(state.foto === 'no' && tieneFotoValida(d)) return false;
    if(state.avalCat === 'si' && !tieneAvaluoValido(d)) return false;
    if(state.avalCat === 'no' && tieneAvaluoValido(d)) return false;
    if(state.avalCom === 'si' && !tieneAvaluoComercialValido(d)) return false;
    if(state.avalCom === 'no' && tieneAvaluoComercialValido(d)) return false;
    const esExtinto = (d['EXTINCIÓN DOMINIO']||'').toString().trim().toUpperCase() === 'SI';
    if(state.ext === 'si' && !esExtinto) return false;
    if(state.ext === 'no' && esExtinto) return false;
    if(state.anioAval && String(parseInt(d['AÑO AVALÚO'], 10)) !== state.anioAval) return false;
    return true;
  });

  currentPage = 1;
  render();
}

function etapaClass(etapa){
  return 'etapa-' + (etapa||'').replace(/\s+/g,'_');
}

function fmtMoney(v){
  if(!v) return '—';
  const s = v.toString().replace('$','').trim();
  return s ? '$ '+s : '—';
}

function isMobile(){ return window.innerWidth < 760; }

function render(){
  const tbody = document.getElementById('tableBody');
  const empty = document.getElementById('emptyState');
  const tableWrap = document.querySelector('.table-wrap');
  const cardsContainer = document.getElementById('cardsContainer');
  const total = filtered.length;
  const start = (currentPage-1)*PAGE_SIZE;
  const pageItems = filtered.slice(start, start+PAGE_SIZE);

  document.getElementById('resultsCount').innerHTML =
    `<b>${total.toLocaleString('es-CO')}</b> predios encontrados`;

  if(total === 0){
    tbody.innerHTML = '';
    cardsContainer.innerHTML = '';
    empty.style.display = 'block';
    document.getElementById('pagination').innerHTML = '';
    return;
  }
  empty.style.display = 'none';

  if(isMobile()){
    tableWrap.style.display = 'none';
    cardsContainer.style.display = 'flex';
    tbody.innerHTML = '';
    cardsContainer.innerHTML = pageItems.map((d, i)=>{
      const idx = DATA.indexOf(d);
      const foto = tieneFotoValida(d);
      const aval = tieneAvaluoValido(d);
      const tipo = (d['TIPO BIEN']||'').split(' - ').slice(1).join(' · ');
      const ubicacion = [d['MUNICIPIO'], d['DEPARTAMENTO']].filter(Boolean).join(', ');
      // Entrada escalonada breve (tope de 12 tarjetas visibles a la vez).
      const retraso = Math.min(i, 12) * 30;
      return `
      <div class="predio-card fila-in" style="animation-delay:${retraso}ms" onclick="openModal(${idx})">
        <div class="card-top">
          <div class="card-top-left">
            <div class="card-codigo">${d['CÓDIGO FRV']||'—'}</div>
            <div class="card-nombre">${d['NOMBRE BIEN']||'Sin nombre'}</div>
            ${tipo ? `<div class="card-tipo">${tipo}</div>` : ''}
          </div>
          <span class="card-chevron">›</span>
        </div>
        <div class="card-meta-row">
          <span>FMI&nbsp;<b>${d['FMI']||'—'}</b></span>
          ${ubicacion ? `<span>📍 ${ubicacion}</span>` : ''}
        </div>
        <div class="card-badges-row">
          <span class="etapa-pill ${etapaClass(d['ETAPA GESTIÓN'])}">${d['ETAPA GESTIÓN']||'—'}</span>
          ${foto
            ? `<span class="badge si"><span class="dot"></span>Foto&nbsp;·&nbsp;${d['CANT_FOTOS_LOCAL']||0}</span>`
            : `<span class="badge no"><span class="dot"></span>Sin foto</span>`}
          ${aval
            ? `<span class="badge si"><span class="dot"></span>Avalúo&nbsp;${d['AÑO AVALÚO']||''}</span>`
            : `<span class="badge no"><span class="dot"></span>Sin avalúo</span>`}
          ${aval && d['VALOR AVALÚO'] ? `<span class="card-valor">${fmtMoney(d['VALOR AVALÚO'])}</span>` : ''}
        </div>
      </div>`;
    }).join('');
  } else {
    tableWrap.style.display = '';
    cardsContainer.style.display = 'none';
    cardsContainer.innerHTML = '';
    tbody.innerHTML = pageItems.map((d, i)=>{
      const idx = DATA.indexOf(d);
      const cantFotosLocal = parseInt(d['CANT_FOTOS_LOCAL'], 10) || 0;
      const foto = cantFotosLocal > 0;
      const aval = tieneAvaluoValido(d);
      let anioAvaluoLabel = 'Sí';
      if(d['AÑO AVALÚO']){
        const anio = parseInt(d['AÑO AVALÚO'], 10);
        anioAvaluoLabel = (Number.isInteger(anio) && anio >= 2000) ? anio : '—';
      }
      // Entrada escalonada breve (tope de 12 filas visibles a la vez).
      const retraso = Math.min(i, 12) * 30;
      return `
      <tr class="fila-in" style="animation-delay:${retraso}ms" onclick="openModal(${idx})">
        <td class="td-codigo">${d['CÓDIGO FRV']||'—'}</td>
        <td class="td-nombre">${d['NOMBRE BIEN']||'Sin nombre'}<span class="sub">${(d['TIPO BIEN']||'').split(' - ').slice(1).join(' · ')}</span></td>
        <td class="td-fmi">${d['FMI']||'—'}</td>
        <td>${d['MUNICIPIO']||'—'}<span class="sub" style="display:block;font-size:10.5px;color:var(--ink-soft)">${d['DEPARTAMENTO']||''}</span></td>
        <td><span class="etapa-pill ${etapaClass(d['ETAPA GESTIÓN'])}">${d['ETAPA GESTIÓN']||'—'}</span></td>
        <td>${extintoLabel(d['EXTINCIÓN DOMINIO'])}</td>
        <td>${d['ÁREA HA CATASTRO']||'—'}</td>
        <td>${foto ? `<span class="badge si"><span class="dot"></span>Sí · ${cantFotosLocal}</span>` : `<span class="badge no"><span class="dot"></span>No</span>`}</td>
        ${hayColumnaAvaluo ? `<td>${aval ? `<span class="badge si"><span class="dot"></span>${anioAvaluoLabel}</span>` : `<span class="badge no"><span class="dot"></span>No</span>`}</td>` : ''}
      </tr>`;
    }).join('');
  }

  renderPagination(total);
}

function renderPagination(total){
  const pages = Math.ceil(total/PAGE_SIZE);
  const pag = document.getElementById('pagination');
  if(pages <= 1){ pag.innerHTML=''; return; }

  let html = `<button class="page-btn" onclick="goPage(${currentPage-1})" ${currentPage===1?'disabled':''}>‹ Anterior</button>`;

  let pagesToShow = [];
  for(let p=1; p<=pages; p++){
    if(p===1 || p===pages || Math.abs(p-currentPage)<=2) pagesToShow.push(p);
  }
  let prev = 0;
  pagesToShow.forEach(p=>{
    if(prev && p - prev > 1) html += `<span style="padding:0 4px;color:var(--ink-soft)">…</span>`;
    html += `<button class="page-btn ${p===currentPage?'current':''}" onclick="goPage(${p})">${p}</button>`;
    prev = p;
  });

  html += `<button class="page-btn" onclick="goPage(${currentPage+1})" ${currentPage===pages?'disabled':''}>Siguiente ›</button>`;
  pag.innerHTML = html;
}

function goPage(p){
  currentPage = p;
  render();
  window.scrollTo({top:0, behavior:'smooth'});
}

function buildSharepointUrl(nombreCarpeta){
  const base = 'https://activosporcolombia.sharepoint.com/sites/ActiBOX-FVR/FOTOS%20%20FRV/Forms/AllItems.aspx';
  const idPath = `/sites/ActiBOX-FVR/FOTOS  FRV/${nombreCarpeta}`;
  return `${base}?id=${encodeURI(idPath)}&p=true&ga=1`;
}

function openModal(idx){
  const d = DATA[idx];
  document.getElementById('modalCodigo').textContent = d['CÓDIGO FRV'] || ('Código '+d['CÓDIGO']);
  document.getElementById('modalNombre').textContent = d['NOMBRE BIEN'] || 'Sin nombre registrado';

  const nombreCarpeta = (d['FMI'] || d['CÓDIGO FRV'] || '').trim();
  const sharepointActions = document.getElementById('mSharepointActions');
  if(nombreCarpeta){
    sharepointActions.style.display = '';
    document.getElementById('mSharepointLink').href = buildSharepointUrl(nombreCarpeta);
  }else{
    sharepointActions.style.display = 'none';
  }

  document.getElementById('mFmi').textContent = d['FMI'] || 'No aplica';
  document.getElementById('mDepto').textContent = d['DEPARTAMENTO'] || '—';
  document.getElementById('mMuni').textContent = d['MUNICIPIO'] || '—';
  document.getElementById('mEtapa').textContent = d['ETAPA GESTIÓN'] || '—';
  document.getElementById('mSistema').textContent = d['SISTEMA ADMON'] || 'No definido';
  document.getElementById('mExtincion').textContent = (d['EXTINCIÓN DOMINIO']||'').toUpperCase()==='SI' ? 'Sí' : 'No';

  const tieneValor = v => v !== undefined && v !== null && String(v).trim() !== '';

  const tieneDatosAvaluo = [
    d['VALOR AVALÚO'], d['AÑO AVALÚO'], d['TIPO AVALÚO'], d['FECHA AVALÚO'],
    d['VALOR AVALÚO COMERCIAL'], d['AÑO AVALÚO COMERCIAL'], d['FECHA AVALÚO COMERCIAL']
  ].some(tieneValor);

  document.getElementById('avaluoTitle').style.display = tieneDatosAvaluo ? '' : 'none';
  document.getElementById('avaluoGrid').style.display = tieneDatosAvaluo ? '' : 'none';

  if(tieneDatosAvaluo){
    document.getElementById('mValorAvaluo').textContent = fmtMoney(d['VALOR AVALÚO']);
    document.getElementById('mConAvaluoComerc').textContent = d['CON AVALÚO COMERC.'] || '—';
    document.getElementById('mAnioAvaluo').textContent = d['AÑO AVALÚO'] || '—';
    document.getElementById('mTipoAvaluo').textContent = d['TIPO AVALÚO'] || '—';
    document.getElementById('mFechaAvaluo').textContent = d['FECHA AVALÚO'] || '—';

    document.getElementById('mValorAvaluoComercialField').style.display = tieneValor(d['VALOR AVALÚO COMERCIAL']) ? '' : 'none';
    document.getElementById('mValorAvaluoComercial').textContent = fmtMoney(d['VALOR AVALÚO COMERCIAL']);

    document.getElementById('mAnioAvaluoComercialField').style.display = tieneValor(d['AÑO AVALÚO COMERCIAL']) ? '' : 'none';
    document.getElementById('mAnioAvaluoComercial').textContent = d['AÑO AVALÚO COMERCIAL'] || '—';

    document.getElementById('mFechaAvaluoComercialField').style.display = tieneValor(d['FECHA AVALÚO COMERCIAL']) ? '' : 'none';
    document.getElementById('mFechaAvaluoComercial').textContent = d['FECHA AVALÚO COMERCIAL'] || '—';
  }

  document.getElementById('mAreaHaCatastro').textContent = d['ÁREA HA CATASTRO'] || '—';
  document.getElementById('mAreaHaEscritura').textContent = d['ÁREA HA ESCRITURA'] || '—';
  document.getElementById('mAreaHaMatricula').textContent = d['ÁREA HA MATRÍCULA'] || '—';
  document.getElementById('mAreaM2Catastro').textContent = d['ÁREA M2 CATASTRO'] || '—';
  document.getElementById('mAreaM2Escritura').textContent = d['ÁREA M2 ESCRITURA'] || '—';
  document.getElementById('mAreaM2Matricula').textContent = d['ÁREA M2 MATRÍCULA'] || '—';
  document.getElementById('mAreaConstruida').textContent = d['ÁREA CONSTRUIDA'] || '—';
  document.getElementById('mEstadoFolio').textContent = d['ESTADO FOLIO'] || '—';
  document.getElementById('mEstadoActualBien').textContent = d['ESTADO ACTUAL BIEN'] || '—';
  document.getElementById('mFechaApertura').textContent = d['FECHA APERTURA'] || '—';
  document.getElementById('mFechaInspecc').textContent = d['FECHA INSPECC.'] || '—';
  document.getElementById('mNCatastral').textContent = d['N° CATASTRAL'] || '—';

  document.getElementById('modalOverlay').classList.add('open');
}

document.getElementById('modalClose').onclick = ()=> document.getElementById('modalOverlay').classList.remove('open');
document.getElementById('modalOverlay').onclick = (e)=>{ if(e.target.id==='modalOverlay') e.currentTarget.classList.remove('open'); };

// Eventos
document.getElementById('searchInput').addEventListener('input', e=>{
  state.search = e.target.value;
  applyFilters();
});
document.getElementById('filterDepto').addEventListener('change', e=>{
  state.depto = e.target.value;
  applyFilters();
});
document.getElementById('filterEtapa').addEventListener('change', e=>{
  state.etapa = e.target.value;
  applyFilters();
});
document.getElementById('filterAnioAval').addEventListener('change', e=>{
  state.anioAval = e.target.value;
  applyFilters();
});
document.querySelectorAll('.toggle-btn').forEach(btn=>{
  btn.addEventListener('click', ()=>{
    const filter = btn.dataset.filter;
    const group = document.querySelectorAll(`.toggle-btn.${filter}`);
    // cycle: '' -> 'si' -> 'no' -> ''
    const cur = state[filter];
    const next = cur === '' ? 'si' : cur === 'si' ? 'no' : '';
    state[filter] = next;
    btn.classList.toggle('active', next !== '');
    btn.textContent = filter === 'foto'
      ? (next==='' ? 'Foto: todos' : next==='si' ? 'Foto: sí ✓' : 'Foto: no ✕')
      : filter === 'avalCat'
      ? (next==='' ? 'Aval. Catastral: todos' : next==='si' ? 'Aval. Catastral: sí ✓' : 'Aval. Catastral: no ✕')
      : filter === 'avalCom'
      ? (next==='' ? 'Aval. Comercial: todos' : next==='si' ? 'Aval. Comercial: sí ✓' : 'Aval. Comercial: no ✕')
      : (next==='' ? 'Extinto: todos' : next==='si' ? 'Extinto: sí ✓' : 'Extinto: no ✕');
    applyFilters();
  });
});

document.getElementById('clearBtn').addEventListener('click', ()=>{
  state.search=''; state.depto=''; state.etapa=''; state.foto=''; state.avalCat=''; state.avalCom=''; state.ext=''; state.anioAval='';
  document.getElementById('searchInput').value='';
  document.getElementById('filterDepto').value='';
  document.getElementById('filterEtapa').value='';
  document.getElementById('filterAnioAval').value='';
  document.querySelectorAll('.toggle-btn').forEach(b=>{
    b.classList.remove('active');
    b.textContent = b.classList.contains('foto') ? 'Foto: todos'
      : b.classList.contains('avalCat') ? 'Aval. Catastral: todos'
      : b.classList.contains('avalCom') ? 'Aval. Comercial: todos'
      : 'Extinto: todos';
  });
  applyFilters();
});

document.getElementById('lastUpdate').textContent = 'Actualizado: ' + new Date().toLocaleDateString('es-CO', {day:'2-digit',month:'long',year:'numeric'});

let _resizeTick;
window.addEventListener('resize', ()=>{
  clearTimeout(_resizeTick);
  _resizeTick = setTimeout(render, 120);
});

loadData();

/* Cierre de sesión automático por inactividad (10 min), igual que en
   los visores de SAE. Cualquier click/tecla/scroll reinicia el reloj. */
async function cerrarSesionFRV(motivo){
  try{
    await fetch('/api/logout', {
      method:'POST',
      headers:{'Content-Type':'application/json'},
      body: JSON.stringify({ motivo: motivo || null })
    });
  }catch(e){}
  // Este visor vive dentro de un <iframe> del portal; le pedimos al
  // padre que vuelva a la pantalla de login en vez de recargar solo el iframe.
  if(window.parent && window.parent !== window){
    window.parent.postMessage({ tipo: 'sesion-cerrada' }, window.location.origin);
  } else {
    window.location.href = '/';
  }
}

(function(){
  var MINUTOS_INACTIVIDAD = 5;
  var t = null;
  function reiniciar(){
    if(t) clearTimeout(t);
    t = setTimeout(function(){ cerrarSesionFRV('inactividad'); }, MINUTOS_INACTIVIDAD * 60 * 1000);
  }
  ['click','keydown','mousemove','scroll','touchstart'].forEach(function(ev){
    document.addEventListener(ev, reiniciar, {passive:true});
  });
  reiniciar();
})();
