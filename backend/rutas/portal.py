"""
Portal: el shell con las pestañas, y el login/logout/sesión que comparten
todos los módulos.

El login real lo valida Supabase Auth — aquí nunca se guardan ni se
comparan contraseñas. El rol y el nombre de cada usuario viven en el
`user_metadata` de Supabase Auth.
"""
from __future__ import annotations

import requests
from flask import Blueprint, jsonify, request, send_from_directory, session

from backend import config, supabase
from backend.permisos import ROLES_VISIBLES, modulos_visibles
from backend.registro import obtener_ip_cliente, registrar_log

bp = Blueprint("portal", __name__)


@bp.route("/")
def shell():
    return send_from_directory(config.carpeta_modulo("portal"), "index.html")


@bp.route("/portal/<path:filename>")
def estaticos(filename):
    return send_from_directory(config.carpeta_modulo("portal"), filename)


@bp.route("/api/login", methods=["POST"])
def login():
    body = request.get_json(silent=True) or {}
    usuario = (body.get("usuario") or "").strip()
    password = body.get("password") or ""
    if not usuario or not password:
        return jsonify({"error": "Faltan credenciales"}), 400

    email = config.USER_EMAILS.get(usuario, usuario)

    r = requests.post(
        supabase.url("/auth/v1/token?grant_type=password"),
        headers=supabase.cabeceras_anon(),
        json={"email": email, "password": password},
        timeout=10,
    )
    if r.status_code != 200:
        return jsonify({"error": "Usuario o contraseña incorrectos"}), 401

    user = r.json().get("user", {})
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


@bp.route("/api/logout", methods=["POST"])
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


@bp.route("/api/session")
def estado_sesion():
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
