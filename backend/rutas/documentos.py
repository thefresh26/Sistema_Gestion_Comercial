"""
Módulo Documentos: generador de Actas, Certificados DD, etc.

A diferencia de los demás módulos (que consultan Supabase), este habla con
su propia base de datos (Neon, ver DATABASE_URL) para los datos y archivos
de cada caso, y con la base de negocio existente (solo lectura, ver
AZURE_DATABASE_URL) para tipos como el Certificado DD.

Aquí viven solo las rutas HTTP. La lógica de cada tipo de documento está
en `backend/generador/tipos/`, y las pantallas en
`frontend/documentos/plantillas/`.
"""
from __future__ import annotations

import io
import os
import re
import zipfile

from flask import (
    Blueprint,
    current_app,
    jsonify,
    redirect,
    render_template,
    request,
    send_file,
    send_from_directory,
    session,
    url_for,
)

from backend import config
from backend.generador import db
from backend.generador.tipos import TIPOS
from backend.permisos import requires_modulo
from backend.registro import obtener_ip_cliente, registrar_log

CARPETA = config.carpeta_modulo("documentos")

bp = Blueprint(
    "documentos",
    __name__,
    template_folder=os.path.join(CARPETA, "plantillas"),
)

MIME_DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
MIME_ZIP = "application/zip"


def _tipo_o_404(tipo: str):
    info = TIPOS.get(tipo)
    if not info or not info["disponible"]:
        return None
    return info


def _mime_type_por_nombre(nombre_archivo: str) -> str:
    """La mayoría de tipos de documento siempre generan un .docx, pero
    Declaración Juramentada puede entregar un .zip cuando encuentra varios
    participantes (una Declaración por cada uno). El mimetype debe
    corresponder al archivo real, o el navegador/Word no lo puede abrir."""
    if nombre_archivo.lower().endswith(".zip"):
        return MIME_ZIP
    return MIME_DOCX


# ── Pantallas ───────────────────────────────────────────────────────────

@bp.route("/documentos/")
@requires_modulo("documentos")
def index():
    return render_template("index.html", tipos=TIPOS)


@bp.route("/documentos/style.css")
@requires_modulo("documentos")
def style():
    return send_from_directory(CARPETA, "style.css")


@bp.route("/documentos/caso/<tipo>/<fmi>")
@requires_modulo("documentos")
def ver_caso(tipo: str, fmi: str):
    info = _tipo_o_404(tipo)
    if not info:
        return "Ese tipo de documento todavía no está disponible.", 404
    modulo = info["modulo"]

    caso = db.obtener_caso(fmi)
    if not caso:
        db.upsert_caso(fmi, {"estado": "pendiente", "pendientes": []})
        caso = db.obtener_caso(fmi)

    documentos = db.listar_documentos(fmi)
    documentos_fuente = [d for d in documentos if d["tipo"] != "documento_generado"]
    documentos_generados = [
        d for d in documentos
        if d["tipo"] == "documento_generado" and d["tipo_salida"] == tipo
    ]

    registrar_log("documentos", session.get("email"), "ver_caso", f"{tipo}:{fmi}", obtener_ip_cliente())

    return render_template(
        "caso.html",
        tipo=tipo,
        info=info,
        caso=caso,
        documentos_fuente=documentos_fuente,
        documentos_generados=documentos_generados,
        correcciones=db.obtener_correcciones(fmi),
        tipos_documento_fuente=modulo.TIPOS_DOCUMENTO_FUENTE,
        campos_editables=modulo.CAMPOS_EDITABLES,
        error=request.args.get("error"),
    )


# ── Búsqueda ────────────────────────────────────────────────────────────

@bp.route("/api/documentos/buscar")
@requires_modulo("documentos")
def buscar():
    termino = request.args.get("q", "").strip()
    tipo = request.args.get("tipo", "")

    # El Certificado DD es distinto a los demas tipos: un mismo FMI/codigo
    # de subasta puede tener VARIAS personas asociadas (cada oferente
    # necesita su propio certificado), mientras que la tabla local "casos"
    # esta pensada para 1 FMI = 1 caso -- por eso una busqueda por FMI solo
    # devolvia 1 fila aunque hubiera mas gente inscrita en esa subasta. Para
    # este tipo se resuelve en vivo contra la base de negocio en vez de
    # "casos", y se devuelve una fila por cada persona encontrada.
    if tipo == "certificado_dd" and termino and not termino.isdigit():
        from backend.generador.tipos.certificado_dd import buscar_participante
        try:
            participantes = buscar_participante(termino)
        except Exception:
            participantes = []
        resultados = []
        for p in participantes:
            identificador_doc = re.sub(r"\D", "", p["cedula"]) or p["cedula"]
            existente = db.obtener_documento_generado(identificador_doc, "certificado_dd")
            resultados.append({
                "fmi": identificador_doc,
                "arrendatario_nombre": p["nombre"],
                "direccion": f"C.C./NIT: {p['cedula']}",
                "documento_id": existente["id"] if existente else None,
                "estado": None,
            })
        return jsonify(resultados)

    return jsonify(db.buscar_casos(termino, tipo_salida=tipo or None))


@bp.route("/documentos/caso/<tipo>/<fmi>/oferentes")
@requires_modulo("documentos")
def oferentes(tipo: str, fmi: str):
    """Lista todos los oferentes inscritos en la subasta de este FMI,
    incluyendo al ganador -- a diferencia del Acta de Subasta, que solo
    incluye a quien tiene una puja con monto registrado. Sirve para
    diagnosticar casos donde el Acta sale "sin ganador": aqui se ve si
    el problema es que nadie quedo marcado como ganador en la base de
    datos, o si el ganador esta inscrito pero sin puja registrada."""
    if not _tipo_o_404(tipo):
        return jsonify({"error": "Ese tipo de documento todavía no está disponible."}), 404
    if tipo not in ("acta_subasta", "informe_subasta"):
        return jsonify({"error": "Este tipo de documento no tiene oferentes de subasta asociados."}), 400

    from backend.generador.tipos.acta_subasta import obtener_oferentes
    try:
        datos = obtener_oferentes(fmi)
    except ValueError as e:
        return jsonify({"error": str(e)}), 404

    registrar_log("documentos", session.get("email"), "ver_oferentes", f"{tipo}:{fmi}", obtener_ip_cliente())
    return jsonify(datos)


# ── Documentos fuente y correcciones ────────────────────────────────────

@bp.route("/documentos/caso/<tipo>/<fmi>/documentos", methods=["POST"])
@requires_modulo("documentos")
def subir_documento(tipo: str, fmi: str):
    if not _tipo_o_404(tipo):
        return "Ese tipo de documento todavía no está disponible.", 404
    tipo_fuente = request.form.get("tipo_fuente")
    archivo = request.files.get("archivo")
    if not tipo_fuente or not archivo or not archivo.filename:
        return redirect(url_for("documentos.ver_caso", tipo=tipo, fmi=fmi))

    db.guardar_documento(
        fmi, tipo_fuente, archivo.filename,
        archivo.mimetype or "application/octet-stream", archivo.read(),
    )
    registrar_log("documentos", session.get("email"), "subir_documento", f"{tipo}:{fmi}:{tipo_fuente}", obtener_ip_cliente())
    return redirect(url_for("documentos.ver_caso", tipo=tipo, fmi=fmi))


@bp.route("/documentos/caso/<tipo>/<fmi>/editar", methods=["POST"])
@requires_modulo("documentos")
def editar_correccion(tipo: str, fmi: str):
    campo = request.form.get("campo", "")
    valor = request.form.get("valor", "")
    nota = request.form.get("nota", "")
    if valor.strip():
        db.guardar_correccion(fmi, campo, valor.strip(), nota=nota, usuario=session.get("email", ""))
    else:
        db.borrar_correccion(fmi, campo)
    registrar_log("documentos", session.get("email"), "editar_correccion", f"{tipo}:{fmi}:{campo}", obtener_ip_cliente())
    return redirect(url_for("documentos.ver_caso", tipo=tipo, fmi=fmi))


# ── Generación y descarga ───────────────────────────────────────────────

def _guardar_generado(fmi: str, tipo: str, nombre_archivo: str, contenido: bytes) -> int:
    doc_id = db.guardar_documento(
        fmi, "documento_generado", nombre_archivo,
        _mime_type_por_nombre(nombre_archivo), contenido, tipo_salida=tipo,
    )
    db.registrar_generacion(fmi, doc_id, usuario=session.get("email", ""))
    registrar_log("documentos", session.get("email"), "generar", f"{tipo}:{fmi} -> {nombre_archivo}", obtener_ip_cliente())
    return doc_id


@bp.route("/documentos/caso/<tipo>/<fmi>/generar", methods=["POST"])
@requires_modulo("documentos")
def generar(tipo: str, fmi: str):
    info = _tipo_o_404(tipo)
    if not info:
        return "Ese tipo de documento todavía no está disponible.", 404

    try:
        contenido, nombre_archivo, _pendientes = info["modulo"].generar(fmi)
    except ValueError as e:
        # Dato de negocio no encontrado (ej. el FMI/código no tiene ninguna
        # subasta asociada) -- se muestra como mensaje en la ficha, no como
        # error 500 crudo.
        return redirect(url_for("documentos.ver_caso", tipo=tipo, fmi=fmi, error=str(e)))
    except Exception as e:
        # Cualquier otro fallo (consulta a la base de negocio, plantilla,
        # etc.) se registra completo en los logs para poder diagnosticarlo,
        # y se muestra un mensaje entendible en la ficha en vez de un 500
        # en blanco que no dice nada.
        current_app.logger.exception("Error generando documento %s para %s", tipo, fmi)
        return redirect(url_for(
            "documentos.ver_caso", tipo=tipo, fmi=fmi,
            error=f"No se pudo generar el documento: {e}",
        ))

    _guardar_generado(fmi, tipo, nombre_archivo, contenido)
    return redirect(url_for("documentos.ver_caso", tipo=tipo, fmi=fmi))


@bp.route("/documentos/caso/<tipo>/<fmi>/generar-descargar")
@requires_modulo("documentos")
def generar_descargar(tipo: str, fmi: str):
    """Flujo directo desde la búsqueda: genera (si hace falta) y descarga
    el documento de una sola vez, sin pasar por la ficha del caso ni por
    el botón 'Generar ahora'."""
    info = _tipo_o_404(tipo)
    if not info:
        return "Ese tipo de documento todavía no está disponible.", 404

    existente = db.obtener_documento_generado(fmi, tipo)
    if existente:
        registrar_log("documentos", session.get("email"), "descargar", f"{tipo}:{fmi}", obtener_ip_cliente())
        return send_file(
            io.BytesIO(existente["contenido"]),
            mimetype=existente["mime_type"],
            as_attachment=True,
            download_name=existente["nombre_archivo"],
        )

    # Ojo: esta ruta la llama SIEMPRE el frontend via fetch() (nunca
    # navegacion directa), asi que ante un fallo se responde JSON + codigo
    # de error (para que fetch vea res.ok = false) en vez de un redirect:
    # un redirect aqui terminaria "descargando" la pagina HTML de la ficha
    # como si fuera el documento, sin avisar a nadie que algo fallo.
    try:
        contenido, nombre_archivo, _pendientes = info["modulo"].generar(fmi)
    except ValueError as e:
        return jsonify({"error": str(e)}), 404
    except Exception as e:
        current_app.logger.exception("Error generando documento %s para %s", tipo, fmi)
        return jsonify({"error": f"No se pudo generar el documento: {e}"}), 500

    # La columna documentos.fmi tiene una llave foranea hacia casos(fmi):
    # si nadie paso antes por la ficha del caso (ver_caso, que si crea esa
    # fila), este INSERT fallaba con un ForeignKeyViolation -- un 500 en
    # blanco, porque este flujo de "generar y descargar de una vez desde
    # la busqueda" es justamente el que se salta la ficha.
    if not db.obtener_caso(fmi):
        db.upsert_caso(fmi, {"estado": "pendiente", "pendientes": []})

    _guardar_generado(fmi, tipo, nombre_archivo, contenido)

    return send_file(
        io.BytesIO(contenido),
        mimetype=_mime_type_por_nombre(nombre_archivo),
        as_attachment=True,
        download_name=nombre_archivo,
    )


@bp.route("/documentos/documento/<int:doc_id>")
@requires_modulo("documentos")
def descargar(doc_id: int):
    documento = db.obtener_documento(doc_id)
    if not documento:
        return "Documento no encontrado", 404
    return send_file(
        io.BytesIO(documento["contenido"]),
        mimetype=documento["mime_type"],
        as_attachment=True,
        download_name=documento["nombre_archivo"],
    )


@bp.route("/documentos/descargar-varios")
@requires_modulo("documentos")
def descargar_varios():
    """Descarga en un solo .zip varios documentos ya generados, para
    cuando la búsqueda trajo muchos casos a la vez -- así no hay que
    entrar caso por caso a descargar uno por uno."""
    ids = [int(x) for x in request.args.get("ids", "").split(",") if x.strip().isdigit()]
    if not ids:
        return "No se especificó ningún documento para descargar.", 400

    buffer = io.BytesIO()
    nombres_usados: set[str] = set()
    incluidos = 0
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for doc_id in ids:
            documento = db.obtener_documento(doc_id)
            if not documento:
                continue
            nombre = documento["nombre_archivo"]
            base, ext = os.path.splitext(nombre)
            candidato, n = nombre, 1
            while candidato in nombres_usados:
                candidato = f"{base}_{n}{ext}"
                n += 1
            nombres_usados.add(candidato)
            zf.writestr(candidato, documento["contenido"])
            incluidos += 1

    if incluidos == 0:
        return "Ninguno de los documentos solicitados existe.", 404

    buffer.seek(0)
    registrar_log("documentos", session.get("email"), "descargar_varios", f"{incluidos} documento(s)", obtener_ip_cliente())
    return send_file(
        buffer,
        mimetype=MIME_ZIP,
        as_attachment=True,
        download_name="documentos.zip",
    )
