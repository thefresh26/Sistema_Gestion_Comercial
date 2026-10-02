"""
Integración con la API oficial de exportación de datos de Microsoft
Clarity (https://www.clarity.ms/export-data/api/v1/project-live-insights).

Esto reemplaza el paso manual de "sube 2 capturas de pantalla de Clarity y
escribe a mano las cifras de sesiones" que tenía el Informe de Subasta: en
vez de depender de la sesión personal del usuario en su navegador, el
sistema llama directamente a esta API con un TOKEN DE PROYECTO (no una
contraseña personal -- se genera desde Clarity > Configuración > Exportar
datos > Generar nuevo token de API, y es seguro guardarlo como variable de
entorno, a diferencia de una contraseña).

Limitación real de la API (no depende de este código): solo cubre el
tráfico de los últimos 1 a 3 días. Si el Informe se genera mucho después
de que cierra la subasta, esta API ya no va a tener esos datos -- en ese
caso `obtener_metricas_clarity` devuelve None y el sistema sigue
funcionando igual, simplemente sin esas 3 cifras (el documento se genera
de todas formas).
"""
from __future__ import annotations

import os

import requests

CLARITY_API_TOKEN = os.environ.get("CLARITY_API_TOKEN", "")
CLARITY_ENDPOINT = "https://www.clarity.ms/export-data/api/v1/project-live-insights"


def obtener_metricas_clarity(url_pagina: str | None, num_dias: int = 3) -> dict | None:
    """Devuelve {'sesiones_totales', 'bots_excluidos', 'sesiones_url'} a
    partir de la API de Clarity, o None si no hay token configurado, la
    API falla, o no devuelve datos (por ejemplo, porque ya pasaron más de
    1-3 días desde que hubo tráfico)."""
    if not CLARITY_API_TOKEN:
        return None

    try:
        resp = requests.get(
            CLARITY_ENDPOINT,
            params={"numOfDays": num_dias, "dimension1": "URL"},
            headers={"Authorization": f"Bearer {CLARITY_API_TOKEN}"},
            timeout=15,
        )
        resp.raise_for_status()
        datos = resp.json()
    except Exception:
        return None

    if not isinstance(datos, list):
        return None

    total_sesiones = 0
    total_bots = 0
    sesiones_url = 0
    encontrado_url = False
    huella_pagina = (url_pagina or "").strip().rstrip("/").lower()

    for metrica in datos:
        if metrica.get("metricName") != "Traffic":
            continue
        for info in metrica.get("information", []) or []:
            try:
                sesiones = int(float(info.get("totalSessionCount", 0) or 0))
            except (TypeError, ValueError):
                sesiones = 0
            try:
                bots = int(float(info.get("totalBotSessionCount", 0) or 0))
            except (TypeError, ValueError):
                bots = 0
            total_sesiones += sesiones
            total_bots += bots

            url_fila = (info.get("URL") or info.get("Url") or info.get("url") or "").strip().rstrip("/").lower()
            if huella_pagina and url_fila and huella_pagina in url_fila:
                sesiones_url += sesiones
                encontrado_url = True

    if total_sesiones == 0 and total_bots == 0:
        # La API respondió pero sin ningún dato de tráfico -- probablemente
        # ya pasó la ventana de 1-3 días que cubre.
        return None

    return {
        "sesiones_totales": total_sesiones,
        "bots_excluidos": total_bots,
        "sesiones_url": sesiones_url if encontrado_url else 0,
    }
