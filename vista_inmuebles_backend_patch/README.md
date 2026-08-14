# Vista_Inmuebles — backend

Versión con backend intermedio (Flask), mismo patrón que Backend_SAE.
El navegador ya no habla directo con Supabase.

## Desplegar en Render (plan gratis)

1. Sube esta carpeta a un repo nuevo en GitHub.
2. Render → New → Web Service → conecta el repo.
   - Build command: `pip install -r requirements.txt`
   - Start command: `gunicorn app:app`
3. Variables de entorno (Settings → Environment):
   - `SECRET_KEY`
   - `SUPABASE_URL`
   - `SUPABASE_ANON_KEY`
   - `SUPABASE_SERVICE_ROLE_KEY`
4. Antes de usarlo, corre `01_endurecer_vista_inmuebles.sql` en Supabase (SQL Editor).

## Usuarios

- `comercial2026` (contraseña de siempre) — rol comercial.
- Correos institucionales con rol `comercial` o `juridico` asignado por SQL
  (ver `raw_user_meta_data`), entran directamente con su correo completo.
- `broker2026` fue retirado del login (la cuenta sigue en Supabase, pero
  ya no puede iniciar sesión desde este visor).
