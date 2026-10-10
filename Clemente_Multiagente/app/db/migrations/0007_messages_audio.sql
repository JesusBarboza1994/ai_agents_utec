-- Audios de WhatsApp: una fila `audio_url` por audio. `content` es la URL de Cloudinary
-- y `transcription` el texto que devolvio ElevenLabs (NULL si la transcripcion fallo).
-- El agente nunca ve el audio: recibe `transcription` como si fuera texto del cliente.
ALTER TABLE messages ADD COLUMN IF NOT EXISTS transcription TEXT;

ALTER TABLE messages DROP CONSTRAINT IF EXISTS messages_type_check;
ALTER TABLE messages ADD CONSTRAINT messages_type_check CHECK (type IN ('text', 'image_url', 'audio_url'));
