# Guía para contribuir

Reglas propias de este proyecto que hay que respetar al editarlo. Para
entender cómo está organizado el código, lee primero la sección
"Estructura del proyecto" del [README](README.md).

## Push

La rama local es `main`, pero el remoto usa `master`. El push siempre es:

```
git push origin HEAD:master
```

Nunca hagas `git push origin main` ni configures `main` como upstream por
defecto.

## Dónde va cada cosa

| Si vas a tocar…                        | Es en…                                  |
|----------------------------------------|-----------------------------------------|
| quién puede ver un módulo, o un rol     | `backend/permisos.py`                   |
| una ruta o endpoint de un módulo        | `backend/rutas/<modulo>.py`             |
| una pantalla (HTML/CSS/JS)              | `frontend/<modulo>/`                    |
| un tipo de documento generable          | `backend/generador/tipos/<tipo>.py`     |
| una plantilla .docx                     | `backend/generador/plantillas_word/`    |
| una variable de entorno                 | `backend/config.py` **y** `.env.example`|

Regla general: **nada de código suelto en la raíz**. `app.py` solo crea la
aplicación; todo lo demás vive en `backend/` o `frontend/`.

## Variables de entorno

Copia `.env.example` a `.env` y llena los valores reales. El `.env` real
nunca se sube a git (está en `.gitignore`). Las variables se leen **solo**
en `backend/config.py` — el resto del código importa de ahí, nunca llama a
`os.environ` por su cuenta.

## Entorno virtual

`venv/` nunca se sube a git — ya está en `.gitignore`. No lo agregues a
mano ni lo excluyas del ignore.

## Módulos nuevos

El frontend de cada módulo sigue este patrón:

```
frontend/<nombre_modulo>/
├── index.html
├── src/
│   ├── css/
│   └── js/
└── public/logos/   (opcional, si el módulo necesita imágenes propias)
```

Y su backend, este:

```
backend/rutas/<nombre_modulo>.py     → un Blueprint con sus rutas
```

Después hay que registrarlo en dos sitios: `TODOS` en
`backend/rutas/__init__.py` y `MODULOS` en `backend/permisos.py`. El
checklist completo está al final del README.

## Roles y permisos

Los roles y permisos de cada módulo se cambian **solo** en
`backend/permisos.py` (`MODULOS`, `ROLES_VISIBLES`,
`ROLES_SIN_AVALUO_FRV`). Está documentado en `docs/permisos.md` — revisa
ese archivo antes de tocarlos, y actualízalo con el cambio.

## Archivos con secretos

Ningún archivo `.env` se lee ni se sube, bajo ninguna circunstancia. Si
necesitas documentar una variable nueva, agrégala a `.env.example` con un
valor de ejemplo, nunca con el real.
