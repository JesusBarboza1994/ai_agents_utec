"""El personal resuelve una revision humana y el cliente de WhatsApp recibe la decision; sin modelo, sin red.

Se simulan la resolucion del orquestador y el envio de Twilio: aqui se prueba que el aviso sale, que no
se filtra nada al panel, y que un fallo del envio nunca deshace la decision del personal.
"""
from dataclasses import replace

import pytest

from app import create_app
from app.communication.services import aviso_staff_service as aviso
from app.communication.services import outbound_whatsapp_service as saliente
from app.communication.services.sesiones import limpiar_sesion, obtener_sesion
from app.contratos import RespuestaClemente
from app.seguridad.guardrails_ai import ResultadoEntrada

SESION_WHATSAPP = "whatsapp-51999111222"
SESION_WEB = "web-abc123def456"
TOKEN = "token-staff"
AUTORIZACION = {"Authorization": f"Bearer {TOKEN}"}
TEXTO = "Tu solicitud quedó registrada con el código I-ABC123. La mesa todavía no está confirmada."


@pytest.fixture
def staff(monkeypatch):
    """Cliente Flask con token del personal, Twilio configurado y un envio simulado que anota lo enviado."""
    enviados = []

    def enviar_falso(sid, token, desde, para, cuerpo):
        """Anota el envio en vez de llamar a Twilio y devuelve un id de mensaje."""
        enviados.append({"sid": sid, "desde": desde, "para": para, "cuerpo": cuerpo})
        return "SM123"

    def resolver_falso(sesion_id, decision, motivo=""):
        """Resolucion simulada del orquestador: devuelve el texto de cierre para el cliente."""
        return RespuestaClemente(texto=TEXTO, agente="reservas", sesion_id=sesion_id, escalado=True)

    monkeypatch.setattr(saliente, "send_whatsapp_message", enviar_falso)
    monkeypatch.setattr("app.orquestador.grafo.resolver_revision", resolver_falso)
    app = create_app()
    app.config["TESTING"] = True
    app.config["CLEMENTE"] = replace(
        app.config["CLEMENTE"], hitl_token=TOKEN, database_url="", guardrails_url="",
        twilio_account_sid="AC123", twilio_auth_token="secreto", twilio_whatsapp_from="14155238886",
    )
    cliente = app.test_client()
    cliente.enviados = enviados
    for sesion in (SESION_WHATSAPP, SESION_WEB):
        limpiar_sesion(sesion)
    return cliente


def _resolver(cliente, sesion_id=SESION_WHATSAPP, decision="approve", cabeceras=AUTORIZACION):
    """Llama al endpoint del personal para resolver la revision de una sesion."""
    return cliente.post(
        f"/api/staff/revisiones/{sesion_id}/resolver", json={"decision": decision}, headers=cabeceras,
    )


@pytest.mark.parametrize("decision", ["approve", "reject"])
def test_resolver_en_whatsapp_envia_el_texto_al_cliente(staff, decision):
    """Aprobar o rechazar avisa al cliente por WhatsApp con el mismo texto que ve el panel."""
    respuesta = _resolver(staff, decision=decision)

    assert respuesta.status_code == 200
    datos = respuesta.get_json()
    assert datos["notificacion"] == {"canal": "whatsapp", "estado": "enviado", "motivo": ""}
    assert staff.enviados == [{
        "sid": "AC123", "desde": "14155238886", "para": "51999111222", "cuerpo": TEXTO,
    }]
    assert datos["respuesta_cliente"] == TEXTO


def test_en_el_webchat_no_se_envia_nada_y_se_explica(staff):
    """El webchat no tiene canal de salida: se resuelve, no se envia y el panel recibe el motivo."""
    respuesta = _resolver(staff, sesion_id="abc123def456")

    assert respuesta.status_code == 200
    assert respuesta.get_json()["notificacion"] == {
        "canal": "webchat", "estado": "no_aplica", "motivo": aviso.MOTIVO_WEBCHAT,
    }
    assert staff.enviados == []


def test_fuera_de_la_ventana_de_24_horas_la_decision_sigue_resuelta(staff, monkeypatch):
    """Si Twilio rechaza por la ventana de 24 horas, la revision queda resuelta y el panel lo sabe."""
    def rechazo(*args):
        """Simula el rechazo 63016 de Twilio con datos que no deben llegar al panel."""
        raise saliente.WhatsAppSendError(
            "Twilio rejected the message (400): {'code': 63016, 'to': 'whatsapp:+51999111222', 'auth': 'secreto'}"
        )

    monkeypatch.setattr(saliente, "send_whatsapp_message", rechazo)
    respuesta = _resolver(staff)

    assert respuesta.status_code == 200
    assert respuesta.get_json()["estado"] == "resuelta"
    assert respuesta.get_json()["notificacion"] == {
        "canal": "whatsapp", "estado": "no_enviado", "motivo": aviso.MOTIVO_VENTANA,
    }
    notificacion = str(respuesta.get_json()["notificacion"])
    assert "51999111222" not in notificacion and "63016" not in notificacion
    assert "secreto" not in respuesta.get_data(as_text=True)


def test_sin_credenciales_de_twilio_se_explica_sin_romper(staff, monkeypatch):
    """Sin credenciales el envio falla con un motivo claro y la decision del personal se conserva."""
    staff.application.config["CLEMENTE"] = replace(
        staff.application.config["CLEMENTE"], twilio_account_sid="", twilio_auth_token="",
    )
    monkeypatch.undo()   # usa el servicio real: debe negarse antes de abrir la red
    monkeypatch.setattr("app.orquestador.grafo.resolver_revision",
                        lambda sesion_id, decision, motivo="": RespuestaClemente(
                            texto=TEXTO, agente="reservas", sesion_id=sesion_id))
    respuesta = _resolver(staff)

    assert respuesta.status_code == 200
    assert respuesta.get_json()["notificacion"]["estado"] == "no_enviado"
    assert respuesta.get_json()["notificacion"]["motivo"] == aviso.MOTIVO_SIN_CREDENCIALES


def test_un_error_inesperado_al_enviar_no_tumba_el_endpoint(staff, monkeypatch):
    """Una excepcion cualquiera del envio se traduce en no_enviado, no en un 500."""
    def explota(*args):
        """Simula una caida de red o un fallo no previsto del cliente HTTP."""
        raise ConnectionError("sin red")

    monkeypatch.setattr(saliente, "send_whatsapp_message", explota)
    respuesta = _resolver(staff)

    assert respuesta.status_code == 200
    assert respuesta.get_json()["notificacion"] == {
        "canal": "whatsapp", "estado": "no_enviado", "motivo": aviso.MOTIVO_ERROR,
    }


def test_el_aviso_pasa_por_la_redaccion_de_salida_del_chat(staff, monkeypatch):
    """El cuerpo enviado tapa el correo y deja visible el telefono, igual que cualquier respuesta del chat."""
    monkeypatch.setattr(
        "app.orquestador.grafo.resolver_revision",
        lambda sesion_id, decision, motivo="": RespuestaClemente(
            texto="Anotado para 900000001. Te escribimos a ana@correo.com.", agente="reservas", sesion_id=sesion_id),
    )
    _resolver(staff)

    cuerpo = staff.enviados[0]["cuerpo"]
    assert "ana@correo.com" not in cuerpo
    assert "900000001" in cuerpo


def test_si_la_salida_se_bloquea_se_envia_el_texto_neutro(staff, monkeypatch):
    """Si el control de salida rechaza el texto, al cliente le llega el aviso neutro y no el original."""
    monkeypatch.setattr(aviso, "validar_salida",
                        lambda texto, sesion_id, config: ResultadoEntrada(False, texto, "toxico"))
    _resolver(staff)

    assert staff.enviados[0]["cuerpo"] == aviso.TEXTO_SALIDA_BLOQUEADA


def test_sin_token_no_se_resuelve_ni_se_envia(staff):
    """Sin la credencial del personal no hay resolucion ni aviso."""
    respuesta = _resolver(staff, cabeceras={})

    assert respuesta.status_code == 401
    assert staff.enviados == []


def test_una_revision_inexistente_no_envia_nada(staff, monkeypatch):
    """Si no hay revision pendiente para esa sesion (404), tampoco se avisa a nadie."""
    def sin_revision(sesion_id, decision, motivo=""):
        """Simula la cola vacia: el orquestador no encuentra la revision."""
        raise KeyError("No existe una revisión pendiente para esa sesión")

    monkeypatch.setattr("app.orquestador.grafo.resolver_revision", sin_revision)
    respuesta = _resolver(staff)

    assert respuesta.status_code == 404
    assert staff.enviados == []


def test_el_aviso_enviado_se_guarda_redactado_en_el_historial(staff, monkeypatch):
    """Con base configurada, el aviso queda como turno del asistente, redactado, para el siguiente mensaje."""
    guardados = []
    staff.application.config["CLEMENTE"] = replace(staff.application.config["CLEMENTE"], database_url="postgresql://x")
    monkeypatch.setattr(aviso.customers_repository, "get_or_create_customer", lambda chat_key, **kw: "cliente-1")
    monkeypatch.setattr(aviso.chats_repository, "get_or_create_chat", lambda chat_key, cid, **kw: "chat-1")
    monkeypatch.setattr(aviso.chats_repository, "touch", lambda chat_id: guardados.append(("touch", chat_id)))
    monkeypatch.setattr(aviso.messages_repository, "append_message",
                        lambda chat_id, rol, texto, **kw: guardados.append((chat_id, rol, texto)))
    monkeypatch.setattr(
        "app.orquestador.grafo.resolver_revision",
        lambda sesion_id, decision, motivo="": RespuestaClemente(
            texto="Listo, escribe a ana@correo.com", agente="reservas", sesion_id=sesion_id),
    )
    _resolver(staff)

    assert ("chat-1", "assistant", "Listo, escribe a [REDACTED_EMAIL]") in guardados
    assert ("touch", "chat-1") in guardados


def test_un_fallo_al_guardar_el_historial_no_afecta_al_aviso(staff, monkeypatch):
    """Si la base falla al guardar, el aviso ya salio y el endpoint responde igual."""
    def base_caida(*args, **kwargs):
        """Simula una caida de Postgres al abrir el cliente."""
        raise RuntimeError("base caida")

    staff.application.config["CLEMENTE"] = replace(staff.application.config["CLEMENTE"], database_url="postgresql://x")
    monkeypatch.setattr(aviso.customers_repository, "get_or_create_customer", base_caida)
    respuesta = _resolver(staff)

    assert respuesta.status_code == 200
    assert respuesta.get_json()["notificacion"]["estado"] == "enviado"
    assert len(staff.enviados) == 1


def test_sin_base_no_se_toca_el_historial(staff, monkeypatch):
    """Sin base configurada el aviso sale y no se toca Postgres (el hilo en memoria es otra cosa)."""
    def no_debe_llamarse(*args, **kwargs):
        """Falla la prueba si el servicio intenta escribir en la base sin tenerla configurada."""
        raise AssertionError("no debia tocar la base")

    monkeypatch.setattr(aviso.customers_repository, "get_or_create_customer", no_debe_llamarse)
    respuesta = _resolver(staff)

    assert respuesta.get_json()["notificacion"]["estado"] == "enviado"


# --- el cliente tiene que enterarse de la decision al escribir de nuevo ---------------------------

def test_el_webchat_guarda_la_decision_en_el_hilo_para_el_siguiente_mensaje(staff):
    """El webchat no tiene envio, pero la decision queda como turno del asistente: al escribir de nuevo, el agente la sabe."""
    _resolver(staff, sesion_id=SESION_WEB, decision="reject")

    assert obtener_sesion(SESION_WEB, "webchat").historial[-1] == {"role": "assistant", "content": TEXTO}


def test_si_el_envio_falla_la_decision_igual_queda_en_el_hilo(staff, monkeypatch):
    """Fuera de la ventana de 24 horas el cliente no recibe el aviso, pero su siguiente mensaje ya encuentra la decision."""
    def rechazo(*args):
        """Simula el rechazo 63016 de Twilio por la ventana de 24 horas."""
        raise saliente.WhatsAppSendError("Twilio rejected the message (400): {'code': 63016}")

    monkeypatch.setattr(saliente, "send_whatsapp_message", rechazo)
    _resolver(staff, decision="reject")

    assert obtener_sesion(SESION_WHATSAPP, "whatsapp").historial[-1] == {"role": "assistant", "content": TEXTO}


def test_sin_base_el_aviso_enviado_tambien_queda_en_el_hilo_en_memoria(staff):
    """Sin Postgres el chat lee el hilo de la memoria: la decision tiene que estar ahi, aunque el aviso haya salido."""
    _resolver(staff)

    assert obtener_sesion(SESION_WHATSAPP, "whatsapp").historial[-1] == {"role": "assistant", "content": TEXTO}


def test_el_hilo_guarda_la_decision_redactada(staff, monkeypatch):
    """Lo que queda en el hilo va sin correo ni telefono, igual que lo que se guarda en Postgres."""
    monkeypatch.setattr(
        "app.orquestador.grafo.resolver_revision",
        lambda sesion_id, decision, motivo="": RespuestaClemente(
            texto="Escribe a ana@correo.com o llama al 900000001.", agente="reservas", sesion_id=sesion_id),
    )
    _resolver(staff, sesion_id=SESION_WEB)

    contenido = obtener_sesion(SESION_WEB, "webchat").historial[-1]["content"]
    assert "ana@correo.com" not in contenido and "900000001" not in contenido


def test_con_base_el_webchat_guarda_la_decision_en_su_chat(staff, monkeypatch):
    """Con Postgres, la decision del webchat entra al chat del navegador (chat_key = sesion_id, canal webchat)."""
    guardados, canales = [], []
    staff.application.config["CLEMENTE"] = replace(staff.application.config["CLEMENTE"], database_url="postgresql://x")
    monkeypatch.setattr(aviso.customers_repository, "get_or_create_customer", lambda chat_key, **kw: f"cliente-{chat_key}")

    def abrir_chat(chat_key, cliente_id, **kw):
        """Anota el canal con el que se abre el chat y devuelve su id."""
        canales.append((chat_key, kw.get("channel")))
        return "chat-1"

    monkeypatch.setattr(aviso.chats_repository, "get_or_create_chat", abrir_chat)
    monkeypatch.setattr(aviso.chats_repository, "touch", lambda chat_id: None)
    monkeypatch.setattr(aviso.messages_repository, "append_message",
                        lambda chat_id, rol, texto, **kw: guardados.append((chat_id, rol, texto)))
    _resolver(staff, sesion_id=SESION_WEB, decision="reject")

    assert canales == [(SESION_WEB, "webchat")]
    assert guardados == [("chat-1", "assistant", TEXTO)]
    assert staff.enviados == []


def test_con_base_y_envio_fallido_la_decision_se_guarda_igual(staff, monkeypatch):
    """Si Twilio rechaza el envio, la decision igual entra a messages para el siguiente mensaje del cliente."""
    guardados = []
    staff.application.config["CLEMENTE"] = replace(staff.application.config["CLEMENTE"], database_url="postgresql://x")
    monkeypatch.setattr(aviso.customers_repository, "get_or_create_customer", lambda chat_key, **kw: "cliente-1")
    monkeypatch.setattr(aviso.chats_repository, "get_or_create_chat", lambda chat_key, cid, **kw: "chat-1")
    monkeypatch.setattr(aviso.chats_repository, "touch", lambda chat_id: None)
    monkeypatch.setattr(aviso.messages_repository, "append_message",
                        lambda chat_id, rol, texto, **kw: guardados.append((chat_id, rol, texto)))
    monkeypatch.setattr(saliente, "send_whatsapp_message",
                        lambda *a: (_ for _ in ()).throw(saliente.WhatsAppSendError("code 63016")))
    _resolver(staff, decision="reject")

    assert guardados == [("chat-1", "assistant", TEXTO)]
