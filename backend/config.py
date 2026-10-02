"""
Configuración central: rutas de carpetas, variables de entorno y los
datos fijos que varios módulos necesitan.

Todo lo que se lee del entorno (claves de Supabase, etc.) se lee AQUÍ y
solo aquí — el resto del backend importa estas constantes en vez de
llamar a `os.environ` por su cuenta.
"""
from __future__ import annotations

import json
import os

from dotenv import load_dotenv

load_dotenv()

# ── Rutas de carpetas ───────────────────────────────────────────────────
# RAIZ es la carpeta del repositorio (dos niveles arriba de este archivo:
# backend/config.py -> backend/ -> raíz).
RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

#: Carpeta con un subproyecto por pestaña del portal (HTML/CSS/JS).
FRONTEND_DIR = os.path.join(RAIZ, "frontend")

#: Datos auxiliares que se cargan al arrancar (no son base de datos).
DATOS_DIR = os.path.join(RAIZ, "data")


def carpeta_modulo(nombre: str) -> str:
    """Carpeta del frontend de un módulo del portal (`frontend/<nombre>/`)."""
    return os.path.join(FRONTEND_DIR, nombre)


# ── Variables de entorno ────────────────────────────────────────────────
SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-key-change-me")

SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_ANON_KEY = os.environ.get("SUPABASE_ANON_KEY", "")
SUPABASE_SERVICE_ROLE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")

# Clave para la API de integración externa (consulta de inmuebles por FMI).
# La usa un sistema externo (no un usuario logueado), así que se valida con
# un header propio (X-API-Key), nunca con la sesión de Flask.
INTEGRACION_API_KEY = os.environ.get("INTEGRACION_API_KEY", "")


# ── Datos fijos ─────────────────────────────────────────────────────────
# Mapeo usuario corto -> correo real en Supabase Auth. Mismo patrón que los
# tres proyectos originales, reunido en un solo lugar.
USER_EMAILS = {
    "comercial2026": "comercial2026@sae-inmuebles.app",
    "juridica2026":  "juridica2026@sae-inmuebles.app",
    "SAE":           "sae@sae-inmuebles.app",
}

# Directorio de personal exportado de Microsoft 365 (Centro de administración
# → Usuarios → Exportar), correo -> nombre completo. Se usa SOLO para
# sugerir/rellenar el "Nombre completo" en el panel de Permisos — nunca para
# autenticar ni para nada fuera de esa pantalla. Si el archivo no existe el
# sistema sigue funcionando igual, simplemente sin sugerencias automáticas.
DIRECTORIO_M365_PATH = os.path.join(DATOS_DIR, "directorio_m365.json")
try:
    with open(DIRECTORIO_M365_PATH, "r", encoding="utf-8") as _f:
        DIRECTORIO_M365 = json.load(_f)
except (FileNotFoundError, json.JSONDecodeError):
    DIRECTORIO_M365 = {}
