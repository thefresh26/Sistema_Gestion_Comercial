-- Migración: separar "folios" de "unidades" en el dashboard "Estadísticas"
-- para SAE. En el negocio, una unidad puede agrupar varios folios (todos se
-- venden juntos); un folio sin grupo es una unidad de un solo folio. FRV no
-- maneja esta distinción, así que sus filas quedan con medida = 'total'.

ALTER TABLE dashboard_ventas_anual ADD COLUMN IF NOT EXISTS medida TEXT NOT NULL DEFAULT 'total';

ALTER TABLE dashboard_ventas_anual
    DROP CONSTRAINT IF EXISTS dashboard_ventas_anual_sistema_anio_mes_key;

DELETE FROM dashboard_ventas_anual;

ALTER TABLE dashboard_ventas_anual
    ADD CONSTRAINT dashboard_ventas_anual_sistema_anio_mes_medida_key UNIQUE (sistema, anio, mes, medida);
