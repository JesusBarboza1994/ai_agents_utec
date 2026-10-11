"""Una solicitud de mas de 8 personas lleva un codigo G- desde que se pausa hasta su tarjeta de Trello; sin modelo.

Los reclamos siguen con I-. El G- nace al pausar (lo recibe el cliente y lo ve el personal) y la tarjeta que se abre
al aprobar lo conserva, de modo que cliente, panel y tablero hablan del mismo caso.
"""
import re
import time
from types import SimpleNamespace

import pytest

from app.agentes import reservas as agente_reservas
from app.agentes.base import (
    AVISO_REVISION_PENDIENTE, AVISO_REVISION_PENDIENTE_CON_CODIGO, SOLICITUD_EN_REVISION, ejecutar,
)
from app.agentes.contexto import ContextoConversacion
from app.incidencias import codigos, obtener_servicio
from app.incidencias.servicio_json import ServicioIncidenciasJSON
from app.orquestador import grafo

SESION = "whatsapp-51999111222"
CODIGO = "G-ABC123"


class AgenteQuePausa:
    """Agente minimo que, al invocarlo, devuelve la interrupcion de la excepcion de grupo."""

    checkpointer = None

    def invoke(self, entrada, config=None, context=None):
        """Simula el turno en el que el agente llama a `solicitar_excepcion_grupo` y queda pausado."""
        return {"__interrupt__": [SimpleNamespace(value={"action_requests": [{"name": "solicitar_excepcion_grupo"}]})],
                "messages": []}


class AgentePausado:
    """Agente minimo cuyo hilo ya esta detenido esperando la decision del personal."""

    def __init__(self):
        """Marca el hilo como con checkpoint, para que `ejecutar` consulte si esta en pausa."""
        self.checkpointer = object()

    def get_state(self, config):
        """Como LangGraph: un hilo pausado trae nodos pendientes y la interrupcion."""
        return SimpleNamespace(next=("tools",), interrupts=(SimpleNamespace(value={"accion": "revision"}),))

    def invoke(self, entrada, config=None, context=None):
        """No debe llegar al modelo: un hilo pausado responde con el aviso."""
        raise AssertionError("un hilo pausado no debe invocar al modelo")


def _poner_en_cola(monkeypatch, sesion=SESION, **extra):
    """Deja una solicitud en la cola del personal, como la deja un turno que pauso."""
    grafo._cargar_revisiones()
    entrada = {"sesion_id": sesion, "solicitud": {"action_requests": []}, "canal": "whatsapp",
               "creada": time.time(), **extra}
    monkeypatch.setitem(grafo._revisiones, sesion, entrada)
    return entrada


# --- el codigo -------------------------------------------------------------------------

def test_un_codigo_de_grupo_empieza_con_g_y_un_reclamo_con_i():
    """Los dos prefijos generan seis caracteres hexadecimales en mayuscula."""
    assert re.fullmatch(r"G-[0-9A-F]{6}", codigos.nuevo_codigo(codigos.PREFIJO_GRUPO))
    assert re.fullmatch(r"I-[0-9A-F]{6}", codigos.nuevo_codigo(codigos.PREFIJO_INCIDENCIA))
    assert re.fullmatch(r"I-[0-9A-F]{6}", codigos.nuevo_codigo())


def test_un_prefijo_desconocido_es_un_error():
    """Solo existen I y G: otro prefijo es un error de programacion, no un codigo nuevo."""
    with pytest.raises(ValueError):
        codigos.nuevo_codigo("X")


@pytest.mark.parametrize("codigo, esperado", [
    ("G-ABC123", True), ("I-000000", True), ("X-ABC123", False), ("G-abc123", False),
    ("G-12345", False), ("G-ABC1234", False), ("", False), (None, False),
])
def test_solo_se_admiten_codigos_con_la_forma_valida(codigo, esperado):
    """Un codigo pedido por fuera de `I-XXXXXX` o `G-XXXXXX` se ignora."""
    assert codigos.codigo_admitido(codigo) is esperado


# --- el reclamo con ese codigo -----------------------------------------------------------

def test_la_incidencia_usa_el_codigo_que_se_le_pide(tmp_path):
    """La tarjeta de un grupo conserva el G- que el cliente ya tenia."""
    servicio = ServicioIncidenciasJSON(tmp_path / "incidencias.json")

    incidencia = servicio.crear_incidencia("s", "grupo de 9", "reserva", codigo=CODIGO)

    assert incidencia.id == CODIGO
    assert [caso.id for caso in servicio.listar_incidencias()] == [CODIGO]


def test_un_codigo_invalido_o_repetido_genera_uno_nuevo(tmp_path):
    """Un codigo mal formado o ya usado no pisa nada: el caso recibe un I- nuevo."""
    servicio = ServicioIncidenciasJSON(tmp_path / "incidencias.json")
    servicio.crear_incidencia("s", "primero", "reserva", codigo=CODIGO)

    malo = servicio.crear_incidencia("s", "segundo", "reserva", codigo="hola")
    repetido = servicio.crear_incidencia("s", "tercero", "reserva", codigo=CODIGO)

    assert malo.id.startswith("I-") and repetido.id.startswith("I-")
    assert len({caso.id for caso in servicio.listar_incidencias()}) == 3


def test_sin_codigo_el_reclamo_sigue_siendo_i(tmp_path):
    """Los reclamos de siempre no cambian: I- y seis caracteres."""
    incidencia = ServicioIncidenciasJSON(tmp_path / "incidencias.json").crear_incidencia("s", "espera", "espera")

    assert re.fullmatch(r"I-[0-9A-F]{6}", incidencia.id)


# --- al pausar y mientras espera -----------------------------------------------------------

def test_al_pausar_el_cliente_recibe_su_codigo_g():
    """El turno que pausa la solicitud devuelve el texto con el G- y lo deja en el contexto para la cola."""
    contexto = ContextoConversacion(sesion_id=SESION)

    texto = ejecutar(AgenteQuePausa(), "grupo de 9", SESION, contexto=contexto)

    codigo = contexto.datos["revision_humana"]["codigo"]
    assert re.fullmatch(r"G-[0-9A-F]{6}", codigo)
    assert texto == SOLICITUD_EN_REVISION.format(codigo=codigo)
    assert "todavía no hay una mesa confirmada" in texto.lower()


def test_el_hilo_pausado_recuerda_el_codigo_al_cliente(monkeypatch):
    """Un mensaje mientras espera responde con el mismo G- que recibio al pausar y la salida CANCELAR SOLICITUD."""
    _poner_en_cola(monkeypatch, codigo=CODIGO)

    texto = ejecutar(AgentePausado(), "¿y mi solicitud?", SESION)

    assert texto == AVISO_REVISION_PENDIENTE_CON_CODIGO.format(codigo=CODIGO)
    assert "CANCELAR SOLICITUD" in texto


def test_una_solicitud_antigua_sin_codigo_conserva_el_aviso_de_siempre(monkeypatch):
    """Las solicitudes que ya estaban en la cola antes de existir el G- siguen funcionando sin codigo."""
    _poner_en_cola(monkeypatch)

    assert ejecutar(AgentePausado(), "¿y mi solicitud?", SESION) == AVISO_REVISION_PENDIENTE


def test_la_cola_del_personal_muestra_el_codigo(monkeypatch):
    """El panel recibe el G- de cada solicitud pendiente, o None si es una anterior sin codigo."""
    _poner_en_cola(monkeypatch, codigo=CODIGO)
    _poner_en_cola(monkeypatch, sesion="whatsapp-51888000111")

    vista = {item["sesion_id"]: item["codigo"] for item in grafo.revisiones_pendientes()}

    assert vista == {SESION: CODIGO, "whatsapp-51888000111": None}
    assert grafo.codigo_de_revision(SESION) == CODIGO
    assert grafo.codigo_de_revision("whatsapp-51000000000") is None


def test_cancelar_la_solicitud_menciona_su_codigo(monkeypatch):
    """Retirar la solicitud confirma cual se retiro; sin codigo, el mensaje de siempre."""
    monkeypatch.setattr(agente_reservas, "liberar_pausa", lambda sesion: True)
    monkeypatch.setattr(agente_reservas, "tiene_hilo_guardado", lambda sesion: False)
    _poner_en_cola(monkeypatch, codigo=CODIGO)
    assert grafo._cancelar_solicitud(SESION) == grafo.SOLICITUD_CANCELADA_CON_CODIGO.format(codigo=CODIGO)

    _poner_en_cola(monkeypatch)
    assert grafo._cancelar_solicitud(SESION) == grafo.SOLICITUD_CANCELADA


# --- la tarjeta ------------------------------------------------------------------------------

class _ServicioQueAnota:
    """Servicio de incidencias minimo que guarda los argumentos con los que se le pide crear un caso."""

    def __init__(self):
        """Empieza sin llamadas registradas."""
        self.llamadas = []

    def crear_incidencia(self, **kwargs):
        """Anota los argumentos y devuelve un caso con el codigo pedido, o uno I- si no se pidio ninguno."""
        self.llamadas.append(kwargs)
        return SimpleNamespace(id=kwargs.get("codigo", "I-111111"))


def _escalar_con(monkeypatch, origen, **datos):
    """Corre `_escalar` con un servicio simulado y devuelve (codigo del caso, argumentos de la creacion)."""
    servicio = _ServicioQueAnota()
    monkeypatch.setattr(grafo, "servicio_incidencias", lambda: servicio)
    monkeypatch.setattr(grafo, "_escalamiento_previo", lambda sesion: None)
    monkeypatch.setattr(grafo, "_escalado_de", {})        # cada llamada es un caso nuevo, no el que ya se abrio
    contexto = ContextoConversacion(sesion_id=SESION)
    contexto.datos.update(datos)
    codigo = grafo._escalar(SESION, {"origen": origen, "motivo": "m", "detalle": "d"}, "mensaje", contexto)
    return codigo, servicio.llamadas[0]


def test_la_tarjeta_de_un_grupo_conserva_su_codigo(monkeypatch):
    """Al aprobar la excepcion de grupo, el caso se crea con el mismo G- que recibio el cliente."""
    codigo, llamada = _escalar_con(monkeypatch, "reservas_hitl", codigo_grupo=CODIGO)

    assert codigo == CODIGO and llamada["codigo"] == CODIGO


def test_un_escalamiento_comun_no_pide_codigo(monkeypatch):
    """Escalar por otro motivo (hablar con una persona, un conflicto) sigue generando su I- normal."""
    for origen in ("reservas", "orquestador"):
        _, llamada = _escalar_con(monkeypatch, origen, codigo_grupo=CODIGO)
        assert "codigo" not in llamada


def test_aprobar_un_grupo_deja_la_tarjeta_con_su_codigo_g(monkeypatch):
    """De punta a punta con el servicio real: la cola guarda el G-, el personal aprueba y el caso lo conserva."""
    _poner_en_cola(monkeypatch, codigo=CODIGO)

    def resolver(sesion_id, decision, contexto):
        """Simula al agente reanudado: la excepcion queda aprobada y pide abrir el caso."""
        contexto.escalado = True
        contexto.datos["escalamiento"] = {"origen": "reservas_hitl", "motivo": "excepcion aprobada",
                                          "detalle": "grupo de 9"}
        return "El equipo aprobó tramitar la excepción."

    monkeypatch.setattr(agente_reservas, "resolver_revision", resolver)
    monkeypatch.setattr(grafo, "_escalamiento_previo", lambda sesion: None)

    respuesta = grafo.resolver_revision(SESION, "approve")

    assert CODIGO in respuesta.texto
    assert [caso.id for caso in obtener_servicio().listar_incidencias()] == [CODIGO]
