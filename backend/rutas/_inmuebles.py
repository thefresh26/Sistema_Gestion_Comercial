"""
Búsqueda de inmuebles por FMI, compartida por el módulo Vista Inmuebles
(usuarios del portal) y por la API de integración externa (otros sistemas).
Ambos leen exactamente los mismos datos, solo cambia cómo se autentican.
"""
from __future__ import annotations

from backend import supabase


def buscar_inmuebles_por_fmi(fmis: list[str]) -> list[dict] | None:
    """Los inmuebles que existan, en el orden pedido. Devuelve None si la
    base de datos falla (el llamador responde el 502).

    La RPC `buscar_inmueble_activos` solo busca un FMI a la vez, así que
    para varios se le pregunta uno por uno — son consultas puntuales por
    matrícula, no un listado masivo, así que el costo del ciclo es
    insignificante.
    """
    resultados = []
    for fmi in fmis:
        r = supabase.rpc("buscar_inmueble_activos", {"p_fmi": fmi})
        if r.status_code != 200:
            return None
        dato = r.json()  # null (no existe) o el objeto jsonb del inmueble
        if dato:
            resultados.append(dato)
    return resultados
