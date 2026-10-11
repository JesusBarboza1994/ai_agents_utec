"""Un modelo que cierra el turno sin escribir nada no deja al cliente sin respuesta; sin modelo, sin red.

Con el modelo real se vio que, tras guardar un dato del cliente, a veces devolvia texto vacio. Por WhatsApp eso es
un mensaje que Twilio rechaza: el cliente no recibe nada. Aqui se prueba el respaldo en el punto unico por el que
pasan los tres agentes (`ejecutar`) y en la reanudacion tras la decision del personal.
"""
from types import SimpleNamespace

import pytest

from app.agentes import base
from app.agentes.base import RESPALDO_TRAS_LA_REVISION, ejecutar, reanudar_revision
from app.agentes.contexto import ContextoConversacion
from app.observabilidad.trazas import ultimas_trazas


class AgenteQueContesta:
    """Agente minimo sin pausa que devuelve el texto que se le indique, aunque sea vacio."""

    def __init__(self, texto):
        """Guarda lo que va a responder el modelo simulado."""
        self.texto = texto

    def invoke(self, entrada, config=None, context=None):
        """Responde con ese texto, sin interrupcion ni herramientas."""
        return {"messages": [SimpleNamespace(content=self.texto, type="ai")]}


def _vacias_trazadas(sesion):
    """Trazas de respuesta vacia registradas para la sesion."""
    return [t for t in ultimas_trazas(limite=10000, sesion_id=sesion)
            if t.evento == "guardrail" and "vacia" in str(getattr(t, "detalle", {}))]


@pytest.mark.parametrize("texto", ["", "   ", "\n\t"])
def test_una_respuesta_vacia_se_sustituye_por_el_respaldo(texto):
    """Texto vacio o solo espacios: el cliente recibe el respaldo y no un mensaje en blanco."""
    respuesta = ejecutar(AgenteQueContesta(texto), "hola", "vacia-1", fallback="Disculpa, ¿me lo repites?")

    assert respuesta == "Disculpa, ¿me lo repites?"
    assert _vacias_trazadas("vacia-1")


def test_sin_fallback_propio_se_usa_el_de_siempre():
    """Si el agente no pide un respaldo distinto, rige el mensaje por defecto de `ejecutar`."""
    respuesta = ejecutar(AgenteQueContesta(""), "hola", "vacia-2")

    assert respuesta.strip()
    assert "repites" in respuesta


def test_una_respuesta_con_texto_no_se_toca():
    """Lo que el modelo si escribio llega tal cual y no deja traza de respuesta vacia."""
    assert ejecutar(AgenteQueContesta("Listo, te ayudo."), "hola", "vacia-3") == "Listo, te ayudo."
    assert not _vacias_trazadas("vacia-3")


def test_tras_la_decision_del_personal_una_respuesta_vacia_no_promete_nada():
    """Aprobada o rechazada, si el modelo no escribe nada el cliente recibe un texto verdadero: sin mesa confirmada."""
    contexto = ContextoConversacion(sesion_id="vacia-4")
    texto = reanudar_revision(AgenteQueContesta(""), "vacia-4", {"type": "reject"}, contexto, "reservas")

    assert texto == RESPALDO_TRAS_LA_REVISION
    assert "no hay una mesa confirmada" in texto.lower()
    assert _vacias_trazadas("vacia-4")


def test_el_respaldo_tras_la_revision_no_aprueba_ni_rechaza():
    """El texto de respaldo no dice 'aprobada' ni 'rechazada': el modelo no dijo cual fue la decision."""
    plano = base.RESPALDO_TRAS_LA_REVISION.lower()

    assert "aprob" not in plano and "rechaz" not in plano
