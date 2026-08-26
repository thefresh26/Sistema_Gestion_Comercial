# Sistema de Gestión Comercial — Activos por Colombia

Portal unificado que reemplaza varias apps independientes (SAE, FRV y
Vista_Inmuebles) por un solo backend Flask, con un solo login y una sola
sesión, presentado como pestañas en la parte superior.

## Módulos y permisos

El portal tiene seis módulos: **Expresiones SAE**, **Inmuebles FRV**,
**Vista Inmuebles**, **Estadísticas** y **Permisos**, más el propio
**Portal** (login y las pestañas). Quién ve cada uno depende del rol del
usuario — ver el detalle completo, con la tabla de roles y el diccionario
`MODULOS` de `app.py`, en [`docs/permisos.md`](docs/permisos.md).

Los usuarios se administran desde el panel **Permisos** (`/admin/`, solo
para el rol `admin`): crear usuarios, cambiar su rol, deshabilitarlos o
resetear su contraseña, todo contra Supabase Auth directamente — no hay
tabla de usuarios propia.

## Cómo desplegarlo (Render, plan gratis)

1. Sube esta carpeta a un repo de GitHub.
2. En Render: New → Web Service → conecta el repo.
   - Build command: `pip install -r requirements.txt`
   - Start command: `gunicorn app:app`
3. En Settings → Environment, agrega:
   - `SECRET_KEY` (una cadena larga aleatoria)
   - `SUPABASE_URL`
   - `SUPABASE_ANON_KEY`
   - `SUPABASE_SERVICE_ROLE_KEY` (nunca la subas al repo)
4. En Supabase (SQL Editor), antes de usarlo, ejecuta en orden los
   archivos de `sql/` (los de `sql/ya_ejecutados_originales/` ya están
   corridos en producción, quedan solo de referencia histórica).
5. La tarea programada que actualiza **Estadísticas** no corre en Render
   (los Cron Jobs piden tarjeta de crédito en el plan gratis) — corre
   gratis como GitHub Action, ver `.github/workflows/actualizar_dashboard.yml`.

## Sobre las tablas de inventario (no hace falta tocarlas)

`inventario_SAE` e `inventario_Activos` **no son tablas duplicadas que haya
que fusionar**. Las funciones RPC de Supabase (`buscar_folios` y
`buscar_inmueble_activos`) leen los datos completos del inmueble
directamente de `inventario_SAE` — esa es la única fuente de verdad, por
eso es la que tiene la mayor cantidad de inmuebles. `inventario_Activos` es
una tabla chica de referencia que solo se usa para el indicador de
"viabilidad" (si el FMI existe ahí o no). No hay nada que migrar ahí.

## Probar en local

```bash
pip install -r requirements.txt
export SECRET_KEY=dev
export SUPABASE_URL=https://tu-proyecto.supabase.co
export SUPABASE_ANON_KEY=...
export SUPABASE_SERVICE_ROLE_KEY=...
python app.py
```

Abre http://localhost:5000 — vas a ver la pantalla de login, y luego el
portal con las pestañas según el rol con el que entres.

> Nota: la cookie de sesión se marca como `Secure` (solo viaja por HTTPS).
> En producción (Render) no cambia nada, porque Render ya sirve todo por
> HTTPS. Pero si pruebas en tu máquina con `http://localhost` (sin HTTPS),
> el login puede no "pegar" la sesión. Si necesitas probar en local,
> comenta temporalmente la línea `SESSION_COOKIE_SECURE=True` en `app.py`.

## Estructura del proyecto

```
sistema_comercial/
├── app.py                    → backend único: login, sesión, permisos por
│                                módulo y las rutas de cada módulo
├── requirements.txt
├── render.yaml
├── modulos/                  → un subproyecto por pestaña del portal;
│   │                            cada uno se sirve en /<nombre>/ vía
│   │                            send_from_directory, sin depender de esta
│   │                            carpeta contenedora
│   ├── portal/                 → shell con las pestañas y el login
│   │   ├── index.html
│   │   └── src/css/portal.css
│   ├── sae/                    → Expresiones SAE (folio → unidad/expresión)
│   ├── frv/                    → Inmuebles FRV (bienes del Fondo)
│   │   └── data.json             (reemplázalo cuando tengas datos más
│   │                              recientes del scraper de FRV)
│   ├── vista_inmuebles/        → inventario con semáforo de viabilidad
│   ├── dashboard/               → Estadísticas (folios/unidades vendidas)
│   └── admin/                   → panel de Permisos
├── data/
│   └── directorio_m365.json  → nombres reales por correo, para
│                                autocompletar "Nombre completo" al crear
│                                o editar usuarios en el panel de Permisos
├── docs/
│   └── permisos.md           → detalle de roles y quién ve qué
├── scripts/
│   ├── actualizar_dashboard.py    → recalcula Estadísticas (lo corre la
│   │                                 GitHub Action todos los días)
│   └── tarea_programada_local.ps1 → versión con contraseña real, nunca se
│                                     sube a git (ver .gitignore)
├── sql/
│   ├── 00_logs_unificado.sql … 05_dashboard_folios_unidades.sql
│   └── ya_ejecutados_originales/   → scripts ya corridos en producción,
│                                      aquí solo de referencia histórica
└── .github/workflows/actualizar_dashboard.yml
```

## Cómo funciona por dentro (para cuando alguien más lo mantenga)

- El login (`/api/login`) valida contra Supabase Auth — nunca se guardan
  contraseñas en este backend. El rol y el nombre completo de cada usuario
  viven en `user_metadata` de Supabase Auth.
- La sesión (cookie de Flask) es una sola para todo el portal: al loguearte
  una vez, quedas autenticado en todos los módulos que tu rol permite ver.
- Cada pestaña se muestra dentro de un `<iframe>` que apunta a su propia
  URL (`/sae/`, `/frv/`, `/vista_inmuebles/`, `/dashboard/`, `/admin/`) —
  son subproyectos casi independientes que comparten sesión con el portal
  en vez de tener su propio login.
- Todos los eventos (login, logout, búsquedas) se registran en una sola
  tabla `logs_acceso_sistema`, con una columna `modulo` para filtrar por
  origen.

## Cosas que puedes querer ajustar después

- Si agregas un módulo nuevo, solo hace falta: (1) una carpeta nueva en
  `modulos/`, (2) una entrada en `MODULOS` (`app.py`), (3) un par de rutas
  protegidas con `@requires_modulo("nombre")`, (4) una entrada en
  `TAB_LABELS`/`TAB_DESCRIPCIONES` en `modulos/portal/index.html`.
- Si agregas un rol nuevo, actualiza `MODULOS`, `ROLES_VISIBLES` y, si
  aplica, `ROLES_SIN_AVALUO_FRV` en `app.py`, y refleja el cambio en
  [`docs/permisos.md`](docs/permisos.md).
