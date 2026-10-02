"""
Backend del Sistema de Gestión Comercial — portal unificado de Activos
por Colombia.

Une en un solo backend Flask, con un solo login y una sola sesión, los
módulos que antes eran apps independientes:

  - SAE             (antes Backend_SAE / Vista_inmuebles_SAE): consulta de
                     inventario de inmuebles por folio, con expresión de
                     interés y código de subasta.
  - FRV              (antes consulta_frv): consulta de bienes del Fondo de
                     Reparación a las Víctimas, con campos de avalúo
                     ocultos para algunos roles.
  - Vista_Inmuebles  (antes Vista_Inmuebles + Vista_Inmuebles_backend):
                     consulta de inventario con semáforo de viabilidad.
  - Estadísticas, Permisos y Documentos, que nacieron ya dentro del portal.

Cómo está organizado este paquete:

  config.py     → variables de entorno y rutas de carpetas
  permisos.py   → MODULOS (quién ve qué) y los decoradores de las rutas
  supabase.py   → cabeceras y llamadas HTTP a Supabase
  registro.py   → el log unificado de eventos
  rutas/        → un archivo por módulo del portal
  generador/    → el motor que arma los .docx del módulo Documentos

Variables de entorno necesarias (Render → Settings → Environment): ver
`.env.example`.
"""
from __future__ import annotations

from flask import Flask

from backend import config
from backend.rutas import TODOS as BLUEPRINTS


def create_app() -> Flask:
    """Arma la aplicación Flask y le registra todos los módulos."""
    # static_folder=None: cada módulo sirve sus propios estáticos desde
    # `frontend/<modulo>/`, no hay una carpeta /static global.
    app = Flask(__name__, static_folder=None)
    app.secret_key = config.SECRET_KEY

    # Endurecer la cookie de sesión: que nunca sea legible por JavaScript,
    # que solo viaje por HTTPS (Render ya sirve todo por HTTPS), y que no se
    # envíe en peticiones iniciadas desde otros sitios.
    #
    # Ojo al probar en local sobre http://localhost (sin HTTPS): con
    # SESSION_COOKIE_SECURE=True el navegador descarta la cookie y el login
    # no "pega". Ver el README para cómo probarlo.
    app.config.update(
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SECURE=True,
        SESSION_COOKIE_SAMESITE="Lax",
    )

    for bp in BLUEPRINTS:
        app.register_blueprint(bp)

    return app
