"""Cuando el personal rechaza una solicitud de grupo, el agente recibe un mensaje que dice QUIEN rechazo; sin modelo.

Sin motivo, LangChain le entregaba al modelo un "User rejected the tool call..." generico, y el modelo lo leia como si
el cliente hubiera dicho que no: ofrecia "dejarles tu solicitud" de nuevo y, al siguiente mensaje, volvia a pedir la
excepcion. Medido con el modelo real: 3 de 3 rechazos sin motivo terminaban asi.
"""
import pytest

from app.agentes.contexto import ContextoConversacion
from app.incidencias.servicio_json import ServicioIncidenciasJSON
from app.orquestador import grafo


@pytest.fixture
def decision_enviada(tmp_path, monkeypatch):
    """Revision pendiente de un grupo y un agente simulado que anota la decision con que se le reanuda."""
    from app.agentes import reservas

    anotadas = []
    monkeypatch.setattr(grafo, "servicio_incidencias", lambda: ServicioIncidenciasJSON(archivo=tmp_path / "i.json"))
    grafo._revisiones["t-rechazo"] = {
        "sesion_id": "t-rechazo", "contexto": ContextoConversacion(sesion_id="t-rechazo"),
        "solicitud": {}, "canal": "webchat",
    }

    def reanudar(_sid, decision, _contexto):
        """Anota la decision recibida y devuelve el texto que daria el agente."""
        anotadas.append(decision)
        return "El equipo no pudo aprobar la solicitud."

    monkeypatch.setattr(reservas, "resolver_revision", reanudar)
    yield anotadas
    grafo._revisiones.pop("t-rechazo", None)


def test_rechazar_sin_motivo_dice_que_lo_rechazo_el_equipo(decision_enviada):
    """Aun sin motivo, el agente sabe que rechazo el personal, que debe decirselo al cliente y que no repita la solicitud."""
    grafo.resolver_revision("t-rechazo", "reject", "")

    decision = decision_enviada[0]
    assert decision["type"] == "reject"
    assert grafo.MENSAJE_RECHAZO_DEL_PERSONAL in decision["message"]
    assert "NO aprobo" in decision["message"] and "No vuelvas a pedir la excepcion" in decision["message"]


def test_rechazar_con_motivo_lo_agrega_al_mensaje(decision_enviada):
    """El motivo del personal viaja junto al mensaje que dice quien rechazo."""
    grafo.resolver_revision("t-rechazo", "reject", "Ese dia hay evento privado")

    mensaje = decision_enviada[0]["message"]
    assert grafo.MENSAJE_RECHAZO_DEL_PERSONAL in mensaje and "Ese dia hay evento privado" in mensaje


def test_aprobar_no_cambia(decision_enviada):
    """Aprobar sigue enviando solo el tipo y, si hay, el motivo tal cual."""
    grafo._revisiones["t-rechazo"]["contexto"].datos.clear()
    grafo.resolver_revision("t-rechazo", "approve", "capacidad coordinada")

    assert decision_enviada == [{"type": "approve", "message": "capacidad coordinada"}]
