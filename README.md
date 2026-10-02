# Sistema de Gestión Comercial — Activos por Colombia

Portal unificado que reemplaza varias apps independientes (SAE, FRV y
Vista_Inmuebles) por un solo backend Flask, con un solo login y una sola
sesión, presentado como pestañas en la parte superior.

## Estructura del proyecto

Dos carpetas mandan: **`backend/`** es todo el código Python del servidor,
y **`frontend/`** es todo lo que ve el navegador (un subproyecto por
pestaña). Nada de código vive suelto en la raíz: `app.py` solo crea la
aplicación.

```
sistema_gestion_comercial/
│
├── app.py                → punto de entrada (3 líneas): crea la app
│
├── backend/              → TODO el código Python del servidor
│   ├── __init__.py         create_app(): arma Flask y registra los módulos
│   ├── config.py           variables de entorno y rutas de carpetas
│   ├── permisos.py         MODULOS (quién ve qué) + decoradores de rutas
│   ├── supabase.py         cabeceras y llamadas HTTP a Supabase
│   ├── registro.py         el log unificado de eventos
│   │
│   ├── rutas/            → un archivo por módulo del portal
│   │   ├── portal.py       shell con las pestañas + login/logout/sesión
│   │   ├── sae.py          Expresiones SAE
│   │   ├── frv.py          Inmuebles FRV (+ lista blanca de campos)
│   │   ├── vista_inmuebles.py
│   │   ├── dashboard.py    Estadísticas
│   │   ├── admin.py        panel de Permisos
│   │   ├── documentos.py   generador de Actas/Certificados
│   │   ├── integracion.py  API para sistemas externos (X-API-Key)
│   │   └── _inmuebles.py   búsqueda por FMI que comparten
│   │                         vista_inmuebles e integracion
│   │
│   └── generador/        → el motor que arma los .docx
│       ├── db.py           bases de datos del módulo Documentos
│       ├── clarity.py      métricas de tráfico (Informe de Subasta)
│       ├── tipos/          un archivo por tipo de documento generable
│       └── plantillas_word/  los .docx en blanco + sus marcadores
│
├── frontend/             → un subproyecto por pestaña del portal; cada uno
│   │                       se sirve en /<nombre>/ vía send_from_directory
│   ├── portal/             shell con las pestañas y el login
│   │   ├── index.html
│   │   ├── src/css/portal.css, src/js/app.js
│   │   └── public/logos/
│   ├── sae/                Expresiones SAE (folio → unidad/expresión)
│   ├── frv/                Inmuebles FRV (bienes del Fondo)
│   │   └── data.json         (reemplázalo cuando tengas datos más
│   │                          recientes del scraper de FRV)
│   ├── vista_inmuebles/    inventario con semáforo de viabilidad
│   ├── dashboard/          Estadísticas (folios/unidades vendidas)
│   ├── admin/              panel de Permisos
│   └── documentos/         este módulo se pinta en el servidor (Jinja),
│       ├── style.css         no es una SPA como los demás
│       └── plantillas/       base.html, index.html, caso.html
│
├── data/
│   └── directorio_m365.json  → nombres reales por correo, para
│                               autocompletar "Nombre completo" al crear
│                               o editar usuarios en el panel de Permisos
├── docs/
│   └── permisos.md       → detalle de roles y quién ve qué
├── scripts/
│   └── actualizar_dashboard.py  → recalcula Estadísticas (lo corre la
│                                   GitHub Action todos los días; su ruta
│                                   está fija en el workflow, no mover)
├── sql/
│   ├── schema_documentos.sql       → tablas del módulo Documentos (Neon)
│   ├── 00_logs_unificado.sql … 05_dashboard_folios_unidades.sql
│   └── ya_ejecutados_originales/   → scripts ya corridos en producción,
│                                      aquí solo de referencia histórica
│
├── Dockerfile, render.yaml, requirements.txt, runtime.txt  → despliegue
└── .github/workflows/actualizar_dashboard.yml
```

### Por dónde empezar a leer

1. `backend/__init__.py` — qué módulos existen y cómo se arman.
2. `backend/permisos.py` — quién puede ver cada uno.
3. `backend/rutas/<el módulo que te interese>.py` — sus rutas, nada más.

## Módulos y permisos

El portal tiene seis módulos: **Expresiones SAE**, **Inmuebles FRV**,
**Vista Inmuebles**, **Estadísticas**, **Documentos** y **Permisos**, más
el propio **Portal** (login y las pestañas). Quién ve cada uno depende del
rol del usuario — ver el detalle completo, con la tabla de roles y el
diccionario `MODULOS` de [`backend/permisos.py`](backend/permisos.py), en
[`docs/permisos.md`](docs/permisos.md).

Los usuarios se administran desde el panel **Permisos** (`/admin/`, solo
para el rol `admin`): crear usuarios, cambiar su rol, deshabilitarlos o
resetear su contraseña, todo contra Supabase Auth directamente — no hay
tabla de usuarios propia.

## Cómo desplegarlo (Render)

1. Sube esta carpeta a un repo de GitHub.
2. En Render: New → Web Service → conecta el repo. El despliegue usa
   Docker (`render.yaml` → `Dockerfile`), porque el módulo Documentos
   necesita Chrome headless para leer fechas del cronograma de subastas.
3. En Settings → Environment, agrega las variables de
   [`.env.example`](.env.example) (`SECRET_KEY`, `SUPABASE_URL`,
   `SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_ROLE_KEY`, `DATABASE_URL`,
   `AZURE_DATABASE_URL`, `INTEGRACION_API_KEY`). Nunca las subas al repo.
4. En Supabase (SQL Editor), antes de usarlo, ejecuta en orden los
   archivos de `sql/` (los de `sql/ya_ejecutados_originales/` ya están
   corridos en producción, quedan solo de referencia histórica).
5. La tarea programada que actualiza **Estadísticas** no corre en Render
   (los Cron Jobs piden tarjeta de crédito en el plan gratis) — corre
   gratis como GitHub Action, ver `.github/workflows/actualizar_dashboard.yml`.

## Probar en local

```bash
pip install -r requirements.txt
cp .env.example .env     # y llena los valores reales
python app.py
```

Abre http://localhost:5000 — vas a ver la pantalla de login, y luego el
portal con las pestañas según el rol con el que entres.

> Nota: la cookie de sesión se marca como `Secure` (solo viaja por HTTPS).
> En producción (Render) no cambia nada, porque Render ya sirve todo por
> HTTPS. Pero si pruebas en tu máquina con `http://localhost` (sin HTTPS),
> el login puede no "pegar" la sesión. Si necesitas probar en local,
> comenta temporalmente la línea `SESSION_COOKIE_SECURE=True` en
> `backend/__init__.py`.

## Cómo funciona por dentro (para cuando alguien más lo mantenga)

- El login (`/api/login`) valida contra Supabase Auth — nunca se guardan
  contraseñas en este backend. El rol y el nombre completo de cada usuario
  viven en `user_metadata` de Supabase Auth.
- La sesión (cookie de Flask) es una sola para todo el portal: al loguearte
  una vez, quedas autenticado en todos los módulos que tu rol permite ver.
- Cada pestaña se muestra dentro de un `<iframe>` que apunta a su propia
  URL (`/sae/`, `/frv/`, `/vista_inmuebles/`, `/dashboard/`, `/admin/`,
  `/documentos/`) — son subproyectos casi independientes que comparten
  sesión con el portal en vez de tener su propio login.
- Todos los eventos (login, logout, búsquedas) se registran en una sola
  tabla `logs_acceso_sistema`, con una columna `modulo` para filtrar por
  origen.

## Sobre las tablas de inventario (no hace falta tocarlas)

`inventario_SAE` e `inventario_Activos` **no son tablas duplicadas que haya
que fusionar**. Las funciones RPC de Supabase (`buscar_folios` y
`buscar_inmueble_activos`) leen los datos completos del inmueble
directamente de `inventario_SAE` — esa es la única fuente de verdad, por
eso es la que tiene la mayor cantidad de inmuebles. `inventario_Activos` es
una tabla chica de referencia que solo se usa para el indicador de
"viabilidad" (si el FMI existe ahí o no). No hay nada que migrar ahí.

## Cosas que puedes querer ajustar después

- **Módulo nuevo**: (1) carpeta nueva en `frontend/`, (2) archivo nuevo en
  `backend/rutas/` con su `Blueprint`, agregado a `TODOS` en
  `backend/rutas/__init__.py`, (3) una entrada en `MODULOS`
  (`backend/permisos.py`), (4) una entrada en
  `TAB_LABELS`/`TAB_DESCRIPCIONES` en `frontend/portal/index.html`.
- **Rol nuevo**: todo se cambia en `backend/permisos.py` (`MODULOS`,
  `ROLES_VISIBLES` y, si aplica, `ROLES_SIN_AVALUO_FRV`), y se refleja en
  [`docs/permisos.md`](docs/permisos.md).
- **Tipo de documento nuevo**: ver las instrucciones al inicio de
  `backend/generador/tipos/__init__.py`.
