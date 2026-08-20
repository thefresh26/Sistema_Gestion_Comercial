"""
actualizar_dashboard.py — Cron Job del dashboard "Estadísticas".

Se conecta UNA VEZ al día (o con la frecuencia que se configure en Render)
a dos fuentes:

  1. La base de datos "intranet" en Azure (solo lectura), para sacar
     cuántos inmuebles de SAE están en estado "Vendido" y su valor, por
     año — usando fecha_cambio_estado, que sí es una fecha real.

  2. El archivo frv/data.json, para sacar cuántos bienes de FRV están en
     etapa "MONETIZADO" y su valor (VALOR AVALÚO — ver nota abajo). Ese
     archivo NO tiene fecha de venta, así que este script lleva su propio
     control de "cuáles ya había visto" en la tabla
     dashboard_frv_seguimiento, para poder ir armando un historial real
     por año a partir de la fecha en que cada uno se detecta por primera
     vez como monetizado.

El resultado final (cantidad y valor por año, por sistema) se guarda en
la tabla dashboard_ventas_anual de Supabase. La ruta /api/dashboard/resumen
de app.py SOLO lee esa tabla — nunca consulta la base "intranet"
directamente, así que un problema de red hacia Azure nunca puede tumbar
el portal.

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
                SELECT
                    EXTRACT(YEAR FROM fecha_cambio_estado)::int AS anio,
                    COUNT(*) AS cantidad,
                    SUM(COALESCE(precio_base_venta, valor_avaluo_comercial, valor_minimo_venta, 0)) AS valor_total
                FROM mst_inmuebles
                WHERE estado_id = %s AND operator_id = %s
                GROUP BY anio
                ORDER BY anio;
            """, (ESTADO_VENDIDO_ID, OPERATOR_ID_SAE))
            filas = cur.fetchall()
    finally:
        conn.close()

    resultado = {}
    for anio, cantidad, valor_total in filas:
        resultado[anio] = {"cantidad": cantidad, "valor_total": float(valor_total or 0)}
    log(f"SAE: {resultado}")
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
    ruta = os.path.join(BASE_DIR, "frv", "data.json")
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

    # Releer todo el seguimiento (ya con los nuevos incluidos) y agrupar por año.
    todos = supabase_get("dashboard_frv_seguimiento", "?select=fecha_detectado,valor_contable")
    por_anio = defaultdict(lambda: {"cantidad": 0, "valor_total": 0.0})
    for fila in todos:
        anio = int(str(fila["fecha_detectado"])[:4])
        por_anio[anio]["cantidad"] += 1
        por_anio[anio]["valor_total"] += float(fila.get("valor_contable") or 0)

    log(f"FRV agrupado por año: {dict(por_anio)}")
    return dict(por_anio)


def guardar_resultado(sistema, por_anio, anio_primera_corrida=None):
    filas = []
    for anio, datos in por_anio.items():
        filas.append({
            "sistema": sistema,
            "anio": anio,
            "cantidad": datos["cantidad"],
            "valor_total": datos["valor_total"],
            "es_acumulado_historico": (anio == anio_primera_corrida),
            "actualizado_en": "now()",
        })
    supabase_upsert("dashboard_ventas_anual", filas, on_conflict="sistema,anio")


def main():
    if not SUPABASE_URL or not SUPABASE_SERVICE_ROLE_KEY:
        log("Faltan SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY. Abortando.")
        sys.exit(1)

    sae = calcular_sae()
    if sae:
        guardar_resultado("SAE", sae)

    frv = calcular_frv()
    if frv:
        # El primer año en el que aparece cualquier registro de seguimiento
        # es el "bloque histórico inicial" (todo lo que ya estaba
        # MONETIZADO antes de activar este dashboard, sin fecha real).
        anio_inicial = min(frv.keys())
        guardar_resultado("FRV", frv, anio_primera_corrida=anio_inicial)

    log("Listo.")


if __name__ == "__main__":
    main()
