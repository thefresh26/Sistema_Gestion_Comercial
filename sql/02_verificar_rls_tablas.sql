-- ============================================================
-- VERIFICAR Y FORZAR RLS en las tablas de datos
-- Ejecutar completo en Supabase → SQL Editor
-- ============================================================
--
-- Por qué: aunque el backend ya no expone la anon key ni la service_role
-- key al navegador (los tres visores hablan solo con nuestro Flask, y
-- Flask habla con Supabase por detrás), es buena práctica de seguridad
-- en profundidad que las tablas con datos reales tengan Row Level
-- Security (RLS) activado y SIN políticas públicas. Así, aunque alguien
-- consiguiera la anon key de algún modo (por ejemplo, mirando código
-- viejo, un backup, u otro sistema que la use), no podría hacer un
-- GET/POST directo a la API de Supabase y descargarse la tabla completa.
--
-- 1) Esto te muestra qué tablas tienen RLS activado o no:
select schemaname, tablename, rowsecurity
from pg_tables
where schemaname = 'public'
  and tablename in (
    'inventario_SAE',
    'inventario_Activos',
    'expresiones_interes',
    'logs_acceso',
    'logs_acceso_frv',
    'logs_acceso_vi',
    'logs_acceso_sistema'
  );

-- Si en la columna "rowsecurity" alguna de estas sale en "false",
-- ejecuta la línea correspondiente de abajo para activarlo (no rompe
-- nada: las funciones RPC usan "security definer" y siguen funcionando
-- igual; lo único que cambia es que ya no se puede leer/escribir esa
-- tabla directamente desde afuera sin pasar por las funciones RPC).

alter table if exists public."inventario_SAE" enable row level security;
alter table if exists public."inventario_Activos" enable row level security;
alter table if exists public.expresiones_interes enable row level security;

-- No creamos ninguna policy de SELECT/INSERT/UPDATE a propósito: eso
-- deja la tabla completamente cerrada desde el cliente (anon o
-- authenticated), y el único acceso posible queda siendo:
--   a) las funciones RPC (buscar_folios, buscar_inmueble_activos), que
--      corren con "security definer" y sí pueden leer la tabla, o
--   b) el backend Flask con la service_role key, que siempre "bypassa"
--      RLS (por eso los logs y los inserts internos siguen funcionando
--      sin problema).
