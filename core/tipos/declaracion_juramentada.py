"""
Tipo de documento: Declaración Juramentada de un participante de subasta.

Igual que el Certificado de Resultado DD, esto NO se arma con archivos
subidos por alguien -- los datos ya viven en la base de datos de negocio
existente (subastas, participantes, terceros). El "FMI" que se busca aquí
puede ser en realidad una cédula, un NIT, un código de subasta, un FMI de
inmueble o un código de unidad inmobiliaria (UNI-XXXX-AAAA); se resuelve
igual que en el script original `generar_juramentadas.py`.

Ojo: esta conexión (AZURE_DATABASE_URL) es de SOLO LECTURA -- este
sistema nunca escribe en la base de datos de negocio, solo consulta.
"""
from __future__ import annotations

import re
import zipfile
import io
import os

from core import db

RAIZ_PROYECTO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # 3 niveles arriba, igual que certificado_dd.py
RUTA_PLANTILLA = os.path.join(RAIZ_PROYECTO, "word_templates", "003_FORMATO_DECLARACION_JURAMENTADA_FO_GP_008.docx")

TIPOS_DOCUMENTO_FUENTE: dict[str, str] = {}  # este tipo no usa documentos subidos a mano

CAMPOS_EDITABLES = [
    ("nombre", "Nombre"),
    ("cedula", "Cédula / NIT"),
    ("ciudad_cedula", "Ciudad de expedición"),
    ("fecha", "Fecha de diligenciamiento"),
]


def _es_uuid(identificador: str) -> bool:
    return bool(re.match(
        r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
        identificador.lower(),
    ))


def _resolver_auction_uuid(conn, identificador: str) -> str | None:
    if _es_uuid(identificador):
        return identificador
    fila = conn.execute(
        "SELECT id FROM polybid.auctions WHERE code = %(c)s LIMIT 1",
        {"c": identificador},
    ).fetchone()
    if fila:
        return str(fila["id"])
    return None


def _resolver_por_inmueble(conn, identificador: str) -> str | None:
    """Busca el identificador como FMI/código de inmueble/unidad, y
    devuelve el UUID de subasta más reciente asociado. Si hay varias
    subastas, se toma la más reciente automáticamente (a diferencia del
    script de consola original, aquí no hay un usuario esperando en la
    terminal para elegir)."""
    filas = conn.execute(
        """
        SELECT id, grupo_id FROM mst_inmuebles
        WHERE UPPER(numero_matricula) = UPPER(%(id)s)
           OR UPPER(codigo) = UPPER(%(id)s)
           OR UPPER(codigo_grupo) = UPPER(%(id)s)
           OR UPPER(referencia) = UPPER(%(id)s)
        """,
        {"id": identificador},
    ).fetchall()
    if not filas:
        return None
    inmueble_ids = sorted({f["id"] for f in filas if f["id"] is not None})
    grupo_ids = sorted({f["grupo_id"] for f in filas if f["grupo_id"] is not None})

    candidatos = conn.execute(
        """
        SELECT DISTINCT
            COALESCE(a.id, psv.auction_id) AS auction_id,
            COALESCE(a.start_date, psv.fecha_inicio) AS start_date
        FROM polibid_subastas_v2 psv
        LEFT JOIN polybid.auctions a ON a.id = psv.auction_id
        WHERE psv.inmueble_id = ANY(%(inm)s)
           OR (psv.grupo_id IS NOT NULL AND psv.grupo_id = ANY(%(grp)s))
        ORDER BY start_date DESC NULLS LAST
        """,
        {"inm": inmueble_ids or [-1], "grp": grupo_ids or [-1]},
    ).fetchall()
    if not candidatos:
        return None
    return str(candidatos[0]["auction_id"])


def _formatear_fecha(fecha) -> str:
    if not fecha:
        return "—"
    return f"{fecha.day:02d}/{fecha.month:02d}/{fecha.year}"


def _participantes_desde_cedula(conn, identificacion: str) -> list[dict]:
    solo_digitos = re.sub(r"\D", "", identificacion)
    fila = conn.execute(
        """
        SELECT nombre_principal, identificacion_numero, identificacion_tipo,
               lugar_expedicion_doc, ciudad, fecha_diligenciamiento
        FROM contact_terceros
        WHERE regexp_replace(identificacion_numero, '\\D', '', 'g') = %(d)s
           OR regexp_replace(identificacion_numero, '\\D', '', 'g') LIKE %(d)s || '_'
        ORDER BY (identificacion_tipo = 'NIT') DESC
        LIMIT 1
        """,
        {"d": solo_digitos},
    ).fetchone()
    if not fila:
        return []

    ciudad_cedula = fila["ciudad"] if fila["identificacion_tipo"] == "NIT" else (fila["lugar_expedicion_doc"] or "—")
    return [{
        "nombre": (fila["nombre_principal"] or "—").upper(),
        "cedula": str(fila["identificacion_numero"] or "—"),
        "ciudad_cedula": ciudad_cedula or "—",
        "fecha": _formatear_fecha(fila["fecha_diligenciamiento"]),
    }]


def _participantes_de_subasta(conn, auction_uuid: str) -> list[dict]:
    filas = conn.execute(
        """
        SELECT ct.nombre_principal, ct.identificacion_numero, ct.identificacion_tipo,
               ct.lugar_expedicion_doc, ct.ciudad, ct.fecha_diligenciamiento
        FROM polybid.auction_participants ap
        JOIN polibid_credentials pc ON pc.client_id = ap.client_id
        JOIN contact_terceros ct ON ct.id = pc.contact_tercero_id
        WHERE ap.auction_id = %(id)s::uuid
        ORDER BY ap.created_at
        """,
        {"id": auction_uuid},
    ).fetchall()
    resultado = []
    for f in filas:
        ciudad_cedula = f["ciudad"] if f["identificacion_tipo"] == "NIT" else (f["lugar_expedicion_doc"] or "—")
        resultado.append({
            "nombre": (f["nombre_principal"] or "—").upper(),
            "cedula": str(f["identificacion_numero"] or "—"),
            "ciudad_cedula": ciudad_cedula or "—",
            "fecha": _formatear_fecha(f["fecha_diligenciamiento"]),
        })
    return resultado


def _colapsar(xml: str) -> str:
    """Une en un solo <w:t> los marcadores ##...## que Word haya partido
    en varios <w:r> -- igual que en certificado_dd.py."""
    xml = re.sub(
        r'<w:t>##</w:t></w:r><w:r[^>]*><w:rPr>.*?</w:rPr><w:t>([^<#]+)</w:t></w:r><w:r[^>]*><w:rPr>.*?</w:rPr><w:t>##</w:t></w:r>',
        r'<w:t>##\1##</w:t></w:r>', xml, flags=re.DOTALL,
    )
    xml = re.sub(
        r'<w:t>##([^<#]+)#</w:t></w:r><w:proofErr[^/]*/><w:r[^>]*><w:t[^>]*>#\s*</w:t></w:r>',
        r'<w:t>##\1##</w:t></w:r>', xml, flags=re.DOTALL,
    )
    xml = re.sub(r'<w:t>([^<]+)</w:r>', r'<w:t>\1</w:t></w:r>', xml)
    return xml


def _generar_docx_bytes(participante: dict) -> bytes:
    with zipfile.ZipFile(RUTA_PLANTILLA, "r") as zin:
        archivos = {name: zin.read(name) for name in zin.namelist()}

    doc_xml = archivos["word/document.xml"].decode("utf-8")
    doc_xml = _colapsar(doc_xml)
    for marcador, valor in {
        "##nombre##": participante["nombre"],
        "##cedula##": participante["cedula"],
        "##ciudad_cedula##": participante["ciudad_cedula"],
        "##fecha##": participante["fecha"],
    }.items():
        doc_xml = doc_xml.replace(marcador, valor)
    archivos["word/document.xml"] = doc_xml.encode("utf-8")

    salida = io.BytesIO()
    with zipfile.ZipFile(salida, "w", zipfile.ZIP_DEFLATED) as zout:
        for nombre, contenido in archivos.items():
            zout.writestr(nombre, contenido)
    return salida.getvalue()


def buscar_participante(identificador: str) -> list[dict]:
    """Busca participante(s) para el identificador dado (cédula/NIT,
    código de subasta, FMI o código de unidad). No genera nada todavía,
    solo resuelve quién(es) aplicarían -- para mostrar en la interfaz
    antes de generar."""
    identificador = identificador.strip()
    with db.get_conn_negocio() as conn:
        if identificador.isdigit():
            return _participantes_desde_cedula(conn, identificador)
        auction_uuid = _resolver_auction_uuid(conn, identificador) or _resolver_por_inmueble(conn, identificador)
        if not auction_uuid:
            return []
        return _participantes_de_subasta(conn, auction_uuid)


def _nombre_archivo_participante(fmi: str, p: dict, usados: set[str]) -> str:
    """Arma el nombre de archivo de un participante incluyendo su nombre,
    evitando que dos participantes con el mismo nombre truncado se
    sobrescriban entre sí dentro del mismo ZIP."""
    nombre_corto = p["nombre"].replace(" ", "_")[:30]
    base = f"JURA_{fmi}_{nombre_corto}"
    nombre_archivo = f"{base}.docx"
    contador = 2
    while nombre_archivo in usados:
        nombre_archivo = f"{base}_{contador}.docx"
        contador += 1
    usados.add(nombre_archivo)
    return nombre_archivo


def generar(fmi: str) -> tuple[bytes, str, list[str]]:
    """`fmi` aquí es en realidad el identificador (cédula, NIT, FMI,
    código de subasta o unidad). Si resuelve a un solo participante, se
    devuelve su .docx directamente; si resuelve a varios (por ejemplo, al
    buscar por FMI/código de subasta en vez de por cédula), se genera UNA
    Declaración Juramentada por cada uno y se entregan todas juntas en un
    .zip, cada archivo nombrado con el participante correspondiente."""
    participantes = buscar_participante(fmi)
    if not participantes:
        raise ValueError(
            f"No se encontró ninguna persona, empresa, subasta, FMI ni unidad "
            f"inmobiliaria con el identificador '{fmi}'."
        )

    if len(participantes) == 1:
        p = participantes[0]
        contenido = _generar_docx_bytes(p)
        nombre_archivo = _nombre_archivo_participante(fmi, p, set())
        return contenido, nombre_archivo, []

    usados: set[str] = set()
    salida_zip = io.BytesIO()
    with zipfile.ZipFile(salida_zip, "w", zipfile.ZIP_DEFLATED) as zf:
        for p in participantes:
            contenido_docx = _generar_docx_bytes(p)
            nombre_interno = _nombre_archivo_participante(fmi, p, usados)
            zf.writestr(nombre_interno, contenido_docx)

    nombres = ", ".join(p["nombre"] for p in participantes)
    pendientes = [
        f"Se encontraron {len(participantes)} participantes para este identificador "
        f"({nombres}); se generó una Declaración Juramentada por cada uno, incluidas "
        f"todas en este .zip."
    ]
    nombre_zip = f"JURA_{fmi}_{len(participantes)}_participantes.zip"
    return salida_zip.getvalue(), nombre_zip, pendientes
