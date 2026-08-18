# Sistema de Gestión Comercial — Activos por Colombia

Portal unificado que reemplaza tres apps independientes (SAE, FRV y
Vista_Inmuebles) por un solo backend Flask, con un solo login y una sola
sesión, presentado como pestañas en la parte superior.

## Qué cambia respecto a los repos originales

| Antes | Ahora |
|---|---|
| `Backend_SAE` + `Vista_inmuebles_SAE` (su propio login) | Pestaña **Inventario SAE** dentro del portal |
| `consulta_frv` (su propio login) | Pestaña **Bienes FRV** dentro del portal |
| `Vista_Inmuebles` + `Vista_Inmuebles_backend` (su propio login, su propio despliegue) | Pestaña **Inmuebles (Brokers)** dentro del portal — fusionada, ya no es una app aparte |

Los tres seguían usando el mismo proyecto de Supabase y las mismas cuentas
(`comercial2026`, `juridica2026`, `SAE`), así que unificarlos en un solo
login no cambia nada de la base de datos ni de los usuarios: solo evita que
la gente tenga que loguearse varias veces.

Una vez este portal esté funcionando bien en producción, los repos
`Vista_Inmuebles` y `Vista_Inmuebles_backend` (y su servicio en Render)
quedan redundantes — puedes apagarlos cuando quieras, no antes.

## Quién ve qué (tabla de permisos)

Se controla en `app.py`, diccionario `MODULOS`. Ajusta esta tabla si cambian
las reglas de negocio, es el único lugar que hay que tocar:

```python
MODULOS = {
    "sae": {"comercial", "admin"},
    "frv": {"comercial", "juridico", "admin"},
    "vista_inmuebles": {"comercial", "admin"},
}
```

Con esto:
- `comercial2026` ve las tres pestañas (SAE, FRV con campos de avalúo
  ocultos, y Vista Inmuebles con el semáforo de viabilidad).
- `juridica2026` ve solo FRV (con campos de avalúo completos).
- Un futuro usuario con rol `admin` vería todo.

Ya no existe el rol `broker`: Vista_Inmuebles dejó de tener usuarios
externos propios y ahora es una pestaña más, solo para el equipo comercial.

## Cómo desplegarlo (Render, plan gratis)

1. Sube esta carpeta a un repo de GitHub.
2. En Render: New → Web Service → conecta el repo.
   - Build command: `pip install -r requirements.txt`
   - Start command: `gunicorn app:app`
3. En Settings → Environment, agrega:
   - `SECRET_KEY` (una cadena larga aleatoria)
   - `SUPABASE_URL` (la misma que ya usan SAE/FRV/Vista_Inmuebles)
   - `SUPABASE_ANON_KEY`
   - `SUPABASE_SERVICE_ROLE_KEY` (nunca la subas al repo)
4. En Supabase (SQL Editor), antes de usarlo:
   - Confirma que ya corriste `sql/ya_ejecutados_originales/08_endurecer_sae.sql`
     (crea la función `buscar_folios`), `09_ajuste_logs_backend.sql`, y
     `01_endurecer_vista_inmuebles.sql` del repo `Vista_Inmuebles_backend`
     (crea la función `buscar_inmueble_activos`) — si ya los corriste con
     los repos viejos, no hay que repetirlos.
   - Ejecuta `sql/00_logs_unificado.sql` (crea la tabla `logs_acceso_sistema`
     donde ahora se registra todo, con una columna `modulo` para saber si el
     evento vino de SAE, FRV o Vista_Inmuebles).

## Sobre las tablas de inventario (no hace falta tocarlas)

`inventario_SAE` e `inventario_Activos` **no son tablas duplicadas que haya
que fusionar**. Las funciones RPC que ya tienes en Supabase (`buscar_folios`
y `buscar_inmueble_activos`) leen los datos completos del inmueble
directamente de `inventario_SAE` — esa es la única fuente de verdad, por eso
es la que tiene "la gran cantidad de inmuebles". `inventario_Activos` es una
tabla chica de referencia que solo se usa para el indicador de "viabilidad"
(si el FMI existe ahí o no). No hay nada que migrar ahí.

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

## Estructura del proyecto

```
sistema_comercial/
├── app.py                    → backend único: login, sesión, permisos por
│                                módulo, y las rutas de SAE, FRV y
│                                Vista_Inmuebles
├── portal/                   → shell con las pestañas y la pantalla de login
│   ├── index.html
│   └── src/css/portal.css
├── sae/                      → módulo de inventario SAE (se sirve en /sae/)
├── frv/                      → módulo de bienes FRV (se sirve en /frv/)
│   └── data.json             → reemplázalo cuando tengas datos más
│                                recientes del scraper de FRV
├── vista_inmuebles/          → módulo de inventario con semáforo de
│                                viabilidad (se sirve en /vista_inmuebles/)
├── sql/
│   ├── 00_logs_unificado.sql
│   └── ya_ejecutados_originales/   → scripts que ya corriste en los repos
│                                      viejos, aquí solo de referencia
├── requirements.txt
└── render.yaml
```

## Cómo funciona por dentro (para cuando alguien más lo mantenga)

- El login (`/api/login`) sigue validando contra Supabase Auth, igual que
  antes en los 3 proyectos — nunca se guardan contraseñas en este backend.
- La sesión (cookie de Flask) es una sola para todo el portal: al loguearte
  una vez, quedas autenticado en SAE, FRV y Vista_Inmuebles.
- Las tres pestañas se muestran dentro de un `<iframe>` que apunta a
  `/sae/`, `/frv/` y `/vista_inmuebles/` respectivamente — son básicamente
  los visores originales, solo que ahora comparten sesión con el portal en
  vez de tener su propio login. Por eso casi no hubo que tocar su
  HTML/CSS/JS de cada uno.
- Todos los eventos (login, logout, búsquedas) se registran en una sola
  tabla `logs_acceso_sistema`, con una columna `modulo` para filtrar por
  origen ('portal', 'sae', 'frv' o 'vista_inmuebles').

## Cosas que puedes querer ajustar después

- Si agregas un cuarto módulo, solo hace falta: (1) una entrada nueva en
  `MODULOS`, (2) una ruta protegida con `@requires_modulo("nombre")` en
  `app.py`, (3) una entrada en `TAB_LABELS`/`TAB_DESCRIPCIONES` en
  `portal/index.html`.
- Un panel de administración para gestionar permisos (qué rol ve qué
  módulo) desde la interfaz, en vez de editar `MODULOS` directamente en el
  código, es una mejora natural a futuro.
