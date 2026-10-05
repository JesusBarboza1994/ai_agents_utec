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
        self.contenido, self.status_code = contenido, status_code

    def iter_content(self, _tamano):
        yield self.contenido

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False


class _Subida:
    """Respuesta falsa de la API de subida de Cloudinary."""

    def __init__(self, status_code=200, secure_url=URL_CLOUDINARY):
        self.status_code, self.text = status_code, "rechazado"
        self._json = {"secure_url": secure_url}

    def json(self):
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


def test_parse_inbound_audio_solo_sigue_sin_soporte():
    """Audio sin texto sigue sin manejarse, como antes."""
    message = parse_inbound({
        "From": "whatsapp:+51999111222", "NumMedia": "1",
        "MediaUrl0": URL_TWILIO, "MediaContentType0": "audio/ogg",
    })
    assert message.unsupported_reason == "media sin manejar (audio/ogg)"


# --- descarga de Twilio ----------------------------------------------------

def test_descarga_con_credenciales_de_twilio(monkeypatch, tmp_path):
    """La descarga usa Account SID + Auth Token y deja el archivo en el temporal."""
    pedido = {}

    def falso_get(url, **kwargs):
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
        if url.endswith("falla"):
            return _Descarga(status_code=404)
        return _Descarga()

    def falso_post(url, data, files, timeout):
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
        def invoke(self, estado):
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
        def invoke(self, entrada, config=None, context=None):
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
        def with_structured_output(self, _esquema):
            return self

        def invoke(self, mensajes):
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
