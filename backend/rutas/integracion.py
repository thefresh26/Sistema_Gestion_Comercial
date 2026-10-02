"""
API de integración externa.

Para que un sistema externo (no un usuario del portal) pueda consultar
inmuebles por FMI, autenticado con una clave de integración fija en vez de
un login de usuario. Reutiliza la misma búsqueda que Vista Inmuebles.
"""
from __future__ import annotations

from flask import Blueprint, jsonify, request

from backend.permisos import requires_api_key
from backend.registro import obtener_ip_cliente, registrar_log
from backend.rutas._inmuebles import buscar_inmuebles_por_fmi

bp = Blueprint("integracion", __name__)

#: Tope por consulta, para que un sistema externo no pueda pedir el
#: inventario completo de una sola vez.
MAX_FMI_POR_CONSULTA = 50


@bp.route("/api/integracion/inmuebles")
@requires_api_key
def inmuebles():
    fmis_raw = request.args.get("fmi", "")
    fmis = [f.strip() for f in fmis_raw.replace("/", ",").split(",") if f.strip()]
    if not fmis:
        return jsonify({"error": "Falta el parámetro fmi"}), 400
    if len(fmis) > MAX_FMI_POR_CONSULTA:
        return jsonify({"error": f"Máximo {MAX_FMI_POR_CONSULTA} FMI por consulta"}), 400

    resultados = buscar_inmuebles_por_fmi(fmis)
    if resultados is None:
        return jsonify({"error": "Error al consultar la base de datos"}), 502

    registrar_log("integracion_api", "api-externa", "busqueda", ", ".join(fmis), obtener_ip_cliente())
    return jsonify(resultados)
