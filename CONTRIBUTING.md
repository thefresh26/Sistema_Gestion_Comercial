# Guía para contribuir

Reglas propias de este proyecto que hay que respetar al editarlo.

## Push

La rama local es `main`, pero el remoto usa `master`. El push siempre es:

```
git push origin HEAD:master
```

Nunca hagas `git push origin main` ni configures `main` como upstream por defecto.

## Entorno virtual

`venv/` nunca se sube a git — ya está en `.gitignore`. No lo agregues a mano
ni lo excluyas del ignore.

## Variables de entorno

Copia `.env.example` a `.env` y llena los valores reales. El `.env` real
nunca se sube a git (también está en `.gitignore`).

## Módulos nuevos

Cada módulo nuevo dentro de `modulos/` sigue este patrón:

```
modulos/<nombre_modulo>/
├── index.html
├── src/
│   ├── css/
│   └── js/
└── public/logos/   (opcional, si el módulo necesita imágenes propias)
```

## Archivos con contraseñas reales

Estos archivos nunca se leen ni se suben, bajo ninguna circunstancia:

- `scripts/tarea_programada_windows/tarea_programada_local.ps1`
- cualquier archivo `.env`

Si necesitas documentar cómo se usa ese script, crea una versión de
ejemplo sin contraseña (p. ej. `tarea_programada_local.ps1.ejemplo`) en
vez de subir el archivo real.

## Roles y permisos

Los roles y permisos de cada módulo se cambian **solo** en el diccionario
`MODULOS` de `app.py`. Está documentado en `docs/permisos.md` — revisa ese
archivo antes de tocar `MODULOS`.
