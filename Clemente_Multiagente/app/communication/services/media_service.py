"""
Imagenes que llegan por WhatsApp: de la URL de Twilio a una URL de Cloudinary.

Twilio no adjunta el archivo al webhook: manda `NumMedia` y, por cada adjunto,
`MediaUrl{i}` + `MediaContentType{i}`. Esa URL vive en la cuenta de Twilio,
pide las mismas credenciales que la API y no es algo que convenga darle al
agente. Por eso el recorrido es:

    MediaUrl (Twilio) -> archivo temporal local -> Cloudinary -> secure_url

El archivo local solo existe mientras se sube y se borra pase lo que pase.
Lo que sigue viaje es la URL de Cloudinary, que es lo que recibe el agente.

Como `outbound_whatsapp_service`, habla con las dos APIs por HTTP directo con
`requests`, sin SDK: son dos llamadas y no justifican una dependencia mas.
"""

from dataclasses import dataclass

import hashlib
import os
import tempfile
import time

import requests

from ...observabilidad.trazas import registrar

TWILIO_MEDIA_PREFIX = "https://api.twilio.com/"
CLOUDINARY_API_BASE = "https://api.cloudinary.com/v1_1"

# Lo que Clemente acepta como imagen. Audio, video y documentos siguen siendo
# media sin manejar (ver `whatsapp_service.parse_inbound`).
IMAGE_CONTENT_TYPES = {"image/jpeg", "image/png", "image/webp"}

# WhatsApp limita las imagenes a 5 MB; el margen cubre cambios del proveedor
# sin dejar que un adjunto inesperado llene el disco.
MAX_IMAGE_BYTES = 10 * 1024 * 1024
_CHUNK_BYTES = 64 * 1024

_EXTENSIONS = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"}


class MediaError(RuntimeError):
    """No se pudo descargar o subir un adjunto."""


@dataclass(frozen=True)
class MediaAdjunto:
    """Un adjunto tal como lo anuncia Twilio en el webhook."""

    url: str
    content_type: str

    @property
    def es_imagen(self) -> bool:
        """True para los formatos de imagen que Clemente procesa."""
        return self.content_type in IMAGE_CONTENT_TYPES


def extract_media(form) -> list[MediaAdjunto]:
    """Lee `NumMedia` y los pares `MediaUrl{i}`/`MediaContentType{i}` del webhook."""
    try:
        total = int(form.get("NumMedia") or 0)
    except ValueError:
        return []
    adjuntos = []
    for i in range(total):
        url = form.get(f"MediaUrl{i}") or ""
        if url:
            adjuntos.append(MediaAdjunto(url=url, content_type=form.get(f"MediaContentType{i}") or ""))
    return adjuntos


def download_twilio_media(adjunto: MediaAdjunto, account_sid: str, auth_token: str, destino: str) -> str:
    """
    Descarga el adjunto a un archivo temporal dentro de `destino` y devuelve su ruta.

    Solo acepta URLs de la API de Twilio: el formulario ya viene firmado, pero
    asi una URL inesperada nunca recibe nuestras credenciales. Twilio responde
    con una redireccion a su almacenamiento; `requests` no reenvia la
    autenticacion a otro host, que es justo lo correcto. Corta la descarga si
    pasa de MAX_IMAGE_BYTES y borra el archivo si algo falla a medias.
    """
    if not adjunto.url.startswith(TWILIO_MEDIA_PREFIX):
        raise MediaError("La URL del adjunto no es de la API de Twilio.")
    if not account_sid or not auth_token:
        raise MediaError("Faltan TWILIO_ACCOUNT_SID/TWILIO_AUTH_TOKEN para descargar el adjunto.")

    descriptor, ruta = tempfile.mkstemp(suffix=_EXTENSIONS.get(adjunto.content_type, ""), dir=destino)
    try:
        with os.fdopen(descriptor, "wb") as archivo, requests.get(
            adjunto.url, auth=(account_sid, auth_token), stream=True, timeout=15,
        ) as respuesta:
            if respuesta.status_code >= 400:
                raise MediaError(f"Twilio rechazo la descarga ({respuesta.status_code}).")
            escritos = 0
            for bloque in respuesta.iter_content(_CHUNK_BYTES):
                escritos += len(bloque)
                if escritos > MAX_IMAGE_BYTES:
                    raise MediaError(f"El adjunto supera {MAX_IMAGE_BYTES} bytes.")
                archivo.write(bloque)
    except Exception:
        os.remove(ruta)
        raise
    return ruta


def upload_to_cloudinary(ruta: str, cloud_name: str, api_key: str, api_secret: str, folder: str) -> str:
    """
    Sube el archivo con una subida firmada y devuelve su `secure_url`.

    Firma de Cloudinary: SHA-1 de los parametros firmados, ordenados como
    `clave=valor` unidos por '&', seguidos del api_secret. `file`, `api_key`
    y la propia firma no entran en la firma.
    """
    if not cloud_name or not api_key or not api_secret:
        raise MediaError("Faltan CLOUDINARY_CLOUD_NAME/API_KEY/API_SECRET.")

    firmados = {"timestamp": str(int(time.time()))}
    if folder:
        firmados["folder"] = folder
    a_firmar = "&".join(f"{clave}={firmados[clave]}" for clave in sorted(firmados))
    firma = hashlib.sha1(f"{a_firmar}{api_secret}".encode("utf-8")).hexdigest()

    with open(ruta, "rb") as archivo:
        respuesta = requests.post(
            f"{CLOUDINARY_API_BASE}/{cloud_name}/image/upload",
            data={**firmados, "api_key": api_key, "signature": firma},
            files={"file": archivo},
            timeout=30,
        )
    if respuesta.status_code >= 400:
        raise MediaError(f"Cloudinary rechazo la subida ({respuesta.status_code}): {respuesta.text}")
    url = respuesta.json().get("secure_url")
    if not url:
        raise MediaError("Cloudinary no devolvio secure_url.")
    return url


def subir_imagenes(adjuntos: list[MediaAdjunto], config, sesion_id: str) -> list[str]:
    """
    Pasa cada imagen por Twilio -> temporal -> Cloudinary y devuelve las URLs subidas.

    Un adjunto que falla se traza y se omite: el resto del mensaje (el texto y
    las demas imagenes) sigue su camino. Los archivos temporales viven en un
    directorio propio del turno que se borra entero al terminar.
    """
    urls: list[str] = []
    with tempfile.TemporaryDirectory(prefix="clemente-media-") as destino:
        for indice, adjunto in enumerate(a for a in adjuntos if a.es_imagen):
            try:
                ruta = download_twilio_media(
                    adjunto, config.twilio_account_sid, config.twilio_auth_token, destino,
                )
                url = upload_to_cloudinary(
                    ruta, config.cloudinary_cloud_name, config.cloudinary_api_key,
                    config.cloudinary_api_secret, config.cloudinary_folder,
                )
            except Exception as error:
                registrar("error", sesion_id, detalle={
                    "paso": "subir_imagen", "indice": indice,
                    "content_type": adjunto.content_type, "error": str(error),
                })
                continue
            registrar("imagen_subida", sesion_id, detalle={
                "indice": indice, "content_type": adjunto.content_type, "url": url,
            })
            urls.append(url)
    return urls
