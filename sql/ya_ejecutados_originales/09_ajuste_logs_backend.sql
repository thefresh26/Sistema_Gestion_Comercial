-- ============================================================
-- AJUSTE: permitir que el backend (service_role) inserte logs
-- sin depender de auth.uid() (el backend no manda un JWT de usuario).
-- Ejecutar en Supabase → SQL Editor, DESPUÉS de 08_endurecer_sae.sql
-- ============================================================

alter table public.logs_acceso
  alter column usuario_id drop not null,
  alter column usuario_id drop default;

-- grant execute a "authenticated" ya no es estrictamente necesario si
-- todas las búsquedas pasan por el backend (que usa service_role, que
-- ignora los grants), pero se deja para no romper el visor viejo
-- mientras ambos coexistan.
