-- Migración: agregar granularidad mensual al dashboard "Estadísticas".
-- Antes se guardaba un total por año; ahora se guarda un total por año Y
-- MES, para poder filtrar por mes exacto en el dashboard.
--
-- Los datos existentes (agrupados solo por año) se limpian porque ya no
-- sirven con la estructura nueva — se vuelven a calcular automáticamente
-- desde cero la próxima vez que corra actualizar_dashboard.py (ya sea a
-- mano desde GitHub Actions, o en el horario diario).

ALTER TABLE dashboard_ventas_anual ADD COLUMN IF NOT EXISTS mes INTEGER;

ALTER TABLE dashboard_ventas_anual
    DROP CONSTRAINT IF EXISTS dashboard_ventas_anual_sistema_anio_key;

DELETE FROM dashboard_ventas_anual;

ALTER TABLE dashboard_ventas_anual
    ADD CONSTRAINT dashboard_ventas_anual_sistema_anio_mes_key UNIQUE (sistema, anio, mes);
