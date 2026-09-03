"""
actualizar_dashboard.py — Cron Job del dashboard "Estadísticas".

Se conecta UNA VEZ al día (o con la frecuencia que se configure en Render)
a dos fuentes:

  1. La base de datos "intranet" en Azure (solo lectura), para sacar
     cuántos inmuebles de SAE están en estado "Vendido" y su valor, por
     año Y MES — usando fecha_cambio_estado, que sí es una fecha real.
     Se calculan DOS medidas, porque en el negocio son cosas distintas:
       - "folio": cada registro individual de mst_inmuebles (cada folio
         de matrícula).
       - "unidad": un conjunto de folios agrupados en mst_inmuebles bajo
         un mismo grupo_id (una "unidad" puede tener varios folios; al
         venderse la unidad se venden todos sus folios juntos). Un folio
         sin grupo_id es una unidad de un solo folio.

  2. El archivo frv/data.json, para sacar cuántos bienes de FRV están en
     etapa "MONETIZADO" y su valor (VALOR AVALÚO — ver nota abajo). Ese
     archivo NO tiene fecha de venta, así que este script lleva su propio
     control de "cuáles ya había visto" en la tabla
     dashboard_frv_seguimiento, para poder ir armando un historial real
     por año y mes a partir de la fecha en que cada uno se detecta por
     primera vez como monetizado.

El resultado final (cantidad y valor por año Y MES, por sistema) se guarda
en la tabla dashboard_ventas_anual de Supabase. La ruta
/api/dashboard/resumen de app.py SOLO lee esa tabla — nunca consulta la
base "intranet" directamente, así que un problema de red hacia Azure
nunca puede tumbar el portal.

Variables de entorno necesarias (configurar en Render → el Cron Job
también, no solo el Web Service):

  SUPABASE_URL
  SUPABASE_SERVICE_ROLE_KEY

  INTRANET_DB_HOST      p.ej. actibox-ro.postgres.database.azure.com
  INTRANET_DB_PORT      5432
  INTRANET_DB_NAME      intranet
  INTRANET_DB_USER      el usuario de solo lectura
  INTRANET_DB_PASSWORD  la contraseña — SOLO como variable de entorno en
                        Render, nunca en este archivo ni en el chat.

Se ejecuta como un Render "Cron Job" aparte (ver render.yaml), no dentro
del proceso web — así una consulta lenta a Azure nunca demora al portal.
"""

import os
import sys
import json
from datetime import date
from collections import defaultdict

import requests

try:
    import psycopg2
    import psycopg2.extras
except ImportError:
    psycopg2 = None

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_SERVICE_ROLE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")

INTRANET_DB_HOST = os.environ.get("INTRANET_DB_HOST", "")
INTRANET_DB_PORT = os.environ.get("INTRANET_DB_PORT", "5432")
INTRANET_DB_NAME = os.environ.get("INTRANET_DB_NAME", "intranet")
INTRANET_DB_USER = os.environ.get("INTRANET_DB_USER", "")
INTRANET_DB_PASSWORD = os.environ.get("INTRANET_DB_PASSWORD", "")

ESTADO_VENDIDO_ID = 6      # mst_estados_inmueble.codigo = 'VENDIDO'
OPERATOR_ID_SAE = 2        # mst_operators.nombre = 'SAE'


def log(msg):
    print(f"[actualizar_dashboard] {msg}", flush=True)


# ── SAE: se calcula en vivo contra la base "intranet" ──────────────────

def calcular_sae():
    if not psycopg2:
        log("psycopg2 no está instalado — no se puede consultar la base intranet.")
        return {}
    if not INTRANET_DB_HOST or not INTRANET_DB_PASSWORD:
        log("Faltan variables INTRANET_DB_* — se omite el cálculo de SAE.")
        return {}

    conn = psycopg2.connect(
        host=INTRANET_DB_HOST,
        port=INTRANET_DB_PORT,
        dbname=INTRANET_DB_NAME,
        user=INTRANET_DB_USER,
        password=INTRANET_DB_PASSWORD,
        sslmode="require",
        connect_timeout=15,
    )
    try:
        with conn.cursor() as cur:
            cur.execute("""
                WITH vendidos AS (
                    SELECT
                        id,
                        grupo_id,
                        fecha_cambio_estado,
                        COALESCE(precio_base_venta, valor_avaluo_comercial, valor_minimo_venta, 0) AS valor
                    FROM mst_inmuebles
                    WHERE estado_id = %(estado_id)s AND operator_id = %(operator_id)s
                ),
                folios AS (
                    SELECT
                        EXTRACT(YEAR FROM fecha_cambio_estado)::int AS anio,
                        EXTRACT(MONTH FROM fecha_cambio_estado)::int AS mes,
                        COUNT(*) AS cantidad,
                        SUM(valor) AS valor_total,
                        'folio' AS medida
                    FROM vendidos
                    GROUP BY anio, mes
                ),
                unidades_base AS (
                    -- Cada "unidad" es un grupo_id distinto (o, si no tiene
                    -- grupo, el folio individual actúa como su propia unidad).
                    SELECT
                        COALESCE(grupo_id::text, 'ind-' || id::text) AS unidad_key,
                        MIN(fecha_cambio_estado) AS fecha_unidad,
                        SUM(valor) AS valor_unidad
                    FROM vendidos
                    GROUP BY COALESCE(grupo_id::text, 'ind-' || id::text)
                ),
                unidades AS (
                    SELECT
                        EXTRACT(YEAR FROM fecha_unidad)::int AS anio,
                        EXTRACT(MONTH FROM fecha_unidad)::int AS mes,
                        COUNT(*) AS cantidad,
                        SUM(valor_unidad) AS valor_total,
                        'unidad' AS medida
                    FROM unidades_base
                    GROUP BY anio, mes
                )
                SELECT anio, mes, cantidad, valor_total, medida FROM folios
                UNION ALL
                SELECT anio, mes, cantidad, valor_total, medida FROM unidades
                ORDER BY anio, mes, medida;
            """, {"estado_id": ESTADO_VENDIDO_ID, "operator_id": OPERATOR_ID_SAE})
            filas = cur.fetchall()
    finally:
        conn.close()

    resultado = {}
    for anio, mes, cantidad, valor_total, medida in filas:
        resultado[(anio, mes, medida)] = {"cantidad": cantidad, "valor_total": float(valor_total or 0)}
    log(f"SAE: {resultado}")
    return resultado


# ── SUBASTAS: se calcula en vivo contra la base "intranet", combinando
#    LEGACY (mst_subastas + mst_subastas_pujas) y Actibid/Polybid
#    (polybid.auctions + polybid.auction_bids vía la tabla puente
#    polibid_subastas_v2) ────────────────────────────────────────────────
#
# Metodologia verificada manualmente el 2026-09-03 contra ambos sistemas:
#   - Cada subasta ganada se resuelve a UN solo FMI: el del inmueble
#     mismo (tipo INMUEBLE) o el del inmueble "padre" del grupo (tipo
#     GRUPO_INMUEBLE / UNIDAD) -- asi nunca se cuenta un garaje o
#     deposito por separado si ya esta incluido en la venta del grupo.
#   - Se excluyen subastas con estado CANCELADA (LEGACY) o que no
#     lleguen a "FINISHED" (Actibid), y toda fila donde el inmueble
#     tenga la bandera mst_inmuebles.test = true (datos de prueba).
#   - En Actibid, se exige que la subasta este vinculada a un inmueble
#     real via polibid_subastas_v2 (pv.id IS NOT NULL) -- esto excluye
#     automaticamente el ruido de pruebas ("Subasta Rapida", "DEMO...",
#     subastas repetidas del mismo inmueble en el periodo de pruebas
#     ene-mar 2026) sin necesidad de listar cada titulo a mano.
#   - Si un mismo inmueble tiene mas de una subasta ganada (p.ej. una
#     puja con un valor claramente anomalo seguida de una re-subasta
#     real), se usa la de fecha de cierre MAS RECIENTE como la venta
#     valida -- confirmado con los casos reales 370-527439 y
#     50N-20184713 encontrados en esta auditoria.
#   - A diferencia de "SAE", esta consulta NO depende de
#     mst_inmuebles.estado_id: se basa en que exista una puja ganadora
#     real, porque se detecto un bug de sincronizacion donde el
#     inmueble se queda en estado SUBASTA_FINALIZADA sin llegar nunca a
#     VENDIDO, y otros casos donde una venta ganada fue despublicada o
#     devuelta a estados anteriores sin dejar registro del motivo. La
#     puja ganadora real es la fuente de verdad, no el estado actual.
#   - LIMITACION CONOCIDA: no incluye ventas cerradas sin ninguna puja
#     registrada (un puñado de casos historicos de 2025 donde el valor
#     se tomo manualmente de la ficha del inmueble) -- esos requieren
#     revision manual y no se pueden detectar solo con esta consulta.

def calcular_subastas():
    if not psycopg2:
        log("psycopg2 no está instalado — no se puede consultar la base intranet.")
        return {}
    if not INTRANET_DB_HOST or not INTRANET_DB_PASSWORD:
        log("Faltan variables INTRANET_DB_* — se omite el cálculo de SUBASTAS.")
        return {}

    conn = psycopg2.connect(
        host=INTRANET_DB_HOST,
        port=INTRANET_DB_PORT,
        dbname=INTRANET_DB_NAME,
        user=INTRANET_DB_USER,
        password=INTRANET_DB_PASSWORD,
        sslmode="require",
        connect_timeout=15,
    )
    try:
        with conn.cursor() as cur:
            cur.execute("""
                WITH legacy AS (
                    SELECT
                        i.numero_matricula AS fmi,
                        MAX(p.monto) AS valor,
                        s.fecha_fin AS fecha_cierre
                    FROM public.mst_subastas s
                    JOIN public.mst_subastas_pujas p ON p.auction_id = s.id
                    LEFT JOIN public.mst_inmuebles i_ind
                        ON s.tipo_subasta = 'INMUEBLE' AND i_ind.id = s.objeto_id
                    LEFT JOIN public.mst_inmuebles_grupos ig
                        ON s.tipo_subasta = 'GRUPO_INMUEBLE' AND ig.grupo_id = s.objeto_id AND ig.es_padre
                    LEFT JOIN public.mst_inmuebles i_grp ON i_grp.id = ig.inmueble_id
                    JOIN public.mst_inmuebles i ON i.id = COALESCE(i_ind.id, i_grp.id)
                    WHERE s.estado <> 'CANCELADA'
                      AND COALESCE(i.test, false) = false
                    GROUP BY i.numero_matricula, s.id, s.fecha_fin
                ),
                actibid AS (
                    SELECT
                        i.numero_matricula AS fmi,
                        ab.amount AS valor,
                        a.end_date AS fecha_cierre
                    FROM polybid.auctions a
                    JOIN polybid.auction_bids ab ON ab.auction_id = a.id AND ab.status = 'WINNING'
                    JOIN public.polibid_subastas_v2 pv ON pv.auction_id = a.id
                    LEFT JOIN public.mst_inmuebles i_ind ON i_ind.id = pv.inmueble_id
                    LEFT JOIN public.mst_inmuebles_grupos ig ON ig.grupo_id = pv.grupo_id AND ig.es_padre
                    LEFT JOIN public.mst_inmuebles i_grp ON i_grp.id = ig.inmueble_id
                    JOIN public.mst_inmuebles i ON i.id = COALESCE(i_ind.id, i_grp.id)
                    WHERE a.status = 'FINISHED'
                      AND COALESCE(i.test, false) = false
                ),
                todas AS (
                    SELECT * FROM legacy
                    UNION ALL
                    SELECT * FROM actibid
                ),
                por_propiedad AS (
                    SELECT DISTINCT ON (fmi) fmi, valor, fecha_cierre
                    FROM todas
                    ORDER BY fmi, fecha_cierre DESC
                )
                SELECT
                    EXTRACT(YEAR FROM fecha_cierre)::int AS anio,
                    EXTRACT(MONTH FROM fecha_cierre)::int AS mes,
                    COUNT(*) AS cantidad,
                    SUM(valor) AS valor_total
                FROM por_propiedad
                GROUP BY anio, mes
                ORDER BY anio, mes;
            """)
            filas = cur.fetchall()
    finally:
        conn.close()

    resultado = {}
    for anio, mes, cantidad, valor_total in filas:
        resultado[(anio, mes)] = {"cantidad": cantidad, "valor_total": float(valor_total or 0)}
    log(f"SUBASTAS: {resultado}")
    return resultado


# ── FRV: se calcula desde data.json + el seguimiento propio en Supabase ─

def _num(valor_texto):
    if not valor_texto:
        return 0.0
    try:
        return float(str(valor_texto).replace(",", "").strip())
    except ValueError:
        return 0.0


def supabase_get(tabla, params=""):
    r = requests.get(
        f"{SUPABASE_URL}/rest/v1/{tabla}{params}",
        headers={
            "apikey": SUPABASE_SERVICE_ROLE_KEY,
            "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
        },
        timeout=15,
    )
    r.raise_for_status()
    return r.json()


def supabase_upsert(tabla, filas, on_conflict):
    if not filas:
        return
    r = requests.post(
        f"{SUPABASE_URL}/rest/v1/{tabla}?on_conflict={on_conflict}",
        headers={
            "apikey": SUPABASE_SERVICE_ROLE_KEY,
            "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
            "Content-Type": "application/json",
            "Prefer": "resolution=merge-duplicates",
        },
        json=filas,
        timeout=30,
    )
    r.raise_for_status()


def calcular_frv():
    ruta = os.path.join(BASE_DIR, "modulos", "frv", "data.json")
    if not os.path.exists(ruta):
        log("No se encontró frv/data.json — se omite el cálculo de FRV.")
        return {}

    with open(ruta, "r", encoding="utf-8") as f:
        data = json.load(f)

    monetizados = {
        r.get("CÓDIGO FRV") or r.get("CÓDIGO"): r
        for r in data
        if r.get("ETAPA GESTIÓN") == "MONETIZADO"
    }
    log(f"FRV: {len(monetizados)} bienes en MONETIZADO en data.json")

    ya_vistos = {
        fila["codigo_frv"]: fila
        for fila in supabase_get("dashboard_frv_seguimiento", "?select=codigo_frv,fecha_detectado,valor_contable")
    }

    hoy = date.today().isoformat()
    nuevos = []
    for codigo, registro in monetizados.items():
        if not codigo or codigo in ya_vistos:
            continue
        nuevos.append({
            "codigo_frv": codigo,
            "fecha_detectado": hoy,
            "valor_contable": _num(registro.get("VALOR CONTABLE")),
        })

    if nuevos:
        log(f"FRV: {len(nuevos)} bienes nuevos detectados como MONETIZADO, se registran con fecha {hoy}.")
        supabase_upsert("dashboard_frv_seguimiento", nuevos, on_conflict="codigo_frv")

    # Releer todo el seguimiento (ya con los nuevos incluidos) y agrupar por
    # año Y MES de detección.
    todos = supabase_get("dashboard_frv_seguimiento", "?select=fecha_detectado,valor_contable")
    por_anio_mes = defaultdict(lambda: {"cantidad": 0, "valor_total": 0.0})
    for fila in todos:
        fecha_texto = str(fila["fecha_detectado"])
        anio = int(fecha_texto[:4])
        mes = int(fecha_texto[5:7])
        clave = (anio, mes)
        por_anio_mes[clave]["cantidad"] += 1
        por_anio_mes[clave]["valor_total"] += float(fila.get("valor_contable") or 0)

    log(f"FRV agrupado por año y mes: {dict(por_anio_mes)}")
    return dict(por_anio_mes)


def guardar_resultado(sistema, datos_por_clave, clave_primera_corrida=None):
    """
    datos_por_clave: dict con clave (anio, mes) o (anio, mes, medida) —> {cantidad, valor_total}.
    Si la clave no trae medida (FRV, que no distingue folio/unidad), se guarda con medida='total'.
    """
    filas = []
    for clave, datos in datos_por_clave.items():
        if len(clave) == 3:
            anio, mes, medida = clave
            clave_comparar = (anio, mes)
        else:
            anio, mes = clave
            medida = "total"
            clave_comparar = clave
        filas.append({
            "sistema": sistema,
            "anio": anio,
            "mes": mes,
            "medida": medida,
            "cantidad": datos["cantidad"],
            "valor_total": datos["valor_total"],
            "es_acumulado_historico": (clave_comparar == clave_primera_corrida),
            "actualizado_en": "now()",
        })
    supabase_upsert("dashboard_ventas_anual", filas, on_conflict="sistema,anio,mes,medida")


def main():
    if not SUPABASE_URL or not SUPABASE_SERVICE_ROLE_KEY:
        log("Faltan SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY. Abortando.")
        sys.exit(1)

    sae = calcular_sae()
    if sae:
        guardar_resultado("SAE", sae)

    try:
        subastas = calcular_subastas()
        if subastas:
            guardar_resultado("SUBASTAS", subastas)
    except Exception as e:
        # No dejamos que un problema en SUBASTAS tumbe el resto del cron
        # (SAE ya se guardo arriba, y FRV todavia tiene que correr abajo).
        log(f"SUBASTAS: fallo el calculo, se omite esta corrida. Detalle: {e}")

    frv = calcular_frv()
    if frv:
        # El primer año-mes en el que aparece cualquier registro de
        # seguimiento es el "bloque histórico inicial" (todo lo que ya
        # estaba MONETIZADO antes de activar este dashboard, sin fecha
        # real de venta).
        clave_inicial = min(frv.keys())
        guardar_resultado("FRV", frv, clave_primera_corrida=clave_inicial)

    log("Listo.")


if __name__ == "__main__":
    main()
