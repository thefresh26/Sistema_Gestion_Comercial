/* ── BACKEND ──
   Este visor ya NO habla con Supabase directamente: todo pasa por
   nuestro propio backend Flask (/api/login, /api/buscar, /api/logout). */

let currentRole = null;

/* ── CIERRE DE SESIÓN AUTOMÁTICO POR INACTIVIDAD ── */
const MINUTOS_INACTIVIDAD = 5;
let temporizadorInactividad = null;

function iniciarControlInactividad(){
  ['click','keydown','mousemove','scroll','touchstart'].forEach(ev=>{
    document.addEventListener(ev, reiniciarTemporizadorInactividad, {passive:true});
  });
  reiniciarTemporizadorInactividad();
}

function reiniciarTemporizadorInactividad(){
  if(temporizadorInactividad) clearTimeout(temporizadorInactividad);
  temporizadorInactividad = setTimeout(cerrarSesionPorInactividad, MINUTOS_INACTIVIDAD * 60 * 1000);
}

async function cerrarSesionPorInactividad(){
  try{
    await fetch('/api/logout', {
      method:'POST',
      headers:{'Content-Type':'application/json'},
      body: JSON.stringify({ motivo: `Sesión cerrada tras ${MINUTOS_INACTIVIDAD} min de inactividad` })
    });
  }catch(e){}
  // Esta vista vive dentro de un <iframe> del portal del sistema de gestión
  // comercial; avisamos al padre para que vuelva a la pantalla de login en
  // vez de solo recargar este iframe.
  if(window.parent && window.parent !== window){
    window.parent.postMessage({ tipo: 'sesion-cerrada' }, window.location.origin);
  } else {
    location.reload();
  }
}

document.addEventListener('DOMContentLoaded', async function(){
  document.getElementById('l-user').focus();
  ['l-user','l-pass'].forEach(id=>{
    document.getElementById(id).addEventListener('keydown', e=>{ if(e.key==='Enter') doLogin(); });
  });

  try{
    const r = await fetch('/api/session');
    const s = await r.json();
    if(s.autenticado){
      currentRole = s.role;
      document.getElementById('login-overlay').style.display = 'none';
      document.getElementById('hero-eyebrow').textContent =
        currentRole === 'broker' ? 'INTRANET BROKERS · 2026' : 'INTRANET COMERCIAL · 2026';
      iniciarControlInactividad();
    }
  }catch(e){}
});

async function doLogin(){
  const usuario = document.getElementById('l-user').value.trim();
  const pass = document.getElementById('l-pass').value;
  const err = document.getElementById('l-err');
  const btn = document.getElementById('l-btn');
  if(!usuario || !pass) return;

  btn.disabled = true;
  const textoOriginal = btn.textContent;
  btn.textContent = 'Ingresando...';

  try{
    const r = await fetch('/api/login', {
      method:'POST',
      headers:{'Content-Type':'application/json'},
      body: JSON.stringify({ usuario, password: pass })
    });

    btn.disabled = false;
    btn.textContent = textoOriginal;

    if(!r.ok){
      err.style.display = 'block';
      document.getElementById('l-pass').value = '';
      document.getElementById('l-pass').focus();
      return;
    }

    const data = await r.json();
    currentRole = data.role;
    document.getElementById('login-overlay').style.display = 'none';
    document.getElementById('hero-eyebrow').textContent =
      currentRole === 'broker' ? 'INTRANET BROKERS · 2026' : 'INTRANET COMERCIAL · 2026';
    iniciarControlInactividad();
  }catch(e){
    btn.disabled = false;
    btn.textContent = textoOriginal;
    err.style.display = 'block';
  }
}

document.getElementById('qi').addEventListener('keydown', e=>{ if(e.key==='Enter' && !e.shiftKey){ e.preventDefault(); buscar(); } });

function nul(v){return v===null||v===undefined||v==='';}
function fmt(v){if(nul(v))return '<span class="null">—</span>';return String(v);}
function fmtM(v){if(nul(v))return '<span class="null">—</span>';const x=parseFloat(v);if(isNaN(x)||x===0)return '<span class="null">—</span>';return '$ '+x.toLocaleString('es-CO',{maximumFractionDigits:0});}
function fmtA(v){if(nul(v))return '<span class="null">—</span>';const x=parseFloat(v);if(isNaN(x))return '<span class="null">—</span>';return x.toLocaleString('es-CO',{maximumFractionDigits:2})+' m²';}
function esc(v){ return String(v).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;'); }

// Igual que en SAE: separa por coma "," o diagonal "/", quita espacios y
// duplicados, para poder consultar varios FMI de una sola vez.
function parseFmis(q){
  return [...new Set(
    q.split(/[,/]+/).map(s=>s.trim()).filter(s=>s.length>0)
  )];
}

function icon(path){return `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2">${path}</svg>`;}

function chip(v,tipo){
  if(nul(v))return '<span class="null">—</span>';
  const u=String(v).toUpperCase();
  if(tipo==='disp') return u==='DISPONIBLE'?`<span class="chip cg">✓ ${v}</span>`:`<span class="chip cr">✕ ${v}</span>`;
  if(tipo==='ocup'){
    if(u==='DESOCUPADO')return`<span class="chip cg">● ${v}</span>`;
    if(u==='OCUPADO')return`<span class="chip cr">● ${v}</span>`;
    return`<span class="chip cy">● ${v}</span>`;
  }
  if(tipo==='fis'){
    if(u==='BUENO')return`<span class="chip cg">▲ ${v}</span>`;
    if(u==='REGULAR')return`<span class="chip cy">▲ ${v}</span>`;
    if(u==='MALO')return`<span class="chip cr">▼ ${v}</span>`;
    return`<span class="chip cgr">${v}</span>`;
  }
  if(tipo==='via')return u==='VIABLE'?`<span class="chip cg">✓ ${v}</span>`:`<span class="chip cgr">${v}</span>`;
  if(tipo==='inv'){
    if(u.includes('ENAJENAC'))return`<span class="chip cb">${v}</span>`;
    if(u.includes('DEVOLUC'))return`<span class="chip cr">${v}</span>`;
    return`<span class="chip cy">${v}</span>`;
  }
  if(tipo==='aval')return u==='VIGENTE'?'<span class="chip cg">✓ Vigente</span>':'<span class="chip cr">✕ Vencido</span>';
  if(tipo==='ok')return u==='OK'?'<span class="chip cg">✓ OK</span>':'<span class="chip cr">✕ NO</span>';
  return`<span class="chip cgr">${v}</span>`;
}

function evaluarEstadoLegal(r) {
  const legal = String(r.estado_legal || '').toUpperCase().trim();
  const enajenacionOK = String(r.bm_enajenacion_20 || '').toUpperCase() === 'OK';

  const esExtinto = legal.startsWith('EXTINTO');
  const esEnProceso = legal.startsWith('EN PROCESO');
  const esImprocedente = legal.includes('IMPROCEDENTE');

  let chipClase, chipTexto;
  if (esExtinto || esEnProceso) {
    chipClase = 'chip cg';
    chipTexto = '✓ ' + (r.estado_legal || '');
  } else if (esImprocedente) {
    chipClase = 'chip cr';
    chipTexto = '✕ ' + (r.estado_legal || '');
  } else {
    chipClase = 'chip cr';
    chipTexto = r.estado_legal ? '✕ ' + r.estado_legal : '—';
  }

  let enajenacionForzada;
  if (esExtinto) {
    enajenacionForzada = 'OK';
  } else if (esEnProceso) {
    enajenacionForzada = r.bm_enajenacion_20;
  } else {
    enajenacionForzada = 'NO';
  }

  const debeSupmar = (esExtinto && !enajenacionOK);
  const avanceBase = parseFloat(r.avance || 0);
  const avanceAjustado = debeSupmar ? Math.min(avanceBase + 0.20, 1.0) : avanceBase;

  return { chipClase, chipTexto, enajenacionForzada, avanceAjustado };
}

function semaforo(r){
  const ev = evaluarEstadoLegal(r);
  const pct = Math.round(ev.avanceAjustado * 100);

  let fillColor, textColor;
  if(pct>=70){fillColor='linear-gradient(90deg,#1ab87a,#2ed18e)';textColor='#138f5e';}
  else if(pct>=40){fillColor='linear-gradient(90deg,#f07b00,#f5a800)';textColor='#b85c00';}
  else{fillColor='linear-gradient(90deg,#c02020,#e03535)';textColor='#c02020';}

  const items=[
    {label:'Catastral',peso:'10%',val:r.bk_catastral_10},
    {label:'Avalúo Comercial',peso:'40%',val:r.bl_avaluo_40},
    {label:'Enajenación',peso:'20%',val:ev.enajenacionForzada},
    {label:'Viabilidad Jca.',peso:'30%',val:r.bn_viabilidad_30},
  ];
  return`
  <div class="sem-header">
    <div>
      <div class="sem-pct-big" style="color:${textColor}">${pct}<span style="font-size:18px;font-weight:600">%</span></div>
      <div class="sem-label-sub">Estado de Avance</div>
    </div>
    <div class="sem-bar-wrap">
      <div style="display:flex;justify-content:space-between;margin-bottom:6px;">
        <span style="font-size:10px;color:var(--muted);font-family:var(--sans);font-weight:600;">PROGRESO TOTAL</span>
        <span style="font-size:10px;color:var(--muted);font-family:var(--sans);">${pct}% completado</span>
      </div>
      <div class="sem-bar"><div class="sem-fill" style="width:${pct}%;background:${fillColor}"></div></div>
    </div>
  </div>
  <div class="sem-items">
    ${items.map(it=>{const ok=String(it.val||'').toUpperCase()==='OK';return`<div class="sem-item ${ok?'ok':'no'}">
      <label>${it.label}</label>
      <div class="sval">${ok?'✓ Cumple':'✕ No cumple'}</div>
      <div class="spct">Peso: ${it.peso}</div>
    </div>`;}).join('')}
  </div>`;
}

function stitleHtml(iconPath,label){
  return`<div class="stitle"><div class="stitle-icon">${icon(iconPath)}</div>${label}</div>`;
}

function renderPropiedadHtml(r){
  const vExists = !!r.viabilidad_existe;

  const mapLink=r.georeferenciado
    ?`<a class="map-link" href="${r.georeferenciado.replace('www.google.com/maps','earth.google.com/web')}" target="_blank">${icon('<path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z"/><circle cx="12" cy="10" r="3"/>')} Ver en Google Earth</a>`
    :'<span class="null">Sin georreferenciación</span>';

  const dispBadge=String(r.disponibilidad||'').toUpperCase()==='DISPONIBLE'
    ?'<span class="disp d-ok">✓ DISPONIBLE</span>'
    :'<span class="disp d-no">✕ NO DISPONIBLE</span>';

  return `
    <div class="top-card">
      <div class="tc-left">
        <div class="tc-label">Folio Matrícula Inmobiliaria</div>
        <div class="fmi-num">${esc(r.fmi)}</div>
        <div class="tc-sub">${fmt(r.clasificacion_activo)} &nbsp;·&nbsp; ${fmt(r.subtipo_activo)} &nbsp;·&nbsp; ${fmt(r.municipio)}, ${fmt(r.departamento)}</div>
      </div>
      <div class="tc-right">
        ${dispBadge}
        ${mapLink}
      </div>
    </div>
    <div class="sec">
      ${stitleHtml('<path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/><polyline points="9 22 9 12 15 12 15 22"/>','Ubicación del Inmueble')}
      <div class="g2">
        <div class="f"><label>Dirección</label><div class="v">${fmt(r.direccion)}</div></div>
        <div class="f"><label>Municipio / Departamento</label><div class="v">${fmt(r.municipio)}, ${fmt(r.departamento)}</div></div>
        <div class="f"><label>Estrato</label><div class="v vm">${fmt(r.estrato)}</div></div>
        <div class="f"><label>Razón Social</label><div class="v" style="font-size:11px">${fmt(r.razon_social)}</div></div>
      </div>
    </div>
    <div class="sec">
      ${stitleHtml('<rect x="2" y="3" width="20" height="14" rx="2"/><line x1="8" y1="21" x2="16" y2="21"/><line x1="12" y1="17" x2="12" y2="21"/>','Estado del Inmueble')}
      <div class="g3">
        <div class="f"><label>Disponibilidad</label><div class="v">${chip(r.disponibilidad,'disp')}</div></div>
        <div class="f"><label>Estado de Ocupación</label><div class="v">${chip(r.estado_ocupacion,'ocup')}</div></div>
        <div class="f"><label>Estado Físico</label><div class="v">${chip(r.estado_fisico,'fis')}</div></div>
        <div class="f"><label>Estado Legal</label><div class="v">${(()=>{
  const ev = evaluarEstadoLegal(r);
  return r.estado_legal ? `<span class="${ev.chipClase}">${ev.chipTexto}</span>` : '—';
})()}</div></div>
        <div class="f"><label>Estado Viabilidad</label><div class="v">${vExists?'<span class="chip cg">✓ Sí</span>':'<span class="chip cr">✕ No</span>'}</div></div>
      </div>
    </div>
    <div class="sec">
      ${stitleHtml('<polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/>','Estado de Avance — Semáforo de Viabilidad')}
      ${semaforo(r)}
    </div>
    <div class="sec">
      ${stitleHtml('<line x1="12" y1="1" x2="12" y2="23"/><path d="M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6"/>','Avalúos y Áreas')}
      <div class="g2">
        <div class="f"><label>Vigencia Catastral</label><div class="v vm">${fmt(r.vigencia_catastral)}</div></div>
        <div class="f"><label>Estado Avalúo</label><div class="v">${chip(r.estado_avaluo,'aval')}</div></div>
        <div class="f"><label>Avalúo Catastral</label><div class="v vm">${fmtM(r.avaluo_catastral)}</div></div>
        ${currentRole==='comercial'?`<div class="f"><label>Avalúo Comercial</label><div class="v vm">${fmtM(r.avaluo_comercial)}</div></div>`:''}
        <div class="f"><label>Fecha de Avalúo</label><div class="v vm">${fmt(r.fecha_avaluo)}</div></div>
        <div class="f"><label>Área Construida</label><div class="v vm">${fmtA(r.area_construida)}</div></div>
        <div class="f"><label>Área Terreno</label><div class="v vm">${fmtA(r.area_terreno)}</div></div>
      </div>
    </div>
    <div class="sec">
      ${stitleHtml('<circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/>','Enajenación y Proceso')}
      <div class="g2">
        <div class="f"><label>Causal</label><div class="v">${fmt(r.causal)}</div></div>
        <div class="f"><label>Enajenación</label><div class="v">${fmt(r.enajenacion)}</div></div>
        <div class="f"><label>Proceso Actual</label><div class="v" style="font-size:11px">${fmt(r.proceso)}</div></div>
      </div>
    </div>
    <div class="sec">
      ${stitleHtml('<path d="M20.59 13.41l-7.17 7.17a2 2 0 0 1-2.83 0L2 12V2h10l8.59 8.59a2 2 0 0 1 0 2.82z"/><line x1="7" y1="7" x2="7.01" y2="7"/>','Comercialización')}
      <div class="g2">
        <div class="f"><label>Estado Comercial</label><div class="v">${fmt(r.estado_comercial)}</div></div>
        <div class="f"><label>Estado de Publicación</label><div class="v">${fmt(r.estado_publicacion)}</div></div>
      </div>
    </div>
  `;
}

function renderNoEncontradoHtml(fmi){
  return `
    <div class="top-card">
      <div class="tc-left">
        <div class="tc-label">Folio Matrícula Inmobiliaria</div>
        <div class="fmi-num">${esc(fmi)}</div>
        <div class="tc-sub"><span class="null">⚠ No se encontró ningún inmueble con este FMI</span></div>
      </div>
    </div>
  `;
}

async function buscar(){
  const raw=document.getElementById('qi').value.trim();
  const sb=document.getElementById('sb');
  const res=document.getElementById('result');
  if(!raw)return;

  const fmis = parseFmis(raw);
  if(fmis.length===0) return;

  sb.style.display='block';sb.className='loading';
  sb.textContent = `⏳ Consultando ${fmis.length} FMI${fmis.length>1?'s':''}...`;
  res.style.display='none';
  try{
    const resp = await fetch(`/api/vista_inmuebles/buscar?fmi=${encodeURIComponent(fmis.join(','))}`);
    if(resp.status===401){ location.reload(); return; }
    if(!resp.ok) throw new Error('HTTP '+resp.status);
    const data = await resp.json();

    const encontrados = new Map((data||[]).map(r=>[String(r.fmi).toUpperCase(), r]));
    const noEncontrados = fmis.filter(f=>!encontrados.has(f.toUpperCase()));

    if(encontrados.size===0){
      sb.style.display='block';sb.className='empty';
      sb.textContent = fmis.length===1
        ? `⚠ No se encontró ningún inmueble con FMI "${fmis[0]}". Verifica el número e intenta de nuevo.`
        : `⚠ No se encontró ningún inmueble con los FMI consultados. Verifica los números e intenta de nuevo.`;
      return;
    }

    sb.style.display='none';
    res.style.display='block';

    // Con un solo FMI se ve exactamente igual que antes: la ficha completa
    // directo. Con varios, se apila una ficha completa por cada uno (en el
    // mismo orden en que se escribieron), con un resumen arriba.
    const resumenHtml = fmis.length>1 ? `
      <div class="top-card" style="margin-bottom:16px;">
        <div class="tc-left">
          <div class="tc-label">Resultado de la consulta</div>
          <div class="fmi-num" style="font-size:16px">${fmis.length} FMI consultados</div>
          <div class="tc-sub">${encontrados.size} encontrado${encontrados.size!==1?'s':''}${noEncontrados.length?` &nbsp;·&nbsp; ${noEncontrados.length} sin resultado`:''}</div>
        </div>
      </div>
    ` : '';

    const fichasHtml = fmis.map((f, i)=>{
      const r = encontrados.get(f.toUpperCase());
      const html = r ? renderPropiedadHtml(r) : renderNoEncontradoHtml(f);
      // Entrada escalonada breve cuando son varios FMI a la vez (tope de 8
      // fichas para que el retraso no se sienta lento con listas largas).
      const retraso = Math.min(i, 8) * 60;
      return `<div class="fila-in" style="animation-delay:${retraso}ms">${html}</div>`;
    }).join('<div style="height:24px"></div>');

    res.innerHTML = resumenHtml + fichasHtml;
  }catch(e){
    sb.style.display='block';sb.className='error';
    sb.textContent='⚠ Error al consultar la base de datos. Verifica tu conexión e intenta de nuevo.';
  }
}
