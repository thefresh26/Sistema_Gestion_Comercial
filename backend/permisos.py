"""
Quién puede ver qué. Este es el ÚNICO archivo que hay que tocar para dar
o quitar acceso a un módulo completo, o para agregar un rol nuevo.

Contiene:
  - la tabla MODULOS (módulo -> roles que lo pueden abrir),
  - los nombres legibles de roles y módulos (para el panel de Permisos),
  - los decoradores que protegen cada ruta.

Está documentado en `docs/permisos.md` — revísalo antes de cambiar MODULOS.
"""
from __future__ import annotations

from functools import wraps
import hmac

from flask import jsonify, request, session

from backend import config

# Qué roles pueden ver/usar cada módulo del portal. Ajusta esta tabla si
# cambian las reglas de negocio.
#
# Roles y qué ve cada uno (acordado con el negocio):
#   comercial       -> ve todo (SAE, FRV, Vista_Inmuebles, Dashboard)
#   admin           -> ve todo (se muestra como "Administrador" en el panel)
#   juridico        -> solo FRV (con los campos de avalúo)
#   sae             -> solo el inventario SAE
#   comunicaciones  -> FRV (sin los campos de avalúo, igual que comercial) y
#                      Vista_Inmuebles ("Inmuebles", los inmuebles normales
#                      con semáforo de viabilidad, no FRV)
MODULOS = {
    "sae": {"comercial", "admin", "sae"},
    "frv": {"comercial", "juridico", "admin", "comunicaciones", "territoriales"},
    "vista_inmuebles": {"comercial", "admin", "comunicaciones", "territoriales"},
    "dashboard": {"comercial", "admin"},
    # Panel de permisos: solo lo abre el rol admin.
    "admin": {"admin"},
    # Generador de documentos (Actas, Certificados DD, etc.).
    "documentos": {"comercial", "admin"},
}

# Roles que NO deben ver los campos de avalúo de FRV (ver CAMPOS_AVALUO en
# backend/rutas/frv.py), aunque sí tengan acceso al módulo.
ROLES_SIN_AVALUO_FRV = {"comercial", "comunicaciones"}

# Nombre para mostrar de cada rol en el panel de administración de permisos.
# El valor interno ("admin") no cambia — así ningún usuario que ya tenga ese
# rol en Supabase pierde acceso — solo cambia cómo se ve en pantalla.
# "sin_acceso" es un rol especial que no aparece en ningún set de MODULOS:
# el usuario puede seguir iniciando sesión (ve "Inicio") pero no ve ningún
# módulo — sirve para revocar acceso sin borrar la cuenta.
ROLES_VISIBLES = {
    "comercial": "Comercial",
    "juridico": "Jurídico",
    "admin": "Administrador",
    "sae": "SAE",
    "comunicaciones": "Comunicaciones",
    "territoriales": "Territoriales",
    "sin_acceso": "Sin acceso",
}

# Nombre para mostrar de cada módulo — se usa solo para pintar en el panel
# de admin la tabla de referencia "qué ve cada rol" (a partir de MODULOS).
MODULOS_LISTA_LEGIBLE = {
    "sae": "Expresiones SAE",
    "frv": "Inmuebles FRV",
    "vista_inmuebles": "Vista Inmuebles",
    "dashboard": "Estadísticas",
    "admin": "Administración",
    "documentos": "Documentos",
}


def modulos_visibles(rol: str) -> dict[str, bool]:
    """Módulo -> si este rol lo puede abrir. Lo consume el portal para
    decidir qué pestañas pinta."""
    return {nombre: (rol in roles) for nombre, roles in MODULOS.items()}


# ── Decoradores de protección de rutas ──────────────────────────────────

def requires_auth(f):
    """Solo exige sesión iniciada, sin mirar el rol."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if "usuario" not in session:
            return jsonify({"error": "No autenticado"}), 401
        return f(*args, **kwargs)
    return decorated


def requires_modulo(nombre_modulo: str):
    """Además de estar logueado, el rol de la sesión debe estar autorizado
    para este módulo (ver MODULOS)."""
    def wrapper(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            if "usuario" not in session:
                return jsonify({"error": "No autenticado"}), 401
            rol = session.get("role", "")
            if rol not in MODULOS.get(nombre_modulo, set()):
                return jsonify({"error": "No tienes permiso para este módulo"}), 403
            return f(*args, **kwargs)
        return decorated
    return wrapper


def requires_api_key(f):
    """Para endpoints usados por sistemas externos (no personas): se
    autentican con un header X-API-Key, no con la sesión de Flask."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if not config.INTEGRACION_API_KEY:
            return jsonify({"error": "API de integración no configurada"}), 503
        clave_recibida = request.headers.get("X-API-Key", "")
        if not hmac.compare_digest(clave_recibida, config.INTEGRACION_API_KEY):
            return jsonify({"error": "Clave de integración inválida"}), 401
        return f(*args, **kwargs)
    return decorated
