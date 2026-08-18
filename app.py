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

SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_ANON_KEY = os.environ.get("SUPABASE_ANON_KEY", "")
SUPABASE_SERVICE_ROLE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")

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
MODULOS = {
    "sae": {"comercial", "admin"},
    "frv": {"comercial", "juridico", "admin"},
    "vista_inmuebles": {"comercial", "admin"},
}

CAMPOS_RESTRINGIDOS_COMERCIAL_FRV = [
    "VALOR AVALÚO",
    "AÑO AVALÚO",
    "TIPO AVALÚO",
    "FECHA AVALÚO",
    "TIENE AVALÚO",
    "VALOR AVALÚO COMERCIAL",
    "AÑO AVALÚO COMERCIAL",
    "FECHA AVALÚO COMERCIAL",
    "TIENE AVALÚO COMERCIAL",
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
    return send_from_directory(os.path.join(BASE_DIR, "portal"), "index.html")


@app.route("/portal/<path:filename>")
def portal_static(filename):
    return send_from_directory(os.path.join(BASE_DIR, "portal"), filename)


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
    role = (user.get("user_metadata") or {}).get("role", "comercial")

    session["usuario"] = usuario
    session["email"] = email
    session["role"] = role

    registrar_log("portal", email, "login", None, obtener_ip_cliente())

    return jsonify({
        "ok": True,
        "role": role,
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
        "role": rol,
        "modulos": modulos_visibles(rol),
    })


# ── MÓDULO SAE ───────────────────────────────────────────────────────────

@app.route("/sae/")
@requires_modulo("sae")
def sae_index():
    return send_from_directory(os.path.join(BASE_DIR, "sae"), "index.html")


@app.route("/sae/<path:filename>")
def sae_static(filename):
    # Los estáticos (css/js/logos) no llevan datos sensibles; el dato
    # sensible (la búsqueda) sí está protegido en /api/sae/buscar.
    return send_from_directory(os.path.join(BASE_DIR, "sae"), filename)


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
    return send_from_directory(os.path.join(BASE_DIR, "frv"), "index.html")


@app.route("/frv/data.json")
@requires_modulo("frv")
def frv_data():
    with open(os.path.join(BASE_DIR, "frv", "data.json"), "r", encoding="utf-8") as f:
        data = json.load(f)

    if session.get("role") == "comercial":
        data = [
            {k: v for k, v in registro.items() if k not in CAMPOS_RESTRINGIDOS_COMERCIAL_FRV}
            for registro in data
        ]

    registrar_log("frv", session.get("email"), "consulta_datos", None, obtener_ip_cliente())
    return jsonify(data)


@app.route("/frv/<path:filename>")
@requires_modulo("frv")
def frv_static(filename):
    return send_from_directory(os.path.join(BASE_DIR, "frv"), filename)


# ── MÓDULO VISTA_INMUEBLES ───────────────────────────────────────────────
# Antes era una app aparte (Vista_Inmuebles + Vista_Inmuebles_backend).
# Se fusionó aquí como una pestaña más, con el mismo login/sesión del
# portal. Solo la ve el rol "comercial" (y "admin"), ver MODULOS arriba.

@app.route("/vista_inmuebles/")
@requires_modulo("vista_inmuebles")
def vista_inmuebles_index():
    return send_from_directory(os.path.join(BASE_DIR, "vista_inmuebles"), "index.html")


@app.route("/vista_inmuebles/<path:filename>")
def vista_inmuebles_static(filename):
    return send_from_directory(os.path.join(BASE_DIR, "vista_inmuebles"), filename)


@app.route("/api/vista_inmuebles/buscar")
@requires_modulo("vista_inmuebles")
def vista_inmuebles_buscar():
    fmi = (request.args.get("fmi") or "").strip()
    if not fmi:
        return jsonify({"error": "Falta el FMI"}), 400

    # RPC buscar_inmueble_activos ya existente en Supabase (junta
    # inventario_SAE + existencia en inventario_Activos para el semáforo
    # de viabilidad). Viene de 01_endurecer_vista_inmuebles.sql.
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

    registrar_log("vista_inmuebles", session.get("email"), "busqueda", fmi, obtener_ip_cliente())

    # La función SQL devuelve null (no filas) o el objeto jsonb del inmueble.
    return jsonify(r.json())


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
