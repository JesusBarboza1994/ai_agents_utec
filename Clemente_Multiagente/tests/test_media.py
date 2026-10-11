"""Imagenes de WhatsApp: Twilio -> temporal local -> Cloudinary -> agente, sin red real."""

import hashlib
import os

import pytest

from app import create_app
from app.config import Config
from app.contratos import RespuestaClemente
from app.communication.services import media_service, whatsapp_service
from app.communication.services.media_service import MediaAdjunto, MediaError
from app.communication.services.whatsapp_service import IncomingMessage, parse_inbound
from app.observabilidad.trazas import ultimas_trazas

URL_TWILIO = "https://api.twilio.com/2010-04-01/Accounts/AC1/Messages/MM1/Media/ME1"
URL_CLOUDINARY = "https://res.cloudinary.com/demo/image/upload/v1/clemente/whatsapp/abc.jpg"
JPEG = MediaAdjunto(url=URL_TWILIO, content_type="image/jpeg")


class _Descarga:
    """Respuesta falsa de `requests.get` con streaming."""

    def __init__(self, contenido=b"\xff\xd8imagen", status_code=200):
        """Guarda el contenido de la descarga simulada y su codigo de estado HTTP."""
        self.contenido, self.status_code = contenido, status_code

    def iter_content(self, _tamano):
        """Entrega el contenido simulado en un unico bloque, como `requests` al leer por trozos."""
        yield self.contenido

    def __enter__(self):
        """Permite usar la descarga simulada como administrador de contexto."""
        return self

    def __exit__(self, *_):
        """Cierra el contexto sin suprimir excepciones."""
        return False


class _Subida:
    """Respuesta falsa de la API de subida de Cloudinary."""

    def __init__(self, status_code=200, secure_url=URL_CLOUDINARY):
        """Guarda el codigo de estado y la URL segura que devolveria Cloudinary."""
        self.status_code, self.text = status_code, "rechazado"
        self._json = {"secure_url": secure_url}

    def json(self):
        """Devuelve el cuerpo JSON simulado de la subida."""
        return self._json


def _config(**kwargs):
    """Config con credenciales falsas de Twilio y Cloudinary."""
    base = dict(
        database_url="postgresql://prueba", langsmith_tracing=False,
        twilio_account_sid="AC1", twilio_auth_token="token",
        cloudinary_cloud_name="demo", cloudinary_api_key="key",
        cloudinary_api_secret="secreto", cloudinary_folder="clemente/whatsapp",
    )
    return Config(**{**base, **kwargs})


# --- lectura del webhook ---------------------------------------------------

def test_extract_media_lee_todos_los_adjuntos():
    """Cada MediaUrl{i} se empareja con su MediaContentType{i}."""
    form = {
        "NumMedia": "2",
        "MediaUrl0": URL_TWILIO, "MediaContentType0": "image/jpeg",
        "MediaUrl1": URL_TWILIO + "2", "MediaContentType1": "audio/ogg",
    }
    assert media_service.extract_media(form) == [
        MediaAdjunto(URL_TWILIO, "image/jpeg"), MediaAdjunto(URL_TWILIO + "2", "audio/ogg"),
    ]


def test_extract_media_sin_adjuntos_o_num_media_invalido():
    """Sin NumMedia, o con uno ilegible, no hay adjuntos."""
    assert media_service.extract_media({"Body": "hola"}) == []
    assert media_service.extract_media({"NumMedia": "x"}) == []


def test_parse_inbound_una_imagen_sin_texto_es_contenido_utilizable():
    """Solo imagen: no queda marcada como media sin manejar."""
    message = parse_inbound({
        "From": "whatsapp:+51999111222", "NumMedia": "1",
        "MediaUrl0": URL_TWILIO, "MediaContentType0": "image/jpeg",
    })
    assert message.media == [JPEG]
    assert message.unsupported_reason is None


def test_parse_inbound_video_solo_sigue_sin_soporte():
    """Video sin texto sigue sin manejarse."""
    message = parse_inbound({
        "From": "whatsapp:+51999111222", "NumMedia": "1",
        "MediaUrl0": URL_TWILIO, "MediaContentType0": "video/mp4",
    })
    assert message.unsupported_reason == "media sin manejar (video/mp4)"


def test_parse_inbound_audio_solo_es_contenido_utilizable():
    """Una nota de voz sin texto ya no es 'sin soporte'; el MIME con codecs tambien cuenta."""
    message = parse_inbound({
        "From": "whatsapp:+51999111222", "NumMedia": "1",
        "MediaUrl0": URL_TWILIO, "MediaContentType0": "audio/ogg; codecs=opus",
    })
    assert message.unsupported_reason is None
    assert message.media[0].es_audio


# --- descarga de Twilio ----------------------------------------------------

def test_descarga_con_credenciales_de_twilio(monkeypatch, tmp_path):
    """La descarga usa Account SID + Auth Token y deja el archivo en el temporal."""
    pedido = {}

    def falso_get(url, **kwargs):
        """Anota la peticion de descarga y devuelve una descarga simulada, sin tocar la red."""
        pedido.update(url=url, **kwargs)
        return _Descarga()

    monkeypatch.setattr(media_service.requests, "get", falso_get)
    ruta = media_service.download_twilio_media(JPEG, "AC1", "token", str(tmp_path))

    assert pedido["url"] == URL_TWILIO
    assert pedido["auth"] == ("AC1", "token")
    assert ruta.endswith(".jpg") and os.path.dirname(ruta) == str(tmp_path)
    with open(ruta, "rb") as archivo:
        assert archivo.read() == b"\xff\xd8imagen"


def test_descarga_rechaza_urls_que_no_son_de_twilio(monkeypatch, tmp_path):
    """Las credenciales nunca viajan a un host que no sea la API de Twilio."""
    monkeypatch.setattr(media_service.requests, "get", lambda *a, **k: pytest.fail("no debe descargar"))
    with pytest.raises(MediaError):
        media_service.download_twilio_media(
            MediaAdjunto("https://evil.example/x.jpg", "image/jpeg"), "AC1", "token", str(tmp_path))


def test_descarga_demasiado_grande_no_deja_archivo(monkeypatch, tmp_path):
    """Pasar del limite corta la descarga y borra el archivo a medias."""
    monkeypatch.setattr(media_service, "MAX_IMAGE_BYTES", 4)
    monkeypatch.setattr(media_service.requests, "get", lambda *a, **k: _Descarga(b"12345"))
    with pytest.raises(MediaError):
        media_service.download_twilio_media(JPEG, "AC1", "token", str(tmp_path))
    assert list(tmp_path.iterdir()) == []


# --- subida a Cloudinary ---------------------------------------------------

def test_subida_firmada_a_cloudinary(monkeypatch, tmp_path):
    """La firma es SHA-1 de los parametros ordenados + api_secret."""
    archivo = tmp_path / "foto.jpg"
    archivo.write_bytes(b"imagen")
    pedido = {}

    def falso_post(url, data, files, timeout):
        """Anota la peticion de subida firmada a Cloudinary y devuelve una respuesta simulada."""
        pedido.update(url=url, data=data, nombre=files["file"].name)
        return _Subida()

    monkeypatch.setattr(media_service.requests, "post", falso_post)
    monkeypatch.setattr(media_service.time, "time", lambda: 1700000000)

    url = media_service.upload_to_cloudinary(str(archivo), "demo", "key", "secreto", "clemente/whatsapp")

    assert url == URL_CLOUDINARY
    assert pedido["url"] == "https://api.cloudinary.com/v1_1/demo/image/upload"
    esperado = hashlib.sha1(b"folder=clemente/whatsapp&timestamp=1700000000secreto").hexdigest()
    assert pedido["data"] == {
        "timestamp": "1700000000", "folder": "clemente/whatsapp",
        "api_key": "key", "signature": esperado,
    }
    assert pedido["nombre"] == str(archivo)


def test_subida_sin_credenciales_de_cloudinary(tmp_path):
    """Sin credenciales no se intenta subir."""
    with pytest.raises(MediaError):
        media_service.upload_to_cloudinary(str(tmp_path / "x.jpg"), "", "", "", "")


# --- recorrido completo ----------------------------------------------------

def test_subir_imagenes_borra_los_temporales_y_omite_lo_que_falla(monkeypatch):
    """Una imagen que falla se traza y se omite; los temporales no sobreviven al turno."""
    rutas = []

    def falso_get(url, **_kwargs):
        """Devuelve una descarga fallida (404) para las URL que terminan en 'falla' y una correcta para las demas."""
        if url.endswith("falla"):
            return _Descarga(status_code=404)
        return _Descarga()

    def falso_post(url, data, files, timeout):
        """Anota el archivo temporal que se sube y devuelve una subida simulada correcta."""
        rutas.append(files["file"].name)
        return _Subida()

    monkeypatch.setattr(media_service.requests, "get", falso_get)
    monkeypatch.setattr(media_service.requests, "post", falso_post)

    adjuntos = [JPEG, MediaAdjunto(URL_TWILIO + "falla", "image/png"),
                MediaAdjunto(URL_TWILIO + "audio", "audio/ogg")]
    urls = media_service.subir_imagenes(adjuntos, _config(), "whatsapp-media-1")

    assert urls == [URL_CLOUDINARY]
    assert rutas and not any(os.path.exists(ruta) for ruta in rutas)
    eventos = [t.evento for t in ultimas_trazas(10, "whatsapp-media-1")]
    assert "imagen_subida" in eventos and "error" in eventos


def _patch_flujo(monkeypatch, recibidos):
    """Base y orquestador falsos: captura el MensajeEntrante que llega al agente."""
    ruta = "app.communication.services.chat_service"
    monkeypatch.setattr(f"{ruta}.customers_repository.get_or_create_customer", lambda *a, **k: "c1")
    monkeypatch.setattr(f"{ruta}.chats_repository.get_or_create_chat", lambda *a, **k: "chat1")
    monkeypatch.setattr(f"{ruta}.messages_repository.append_message", lambda *a, **k: None)
    monkeypatch.setattr(f"{ruta}.messages_repository.get_recent_messages", lambda *a, **k: [])
    monkeypatch.setattr(f"{ruta}.customers_repository.get_customer", lambda *a, **k: {})

    def orquestador(entrante, **_kwargs):
        """Orquestador simulado: guarda el mensaje entrante que recibe y responde 'ok'."""
        recibidos.append(entrante)
        return RespuestaClemente(texto="ok", agente="informacion", sesion_id=entrante.sesion_id)

    monkeypatch.setattr(f"{ruta}.responder_orquestador", orquestador)


def test_la_imagen_llega_al_agente_como_url_de_cloudinary(monkeypatch):
    """Al orquestador le llega la URL de Cloudinary, nunca la de Twilio."""
    recibidos = []
    _patch_flujo(monkeypatch, recibidos)
    monkeypatch.setattr(media_service, "subir_imagenes", lambda adjuntos, config, sesion: [URL_CLOUDINARY])

    with create_app(_config()).app_context():
        reply = whatsapp_service.process_inbound(IncomingMessage(
            channel="whatsapp", chat_key="51999111222", text="", media=[JPEG]))

    assert reply == "ok"
    assert recibidos[0].imagenes == [URL_CLOUDINARY]
    assert recibidos[0].texto == ""


def test_imagen_sin_texto_que_no_se_pudo_subir_no_abre_turno(monkeypatch):
    """Si no hay texto y ninguna imagen se subio, no hay nada que atender."""
    recibidos = []
    _patch_flujo(monkeypatch, recibidos)
    monkeypatch.setattr(media_service, "subir_imagenes", lambda *a: [])

    with create_app(_config()).app_context():
        assert whatsapp_service.process_inbound(IncomingMessage(
            channel="whatsapp", chat_key="51999111222", text="", media=[JPEG])) is None
    assert recibidos == []


def test_el_orquestador_pone_las_imagenes_en_el_contexto_del_agente(monkeypatch):
    """`ContextoConversacion.imagenes` es donde los agentes las encuentran."""
    from app.contratos import MensajeEntrante
    from app.orquestador import grafo

    capturado = {}

    class _Grafo:
        """Grafo simulado que captura el contexto del turno en lugar de ejecutar el orquestador."""
        def invoke(self, estado):
            """Guarda el contexto recibido y devuelve un cierre fijo para el turno."""
            capturado["contexto"] = estado["contexto"]
            return {"respuesta": "ok", "ruta": "informacion", "motivo_ruta": "prueba", "plan": []}

    monkeypatch.setattr(grafo, "obtener_grafo", lambda: _Grafo())
    grafo.responder(MensajeEntrante(sesion_id="web-img", texto="mira", imagenes=[URL_CLOUDINARY]))

    assert capturado["contexto"].imagenes == [URL_CLOUDINARY]


def test_config_lee_cloudinary_url(monkeypatch):
    """CLOUDINARY_URL del panel es la unica fuente de las credenciales de Cloudinary."""
    monkeypatch.setenv("CLOUDINARY_URL", "cloudinary://123456:s3cr%2Bt@mi-nube")
    config = Config.desde_entorno()
    assert (config.cloudinary_cloud_name, config.cloudinary_api_key,
            config.cloudinary_api_secret) == ("mi-nube", "123456", "s3cr+t")
    assert config.cloudinary_folder == "clemente/whatsapp"


def test_config_sin_cloudinary_url_queda_vacia(monkeypatch):
    """Sin CLOUDINARY_URL, o con otro esquema, no hay credenciales."""
    monkeypatch.delenv("CLOUDINARY_URL", raising=False)
    assert Config.desde_entorno().cloudinary_cloud_name == ""
    monkeypatch.setenv("CLOUDINARY_URL", "https://123456:secreto@mi-nube")
    assert Config.desde_entorno().cloudinary_api_key == ""


# --- persistencia como mensaje `image_url` -----------------------------------

def _patch_persistencia(monkeypatch, guardados, recibidos, recientes=()):
    """Base falsa que captura cada fila y orquestador falso que captura el historial."""
    ruta = "app.communication.services.chat_service"
    monkeypatch.setattr(f"{ruta}.customers_repository.get_or_create_customer", lambda *a, **k: "c1")
    monkeypatch.setattr(f"{ruta}.chats_repository.get_or_create_chat", lambda *a, **k: "chat1")
    monkeypatch.setattr(f"{ruta}.chats_repository.touch", lambda *a: None)
    monkeypatch.setattr(f"{ruta}.customers_repository.get_customer", lambda *a, **k: {})
    monkeypatch.setattr(f"{ruta}.messages_repository.get_recent_messages", lambda *a, **k: list(recientes))
    monkeypatch.setattr(
        f"{ruta}.messages_repository.append_message",
        lambda chat_id, rol, contenido, **k: guardados.append((rol, k["message_type"], contenido)),
    )

    def orquestador(entrante, historial=None, **_kwargs):
        """Orquestador simulado: guarda el historial que recibe y responde 'ok'."""
        recibidos.append(historial)
        return RespuestaClemente(texto="ok", agente="informacion", sesion_id=entrante.sesion_id)

    monkeypatch.setattr(f"{ruta}.responder_orquestador", orquestador)


def test_cada_imagen_se_guarda_como_mensaje_image_url(monkeypatch):
    """Imagen + texto: una fila `image_url` con la URL de Cloudinary y una `text`."""
    guardados, recibidos = [], []
    _patch_persistencia(monkeypatch, guardados, recibidos)
    monkeypatch.setattr(media_service, "subir_imagenes", lambda *a: [URL_CLOUDINARY])

    with create_app(_config()).app_context():
        whatsapp_service.process_inbound(IncomingMessage(
            channel="whatsapp", chat_key="51999111222", text="mira esto", media=[JPEG]))

    assert guardados == [
        ("user", "image_url", URL_CLOUDINARY),
        ("user", "text", "mira esto"),
        ("assistant", "text", "ok"),
    ]


def test_imagen_sola_no_guarda_una_fila_de_texto_vacia(monkeypatch):
    """Sin texto, la imagen es el unico mensaje del cliente en la base."""
    guardados, recibidos = [], []
    _patch_persistencia(monkeypatch, guardados, recibidos)
    monkeypatch.setattr(media_service, "subir_imagenes", lambda *a: [URL_CLOUDINARY])

    with create_app(_config()).app_context():
        whatsapp_service.process_inbound(IncomingMessage(
            channel="whatsapp", chat_key="51999111222", text="", media=[JPEG]))

    assert [fila[:2] for fila in guardados] == [("user", "image_url"), ("assistant", "text")]


def test_la_imagen_del_turno_no_se_duplica_en_el_historial(monkeypatch):
    """La imagen de este turno viaja en `imagenes` (la ve el agente), no repetida en el historial."""
    guardados, recibidos = [], []
    previos = [{"role": "user", "type": "text", "content": "hola"},
               {"role": "assistant", "type": "text", "content": "Hola!"}]
    _patch_persistencia(monkeypatch, guardados, recibidos, previos)
    monkeypatch.setattr(media_service, "subir_imagenes", lambda *a: [URL_CLOUDINARY])

    with create_app(_config()).app_context():
        whatsapp_service.process_inbound(IncomingMessage(
            channel="whatsapp", chat_key="51999111222", text="mira", media=[JPEG]))

    assert recibidos[0] == [
        {"role": "user", "content": "hola"},
        {"role": "assistant", "content": "Hola!"},
    ]


def test_imagen_sola_no_pasa_por_guardrails(monkeypatch):
    """Sin texto no hay nada que validar: el servicio rechazaria un texto vacio."""
    guardados, recibidos = [], []
    _patch_persistencia(monkeypatch, guardados, recibidos)
    monkeypatch.setattr(media_service, "subir_imagenes", lambda *a: [URL_CLOUDINARY])
    monkeypatch.setattr("app.seguridad.guardrails_ai.requests.post",
                        lambda *a, **k: pytest.fail("no debe validar un texto vacio"))
    monkeypatch.setattr("app.seguridad.guardrails_ai.validar_salida",
                        lambda texto, *a: type("R", (), {"permitido": True, "texto": texto})())

    with create_app(_config(guardrails_url="http://guardrails")).app_context():
        reply = whatsapp_service.process_inbound(IncomingMessage(
            channel="whatsapp", chat_key="51999111222", text="", media=[JPEG]))

    assert reply == "ok"


# --- el agente ve la imagen ------------------------------------------------

def test_contenido_del_turno_sin_imagenes_es_texto():
    """Sin imagenes el mensaje sigue siendo un string, como siempre."""
    from app.agentes.base import _contenido_del_turno
    assert _contenido_del_turno("hola", []) == "hola"


def test_contenido_del_turno_con_imagen_es_multimodal():
    """Texto con la URL citada + un bloque de imagen por cada imagen."""
    from app.agentes.base import _contenido_del_turno
    assert _contenido_del_turno("mira", [URL_CLOUDINARY]) == [
        {"type": "text", "text": f"mira\n[Imagen adjunta del cliente: {URL_CLOUDINARY}]"},
        {"type": "image", "url": URL_CLOUDINARY},
    ]


def test_ejecutar_manda_la_imagen_al_modelo(monkeypatch):
    """El ultimo mensaje que recibe el agente lleva el bloque de imagen."""
    from app.agentes import base
    from app.agentes.contexto import ContextoConversacion

    enviados = {}

    class _Agente:
        """Agente simulado que captura los mensajes que se enviarian al modelo."""
        def invoke(self, entrada, config=None, context=None):
            """Guarda los mensajes de la entrada y responde con un texto fijo."""
            enviados["mensajes"] = entrada["messages"]
            return {"messages": [type("M", (), {"content": "Veo la foto"})()]}

    monkeypatch.setattr(base, "_hilo_en_pausa", lambda *a: False)
    monkeypatch.setattr(base, "_olvidar_hilo", lambda *a: None)
    monkeypatch.setattr(base, "ficha_del_cliente", lambda *a: "")
    contexto = ContextoConversacion(sesion_id="whatsapp-x", imagenes=[URL_CLOUDINARY])

    assert base.ejecutar(_Agente(), "", "whatsapp-x", [], contexto=contexto) == "Veo la foto"
    contenido = enviados["mensajes"][-1]["content"]
    assert {"type": "image", "url": URL_CLOUDINARY} in contenido
    assert base.TEXTO_SOLO_IMAGEN in contenido[0]["text"]


def test_el_planificador_atiende_un_turno_solo_imagen(monkeypatch):
    """Una imagen sin texto se planifica (no cae en "no me llego ningun mensaje")."""
    from app.agentes.contexto import ContextoConversacion
    from app.orquestador import grafo

    recibido = {}

    class _Modelo:
        """Modelo simulado del planificador: guarda la entrada que recibe y devuelve un plan fijo."""
        def with_structured_output(self, _esquema):
            """Devuelve el mismo modelo simulado, sin aplicar el esquema."""
            return self

        def invoke(self, mensajes):
            """Guarda el ultimo mensaje recibido y devuelve un plan hacia incidencias."""
            recibido["entrada"] = mensajes[-1].content
            return grafo.PlanDeResolucion(pasos=["incidencias"], motivo="foto de un reclamo")

    monkeypatch.setattr(grafo, "resolver_modelo", lambda **k: _Modelo())
    salida = grafo._nodo_planificador({
        "sesion_id": "whatsapp-x", "mensaje": "", "historial": [],
        "contexto": ContextoConversacion(sesion_id="whatsapp-x", imagenes=[URL_CLOUDINARY]),
    })

    assert salida["plan"] == ["incidencias"]
    assert "(sin texto)" in recibido["entrada"]
    assert "adjunto 1 imagen(es)" in recibido["entrada"]


def test_las_imagenes_guardadas_vuelven_en_turnos_siguientes(monkeypatch):
    """Una fila `image_url` leida de la base llega al agente marcada como imagen."""
    guardados, recibidos = [], []
    previos = [{"role": "user", "type": "image_url", "content": URL_CLOUDINARY},
               {"role": "assistant", "type": "text", "content": "Que linda foto"}]
    _patch_persistencia(monkeypatch, guardados, recibidos, previos)

    with create_app(_config()).app_context():
        whatsapp_service.process_inbound(IncomingMessage(
            channel="whatsapp", chat_key="51999111222", text="y la otra?"))

    assert recibidos[0][0] == {"role": "user", "content": f"[imagen del cliente] {URL_CLOUDINARY}"}


# --- imagenes de turnos anteriores -----------------------------------------

def test_las_fotos_recientes_del_historial_vuelven_como_imagen():
    """Una foto de los ultimos turnos se le muestra al modelo; el texto con la URL se conserva."""
    from app.agentes.base import _con_imagenes_recientes
    foto = f"[imagen del cliente] {URL_CLOUDINARY}"
    historial = [{"role": "user", "content": foto}, {"role": "assistant", "content": "Que lindo salon"}]

    resultado = _con_imagenes_recientes(historial)

    assert resultado[0]["content"] == [
        {"type": "text", "text": foto}, {"type": "image", "url": URL_CLOUDINARY},
    ]
    assert resultado[1] == historial[1]
    assert historial[0]["content"] == foto   # no modifica lo recibido


def test_las_fotos_viejas_del_historial_quedan_como_texto(monkeypatch):
    """Fuera de la ventana, la foto no se reenvia: queda solo su URL."""
    from app.agentes import base
    monkeypatch.setattr(base, "MENSAJES_CON_IMAGEN_VISIBLE", 2)
    foto = f"[imagen del cliente] {URL_CLOUDINARY}"
    historial = [{"role": "user", "content": foto},
                 {"role": "assistant", "content": "ok"},
                 {"role": "user", "content": "otra cosa"},
                 {"role": "assistant", "content": "dale"}]

    assert base._con_imagenes_recientes(historial) == historial


def test_las_reglas_de_imagen_estan_en_los_prompts():
    """Los agentes no dicen que no ven fotos, y el planificador no las ata a la continuidad."""
    from app.agentes.prompts import PROMPT_INCIDENCIAS, PROMPT_ORQUESTADOR, PROMPT_RESERVAS
    from app.orquestador.grafo import PROMPT_PLANIFICADOR

    for prompt in (PROMPT_ORQUESTADOR, PROMPT_RESERVAS, PROMPT_INCIDENCIAS):
        assert "nunca digas que no puedes ver o evaluar fotos" in prompt
    assert "esta regla le gana a la\nde continuidad" in PROMPT_PLANIFICADOR


# --- audios: Twilio -> Cloudinary + ElevenLabs -> agente como texto -------------

AUDIO = MediaAdjunto(url=URL_TWILIO, content_type="audio/ogg")
URL_AUDIO = "https://res.cloudinary.com/demo/video/upload/v1/clemente/whatsapp/nota.ogg"


def _patch_audio(monkeypatch, transcripcion="quiero reservar para dos"):
    """Descarga, ElevenLabs y Cloudinary falsos; devuelve las URLs de subida usadas."""
    usadas = []
    monkeypatch.setattr(media_service.requests, "get", lambda *a, **k: _Descarga(b"OggS"))

    def falso_post(url, **_kwargs):
        """Anota la URL de subida y devuelve una subida simulada del audio."""
        usadas.append(url)
        return _Subida(secure_url=URL_AUDIO)

    monkeypatch.setattr(media_service.requests, "post", falso_post)

    def transcribir(ruta, api_key, modelo):
        """Devuelve la transcripcion simulada o lanza la excepcion configurada."""
        if isinstance(transcripcion, Exception):
            raise transcripcion
        return transcripcion

    monkeypatch.setattr(media_service.transcription_service, "transcribir", transcribir)
    return usadas


def test_el_audio_se_sube_como_video_y_se_transcribe(monkeypatch):
    """Cloudinary guarda el audio bajo el tipo `video`; la transcripcion sale del mismo temporal."""
    usadas = _patch_audio(monkeypatch)
    resultado = media_service.procesar_audios([AUDIO], _config(elevenlabs_api_key="k"), "whatsapp-a1")

    assert resultado == [media_service.AudioProcesado(url=URL_AUDIO, transcripcion="quiero reservar para dos")]
    assert usadas == ["https://api.cloudinary.com/v1_1/demo/video/upload"]


def test_audio_sin_transcripcion_se_conserva_y_se_traza(monkeypatch):
    """Si ElevenLabs falla, el audio se sube igual para que el personal pueda oirlo."""
    from app.communication.services.transcription_service import TranscriptionError
    _patch_audio(monkeypatch, transcripcion=TranscriptionError("sin voz"))
    resultado = media_service.procesar_audios([AUDIO], _config(), "whatsapp-a2")

    assert resultado == [media_service.AudioProcesado(url=URL_AUDIO, transcripcion=None)]
    assert any(t.evento == "error" for t in ultimas_trazas(10, "whatsapp-a2"))


def test_audio_que_no_se_pudo_descargar_se_omite(monkeypatch):
    """Sin descarga no hay archivo que transcribir ni subir."""
    _patch_audio(monkeypatch)
    monkeypatch.setattr(media_service.requests, "get", lambda *a, **k: _Descarga(status_code=500))
    assert media_service.procesar_audios([AUDIO], _config(), "whatsapp-a3") == []


def test_el_agente_recibe_la_transcripcion_como_texto(monkeypatch):
    """Texto escrito + audio llegan al orquestador como un solo texto, sin marca de audio."""
    recibidos = []
    _patch_flujo(monkeypatch, recibidos)
    monkeypatch.setattr(
        media_service, "procesar_audios",
        lambda *a: [media_service.AudioProcesado(URL_AUDIO, "para dos personas")],
    )

    with create_app(_config()).app_context():
        reply = whatsapp_service.process_inbound(IncomingMessage(
            channel="whatsapp", chat_key="51999111222", text="hola", media=[AUDIO]))

    assert reply == "ok"
    assert recibidos[0].texto == "hola\npara dos personas"
    assert recibidos[0].imagenes == []


def test_el_audio_se_guarda_como_audio_url_con_su_transcripcion(monkeypatch):
    """Una fila `audio_url` con la transcripcion y NO una fila de texto duplicada."""
    guardados, recibidos = [], []
    _patch_persistencia(monkeypatch, guardados, recibidos)
    monkeypatch.setattr(
        f"app.communication.services.chat_service.messages_repository.append_message",
        lambda chat_id, rol, contenido, **k: guardados.append(
            (rol, k["message_type"], contenido, k.get("transcription"))),
    )
    monkeypatch.setattr(
        media_service, "procesar_audios",
        lambda *a: [media_service.AudioProcesado(URL_AUDIO, "para dos personas")],
    )

    with create_app(_config()).app_context():
        whatsapp_service.process_inbound(IncomingMessage(
            channel="whatsapp", chat_key="51999111222", text="", media=[AUDIO]))

    assert guardados[0] == ("user", "audio_url", URL_AUDIO, "para dos personas")
    assert [g for g in guardados if g[1] == "text" and g[0] == "user"] == []


def test_audio_ilegible_sin_texto_responde_un_aviso(monkeypatch):
    """Sin transcripcion ni texto no se llama al agente: el cliente recibe un aviso."""
    recibidos = []
    _patch_flujo(monkeypatch, recibidos)
    monkeypatch.setattr(
        media_service, "procesar_audios",
        lambda *a: [media_service.AudioProcesado(URL_AUDIO, None)],
    )

    with create_app(_config()).app_context():
        reply = whatsapp_service.process_inbound(IncomingMessage(
            channel="whatsapp", chat_key="51999111222", text="", media=[AUDIO]))

    assert reply == whatsapp_service.MENSAJE_AUDIO_ILEGIBLE
    assert recibidos == []


def test_el_historial_devuelve_el_audio_como_texto_plano():
    """Turnos pasados: el agente ve la transcripcion, sin URL ni marca; un audio mudo se omite."""
    from app.communication.services import chat_service
    audio = {"role": "user", "type": "audio_url", "content": URL_AUDIO, "transcription": "hola, soy Ana"}
    mudo = {"role": "user", "type": "audio_url", "content": URL_AUDIO, "transcription": None}

    assert chat_service._fila_para_el_agente(audio) == {"role": "user", "content": "hola, soy Ana"}
    assert chat_service._fila_para_el_agente(mudo) is None


def test_transcribir_llama_a_elevenlabs(tmp_path, monkeypatch):
    """POST multipart con la clave en xi-api-key y el modelo Scribe; devuelve el texto limpio."""
    from app.communication.services import transcription_service
    archivo = tmp_path / "nota.ogg"
    archivo.write_bytes(b"OggS")
    visto = {}

    class _Resp:
        """Respuesta HTTP simulada de ElevenLabs con una transcripcion con espacios alrededor."""
        status_code = 200
        text = ""
        def json(self):
            """Devuelve el texto transcrito simulado."""
            return {"text": "  hola mundo \n"}

    def falso_post(url, headers, data, files, timeout):
        """Anota la peticion enviada a ElevenLabs y devuelve la respuesta simulada."""
        visto.update(url=url, headers=headers, data=data, nombre=files["file"].name)
        return _Resp()

    monkeypatch.setattr(transcription_service.requests, "post", falso_post)
    assert transcription_service.transcribir(str(archivo), "clave") == "hola mundo"
    assert visto["url"] == "https://api.elevenlabs.io/v1/speech-to-text"
    assert visto["headers"] == {"xi-api-key": "clave"} and visto["data"] == {"model_id": "scribe_v1"}


def test_transcribir_sin_clave_o_sin_voz_falla(tmp_path, monkeypatch):
    """Nunca devuelve una cadena vacia: sin clave o sin voz levanta TranscriptionError."""
    from app.communication.services import transcription_service
    archivo = tmp_path / "nota.ogg"
    archivo.write_bytes(b"OggS")
    with pytest.raises(transcription_service.TranscriptionError):
        transcription_service.transcribir(str(archivo), "")

    class _Vacia:
        """Respuesta HTTP simulada de ElevenLabs cuya transcripcion queda vacia."""
        status_code = 200
        text = ""
        def json(self):
            """Devuelve una transcripcion de solo espacios."""
            return {"text": "   "}

    monkeypatch.setattr(transcription_service.requests, "post", lambda *a, **k: _Vacia())
    with pytest.raises(transcription_service.TranscriptionError):
        transcription_service.transcribir(str(archivo), "clave")
