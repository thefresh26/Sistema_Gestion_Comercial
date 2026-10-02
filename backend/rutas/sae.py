"""
Expresiones SAE: consulta de inventario de inmuebles por folio, con
expresión de interés y código de subasta.

Los datos salen de la RPC `buscar_folios` que ya existía en Supabase
(proyecto original SAE).
"""
from __future__ import annotations

from flask import Blueprint, jsonify, request, send_from_directory, session

from backend import config, supabase
from backend.permisos import requires_modulo
from backend.registro import obtener_ip_cliente, registrar_log

bp = Blueprint("sae", __name__)

CARPETA = config.carpeta_modulo("sae")


@bp.route("/sae/")
@requires_modulo("sae")
def index():
    return send_from_directory(CARPETA, "index.html")


@bp.route("/sae/<path:filename>")
def estaticos(filename):
    # Los estáticos (css/js/logos) no llevan datos sensibles; el dato
    # sensible (la búsqueda) sí está protegido en /api/sae/buscar.
    return send_from_directory(CARPETA, filename)


@bp.route("/api/sae/buscar")
@requires_modulo("sae")
def buscar():
    folios_raw = request.args.get("folios", "")
    folios = [f.strip() for f in folios_raw.replace("/", ",").split(",") if f.strip()]
    if not folios:
        return jsonify([])

    r = supabase.rpc("buscar_folios", {"p_folios": folios})
    if r.status_code != 200:
        return jsonify({"error": "Error al consultar la base de datos"}), 502

    registrar_log("sae", session.get("email"), "busqueda", ", ".join(folios), obtener_ip_cliente())
    return jsonify(r.json())
