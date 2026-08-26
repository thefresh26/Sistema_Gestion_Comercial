/* ── BACKEND ──
   Este visor ya NO habla con Supabase directamente: todo pasa por
   nuestro propio backend Flask (/api/login, /api/buscar, /api/logout).
   Ni el ID del proyecto Supabase ni ninguna clave aparecen aquí. */

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

  /* Si ya hay sesión activa en el backend (cookie válida), entra directo. */
  try{
    const r = await fetch('/api/session');
    const s = await r.json();
    if(s.autenticado){
      document.getElementById('login-overlay').style.display = 'none';
      document.getElementById('hero-eyebrow').textContent = 'CONSULTA DE EXPRESIONES DE INTERÉS · SAE · 2026';
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

    document.getElementById('login-overlay').style.display = 'none';
    document.getElementById('hero-eyebrow').textContent = 'CONSULTA DE EXPRESIONES DE INTERÉS · SAE · 2026';
    iniciarControlInactividad();
  }catch(e){
    btn.disabled = false;
    btn.textContent = textoOriginal;
    err.style.display = 'block';
  }
}

document.getElementById('qi').addEventListener('keydown', e=>{ if(e.key==='Enter' && !e.shiftKey){ e.preventDefault(); buscar(); } });

function nul(v){ return v===null||v===undefined||v===''; }
function esc(v){ return String(v).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;'); }
function icon(path){ return `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2">${path}</svg>`; }
function fmtFmi(v){ return nul(v) ? '—' : String(v).trim().toUpperCase(); }

function dropdownInteres(total){
  total = total || 0;
  if(total<=0) return '<span class="chip ei-no">✕ Ninguna</span>';
  return `<span class="chip ei-yes">✓ ${total} interesado${total>1?'s':''}</span>`;
}

function parseFolios(q){
  return [...new Set(
    q.split(/[,/]+/).map(s=>s.trim()).filter(s=>s.length>0)
  )];
}

async function buscar(){
  const raw = document.getElementById('qi').value.trim();
  const sb = document.getElementById('sb');
  const res = document.getElementById('result');
  if(!raw) return;

  const folios = parseFolios(raw);
  if(folios.length===0) return;

  sb.style.display='block'; sb.className='loading';
  sb.textContent = `⏳ Consultando ${folios.length} folio${folios.length>1?'s':''}...`;
  res.style.display = 'none';

  try{
    const r = await fetch(`/api/sae/buscar?folios=${encodeURIComponent(folios.join(','))}`);
    if(r.status===401){
      location.reload();
      return;
    }
    if(!r.ok) throw new Error('HTTP '+r.status);
    const data = await r.json();

    const found = new Map((data||[]).map(row=>[String(row.fmi).toUpperCase(), row]));
    const noEncontrados = folios.filter(f=>!found.has(f.toUpperCase()));

    sb.style.display='none';
    res.style.display='block';

    const rows = folios.map(f=>{
      const r2 = found.get(f.toUpperCase());
      if(!r2){
        return `<tr class="row-empty">
          <td class="vm">${esc(f)}</td>
          <td colspan="3"><span class="null">⚠ No se encontró este folio en la base de datos</span></td>
        </tr>`;
      }
      const esUnidad = !nul(r2.codigo_subasta);
      const unidadHtml = esUnidad
        ? `<span class="chip cb">${esc(String(r2.codigo_subasta).trim().toUpperCase())}</span>`
        : '<span class="null">No aplica</span>';
      const enlaceHtml = nul(r2.enlace_inmueble)
        ? '<span class="null">No publicado</span>'
        : `<a class="map-link" href="${esc(r2.enlace_inmueble)}" target="_blank">${icon('<path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/><polyline points="15 3 21 3 21 9"/><line x1="10" y1="14" x2="21" y2="3"/>')} Ver inmueble</a>`;
      return `<tr>
        <td class="vm">${esc(fmtFmi(r2.fmi))}</td>
        <td>${unidadHtml}</td>
        <td>${enlaceHtml}</td>
        <td>${dropdownInteres(r2.interesados)}</td>
      </tr>`;
    }).join('');

    res.innerHTML = `
    <div class="top-card">
      <div class="tc-left">
        <div class="tc-label">Resultado de la consulta</div>
        <div class="fmi-num" style="font-size:16px">${folios.length} folio${folios.length>1?'s':''} consultado${folios.length>1?'s':''}</div>
        <div class="tc-sub">${found.size} encontrado${found.size!==1?'s':''}${noEncontrados.length?` &nbsp;·&nbsp; ${noEncontrados.length} sin resultado`:''}</div>
      </div>
    </div>
    <div class="sec">
      <table class="res-table">
        <thead>
          <tr>
            <th>Folio</th>
            <th>Unidad</th>
            <th>Enlace</th>
            <th>Expresión de Interés</th>
          </tr>
        </thead>
        <tbody>
          ${rows}
        </tbody>
      </table>
    </div>
    `;
  }catch(e){
    sb.style.display='block'; sb.className='error';
    sb.textContent='⚠ Error al consultar la base de datos. Verifica tu conexión e intenta de nuevo.';
  }
}
