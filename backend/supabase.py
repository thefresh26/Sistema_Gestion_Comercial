"""
Todo el diálogo HTTP con Supabase pasa por aquí: cabeceras, URLs y las
llamadas que más de un módulo repite (RPC y la lista paginada de usuarios
de Auth).

Las rutas de `backend/rutas/` usan estas funciones en vez de armar a mano
la URL y las cabeceras — así la clave de servicio aparece en un solo sitio.
"""
from __future__ import annotations

import requests

from backend import config


def url(ruta: str) -> str:
    """URL absoluta del proyecto Supabase, p. ej. `url("/rest/v1/tabla")`."""
    return f"{config.SUPABASE_URL}{ruta}"


def cabeceras_anon() -> dict[str, str]:
    """Para el login: la anon key, que es la que valida credenciales."""
    return {
        "apikey": config.SUPABASE_ANON_KEY,
        "Content-Type": "application/json",
    }


def cabeceras_servicio() -> dict[str, str]:
    """Para todo lo demás: la service_role key, que nunca sale del backend."""
    return {
        "apikey": config.SUPABASE_SERVICE_ROLE_KEY,
        "Authorization": f"Bearer {config.SUPABASE_SERVICE_ROLE_KEY}",
        "Content-Type": "application/json",
    }


def rpc(nombre: str, payload: dict, timeout: int = 15) -> requests.Response:
    """Llama una función RPC de Postgres expuesta por Supabase."""
    return requests.post(
        url(f"/rest/v1/rpc/{nombre}"),
        headers=cabeceras_servicio(),
        json=payload,
        timeout=timeout,
    )


def listar_usuarios_auth() -> list[dict] | None:
    """Todos los usuarios de Supabase Auth, recorriendo la paginación.
    Devuelve None si alguna página falla (el llamador responde el 502)."""
    usuarios: list[dict] = []
    pagina = 1
    while True:
        r = requests.get(
            url("/auth/v1/admin/users"),
            headers=cabeceras_servicio(),
            params={"page": pagina, "per_page": 200},
            timeout=15,
        )
        if r.status_code != 200:
            return None
        pagina_datos = r.json().get("users", [])
        if not pagina_datos:
            break
        usuarios.extend(pagina_datos)
        if len(pagina_datos) < 200:
            break
        pagina += 1
    return usuarios
