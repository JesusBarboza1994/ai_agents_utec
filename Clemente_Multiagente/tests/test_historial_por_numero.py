"""En WhatsApp el cliente ve todas las reservas con su numero de contacto, aunque las haya hecho desde otro chat.

El numero lo verifica el canal (la sesion whatsapp-<numero> solo la arma el webhook firmado por Twilio), asi que
deja VER esas reservas. Cambiar o cancelar sigue exigiendo que la reserva sea de esta conversacion. Un telefono
escrito en el chat, el webchat o el id oculto de WhatsApp no abren nada. Sin modelo.
"""
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from app.agentes import autorizacion, fecha
from app.agentes.contexto import ContextoConversacion
from app.agentes.tools import reservas_tools as tools

INSTANTE = datetime(2026, 10, 7, 2, 0, tzinfo=timezone.utc)      # martes 6 de octubre, 21:00 en Lima
NUMERO = "51900000001"


@pytest.fixture(autouse=True)
def reloj_fijo(monkeypatch):
    """Fija el reloj de Lima para que el 2026-10-10 siga siendo una fecha futura."""
    monkeypatch.setattr(fecha, "_reloj", lambda: INSTANTE)


@pytest.fixture
def servicio(monkeypatch, servicio_reservas):
    """Conecta las herramientas al servicio de reservas temporal."""
    monkeypatch.setattr(tools, "servicio_reservas", lambda: servicio_reservas)
    return servicio_reservas


def whatsapp(numero=NUMERO):
    """Runtime de una conversacion de WhatsApp, como la arma el webhook."""
    return SimpleNamespace(context=ContextoConversacion(sesion_id=f"whatsapp-{numero}", canal="whatsapp"))


def reserva_desde_otro_chat(servicio, telefono=NUMERO, sesion="web-otra"):
    """Una reserva hecha desde otra conversacion con ese telefono de contacto."""
    r = servicio.crear_reserva("Cliente ficticio", telefono, "2026-10-10", "20:00", 2, "")
    autorizacion.vincular(sesion, r.id)
    return r


def test_whatsapp_muestra_la_reserva_hecha_desde_otro_chat_con_su_numero(servicio):
    """La reserva se hizo desde el webchat con este numero de contacto: por WhatsApp se ve, con su codigo."""
    r = reserva_desde_otro_chat(servicio)
    texto = tools.buscar_mis_reservas.func(whatsapp())
    assert r.id in texto and "hecha desde otro chat" in texto


@pytest.mark.parametrize("guardado", ["900000001", "+51900000001"])
def test_el_numero_coincide_con_o_sin_codigo_de_pais(servicio, guardado):
    """Quien reservo en el webchat suele escribir 900000001, sin el 51: igual es el numero de WhatsApp."""
    r = reserva_desde_otro_chat(servicio, telefono=guardado)
    assert r.id in tools.buscar_mis_reservas.func(whatsapp())


def test_las_reservas_del_propio_chat_no_se_marcan_como_de_otro(servicio):
    """Una reserva de esta misma conversacion sale una vez y sin la marca de solo ver."""
    r = reserva_desde_otro_chat(servicio, sesion=f"whatsapp-{NUMERO}")
    texto = tools.buscar_mis_reservas.func(whatsapp())
    assert texto.count(r.id) == 1 and "hecha desde otro chat" not in texto


def test_otro_numero_de_whatsapp_no_ve_la_reserva(servicio):
    """El numero tiene que ser el de contacto de la reserva."""
    r = reserva_desde_otro_chat(servicio)
    texto = tools.buscar_mis_reservas.func(whatsapp("51900000002"))
    assert r.id not in texto and texto == tools.SIN_RESERVAS_EN_ESTE_CHAT


def test_el_webchat_no_ve_reservas_por_numero_aunque_la_sesion_lo_parezca(servicio):
    """Solo cuenta el canal WhatsApp: una sesion con forma whatsapp-<numero> que no viene de ese canal no abre nada."""
    r = reserva_desde_otro_chat(servicio)
    falsa = SimpleNamespace(context=ContextoConversacion(sesion_id=f"whatsapp-{NUMERO}", canal="webchat"))
    assert r.id not in tools.buscar_mis_reservas.func(falsa)


def test_el_id_oculto_de_whatsapp_no_es_un_numero(servicio):
    """Con el numero oculto (whatsapp-PE.<id>) no hay telefono verificado: no se busca por numero."""
    reserva_desde_otro_chat(servicio)
    rt = SimpleNamespace(context=ContextoConversacion(sesion_id="whatsapp-PE.2227643368025850", canal="whatsapp"))
    assert tools.buscar_mis_reservas.func(rt) == tools.SIN_RESERVAS_EN_ESTE_CHAT


def test_el_telefono_escrito_en_el_chat_sigue_sin_abrir_nada(servicio):
    """Decir un numero en el webchat no muestra las reservas de ese numero: solo el canal lo verifica."""
    r = reserva_desde_otro_chat(servicio)
    web = SimpleNamespace(context=ContextoConversacion(sesion_id="web-intruso", canal="webchat"))
    assert r.id not in tools.buscar_mis_reservas.func(web, NUMERO)


def test_por_codigo_tambien_se_ve_pero_marcada_como_de_otro_chat(servicio):
    """Si pregunta por el codigo de una reserva de su numero, la ve; desde otro numero, sin datos, no la ve."""
    r = reserva_desde_otro_chat(servicio)
    assert r.id in tools.consultar_reserva_por_codigo.func(r.id, whatsapp())
    texto = tools.consultar_reserva_por_codigo.func(r.id, whatsapp("51900000002"))
    assert texto == tools.PEDIR_DATOS_PARA_VERIFICAR and r.nombre not in texto and r.fecha not in texto


@pytest.mark.parametrize("operacion", ["cancelar", "modificar"])
def test_ver_no_es_cambiar_ni_cancelar(servicio, operacion):
    """La reserva de otro chat se ve, pero no se prepara ninguna operacion sobre ella."""
    r = reserva_desde_otro_chat(servicio)
    rt = whatsapp()
    if operacion == "cancelar":
        texto = tools.cancelar_reserva.func(r.id, rt)
    else:
        texto = tools.modificar_reserva.func(r.id, rt, hora="21:00")
    assert texto == autorizacion.DENEGADO and "confirmacion_pendiente" not in rt.context.datos


def test_el_prompt_dice_que_hacer_con_una_reserva_de_otro_chat():
    """El agente la muestra con su codigo y, para cambiarla, ofrece el equipo; nunca manda al cliente a la web."""
    from app.agentes.prompts import PROMPT_RESERVAS

    plano = " ".join(PROMPT_RESERVAS.split())
    assert 'Una reserva "hecha desde otro chat con este numero": muestrala igual, con su codigo' in plano
    assert "desde aqui no se puede: ofrecele dejar el pedido al equipo con escalar_a_staff" in plano
    assert "No lo mandes a la web, que no es un canal para clientes" in plano


def test_el_aviso_de_chat_sin_reservas_no_manda_a_la_web():
    """El webchat es de control interno: el texto solo menciona otro numero de WhatsApp."""
    assert "web" not in tools.SIN_RESERVAS_EN_ESTE_CHAT.lower()
    assert "otro número de WhatsApp" in tools.SIN_RESERVAS_EN_ESTE_CHAT
    assert "si ya no tiene ese celular, con el código R- de la reserva" in tools.SIN_RESERVAS_EN_ESTE_CHAT
