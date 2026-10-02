"""
Catálogo de tipos de documento que el sistema puede generar. Cada tipo es
un módulo independiente (su propia plantilla, sus propios campos, su
propia lógica de extracción) registrado aquí -- así la interfaz puede
mostrar un filtro "¿qué quieres generar?" y cada tipo se agrega sin tocar
los demás.

Para agregar un tipo nuevo:
  1. Crear `backend/generador/tipos/<clave>.py` con la funcion
     `generar(fmi)` y las listas `CAMPOS_EDITABLES` y
     `TIPOS_DOCUMENTO_FUENTE`.
  2. Poner su plantilla .docx en `backend/generador/plantillas_word/` y
     apuntarla con `ruta_plantilla("<archivo>.docx")`.
  3. Registrarlo abajo en TIPOS con su etiqueta y estado.
"""
from __future__ import annotations

from . import certificado_dd
from . import acta_subasta
from . import informe_subasta
from . import declaracion_juramentada

# Nota historica: hubo dos tipos mas, Acta de Arrendamiento y Acta de
# Alcance, que nunca se activaron -- son procesos que el usuario sigue
# haciendo manualmente, fuera de este sistema. Su codigo se elimino del
# repositorio por no estar en uso; si alguna vez hace falta recuperarlo,
# esta en el historial de git (hasta el commit b8165dd, en core/tipos/).

TIPOS = {
    "certificado_dd": {
        "etiqueta": "Certificado de Resultado DD",
        "descripcion": "Certificado de debida diligencia sobre un tercero (persona o empresa). Se busca por cédula, NIT, FMI, código de subasta o de unidad.",
        "modulo": certificado_dd,
        "disponible": True,
    },
    "acta_subasta": {
        "etiqueta": "Acta de Certificación de Subasta Electrónica",
        "descripcion": "Certifica el resultado de una subasta electrónica. Se busca por FMI, código de subasta o de unidad.",
        "modulo": acta_subasta,
        "disponible": True,
    },
    "informe_subasta": {
        "etiqueta": "Informe de Subasta",
        "descripcion": "Informe consolidado del proceso de subasta de un bien. Las cifras de tráfico se traen solas desde la API de Clarity.",
        "modulo": informe_subasta,
        "disponible": False,
    },
    "declaracion_juramentada": {
        "etiqueta": "Declaración Juramentada",
        "descripcion": "Declaración juramentada de un participante de subasta. Se busca por cédula, NIT, FMI, código de subasta o de unidad.",
        "modulo": declaracion_juramentada,
        "disponible": True,
    },
}


def listar_disponibles() -> list[tuple[str, dict]]:
    return [(clave, t) for clave, t in TIPOS.items()]
