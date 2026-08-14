# Sistema de Gestión Comercial — Activos por Colombia

Portal unificado que reemplaza dos apps independientes (SAE y FRV) por un
solo backend Flask, con un solo login y una sola sesión, presentado como
pestañas en la parte superior. **Vista_Inmuebles (brokers) NO se integra
aquí**: sigue siendo una aplicación aparte, porque pertenece a otro
proceso/área de la empresa. Lo único que hace este portal es mostrar un
botón hacia esa aplicación, y solo a los roles autorizados.

## Qué cambia respecto a los 3 repos originales

| Antes | Ahora |
|---|---|
| `Backend_SAE` + `Vista_inmuebles_SAE` (su propio login) | Pestaña **Inventario SAE** dentro del portal |
| `consulta_frv` (su propio login) | Pestaña **Bienes FRV** dentro del portal |
| `Vista_Inmuebles` + `Vista_Inmuebles_backend` | Sigue siendo su propia app; el portal solo muestra un botón hacia ella si el rol tiene permiso (pestaña **Inmuebles (Brokers)**) |

Los tres seguían usando el mismo proyecto de Supabase y las mismas cuentas
(`comercial2026`, `juridica2026`, `broker2026`, `SAE`), así que unificarlos
en un solo login no cambia nada de la base de datos ni de los usuarios: solo
evita que la gente tenga que loguearse varias veces.

## Quién ve qué (tabla de permisos)

Se controla en `app.py`, diccionario `MODULOS`. Ajusta esta tabla si cambian
las reglas de negocio, es el único lugar que hay que tocar:

```python
MODULOS = {
    "sae": {"comercial", "admin"},
    "frv": {"comercial", "juridico", "admin"},
    "vista_inmuebles": {"comercial", "broker", "admin"},
}
```

Con esto:
- `comercial2026` ve las tres pestañas (SAE, FRV con campos de avalúo
  ocultos, y el botón de Vista Inmuebles).
- `juridica2026` ve solo FRV (con campos de avalúo completos).
- `broker2026` ve solo el botón hacia Vista Inmuebles (no entra a SAE ni a
  FRV, que no son de su área).
- Un futuro usuario con rol `admin` vería todo.

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
   - `VISTA_INMUEBLES_URL` — la URL pública donde está desplegada la app
     de brokers (ej. `https://vista-inmuebles.onrender.com`). Si la dejas
     vacía, el botón "Inmuebles (Brokers)" simplemente no aparece.
4. En Supabase (SQL Editor), antes de usarlo:
   - Si es la primera vez que montas esto, confirma que ya corriste
     `sql/ya_ejecutados_originales/08_endurecer_sae.sql` (crea la función
     `buscar_folios`) y `09_ajuste_logs_backend.sql` en el proyecto de
     Supabase — si ya los corriste con los repos viejos, no hay que
     repetirlos.
   - Ejecuta `sql/00_logs_unificado.sql` (crea la tabla nueva de logs
     `logs_acceso_sistema` donde ahora se registra todo, con una columna
     `modulo` para saber si el evento vino de SAE, de FRV o de
     Vista_Inmuebles/brokers).
5. Redespliega también `Vista_Inmuebles_backend` con el `app.py` actualizado
   que viene en `vista_inmuebles_backend_patch/` (junto a este portal): ese
   único cambio hace que sus logs también caigan en `logs_acceso_sistema`
   (con `modulo='vista_inmuebles'`), en vez de en `logs_acceso_vi`. Esa app
   sigue siendo un despliegue totalmente aparte — solo cambia dónde guarda
   su rastro, para tener toda la trazabilidad de la empresa en un solo
   lugar.

## Sobre las tablas de inventario (no hace falta tocarlas)

`inventario_SAE` e `inventario_Activos` **no son tablas duplicadas que haya
que fusionar**. Ya revisé las funciones RPC que tienes en Supabase:
`buscar_folios` (usada por SAE) y `buscar_inmueble_activos` (usada por
Vista_Inmuebles) leen los datos completos del inmueble directamente de
`inventario_SAE` — esa es la única fuente de verdad, por eso es la que
tiene "la gran cantidad de inmuebles". `inventario_Activos` es una tabla
chica de referencia que solo se usa para el indicador de "viabilidad" (si
el FMI existe ahí o no). No hay nada que migrar ahí.

## Probar en local

```bash
pip install -r requirements.txt
export SECRET_KEY=dev
export SUPABASE_URL=https://tu-proyecto.supabase.co
export SUPABASE_ANON_KEY=...
export SUPABASE_SERVICE_ROLE_KEY=...
export VISTA_INMUEBLES_URL=https://vista-inmuebles.onrender.com
python app.py
```

Abre http://localhost:5000 — vas a ver la pantalla de login, y luego el
portal con las pestañas según el rol con el que entres.

## Estructura del proyecto

```
sistema_comercial/
├── app.py                    → backend único: login, sesión, permisos por
│                                módulo, y las rutas de SAE y FRV
├── portal/                   → shell con las pestañas y la pantalla de login
│   ├── index.html
│   └── src/css/portal.css
├── sae/                      → módulo de inventario SAE (se sirve en /sae/)
├── frv/                      → módulo de bienes FRV (se sirve en /frv/)
│   └── data.json             → reemplázalo cuando tengas datos más
│                                recientes del scraper de FRV
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
  una vez, quedas autenticado tanto para SAE como para FRV.
- Las pestañas SAE y FRV se muestran dentro de un `<iframe>` que apunta a
  `/sae/` y `/frv/` respectivamente — son básicamente los visores
  originales, solo que ahora comparten sesión con el portal en vez de tener
  su propio login. Por eso casi no hubo que tocar su HTML/CSS/JS.
- "Inmuebles (Brokers)" no es un iframe: es un botón que abre la app externa
  en una pestaña nueva del navegador, porque esa app vive en otro dominio y
  tiene su propia base de seguridad (su propio login). El portal solo decide
  si mostrar o no el botón, según el rol — la app de brokers sigue
  protegiéndose a sí misma independientemente de esto.
- Todos los eventos (login, logout, búsquedas) se registran en una sola
  tabla `logs_acceso_sistema`, con una columna `modulo` para filtrar por
  origen.

## Cosas que puedes querer ajustar después

- Si agregas un cuarto módulo, solo hace falta: (1) una entrada nueva en
  `MODULOS`, (2) una ruta protegida con `@requires_modulo("nombre")` en
  `app.py`, (3) una entrada en `TAB_LABELS`/`TAB_DESCRIPCIONES` en
  `portal/index.html`.
- Si más adelante quieres que Vista_Inmuebles (brokers) también comparta la
  sesión del portal (sin pedir un segundo login), habría que juntarla en
  este mismo backend como un módulo más — técnicamente posible, pero se
  decidió dejarla aparte porque es de otro proceso/área y así ambos equipos
  pueden desplegar sus cambios sin pisarse.
