"""
Panel de Permisos (`/admin/`).

Da de alta usuarios y cambia el rol / estado de los que ya existen,
hablando con la Admin API de Supabase Auth — nunca se guardan contraseñas
aquí ni hay una tabla de usuarios propia. Solo lo puede abrir el rol
"admin" (ver backend/permisos.py).
"""
from __future__ import annotations

import requests
from flask import Blueprint, jsonify, request, send_from_directory, session

from backend import config, supabase
from backend.permisos import (
    MODULOS,
    MODULOS_LISTA_LEGIBLE,
    ROLES_VISIBLES,
    requires_modulo,
)
from backend.registro import obtener_ip_cliente, registrar_log

bp = Blueprint("admin", __name__)

CARPETA = config.carpeta_modulo("admin")

#: Supabase no tiene un "ban permanente" real, así que deshabilitar una
#: cuenta se hace con una duración muy larga (~100 años) en vez de "none"
#: (que significa "sin baneo").
BAN_INDEFINIDO = "876000h"

LARGO_MINIMO_PASSWORD = 8


def _detalle_error(r: requests.Response, por_defecto: str) -> str:
    cuerpo = r.json() if r.content else {}
    return cuerpo.get("msg") or cuerpo.get("error_description") or por_defecto


@bp.route("/admin/")
@requires_modulo("admin")
def index():
    return send_from_directory(CARPETA, "index.html")


@bp.route("/admin/<path:filename>")
@requires_modulo("admin")
def estaticos(filename):
    return send_from_directory(CARPETA, filename)


@bp.route("/api/admin/usuarios")
@requires_modulo("admin")
def listar_usuarios():
    usuarios = supabase.listar_usuarios_auth()
    if usuarios is None:
        return jsonify({"error": "Error al consultar usuarios"}), 502

    emails_a_usuario = {v: k for k, v in config.USER_EMAILS.items()}

    salida = []
    for u in usuarios:
        email = u.get("email", "")
        metadata = u.get("user_metadata") or {}
        nombre_guardado = metadata.get("nombre", "")
        salida.append({
            "id": u.get("id"),
            "email": email,
            "usuario": emails_a_usuario.get(email, email),
            "nombre": nombre_guardado,
            # Sugerencia sacada del directorio de Microsoft 365 — solo se
            # llena cuando el usuario todavía no tiene un nombre guardado.
            "sugerencia_nombre": ("" if nombre_guardado else config.DIRECTORIO_M365.get(email.lower(), "")),
            "rol": metadata.get("role", "comercial"),
            "deshabilitado": bool(u.get("banned_until")),
            "creado_en": u.get("created_at"),
            "ultimo_ingreso": u.get("last_sign_in_at"),
            "es_yo": email == session.get("email"),
        })
    salida.sort(key=lambda x: (x["nombre"] or x["usuario"]).lower())

    return jsonify({
        "usuarios": salida,
        "roles": ROLES_VISIBLES,
        "modulos": MODULOS_LISTA_LEGIBLE,
        "matriz": {modulo: sorted(roles) for modulo, roles in MODULOS.items()},
    })


@bp.route("/api/admin/usuarios", methods=["POST"])
@requires_modulo("admin")
def crear_usuario():
    body = request.get_json(silent=True) or {}
    usuario = (body.get("usuario") or "").strip()
    password = body.get("password") or ""
    rol = body.get("rol") or "comercial"
    nombre = (body.get("nombre") or "").strip()

    if not usuario or not password:
        return jsonify({"error": "Faltan usuario o contraseña"}), 400
    if rol not in ROLES_VISIBLES:
        return jsonify({"error": "Rol inválido"}), 400
    if len(password) < LARGO_MINIMO_PASSWORD:
        return jsonify({"error": f"La contraseña debe tener al menos {LARGO_MINIMO_PASSWORD} caracteres"}), 400

    # Si el usuario ya escribió un correo completo se usa tal cual; si no,
    # se arma con el mismo patrón que config.USER_EMAILS.
    email = usuario if "@" in usuario else f"{usuario}@sae-inmuebles.app"

    # Si no escribieron un nombre a mano, se busca en el directorio de
    # Microsoft 365 por si ese correo ya aparece ahí.
    if not nombre:
        nombre = config.DIRECTORIO_M365.get(email.lower(), "")

    r = requests.post(
        supabase.url("/auth/v1/admin/users"),
        headers=supabase.cabeceras_servicio(),
        json={
            "email": email,
            "password": password,
            "email_confirm": True,
            "user_metadata": {"role": rol, "nombre": nombre},
        },
        timeout=15,
    )
    if r.status_code not in (200, 201):
        return jsonify({"error": _detalle_error(r, "Error al crear el usuario")}), 400

    registrar_log("admin", session.get("email"), "crear_usuario", f"{email} ({nombre}) -> rol {rol}", obtener_ip_cliente())
    return jsonify({"ok": True})


@bp.route("/api/admin/usuarios/<user_id>", methods=["PATCH"])
@requires_modulo("admin")
def actualizar_usuario(user_id):
    body = request.get_json(silent=True) or {}

    # Se trae el usuario actual primero para no pisarle otros campos que ya
    # tenga en user_metadata al actualizar el rol.
    r = requests.get(
        supabase.url(f"/auth/v1/admin/users/{user_id}"),
        headers=supabase.cabeceras_servicio(),
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
        payload["ban_duration"] = BAN_INDEFINIDO if body["deshabilitado"] else "none"
        detalle_log.append("cuenta deshabilitada" if body["deshabilitado"] else "cuenta habilitada")

    if body.get("password"):
        if es_yo:
            return jsonify({"error": "No puedes modificar tu propio usuario"}), 400
        if len(body["password"]) < LARGO_MINIMO_PASSWORD:
            return jsonify({"error": f"La contraseña debe tener al menos {LARGO_MINIMO_PASSWORD} caracteres"}), 400
        payload["password"] = body["password"]
        detalle_log.append("contraseña restablecida")

    if not payload:
        return jsonify({"error": "Nada que actualizar"}), 400

    r2 = requests.put(
        supabase.url(f"/auth/v1/admin/users/{user_id}"),
        headers=supabase.cabeceras_servicio(),
        json=payload,
        timeout=15,
    )
    if r2.status_code != 200:
        return jsonify({"error": _detalle_error(r2, "Error al actualizar el usuario")}), 400

    registrar_log(
        "admin", session.get("email"), "editar_usuario",
        f"{email_actual}: {', '.join(detalle_log)}", obtener_ip_cliente(),
    )
    return jsonify({"ok": True})


@bp.route("/api/admin/usuarios/<user_id>", methods=["DELETE"])
@requires_modulo("admin")
def eliminar_usuario(user_id):
    # Se trae el usuario primero -- para el log y para no dejar borrar la
    # propia cuenta (mismo criterio que deshabilitar/editar arriba).
    r = requests.get(
        supabase.url(f"/auth/v1/admin/users/{user_id}"),
        headers=supabase.cabeceras_servicio(),
        timeout=15,
    )
    if r.status_code != 200:
        return jsonify({"error": "Usuario no encontrado"}), 404
    email_actual = r.json().get("email")
    if email_actual == session.get("email"):
        return jsonify({"error": "No puedes eliminar tu propia cuenta"}), 400

    # A diferencia de "deshabilitar" (reversible, solo bloquea el ingreso),
    # esto borra la cuenta de Supabase Auth de forma permanente -- por eso
    # el frontend pide una confirmacion mas fuerte antes de llamar esto.
    r2 = requests.delete(
        supabase.url(f"/auth/v1/admin/users/{user_id}"),
        headers=supabase.cabeceras_servicio(),
        timeout=15,
    )
    if r2.status_code not in (200, 204):
        return jsonify({"error": _detalle_error(r2, "Error al eliminar el usuario")}), 400

    registrar_log("admin", session.get("email"), "eliminar_usuario", email_actual, obtener_ip_cliente())
    return jsonify({"ok": True})


@bp.route("/api/admin/directorio")
@requires_modulo("admin")
def directorio():
    # Correo -> nombre completo, sacado del export de Microsoft 365. El
    # panel lo usa para autocompletar el nombre al escribir un correo nuevo.
    return jsonify(config.DIRECTORIO_M365)


@bp.route("/api/admin/usuarios/sincronizar-nombres", methods=["POST"])
@requires_modulo("admin")
def sincronizar_nombres():
    """Copia el nombre desde el directorio de Microsoft 365 a todo usuario
    del portal que todavía no tenga un "Nombre completo" guardado y cuyo
    correo aparezca en ese directorio. Nunca pisa un nombre que ya exista."""
    if not config.DIRECTORIO_M365:
        return jsonify({"error": "No hay un directorio de Microsoft 365 cargado en el servidor."}), 400

    usuarios = supabase.listar_usuarios_auth()
    if usuarios is None:
        return jsonify({"error": "Error al consultar usuarios"}), 502

    actualizados = []
    for u in usuarios:
        metadata = u.get("user_metadata") or {}
        if metadata.get("nombre"):
            continue  # ya tiene nombre — nunca se sobreescribe
        email = (u.get("email") or "").lower()
        nombre_directorio = config.DIRECTORIO_M365.get(email)
        if not nombre_directorio:
            continue

        metadata["nombre"] = nombre_directorio
        r2 = requests.put(
            supabase.url(f"/auth/v1/admin/users/{u['id']}"),
            headers=supabase.cabeceras_servicio(),
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
