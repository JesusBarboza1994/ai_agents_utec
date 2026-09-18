"""
Pruebas del servidor MCP de tickets -- Sesion 16.

Corren **sin red y sin credenciales**: el cliente se conecta al servidor en
memoria (`fastmcp.Client` acepta el objeto servidor) y el servidor escribe en un
JSON temporal. Ni Trello ni el modelo participan.

La prueba que importa de verdad es la primera: verifica que el servidor **no
publica** ninguna herramienta de cierre. Ese es el limite de permisos del
proyecto, y una prueba es la unica forma de que siga siendo cierto dentro de un
mes, cuando alguien agregue una herramienta "solo para probar".
"""

import pytest

from app.incidencias import mcp_trello
from app.incidencias.servicio_json import ServicioIncidenciasJSON
from app.incidencias.servicio_mcp import ServicioIncidenciasMCP


@pytest.fixture
def servicio_mcp(tmp_path, monkeypatch):
    """Cliente MCP contra el servidor en memoria, con almacenamiento temporal."""
    local = ServicioIncidenciasJSON(archivo=tmp_path / "incidencias.json")
    # Sin esto el servidor resolveria Trello si hay credenciales en el .env, y
    # las pruebas escribirian tarjetas de verdad en el tablero del equipo.
    monkeypatch.setattr(mcp_trello, "_backend", lambda: local)
    return ServicioIncidenciasMCP(destino=mcp_trello.mcp, espejo=local)


# --------------------------------------------------------------------------
# El limite de permisos
# --------------------------------------------------------------------------

def test_el_servidor_no_publica_ninguna_herramienta_de_cierre(servicio_mcp):
    """
    El corazon del diseno: el agente no tiene prohibido cerrar un ticket, es que
    **no existe** la herramienta del otro lado del protocolo. Aunque el prompt
    fallara entero, no hay nada que llamar.

    El cierre lo confirma una persona moviendo la tarjeta en su tablero, que es
    lo que exige el Entregable 01.
    """
    publicadas = {h["nombre"] for h in servicio_mcp.herramientas()}

    assert publicadas == {
        "crear_ticket", "consultar_ticket", "listar_tickets", "comentar_ticket",
    }
    for prohibida in ("cerrar_ticket", "mover_ticket", "borrar_ticket", "dar_compensacion"):
        assert prohibida not in publicadas


def test_toda_herramienta_publicada_se_describe_para_el_modelo(servicio_mcp):
    """El docstring es el contrato que lee el modelo: una tool sin descripcion
    es una tool que el agente va a usar mal."""
    for herramienta in servicio_mcp.herramientas():
        assert herramienta["descripcion"].strip(), herramienta["nombre"]


# --------------------------------------------------------------------------
# El camino completo
# --------------------------------------------------------------------------

def test_un_ticket_creado_por_mcp_vuelve_con_su_plazo(servicio_mcp):
    """Verifica que un ticket creado por mcp vuelve con su plazo."""
    incidencia = servicio_mcp.crear_incidencia(
        sesion_id="whatsapp-51999000111",
        descripcion="Espere 40 minutos con reserva confirmada.",
        tipo="espera",
    )

    assert incidencia.id.startswith("I-")
    assert incidencia.tipo == "espera"
    assert incidencia.plazo_horas == 4        # el plazo lo pone la operacion, no el modelo
    assert incidencia.estado == "abierta"     # nace abierta: nadie la cierra sola


def test_lo_creado_por_mcp_se_puede_volver_a_leer_por_mcp(servicio_mcp):
    """Verifica que lo creado por mcp se puede volver a leer por mcp."""
    creada = servicio_mcp.crear_incidencia(
        sesion_id="web-1", descripcion="El plato llego frio.", tipo="producto",
    )

    leidas = servicio_mcp.listar_incidencias()
    assert [i.id for i in leidas] == [creada.id]

    consultada = servicio_mcp.llamar("consultar_ticket", ticket_id=creada.id)
    assert consultada["id"] == creada.id
    assert consultada["plazo_horas"] == 8


def test_consultar_un_ticket_que_no_existe_no_revienta(servicio_mcp):
    """Un codigo mal tipeado por el cliente es lo normal, no una excepcion."""
    respuesta = servicio_mcp.llamar("consultar_ticket", ticket_id="I-NOEXISTE")
    assert "error" in respuesta


def test_comentar_por_mcp_persiste_la_nota_y_no_finge_exito(servicio_mcp):
    """Verifica que comentar por mcp persiste la nota y no finge exito."""
    ticket = servicio_mcp.crear_incidencia("sesion-prueba", "Caso ficticio")
    assert servicio_mcp.anotar(ticket.id, "dato adicional ficticio")
    assert "dato adicional ficticio" in servicio_mcp.listar_incidencias()[0].descripcion
    assert not servicio_mcp.anotar("I-INEXISTENTE", "no debe perderse en silencio")


# --------------------------------------------------------------------------
# Que pasa cuando el protocolo falla
# --------------------------------------------------------------------------

def test_si_el_servidor_no_responde_el_reclamo_no_se_pierde(tmp_path):
    """
    Un servicio externo caido no puede costarle al cliente su reclamo. El
    servicio cae al registro local, avisa, y le devuelve igual su codigo.
    """
    local = ServicioIncidenciasJSON(archivo=tmp_path / "incidencias.json")
    roto = ServicioIncidenciasMCP(destino="http://localhost:59999/mcp", espejo=local)

    incidencia = roto.crear_incidencia(
        sesion_id="web-2", descripcion="Reserva que no aparecia.", tipo="reserva",
    )

    assert incidencia.id.startswith("I-")
    assert local.listar_incidencias()[0].id == incidencia.id


# --------------------------------------------------------------------------
# La costura con el resto del proyecto
# --------------------------------------------------------------------------

def test_el_backend_mcp_cumple_el_mismo_contrato_que_los_otros_dos():
    """
    Los tres backends son intercambiables: si alguno pierde un metodo, el
    agente se rompe recien en produccion. Aqui se rompe la prueba.
    """
    from app.incidencias.servicio_trello import ServicioIncidenciasTrello

    for metodo in ("crear_incidencia", "listar_incidencias", "cerrar_incidencia"):
        for clase in (ServicioIncidenciasMCP, ServicioIncidenciasTrello, ServicioIncidenciasJSON):
            assert callable(getattr(clase, metodo, None)), f"{clase.__name__}.{metodo}"
