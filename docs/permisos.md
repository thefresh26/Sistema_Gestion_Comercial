# Permisos por rol

Este documento explica quién ve qué dentro del portal. Se controla en
`app.py`, en el diccionario `MODULOS` (qué roles pueden entrar a cada
módulo) y en el conjunto `ROLES_SIN_AVALUO_FRV` (qué roles ven los campos
de avalúo comercial dentro de FRV). Si cambian las reglas de negocio, esos
dos lugares son los únicos que hay que tocar en el código — el panel de
Permisos (`/admin/`) permite crear usuarios y asignarles rol sin tocar
código en absoluto.

## Módulos

```python
MODULOS = {
    "sae": {"comercial", "admin", "sae"},
    "frv": {"comercial", "juridico", "admin", "comunicaciones"},
    "vista_inmuebles": {"comercial", "admin", "comunicaciones"},
    "dashboard": {"comercial", "admin"},
    "admin": {"admin"},
}

ROLES_SIN_AVALUO_FRV = {"comercial", "comunicaciones"}
```

## Qué ve cada rol

| Rol | Expresiones SAE | Inmuebles FRV | Vista Inmuebles | Estadísticas | Permisos |
|---|---|---|---|---|---|
| `comercial` | Sí | Sí (sin avalúos) | Sí | Sí | No |
| `juridico` | No | Sí (con avalúos) | No | No | No |
| `sae` | Sí | No | No | No | No |
| `comunicaciones` | No | Sí (sin avalúos) | Sí | No | No |
| `admin` | Sí | Sí (con avalúos) | Sí | Sí | Sí |
| `sin_acceso` | No | No | No | No | No |

## Nombres de los roles en el panel de Permisos

`ROLES_VISIBLES` en `app.py` define cómo se muestra cada rol en el panel
de administración:

```python
ROLES_VISIBLES = {
    "comercial": "Comercial",
    "juridico": "Jurídico",
    "admin": "Administrador",
    "sae": "SAE",
    "comunicaciones": "Comunicaciones",
    "sin_acceso": "Sin acceso",
}
```

## Dónde vive esto de verdad

No hay una tabla de usuarios propia: los usuarios, contraseñas y roles
viven en Supabase Auth (`user_metadata.role` y `user_metadata.nombre` de
cada usuario). El panel de Permisos (`/admin/`, solo visible para el rol
`admin`) lee y escribe directamente ahí a través de la API de
administración de Supabase — crear un usuario, cambiarle el rol,
deshabilitarlo o resetear su contraseña desde el panel se refleja de
inmediato en Supabase, porque es la misma base.
