-- `type`: que es el `content` de cada mensaje.
--   text      -> lo que escribio el cliente o respondio Clemente (todo lo anterior a esta migracion)
--   image_url -> una imagen del cliente: `content` es su URL de Cloudinary, no la de
--                Twilio (ver app/communication/services/media_service.py)
--
-- Una imagen es una fila propia y no un adjunto del mensaje de texto: asi el
-- historial la conserva en su lugar de la conversacion y el agente la vuelve a
-- ver en los turnos siguientes, aunque el cliente la haya mandado sin texto.
ALTER TABLE messages ADD COLUMN IF NOT EXISTS type TEXT NOT NULL DEFAULT 'text';

ALTER TABLE messages DROP CONSTRAINT IF EXISTS messages_type_check;
ALTER TABLE messages ADD CONSTRAINT messages_type_check CHECK (type IN ('text', 'image_url'));
