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


# --- lo que hizo el equipo, escrito para el cliente ------------------------------------------------------------

class _RespuestaTrello:
    """Respuesta simulada de la API de Trello con los comentarios de la tarjeta."""

    def __init__(self, comentarios):
        """Guarda los comentarios, del mas reciente al mas antiguo, como los da Trello."""
        self.comentarios = comentarios

    def raise_for_status(self):
        """La llamada salio bien."""

    def json(self):
        """Los comentarios con la forma de la API de Trello."""
        return [{"type": "commentCard", "data": {"text": t}} for t in self.comentarios]


@pytest.fixture
def comentarios(monkeypatch):
    """Credenciales de Trello y comentarios simulados de la tarjeta; anota que tarjeta se consulto."""
    estado = {"comentarios": [], "tarjetas": []}

    def get_falso(url, params=None, timeout=None):
        """Devuelve los comentarios configurados en vez de llamar a Trello."""
        estado["tarjetas"].append(url.split("/cards/")[1].split("/")[0])
        assert params["filter"] == "commentCard"
        return _RespuestaTrello(estado["comentarios"])

    monkeypatch.setenv("TRELLO_API_KEY", "clave")
    monkeypatch.setenv("TRELLO_TOKEN", "token")
    monkeypatch.setattr(cierre.requests, "get", get_falso)
    return estado


def _caso_de(tipo, descripcion):
    """Registra un caso de ese tipo para la sesion de la prueba y devuelve su codigo."""
    return ServicioIncidenciasJSON().crear_incidencia(SESION, descripcion, tipo).id


def test_un_reclamo_cuenta_de_que_se_trataba_y_lo_que_hizo_el_equipo(trello, comentarios):
    """El cliente lee su reclamo en una frase y la resolucion que el equipo escribio para el."""
    caso = _caso_de("producto", "El plato llegó frío")
    comentarios["comentarios"] = ["Para el cliente: te dejamos un postre de cortesía en tu próxima visita."]
    _post(trello, _carga(caso, titulo=f"{caso} · producto · El plato llegó frío"))
    assert trello.enviados[0]["cuerpo"] == (f"¡Listo! Revisamos tu caso {caso} (El plato llegó frío). Lo que hicimos: "
                                            "te dejamos un postre de cortesía en tu próxima visita. Gracias por avisarnos ✅")
    assert comentarios["tarjetas"] == ["c1"]


def test_un_pedido_de_hablar_con_una_persona_pregunta_si_quedo_resuelto(trello, comentarios):
    """En un pedido de atencion, despues de la resolucion se le pregunta si falta algo."""
    caso = _caso_de("otro", "[escalado desde orquestador] pide una persona\nMensaje del cliente: hola")
    comentarios["comentarios"] = ["para el cliente:   te llamamos al número que dejaste"]
    _post(trello, _carga(caso, titulo=f"{caso} · otro · pide una persona"))
    assert trello.enviados[0]["cuerpo"] == cierre.CIERRE_PEDIDO_DE_PERSONA.format(
        codigo=caso, resolucion="te llamamos al número que dejaste")


def test_un_grupo_con_resolucion_usa_el_texto_general(trello, comentarios):
    """Un caso de otro tipo con resolucion escrita la incluye en el aviso general."""
    caso = _caso_de("reserva", "[escalado desde reservas_hitl] grupo de 12")
    comentarios["comentarios"] = ["Para el cliente: los esperamos el sábado con dos mesas juntas en el salón"]
    _post(trello, _carga(caso))
    assert trello.enviados[0]["cuerpo"] == cierre.CIERRE_CON_RESOLUCION.format(
        codigo=caso, resolucion="los esperamos el sábado con dos mesas juntas en el salón")


def test_las_notas_internas_nunca_salen(trello, comentarios):
    """Sin un comentario "Para el cliente:" se manda el aviso generico, aunque haya otras notas."""
    caso = _caso_de("producto", "El plato llegó frío")
    comentarios["comentarios"] = ["El cocinero dice que fue el horno", "[dato nuevo del cliente] mesa 4"]
    _post(trello, _carga(caso))
    assert trello.enviados[0]["cuerpo"] == cierre.TEXTO_CIERRE.format(codigo=caso)


def test_cuenta_el_comentario_para_el_cliente_mas_reciente(trello, comentarios):
    """Si el equipo corrigio la resolucion, sale la ultima que escribio."""
    caso = _caso_de("otro", "[escalado desde orquestador] pide una persona")
    comentarios["comentarios"] = ["Para el cliente: te llamamos hoy", "nota interna", "Para el cliente: te llamamos mañana"]
    _post(trello, _carga(caso))
    assert "te llamamos hoy" in trello.enviados[0]["cuerpo"] and "mañana" not in trello.enviados[0]["cuerpo"]


def test_si_trello_no_responde_se_avisa_igual_con_el_texto_generico(trello, monkeypatch):
    """Que no se pueda leer la resolucion no impide avisar que el caso se cerro."""
    monkeypatch.setenv("TRELLO_API_KEY", "clave")
    monkeypatch.setenv("TRELLO_TOKEN", "token")

    def falla(*args, **kwargs):
        """Trello no responde."""
        raise cierre.requests.ConnectionError("sin red")

    monkeypatch.setattr(cierre.requests, "get", falla)
    caso = _caso_de("producto", "El plato llegó frío")
    _post(trello, _carga(caso))
    assert trello.enviados[0]["cuerpo"] == cierre.TEXTO_CIERRE.format(codigo=caso)


def test_una_resolucion_larga_se_corta_y_el_resumen_tambien():
    """Ni la resolucion ni el resumen del reclamo convierten el aviso en un texto interminable."""
    larga = "a " * 600
    caso = ServicioIncidenciasJSON().crear_incidencia(SESION, "palabra " * 40, "espera")
    texto = cierre.texto_de_cierre(caso, caso.id, larga.strip()[:cierre.LARGO_MAXIMO_RESOLUCION])
    assert len(texto) < 600 and "…" in texto


def test_el_aviso_del_cierre_pasa_por_la_validacion_de_salida(trello, comentarios, monkeypatch):
    """Lo que escribe una persona pasa por los mismos controles de salida que cualquier respuesta."""
    from app.communication.services import aviso_staff_service

    revisados = []
    original = aviso_staff_service.avisar_decision
    monkeypatch.setattr(aviso_staff_service, "avisar_decision",
                        lambda sesion, texto: revisados.append(texto) or original(sesion, texto))
    caso = _caso_de("producto", "El plato llegó frío")
    comentarios["comentarios"] = ["Para el cliente: escríbenos a gerencia@clemente.demo"]
    _post(trello, _carga(caso))
    assert revisados and "gerencia@clemente.demo" not in trello.enviados[0]["cuerpo"]
