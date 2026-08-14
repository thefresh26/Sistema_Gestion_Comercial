-- ============================================================
-- ENDURECIMIENTO DE SEGURIDAD — Vista_Inmuebles (broker/comercial)
-- Ejecutar completo en Supabase → SQL Editor
-- ============================================================

-- 1) FUNCIÓN RPC: junta inventario_SAE + existencia en inventario_Activos
--    (antes esto se hacía con 2 fetch directos desde el navegador). El
--    cliente ya no ve nombres de tablas/columnas ni arma ningún filtro.
create or replace function public.buscar_inmueble_activos(p_fmi text)
returns jsonb
language sql
security definer
set search_path = public
as $$
  select to_jsonb(i) || jsonb_build_object(
    'viabilidad_existe',
    exists(
      select 1 from "inventario_Activos" a
      where upper(a.fmi) = upper(p_fmi)
    )
  )
  from "inventario_SAE" i
  where upper(i.fmi) = upper(p_fmi)
  limit 1;
$$;

revoke all on function public.buscar_inmueble_activos(text) from public;
grant execute on function public.buscar_inmueble_activos(text) to authenticated;


-- 2) TABLA DE TRAZABILIDAD propia de este visor (separada de la de SAE,
--    para no mezclar accesos de proyectos distintos).
create table if not exists public.logs_acceso_vi (
  id bigint generated always as identity primary key,
  usuario_email text,
  accion text not null,          -- 'login' | 'busqueda' | 'logout' | 'logout_inactividad'
  detalle text,                  -- ej. el FMI consultado
  ip_address text,
  creado_en timestamptz not null default now()
);

alter table public.logs_acceso_vi enable row level security;
-- No se crea policy de SELECT ni de INSERT para anon/authenticated:
-- el backend escribe usando la service_role key, que bypassa RLS.
-- Nadie puede leer ni insertar en esta tabla desde el navegador.


-- 3) Verificación rápida (opcional):
-- select * from public.buscar_inmueble_activos('50C-1874919');
