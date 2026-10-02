# Permisos por rol

Este documento explica quién ve qué dentro del portal.

Todo se controla en un solo archivo, [`backend/permisos.py`](../backend/permisos.py):

- `MODULOS` — qué roles pueden entrar a cada módulo.
- `ROLES_SIN_AVALUO_FRV` — qué roles **no** ven los campos de avalúo
  dentro de FRV (aunque sí tengan acceso al módulo).
- `ROLES_VISIBLES` — cómo se llama cada rol en pantalla.

Si cambian las reglas de negocio, ese archivo es el único que hay que
tocar en el código — y hay que actualizar este documento con el cambio. El
panel de Permisos (`/admin/`) permite crear usuarios y asignarles rol sin
tocar código en absoluto.

## Qué ve cada rol

| Rol | Expresiones SAE | Inmuebles FRV | Vista Inmuebles | Estadísticas | Administración | Documentos |
|---|---|---|---|---|---|---|
| `comercial` | Sí | Sí (sin avalúos) | Sí | Sí | No | Sí |
| `juridico` | No | Sí (con avalúos) | No | No | No | No |
| `admin` | Sí | Sí (con avalúos) | Sí | Sí | Sí | Sí |
| `sae` | Sí | No | No | No | No | No |
| `comunicaciones` | No | Sí (sin avalúos) | Sí | No | No | No |
| `territoriales` | No | Sí (con avalúos) | Sí | No | No | No |
| `sin_acceso` | No | No | No | No | No | No |

`sin_acceso` es un rol especial: el usuario puede seguir iniciando sesión
(ve "Inicio") pero no ve ningún módulo — sirve para revocar acceso sin
borrar la cuenta.

## Los campos de avalúo de FRV

El módulo FRV no manda al navegador la fila completa del `data.json`: solo
los campos de una lista blanca, en `backend/rutas/frv.py`.

- `CAMPOS_BASE` — los que ve cualquier rol con acceso al módulo.
- `CAMPOS_AVALUO` — los de avalúo, que se agregan **solo** para roles que
  no están en `ROLES_SIN_AVALUO_FRV`.

Se usa lista blanca a propósito: si el scraper de FRV agrega columnas
nuevas al `data.json`, no se exponen solas — hay que agregarlas a mano a
una de las dos listas primero.

## Cómo se aplica en el código

Cada ruta se protege con el decorador `@requires_modulo("<nombre>")`, que
exige sesión iniciada **y** que el rol esté autorizado para ese módulo:

```python
@bp.route("/api/sae/buscar")
@requires_modulo("sae")
def buscar():
    ...
```

Sin sesión responde `401`; con sesión pero sin permiso, `403`. Los
archivos estáticos de algunos módulos (css/js/logos) se sirven sin
decorador a propósito, porque no llevan datos sensibles — el dato
sensible siempre está detrás de un endpoint `/api/...` protegido.

La API de integración externa (`/api/integracion/inmuebles`) es la
excepción: no la usa una persona logueada sino otro sistema, así que se
autentica con el header `X-API-Key` (decorador `@requires_api_key`), nunca
con la sesión.

## Dónde vive esto de verdad

No hay una tabla de usuarios propia: los usuarios, contraseñas y roles
viven en Supabase Auth (`user_metadata.role` y `user_metadata.nombre` de
cada usuario). El panel de Permisos (`/admin/`, solo visible para el rol
`admin`) lee y escribe directamente ahí a través de la API de
administración de Supabase — crear un usuario, cambiarle el rol,
deshabilitarlo o resetear su contraseña desde el panel se refleja de
inmediato en Supabase, porque es la misma base.
