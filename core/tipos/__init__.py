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

from . import certificado_dd
from . import acta_subasta
from . import informe_subasta
from . import declaracion_juramentada

# Acta de Arrendamiento y Acta de Alcance quedaron fuera a propósito: son
# procesos que el usuario sigue haciendo manualmente (fuera de este
# sistema), no dependen de ninguna base de datos que este módulo pueda
# consultar solo. El código sigue en core/tipos/acta_arrendamiento.py y
# core/tipos/acta_alcance.py por si se quieren reactivar más adelante --
# solo hace falta volver a importarlos y agregarlos aquí abajo.

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
