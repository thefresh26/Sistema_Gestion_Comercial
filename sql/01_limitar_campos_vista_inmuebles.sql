-- ============================================================
-- ENDURECER buscar_inmueble_activos: ya no expone la fila completa
-- Ejecutar completo en Supabase → SQL Editor
-- ============================================================
--
-- Por qué: la función original (01_endurecer_vista_inmuebles.sql, del
-- repo Vista_Inmuebles_backend) hacía `to_jsonb(i)`, es decir devolvía
-- TODAS las columnas de "inventario_SAE" tal cual están en la base de
-- datos, aunque el visor de Vista Inmuebles solo muestra un subconjunto
-- de esos campos en pantalla. Eso significa que si alguien abre las
-- herramientas de desarrollador del navegador (pestaña "Network"/
-- "Inspeccionar") y mira la respuesta de /api/vista_inmuebles/buscar,
-- podía ver campos que ni siquiera se muestran en la pantalla.
--
-- Este script reemplaza esa función para que devuelva EXACTAMENTE los
-- mismos campos que ya usa vista_inmuebles/src/js/app.js (ni uno más),
-- siguiendo el mismo patrón que ya se usaba en buscar_folios (SAE):
-- el cliente solo recibe lo que necesita para pintar la pantalla, nunca
-- la fila cruda de la base de datos.

create or replace function public.buscar_inmueble_activos(p_fmi text)
returns jsonb
language sql
security definer
set search_path = public
as $$
  select jsonb_build_object(
    'fmi', i.fmi,
    'clasificacion_activo', i.clasificacion_activo,
    'subtipo_activo', i.subtipo_activo,
    'municipio', i.municipio,
    'departamento', i.departamento,
    'direccion', i.direccion,
    'estrato', i.estrato,
    'razon_social', i.razon_social,
    'disponibilidad', i.disponibilidad,
    'estado_ocupacion', i.estado_ocupacion,
    'estado_fisico', i.estado_fisico,
    'estado_legal', i.estado_legal,
    'bm_enajenacion_20', i.bm_enajenacion_20,
    'avance', i.avance,
    'bk_catastral_10', i.bk_catastral_10,
    'bl_avaluo_40', i.bl_avaluo_40,
    'bn_viabilidad_30', i.bn_viabilidad_30,
    'vigencia_catastral', i.vigencia_catastral,
    'estado_avaluo', i.estado_avaluo,
    'avaluo_catastral', i.avaluo_catastral,
    'avaluo_comercial', i.avaluo_comercial,
    'fecha_avaluo', i.fecha_avaluo,
    'area_construida', i.area_construida,
    'area_terreno', i.area_terreno,
    'causal', i.causal,
    'enajenacion', i.enajenacion,
    'proceso', i.proceso,
    'estado_comercial', i.estado_comercial,
    'estado_publicacion', i.estado_publicacion,
    'georeferenciado', i.georeferenciado,
    'viabilidad_existe', exists(
      select 1 from "inventario_Activos" a
      where upper(a.fmi) = upper(p_fmi)
    )
  )
  from "inventario_SAE" i
  where upper(i.fmi) = upper(p_fmi)
  limit 1;
$$;

-- Se mantienen los mismos permisos: solo usuarios logueados (rol
-- "authenticated" en Supabase Auth) pueden ejecutar la función, nunca
-- el público anónimo.
revoke all on function public.buscar_inmueble_activos(text) from public;
grant execute on function public.buscar_inmueble_activos(text) to authenticated;

-- Verificación rápida (opcional):
-- select * from public.buscar_inmueble_activos('50C-1874919');
-- El resultado ya no debe traer columnas fuera de esta lista.
