"""
Transcripcion de audios con ElevenLabs (Speech to Text, modelo Scribe).

Como `media_service` y `outbound_whatsapp_service`, habla con la API por HTTP
directo con `requests`, sin SDK. Recibe la ruta de un archivo local y devuelve
el texto; no sabe nada de WhatsApp ni de Cloudinary.

El idioma no se fija: Scribe lo detecta solo, que es lo correcto para clientes
que escriben en espanol, ingles o mezclan.
"""

import requests

ELEVENLABS_STT_URL = "https://api.elevenlabs.io/v1/speech-to-text"


class TranscriptionError(RuntimeError):
    """No se pudo transcribir el audio."""


def transcribir(ruta: str, api_key: str, modelo: str = "scribe_v1", timeout: float = 60) -> str:
    """Transcribe el archivo de audio en `ruta` y devuelve el texto, sin espacios en los bordes.

    Falla con TranscriptionError si falta la clave, si ElevenLabs rechaza la
    peticion o si el audio no tiene voz reconocible (texto vacio): el llamador
    decide que hacer, esta funcion nunca devuelve una cadena vacia."""
    if not api_key:
        raise TranscriptionError("Falta ELEVENLABS_API_KEY.")

    with open(ruta, "rb") as archivo:
        respuesta = requests.post(
            ELEVENLABS_STT_URL,
            headers={"xi-api-key": api_key},
            data={"model_id": modelo},
            files={"file": archivo},
            timeout=timeout,
        )
    if respuesta.status_code >= 400:
        raise TranscriptionError(f"ElevenLabs rechazo la transcripcion ({respuesta.status_code}): {respuesta.text[:200]}")
    texto = (respuesta.json().get("text") or "").strip()
    if not texto:
        raise TranscriptionError("El audio no contiene voz reconocible.")
    return texto
