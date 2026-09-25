"""Un cliente cuya solicitud espera al staff puede seguir escribiendo sin romper el agente; sin modelo."""
from types import SimpleNamespace

from app.agentes import base
from app.agentes.base import AVISO_REVISION_PENDIENTE, ejecutar


class AgenteFalso:
    """Agente minimo: dice si su hilo esta en pausa y cuenta cuantas veces lo invocaron."""

    def __init__(self, en_pausa, con_checkpoint=True):
        """Guarda si el hilo esta detenido esperando al staff y si hay checkpoint."""
        self.checkpointer = object() if con_checkpoint else None
        self.en_pausa = en_pausa
        self.invocaciones = 0

    def get_state(self, config):
        """Como LangGraph: `next` trae los nodos pendientes cuando el hilo esta pausado."""
        return SimpleNamespace(next=("tools",) if self.en_pausa else ())

    def invoke(self, entrada, config=None, context=None):
        """Responde algo fijo, anota que se llamo al modelo y con que configuracion."""
        self.invocaciones += 1
        self.config = config
        return {"messages": [SimpleNamespace(content="Hola, te ayudo.", type="ai")]}


def test_con_la_revision_pendiente_no_se_invoca_al_modelo():
    """Un mensaje nuevo con el hilo pausado recibe el aviso y no llega al modelo: OpenAI rechazaba ese hilo con un 400."""
    agente = AgenteFalso(en_pausa=True)
    assert ejecutar(agente, "¿cuánto tardan?", "web-1") == AVISO_REVISION_PENDIENTE
    assert agente.invocaciones == 0


def test_el_limite_de_pasos_alcanza_para_seis_vueltas_de_herramientas():
    """Cada vuelta modelo-herramientas cuesta 7 pasos y el turno 2 mas: con 30 un camino normal de 5 vueltas se cortaba."""
    assert base.LIMITE_DE_PASOS >= 7 * 6 + 2


def test_el_turno_se_invoca_con_ese_limite_de_pasos():
    """ejecutar() pasa LIMITE_DE_PASOS a LangGraph, no un numero suelto."""
    agente = AgenteFalso(en_pausa=False)
    ejecutar(agente, "hola", "web-1")
    assert agente.config["recursion_limit"] == base.LIMITE_DE_PASOS


def test_sin_pausa_el_turno_sigue_su_camino():
    """Un hilo que no esta pausado invoca al agente como siempre."""
    agente = AgenteFalso(en_pausa=False)
    assert ejecutar(agente, "hola", "web-1") == "Hola, te ayudo."
    assert agente.invocaciones == 1


def test_sin_checkpoint_no_se_consulta_la_pausa():
    """Un agente sin checkpoint (como los tests o el agente de informacion) nunca se considera pausado."""
    agente = AgenteFalso(en_pausa=True, con_checkpoint=False)
    assert ejecutar(agente, "hola", "web-1") == "Hola, te ayudo."
    assert agente.invocaciones == 1


def test_si_falla_leer_el_estado_el_turno_sigue():
    """Un error al consultar el estado del hilo no le quita la respuesta al cliente."""
    agente = AgenteFalso(en_pausa=False)

    def get_state_roto(config):
        """Simula una base de checkpoints caida."""
        raise RuntimeError("checkpoint no disponible")

    agente.get_state = get_state_roto
    assert ejecutar(agente, "hola", "web-1") == "Hola, te ayudo."


def test_el_aviso_deja_una_traza_para_el_staff():
    """El mensaje que llega durante la pausa queda registrado para poder verlo despues."""
    from app.observabilidad import trazas
    ejecutar(AgenteFalso(en_pausa=True), "¿ya?", "web-traza")
    assert any(t.evento == "hitl_en_espera" and t.sesion_id == "web-traza" for t in trazas.ultimas_trazas(50))
    assert base.AVISO_REVISION_PENDIENTE
