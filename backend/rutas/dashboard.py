"""
Estadísticas (folios y unidades vendidas).

No consulta ninguna base de datos externa en vivo: solo lee la tabla
`dashboard_ventas_anual`, que la GitHub Action
(`scripts/actualizar_dashboard.py`) mantiene actualizada. Así, un problema
de red hacia la base "intranet" de Azure nunca puede tumbar ni hacer lento
este tab.
"""
from __future__ import annotations

import requests
from flask import Blueprint, jsonify, send_from_directory, session

from backend import config, supabase
from backend.permisos import requires_modulo
from backend.registro import obtener_ip_cliente, registrar_log

bp = Blueprint("dashboard", __name__)

CARPETA = config.carpeta_modulo("dashboard")

_COLUMNAS = "sistema,anio,mes,medida,cantidad,valor_total,es_acumulado_historico,actualizado_en"


@bp.route("/dashboard/")
@requires_modulo("dashboard")
def index():
    return send_from_directory(CARPETA, "index.html")


@bp.route("/dashboard/<path:filename>")
def estaticos(filename):
    return send_from_directory(CARPETA, filename)


@bp.route("/api/dashboard/resumen")
@requires_modulo("dashboard")
def resumen():
    r = requests.get(
        supabase.url(f"/rest/v1/dashboard_ventas_anual?select={_COLUMNAS}&order=anio.asc,mes.asc"),
        headers=supabase.cabeceras_servicio(),
        timeout=10,
    )
    if r.status_code != 200:
        return jsonify({"error": "Error al consultar el resumen"}), 502

    registrar_log("dashboard", session.get("email"), "consulta", None, obtener_ip_cliente())
    return jsonify(r.json())
