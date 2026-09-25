"""
Tipo de documento: Certificado de Resultado DD (Debida Diligencia).

A diferencia de las Actas de Arrendamiento, este NO se arma con PDFs
subidos por alguien -- los datos ya viven en la base de datos de negocio
existente (subastas, participantes, terceros). El "FMI" que se busca aquí
puede ser en realidad una cédula, un NIT, un código de subasta, un FMI de
inmueble o un código de unidad inmobiliaria (UNI-XXXX-AAAA); se resuelve
igual que en el script original `generar_certificados_dd.py`.

Ojo: esta conexión (AZURE_DATABASE_URL) es de SOLO LECTURA -- este
sistema nunca escribe en la base de datos de negocio, solo consulta.
"""
from __future__ import annotations

import re
import zipfile
import io
import os

from core import db

RAIZ_PROYECTO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # sin cambios: sigue siendo 3 niveles arriba
RUTA_PLANTILLA = os.path.join(RAIZ_PROYECTO, "word_templates", "002_CERTIFICADO_RESULTADO_DD.docx")

TIPOS_DOCUMENTO_FUENTE: dict[str, str] = {}  # este tipo no usa documentos subidos a mano

CAMPOS_EDITABLES = [
    ("nombre", "Nombre del participante"),
    ("cedula", "Cédula / NIT"),
    ("id_puja", "Número de puja"),
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


def _participantes_desde_cedula(conn, identificacion: str) -> list[dict]:
    solo_digitos = re.sub(r"\D", "", identificacion)
    fila = conn.execute(
        """
        SELECT id, nombre_principal, identificacion_numero, identificacion_tipo
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

    puja = conn.execute(
        """
        SELECT ap.id
        FROM polibid_credentials pc
        JOIN polybid.auction_participants ap ON ap.client_id = pc.client_id
        LEFT JOIN polybid.auctions a ON a.id = ap.auction_id
        WHERE pc.contact_tercero_id = %(id)s
        ORDER BY a.start_date DESC NULLS LAST
        LIMIT 1
        """,
        {"id": fila["id"]},
    ).fetchone()

    return [{
        "nombre": (fila["nombre_principal"] or "—").upper(),
        "cedula": str(fila["identificacion_numero"] or "—"),
        "id_puja": str(puja["id"]) if puja else "—",
    }]


def _participantes_de_subasta(conn, auction_uuid: str) -> list[dict]:
    # LEFT JOIN a proposito: con JOIN normal, cualquier inscrito cuyo
    # client_id no tuviera credenciales vinculadas (o cuyo tercero no
    # estuviera enlazado) desaparecia en silencio de la lista, aunque SI
    # estuviera inscrito en la subasta -- por eso a veces "no traia a
    # todos" los participantes de un FMI.
    filas = conn.execute(
        """
        SELECT ap.id AS puja_id, ap.client_id, ct.nombre_principal,
               ct.identificacion_numero, ct.identificacion_tipo
        FROM polybid.auction_participants ap
        LEFT JOIN polibid_credentials pc ON pc.client_id = ap.client_id
        LEFT JOIN contact_terceros ct ON ct.id = pc.contact_tercero_id
        WHERE ap.auction_id = %(id)s::uuid
        """,
        {"id": auction_uuid},
    ).fetchall()
    return [{
        "nombre": (f["nombre_principal"] or "Sin nombre registrado").upper(),
        "cedula": str(f["identificacion_numero"] or "—"),
        "id_puja": str(f["puja_id"]) if f["puja_id"] is not None else "—",
    } for f in filas]


def _colapsar(xml: str) -> str:
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
        "##id_puja##": participante["id_puja"],
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


def generar(fmi: str) -> tuple[bytes, str, list[str]]:
    """`fmi` aquí es en realidad el identificador (cédula, NIT, FMI,
    código de subasta o unidad). Si resuelve a más de un participante,
    por ahora se genera el primero -- se puede refinar la interfaz más
    adelante para elegir entre varios, igual que hacía el script original
    por consola."""
    participantes = buscar_participante(fmi)
    if not participantes:
        raise ValueError(
            f"No se encontró ninguna persona, empresa, subasta, FMI ni unidad "
            f"inmobiliaria con el identificador '{fmi}'."
        )
    pendientes = []
    if len(participantes) > 1:
        pendientes.append(
            f"Se encontraron {len(participantes)} participantes para este identificador; "
            f"se generó el del primero de la lista ({participantes[0]['nombre']}). "
            f"Revisa si necesitas alguno de los otros."
        )
    p = participantes[0]
    contenido = _generar_docx_bytes(p)
    nombre_corto = p["nombre"].replace(" ", "_")[:30]
    nombre_archivo = f"DD_{fmi}_{nombre_corto}.docx"
    return contenido, nombre_archivo, pendientes
