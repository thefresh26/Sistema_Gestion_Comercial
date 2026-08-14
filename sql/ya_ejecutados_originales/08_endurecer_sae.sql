-- ============================================================
-- ENDURECIMIENTO DE SEGURIDAD — Vista_inmuebles_SAE
-- Ejecutar completo en Supabase → SQL Editor
-- (Desactiva la traducción automática de Chrome antes de pegar)
-- ============================================================

-- 1) FUNCIÓN RPC: reemplaza el SELECT visible desde el navegador.
--    El cliente ya no arma la consulta ni conoce los nombres reales
--    de las tablas/columnas internas; solo llama a esta función y
--    recibe exactamente los campos que necesita mostrar.
create or replace function public.buscar_folios(p_folios text[])
returns table (
  fmi text,
  codigo_subasta text,
  enlace_inmueble text,
  interesados int
)
language sql
security definer
set search_path = public
as $$
  select
    i.fmi,
    i.codigo_subasta,
    i.enlace_inmueble,
    coalesce(count(e.fmi) filter (where e.analista is not null and e.analista <> ''), 0)::int as interesados
  from "inventario_SAE" i
  left join expresiones_interes e on upper(e.fmi) = upper(i.fmi)
  where upper(i.fmi) = any (select upper(x) from unnest(p_folios) as x)
  group by i.fmi, i.codigo_subasta, i.enlace_inmueble;
$$;

-- Solo usuarios logueados pueden ejecutar la función (no "anon" público).
revoke all on function public.buscar_folios(text[]) from public;
grant execute on function public.buscar_folios(text[]) to authenticated;


-- 2) TABLA DE TRAZABILIDAD: registra quién consultó qué y cuándo.
create table if not exists public.logs_acceso (
  id bigint generated always as identity primary key,
  usuario_id uuid not null default auth.uid(),
  usuario_email text,
  accion text not null,          -- 'login' | 'busqueda' | 'logout' | 'logout_inactividad'
  detalle text,                  -- ej. folios consultados
  creado_en timestamptz not null default now()
);

alter table public.logs_acceso enable row level security;

-- Cualquier usuario autenticado puede INSERTAR su propio log...
create policy "insertar_propio_log" on public.logs_acceso
for insert to authenticated
with check (auth.uid() = usuario_id);

-- ...pero NADIE puede leer los logs desde el cliente (ni siquiera el
-- propio usuario). Solo se consultan desde el panel de Supabase con
-- la service_role key, o desde el SQL Editor.
-- (No se crea policy de SELECT => select queda bloqueado por defecto)


-- 3) Verificación rápida (opcional, puedes correr esto para probar):
-- select * from public.buscar_folios(array['50C-1874919']);
