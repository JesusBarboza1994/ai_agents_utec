-- `data`: todo lo que se sabe del cliente y no tiene columna propia -- alergias,
-- preferencias de zona, idioma, lo que el agente vaya recogiendo. Sin tipar a
-- proposito: cada dato nuevo no deberia costar una migracion.
--
-- Es la columna `extra` de 0001, renombrada. Nacio con la misma intencion y
-- nunca tuvo lector ni escritor; dos blobs sin tipar en la misma tabla se
-- habrian repartido los datos del cliente sin que nadie supiera cual mirar.
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'customers' AND column_name = 'extra'
    ) THEN
        ALTER TABLE customers RENAME COLUMN extra TO data;
    END IF;
END $$;

ALTER TABLE customers ADD COLUMN IF NOT EXISTS data JSONB NOT NULL DEFAULT '{}';
