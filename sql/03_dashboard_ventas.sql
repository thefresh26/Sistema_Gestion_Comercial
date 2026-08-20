-- Tabla donde se cachean los totales de ventas del dashboard comercial.
-- La llena el Cron Job (scripts/actualizar_dashboard.py); la lee la ruta
-- /api/dashboard/resumen de app.py. El tab del dashboard NUNCA consulta
-- directamente la base "intranet" de Azure — solo lee esta tabla, que ya
-- viene calculada.

CREATE TABLE IF NOT EXISTS dashboard_ventas_anual (
    id              BIGSERIAL PRIMARY KEY,
    sistema         TEXT NOT NULL,              -- 'SAE' o 'FRV'
    anio            INTEGER NOT NULL,
    cantidad        INTEGER NOT NULL DEFAULT 0,
    valor_total     NUMERIC(18,2) NOT NULL DEFAULT 0,
    es_acumulado_historico BOOLEAN NOT NULL DEFAULT FALSE,
    actualizado_en  TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (sistema, anio)
);

ALTER TABLE dashboard_ventas_anual ENABLE ROW LEVEL SECURITY;
-- Sin políticas públicas: solo el backend (service_role) lee/escribe aquí,
-- igual que el resto de tablas del sistema.

-- Seguimiento de qué bienes de FRV ya se contaron como "MONETIZADO", para
-- poder construir un historial real por año hacia adelante (el data.json
-- de FRV no trae fecha de venta, solo el estado actual — ver conversación
-- del 20 de agosto de 2026). La primera vez que este Cron Job corra,
-- todos los que ya estén en MONETIZADO quedan marcados con la fecha de
-- esa primera corrida (es_acumulado_historico = true en la tabla de
-- arriba); de ahí en adelante, cada nuevo "MONETIZADO" se detecta y se le
-- asigna la fecha real en que se detectó el cambio.
CREATE TABLE IF NOT EXISTS dashboard_frv_seguimiento (
    codigo_frv      TEXT PRIMARY KEY,
    fecha_detectado DATE NOT NULL DEFAULT CURRENT_DATE,
    valor_contable  NUMERIC(18,2) NOT NULL DEFAULT 0
);

ALTER TABLE dashboard_frv_seguimiento ENABLE ROW LEVEL SECURITY;
