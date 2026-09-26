"""El cliente ve su propio telefono en la respuesta, pero lo que se guarda sigue redactado; sin modelo ni base de datos."""
import pytest

from app import create_app
from app.communication.services import chat_service
from app.contratos import MensajeEntrante, RespuestaClemente
from app.communication.services.sesiones import obtener_sesion

RESUMEN = "Crear reserva: Ana Ruiz, sabado 2026-10-10 a las 20:00 (hora de Lima), 2 personas, contacto 977666555. Escribe CONFIRMO 1A2B3C4D."


@pytest.fixture
def contexto_de_app(monkeypatch):
    """Una app de prueba sin Guardrails externo y con un orquestador que devuelve el resumen de una reserva."""
    monkeypatch.setenv("CLEMENTE_GUARDRAILS_URL", "")

    def orquestador(entrante, historial=None, cliente=None, chat_key=None):
        """Responde con un resumen que trae el telefono y un correo, como haria el agente de reservas."""
        return RespuestaClemente(texto=f"{RESUMEN} Aviso a ana@correo.com.", agente="reservas", sesion_id=entrante.sesion_id)

    monkeypatch.setattr(chat_service, "responder_orquestador", orquestador)
    with create_app().app_context():
        yield


def test_el_cliente_ve_su_telefono_pero_no_el_correo(contexto_de_app, monkeypatch):
    """En la respuesta el telefono se muestra (el cliente lo comprueba); el correo sigue tapado."""
    monkeypatch.setattr(chat_service, "_abrir_chat", lambda *a, **k: None)
    respuesta = chat_service.handle_incoming_message(MensajeEntrante(sesion_id="web-tel-1", texto="quiero reservar", canal="webchat"))
    assert "contacto 977666555" in respuesta.texto and "REDACTED_TELEFONO" not in respuesta.texto
    assert "ana@correo.com" not in respuesta.texto and "[REDACTED_EMAIL]" in respuesta.texto


def test_lo_que_se_guarda_en_la_base_sigue_sin_telefono(contexto_de_app, monkeypatch):
    """Con base de datos, el turno de Clemente se guarda con el telefono tapado aunque el cliente lo haya visto."""
    guardados = []
    monkeypatch.setattr(chat_service, "_abrir_chat", lambda *a, **k: "chat-1")
    monkeypatch.setattr(chat_service, "_historial", lambda *a, **k: [])
    monkeypatch.setattr(chat_service, "_ficha_del_cliente", lambda *a, **k: {})
    monkeypatch.setattr(chat_service, "_guardar", lambda chat_id, sesion_id, rol, texto, **k: guardados.append((rol, texto)))
    respuesta = chat_service.handle_incoming_message(MensajeEntrante(sesion_id="web-tel-2", texto="quiero reservar", canal="webchat"))
    assert "977666555" in respuesta.texto
    guardado = dict(guardados)["assistant"]
    assert "977666555" not in guardado and "[REDACTED_TELEFONO]" in guardado


def test_la_memoria_del_proceso_tampoco_conserva_el_telefono(contexto_de_app, monkeypatch):
    """Sin base de datos, el historial que se reinyecta al modelo en el turno siguiente tampoco trae el numero."""
    monkeypatch.setattr(chat_service, "_abrir_chat", lambda *a, **k: None)
    chat_service.handle_incoming_message(MensajeEntrante(sesion_id="web-tel-3", texto="quiero reservar", canal="webchat"))
    ultimo = obtener_sesion("web-tel-3").historial[-1]
    assert ultimo["role"] == "assistant" and "977666555" not in ultimo["content"]
