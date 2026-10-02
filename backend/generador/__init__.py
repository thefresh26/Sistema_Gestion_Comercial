"""
Motor del módulo Documentos: arma los .docx a partir de las plantillas de
Word y los datos de cada caso.

  db.py              → la base de datos de casos (Neon) y la de negocio
                        (Azure, solo lectura)
  clarity.py         → métricas de tráfico para el Informe de Subasta
  tipos/             → un archivo por tipo de documento generable
  plantillas_word/   → los .docx en blanco con los marcadores ##campo##

Las rutas HTTP de este módulo están en `backend/rutas/documentos.py`.
"""
from __future__ import annotations

import os

#: Carpeta con las plantillas .docx en blanco.
CARPETA_PLANTILLAS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "plantillas_word")


def ruta_plantilla(nombre_archivo: str) -> str:
    """Ruta absoluta de una plantilla de Word."""
    return os.path.join(CARPETA_PLANTILLAS, nombre_archivo)
