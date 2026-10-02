"""
Vista Inmuebles: consulta de inventario con semáforo de viabilidad.

Antes era una app aparte (Vista_Inmuebles + Vista_Inmuebles_backend). Se
fusionó aquí como una pestaña más, con el mismo login/sesión del portal.
"""
from __future__ import annotations

from flask import Blueprint, jsonify, request, send_from_directory, session

from backend import config
from backend.permisos import requires_modulo
from backend.registro import obtener_ip_cliente, registrar_log
from backend.rutas._inmuebles import buscar_inmuebles_por_fmi

bp = Blueprint("vista_inmuebles", __name__)

CARPETA = config.carpeta_modulo("vista_inmuebles")


@bp.route("/vista_inmuebles/")
@requires_modulo("vista_inmuebles")
def index():
    return send_from_directory(CARPETA, "index.html")


@bp.route("/vista_inmuebles/<path:filename>")
def estaticos(filename):
    return send_from_directory(CARPETA, filename)


@bp.route("/api/vista_inmuebles/buscar")
@requires_modulo("vista_inmuebles")
def buscar():
    fmis_raw = request.args.get("fmi", "")
    fmis = [f.strip() for f in fmis_raw.replace("/", ",").split(",") if f.strip()]
    if not fmis:
        return jsonify({"error": "Falta el FMI"}), 400

    resultados = buscar_inmuebles_por_fmi(fmis)
    if resultados is None:
        return jsonify({"error": "Error al consultar la base de datos"}), 502

    registrar_log("vista_inmuebles", session.get("email"), "busqueda", ", ".join(fmis), obtener_ip_cliente())

    # Siempre una lista (aunque haya sido un solo FMI) — el frontend decide
    # cómo mostrarla según cuántos resultados vengan.
    return jsonify(resultados)
