"""Si la base de reservas no responde, el agente atiende igual, sin la ficha; sin modelo, sin red.

Caso real (2026-10-11): con la conexion a Postgres caida, `ficha_del_cliente` lanzaba DatabaseError en cada turno de
los tres agentes y el cliente leia "Disculpa, no puedo procesar tu mensaje" hasta para "Quiero hacer una reserva".
"""
from types import SimpleNamespace

import psycopg2

from app.agentes import base
from app.observabilidad.trazas import ultimas_trazas


class AgenteQueAnota:
    """Agente minimo que responde un texto fijo y guarda lo que recibio."""

    def __init__(self, texto):
        """Guarda la respuesta que va a dar."""
        self.texto = texto
        self.recibido = None

    def invoke(self, entrada, config=None, context=None):
        """Anota los mensajes recibidos y responde sin herramientas."""
        self.recibido = entrada["messages"]
        return {"messages": [SimpleNamespace(content=self.texto, type="ai")]}


def _base_caida(sesion_id):
    """La consulta de reservas propias con la conexion cortada."""
    raise psycopg2.DatabaseError("SSL SYSCALL error: EOF detected")


def test_con_la_base_caida_el_agente_responde_igual(monkeypatch):
    """El cliente recibe la respuesta del agente, no el aviso de error."""
    monkeypatch.setattr(base, "ficha_del_cliente", _base_caida)
    agente = AgenteQueAnota("¡Claro! ¿Para qué fecha, hora y cuántas personas?")
    respuesta = base.ejecutar(agente, "Quiero hacer una reserva", "whatsapp-ficha-1", flujo="reservas")
    assert respuesta == "¡Claro! ¿Para qué fecha, hora y cuántas personas?"
    assert "Quiero hacer una reserva" in str(agente.recibido[-1]["content"])


def test_la_caida_queda_registrada_solo_con_su_tipo(monkeypatch):
    """La traza dice donde fallo y el tipo de error, sin el mensaje de la base (puede traer el host)."""
    monkeypatch.setattr(base, "ficha_del_cliente", _base_caida)
    base.ejecutar(AgenteQueAnota("ok"), "hola", "whatsapp-ficha-2", flujo="reservas")
    errores = [t.detalle for t in ultimas_trazas(limite=10000, sesion_id="whatsapp-ficha-2") if t.evento == "error"]
    assert errores == [{"error": "ficha: DatabaseError"}]


def test_con_la_base_sana_la_ficha_sigue_llegando(monkeypatch):
    """El arreglo no cambia el camino normal: las reservas propias viajan en el turno."""
    monkeypatch.setattr(base, "ficha_del_cliente", lambda sesion_id: "R-ABC123: Ana, 2026-10-14 a las 20:00")
    agente = AgenteQueAnota("ok")
    base.ejecutar(agente, "¿qué reservas tengo?", "whatsapp-ficha-3", flujo="reservas")
    assert "R-ABC123" in str(agente.recibido[-1]["content"])
