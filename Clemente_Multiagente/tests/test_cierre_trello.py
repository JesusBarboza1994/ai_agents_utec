"""El personal mueve una tarjeta a "Resuelto" en Trello y el cliente de WhatsApp recibe el aviso; sin red ni modelo.

Se simulan las llamadas firmadas de Trello y el envio de Twilio: aqui se prueba que solo se acepta una llamada
firmada, que solo cuenta el paso a la lista Resuelto, que cada caso se avisa una sola vez y que un fallo del envio
no rompe nada ni se da por avisado.
"""
import base64
import hashlib
import hmac
import json
from dataclasses import replace

import pytest

from app import create_app
from app.communication.services import bandeja_webchat as bandeja
from app.communication.services import cierre_trello_service as cierre
from app.communication.services import outbound_whatsapp_service as saliente
from app.incidencias.servicio_json import ServicioIncidenciasJSON

SECRETO = "secreto-de-prueba"
URL = "https://clemente.ejemplo/api/webhook/trello"
SESION = "whatsapp-51999111222"
CODIGO_GRUPO = "G-ABC123"


@pytest.fixture
def trello(monkeypatch, tmp_path):
    """Cliente Flask con el secreto de Trello y Twilio configurados, y un envio simulado que anota lo enviado."""
    enviados = []

    def enviar_falso(sid, token, desde, para, cuerpo):
        """Anota el envio en vez de llamar a Twilio y devuelve un id de mensaje."""
        enviados.append({"para": para, "cuerpo": cuerpo})
        return "SM123"

    monkeypatch.setattr(saliente, "send_whatsapp_message", enviar_falso)
    monkeypatch.setattr(cierre, "ARCHIVO_AVISOS", tmp_path / "avisos_cierre.json")
    monkeypatch.setattr(bandeja, "ARCHIVO", tmp_path / "bandeja_webchat.json")
    app = create_app()
    app.config["TESTING"] = True
    app.config["CLEMENTE"] = replace(
        app.config["CLEMENTE"], trello_secret=SECRETO, trello_webhook_url=URL, database_url="", guardrails_url="",
        twilio_account_sid="AC123", twilio_auth_token="secreto", twilio_whatsapp_from="14155238886",
    )
    cliente = app.test_client()
    cliente.enviados = enviados
    return cliente


def _firmar(cuerpo: bytes, secreto: str = SECRETO) -> str:
    """Firma como Trello: base64 del HMAC-SHA1 del cuerpo mas la URL registrada."""
    return base64.b64encode(hmac.new(secreto.encode(), cuerpo + URL.encode(), hashlib.sha1).digest()).decode()


def _carga(codigo, antes="En atención", despues="Resuelto", tipo="updateCard", titulo=None):
    """Llamada de Trello que mueve la tarjeta de un caso de una lista a otra."""
    nombre = titulo if titulo is not None else f"{codigo} · reserva · grupo de 9"
    datos = {"card": {"id": "c1", "name": nombre}, "listAfter": {"name": despues}}
    if antes:
        datos["listBefore"] = {"name": antes}
    return {"action": {"type": tipo, "data": datos}}


def _post(cliente, carga, firma=True):
    """Envia la llamada al webhook, firmada como Trello o sin firma."""
    cuerpo = json.dumps(carga).encode()
    cabeceras = {"Content-Type": "application/json"}
    if firma:
        cabeceras["X-Trello-Webhook"] = _firmar(cuerpo)
    return cliente.post("/api/webhook/trello", data=cuerpo, headers=cabeceras)


def _caso(sesion=SESION, codigo=None):
    """Registra un caso abierto de esa sesion y devuelve su codigo."""
    return ServicioIncidenciasJSON().crear_incidencia(sesion, "espera de 40 minutos", "espera", codigo=codigo).id


# --- la llamada -------------------------------------------------------------------------

def test_trello_comprueba_la_url_con_un_head(trello):
    """Al registrar el webhook Trello hace un HEAD: la URL tiene que responder 200."""
    assert trello.head("/api/webhook/trello").status_code == 200


def test_sin_firma_no_se_acepta_la_llamada(trello):
    """Una llamada sin la cabecera de firma se rechaza y no avisa a nadie."""
    respuesta = _post(trello, _carga(_caso()), firma=False)

    assert respuesta.status_code == 401
    assert trello.enviados == []


def test_una_firma_de_otro_secreto_no_se_acepta(trello):
    """Una firma calculada con otro secreto no pasa."""
    carga = json.dumps(_carga(_caso())).encode()
    respuesta = trello.post("/api/webhook/trello", data=carga, headers={
        "X-Trello-Webhook": _firmar(carga, "otro-secreto"), "Content-Type": "application/json"})

    assert respuesta.status_code == 401
    assert trello.enviados == []


def test_sin_secreto_configurado_no_se_acepta_ninguna_llamada(trello):
    """Sin TRELLO_SECRET el webhook falla cerrado: ni siquiera una firma calculada con secreto vacio entra."""
    trello.application.config["CLEMENTE"] = replace(trello.application.config["CLEMENTE"], trello_secret="")
    carga = json.dumps(_carga(_caso())).encode()
    respuesta = trello.post("/api/webhook/trello", data=carga, headers={
        "X-Trello-Webhook": _firmar(carga, ""), "Content-Type": "application/json"})

    assert respuesta.status_code == 401
    assert trello.enviados == []


@pytest.mark.parametrize("secreto, url, firma, esperado", [
    (SECRETO, URL, "", False), (SECRETO, "", "x", False), ("", URL, "x", False),
])
def test_firma_valida_exige_secreto_url_y_firma(secreto, url, firma, esperado):
    """Falta cualquiera de los tres datos y la firma no es valida."""
    assert cierre.firma_valida(b"{}", url, firma, secreto) is esperado


# --- que cuenta como cierre ----------------------------------------------------------------

@pytest.mark.parametrize("codigo", [None, CODIGO_GRUPO])
def test_mover_a_resuelto_avisa_al_cliente_por_whatsapp(trello, codigo):
    """Una tarjeta que pasa a Resuelto envia al cliente su codigo (I- o G-) y queda anotada como avisada."""
    caso = _caso(codigo=codigo)

    respuesta = _post(trello, _carga(caso))

    assert respuesta.status_code == 200
    assert respuesta.get_json() == {"codigo": caso, "estado": "enviado", "motivo": ""}
    assert trello.enviados == [{"para": "51999111222", "cuerpo": cierre.TEXTO_CIERRE.format(codigo=caso)}]
    assert caso in json.loads(cierre.ARCHIVO_AVISOS.read_text(encoding="utf-8"))


def test_la_lista_se_reconoce_sin_importar_mayusculas_ni_espacios(trello):
    """'  RESUELTO ' cuenta igual que 'Resuelto'."""
    _post(trello, _carga(_caso(), despues="  RESUELTO "))

    assert len(trello.enviados) == 1


def test_un_caso_se_avisa_una_sola_vez(trello):
    """Un reintento de Trello o mover la tarjeta de ida y vuelta no repiten el mensaje."""
    caso = _caso()

    _post(trello, _carga(caso))
    _post(trello, _carga(caso, antes="Resuelto", despues="En atención"))
    segunda = _post(trello, _carga(caso))

    assert segunda.get_json()["estado"] == "ya_avisado"
    assert len(trello.enviados) == 1


@pytest.mark.parametrize("carga", [
    _carga("I-ABC123", despues="En atención"),
    _carga("I-ABC123", antes=None),
    _carga("I-ABC123", tipo="commentCard"),
    _carga("I-ABC123", titulo="Una tarjeta cualquiera"),
    _carga("I-ABC123", titulo="X-ABC123 · reserva · no es un codigo"),
])
def test_lo_que_no_es_un_cierre_no_avisa(trello, carga):
    """Otra lista, una tarjeta nueva sin lista anterior, otra accion o un titulo sin codigo valido se ignoran."""
    respuesta = _post(trello, carga)

    assert respuesta.status_code == 200
    assert respuesta.get_json()["estado"] == "ignorado"
    assert trello.enviados == []


def test_un_codigo_que_no_existe_no_avisa(trello):
    """Una tarjeta con un codigo valido pero sin caso registrado no manda nada."""
    respuesta = _post(trello, _carga("I-FFFFFF"))

    assert respuesta.get_json() == {"estado": "ignorado", "motivo": "caso desconocido", "codigo": "I-FFFFFF"}
    assert trello.enviados == []


def test_un_caso_del_webchat_queda_en_la_bandeja_del_chat(trello):
    """Un caso del webchat no sale por Twilio: el aviso queda en la bandeja de su navegador y el caso se anota avisado."""
    caso = _caso(sesion="web-abc123def456", codigo=CODIGO_GRUPO)

    respuesta = _post(trello, _carga(caso))

    assert respuesta.get_json() == {"codigo": caso, "estado": "enviado", "motivo": ""}
    assert trello.enviados == []
    assert [m["texto"] for m in bandeja.recoger("web-abc123def456")] == [cierre.TEXTO_CIERRE.format(codigo=caso)]
    assert caso in json.loads(cierre.ARCHIVO_AVISOS.read_text(encoding="utf-8"))


def test_un_caso_del_webchat_se_avisa_una_sola_vez(trello):
    """Mover la tarjeta de ida y vuelta no deja un segundo mensaje en la bandeja."""
    caso = _caso(sesion="web-abc123def456")

    _post(trello, _carga(caso))
    _post(trello, _carga(caso, antes="Resuelto", despues="En atención"))
    segunda = _post(trello, _carga(caso))

    assert segunda.get_json()["estado"] == "ya_avisado"
    assert len(bandeja.recoger("web-abc123def456")) == 1


def test_un_cuerpo_que_no_es_un_objeto_se_ignora(trello):
    """Un cuerpo firmado pero sin la forma esperada no rompe el webhook."""
    cuerpo = b"[]"
    respuesta = trello.post("/api/webhook/trello", data=cuerpo, headers={
        "X-Trello-Webhook": _firmar(cuerpo), "Content-Type": "application/json"})

    assert respuesta.status_code == 200
    assert trello.enviados == []


# --- cuando el envio falla -------------------------------------------------------------------

def test_si_el_envio_falla_no_se_da_por_avisado_y_se_puede_reintentar(trello, monkeypatch):
    """Un rechazo de Twilio responde 200 con el motivo, no deja el caso como avisado y el siguiente intento envia."""
    caso = _caso()

    def rechazo(*args):
        """Simula que WhatsApp rechaza el mensaje por la ventana de 24 horas."""
        raise saliente.WhatsAppSendError("Twilio rejected the message (400): {'code': 63016}")

    monkeypatch.setattr(saliente, "send_whatsapp_message", rechazo)
    primera = _post(trello, _carga(caso))
    assert primera.status_code == 200
    assert primera.get_json()["estado"] == "no_enviado"
    assert "24 horas" in primera.get_json()["motivo"]
    assert not cierre.ARCHIVO_AVISOS.exists()

    monkeypatch.setattr(saliente, "send_whatsapp_message", lambda *a: "SM999")
    segunda = _post(trello, _carga(caso))

    assert segunda.get_json()["estado"] == "enviado"


def test_un_error_inesperado_no_tumba_el_webhook(trello, monkeypatch):
    """Una excepcion al avisar se traduce en 200 con estado error: Trello no debe reintentar sin parar."""
    def explota(carga):
        """Simula un fallo no previsto dentro del servicio."""
        raise RuntimeError("fallo inesperado")

    monkeypatch.setattr(cierre, "avisar_cierre", explota)
    respuesta = _post(trello, _carga(_caso()))

    assert respuesta.status_code == 200
    assert respuesta.get_json() == {"estado": "error"}
