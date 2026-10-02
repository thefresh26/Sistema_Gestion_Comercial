"""
Inmuebles FRV: bienes del Fondo de Reparación a las Víctimas.

A diferencia de los demás módulos, los datos no salen de Supabase sino de
un `data.json` que produce el scraper de FRV. Lo que llega al navegador se
filtra con lista blanca (ver CAMPOS_BASE / CAMPOS_AVALUO).
"""
from __future__ import annotations

import json
import os

from flask import Blueprint, jsonify, send_from_directory, session

from backend import config
from backend.permisos import ROLES_SIN_AVALUO_FRV, requires_modulo
from backend.registro import obtener_ip_cliente, registrar_log

bp = Blueprint("frv", __name__)

CARPETA = config.carpeta_modulo("frv")

# Campos visibles para CUALQUIER rol con acceso al módulo (son justo los
# que pinta frv/index.html). Se usa lista blanca a propósito: así, si el
# scraper de FRV agrega columnas nuevas a data.json en el futuro, no se
# exponen automáticamente al navegador — hay que agregarlas aquí primero.
CAMPOS_BASE = [
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

# Campos de avalúo: solo se agregan para roles que NO estén en
# ROLES_SIN_AVALUO_FRV (ver backend/permisos.py).
CAMPOS_AVALUO = [
    "VALOR AVALÚO",
    "AÑO AVALÚO",
    "TIPO AVALÚO",
    "FECHA AVALÚO",
    "TIENE AVALÚO CATASTRAL",
    "VALOR AVALÚO CATASTRAL",
    "AÑO AVALÚO CATASTRAL",
    "FECHA AVALÚO CATASTRAL",
    "TIENE AVALÚO COMERCIAL",
    "VALOR AVALÚO COMERCIAL",
    "AÑO AVALÚO COMERCIAL",
    "FECHA AVALÚO COMERCIAL",
    "CON AVALÚO COMERC.",
]


@bp.route("/frv/")
@requires_modulo("frv")
def index():
    return send_from_directory(CARPETA, "index.html")


@bp.route("/frv/data.json")
@requires_modulo("frv")
def datos():
    with open(os.path.join(CARPETA, "data.json"), "r", encoding="utf-8") as f:
        data = json.load(f)

    # Lista blanca: solo salen los campos que la pantalla realmente usa,
    # nunca la fila completa del data.json.
    campos_permitidos = set(CAMPOS_BASE)
    if session.get("role") not in ROLES_SIN_AVALUO_FRV:
        campos_permitidos |= set(CAMPOS_AVALUO)

    data = [
        {k: v for k, v in registro.items() if k in campos_permitidos}
        for registro in data
    ]

    registrar_log("frv", session.get("email"), "consulta_datos", None, obtener_ip_cliente())
    return jsonify(data)


@bp.route("/frv/<path:filename>")
@requires_modulo("frv")
def estaticos(filename):
    return send_from_directory(CARPETA, filename)
