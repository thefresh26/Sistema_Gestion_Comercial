"""
Tipo de documento: Acta de Certificación de Subasta Electrónica.

Port del script original `generar_acta.py` (scraping de fechas incluido,
tal como el usuario pidió mantenerlo igual). Diferencias frente al script
de consola original:

  - No pide nada por consola: si un FMI/unidad tiene varias subastas
    asociadas, se usa automáticamente la más reciente (igual que ya se
    hace en `certificado_dd.py` y `acta_alcance.py`), en vez de listarlas
    y esperar que alguien elija en una terminal que aquí no existe.
  - La conexión a la base de datos de negocio (AZURE_DATABASE_URL) se abre
    en modo "tupla" (`db.get_conn_negocio_tuplas()`), no en modo
    diccionario, para poder reutilizar el código del script original casi
    sin cambios (`row[0]`, `row[1]`, ...). Sigue siendo de SOLO LECTURA.
  - En vez de `core.get_connection` + `fetch_informe` (la capa de conexión
    vieja, con `vault.py`/`local.conf`), se consulta `polybid.auctions`
    directamente para el status/fechas/precio de la subasta y el ganador
    se resuelve con la misma lógica que `acta_alcance.py`.

El scraping de fechas (Selenium + Chrome headless) se mantiene EXACTAMENTE
igual al script original: navega a la página pública del inmueble/unidad
en activosporcolombia.com y lee el cronograma. Esto requiere que el
servidor tenga Chrome/Chromium instalado (ver Dockerfile).
"""
from __future__ import annotations

import re
import time
import zipfile
import io
import os

from core import db

RAIZ_PROYECTO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
RUTA_PLANTILLA = os.path.join(
    RAIZ_PROYECTO, "word_templates", "ACTA_DE_CERTIFICACIÓN_DE_SUBASTA_ELECTRÓNICA.docx"
)

TIPOS_DOCUMENTO_FUENTE: dict[str, str] = {}  # no usa documentos subidos a mano

CAMPOS_EDITABLES = [
    ("fecha_publicacion", "Fecha de publicación"),
    ("fecha_inicio", "Fecha de apertura"),
    ("fecha_fin", "Fecha de cierre"),
    ("nombre_ganador", "Oferente ganador"),
    ("cedula_ganador", "Cédula/NIT del ganador"),
]


# ---------------------------------------------------------------------
# Resolver identificador -> UUID de subasta
# ---------------------------------------------------------------------

def _es_uuid(identificador: str) -> bool:
    return bool(re.match(
        r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
        identificador.lower(),
    ))


def _resolver_uuid(conn, identificador: str) -> str | None:
    if _es_uuid(identificador):
        return identificador
    with conn.cursor() as cur:
        cur.execute("SELECT id FROM polybid.auctions WHERE code = %s LIMIT 1", (identificador,))
        row = cur.fetchone()
        if row:
            return str(row[0])
    return None


def _codigo_unidad_de_grupo(conn, grupo_id_val) -> str | None:
    if not grupo_id_val:
        return None
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT codigo_grupo FROM mst_inmuebles
            WHERE grupo_id = %s AND codigo_grupo IS NOT NULL
            ORDER BY es_padre DESC, id LIMIT 1
            """,
            (grupo_id_val,),
        )
        row = cur.fetchone()
        return row[0] if row and row[0] else None


def _resolver_identificador(conn, identificador: str) -> str:
    """Igual que en el script original, pero sin preguntar por consola: si
    hay varias subastas asociadas al FMI/unidad, se usa la más reciente."""
    identificador = identificador.strip()

    uuid_directo = _resolver_uuid(conn, identificador)
    if uuid_directo:
        return uuid_directo

    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, grupo_id, codigo, numero_matricula, codigo_grupo, nombre_grupo
            FROM mst_inmuebles
            WHERE UPPER(numero_matricula) = UPPER(%s)
               OR UPPER(codigo) = UPPER(%s)
               OR UPPER(codigo_grupo) = UPPER(%s)
               OR UPPER(referencia) = UPPER(%s)
            """,
            (identificador, identificador, identificador, identificador),
        )
        rows = cur.fetchall()

    if not rows:
        raise ValueError(
            f"No se encontró ninguna subasta, código, FMI ni unidad inmobiliaria "
            f"con el identificador '{identificador}'."
        )

    inmueble_ids = sorted({r[0] for r in rows if r[0] is not None})
    grupo_ids = sorted({r[1] for r in rows if r[1] is not None})

    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT DISTINCT
                COALESCE(a.id, psv.auction_id)      AS auction_id,
                COALESCE(a.start_date, psv.fecha_inicio) AS start_date
            FROM polibid_subastas_v2 psv
            LEFT JOIN polybid.auctions a ON a.id = psv.auction_id
            WHERE psv.inmueble_id = ANY(%s)
               OR (psv.grupo_id IS NOT NULL AND psv.grupo_id = ANY(%s))
            ORDER BY start_date DESC NULLS LAST
            """,
            (inmueble_ids or [-1], grupo_ids or [-1]),
        )
        candidatos = cur.fetchall()

    if not candidatos:
        raise ValueError(
            f"Se encontró el inmueble/unidad '{identificador}' pero no tiene "
            f"ninguna subasta asociada."
        )
    return str(candidatos[0][0])


# ---------------------------------------------------------------------
# Scraping de fechas (sin cambios frente al script original)
# ---------------------------------------------------------------------

def _slugify(texto: str) -> str:
    texto = (texto or "").lower()
    for k, v in {"á": "a", "é": "e", "í": "i", "ó": "o", "ú": "u", "ñ": "n", "ü": "u"}.items():
        texto = texto.replace(k, v)
    texto = re.sub(r"[\s\-]+", "-", texto)
    texto = re.sub(r"[^a-z0-9\-]", "", texto)
    return texto.strip("-")


def _convertir_fecha_espanol(texto: str) -> str | None:
    meses = {
        "enero": "01", "febrero": "02", "marzo": "03", "abril": "04",
        "mayo": "05", "junio": "06", "julio": "07", "agosto": "08",
        "septiembre": "09", "octubre": "10", "noviembre": "11", "diciembre": "12",
    }
    try:
        partes = texto.lower().split()
        dia = partes[0].zfill(2)
        mes = meses.get(partes[2], "00")
        anio = partes[4]
        hora = partes[7] if len(partes) > 7 else "10:00"
        ampm = "".join(partes[8:]).replace(".", "") if len(partes) > 8 else "am"
        return f"{dia}/{mes}/{anio} {hora} {ampm}"
    except Exception:
        return None


def _scrape_fechas(grupo_id, nombre_grupo: str, inm_id=None) -> dict:
    """Extrae fecha de publicación, apertura y cierre desde la página web
    pública del inmueble/unidad -- igual que en `generar_acta.py`. Requiere
    Chrome/Chromium instalado en el servidor (ver Dockerfile)."""
    resultado = {"publicacion": "—", "apertura": "—", "cierre": "—", "direccion": "—"}
    try:
        from selenium import webdriver
        from selenium.webdriver.chrome.service import Service
        from selenium.webdriver.chrome.options import Options
        from selenium.webdriver.common.by import By
        from webdriver_manager.chrome import ChromeDriverManager

        slug = _slugify(nombre_grupo) if nombre_grupo else ""
        if grupo_id:
            url = f"https://activosporcolombia.com/es/unidad-inmobiliaria/{grupo_id}/{slug}"
        else:
            url = f"https://activosporcolombia.com/es/inmueble/{inm_id}/{slug}"

        options = Options()
        for a in [
            "--headless", "--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu",
            "--disable-extensions", "--disable-images", "--blink-settings=imagesEnabled=false",
            "--window-size=1600,1000",
        ]:
            options.add_argument(a)
        options.page_load_strategy = "eager"
        options.add_argument(
            "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )

        chrome_bin = os.environ.get("CHROME_BIN") or os.environ.get("GOOGLE_CHROME_BIN")
        if chrome_bin:
            options.binary_location = chrome_bin

        # Si la imagen Docker ya trae un chromedriver fijado en el build
        # (ver Dockerfile), se usa directo -- evita que CADA generacion
        # tenga que consultar internet para verificar la version del
        # driver, que es lo que hacia esto mas lento de lo necesario.
        driver_path = os.environ.get("CHROMEDRIVER_PATH")
        if not driver_path or not os.path.isfile(driver_path):
            try:
                driver_path = ChromeDriverManager(cache_valid_range=30).install()
            except TypeError:
                driver_path = ChromeDriverManager().install()
            except Exception:
                driver_path = os.environ.get("CHROMEDRIVER_PATH", "chromedriver")
        driver = webdriver.Chrome(service=Service(driver_path), options=options)
        try:
            driver.set_page_load_timeout(15)
            driver.get(url)

            espera_max = 6.0
            paso = 0.3
            transcurrido = 0.0
            lineas: list[str] = []
            while transcurrido < espera_max:
                time.sleep(paso)
                transcurrido += paso
                lineas = driver.find_element(By.TAG_NAME, "body").text.split("\n")
                texto_actual = "\n".join(lineas)
                if "Cronograma del proceso" in texto_actual and (
                    "COMPLETADO" in texto_actual.upper() or "→" in texto_actual
                ):
                    break

            meses_abr = {
                "ene": "01", "feb": "02", "mar": "03", "abr": "04", "may": "05", "jun": "06",
                "jul": "07", "ago": "08", "sep": "09", "sept": "09", "oct": "10", "nov": "11", "dic": "12",
            }

            inicio_cron = next(
                (i for i, l in enumerate(lineas) if "Cronograma del proceso" in l), 0
            )

            anio = "2026"
            for l in lineas[inicio_cron:]:
                m = re.search(r"20\d{2}", l)
                if m:
                    anio = m.group()
                    break

            def _siguiente_no_vacia(desde: int) -> int | None:
                j = desde
                while j < len(lineas) and not lineas[j].strip():
                    j += 1
                return j if j < len(lineas) else None

            idx_fase1_nombre = None
            for i, linea in enumerate(lineas):
                if i < inicio_cron:
                    continue
                if "Publicación próxima en subasta" in linea or "Registro y cargue de documentos" in linea:
                    idx_fase1_nombre = i
                    break

            if idx_fase1_nombre is not None:
                try:
                    idx_rango = _siguiente_no_vacia(idx_fase1_nombre + 1)
                    idx_mes = _siguiente_no_vacia(idx_rango + 1) if idx_rango is not None else None
                    rango = lineas[idx_rango].strip()
                    mes_l = lineas[idx_mes].strip()
                    dia = rango.split()[0].zfill(2)
                    mes = meses_abr.get(mes_l.split(".")[0].strip(), "00")
                    resultado["publicacion"] = f"{dia}/{mes}/{anio} 10:00 am"
                except Exception:
                    pass

            encontre_estado = False
            fechas_subasta = []
            for linea in lineas:
                linea = linea.strip()
                if "Estado de la Subasta" in linea:
                    encontre_estado = True
                    continue
                if encontre_estado and "de 20" in linea and "a las" in linea:
                    fecha_fmt = _convertir_fecha_espanol(linea)
                    if fecha_fmt:
                        fechas_subasta.append(fecha_fmt)
                    if len(fechas_subasta) == 2:
                        break

            if len(fechas_subasta) >= 1:
                resultado["apertura"] = fechas_subasta[0]
            if len(fechas_subasta) >= 2:
                resultado["cierre"] = fechas_subasta[1]

            if resultado["apertura"] == "—" or resultado["cierre"] == "—":
                for i, linea in enumerate(lineas):
                    if i < inicio_cron:
                        continue
                    if "subasta (apertura y cierre)" in linea.lower():
                        try:
                            idx_rango = _siguiente_no_vacia(i + 1)
                            idx_mes = _siguiente_no_vacia(idx_rango + 1) if idx_rango is not None else None
                            rango = lineas[idx_rango].strip()
                            mes_l = lineas[idx_mes].strip()
                            mes = meses_abr.get(mes_l.split(".")[0].strip(), "00")
                            if "→" in rango:
                                partes = rango.split()
                                dia_i, dia_f = partes[0].zfill(2), partes[2].zfill(2)
                            else:
                                dia_i = dia_f = rango.split()[0].zfill(2)
                            if resultado["apertura"] == "—":
                                resultado["apertura"] = f"{dia_i}/{mes}/{anio}"
                            if resultado["cierre"] == "—":
                                resultado["cierre"] = f"{dia_f}/{mes}/{anio}"
                        except Exception:
                            pass
                        break

            for i, linea in enumerate(lineas):
                if "Dirección:" in linea:
                    dir_texto = linea.replace("Dirección:", "").strip()
                    if dir_texto:
                        resultado["direccion"] = dir_texto
                        break
        finally:
            driver.quit()
    except Exception as e:
        resultado["_error"] = str(e)
    return resultado


# ---------------------------------------------------------------------
# Datos de la base de datos de negocio
# ---------------------------------------------------------------------

def _fmt_fecha(fecha) -> str:
    if not fecha:
        return "—"
    return f"{fecha.day:02d}/{fecha.month:02d}/{fecha.year}"


def _fmt_numero(valor) -> str:
    if not valor:
        return "0"
    try:
        return f"{int(valor):,}".replace(",", ".")
    except Exception:
        return str(valor)


def _obtener_subasta(conn, auction_uuid: str) -> dict:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT code, status, start_date, end_date, created_at FROM polybid.auctions WHERE id = %s::uuid",
            (auction_uuid,),
        )
        row = cur.fetchone()
    if not row:
        return {}
    return {"code": row[0], "status": row[1], "start_date": row[2], "end_date": row[3], "created_at": row[4]}


def _ganador_de_subasta(conn, auction_uuid: str) -> dict:
    """Misma lógica que `_ganador_de_subasta` de acta_alcance.py: primero
    la puja marcada 'WINNING'; si aún no existe, la mejor oferta vigente."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT b.amount, b.client_id, ct.nombre_principal, ct.identificacion_numero
            FROM polybid.auction_bids b
            INNER JOIN polybid.auction_participants p
                ON p.auction_id = b.auction_id AND p.client_id = b.client_id
            LEFT JOIN polibid_credentials pc ON pc.client_id = b.client_id
            LEFT JOIN contact_terceros ct ON ct.id = pc.contact_tercero_id
            WHERE b.auction_id = %s::uuid AND b.status = 'WINNING'
            LIMIT 1
            """,
            (auction_uuid,),
        )
        row = cur.fetchone()
        if not row:
            cur.execute(
                """
                SELECT b.amount, b.client_id, ct.nombre_principal, ct.identificacion_numero
                FROM polybid.auction_bids b
                INNER JOIN polybid.auction_participants p
                    ON p.auction_id = b.auction_id AND p.client_id = b.client_id
                LEFT JOIN polibid_credentials pc ON pc.client_id = b.client_id
                LEFT JOIN contact_terceros ct ON ct.id = pc.contact_tercero_id
                WHERE b.auction_id = %s::uuid
                ORDER BY b.amount DESC, b.created_at DESC
                LIMIT 1
                """,
                (auction_uuid,),
            )
            row = cur.fetchone()
    if not row:
        return {}
    return {"amount": row[0], "client_id": row[1], "nombre_principal": row[2], "identificacion_numero": row[3]}


def _obtener_datos_acta(conn, auction_uuid: str) -> dict:
    subasta = _obtener_subasta(conn, auction_uuid)

    inmueble: dict = {}
    grupo_id = None
    nombre_grupo = ""
    inm_id = None

    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT psv.contact_tercero_id, psv.inmueble_id, psv.grupo_id, ct.direccion_principal
            FROM polibid_subastas_v2 psv
            LEFT JOIN contact_terceros ct ON ct.id = psv.contact_tercero_id
            WHERE psv.auction_id = %s::uuid
            ORDER BY psv.id DESC LIMIT 1
            """,
            (auction_uuid,),
        )
        link = cur.fetchone()
        direccion = "—"
        if link:
            direccion = link[3] or "—"
            if link[1]:
                inm_id = link[1]
                cur.execute(
                    """SELECT codigo, numero_matricula, referencia, grupo_id, nombre_grupo, referencia
                       FROM mst_inmuebles WHERE id = %s""",
                    (link[1],),
                )
                row = cur.fetchone()
                if row:
                    grupo_id = row[3]
                    nombre_grupo = row[4] or row[2] or ""
                    inmueble = {"codigo": row[0] or "—", "fmi": row[1] or "—", "nombre_grupo": row[4] or row[2] or "—"}
            elif link[2]:
                cur.execute(
                    """SELECT id, codigo, numero_matricula, grupo_id, nombre_grupo, referencia, codigo_grupo
                       FROM mst_inmuebles WHERE grupo_id = %s ORDER BY es_padre DESC, id""",
                    (link[2],),
                )
                rows_g = cur.fetchall()
                if rows_g:
                    r = rows_g[0]
                    grupo_id = r[3]
                    nombre_grupo = r[4] or r[5] or ""
                    codigo_inm = r[6] or r[1] or "—"
                    fmi_inm = ", ".join(x[2] for x in rows_g if x[2])
                    inmueble = {"codigo": codigo_inm, "fmi": fmi_inm, "nombre_grupo": nombre_grupo}
        inmueble["direccion"] = inmueble.get("nombre_grupo", direccion)

        if not inmueble.get("fmi") or inmueble.get("fmi") == "—":
            cur.execute(
                """
                SELECT DISTINCT mani.grupo_id, mani.inmueble_id
                FROM polybid.auction_participants p
                JOIN polibid_credentials pc ON pc.client_id = p.client_id
                JOIN manifestacion_interes mani ON mani.contact_tercero_id = pc.contact_tercero_id
                WHERE p.auction_id = %s::uuid
                  AND (mani.grupo_id IS NOT NULL OR mani.inmueble_id IS NOT NULL)
                ORDER BY mani.grupo_id DESC NULLS LAST
                LIMIT 1
                """,
                (auction_uuid,),
            )
            mani = cur.fetchone()
            if mani:
                if mani[0]:
                    cur.execute(
                        """SELECT id, codigo, numero_matricula, grupo_id, nombre_grupo, referencia, codigo_grupo
                           FROM mst_inmuebles WHERE grupo_id = %s ORDER BY es_padre DESC, id""",
                        (mani[0],),
                    )
                    rows_g = cur.fetchall()
                    if rows_g:
                        r = rows_g[0]
                        grupo_id = r[3]
                        nombre_grupo = r[4] or r[5] or ""
                        codigo_inm = r[6] or r[1] or "—"
                        fmi_inm = ", ".join(x[2] for x in rows_g if x[2])
                        inmueble = {"codigo": codigo_inm, "fmi": fmi_inm, "nombre_grupo": nombre_grupo, "direccion": nombre_grupo}
                elif mani[1]:
                    inm_id = mani[1]
                    cur.execute(
                        """SELECT id, codigo, numero_matricula, grupo_id, nombre_grupo, referencia
                           FROM mst_inmuebles WHERE id = %s""",
                        (mani[1],),
                    )
                    r = cur.fetchone()
                    if r:
                        grupo_id = r[3]
                        nombre_grupo = r[4] or r[5] or ""
                        inmueble = {"codigo": r[1] or "—", "fmi": r[2] or "—", "nombre_grupo": nombre_grupo, "direccion": nombre_grupo}

    if grupo_id:
        codigo_unidad = _codigo_unidad_de_grupo(conn, grupo_id)
        if codigo_unidad:
            inmueble["fmi"] = codigo_unidad

    fechas = _scrape_fechas(grupo_id, nombre_grupo, inm_id=inm_id)
    fecha_apertura = fechas.get("apertura", "—")
    fecha_cierre = fechas.get("cierre", "—")

    fecha_publicacion = fechas.get("publicacion", "—")
    if fecha_publicacion == "—" and subasta.get("created_at"):
        ca = subasta["created_at"]
        fecha_publicacion = f"{ca.day:02d}/{ca.month:02d}/{ca.year} {ca.strftime('%I:%M %p').lstrip('0').lower()}"

    participantes = []
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT
                ct.nombre_principal, ct.identificacion_numero, ct.identificacion_tipo,
                ct.lugar_expedicion_doc, ct.ciudad,
                (SELECT b.amount FROM polybid.auction_bids b
                 WHERE b.auction_id = p.auction_id AND b.client_id = p.client_id
                 ORDER BY b.created_at DESC LIMIT 1) AS ultima_puja
            FROM polybid.auction_participants p
            LEFT JOIN polibid_credentials pc ON pc.client_id = p.client_id
            LEFT JOIN contact_terceros ct ON ct.id = pc.contact_tercero_id
            WHERE p.auction_id = %s::uuid
            ORDER BY p.created_at
            """,
            (auction_uuid,),
        )
        for row in cur.fetchall():
            nombre, cedula, tipo_id, lugar_exp, ciudad, monto = row
            if not monto:
                continue
            ciudad_cedula = ciudad if tipo_id == "NIT" else (lugar_exp or "—")
            participantes.append({
                "nombre": (nombre or "—").upper(),
                "cedula": str(cedula or "—"),
                "ciudad_cedula": ciudad_cedula or "—",
                "monto": _fmt_numero(monto),
            })

    ganador = _ganador_de_subasta(conn, auction_uuid)

    return {
        "codigo_subasta": subasta.get("code", "—") or "—",
        "fecha_publicacion": fecha_publicacion,
        "fecha_inicio": fecha_apertura if fecha_apertura != "—" else _fmt_fecha(subasta.get("start_date")),
        "fecha_fin": fecha_cierre if fecha_cierre != "—" else _fmt_fecha(subasta.get("end_date")),
        "fmi": inmueble.get("fmi", "—"),
        "direcion": fechas.get("direccion", inmueble.get("direccion", "—")),
        "direccion": fechas.get("direccion", inmueble.get("direccion", "—")),
        "codigo_inmueble": inmueble.get("codigo", "—"),
        "participantes": participantes,
        "nombre_ganador": (ganador.get("nombre_principal") or "—").upper() if ganador else "—",
        "cedula_ganador": str(ganador.get("identificacion_numero") or "—") if ganador else "—",
        "monto_ganador": _fmt_numero(ganador.get("amount")) if ganador else "0",
    }


# ---------------------------------------------------------------------
# Generación del .docx (idéntico al script original)
# ---------------------------------------------------------------------

def _generar_docx_bytes(datos: dict) -> bytes:
    with zipfile.ZipFile(RUTA_PLANTILLA, "r") as zin:
        archivos = {name: zin.read(name) for name in zin.namelist()}

    doc_xml = archivos["word/document.xml"].decode("utf-8")

    reemplazos = {
        "##codigo_subasta##": datos["codigo_subasta"],
        "##fecha_publicacion##": datos["fecha_publicacion"],
        "##fecha_inicio##": datos["fecha_inicio"],
        "##fecha_fin##": datos["fecha_fin"],
        "##fmi##": datos["fmi"],
        "##direcion##": datos["direcion"],
        "##direccion##": datos["direccion"],
        "##codigo_inmueble##": datos["codigo_inmueble"],
        "##nombre_ganador##": datos["nombre_ganador"],
        "##cedula_ganador##": datos["cedula_ganador"],
        "##monto_ganador##": datos["monto_ganador"],
    }

    doc_xml = re.sub(
        r'<w:t>##fecha_</w:t></w:r><w:r[^>]*><w:rPr>.*?</w:rPr><w:t>([^<]+)</w:t></w:r><w:r[^>]*><w:rPr>.*?</w:rPr><w:t>##</w:t></w:r>',
        r'<w:t>##fecha_\1##</w:t></w:r>', doc_xml, flags=re.DOTALL,
    )
    doc_xml = re.sub(
        r'<w:t>##</w:t></w:r><w:r[^>]*><w:t>([^<#]+)</w:t></w:r><w:r[^>]*><w:t>##</w:t></w:r>',
        r'<w:t>##\1##</w:t></w:r>', doc_xml, flags=re.DOTALL,
    )
    doc_xml = re.sub(
        r'<w:t>##([^<#]+)#</w:t></w:r><w:proofErr[^/]*/><w:r[^>]*><w:t[^>]*>#\s*</w:t></w:r>',
        r'<w:t>##\1##</w:t></w:r>', doc_xml, flags=re.DOTALL,
    )
    doc_xml = re.sub(r'<w:t>([^<]+)</w:r>', r'<w:t>\1</w:t></w:r>', doc_xml)

    for placeholder, valor in reemplazos.items():
        doc_xml = doc_xml.replace(placeholder, valor)

    PARRAFO_PLANTILLA = (
        '<w:p w14:paraId="28701AD4" w14:textId="1843D5B8" w:rsidR="00A46A55" '
        'w:rsidRDefault="007F604A" w:rsidP="001141D7"><w:pPr><w:ind w:left="360" '
        'w:right="704"/></w:pPr><w:r><w:t>##nombre##</w:t></w:r>'
        '<w:r w:rsidR="00511C95"><w:t xml:space="preserve"> </w:t></w:r>'
        '<w:r w:rsidR="005F4ECB" w:rsidRPr="005F4ECB"><w:rPr><w:lang w:val="es-ES"/>'
        '</w:rPr><w:t xml:space="preserve">– C.C: </w:t></w:r>'
        '<w:r><w:t xml:space="preserve">##cedula##, </w:t></w:r>'
        '<w:r><w:rPr><w:lang w:val="es-ES"/></w:rPr>'
        '<w:t xml:space="preserve">##ciudad_cedula## </w:t></w:r>'
        '<w:r w:rsidR="005F4ECB" w:rsidRPr="005F4ECB"><w:rPr><w:lang w:val="es-ES"/>'
        '</w:rPr><w:t xml:space="preserve">- </w:t></w:r>'
        '<w:r w:rsidR="00511C95" w:rsidRPr="00511C95">'
        '<w:t xml:space="preserve">$ </w:t></w:r>'
        '<w:r><w:t>##monto##</w:t></w:r></w:p>'
    )

    if datos["participantes"]:
        parrafos_participantes = ""
        for p in datos["participantes"]:
            parrafo = PARRAFO_PLANTILLA
            parrafo = parrafo.replace("##nombre##", p["nombre"])
            parrafo = parrafo.replace("##cedula##", p["cedula"])
            parrafo = parrafo.replace("##ciudad_cedula##", p["ciudad_cedula"])
            parrafo = parrafo.replace("##monto##", p["monto"])
            parrafos_participantes += parrafo
        doc_xml = doc_xml.replace(PARRAFO_PLANTILLA, parrafos_participantes)
    else:
        doc_xml = doc_xml.replace(PARRAFO_PLANTILLA, "")

    archivos["word/document.xml"] = doc_xml.encode("utf-8")

    salida = io.BytesIO()
    with zipfile.ZipFile(salida, "w", zipfile.ZIP_DEFLATED) as zout:
        for name, contenido in archivos.items():
            zout.writestr(name, contenido)
    return salida.getvalue()


def obtener_oferentes(identificador: str) -> dict:
    """Lista TODOS los oferentes inscritos en la subasta asociada a este
    FMI/codigo/unidad, incluyendo su ultima puja y si quedaron marcados
    como ganadores (status 'WINNING').

    A diferencia de lo que se imprime en el Acta -- que solo incluye a
    quien SI tiene una puja registrada con monto, y elige un ganador solo
    si hay alguien con status 'WINNING' o, en su defecto, la puja mas alta
    -- aqui se listan todos los inscritos aunque no hayan llegado a pujar.
    Esto es justo para diagnosticar casos donde el Acta sale sin ganador:
    o nadie tiene status 'WINNING' y tampoco hay pujas con monto, o el
    ganador real esta inscrito pero sin puja registrada (por lo que el
    Acta no puede saber que gano)."""
    with db.get_conn_negocio_tuplas() as conn:
        auction_uuid = _resolver_identificador(conn, identificador)
        subasta = _obtener_subasta(conn, auction_uuid)
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    ct.nombre_principal, ct.identificacion_numero, p.client_id,
                    (SELECT b.amount FROM polybid.auction_bids b
                     WHERE b.auction_id = p.auction_id AND b.client_id = p.client_id
                     ORDER BY b.created_at DESC LIMIT 1) AS ultima_puja,
                    (SELECT b.status FROM polybid.auction_bids b
                     WHERE b.auction_id = p.auction_id AND b.client_id = p.client_id
                     ORDER BY b.created_at DESC LIMIT 1) AS status_puja,
                    p.created_at
                FROM polybid.auction_participants p
                LEFT JOIN polibid_credentials pc ON pc.client_id = p.client_id
                LEFT JOIN contact_terceros ct ON ct.id = pc.contact_tercero_id
                WHERE p.auction_id = %s::uuid
                ORDER BY ultima_puja DESC NULLS LAST, p.created_at
                """,
                (auction_uuid,),
            )
            filas = cur.fetchall()

    oferentes = []
    for nombre, cedula, client_id, monto, status, se_registro in filas:
        oferentes.append({
            "nombre": (nombre or "Sin nombre registrado").upper(),
            "cedula": str(cedula or "—"),
            "client_id": str(client_id) if client_id is not None else "—",
            "monto": _fmt_numero(monto) if monto else None,
            "status_puja": status or None,
            "gano": (status or "").upper() == "WINNING",
            "se_registro": _fmt_fecha(se_registro) if se_registro else "—",
        })

    return {
        "codigo_subasta": subasta.get("code", "—") or "—",
        "total_oferentes": len(oferentes),
        "oferentes": oferentes,
    }


def generar(fmi: str) -> tuple[bytes, str, list[str]]:
    """`fmi` es el identificador de búsqueda: UUID/código de subasta, FMI
    de inmueble individual, o código de unidad inmobiliaria."""
    with db.get_conn_negocio_tuplas() as conn:
        auction_uuid = _resolver_identificador(conn, fmi)
        datos = _obtener_datos_acta(conn, auction_uuid)

    pendientes: list[str] = []
    if datos["nombre_ganador"] == "—":
        pendientes.append("Oferente ganador: no se encontró en la base de datos, revisar a mano.")
    if datos["fecha_inicio"] == "—" or datos["fecha_fin"] == "—":
        pendientes.append("Fechas de apertura/cierre: no se pudieron obtener del sitio web, revisar a mano.")
    if datos["direccion"] == "—":
        pendientes.append("Dirección: no se encontró, revisar a mano.")

    contenido = _generar_docx_bytes(datos)
    codigo_corto = re.sub(r"[^A-Za-z0-9]+", "_", datos["codigo_subasta"].replace("ACTIBID-", ""))[:20]
    nombre_archivo = f"ACTA_{codigo_corto or fmi}.docx"

    db.upsert_caso(fmi, {
        "estado": "con_observaciones" if pendientes else "completo",
        "pendientes": pendientes,
    })
    return contenido, nombre_archivo, pendientes
