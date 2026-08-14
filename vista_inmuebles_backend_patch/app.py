"""
app.py — Backend intermedio (Flask) para Vista_Inmuebles (broker/comercial).

Mismo patrón que Backend_SAE: el navegador ya no habla directo con
Supabase. Le habla a este servidor, y este servidor (con la
service_role key, nunca expuesta al navegador) es el único que habla
con Supabase.

Variables de entorno necesarias (Render → Settings → Environment):
  SECRET_KEY                - clave para firmar la sesión de Flask
  SUPABASE_URL               - URL del proyecto
  SUPABASE_ANON_KEY          - anon key
  SUPABASE_SERVICE_ROLE_KEY  - service_role key (solo server-side)
"""

import os
import requests
from functools import wraps
from flask import Flask, send_from_directory, request, session, jsonify

app = Flask(__name__, static_folder="visor", static_url_path="")
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-key-change-me")

SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_ANON_KEY = os.environ.get("SUPABASE_ANON_KEY", "")
SUPABASE_SERVICE_ROLE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")

USER_EMAILS = {
    "comercial2026": "comercial2026@sae-inmuebles.app",
}


def obtener_ip_cliente():
    xff = request.headers.get("X-Forwarded-For", "")
    if xff:
        return xff.split(",")[0].strip()
    return request.remote_addr


def requires_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "usuario" not in session:
            return jsonify({"error": "No autenticado"}), 401
        return f(*args, **kwargs)
    return decorated


@app.route("/")
def index():
    return send_from_directory("visor", "index.html")


@app.route("/api/login", methods=["POST"])
def login():
    body = request.get_json(silent=True) or {}
    usuario = (body.get("usuario") or "").strip()
    password = body.get("password") or ""
    if not usuario or not password:
        return jsonify({"error": "Faltan credenciales"}), 400

    email = USER_EMAILS.get(usuario, usuario)

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

    registrar_log(email, "login", None, obtener_ip_cliente())
    return jsonify({"ok": True, "role": role})


@app.route("/api/logout", methods=["POST"])
def logout():
    detalle = (request.get_json(silent=True) or {}).get("motivo")
    if session.get("email"):
        registrar_log(session["email"], "logout" if not detalle else "logout_inactividad", detalle, obtener_ip_cliente())
    session.clear()
    return jsonify({"ok": True})


@app.route("/api/session")
def get_session():
    if "usuario" not in session:
        return jsonify({"autenticado": False})
    return jsonify({"autenticado": True, "role": session.get("role")})


@app.route("/api/buscar")
@requires_auth
def buscar():
    fmi = (request.args.get("fmi") or "").strip()
    if not fmi:
        return jsonify({"error": "Falta el FMI"}), 400

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

    registrar_log(session.get("email"), "busqueda", fmi, obtener_ip_cliente())

    resultado = r.json()
    # La función SQL devuelve null (no filas) o el objeto jsonb del inmueble.
    return jsonify(resultado)


def registrar_log(email, accion, detalle, ip=None):
    """Escribe en la tabla de trazabilidad UNIFICADA del sistema
    (logs_acceso_sistema, compartida con el portal SAE+FRV), marcando
    modulo='vista_inmuebles' para distinguir el origen. Esta app sigue
    siendo un despliegue aparte; lo único que cambia es dónde queda el
    rastro de accesos, para tener toda la trazabilidad de la empresa en
    un solo lugar. Ver sql/00_logs_unificado.sql en el repo del portal."""
    try:
        requests.post(
            f"{SUPABASE_URL}/rest/v1/logs_acceso_sistema",
            headers={
                "apikey": SUPABASE_SERVICE_ROLE_KEY,
                "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "modulo": "vista_inmuebles",
                "usuario_email": email,
                "accion": accion,
                "detalle": detalle,
                "ip_address": ip,
            },
            timeout=5,
        )
    except Exception:
        pass


@app.route("/<path:filename>")
def static_files(filename):
    return send_from_directory("visor", filename)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
