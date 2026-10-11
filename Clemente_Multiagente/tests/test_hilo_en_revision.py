"""Solo un hilo con una interrupcion real del staff cuenta como revision; un turno cortado por un error no.

Caso real (webchat local, 2026-10-11): una herramienta fallo a mitad de turno, el hilo de
reservas quedo con un paso pendiente y el siguiente mensaje se trato como una revision del
staff: el cliente leyo "tu solicitud anterior al equipo ya no estaba vigente" sin haber pedido
nada al equipo, y su mensaje se perdio. Las pruebas usan grafos minimos de LangGraph con un
SqliteSaver en memoria: el mismo checkpointer que usa reservas, sin modelo ni red.
"""
import sqlite3
from typing import TypedDict

import pytest
from langchain_core.messages import AIMessage
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt

from app.agentes import base
from app.agentes import reservas as agente_reservas
from app.agentes.contexto import ContextoConversacion

SESION = "web-prueba-hilo"


class _Estado(TypedDict):
    """Estado minimo de los grafos de prueba."""

    x: int


def _paso_que_pide_revision(estado):
    """Se detiene como lo hace la revision humana: con una interrupcion real."""
    interrupt({"accion": "solicitar_excepcion_grupo"})
    return {"x": 1}


def _paso_que_falla(estado):
    """Simula una herramienta que lanza un error a mitad de turno."""
    raise RuntimeError("falla simulada de una herramienta")


def _grafo(nodo, saver):
    """Grafo START -> antes -> nodo -> END, compilado con el checkpointer dado."""
    grafo = StateGraph(_Estado)
    grafo.add_node("antes", lambda estado: {"x": 0})
    grafo.add_node("nodo", nodo)
    grafo.add_edge(START, "antes")
    grafo.add_edge("antes", "nodo")
    grafo.add_edge("nodo", END)
    return grafo.compile(checkpointer=saver)


def _config():
    """Config del hilo de reservas de la sesion de prueba, igual que la arma `ejecutar`."""
    return {"configurable": {"thread_id": base.id_de_hilo(agente_reservas.FLUJO, SESION)}}


@pytest.fixture
def saver():
    """SqliteSaver en memoria, el mismo tipo de checkpointer que usa reservas."""
    return SqliteSaver(sqlite3.connect(":memory:", check_same_thread=False))


def _dejar_hilo(nodo, saver):
    """Corre el grafo hasta que se pausa o se corta, y lo devuelve con ese estado guardado."""
    grafo = _grafo(nodo, saver)
    try:
        grafo.invoke({"x": 0}, _config())
    except RuntimeError:
        pass
    return grafo


def test_los_dos_casos_dejan_un_paso_pendiente(saver):
    """Por eso `next` no alcanza para distinguirlos: solo la revision tiene interrupcion."""
    pausado = _dejar_hilo(_paso_que_pide_revision, saver).get_state(_config())
    assert pausado.next and pausado.interrupts

    saver_cortado = SqliteSaver(sqlite3.connect(":memory:", check_same_thread=False))
    cortado = _dejar_hilo(_paso_que_falla, saver_cortado).get_state(_config())
    assert cortado.next and not cortado.interrupts


def test_solo_una_interrupcion_real_cuenta_como_revision(saver):
    """`_hilo_en_pausa` es True con la revision del staff y False con un turno cortado."""
    assert base._hilo_en_pausa(_dejar_hilo(_paso_que_pide_revision, saver), _config())

    saver_cortado = SqliteSaver(sqlite3.connect(":memory:", check_same_thread=False))
    assert not base._hilo_en_pausa(_dejar_hilo(_paso_que_falla, saver_cortado), _config())


def test_el_resto_de_un_turno_cortado_se_borra_y_una_revision_no(saver):
    """El turno cortado se limpia antes del mensaje nuevo; la revision conserva su checkpoint."""
    cortado = _dejar_hilo(_paso_que_falla, saver)
    base._descartar_turno_inconcluso(cortado, _config(), SESION, agente_reservas.FLUJO)
    assert saver.get_tuple(_config()) is None

    saver_pausado = SqliteSaver(sqlite3.connect(":memory:", check_same_thread=False))
    pausado = _dejar_hilo(_paso_que_pide_revision, saver_pausado)
    base._descartar_turno_inconcluso(pausado, _config(), SESION, agente_reservas.FLUJO)
    assert saver_pausado.get_tuple(_config()) is not None
    assert pausado.get_state(_config()).interrupts


def test_cancelar_solicitud_solo_ve_una_revision_real(monkeypatch, saver):
    """`tiene_hilo_guardado` (lo usan CANCELAR SOLICITUD y la pausa huerfana) ignora un turno cortado."""
    monkeypatch.setattr(agente_reservas, "_obtener_checkpointer", lambda: saver)
    assert not agente_reservas.tiene_hilo_guardado(SESION)

    _dejar_hilo(_paso_que_falla, saver)
    assert not agente_reservas.tiene_hilo_guardado(SESION)

    saver_pausado = SqliteSaver(sqlite3.connect(":memory:", check_same_thread=False))
    monkeypatch.setattr(agente_reservas, "_obtener_checkpointer", lambda: saver_pausado)
    _dejar_hilo(_paso_que_pide_revision, saver_pausado)
    assert agente_reservas.tiene_hilo_guardado(SESION)


def test_despues_de_un_turno_cortado_el_mensaje_nuevo_se_atiende(monkeypatch, saver):
    """`ejecutar` no responde "sigue en revision": limpia el resto e invoca al agente con el mensaje."""
    grafo_cortado = _dejar_hilo(_paso_que_falla, saver)
    recibido = {}

    class _Agente:
        """Agente de reservas de prueba con el hilo cortado guardado en su checkpointer."""

        checkpointer = saver

        def get_state(self, config):
            """Estado real del hilo guardado."""
            return grafo_cortado.get_state(config)

        def invoke(self, entrada, config=None, context=None):
            """Registra que el mensaje nuevo llego y si el hilo ya estaba limpio."""
            recibido["hilo_limpio"] = saver.get_tuple(config) is None
            return {"messages": [AIMessage(content="Claro, te ayudo con tu reserva.")]}

    monkeypatch.setattr(base, "ficha_del_cliente", lambda *a: "")
    contexto = ContextoConversacion(sesion_id=SESION)

    respuesta = base.ejecutar(
        _Agente(), "Necesito una reserva para el martes a las 7 pm", SESION, [],
        contexto=contexto, flujo=agente_reservas.FLUJO,
    )

    assert respuesta == "Claro, te ayudo con tu reserva."
    assert respuesta != base.AVISO_REVISION_PENDIENTE
    assert recibido["hilo_limpio"]
    assert "hilo_en_revision" not in contexto.datos
