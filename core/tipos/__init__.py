"""
Catálogo de tipos de documento que el sistema puede generar. Cada tipo es
un módulo independiente (su propia plantilla, sus propios campos, su
propia lógica de extracción) registrado aquí -- así la interfaz puede
mostrar un filtro "¿qué quieres generar?" y cada tipo se agrega sin tocar
los demás.

Para agregar un tipo nuevo:
  1. Crear app/tipos/<clave>.py con las funciones `generar(fmi, contexto)`
     y la lista `CAMPOS_EDITABLES`.
  2. Registrarlo abajo en TIPOS con su etiqueta y estado.
"""
from __future__ import annotations

from . import acta_arrendamiento
from . import certificado_dd
from . import acta_alcance

TIPOS = {
    "acta_arrendamiento": {
        "etiqueta": "Acta de Arrendamiento",
        "descripcion": "Comité de arrendamiento: aprueba el arrendatario y el canon de un inmueble.",
        "modulo": acta_arrendamiento,
        "disponible": True,
    },
    "certificado_dd": {
        "etiqueta": "Certificado de Resultado DD",
        "descripcion": "Certificado de debida diligencia sobre un tercero (persona o empresa). Se busca por cédula, NIT, FMI, código de subasta o de unidad.",
        "modulo": certificado_dd,
        "disponible": True,
    },
    "acta_alcance": {
        "etiqueta": "Acta de Alcance",
        "descripcion": "Acta de alcance de un proceso o paquete de bienes. Requiere subir primero el Acta vieja del proceso.",
        "modulo": acta_alcance,
        "disponible": True,
    },
    "acta_subasta": {
        "etiqueta": "Acta de Certificación de Subasta Electrónica",
        "descripcion": "Certifica el resultado de una subasta electrónica.",
        "modulo": None,
        "disponible": False,
    },
    "informe_subasta": {
        "etiqueta": "Informe de Subasta",
        "descripcion": "Informe consolidado del proceso de subasta de un bien.",
        "modulo": None,
        "disponible": False,
    },
}


def listar_disponibles() -> list[tuple[str, dict]]:
    return [(clave, t) for clave, t in TIPOS.items()]
