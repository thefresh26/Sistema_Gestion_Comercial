"""
Tipo de documento: Acta de Arrendamiento.

Envuelve la lógica ya probada de extracción (app/extraction.py) y
generación (app/generator.py) bajo la interfaz común que espera el
catálogo de tipos (app/tipos/__init__.py), para que el sistema pueda
ofrecer varios tipos de documento sin mezclar su lógica.
"""
from __future__ import annotations

from core import db
from core.extraction import extraer_datos_arrendatario, extraer_de_estimado_renta
from core.generator import generar_acta

CLAVE = "acta_arrendamiento"

TIPOS_DOCUMENTO_FUENTE = {
    "estimado_renta": "Estimado de Renta",
    "aprobado_poliza": "Aprobado / Póliza",
    "solicitud_arrendamiento": "Solicitud de Arrendamiento",
    "carta_juramentada": "Carta / Declaración Juramentada",
    "sagrilaft": "SAGRILAFT aprobado",
    "foto_inmueble": "Foto del inmueble",
}

CAMPOS_EDITABLES = [
    ("arrendatario_nombre", "Nombre del arrendatario"),
    ("id_siglas", "C.C. o NIT"),
    ("id_numero", "Número de identificación"),
    ("id_ciudad", "Ciudad de expedición"),
    ("direccion", "Dirección del inmueble"),
    ("tipo_bien", "Tipo de bien"),
    ("descripcion", "Descripción del inmueble"),
]


def generar(fmi: str) -> tuple[bytes, str, list[str]]:
    """Genera el Acta para el FMI dado, usando los documentos de origen ya
    subidos a la base de datos y las correcciones manuales guardadas.
    Devuelve (contenido_docx, nombre_archivo, pendientes)."""
    caso = db.obtener_caso(fmi) or {}
    pendientes: list[str] = []

    candidatos = []
    for tipo in ("aprobado_poliza", "solicitud_arrendamiento", "carta_juramentada"):
        doc = db.obtener_ultimo_documento(fmi, tipo)
        if doc:
            candidatos.append((tipo, doc["contenido"]))

    datos_arrendatario, _fuente = extraer_datos_arrendatario(candidatos)
    if not datos_arrendatario:
        datos_arrendatario = {}
        pendientes.append(
            "No se encontró el documento de Aprobado/Póliza del arrendatario "
            "(ni Solicitud de Arrendamiento ni Carta Juramentada legible); "
            "nombre y cédula/NIT quedaron en blanco, revisar y completar a mano."
        )

    datos_inmueble = {"direccion": "—", "tipo_bien": "—", "descripcion": None}
    doc_estimado = db.obtener_ultimo_documento(fmi, "estimado_renta")
    if doc_estimado:
        datos_inmueble = extraer_de_estimado_renta(doc_estimado["contenido"])
    else:
        pendientes.append("No se subió el Estimado de Renta; dirección y tipo de bien quedaron en blanco.")

    datos = {
        "fmi": fmi,
        "territorial": caso.get("territorial"),
        "tipo_contrato": caso.get("tipo_contrato") or "CONTRATO VIVIENDA",
        **datos_inmueble,
        **datos_arrendatario,
    }
    correcciones = db.obtener_correcciones(fmi)
    datos.update(correcciones)

    fotos = [d["contenido"] for d in [
        db.obtener_documento(row["id"]) for row in db.listar_documentos(fmi, "foto_inmueble")
    ]]
    doc_sagrilaft = db.obtener_ultimo_documento(fmi, "sagrilaft")

    contenido = generar_acta(
        datos,
        fotos_inmueble=fotos,
        foto_sagrilaft=doc_sagrilaft["contenido"] if doc_sagrilaft else None,
    )
    nombre_archivo = f"ACTA_ARRENDAMIENTO_{fmi}.docx"

    estado = "con_observaciones" if pendientes else "completo"
    db.upsert_caso(fmi, {**datos, "estado": estado, "pendientes": pendientes})

    return contenido, nombre_archivo, pendientes
