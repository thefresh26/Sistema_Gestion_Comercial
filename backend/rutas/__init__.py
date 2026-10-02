"""
Las rutas HTTP, un archivo por módulo del portal.

Para agregar un módulo nuevo: crea `backend/rutas/<nombre>.py` con un
`bp = Blueprint(...)`, impórtalo aquí y agrégalo a TODOS.
"""
from __future__ import annotations

from backend.rutas import (
    admin,
    dashboard,
    documentos,
    frv,
    integracion,
    portal,
    sae,
    vista_inmuebles,
)

#: Todos los blueprints que `create_app()` registra, en el orden en que
#: aparecen las pestañas del portal.
TODOS = [
    portal.bp,
    sae.bp,
    frv.bp,
    vista_inmuebles.bp,
    dashboard.bp,
    documentos.bp,
    admin.bp,
    integracion.bp,
]
