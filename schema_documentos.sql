-- Esquema para el sistema de Actas de Arrendamiento (words_comercial)
-- Base de datos: Neon (Postgres). Guarda tanto los datos estructurados de
-- cada caso como los archivos (PDFs de origen y Actas generadas) como
-- binarios (bytea), para no depender de un storage externo.

CREATE TABLE IF NOT EXISTS casos (
    fmi                 TEXT PRIMARY KEY,
    territorial         TEXT,
    tipo_bien           TEXT,
    tipo_contrato       TEXT,
    direccion           TEXT,
    arrendatario_nombre TEXT,
    id_siglas           TEXT,       -- 'C.C.' o 'NIT'
    id_numero           TEXT,
    id_ciudad           TEXT,
    estado              TEXT NOT NULL DEFAULT 'pendiente', -- pendiente | completo | con_observaciones
    pendientes          JSONB NOT NULL DEFAULT '[]',       -- lista de textos "falta esto, revisar aquello"
    creado_en           TIMESTAMPTZ NOT NULL DEFAULT now(),
    actualizado_en      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Correcciones manuales por campo: si existe una fila aquí para
-- (fmi, campo), su valor tiene prioridad sobre lo que la extracción
-- automática haya calculado para ese campo. Así una corrección puntual
-- (ej. "arrendatario_nombre" de un caso con documento escaneado sin
-- texto) queda guardada para siempre sin tocar el resto de la lógica.
CREATE TABLE IF NOT EXISTS correcciones_manuales (
    fmi             TEXT NOT NULL REFERENCES casos(fmi) ON DELETE CASCADE,
    campo           TEXT NOT NULL,
    valor           TEXT NOT NULL,
    nota            TEXT,
    actualizado_por TEXT,
    actualizado_en  TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (fmi, campo)
);

-- Documentos: tanto los PDFs de origen (subidos una vez por caso) como
-- las Actas ya generadas (una nueva versión cada vez que se regenera).
CREATE TABLE IF NOT EXISTS documentos (
    id              BIGSERIAL PRIMARY KEY,
    fmi             TEXT NOT NULL REFERENCES casos(fmi) ON DELETE CASCADE,
    tipo            TEXT NOT NULL, -- estimado_renta | solicitud_arrendamiento | carta_juramentada
                                    -- | cedula | rut | sagrilaft | foto_inmueble | documento_generado
    tipo_salida     TEXT,           -- solo cuando tipo='documento_generado': la clave del catálogo
                                     -- de app/tipos (ej. 'acta_arrendamiento', 'certificado_dd')
    nombre_archivo  TEXT NOT NULL,
    mime_type       TEXT NOT NULL,
    tamano_bytes    BIGINT NOT NULL,
    contenido       BYTEA NOT NULL,
    subido_en       TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_documentos_fmi ON documentos(fmi);
CREATE INDEX IF NOT EXISTS idx_documentos_fmi_tipo ON documentos(fmi, tipo);
CREATE INDEX IF NOT EXISTS idx_casos_arrendatario ON casos USING gin (to_tsvector('spanish', coalesce(arrendatario_nombre, '')));

-- Contadores/consecutivos que antes vivían en un archivo de texto local
-- (state/consecutivo_alcance.txt) -- ahora en la base de datos para que
-- no dependan de en qué computador corre el sistema.
CREATE TABLE IF NOT EXISTS contadores (
    clave   TEXT PRIMARY KEY,
    valor   INTEGER NOT NULL
);

-- Historial simple de quién generó qué Acta y cuándo (para auditoría).
CREATE TABLE IF NOT EXISTS generaciones (
    id              BIGSERIAL PRIMARY KEY,
    fmi             TEXT NOT NULL REFERENCES casos(fmi) ON DELETE CASCADE,
    documento_id    BIGINT REFERENCES documentos(id) ON DELETE SET NULL,
    generado_por    TEXT,
    generado_en     TIMESTAMPTZ NOT NULL DEFAULT now()
);
