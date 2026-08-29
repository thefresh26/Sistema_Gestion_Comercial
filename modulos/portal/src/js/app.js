const TAB_LABELS = {
  inicio: 'Inicio',
  sae: 'Expresiones SAE',
  frv: 'Inmuebles FRV',
  vista_inmuebles: 'Inmuebles',
  dashboard: 'Estadísticas',
  admin: 'Permisos',
};

const TAB_DESCRIPCIONES = {
  sae: 'Consulta por folio (FMI): unidad, enlace del inmueble y expresión de interés.',
  frv: 'Consulta de bienes del Fondo de Reparación a las Víctimas.',
  vista_inmuebles: 'Consulta de inventario con semáforo de viabilidad, por folio (FMI).',
  dashboard: 'Folios y unidades vendidas en SAE y FRV, por año.',
  admin: 'Crear usuarios y asignar qué módulos puede ver cada uno.',
};

let sesionActual = null;

async function cargarSesion(){
  const r = await fetch('/api/session');
  const s = await r.json();
  sesionActual = s;
  if(s.autenticado){
    mostrarShell(s);
  }else{
    mostrarLogin();
  }
}

function mostrarLogin(){
  document.getElementById('login-screen').style.display = 'flex';
  document.getElementById('shell').style.display = 'none';
}

function mostrarShell(s){
  document.getElementById('login-screen').style.display = 'none';
  document.getElementById('shell').style.display = 'flex';
  document.getElementById('info-usuario').textContent = s.nombre || s.usuario || '—';
  document.getElementById('info-rol').textContent = s.role_legible || s.role || '—';

  construirTabs(s.modulos || {});
  activarTab('inicio');
}

function construirTabs(modulos){
  const cont = document.getElementById('tabs');
  cont.innerHTML = '';
  const cards = document.getElementById('inicio-cards');
  cards.innerHTML = '';

  // "Inicio" siempre visible.
  const tabsVisibles = ['inicio', ...Object.keys(TAB_LABELS).filter(k => k !== 'inicio' && modulos[k])];

  tabsVisibles.forEach(nombre=>{
    const btn = document.createElement('button');
    btn.className = 'tab-btn';
    btn.textContent = TAB_LABELS[nombre];
    btn.dataset.tab = nombre;
    btn.onclick = () => activarTab(nombre);
    cont.appendChild(btn);

    if(nombre !== 'inicio'){
      const card = document.createElement('div');
      card.className = 'modulo-card';
      card.onclick = () => activarTab(nombre);
      card.innerHTML = `<h3>${TAB_LABELS[nombre]}</h3><p>${TAB_DESCRIPCIONES[nombre] || ''}</p>`;
      cards.appendChild(card);
    }
  });
}

function activarTab(nombre){
  document.querySelectorAll('.tab-btn').forEach(b => b.classList.toggle('active', b.dataset.tab === nombre));
  document.querySelectorAll('.tab-panel').forEach(p => p.classList.toggle('active', p.dataset.tab === nombre));

  // Carga perezosa de los iframes: solo se pide el módulo la primera vez
  // que se abre su pestaña.
  if(nombre === 'sae'){
    const f = document.getElementById('frame-sae');
    if(!f.src) f.src = '/sae/';
  }
  if(nombre === 'frv'){
    const f = document.getElementById('frame-frv');
    if(!f.src) f.src = '/frv/';
  }
  if(nombre === 'vista_inmuebles'){
    const f = document.getElementById('frame-vista_inmuebles');
    if(!f.src) f.src = '/vista_inmuebles/';
  }
  if(nombre === 'dashboard'){
    const f = document.getElementById('frame-dashboard');
    if(!f.src) f.src = '/dashboard/';
  }
  if(nombre === 'admin'){
    const f = document.getElementById('frame-admin');
    if(!f.src) f.src = '/admin/';
  }
}

async function doLogin(){
  const usuario = document.getElementById('l-user').value.trim();
  const password = document.getElementById('l-pass').value;
  const err = document.getElementById('login-error');
  const btn = document.getElementById('l-btn');
  if(!usuario || !password) return;

  err.style.display = 'none';
  btn.disabled = true;
  const textoOriginal = btn.textContent;
  btn.textContent = 'Ingresando...';

  try{
    const r = await fetch('/api/login', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({ usuario, password }),
    });
    btn.disabled = false;
    btn.textContent = textoOriginal;

    if(!r.ok){
      err.style.display = 'block';
      document.getElementById('l-pass').value = '';
      document.getElementById('l-pass').focus();
      return;
    }
    await cargarSesion();
  }catch(e){
    btn.disabled = false;
    btn.textContent = textoOriginal;
    err.style.display = 'block';
  }
}

async function cerrarSesion(){
  try{
    await fetch('/api/logout', { method: 'POST', headers: {'Content-Type':'application/json'}, body: '{}' });
  }catch(e){}
  // Limpia los iframes para que la próxima sesión no arranque con datos
  // de la sesión anterior en memoria.
  limpiarFrames();
  mostrarLogin();
}

function limpiarFrames(){
  ['frame-sae', 'frame-frv', 'frame-vista_inmuebles', 'frame-dashboard', 'frame-admin'].forEach(id=>{
    const f = document.getElementById(id);
    if(f) f.src = '';
  });
}

// Los módulos SAE, FRV y Vista_Inmuebles corren dentro de un <iframe> y
// pueden cerrar la sesión por inactividad propia; cuando eso pasa, avisan
// al portal por postMessage para que toda la pantalla vuelva al login.
window.addEventListener('message', (ev)=>{
  if(ev.origin !== window.location.origin) return;
  if(ev.data && ev.data.tipo === 'sesion-cerrada'){
    limpiarFrames();
    mostrarLogin();
  }
});

['l-user','l-pass'].forEach(id=>{
  document.getElementById(id).addEventListener('keydown', e=>{ if(e.key==='Enter') doLogin(); });
});

cargarSesion();
