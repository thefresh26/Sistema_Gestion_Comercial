let usuarios = [];
let roles = {};
let modulosLegibles = {};
let matriz = {};
let directorioM365 = {}; // correo (minúsculas) -> nombre, desde Microsoft 365
let usuarioEnEdicion = null; // para el modal de restablecer contraseña

function mostrarToast(mensaje, esError){
  const t = document.getElementById('toast');
  t.textContent = mensaje;
  t.classList.toggle('error', !!esError);
  t.classList.add('visible');
  clearTimeout(mostrarToast._t);
  mostrarToast._t = setTimeout(() => t.classList.remove('visible'), 3200);
}

function fmtFecha(iso){
  if(!iso) return 'Nunca';
  const d = new Date(iso);
  if(isNaN(d)) return '—';
  return d.toLocaleString('es-CO', { day:'2-digit', month:'short', year:'numeric', hour:'2-digit', minute:'2-digit' });
}

async function cargarUsuarios(sincronizarAutomatico){
  if(sincronizarAutomatico === undefined) sincronizarAutomatico = true;
  document.getElementById('estado-carga').style.display = 'block';
  document.getElementById('estado-error').style.display = 'none';
  document.getElementById('contenido').style.display = 'none';
  try{
    const r = await fetch('/api/admin/usuarios');
    if(!r.ok){
      const cuerpo = await r.json().catch(() => ({}));
      throw new Error(cuerpo.error || 'No se pudo cargar la lista de usuarios.');
    }
    const data = await r.json();
    usuarios = data.usuarios || [];
    roles = data.roles || {};
    modulosLegibles = data.modulos || {};
    matriz = data.matriz || {};

    construirReferenciaRoles();
    construirSelectRoles(document.getElementById('nu-rol'));
    construirTablaUsuarios();

    document.getElementById('estado-carga').style.display = 'none';
    document.getElementById('contenido').style.display = 'block';

    await cargarDirectorioM365();

    // Si algún usuario todavía no tiene nombre pero ya hay una coincidencia
    // en el directorio de Microsoft 365, se copia sola — sin que nadie
    // tenga que hacer clic en nada. Solo se intenta una vez por carga para
    // no quedar en un ciclo.
    if(sincronizarAutomatico){
      const hayPendientes = usuarios.some(u => !u.nombre && u.sugerencia_nombre);
      if(hayPendientes){
        await sincronizarNombresM365({ silencioso: true });
        await cargarUsuarios(false);
      }
    }
  }catch(e){
    document.getElementById('estado-carga').style.display = 'none';
    const err = document.getElementById('estado-error');
    err.textContent = e.message || 'Ocurrió un error inesperado.';
    err.style.display = 'block';
  }
}

function construirReferenciaRoles(){
  const grid = document.getElementById('ref-grid');
  const nombresModulo = Object.keys(modulosLegibles);
  grid.innerHTML = Object.keys(roles).map(rol => {
    const filas = nombresModulo.map(mod => {
      const puede = (matriz[mod] || []).includes(rol);
      return `<div class="ref-modulo ${puede ? 'si-ve' : 'no-ve'}"><span class="chk">${puede ? '✓' : '—'}</span> ${modulosLegibles[mod]}</div>`;
    }).join('');
    return `
      <div class="ref-tile">
        <div class="ref-rol">${roles[rol]}</div>
        <div class="ref-modulos">${filas || '<div class="ref-modulo no-ve"><span class="chk">—</span> Ningún módulo</div>'}</div>
      </div>
    `;
  }).join('');
}

function construirSelectRoles(select, valorActual){
  select.innerHTML = Object.keys(roles)
    .map(r => `<option value="${r}" ${r === valorActual ? 'selected' : ''}>${roles[r]}</option>`)
    .join('');
}

function construirTablaUsuarios(){
  document.getElementById('conteo-usuarios').textContent = `${usuarios.length} usuario${usuarios.length === 1 ? '' : 's'}`;
  const body = document.getElementById('tabla-usuarios-body');
  body.innerHTML = usuarios.map((u, i) => {
    const selectId = `rol-${u.id}`;
    // Si todavía no tiene nombre guardado pero ya hay coincidencia en el
    // directorio de Microsoft 365, se muestra de una vez: el nombre real
    // ya se está guardando solo en segundo plano (ver cargarUsuarios).
    const nombreMostrado = u.nombre || u.sugerencia_nombre || u.usuario;
    // Entrada escalonada breve (tope de 15 filas visibles a la vez).
    const retraso = Math.min(i, 15) * 25;
    return `
      <tr class="fila-in ${u.deshabilitado ? 'fila-deshabilitada' : ''}" style="animation-delay:${retraso}ms">
        <td>
          <div class="usuario-celda">
            <span class="usuario-nombre">${nombreMostrado}${u.es_yo ? '<span class="usuario-tu">Tú</span>' : ''}</span>
            <span class="usuario-email">${u.usuario}${u.usuario !== u.email ? ' · ' + u.email : ''}</span>
          </div>
        </td>
        <td>
          <select class="rol-select" id="${selectId}" data-id="${u.id}" ${u.es_yo ? 'disabled title="No puedes cambiar tu propio rol"' : ''}></select>
        </td>
        <td><span class="badge-estado ${u.deshabilitado ? 'inactivo' : 'activo'}">${u.deshabilitado ? 'Deshabilitado' : 'Activo'}</span></td>
        <td>${fmtFecha(u.ultimo_ingreso)}</td>
        <td>
          <div class="acciones">
            <button class="btn-accion" data-accion="editar" data-id="${u.id}" data-nombre="${nombreMostrado}" ${u.es_yo ? 'disabled title="No puedes editar tu propio usuario"' : ''}>Editar</button>
            ${u.deshabilitado
              ? `<button class="btn-accion exito" data-accion="habilitar" data-id="${u.id}" ${u.es_yo ? 'disabled' : ''}>Habilitar</button>`
              : `<button class="btn-accion peligro" data-accion="deshabilitar" data-id="${u.id}" ${u.es_yo ? 'disabled' : ''}>Deshabilitar</button>`
            }
          </div>
        </td>
      </tr>
    `;
  }).join('');

  // Los <select> se llenan aparte (no se puede meter el <option selected>
  // limpio dentro del template de arriba sin duplicar la lista de roles).
  usuarios.forEach(u => {
    const sel = document.getElementById(`rol-${u.id}`);
    if(sel) construirSelectRoles(sel, u.rol);
  });

  body.querySelectorAll('.rol-select').forEach(sel => {
    sel.addEventListener('change', () => cambiarRol(sel.dataset.id, sel.value));
  });
  body.querySelectorAll('.btn-accion').forEach(btn => {
    btn.addEventListener('click', () => {
      const accion = btn.dataset.accion;
      if(accion === 'editar') abrirModalClave(btn.dataset.id, btn.dataset.nombre);
      if(accion === 'deshabilitar') cambiarEstado(btn.dataset.id, true);
      if(accion === 'habilitar') cambiarEstado(btn.dataset.id, false);
    });
  });
}

// ── Directorio de Microsoft 365 (autocompletar / sincronizar nombres) ───

async function cargarDirectorioM365(){
  try{
    const r = await fetch('/api/admin/directorio');
    if(!r.ok) return; // no es crítico: el panel sigue funcionando sin esto
    directorioM365 = await r.json();
  }catch(e){
    directorioM365 = {};
  }
}

async function sincronizarNombresM365(opts){
  opts = opts || {};
  const silencioso = !!opts.silencioso;
  const btn = document.getElementById('btn-sincronizar-nombres');
  const textoOriginal = btn.textContent;
  if(!silencioso){
    btn.disabled = true;
    btn.textContent = 'Copiando…';
  }
  try{
    const r = await fetch('/api/admin/usuarios/sincronizar-nombres', { method: 'POST' });
    const cuerpo = await r.json().catch(() => ({}));
    if(!r.ok) throw new Error(cuerpo.error || 'No se pudo sincronizar con Microsoft 365.');
    const n = (cuerpo.actualizados || []).length;
    if(!silencioso){
      mostrarToast(n > 0 ? `${n} nombre${n === 1 ? '' : 's'} copiado${n === 1 ? '' : 's'} desde Microsoft 365.` : 'No había nombres nuevos para copiar.');
      await cargarUsuarios(false);
    }else if(n > 0){
      // Se hizo solo, al abrir el panel — no hacía falta que nadie le diera clic.
      mostrarToast(`${n} nombre${n === 1 ? '' : 's'} completado${n === 1 ? '' : 's'} automáticamente desde Microsoft 365.`);
    }
  }catch(e){
    if(!silencioso) mostrarToast(e.message, true);
  }finally{
    if(!silencioso){
      btn.disabled = false;
      btn.textContent = textoOriginal;
    }
  }
}

async function cambiarRol(id, rol){
  try{
    const r = await fetch(`/api/admin/usuarios/${id}`, {
      method: 'PATCH',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({ rol }),
    });
    const cuerpo = await r.json().catch(() => ({}));
    if(!r.ok) throw new Error(cuerpo.error || 'No se pudo cambiar el rol.');
    mostrarToast('Rol actualizado.');
    await cargarUsuarios();
  }catch(e){
    mostrarToast(e.message, true);
    await cargarUsuarios();
  }
}

async function cambiarEstado(id, deshabilitado){
  const usuario = usuarios.find(u => u.id === id);
  if(deshabilitado){
    const ok = confirm(`¿Deshabilitar a "${usuario ? usuario.usuario : ''}"? No podrá volver a iniciar sesión hasta que lo habilites de nuevo.`);
    if(!ok) return;
  }
  try{
    const r = await fetch(`/api/admin/usuarios/${id}`, {
      method: 'PATCH',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({ deshabilitado }),
    });
    const cuerpo = await r.json().catch(() => ({}));
    if(!r.ok) throw new Error(cuerpo.error || 'No se pudo actualizar el estado.');
    mostrarToast(deshabilitado ? 'Usuario deshabilitado.' : 'Usuario habilitado.');
    await cargarUsuarios();
  }catch(e){
    mostrarToast(e.message, true);
  }
}

// ── Modal: nuevo usuario ──────────────────────────────────────────────

function abrirModalNuevo(){
  document.getElementById('nu-nombre').value = '';
  document.getElementById('nu-usuario').value = '';
  document.getElementById('nu-password').value = '';
  construirSelectRoles(document.getElementById('nu-rol'), 'comercial');
  document.getElementById('nu-nota').textContent = 'Si escribes solo un nombre de usuario (sin @), se creará con el correo "usuario@sae-inmuebles.app".';
  ocultarErrorModal('nu-error');
  document.getElementById('modal-fondo').classList.add('visible');
  document.getElementById('nu-usuario').focus();
}

function cerrarModalNuevo(){
  document.getElementById('modal-fondo').classList.remove('visible');
}

function ocultarErrorModal(id){
  const el = document.getElementById(id);
  el.textContent = '';
  el.classList.remove('visible');
}

function mostrarErrorModal(id, mensaje){
  const el = document.getElementById(id);
  el.textContent = mensaje;
  el.classList.add('visible');
}

async function crearUsuario(){
  const nombre = document.getElementById('nu-nombre').value.trim();
  const usuario = document.getElementById('nu-usuario').value.trim();
  const password = document.getElementById('nu-password').value;
  const rol = document.getElementById('nu-rol').value;
  ocultarErrorModal('nu-error');

  if(!usuario || !password){
    mostrarErrorModal('nu-error', 'Escribe un usuario y una contraseña.');
    return;
  }
  if(password.length < 8){
    mostrarErrorModal('nu-error', 'La contraseña debe tener al menos 8 caracteres.');
    return;
  }

  const btn = document.getElementById('nu-crear');
  btn.disabled = true;
  btn.textContent = 'Creando…';
  try{
    const r = await fetch('/api/admin/usuarios', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({ nombre, usuario, password, rol }),
    });
    const cuerpo = await r.json().catch(() => ({}));
    if(!r.ok) throw new Error(cuerpo.error || 'No se pudo crear el usuario.');
    cerrarModalNuevo();
    mostrarToast('Usuario creado.');
    await cargarUsuarios();
  }catch(e){
    mostrarErrorModal('nu-error', e.message);
  }finally{
    btn.disabled = false;
    btn.textContent = 'Crear usuario';
  }
}

// ── Modal: restablecer contraseña ──────────────────────────────────────

function abrirModalClave(id, nombreMostrado){
  usuarioEnEdicion = id;
  const u = usuarios.find(x => x.id === id);
  document.getElementById('clave-usuario-nombre').textContent = `Usuario: ${nombreMostrado}`;
  document.getElementById('cl-nombre').value = (u && u.nombre) || '';
  document.getElementById('cl-password').value = '';
  ocultarErrorModal('cl-error');
  document.getElementById('modal-fondo-clave').classList.add('visible');
  document.getElementById('cl-nombre').focus();
}

function cerrarModalClave(){
  document.getElementById('modal-fondo-clave').classList.remove('visible');
  usuarioEnEdicion = null;
}

async function guardarClave(){
  const nombre = document.getElementById('cl-nombre').value.trim();
  const password = document.getElementById('cl-password').value;
  ocultarErrorModal('cl-error');
  if(password && password.length < 8){
    mostrarErrorModal('cl-error', 'La contraseña debe tener al menos 8 caracteres.');
    return;
  }

  const body = { nombre };
  if(password) body.password = password;

  const btn = document.getElementById('cl-guardar');
  btn.disabled = true;
  btn.textContent = 'Guardando…';
  try{
    const r = await fetch(`/api/admin/usuarios/${usuarioEnEdicion}`, {
      method: 'PATCH',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(body),
    });
    const cuerpo = await r.json().catch(() => ({}));
    if(!r.ok) throw new Error(cuerpo.error || 'No se pudo guardar los cambios.');
    cerrarModalClave();
    mostrarToast('Usuario actualizado.');
    await cargarUsuarios();
  }catch(e){
    mostrarErrorModal('cl-error', e.message);
  }finally{
    btn.disabled = false;
    btn.textContent = 'Guardar';
  }
}

// ── Eventos ─────────────────────────────────────────────────────────────

document.getElementById('btn-nuevo-usuario').addEventListener('click', abrirModalNuevo);
document.getElementById('btn-sincronizar-nombres').addEventListener('click', sincronizarNombresM365);
document.getElementById('nu-cancelar').addEventListener('click', cerrarModalNuevo);
document.getElementById('nu-crear').addEventListener('click', crearUsuario);
document.getElementById('modal-fondo').addEventListener('click', (ev) => { if(ev.target.id === 'modal-fondo') cerrarModalNuevo(); });

// Autocompletar el nombre al escribir un correo que ya está en el
// directorio de Microsoft 365 — solo si el admin no ha escrito ya un
// nombre a mano, para no pisarle lo que esté tecleando.
document.getElementById('nu-usuario').addEventListener('input', (ev) => {
  const correo = ev.target.value.trim().toLowerCase();
  const nombreActual = document.getElementById('nu-nombre').value.trim();
  if(!nombreActual && correo.includes('@') && directorioM365[correo]){
    document.getElementById('nu-nombre').value = directorioM365[correo];
  }
});

document.getElementById('cl-cancelar').addEventListener('click', cerrarModalClave);
document.getElementById('cl-guardar').addEventListener('click', guardarClave);
document.getElementById('modal-fondo-clave').addEventListener('click', (ev) => { if(ev.target.id === 'modal-fondo-clave') cerrarModalClave(); });

// Esta app corre dentro de un <iframe> del portal; si en algún momento se
// agrega expiración de sesión propia como en los otros módulos, avisar
// al portal por postMessage sigue el mismo patrón ya usado ahí.

cargarUsuarios();
