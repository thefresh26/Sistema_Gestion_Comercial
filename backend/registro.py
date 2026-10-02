"""
Registro de eventos (login, búsquedas, generación de documentos…).

Todo el sistema unificado escribe en una sola tabla `logs_acceso_sistema`
(ver `sql/00_logs_unificado.sql`) con una columna `modulo` para distinguir
de dónde viene cada evento.
"""
from __future__ import annotations

import requests
from flask import request

from backend import supabase


def obtener_ip_cliente() -> str | None:
    """IP real del usuario: detrás de Render la verdadera viene en
    X-Forwarded-For, no en remote_addr."""
    xff = request.headers.get("X-Forwarded-For", "")
    if xff:
        return xff.split(",")[0].strip()
    return request.remote_addr


def registrar_log(modulo, email, accion, detalle=None, ip=None) -> None:
    """Mejor esfuerzo: si falla el log, no interrumpe la respuesta al
    usuario."""
    try:
        requests.post(
            supabase.url("/rest/v1/logs_acceso_sistema"),
            headers=supabase.cabeceras_servicio(),
            json={
                "modulo": modulo,
                "usuario_email": email,
                "accion": accion,
                "detalle": detalle,
                "ip_address": ip,
            },
            timeout=5,
        )
    except Exception:
        pass
