"""
app.py — Sistema de Gestión Comercial (portal unificado).

Une en un solo backend Flask, con un solo login y una sola sesión, los
módulos que antes eran apps independientes:

  - SAE             (antes Backend_SAE / Vista_inmuebles_SAE): consulta de
                     inventario de inmuebles por folio, con expresión de
                     interés y código de subasta.
  - FRV              (antes consulta_frv): consulta de bienes del Fondo de
                     Reparación a las Víctimas, con campos de avalúo
                     ocultos para el rol "comercial".
  - Vista_Inmuebles  (antes Vista_Inmuebles + Vista_Inmuebles_backend):
                     consulta de inventario con semáforo de viabilidad.
                     Fusionada aquí como una pestaña más — ya no es un
                     despliegue aparte. Solo la ve el rol "comercial" (y
                     "admin"); ver MODULOS más abajo.

Variables de entorno necesarias (Render → Settings → Environment):
  SECRET_KEY                 - clave para firmar la sesión de Flask
  SUPABASE_URL                - URL del proyecto Supabase (la misma que ya
                                usan SAE, FRV y Vista_Inmuebles)
  SUPABASE_ANON_KEY           - anon key
  SUPABASE_SERVICE_ROLE_KEY   - service_role key (solo server-side)
"""

import os
import json
import requests
from functools import wraps
from flask import Flask, send_from_directory, request, session, jsonify

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

app = Flask(__name__, static_folder=None)
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-key-change-me")

# Endurecer la cookie de sesión: que nunca sea legible por JavaScript, que
# solo viaje por HTTPS (Render ya sirve todo por HTTPS), y que no se envíe
# en peticiones iniciadas desde otros sitios.
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SECURE=True,
    SESSION_COOKIE_SAMESITE="Lax",
)

SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_ANON_KEY = os.environ.get("SUPABASE_ANON_KEY", "")
SUPABASE_SERVICE_ROLE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")

# Directorio de personal exportado de Microsoft 365 (Centro de administración
# → Usuarios → Exportar), correo -> nombre completo. Se usa SOLO para
# sugerir/rellenar el "Nombre completo" en el panel de Permisos — nunca para
# autenticar ni para nada fuera de esa pantalla. Si el archivo no existe el
# sistema sigue funcionando igual, simplemente sin sugerencias automáticas.
DIRECTORIO_M365_PATH = os.path.join(BASE_DIR, "data", "directorio_m365.json")
try:
    with open(DIRECTORIO_M365_PATH, "r", encoding="utf-8") as _f:
        DIRECTORIO_M365 = json.load(_f)
except (FileNotFoundError, json.JSONDecodeError):
    DIRECTORIO_M365 = {}

# Mapeo usuario corto -> correo real en Supabase Auth. Mismo patrón que los
# tres proyectos originales, reunido en un solo lugar.
USER_EMAILS = {
    "comercial2026": "comercial2026@sae-inmuebles.app",
    "juridica2026":  "juridica2026@sae-inmuebles.app",
    "SAE":           "sae@sae-inmuebles.app",
}

# Qué roles pueden ver/usar cada módulo del portal. Ajusta esta tabla si
# cambian las reglas de negocio; es el único lugar donde hay que tocar algo
# para dar o quitar acceso a un módulo completo.
#
# Roles y qué ve cada uno (acordado con el negocio):
#   comercial       -> ve todo (SAE, FRV, Vista_Inmuebles, Dashboard)
#   admin           -> ve todo (se muestra como "Administrador" en el panel)
#   juridico        -> solo FRV (con los campos de avalúo)
#   sae             -> solo el inventario SAE
#   comunicaciones  -> FRV (sin los campos de avalúo, igual que comercial) y
#                      Vista_Inmuebles ("Inmuebles", los inmuebles normales
#                      con semáforo de viabilidad, no FRV)
MODULOS = {
    "sae": {"comercial", "admin", "sae"},
    "frv": {"comercial", "juridico", "admin", "comunicaciones"},
    "vista_inmuebles": {"comercial", "admin", "comunicaciones"},
    "dashboard": {"comercial", "admin"},
    # Panel de permisos: solo lo abre el rol admin (ver pregunta al usuario).
    "admin": {"admin"},
}

# Roles que NO deben ver los campos de avalúo de FRV (ver CAMPOS_AVALUO_FRV
# más abajo), aunque sí tengan acceso al módulo.
ROLES_SIN_AVALUO_FRV = {"comercial", "comunicaciones"}

# Nombre para mostrar de cada rol en el panel de administración de permisos.
# El valor interno ("admin") no cambia — así ningún usuario que ya tenga ese
# rol en Supabase pierde acceso — solo cambia cómo se ve en pantalla.
# "sin_acceso" es un rol especial que no aparece en ningún set de MODULOS:
# el usuario puede seguir iniciando sesión (ve "Inicio") pero no ve ningún
# módulo — sirve para revocar acceso sin borrar la cuenta.
ROLES_VISIBLES = {
    "comercial": "Comercial",
    "juridico": "Jurídico",
    "admin": "Administrador",
    "sae": "SAE",
    "comunicaciones": "Comunicaciones",
    "sin_acceso": "Sin acceso",
}

# Nombre para mostrar de cada módulo — se usa solo para pintar en el panel
# de admin la tabla de referencia "qué ve cada rol" (a partir de MODULOS).
MODULOS_LISTA_LEGIBLE = {
    "sae": "Expresiones SAE",
    "frv": "Inmuebles FRV",
    "vista_inmuebles": "Vista Inmuebles",
    "dashboard": "Estadísticas",
    "admin": "Administración",
}

# Campos de FRV visibles para CUALQUIER rol con acceso al módulo (son
# justo los que pinta frv/index.html). Se usa lista blanca a propósito:
# así, si el scraper de FRV agrega columnas nuevas a data.json en el
# futuro, no se exponen automáticamente al navegador — hay que agregarlas
# a mano aquí primero.
CAMPOS_BASE_FRV = [
    "CÓDIGO",
    "CÓDIGO FRV",
    "NOMBRE BIEN",
    "TIPO BIEN",
    "FMI",
    "POSTULADO",
    "DEPARTAMENTO",
    "MUNICIPIO",
    "SISTEMA ADMON",
    "EXTINCIÓN DOMINIO",
    "ETAPA GESTIÓN",
    "ÁREA HA CATASTRO",
    "ÁREA HA ESCRITURA",
    "ÁREA HA MATRÍCULA",
    "ÁREA M2 CATASTRO",
    "ÁREA M2 ESCRITURA",
    "ÁREA M2 MATRÍCULA",
    "ÁREA CONSTRUIDA",
    "ESTADO FOLIO",
    "ESTADO ACTUAL BIEN",
    "FECHA APERTURA",
    "FECHA INSPECC.",
    "N° CATASTRAL",
    "CANT_FOTOS_LOCAL",
]

# Campos de avalúo: solo se agregan para roles distintos de "comercial"
# (jurídico, admin).
CAMPOS_AVALUO_FRV = [
    "VALOR AVALÚO",
    "AÑO AVALÚO",
    "TIPO AVALÚO",
    "FECHA AVALÚO",
    "VALOR AVALÚO COMERCIAL",
    "AÑO AVALÚO COMERCIAL",
    "FECHA AVALÚO COMERCIAL",
    "CON AVALÚO COMERC.",
]


def obtener_ip_cliente():
    xff = request.headers.get("X-Forwarded-For", "")
    if xff:
        return xff.split(",")[0].strip()
    return request.remote_addr


def registrar_log(modulo, email, accion, detalle, ip=None):
    """Mejor esfuerzo: si falla el log, no interrumpe la respuesta al usuario.
    Todo el sistema unificado escribe en una sola tabla (logs_acceso_sistema,
    ver sql/00_logs_unificado.sql) con una columna 'modulo' para distinguir
    de dónde viene cada evento."""
    try:
        requests.post(
            f"{SUPABASE_URL}/rest/v1/logs_acceso_sistema",
            headers={
                "apikey": SUPABASE_SERVICE_ROLE_KEY,
                "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "modulo": modulo,
                "usuario_email": email,
                "accion": accion,
                "detalle": detalle,
                "ip_address": ip,
            },
            timeout=5,
        )
    except Exception:
        pass


def requires_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "usuario" not in session:
            return jsonify({"error": "No autenticado"}), 401
        return f(*args, **kwargs)
    return decorated


def requires_modulo(nombre_modulo):
    """Además de estar logueado, el rol de la sesión debe estar autorizado
    para este módulo (ver MODULOS)."""
    def wrapper(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            if "usuario" not in session:
                return jsonify({"error": "No autenticado"}), 401
            rol = session.get("role", "")
            if rol not in MODULOS.get(nombre_modulo, set()):
                return jsonify({"error": "No tienes permiso para este módulo"}), 403
            return f(*args, **kwargs)
        return decorated
    return wrapper


def modulos_visibles(rol):
    return {nombre: (rol in roles) for nombre, roles in MODULOS.items()}


# ── PORTAL (shell + login) ──────────────────────────────────────────────

@app.route("/")
def portal_shell():
    return send_from_directory(os.path.join(BASE_DIR, "modulos", "portal"), "index.html")


@app.route("/portal/<path:filename>")
def portal_static(filename):
    return send_from_directory(os.path.join(BASE_DIR, "modulos", "portal"), filename)


@app.route("/api/login", methods=["POST"])
def login():
    body = request.get_json(silent=True) or {}
    usuario = (body.get("usuario") or "").strip()
    password = body.get("password") or ""
    if not usuario or not password:
        return jsonify({"error": "Faltan credenciales"}), 400

    email = USER_EMAILS.get(usuario, usuario)

    # El login real lo sigue validando Supabase Auth (nunca guardamos ni
    # comparamos contraseñas aquí).
    r = requests.post(
        f"{SUPABASE_URL}/auth/v1/token?grant_type=password",
        headers={"apikey": SUPABASE_ANON_KEY, "Content-Type": "application/json"},
        json={"email": email, "password": password},
        timeout=10,
    )
    if r.status_code != 200:
        return jsonify({"error": "Usuario o contraseña incorrectos"}), 401

    data = r.json()
    user = data.get("user", {})
    metadata = user.get("user_metadata") or {}
    role = metadata.get("role", "comercial")
    nombre = metadata.get("nombre", "")

    session["usuario"] = usuario
    session["email"] = email
    session["role"] = role
    session["nombre"] = nombre

    registrar_log("portal", email, "login", None, obtener_ip_cliente())

    return jsonify({
        "ok": True,
        "role": role,
        "role_legible": ROLES_VISIBLES.get(role, role),
        "nombre": nombre,
        "modulos": modulos_visibles(role),
    })


@app.route("/api/logout", methods=["POST"])
def logout():
    detalle = (request.get_json(silent=True) or {}).get("motivo")
    if session.get("email"):
        registrar_log(
            "portal",
            session["email"],
            "logout" if not detalle else "logout_inactividad",
            detalle,
            obtener_ip_cliente(),
        )
    session.clear()
    return jsonify({"ok": True})


@app.route("/api/session")
def get_session():
    if "usuario" not in session:
        return jsonify({"autenticado": False})
    rol = session.get("role", "")
    return jsonify({
        "autenticado": True,
        "usuario": session.get("usuario"),
        "nombre": session.get("nombre", ""),
        "role": rol,
        "role_legible": ROLES_VISIBLES.get(rol, rol),
        "modulos": modulos_visibles(rol),
    })


# ── MÓDULO SAE ───────────────────────────────────────────────────────────

@app.route("/sae/")
@requires_modulo("sae")
def sae_index():
    return send_from_directory(os.path.join(BASE_DIR, "modulos", "sae"), "index.html")


@app.route("/sae/<path:filename>")
def sae_static(filename):
    # Los estáticos (css/js/logos) no llevan datos sensibles; el dato
    # sensible (la búsqueda) sí está protegido en /api/sae/buscar.
    return send_from_directory(os.path.join(BASE_DIR, "modulos", "sae"), filename)


@app.route("/api/sae/buscar")
@requires_modulo("sae")
def sae_buscar():
    folios_raw = request.args.get("folios", "")
    folios = [f.strip() for f in folios_raw.replace("/", ",").split(",") if f.strip()]
    if not folios:
        return jsonify([])

    # RPC buscar_folios ya existente en Supabase (proyecto original SAE).
    r = requests.post(
        f"{SUPABASE_URL}/rest/v1/rpc/buscar_folios",
        headers={
            "apikey": SUPABASE_SERVICE_ROLE_KEY,
            "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
            "Content-Type": "application/json",
        },
        json={"p_folios": folios},
        timeout=15,
    )
    if r.status_code != 200:
        return jsonify({"error": "Error al consultar la base de datos"}), 502

    registrar_log("sae", session.get("email"), "busqueda", ", ".join(folios), obtener_ip_cliente())
    return jsonify(r.json())


# ── MÓDULO FRV ───────────────────────────────────────────────────────────

@app.route("/frv/")
@requires_modulo("frv")
def frv_index():
    return send_from_directory(os.path.join(BASE_DIR, "modulos", "frv"), "index.html")


@app.route("/frv/data.json")
@requires_modulo("frv")
def frv_data():
    with open(os.path.join(BASE_DIR, "modulos", "frv", "data.json"), "r", encoding="utf-8") as f:
        data = json.load(f)

    # Lista blanca: solo salen los campos que la pantalla realmente usa,
    # nunca la fila completa del data.json.
    campos_permitidos = set(CAMPOS_BASE_FRV)
    if session.get("role") not in ROLES_SIN_AVALUO_FRV:
        campos_permitidos |= set(CAMPOS_AVALUO_FRV)

    data = [
        {k: v for k, v in registro.items() if k in campos_permitidos}
        for registro in data
    ]

    registrar_log("frv", session.get("email"), "consulta_datos", None, obtener_ip_cliente())
    return jsonify(data)


@app.route("/frv/<path:filename>")
@requires_modulo("frv")
def frv_static(filename):
    return send_from_directory(os.path.join(BASE_DIR, "modulos", "frv"), filename)


# ── MÓDULO VISTA_INMUEBLES ───────────────────────────────────────────────
# Antes era una app aparte (Vista_Inmuebles + Vista_Inmuebles_backend).
# Se fusionó aquí como una pestaña más, con el mismo login/sesión del
# portal. Solo la ve el rol "comercial" (y "admin"), ver MODULOS arriba.

@app.route("/vista_inmuebles/")
@requires_modulo("vista_inmuebles")
def vista_inmuebles_index():
    return send_from_directory(os.path.join(BASE_DIR, "modulos", "vista_inmuebles"), "index.html")


@app.route("/vista_inmuebles/<path:filename>")
def vista_inmuebles_static(filename):
    return send_from_directory(os.path.join(BASE_DIR, "modulos", "vista_inmuebles"), filename)


@app.route("/api/vista_inmuebles/buscar")
@requires_modulo("vista_inmuebles")
def vista_inmuebles_buscar():
    fmis_raw = request.args.get("fmi", "")
    fmis = [f.strip() for f in fmis_raw.replace("/", ",").split(",") if f.strip()]
    if not fmis:
        return jsonify({"error": "Falta el FMI"}), 400

    # La RPC buscar_inmueble_activos (01_endurecer_vista_inmuebles.sql) solo
    # busca un FMI a la vez, así que para varios se le pregunta uno por uno
    # — son consultas puntuales por matrícula, no un listado masivo, así que
    # el costo de hacerlo en un ciclo es insignificante.
    resultados = []
    for fmi in fmis:
        r = requests.post(
            f"{SUPABASE_URL}/rest/v1/rpc/buscar_inmueble_activos",
            headers={
                "apikey": SUPABASE_SERVICE_ROLE_KEY,
                "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
                "Content-Type": "application/json",
            },
            json={"p_fmi": fmi},
            timeout=15,
        )
        if r.status_code != 200:
            return jsonify({"error": "Error al consultar la base de datos"}), 502
        dato = r.json()  # null (no existe) o el objeto jsonb del inmueble
        if dato:
            resultados.append(dato)

    registrar_log("vista_inmuebles", session.get("email"), "busqueda", ", ".join(fmis), obtener_ip_cliente())

    # Siempre una lista (aunque haya sido un solo FMI) — el frontend decide
    # cómo mostrarla según cuántos resultados vengan.
    return jsonify(resultados)


# ── MÓDULO DASHBOARD ("Estadísticas") ───────────────────────────────────
# No consulta ninguna base de datos externa en vivo: solo lee la tabla
# dashboard_ventas_anual, que el Cron Job (scripts/actualizar_dashboard.py)
# mantiene actualizada. Así, un problema de red hacia la base "intranet"
# de Azure nunca puede tumbar ni hacer lento este tab.

@app.route("/dashboard/")
@requires_modulo("dashboard")
def dashboard_index():
    return send_from_directory(os.path.join(BASE_DIR, "modulos", "dashboard"), "index.html")


@app.route("/dashboard/<path:filename>")
def dashboard_static(filename):
    return send_from_directory(os.path.join(BASE_DIR, "modulos", "dashboard"), filename)


@app.route("/api/dashboard/resumen")
@requires_modulo("dashboard")
def dashboard_resumen():
    r = requests.get(
        f"{SUPABASE_URL}/rest/v1/dashboard_ventas_anual?select=sistema,anio,mes,medida,cantidad,valor_total,es_acumulado_historico,actualizado_en&order=anio.asc,mes.asc",
        headers={
            "apikey": SUPABASE_SERVICE_ROLE_KEY,
            "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
        },
        timeout=10,
    )
    if r.status_code != 200:
        return jsonify({"error": "Error al consultar el resumen"}), 502

    registrar_log("dashboard", session.get("email"), "consulta", None, obtener_ip_cliente())
    return jsonify(r.json())


# ── MÓDULO ADMIN (panel de permisos) ─────────────────────────────────────
# Da de alta usuarios y cambia el rol / estado de los que ya existen,
# hablando con la Admin API de Supabase Auth (nunca se guardan contraseñas
# aquí). Solo lo puede abrir el rol "admin" (ver MODULOS arriba).

@app.route("/admin/")
@requires_modulo("admin")
def admin_index():
    return send_from_directory(os.path.join(BASE_DIR, "modulos", "admin"), "index.html")


@app.route("/admin/<path:filename>")
@requires_modulo("admin")
def admin_static(filename):
    return send_from_directory(os.path.join(BASE_DIR, "modulos", "admin"), filename)


def _supabase_admin_headers():
    return {
        "apikey": SUPABASE_SERVICE_ROLE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
        "Content-Type": "application/json",
    }


@app.route("/api/admin/usuarios")
@requires_modulo("admin")
def admin_listar_usuarios():
    usuarios = []
    pagina = 1
    while True:
        r = requests.get(
            f"{SUPABASE_URL}/auth/v1/admin/users",
            headers=_supabase_admin_headers(),
            params={"page": pagina, "per_page": 200},
            timeout=15,
        )
        if r.status_code != 200:
            return jsonify({"error": "Error al consultar usuarios"}), 502
        pagina_datos = r.json().get("users", [])
        if not pagina_datos:
            break
        usuarios.extend(pagina_datos)
        if len(pagina_datos) < 200:
            break
        pagina += 1

    emails_a_usuario = {v: k for k, v in USER_EMAILS.items()}

    salida = []
    for u in usuarios:
        email = u.get("email", "")
        metadata = u.get("user_metadata") or {}
        rol = metadata.get("role", "comercial")
        nombre_guardado = metadata.get("nombre", "")
        salida.append({
            "id": u.get("id"),
            "email": email,
            "usuario": emails_a_usuario.get(email, email),
            "nombre": nombre_guardado,
            # Sugerencia sacada del directorio de Microsoft 365 — solo se
            # llena cuando el usuario todavía no tiene un nombre guardado.
            "sugerencia_nombre": ("" if nombre_guardado else DIRECTORIO_M365.get(email.lower(), "")),
            "rol": rol,
            "deshabilitado": bool(u.get("banned_until")),
            "creado_en": u.get("created_at"),
            "ultimo_ingreso": u.get("last_sign_in_at"),
            "es_yo": email == session.get("email"),
        })
    salida.sort(key=lambda x: (x["nombre"] or x["usuario"]).lower())
    matriz = {modulo: sorted(roles) for modulo, roles in MODULOS.items()}
    return jsonify({
        "usuarios": salida,
        "roles": ROLES_VISIBLES,
        "modulos": MODULOS_LISTA_LEGIBLE,
        "matriz": matriz,
    })


@app.route("/api/admin/usuarios", methods=["POST"])
@requires_modulo("admin")
def admin_crear_usuario():
    body = request.get_json(silent=True) or {}
    usuario = (body.get("usuario") or "").strip()
    password = body.get("password") or ""
    rol = body.get("rol") or "comercial"
    nombre = (body.get("nombre") or "").strip()

    if not usuario or not password:
        return jsonify({"error": "Faltan usuario o contraseña"}), 400
    if rol not in ROLES_VISIBLES:
        return jsonify({"error": "Rol inválido"}), 400
    if len(password) < 8:
        return jsonify({"error": "La contraseña debe tener al menos 8 caracteres"}), 400

    # Si el usuario ya escribió un correo completo se usa tal cual; si no,
    # se arma con el mismo patrón que USER_EMAILS.
    email = usuario if "@" in usuario else f"{usuario}@sae-inmuebles.app"

    # Si no escribieron un nombre a mano, se busca en el directorio de
    # Microsoft 365 por si ese correo ya aparece ahí.
    if not nombre:
        nombre = DIRECTORIO_M365.get(email.lower(), "")

    r = requests.post(
        f"{SUPABASE_URL}/auth/v1/admin/users",
        headers=_supabase_admin_headers(),
        json={
            "email": email,
            "password": password,
            "email_confirm": True,
            "user_metadata": {"role": rol, "nombre": nombre},
        },
        timeout=15,
    )
    if r.status_code not in (200, 201):
        cuerpo = r.json() if r.content else {}
        detalle = cuerpo.get("msg") or cuerpo.get("error_description") or "Error al crear el usuario"
        return jsonify({"error": detalle}), 400

    registrar_log("admin", session.get("email"), "crear_usuario", f"{email} ({nombre}) -> rol {rol}", obtener_ip_cliente())
    return jsonify({"ok": True})


@app.route("/api/admin/usuarios/<user_id>", methods=["PATCH"])
@requires_modulo("admin")
def admin_actualizar_usuario(user_id):
    body = request.get_json(silent=True) or {}

    # Se trae el usuario actual primero para no pisarle otros campos que ya
    # tenga en user_metadata al actualizar el rol.
    r = requests.get(
        f"{SUPABASE_URL}/auth/v1/admin/users/{user_id}",
        headers=_supabase_admin_headers(),
        timeout=15,
    )
    if r.status_code != 200:
        return jsonify({"error": "Usuario no encontrado"}), 404
    actual = r.json()
    email_actual = actual.get("email")
    es_yo = email_actual == session.get("email")

    payload = {}
    detalle_log = []
    metadata_actual = actual.get("user_metadata") or {}
    metadata_cambio = False

    if "rol" in body:
        rol = body["rol"]
        if rol not in ROLES_VISIBLES:
            return jsonify({"error": "Rol inválido"}), 400
        if es_yo and rol != "admin":
            return jsonify({"error": "No puedes quitarte tu propio rol de administrador"}), 400
        metadata_actual["role"] = rol
        metadata_cambio = True
        detalle_log.append(f"rol -> {rol}")

    if "nombre" in body:
        if es_yo:
            return jsonify({"error": "No puedes modificar tu propio usuario"}), 400
        metadata_actual["nombre"] = (body["nombre"] or "").strip()
        metadata_cambio = True
        detalle_log.append(f"nombre -> {metadata_actual['nombre']}")

    if metadata_cambio:
        payload["user_metadata"] = metadata_actual

    if "deshabilitado" in body:
        if es_yo and body["deshabilitado"]:
            return jsonify({"error": "No puedes deshabilitar tu propia cuenta"}), 400
        # ~100 años: Supabase no tiene un "ban permanente" real, así que se
        # usa una duración muy larga en vez de "none" (que significa "sin
        # baneo") para deshabilitar el ingreso indefinidamente.
        payload["ban_duration"] = "876000h" if body["deshabilitado"] else "none"
        detalle_log.append("cuenta deshabilitada" if body["deshabilitado"] else "cuenta habilitada")

    if body.get("password"):
        if es_yo:
            return jsonify({"error": "No puedes modificar tu propio usuario"}), 400
        if len(body["password"]) < 8:
            return jsonify({"error": "La contraseña debe tener al menos 8 caracteres"}), 400
        payload["password"] = body["password"]
        detalle_log.append("contraseña restablecida")

    if not payload:
        return jsonify({"error": "Nada que actualizar"}), 400

    r2 = requests.put(
        f"{SUPABASE_URL}/auth/v1/admin/users/{user_id}",
        headers=_supabase_admin_headers(),
        json=payload,
        timeout=15,
    )
    if r2.status_code != 200:
        cuerpo = r2.json() if r2.content else {}
        detalle = cuerpo.get("msg") or cuerpo.get("error_description") or "Error al actualizar el usuario"
        return jsonify({"error": detalle}), 400

    registrar_log(
        "admin", session.get("email"), "editar_usuario",
        f"{email_actual}: {', '.join(detalle_log)}", obtener_ip_cliente(),
    )
    return jsonify({"ok": True})


@app.route("/api/admin/directorio")
@requires_modulo("admin")
def admin_directorio():
    # Correo -> nombre completo, sacado del export de Microsoft 365. El
    # panel lo usa para autocompletar el nombre al escribir un correo nuevo.
    return jsonify(DIRECTORIO_M365)


@app.route("/api/admin/usuarios/sincronizar-nombres", methods=["POST"])
@requires_modulo("admin")
def admin_sincronizar_nombres():
    """Copia el nombre desde el directorio de Microsoft 365 a todo usuario
    del portal que todavía no tenga un "Nombre completo" guardado y cuyo
    correo aparezca en ese directorio. Nunca pisa un nombre que ya exista."""
    if not DIRECTORIO_M365:
        return jsonify({"error": "No hay un directorio de Microsoft 365 cargado en el servidor."}), 400

    usuarios = []
    pagina = 1
    while True:
        r = requests.get(
            f"{SUPABASE_URL}/auth/v1/admin/users",
            headers=_supabase_admin_headers(),
            params={"page": pagina, "per_page": 200},
            timeout=15,
        )
        if r.status_code != 200:
            return jsonify({"error": "Error al consultar usuarios"}), 502
        pagina_datos = r.json().get("users", [])
        if not pagina_datos:
            break
        usuarios.extend(pagina_datos)
        if len(pagina_datos) < 200:
            break
        pagina += 1

    actualizados = []
    for u in usuarios:
        metadata = u.get("user_metadata") or {}
        if metadata.get("nombre"):
            continue  # ya tiene nombre — nunca se sobreescribe
        email = (u.get("email") or "").lower()
        nombre_directorio = DIRECTORIO_M365.get(email)
        if not nombre_directorio:
            continue

        metadata["nombre"] = nombre_directorio
        r2 = requests.put(
            f"{SUPABASE_URL}/auth/v1/admin/users/{u['id']}",
            headers=_supabase_admin_headers(),
            json={"user_metadata": metadata},
            timeout=15,
        )
        if r2.status_code == 200:
            actualizados.append({"email": email, "nombre": nombre_directorio})

    if actualizados:
        registrar_log(
            "admin", session.get("email"), "sincronizar_nombres_m365",
            f"{len(actualizados)} usuarios: " + "; ".join(f"{a['email']} -> {a['nombre']}" for a in actualizados),
            obtener_ip_cliente(),
        )

    return jsonify({"ok": True, "actualizados": actualizados})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
