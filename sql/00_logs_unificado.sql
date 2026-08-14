-- ============================================================
-- Sistema de Gestión Comercial — tabla de trazabilidad unificada.
--
-- Antes había 3 tablas de logs, una por app (logs_acceso, logs_acceso_vi,
-- logs_acceso_frv). Ahora las 3 escriben en una sola tabla, con una
-- columna "modulo" para saber de dónde vino cada evento:
--   'portal' / 'sae' / 'frv'  -> este backend unificado (SAE + FRV)
--   'vista_inmuebles'         -> Vista_Inmuebles_backend (brokers), que
--                                sigue siendo una app separada — solo
--                                cambia dónde guarda su rastro. Requiere
--                                actualizar su app.py (ver el archivo
--                                vista_inmuebles_backend_patch/app.py que
--                                te entregué junto con este portal).
--
-- Nota sobre inventario: NO hace falta tocar inventario_SAE ni
-- inventario_Activos. Ya están bien como están — inventario_SAE es la
-- única fuente de verdad de los datos del inmueble (la usan tanto SAE
-- como Vista_Inmuebles vía la función buscar_inmueble_activos), e
-- inventario_Activos es solo una tabla chica de referencia para el
-- indicador de "viabilidad" (si el FMI existe ahí o no). No son
-- duplicados que haya que fusionar.
--
-- Requisito previo: este portal reutiliza las funciones/tablas que ya
-- creaste en los proyectos originales:
--   - RPC buscar_folios(p_folios) -> usada por el módulo SAE
--     (viene de 08_endurecer_sae.sql / 01_migracion_supabase.sql del
--     repo Vista_inmuebles_SAE)
--   - Las columnas expresion_interes / codigo_subasta en inventario_SAE
--     (05_carga_expresiones_interes.sql, 07_codigos_subasta_v2.sql)
-- Ninguno de esos scripts cambia: el portal solo llama a esa RPC igual
-- que lo hacía Backend_SAE.
-- ============================================================

create table if not exists public.logs_acceso_sistema (
  id bigint generated always as identity primary key,
  modulo text not null,              -- 'portal' | 'sae' | 'frv'
  usuario_email text,
  accion text,
  detalle text,
  ip_address text,
  creado_en timestamptz not null default now()
);

alter table public.logs_acceso_sistema enable row level security;
-- Sin políticas: solo el backend con service_role puede escribir/leer,
-- igual que en logs_acceso_vi / logs_acceso_frv. El navegador nunca
-- tiene la service_role key, así que no puede tocar esta tabla.

-- Si quieres conservar el historial de las tablas viejas, puedes migrarlo
-- así (opcional, ejecutar solo si te sirve tener todo en un solo lugar):
--
-- insert into public.logs_acceso_sistema (modulo, usuario_email, accion, detalle, ip_address, creado_en)
--   select 'sae', usuario_email, accion, detalle, ip_address, creado_en from public.logs_acceso;
-- insert into public.logs_acceso_sistema (modulo, usuario_email, accion, detalle, ip_address, creado_en)
--   select 'frv', usuario_email, accion, detalle, ip_address, creado_en from public.logs_acceso_frv;
-- insert into public.logs_acceso_sistema (modulo, usuario_email, accion, detalle, ip_address, creado_en)
--   select 'vista_inmuebles', usuario_email, accion, detalle, ip_address, creado_en from public.logs_acceso_vi;
