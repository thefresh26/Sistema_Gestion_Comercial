"""
Tipo de documento: Informe de Subasta Electrónica.

Port del script original `generar_informe.py`. El scraping de fechas
(Selenium + Chrome headless, 16 fechas de cronograma) se mantiene
EXACTAMENTE igual al script original -- requiere Chrome/Chromium
instalado en el servidor (ver Dockerfile).

Diferencia importante con el script original -- tráfico web (Microsoft
Clarity):

El script original abre una ventana de Chrome YA ABIERTA en el
computador del usuario, con la sesión personal de Clarity ya iniciada
(conectándose por el puerto de depuración remota 9222), y desde ahí toma
2 capturas de pantalla del dashboard. Eso solo puede funcionar en un
computador con esa sesión abierta -- un servidor en la nube no tiene (ni
puede tener de forma segura) la sesión de Microsoft de nadie iniciada,
así que esa parte no se puede scrapear automáticamente aquí.

En su lugar, este módulo llama a la API oficial de exportación de datos
de Clarity (ver `core/clarity.py`) con un token de proyecto (no una
contraseña personal) para traer las 3 cifras de sesiones automáticamente
-- ya no hace falta subir ninguna captura de pantalla ni escribirlas a
mano. Esa API solo cubre el tráfico de los últimos 1-3 días; si el
Informe se genera después de esa ventana, el documento se genera de
todas formas, solo que sin esas 3 cifras (quedan como "—").
"""
from __future__ import annotations

import io
import os
import re
import time
import zipfile
from io import BytesIO

from core import clarity, db

RAIZ_PROYECTO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
RUTA_PLANTILLA = os.path.join(RAIZ_PROYECTO, "word_templates", "INFORME_SUBASTA.docx")

MESES_ABR = {
    "ene": "01", "feb": "02", "mar": "03", "abr": "04", "may": "05", "jun": "06",
    "jul": "07", "ago": "08", "sep": "09", "sept": "09", "oct": "10", "nov": "11", "dic": "12",
}

# Ya no se piden capturas de pantalla de Clarity: las 3 cifras de
# sesiones se traen solas desde la API de Clarity (ver core/clarity.py).
TIPOS_DOCUMENTO_FUENTE: dict[str, str] = {}

# Los 3 campos de Clarity ya no son editables a mano (los llena la API) --
# solo quedan estos por si el scraping/base de datos no encuentra algo.
CAMPOS_EDITABLES = [
    ("nombre_ganador", "Oferente ganador"),
    ("fecha_inicio", "Fecha de apertura"),
    ("fecha_fin", "Fecha de cierre"),
    ("clarity_sesiones_totales", "Sesiones totales (Clarity) -- solo si la API no las trajo"),
    ("clarity_bots_excluidos", "Sesiones de bot excluidas (Clarity) -- solo si la API no las trajo"),
    ("clarity_sesiones_url", "Sesiones de la URL del inmueble (Clarity) -- solo si la API no las trajo"),
]

FILA_FMI = '<w:tr w:rsidR="004335EC" w14:paraId="7346AD35" w14:textId="77777777" w:rsidTr="001D7A74"><w:tc><w:tcPr><w:tcW w:w="800" w:type="pct"/><w:tcBorders><w:top w:val="single" w:sz="4" w:space="0" w:color="auto"/><w:left w:val="single" w:sz="6" w:space="0" w:color="DDDDDD"/><w:bottom w:val="single" w:sz="4" w:space="0" w:color="auto"/><w:right w:val="single" w:sz="6" w:space="0" w:color="DDDDDD"/></w:tcBorders><w:tcMar><w:top w:w="120" w:type="dxa"/><w:left w:w="120" w:type="dxa"/><w:bottom w:w="120" w:type="dxa"/><w:right w:w="120" w:type="dxa"/></w:tcMar><w:vAlign w:val="center"/><w:hideMark/></w:tcPr><w:p w14:paraId="3405DB84" w14:textId="0D6A24F0" w:rsidR="004335EC" w:rsidRDefault="003F62F4" w:rsidP="001E7040"><w:pPr><w:rPr><w:rFonts w:ascii="Arial" w:hAnsi="Arial" w:cs="Arial"/><w:sz w:val="21"/><w:szCs w:val="21"/></w:rPr></w:pPr><w:r><w:rPr><w:rFonts w:ascii="Arial" w:hAnsi="Arial" w:cs="Arial"/><w:sz w:val="21"/><w:szCs w:val="21"/></w:rPr><w:t>##fmi##</w:t></w:r></w:p></w:tc><w:tc><w:tcPr><w:tcW w:w="726" w:type="pct"/><w:tcBorders><w:top w:val="single" w:sz="4" w:space="0" w:color="auto"/><w:left w:val="single" w:sz="6" w:space="0" w:color="DDDDDD"/><w:bottom w:val="single" w:sz="4" w:space="0" w:color="auto"/><w:right w:val="single" w:sz="6" w:space="0" w:color="DDDDDD"/></w:tcBorders><w:tcMar><w:top w:w="120" w:type="dxa"/><w:left w:w="120" w:type="dxa"/><w:bottom w:w="120" w:type="dxa"/><w:right w:w="120" w:type="dxa"/></w:tcMar><w:vAlign w:val="center"/><w:hideMark/></w:tcPr><w:p w14:paraId="5FC3148B" w14:textId="0F16A98C" w:rsidR="00711FCF" w:rsidRDefault="003F62F4" w:rsidP="0042080F"><w:pPr><w:jc w:val="center"/><w:rPr><w:rFonts w:ascii="Arial" w:hAnsi="Arial" w:cs="Arial"/><w:sz w:val="21"/><w:szCs w:val="21"/></w:rPr></w:pPr><w:r><w:rPr><w:rFonts w:ascii="Arial" w:hAnsi="Arial" w:cs="Arial"/><w:sz w:val="21"/><w:szCs w:val="21"/></w:rPr><w:t>##direccion##</w:t></w:r></w:p></w:tc><w:tc><w:tcPr><w:tcW w:w="951" w:type="pct"/><w:tcBorders><w:top w:val="single" w:sz="4" w:space="0" w:color="auto"/><w:left w:val="single" w:sz="6" w:space="0" w:color="DDDDDD"/><w:bottom w:val="single" w:sz="4" w:space="0" w:color="auto"/><w:right w:val="single" w:sz="6" w:space="0" w:color="DDDDDD"/></w:tcBorders><w:tcMar><w:top w:w="120" w:type="dxa"/><w:left w:w="120" w:type="dxa"/><w:bottom w:w="120" w:type="dxa"/><w:right w:w="120" w:type="dxa"/></w:tcMar><w:vAlign w:val="center"/><w:hideMark/></w:tcPr><w:p w14:paraId="19DECA7C" w14:textId="344F554D" w:rsidR="00401EB7" w:rsidRPr="004E5742" w:rsidRDefault="003F62F4" w:rsidP="00401EB7"><w:pPr><w:jc w:val="center"/><w:rPr><w:rFonts w:ascii="Arial" w:hAnsi="Arial" w:cs="Arial"/><w:sz w:val="21"/><w:szCs w:val="21"/></w:rPr></w:pPr><w:r><w:rPr><w:rFonts w:ascii="Arial" w:hAnsi="Arial" w:cs="Arial"/><w:sz w:val="21"/><w:szCs w:val="21"/></w:rPr><w:t>##ciudad##</w:t></w:r></w:p></w:tc><w:tc><w:tcPr><w:tcW w:w="795" w:type="pct"/><w:tcBorders><w:top w:val="single" w:sz="4" w:space="0" w:color="auto"/><w:left w:val="single" w:sz="6" w:space="0" w:color="DDDDDD"/><w:bottom w:val="single" w:sz="4" w:space="0" w:color="auto"/><w:right w:val="single" w:sz="6" w:space="0" w:color="DDDDDD"/></w:tcBorders><w:tcMar><w:top w:w="120" w:type="dxa"/><w:left w:w="120" w:type="dxa"/><w:bottom w:w="120" w:type="dxa"/><w:right w:w="120" w:type="dxa"/></w:tcMar><w:vAlign w:val="center"/><w:hideMark/></w:tcPr><w:p w14:paraId="19DECA7C" w14:textId="344F554D" w:rsidR="00401EB7" w:rsidRPr="004E5742" w:rsidRDefault="003F62F4" w:rsidP="00401EB7"><w:pPr><w:jc w:val="center"/><w:rPr><w:rFonts w:ascii="Arial" w:hAnsi="Arial" w:cs="Arial"/><w:sz w:val="21"/><w:szCs w:val="21"/></w:rPr></w:pPr><w:r><w:rPr><w:rFonts w:ascii="Arial" w:hAnsi="Arial" w:cs="Arial"/><w:sz w:val="21"/><w:szCs w:val="21"/></w:rPr><w:t>##departamento##</w:t></w:r></w:p></w:tc><w:tc><w:tcPr><w:tcW w:w="889" w:type="pct"/><w:tcBorders><w:top w:val="single" w:sz="4" w:space="0" w:color="auto"/><w:left w:val="single" w:sz="6" w:space="0" w:color="DDDDDD"/><w:bottom w:val="single" w:sz="4" w:space="0" w:color="auto"/><w:right w:val="single" w:sz="6" w:space="0" w:color="DDDDDD"/></w:tcBorders><w:tcMar><w:top w:w="120" w:type="dxa"/><w:left w:w="120" w:type="dxa"/><w:bottom w:w="120" w:type="dxa"/><w:right w:w="120" w:type="dxa"/></w:tcMar><w:vAlign w:val="center"/><w:hideMark/></w:tcPr><w:p w14:paraId="130AAB20" w14:textId="33B82877" w:rsidR="004335EC" w:rsidRDefault="003F62F4"><w:pPr><w:jc w:val="center"/><w:rPr><w:rFonts w:ascii="Arial" w:hAnsi="Arial" w:cs="Arial"/><w:sz w:val="21"/><w:szCs w:val="21"/></w:rPr></w:pPr><w:r><w:rPr><w:rFonts w:ascii="Arial" w:hAnsi="Arial" w:cs="Arial"/><w:sz w:val="21"/><w:szCs w:val="21"/></w:rPr><w:t>##tipo_inmueble##</w:t></w:r></w:p></w:tc><w:tc><w:tcPr><w:tcW w:w="839" w:type="pct"/><w:tcBorders><w:top w:val="single" w:sz="4" w:space="0" w:color="auto"/><w:left w:val="single" w:sz="6" w:space="0" w:color="DDDDDD"/><w:bottom w:val="single" w:sz="4" w:space="0" w:color="auto"/><w:right w:val="single" w:sz="6" w:space="0" w:color="DDDDDD"/></w:tcBorders><w:tcMar><w:top w:w="120" w:type="dxa"/><w:left w:w="120" w:type="dxa"/><w:bottom w:w="120" w:type="dxa"/><w:right w:w="120" w:type="dxa"/></w:tcMar><w:vAlign w:val="center"/><w:hideMark/></w:tcPr><w:p w14:paraId="1B53A752" w14:textId="01C72209" w:rsidR="004335EC" w:rsidRDefault="003F62F4" w:rsidP="00672C46"><w:pPr><w:jc w:val="center"/><w:rPr><w:rFonts w:ascii="Arial" w:hAnsi="Arial" w:cs="Arial"/><w:sz w:val="21"/><w:szCs w:val="21"/></w:rPr></w:pPr><w:r><w:rPr><w:rFonts w:ascii="Arial" w:hAnsi="Arial" w:cs="Arial"/><w:sz w:val="21"/><w:szCs w:val="21"/></w:rPr><w:t>##area##</w:t></w:r></w:p></w:tc></w:tr>'


# ---------------------------------------------------------------------
# Resolver identificador -> UUID de subasta (sin preguntar por consola)
# ---------------------------------------------------------------------

def _resolver_uuid(conn, identificador: str) -> str | None:
    if re.match(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", identificador.lower()):
        return identificador
    with conn.cursor() as cur:
        cur.execute("SELECT id FROM polybid.auctions WHERE code = %s LIMIT 1", (identificador,))
        row = cur.fetchone()
        if row:
            return str(row[0])
    return None


def _resolver_identificador(conn, identificador: str) -> str:
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
                COALESCE(a.id, psv.auction_id) AS auction_id,
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


def _fmt_fecha(f):
    return f"{f.day:02d}/{f.month:02d}/{f.year}" if f else "—"


def _fmt_numero(v):
    try:
        return f"{int(v):,}".replace(",", ".")
    except Exception:
        return str(v) if v else "0"


def _slugify(t):
    if not t:
        return ""
    t = t.lower()
    for k, v in {"á": "a", "é": "e", "í": "i", "ó": "o", "ú": "u", "ñ": "n"}.items():
        t = t.replace(k, v)
    t = re.sub(r"[\s\-]+", "-", t)
    t = re.sub(r"[^a-z0-9\-]", "", t)
    return t.strip("-")


def _limpiar(v):
    v = str(v) if v else ""
    v = "".join(c for c in v if ord(c) >= 32)
    return v.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


_RUN_RE = re.compile(
    r'<w:r\b[^>]*>(?:<w:rPr>.*?</w:rPr>)?<w:t[^>]*>([^<]*)</w:t></w:r>', re.DOTALL,
)
_RUN_OPEN_RE = re.compile(r'^(<w:r\b[^>]*>(?:<w:rPr>.*?</w:rPr>)?<w:t[^>]*>)', re.DOTALL)


def _colapsar_marcadores(xml):
    piezas = []
    pos = 0
    fin_anterior = None
    buffer = []
    buffer_textos = []
    dobles_vistos = 0

    def volcar():
        if not buffer:
            return
        if len(buffer) == 1:
            piezas.append(buffer[0])
        else:
            m = _RUN_OPEN_RE.match(buffer[0])
            apertura = m.group(1) if m else "<w:r><w:t>"
            piezas.append(apertura + "".join(buffer_textos) + "</w:t></w:r>")
        buffer.clear()
        buffer_textos.clear()

    for m in _RUN_RE.finditer(xml):
        if fin_anterior is None or m.start() != fin_anterior:
            volcar()
            dobles_vistos = 0
            piezas.append(xml[pos:m.start()])
        texto = m.group(1)
        buffer.append(m.group(0))
        buffer_textos.append(texto)
        dobles_vistos += texto.count("##")
        if dobles_vistos % 2 == 0:
            volcar()
            dobles_vistos = 0
        pos = fin_anterior = m.end()

    volcar()
    piezas.append(xml[pos:])
    return "".join(piezas)


def _colapsar_xml(xml):
    xml = re.sub(r'<w:t>([^<]+)</w:r>', r'<w:t>\1</w:t></w:r>', xml)
    xml = _colapsar_marcadores(xml)
    return xml


# ---------------------------------------------------------------------
# Scraping (idéntico al script original)
# ---------------------------------------------------------------------

def _scrape(grupo_id, nombre_grupo, inm_id=None):
    res = {f"fecha_cronograma{i}": "—" for i in range(1, 17)}
    res.update({"fecha_publicacion": "—", "fecha_inicio": "—", "fecha_fin": "—"})
    try:
        from selenium import webdriver
        from selenium.webdriver.chrome.service import Service
        from selenium.webdriver.chrome.options import Options
        from selenium.webdriver.common.by import By
        from webdriver_manager.chrome import ChromeDriverManager

        slug = _slugify(nombre_grupo)
        if grupo_id:
            url = f"https://activosporcolombia.com/es/unidad-inmobiliaria/{grupo_id}/{slug}"
        else:
            url = f"https://activosporcolombia.com/es/inmueble/{inm_id}/{slug}"

        opts = Options()
        for a in ["--headless", "--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu",
                  "--disable-extensions", "--disable-images", "--blink-settings=imagesEnabled=false",
                  "--window-size=1600,1000"]:
            opts.add_argument(a)
        opts.page_load_strategy = "eager"
        opts.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36")

        chrome_bin = os.environ.get("CHROME_BIN") or os.environ.get("GOOGLE_CHROME_BIN")
        if chrome_bin:
            opts.binary_location = chrome_bin

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
        driver = webdriver.Chrome(service=Service(driver_path), options=opts)
        try:
            driver.set_page_load_timeout(15)
            driver.get(url)

            espera_max = 6.0
            paso = 0.3
            transcurrido = 0.0
            lineas = []
            while transcurrido < espera_max:
                time.sleep(paso)
                transcurrido += paso
                lineas = [l.strip() for l in driver.find_element(By.TAG_NAME, "body").text.split("\n")]
                texto_actual = "\n".join(lineas)
                if "Cronograma del proceso" in texto_actual and (
                    "COMPLETADO" in texto_actual.upper() or "→" in texto_actual
                ):
                    break

            inicio_cron = next((i for i, l in enumerate(lineas) if "Cronograma del proceso" in l), 0)

            anio = "2026"
            for l in lineas[inicio_cron:]:
                m = re.search(r"20\d{2}", l)
                if m:
                    anio = m.group()
                    break

            texto_crono = "\n".join(lineas[inicio_cron:inicio_cron + 60]).lower()
            if "publicación próxima en subasta" in texto_crono:
                fases = [
                    ("Publicación próxima en subasta", "fecha_cronograma1", "fecha_cronograma2"),
                    ("Registro", "fecha_cronograma3", "fecha_cronograma4"),
                    ("Análisis debida diligencia", "fecha_cronograma5", "fecha_cronograma6"),
                    ("Análisis financiero", "fecha_cronograma7", "fecha_cronograma8"),
                    ("Expedición y envío de cupones", "fecha_cronograma9", "fecha_cronograma10"),
                    ("seriedad", "fecha_cronograma11", "fecha_cronograma12"),
                    ("Validación y confirmación", "fecha_cronograma13", "fecha_cronograma14"),
                    ("Subasta", "fecha_cronograma15", "fecha_cronograma16"),
                ]
            else:
                fases = [
                    ("Registro y cargue de documentos", "fecha_cronograma1", "fecha_cronograma2"),
                    ("Análisis debida diligencia", "fecha_cronograma3", "fecha_cronograma4"),
                    ("Cargue de documentos financieros", "fecha_cronograma5", "fecha_cronograma6"),
                    ("Análisis financiero", "fecha_cronograma7", "fecha_cronograma8"),
                    ("Expedición y envío de cupones", "fecha_cronograma9", "fecha_cronograma10"),
                    ("Pago seriedad de la oferta", "fecha_cronograma11", "fecha_cronograma12"),
                    ("Validación y confirmación", "fecha_cronograma13", "fecha_cronograma14"),
                    ("Subasta", "fecha_cronograma15", "fecha_cronograma16"),
                ]

            def _siguiente_no_vacia(desde):
                j = desde
                while j < len(lineas) and not lineas[j].strip():
                    j += 1
                return j if j < len(lineas) else None

            inicio_fases = inicio_cron
            for i in range(inicio_cron, min(inicio_cron + 15, len(lineas))):
                if lineas[i].startswith("Del ") and "de 20" in lineas[i]:
                    inicio_fases = i + 1
                    break

            cursor = inicio_fases
            for fase, ph_ini, ph_fin in fases:
                for i in range(cursor, len(lineas)):
                    l = lineas[i]
                    if fase.lower() in l.lower():
                        idx_cand = _siguiente_no_vacia(i + 1)
                        cand = lineas[idx_cand] if idx_cand is not None else ""
                        if cand and cand[0].isdigit():
                            idx_mes = _siguiente_no_vacia(idx_cand + 1)
                            mes_l = lineas[idx_mes] if idx_mes is not None else ""
                            mes = MESES_ABR.get(mes_l.split(".")[0].strip(), "00")
                            if "→" in cand:
                                partes = cand.split()
                                dia_i, dia_f = partes[0].zfill(2), partes[2].zfill(2)
                            else:
                                dia_i = dia_f = cand.split()[0].zfill(2)
                            res[ph_ini] = f"{dia_i}/{mes}/{anio}"
                            res[ph_fin] = f"{dia_f}/{mes}/{anio}"
                            if ph_ini == "fecha_cronograma1":
                                res["fecha_publicacion"] = f"{dia_i}/{mes}/{anio} 10:00 am"
                            cursor = idx_mes + 1 if idx_mes is not None else i + 1
                        else:
                            cursor = i + 1
                        break

            meses_l = {"enero": "01", "febrero": "02", "marzo": "03", "abril": "04", "mayo": "05", "junio": "06",
                       "julio": "07", "agosto": "08", "septiembre": "09", "octubre": "10", "noviembre": "11", "diciembre": "12"}
            encontre = False
            fechas = []
            for l in lineas:
                if "Estado de la Subasta" in l:
                    encontre = True
                    continue
                if encontre and "de 20" in l and "a las" in l:
                    try:
                        p = l.lower().split()
                        dia = p[0].zfill(2)
                        mes = meses_l.get(p[2], "00")
                        yr = p[4]
                        hr = p[7]
                        ap = "".join(p[8:]).replace(".", "")
                        fechas.append(f"{dia}/{mes}/{yr} {hr} {ap}")
                    except Exception:
                        pass
                    if len(fechas) == 2:
                        break
            if fechas:
                res["fecha_inicio"] = fechas[0]
            if len(fechas) > 1:
                res["fecha_fin"] = fechas[1]

            if res["fecha_inicio"] == "—" and res.get("fecha_cronograma15", "—") != "—":
                res["fecha_inicio"] = res["fecha_cronograma15"]
            if res["fecha_fin"] == "—" and res.get("fecha_cronograma16", "—") != "—":
                res["fecha_fin"] = res["fecha_cronograma16"]
        finally:
            driver.quit()
    except Exception as e:
        res["_error"] = str(e)
    return res


def _buscar_inmueble_por_grupo(conn, grupo_id_val):
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, codigo, numero_matricula, grupo_id, nombre_grupo,
                   area_lote, area_construida, referencia, codigo_grupo
            FROM mst_inmuebles WHERE grupo_id = %s ORDER BY es_padre DESC, id
            """,
            (grupo_id_val,),
        )
        rows = cur.fetchall()
    if not rows:
        return {}, [], ""
    r = rows[0]
    nombre_grupo = r[4] or r[7] or ""
    inmueble = {
        "codigo": r[8] or r[1] or "—",
        "fmi": ", ".join(x[2] for x in rows if x[2]),
        "area": str(r[5] or r[6] or 0),
    }
    fmis_lista = [{"fmi": x[2] or "—", "area": str(x[5] or x[6] or 0)} for x in rows]
    return inmueble, fmis_lista, nombre_grupo


def _obtener_subasta(conn, auction_uuid):
    with conn.cursor() as cur:
        cur.execute(
            "SELECT code, status, start_date, end_date, created_at, initial_value FROM polybid.auctions WHERE id = %s::uuid",
            (auction_uuid,),
        )
        row = cur.fetchone()
    if not row:
        return {}
    return {"code": row[0], "status": row[1], "start_date": row[2], "end_date": row[3],
            "created_at": row[4], "initial_value": row[5]}


def _ganador_de_subasta(conn, auction_uuid):
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT b.amount, ct.nombre_principal
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
                SELECT b.amount, ct.nombre_principal
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
    return {"amount": row[0], "nombre_principal": row[1]}


def _obtener_datos(conn, auction_uuid):
    subasta = _obtener_subasta(conn, auction_uuid)

    inmueble = {}
    grupo_id = None
    nombre_grupo = ""
    inm_id = None
    fmis_lista = []

    with conn.cursor() as cur:
        cur.execute(
            "SELECT inmueble_id, grupo_id FROM polibid_subastas_v2 WHERE auction_id=%s::uuid ORDER BY id DESC LIMIT 1",
            (auction_uuid,),
        )
        link = cur.fetchone()
        if link and link[0]:
            inm_id = link[0]
            cur.execute(
                """SELECT codigo, numero_matricula, grupo_id, nombre_grupo,
                          area_lote, area_construida, referencia, codigo_grupo
                   FROM mst_inmuebles WHERE id=%s""",
                (inm_id,),
            )
            row = cur.fetchone()
            if row:
                grupo_id = row[2]
                nombre_grupo = row[3] or row[6] or ""
                if grupo_id:
                    inmueble, fmis_lista, nombre_grupo = _buscar_inmueble_por_grupo(conn, grupo_id)
                else:
                    inmueble = {"codigo": row[7] or row[0] or "—", "fmi": row[1] or "—", "area": str(row[4] or row[5] or 0)}
                    fmis_lista = [{"fmi": row[1] or "—", "area": str(row[4] or row[5] or 0)}]
        elif link and link[1]:
            grupo_id = link[1]
            inmueble, fmis_lista, nombre_grupo = _buscar_inmueble_por_grupo(conn, grupo_id)

    if not inmueble:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT mani.grupo_id, mani.inmueble_id
                FROM polybid.auction_participants p
                JOIN polibid_credentials pc ON pc.client_id = p.client_id
                JOIN manifestacion_interes mani ON mani.contact_tercero_id = pc.contact_tercero_id
                WHERE p.auction_id = %s::uuid
                  AND (mani.grupo_id IS NOT NULL OR mani.inmueble_id IS NOT NULL)
                GROUP BY mani.grupo_id, mani.inmueble_id
                ORDER BY COUNT(*) DESC LIMIT 1
                """,
                (auction_uuid,),
            )
            mani = cur.fetchone()
            if mani:
                if mani[0]:
                    grupo_id = mani[0]
                    inmueble, fmis_lista, nombre_grupo = _buscar_inmueble_por_grupo(conn, grupo_id)
                elif mani[1]:
                    inm_id = mani[1]
                    cur.execute(
                        """SELECT codigo, numero_matricula, grupo_id, nombre_grupo,
                                  area_lote, area_construida, referencia, codigo_grupo
                           FROM mst_inmuebles WHERE id=%s""",
                        (inm_id,),
                    )
                    row = cur.fetchone()
                    if row:
                        grupo_id = row[2]
                        if grupo_id:
                            inmueble, fmis_lista, nombre_grupo = _buscar_inmueble_por_grupo(conn, grupo_id)
                        else:
                            nombre_grupo = row[3] or row[6] or ""
                            inmueble = {"codigo": row[7] or row[0] or "—", "fmi": row[1] or "—", "area": str(row[4] or row[5] or 0)}
                            fmis_lista = [{"fmi": row[1] or "—", "area": str(row[4] or row[5] or 0)}]

    ciudad = departamento = "—"
    if nombre_grupo and "," in nombre_grupo:
        parte = nombre_grupo.split("-")[-1].strip() if "-" in nombre_grupo else nombre_grupo
        m = re.search(r"([^,]+),\s*([^,]+)$", parte)
        if m:
            ciudad = m.group(1).strip()
            departamento = m.group(2).strip()
    if ciudad == "—" and inm_id:
        with conn.cursor() as cur:
            try:
                cur.execute(
                    """SELECT c.name, d.name FROM mst_inmuebles mi
                       JOIN cities c ON c.codigo=mi.city_id
                       JOIN departments d ON d.id_departamento=c.id_departamento
                       WHERE mi.id=%s""",
                    (inm_id,),
                )
                row = cur.fetchone()
                if row:
                    ciudad = row[0] or "—"
                    departamento = row[1] or "—"
            except Exception:
                pass

    tipo_inmueble = "—"
    with conn.cursor() as cur:
        try:
            cur.execute(
                """SELECT ti.tipo_inmueble FROM polibid_subastas_v2 psv
                   JOIN mst_inmuebles mi ON mi.id=psv.inmueble_id
                   JOIN mst_tipos_inmueble ti ON ti.id_tipo_inmueble=mi.tipo_inmueble_id
                   WHERE psv.auction_id=%s::uuid ORDER BY psv.id DESC LIMIT 1""",
                (auction_uuid,),
            )
            row = cur.fetchone()
            if row:
                tipo_inmueble = row[0] or "—"
        except Exception:
            pass

    for f in fmis_lista:
        f["direccion"] = nombre_grupo or "—"
        f["ciudad"] = ciudad
        f["departamento"] = departamento
        f["tipo_inmueble"] = tipo_inmueble

    ganador = _ganador_de_subasta(conn, auction_uuid)
    ganador_nombre = (ganador.get("nombre_principal") or "—").upper() if ganador else "—"
    monto_ganador = ganador.get("amount", 0) if ganador else 0
    precio_base = subasta.get("initial_value", 0) or 0
    incremento = "—"
    if precio_base and monto_ganador:
        try:
            incremento = f"{((float(monto_ganador) - float(precio_base)) / float(precio_base)) * 100:.2f}"
        except Exception:
            pass

    participantes = []
    with conn.cursor() as cur:
        cur.execute(
            """SELECT p.id, ct.nombre_principal, ct.email, p.status, p.created_at
               FROM polybid.auction_participants p
               LEFT JOIN polibid_credentials pc ON pc.client_id=p.client_id
               LEFT JOIN contact_terceros ct ON ct.id=pc.contact_tercero_id
               WHERE p.auction_id=%s::uuid ORDER BY p.created_at""",
            (auction_uuid,),
        )
        for row in cur.fetchall():
            participantes.append({
                "id": str(row[0]), "nombre": (row[1] or "—").upper(),
                "correo": (row[2] or "—").lower(), "estado_registro": row[3] or "—",
                "fecha_registro": _fmt_fecha(row[4]),
            })
        inscritos = len(participantes)
        cur.execute("SELECT COUNT(DISTINCT client_id) FROM polybid.auction_bids WHERE auction_id=%s::uuid", (auction_uuid,))
        con_ofertas = cur.fetchone()[0] or 0
        cur.execute("SELECT COUNT(*) FROM polybid.auction_bids WHERE auction_id=%s::uuid", (auction_uuid,))
        total_ofertas = cur.fetchone()[0] or 0

    pujas = []
    with conn.cursor() as cur:
        cur.execute(
            """SELECT b.id, ct.nombre_principal, ct.email, b.amount, b.created_at
               FROM polybid.auction_bids b
               LEFT JOIN polibid_credentials pc ON pc.client_id=b.client_id
               LEFT JOIN contact_terceros ct ON ct.id=pc.contact_tercero_id
               WHERE b.auction_id=%s::uuid ORDER BY b.created_at""",
            (auction_uuid,),
        )
        for row in cur.fetchall():
            pujas.append({
                "id": str(row[0]), "nombre": (row[1] or "—").upper(),
                "email": (row[2] or "—").lower(), "monto": _fmt_numero(row[3]),
                "fecha": row[4].strftime("%d/%m/%Y %H:%M") if row[4] else "—",
            })

    if grupo_id:
        url_pagina = f"https://activosporcolombia.com/es/unidad-inmobiliaria/{grupo_id}/{_slugify(nombre_grupo)}"
    elif inm_id:
        url_pagina = f"https://activosporcolombia.com/es/inmueble/{inm_id}/{_slugify(nombre_grupo)}"
    else:
        url_pagina = "—"

    web = _scrape(grupo_id, nombre_grupo, inm_id)

    fecha_publicacion = web.get("fecha_publicacion", "—")
    if fecha_publicacion == "—":
        with conn.cursor() as cur:
            cur.execute("SELECT created_at FROM polybid.auctions WHERE id = %s::uuid", (auction_uuid,))
            row = cur.fetchone()
            if row and row[0]:
                fecha_publicacion = f"{row[0].day:02d}/{row[0].month:02d}/{row[0].year} " \
                                     f"{row[0].strftime('%I:%M %p').lstrip('0').lower()}"

    fecha_inicio_web = web.get("fecha_inicio", "—")
    fecha_inicio = fecha_inicio_web if fecha_inicio_web != "—" else _fmt_fecha(subasta.get("start_date"))
    fecha_fin_web = web.get("fecha_fin", "—")
    fecha_fin = fecha_fin_web if fecha_fin_web != "—" else _fmt_fecha(subasta.get("end_date"))

    return {
        "codigo_subasta": subasta.get("code", "—") or "—",
        "fecha_publicacion": fecha_publicacion,
        "fecha_inicio": fecha_inicio,
        "fecha_fin": fecha_fin,
        "fmi": inmueble.get("fmi", "—"),
        "direccion": nombre_grupo or "—",
        "ciudad": ciudad,
        "departamento": departamento,
        "tipo_inmueble": tipo_inmueble,
        "area": inmueble.get("area", "—"),
        "codigo_inmueble": inmueble.get("codigo", "—"),
        "precio_base": _fmt_numero(precio_base),
        "nombre_ganador": ganador_nombre,
        "oferta_gandora": _fmt_numero(monto_ganador),
        "incremento": incremento,
        "porcentaje_subasta": incremento,
        "incritos": str(inscritos),
        "ofertas": str(con_ofertas),
        "total_ofertas": str(total_ofertas),
        "url_pagina": url_pagina,
        "participantes": participantes,
        "fmis_grupo": fmis_lista,
        "pujas": pujas,
        **{f"fecha_cronograma{i}": web.get(f"fecha_cronograma{i}", "—") for i in range(1, 17)},
    }


# ---------------------------------------------------------------------
# Tabla de pujas e inserción de imágenes (idéntico al script original)
# ---------------------------------------------------------------------

def _celda_puja(texto, cabecera=False, bg="FFFFFF", ancho="1080"):
    bold = "<w:b/>" if cabecera else ""
    color = '<w:color w:val="FFFFFF"/>' if cabecera else '<w:color w:val="000000"/>'
    fill = "1E3A5F" if cabecera else bg
    shd = f'<w:shd w:val="clear" w:color="auto" w:fill="{fill}"/>'
    borde = '<w:tcBorders><w:top w:val="single" w:sz="4" w:color="CCCCCC"/><w:left w:val="single" w:sz="4" w:color="CCCCCC"/><w:bottom w:val="single" w:sz="4" w:color="CCCCCC"/><w:right w:val="single" w:sz="4" w:color="CCCCCC"/></w:tcBorders>'
    rpr = f'<w:rPr>{bold}{color}<w:rFonts w:ascii="Arial" w:hAnsi="Arial" w:cs="Arial"/><w:sz w:val="18"/><w:szCs w:val="18"/></w:rPr>'
    ppr = f'<w:pPr><w:spacing w:before="60" w:after="60"/>{rpr}</w:pPr>'
    lineas = str(texto).split("\n")
    parrafos = "".join(f'<w:p>{ppr}<w:r>{rpr}<w:t xml:space="preserve">{l}</w:t></w:r></w:p>' for l in lineas)
    return f'<w:tc><w:tcPr><w:tcW w:w="{ancho}" w:type="dxa"/>{borde}{shd}</w:tcPr>{parrafos}</w:tc>'


def _generar_tabla_pujas(pujas):
    if not pujas:
        return '<w:p><w:r><w:t>Sin pujas registradas.</w:t></w:r></w:p>'
    anchos = ["2800", "4200", "2000", "2800"]
    cols = ["ID", "Usuario", "Monto", "Fecha"]
    cabecera = "<w:tr><w:trPr><w:tblHeader/></w:trPr>" + "".join(
        _celda_puja(c, cabecera=True, ancho=a) for c, a in zip(cols, anchos)) + "</w:tr>"
    filas = ""
    for i, p in enumerate(pujas):
        bg = "F0F4F8" if i % 2 == 0 else "FFFFFF"
        usuario = f"{p['nombre']}\n{p['email']}"
        vals = [p["id"], usuario, f"$ {p['monto']}", p["fecha"]]
        filas += "<w:tr>" + "".join(_celda_puja(v, bg=bg, ancho=a) for v, a in zip(vals, anchos)) + "</w:tr>"
    return (
        '<w:tbl><w:tblPr><w:tblW w:w="11800" w:type="dxa"/><w:jc w:val="center"/>'
        '<w:tblBorders><w:top w:val="single" w:sz="4" w:color="CCCCCC"/>'
        '<w:left w:val="single" w:sz="4" w:color="CCCCCC"/>'
        '<w:bottom w:val="single" w:sz="4" w:color="CCCCCC"/>'
        '<w:right w:val="single" w:sz="4" w:color="CCCCCC"/>'
        '<w:insideH w:val="single" w:sz="4" w:color="CCCCCC"/>'
        '<w:insideV w:val="single" w:sz="4" w:color="CCCCCC"/>'
        f'</w:tblBorders></w:tblPr>{cabecera}{filas}</w:tbl><w:p/>'
    )


_CLARITY_ANCHO_EMU = {"foto_clarity": 5619750, "foto_clarity_url": 3924754}


def _siguiente_rid(rels_xml):
    ids = [int(n) for n in re.findall(r'Id="rId(\d+)"', rels_xml)]
    return f"rId{(max(ids) + 1) if ids else 1}"


def _agregar_relacion_imagen(archivos, nombre_media):
    rels_path = "word/_rels/document.xml.rels"
    rels_xml = archivos[rels_path].decode("utf-8")
    nuevo_rid = _siguiente_rid(rels_xml)
    nueva_relacion = (
        f'<Relationship Id="{nuevo_rid}" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" '
        f'Target="media/{nombre_media}"/>'
    )
    rels_xml = rels_xml.replace("</Relationships>", nueva_relacion + "</Relationships>")
    archivos[rels_path] = rels_xml.encode("utf-8")
    return nuevo_rid


def _drawing_xml(rid, cx, cy, doc_id, nombre):
    anchor = f"{doc_id:08X}"
    return (
        "<w:drawing>"
        f'<wp:inline distT="0" distB="0" distL="0" distR="0" '
        f'wp14:anchorId="{anchor}" wp14:editId="{anchor}">'
        f'<wp:extent cx="{cx}" cy="{cy}"/>'
        '<wp:effectExtent l="0" t="0" r="0" b="0"/>'
        f'<wp:docPr id="{doc_id}" name="{nombre}"/>'
        '<wp:cNvGraphicFramePr>'
        '<a:graphicFrameLocks xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" noChangeAspect="1"/>'
        "</wp:cNvGraphicFramePr>"
        '<a:graphic xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">'
        '<a:graphicData uri="http://schemas.openxmlformats.org/drawingml/2006/picture">'
        '<pic:pic xmlns:pic="http://schemas.openxmlformats.org/drawingml/2006/picture">'
        f'<pic:nvPicPr><pic:cNvPr id="{doc_id}" name="{nombre}"/><pic:cNvPicPr/></pic:nvPicPr>'
        f'<pic:blipFill><a:blip r:embed="{rid}" cstate="print"/>'
        "<a:stretch><a:fillRect/></a:stretch></pic:blipFill>"
        f'<pic:spPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="{cx}" cy="{cy}"/></a:xfrm>'
        '<a:prstGeom prst="rect"><a:avLst/></a:prstGeom></pic:spPr>'
        "</pic:pic></a:graphicData></a:graphic></wp:inline></w:drawing>"
    )


def _insertar_imagen_en_placeholder(archivos, doc_xml, placeholder, pil_img, ancho_emu, doc_id, nombre_media):
    marca = f"##{placeholder}##"
    idx = doc_xml.find(marca)
    if idx < 0:
        return doc_xml
    if pil_img is None:
        return doc_xml.replace(marca, "(cifras de tráfico tomadas de la API de Clarity)")

    buf = BytesIO()
    pil_img.save(buf, format="PNG")
    archivos[f"word/media/{nombre_media}"] = buf.getvalue()
    rid = _agregar_relacion_imagen(archivos, nombre_media)

    ancho_px, alto_px = pil_img.size
    cx = ancho_emu
    cy = int(cx * (alto_px / ancho_px)) if ancho_px else ancho_emu

    inicio_t = doc_xml.rfind("<w:t", 0, idx)
    fin_t = doc_xml.find("</w:t>", idx)
    if inicio_t < 0 or fin_t < 0:
        return doc_xml
    fin_t += len("</w:t>")

    dibujo = _drawing_xml(rid, cx, cy, doc_id, placeholder)
    return doc_xml[:inicio_t] + dibujo + doc_xml[fin_t:]


def _imagen_fuente(fmi: str, tipo: str):
    """Carga como imagen PIL la última captura de Clarity subida a mano
    para este caso (tipo 'clarity_resumen' o 'clarity_paginas'), o None si
    todavía no se subió ninguna."""
    doc = db.obtener_ultimo_documento(fmi, tipo)
    if not doc:
        return None
    try:
        from PIL import Image
        return Image.open(BytesIO(doc["contenido"]))
    except Exception:
        return None


def generar_docx(fmi: str, datos: dict, correcciones: dict) -> bytes:
    with zipfile.ZipFile(RUTA_PLANTILLA, "r") as zin:
        archivos = {name: zin.read(name) for name in zin.namelist()}

    doc_xml = archivos["word/document.xml"].decode("utf-8")
    doc_xml = _colapsar_xml(doc_xml)

    fmis_lista = datos.get("fmis_grupo", [])
    if FILA_FMI in doc_xml and fmis_lista:
        filas_fmi = ""
        for item in fmis_lista:
            f = FILA_FMI
            f = f.replace("##fmi##", _limpiar(item.get("fmi", "—")))
            f = f.replace("##direccion##", _limpiar(item.get("direccion", "—")))
            f = f.replace("##ciudad##", _limpiar(item.get("ciudad", "—")))
            f = f.replace("##departamento##", _limpiar(item.get("departamento", "—")))
            f = f.replace("##tipo_inmueble##", _limpiar(item.get("tipo_inmueble", "—")))
            f = f.replace("##area##", _limpiar(item.get("area", "0")))
            filas_fmi += f
        doc_xml = doc_xml.replace(FILA_FMI, filas_fmi)

    idx = doc_xml.find("##id_partipante##")
    if idx >= 0:
        inicio = doc_xml.rfind("<w:tr ", 0, idx)
        fin = doc_xml.find("</w:tr>", idx) + 7
        fila_plantilla = doc_xml[inicio:fin]
        filas_xml = ""
        for part in datos.get("participantes", []):
            f = fila_plantilla
            f = f.replace("##id_partipante##", _limpiar(part.get("id", "—")))
            f = f.replace("##nombre##", _limpiar(part.get("nombre", "—")))
            f = f.replace("##correo##", _limpiar(part.get("correo", "—")))
            f = f.replace("##estado_registro##", _limpiar(part.get("estado_registro", "—")))
            f = f.replace("##fecha_registro##", _limpiar(part.get("fecha_registro", "—")))
            filas_xml += f
        doc_xml = doc_xml[:inicio] + filas_xml + doc_xml[fin:]

    clarity_sesiones_totales = correcciones.get("clarity_sesiones_totales", "—")
    clarity_bots_excluidos = correcciones.get("clarity_bots_excluidos", "—")
    clarity_sesiones_url = correcciones.get("clarity_sesiones_url", "0")
    nombre_ganador = correcciones.get("nombre_ganador", datos["nombre_ganador"])
    fecha_inicio = correcciones.get("fecha_inicio", datos["fecha_inicio"])
    fecha_fin = correcciones.get("fecha_fin", datos["fecha_fin"])

    reemplazos = {
        "##codigo_subasta##": datos["codigo_subasta"],
        "##fecha_publicacion##": datos["fecha_publicacion"],
        "##fecha_inicio##": fecha_inicio,
        "##fecha_fin##": fecha_fin,
        "##fmi##": datos["fmi"],
        "##direccion##": datos["direccion"],
        "##ciudad##": datos["ciudad"],
        "##departamento##": datos["departamento"],
        "##tipo_inmueble##": datos["tipo_inmueble"],
        "##area##": datos["area"],
        "##codigo_inmueble##": datos["codigo_inmueble"],
        "##precio_base##": datos["precio_base"],
        "##nombre_ganador##": nombre_ganador,
        "##oferta_gandora##": datos["oferta_gandora"],
        "##incremento##": datos["incremento"],
        "##porcentaje_subasta##": datos["porcentaje_subasta"],
        "##incritos##": datos["incritos"],
        "##ofertas##": datos["ofertas"],
        "##total_ofertas##": datos["total_ofertas"],
        "##url_pagina##": datos["url_pagina"],
        "##clarity_sesiones_totales##": clarity_sesiones_totales,
        "##clarity_bots_excluidos##": clarity_bots_excluidos,
        "##clarity_sesiones_url##": clarity_sesiones_url,
        "##cantidad##": clarity_sesiones_totales if clarity_sesiones_totales != "—" else "0",
        "##cantidad_sesiones##": clarity_bots_excluidos if clarity_bots_excluidos != "—" else "0",
        "##cantidad_url##": clarity_sesiones_url,
    }
    for i in range(1, 17):
        reemplazos[f"##fecha_cronograma{i}##"] = datos.get(f"fecha_cronograma{i}", "—")

    for ph, val in reemplazos.items():
        doc_xml = doc_xml.replace(ph, _limpiar(val))

    idx_tabla = doc_xml.find("##tabla_pujas##")
    if idx_tabla >= 0:
        inicio_p = doc_xml.rfind("<w:p ", 0, idx_tabla)
        fin_p = doc_xml.find("</w:p>", idx_tabla) + 6
        doc_xml = doc_xml[:inicio_p] + _generar_tabla_pujas(datos.get("pujas", [])) + doc_xml[fin_p:]

    doc_xml = _insertar_imagen_en_placeholder(
        archivos, doc_xml, "foto_clarity", _imagen_fuente(fmi, "clarity_resumen"),
        _CLARITY_ANCHO_EMU["foto_clarity"], 900001, "clarity_resumen.png",
    )
    doc_xml = _insertar_imagen_en_placeholder(
        archivos, doc_xml, "foto_clarity_url", _imagen_fuente(fmi, "clarity_paginas"),
        _CLARITY_ANCHO_EMU["foto_clarity_url"], 900002, "clarity_paginas.png",
    )

    archivos["word/document.xml"] = doc_xml.encode("utf-8")

    if "word/footer1.xml" in archivos:
        footer = archivos["word/footer1.xml"].decode("utf-8")
        footer = footer.replace("##fecha_publicacion##", _limpiar(datos["fecha_publicacion"]))
        footer = footer.replace("##codigo_subasta##", _limpiar(datos["codigo_subasta"]))
        archivos["word/footer1.xml"] = footer.encode("utf-8")

    salida = io.BytesIO()
    with zipfile.ZipFile(salida, "w", zipfile.ZIP_DEFLATED) as zout:
        for name, d in archivos.items():
            zout.writestr(name, d)
    return salida.getvalue()


def generar(fmi: str) -> tuple[bytes, str, list[str]]:
    with db.get_conn_negocio_tuplas() as conn:
        auction_uuid = _resolver_identificador(conn, fmi)
        datos = _obtener_datos(conn, auction_uuid)

    correcciones = db.obtener_correcciones(fmi)

    pendientes: list[str] = []

    # Cifras de Clarity: si el usuario no las corrigió a mano, se intenta
    # traerlas solas desde la API de Clarity (ver core/clarity.py). Si la
    # API no tiene token configurado o no devuelve datos (por ejemplo, ya
    # pasaron más de 1-3 días desde que hubo tráfico), el documento se
    # genera igual, solo que sin esas 3 cifras.
    if "clarity_sesiones_totales" not in correcciones:
        metricas = clarity.obtener_metricas_clarity(datos.get("url_pagina"))
        if metricas:
            correcciones = {
                **correcciones,
                "clarity_sesiones_totales": str(metricas["sesiones_totales"]),
                "clarity_bots_excluidos": str(metricas["bots_excluidos"]),
                "clarity_sesiones_url": str(metricas["sesiones_url"]),
            }
        else:
            pendientes.append(
                "Sesiones de Clarity: la API no devolvió datos (sin token configurado, o ya "
                "pasó la ventana de 1-3 días que cubre) -- si hacen falta, complétalas a mano "
                "en 'Editar campos'."
            )

    if datos["nombre_ganador"] == "—":
        pendientes.append("Oferente ganador: no se encontró en la base de datos, revisar a mano.")
    if datos["fecha_inicio"] == "—" or datos["fecha_fin"] == "—":
        pendientes.append("Fechas de apertura/cierre: no se pudieron obtener del sitio web, revisar a mano.")

    contenido = generar_docx(fmi, datos, correcciones)
    codigo_corto = re.sub(r"[^A-Za-z0-9]+", "_", datos["codigo_subasta"].replace("ACTIBID-", ""))[:20]
    nombre_archivo = f"INFORME_{codigo_corto or fmi}.docx"

    db.upsert_caso(fmi, {
        "estado": "con_observaciones" if pendientes else "completo",
        "pendientes": pendientes,
    })
    return contenido, nombre_archivo, pendientes
