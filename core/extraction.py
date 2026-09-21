"""
Lógica de extracción de datos desde los PDFs de cada caso.

Es una adaptación del script original `generar_acta_arrendamiento.py`
(que corre localmente en el computador y lee archivos de una carpeta) a
esta versión web: en vez de recibir una ruta de archivo (Path), cada
función recibe los BYTES del PDF (tal como se leyeron de la base de
datos) y trabaja sobre ellos en memoria con io.BytesIO.

La lógica de las expresiones regulares es la misma, ya probada contra
casos reales durante el desarrollo del script original.
"""
from __future__ import annotations

import io
import re

import pdfplumber


def _texto_pdf(contenido_pdf: bytes) -> str:
    """Extrae el texto de un PDF (todas las páginas). Si el PDF es un
    escaneo sin texto, devuelve cadena vacía -- OCR queda fuera de esta
    primera versión web (se puede agregar después con pytesseract, igual
    que en el script original)."""
    try:
        with pdfplumber.open(io.BytesIO(contenido_pdf)) as pdf:
            partes = [pagina.extract_text() or "" for pagina in pdf.pages]
        return "\n".join(partes)
    except Exception:
        return ""


def _normalizar_siglas_id(etiqueta: str | None, numero: str = "") -> str:
    if etiqueta and etiqueta.strip().upper().replace(".", "").startswith("NIT"):
        return "NIT"
    if etiqueta:
        return "C.C."
    if numero and re.search(r"-\d\s*$", numero.strip()):
        return "NIT"
    return "C.C."


def _limpiar_descripcion_cadastral(texto: str) -> str:
    """Corta el texto si aparece un bloque de nomenclatura catastral con
    las letras separadas por espacios (ej. 'N o m e n c l a'), que
    algunos PDF traen pegado al final de la descripción real."""
    m = re.search(r"(?:\b[A-Za-zÀ-ÿ]\s){5,}[A-Za-zÀ-ÿ]\b", texto)
    if m and m.start() > 50:
        return texto[: m.start()].strip()
    return texto


def extraer_de_aprobado(contenido_pdf: bytes) -> dict | None:
    """Formato 'DATOS DEL ARRENDATARIO / <NOMBRE> / (NIT|CC|C.C.):<NUM>'."""
    texto = _texto_pdf(contenido_pdf)
    m = re.search(
        r"DATOS\s+DEL\s+ARRENDATARIO\s*\n\s*([A-ZÑÁÉÍÓÚ\s.,&]+?)\s*\n\s*"
        r"(NIT|C\.?C\.?)\s*:?\s*([\d.\-]+)",
        texto, re.IGNORECASE,
    )
    if not m:
        return None
    nombre, etiqueta, numero = m.groups()
    return {
        "arrendatario_nombre": nombre.strip(),
        "id_numero": numero.strip(),
        "id_siglas": _normalizar_siglas_id(etiqueta, numero),
        "id_ciudad": None,
    }


def extraer_de_solicitud_arrendamiento(contenido_pdf: bytes) -> dict | None:
    texto = _texto_pdf(contenido_pdf)
    m = re.search(
        r"Yo\s+([A-ZÑÁÉÍÓÚ\s]+?)\s+identificad[oa]\s*\(?a?\)?\s*con\s+el\s+documento\s+de\s+identidad\s+"
        r"C\.C\.\s*(X)?\s*,\s*C\.E\.\s*(X)?\s*,?\s*NIT\s*No\.\s*([\d.\-]+)\s+expedido\s+en\s*"
        r"(?:la\s+ciudad\s+de\s*)?([A-ZÑÁÉÍÓÚ,.\s]+?),\s*actuando",
        texto, re.IGNORECASE,
    )
    if not m:
        return None
    nombre, marca_cc, marca_ce, numero, ciudad = m.groups()
    etiqueta = "C.E." if (marca_ce and not marca_cc) else ("C.C." if marca_cc else None)
    return {
        "arrendatario_nombre": nombre.strip(),
        "id_numero": numero.strip(),
        "id_siglas": _normalizar_siglas_id(etiqueta, numero),
        "id_ciudad": re.sub(r"\s+", " ", ciudad).strip(" ,."),
    }


def extraer_de_carta_juramentada(contenido_pdf: bytes) -> dict | None:
    texto = _texto_pdf(contenido_pdf).replace("_", "")
    m = re.search(
        r"Yo,?\s+([A-Za-zÀ-ÿ\s]+?),?\s+identificad[oa]\s*\(?a?\)?\s*con\s+"
        r"(Cedula de ciudadan[íi]a\]?|documento de identidad n[uú]mero|C\.C\.?|CC|NIT)\.?\s*(?:No\.?)?\s*"
        r"([\d.\-]+)\s+de\s+([A-Za-zÀ-ÿ,\s]+?)\s*,?\s*actuando",
        texto, re.IGNORECASE,
    )
    if not m:
        return None
    nombre, tipo_doc, numero, ciudad = m.groups()
    etiqueta = "NIT" if "NIT" in tipo_doc.upper() else "C.C."
    return {
        "arrendatario_nombre": re.sub(r"\s+", " ", nombre).strip().upper(),
        "id_numero": numero.strip(),
        "id_siglas": _normalizar_siglas_id(etiqueta, numero),
        "id_ciudad": re.sub(r"\s+", " ", ciudad).strip(" ,."),
    }


def extraer_datos_arrendatario(candidatos: list[tuple[str, bytes]]) -> tuple[dict | None, str | None]:
    """Prueba cada documento candidato (en orden de preferencia) hasta que
    uno funcione. `candidatos` es una lista de (tipo_documento, bytes).
    Devuelve (datos, tipo_documento_usado) o (None, None) si ninguno dio
    resultado (ej. todos son escaneos sin texto)."""
    extractores = {
        "aprobado_poliza": extraer_de_aprobado,
        "solicitud_arrendamiento": extraer_de_solicitud_arrendamiento,
        "carta_juramentada": extraer_de_carta_juramentada,
    }
    for tipo, contenido in candidatos:
        extractor = extractores.get(tipo)
        if not extractor:
            continue
        datos = extractor(contenido)
        if datos:
            return datos, tipo
    return None, None


def extraer_de_estimado_renta(contenido_pdf: bytes) -> dict:
    """Saca dirección, tipo de bien y descripción del Estimado de Renta.
    Cubre el formato de tabla ('DESCRIPCIÓN' como fila) y cae de vuelta a
    los patrones de texto plano si no encuentra la tabla."""
    resultado = {"direccion": "—", "tipo_bien": "—", "descripcion": None}

    # 1. Intento por tabla (formato "Dictamen Comercial y Financiero").
    try:
        with pdfplumber.open(io.BytesIO(contenido_pdf)) as pdf:
            page = pdf.pages[0]
            tablas = page.find_tables()
            for fila in (tablas[0].rows if tablas else []):
                celdas = [c for c in fila.cells if c]
                if len(celdas) < 2:
                    continue
                etiqueta = (page.crop(celdas[0]).extract_text(x_tolerance=1) or "").strip().upper()
                if etiqueta in ("DESCRIPCIÓN", "DESCRIPCION"):
                    contenido = page.crop(celdas[1]).extract_text(x_tolerance=1) or ""
                    texto = " ".join(l.strip() for l in contenido.split("\n") if l.strip())
                    resultado["descripcion"] = _limpiar_descripcion_cadastral(texto)
    except Exception:
        pass

    texto = _texto_pdf(contenido_pdf)

    m = re.search(r"DIRECCI[ÓO]N\s+(?!General\b)([^\n]+)", texto, re.IGNORECASE)
    if m:
        resultado["direccion"] = m.group(1).strip()
    else:
        m = re.search(r"Ubicaci[oó]n\s*:?\s*([^\n]+)", texto, re.IGNORECASE)
        if m:
            resultado["direccion"] = m.group(1).strip()

    m = re.search(r"TIPO\s+DE\s+(?:BIEN|INMUEBLE)\s*:?\s*([^\n]+)", texto, re.IGNORECASE)
    if m:
        resultado["tipo_bien"] = m.group(1).strip().upper()

    return resultado
