"""Quien perdio el celular con el que reservo ve su reserva desde otro numero dando el codigo, el nombre y el telefono.

Solo para verla: no la vincula a la nueva conversacion, asi que cambiarla o cancelarla sigue en manos del personal.
No revela si un codigo existe ni cual dato fallo, y los intentos fallidos tienen tope por conversacion y por codigo,
guardado en SQLite. Sin modelo.
"""
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from app.agentes import autorizacion, fecha
from app.agentes.contexto import ContextoConversacion
from app.agentes.tools import reservas_tools as tools

INSTANTE = datetime(2026, 10, 7, 2, 0, tzinfo=timezone.utc)      # martes 6 de octubre, 21:00 en Lima
NUMERO_PERDIDO = "51900000001"
NUMERO_NUEVO = "51900000002"


@pytest.fixture(autouse=True)
def reloj_fijo(monkeypatch):
    """Fija el reloj de Lima para que el 2026-10-10 siga siendo una fecha futura."""
    monkeypatch.setattr(fecha, "_reloj", lambda: INSTANTE)


@pytest.fixture
def servicio(monkeypatch, servicio_reservas):
    """Conecta las herramientas al servicio de reservas temporal."""
    monkeypatch.setattr(tools, "servicio_reservas", lambda: servicio_reservas)
    return servicio_reservas


@pytest.fixture
def reserva(servicio):
    """Una reserva hecha por WhatsApp desde el numero que el cliente ya no tiene."""
    r = servicio.crear_reserva("Ana Ruiz Pérez", "900000001", "2026-10-10", "20:00", 2, "")
    autorizacion.vincular(f"whatsapp-{NUMERO_PERDIDO}", r.id)
    return r


def whatsapp(numero=NUMERO_NUEVO):
    """Runtime de una conversacion de WhatsApp, como la arma el webhook."""
    return SimpleNamespace(context=ContextoConversacion(sesion_id=f"whatsapp-{numero}", canal="whatsapp"))


def consultar(codigo, rt=None, nombre="", telefono=""):
    """Llama a la herramienta como lo haria el agente de reservas."""
    return tools.consultar_reserva_por_codigo.func(codigo, rt or whatsapp(), nombre=nombre, telefono=telefono)


def test_sin_datos_pide_el_nombre_y_el_telefono_sin_mostrar_nada(reserva):
    """Solo con el codigo no se ve: la herramienta le dice al agente que pida los dos datos."""
    rt = whatsapp()
    texto = consultar(reserva.id, rt)
    assert texto == tools.PEDIR_DATOS_PARA_VERIFICAR
    assert reserva.nombre not in texto and reserva.fecha not in texto
    assert rt.context.datos["guardrail_autorizacion"] == {"estado": "bloqueado"}


@pytest.mark.parametrize("nombre, telefono", [
    ("Ana Ruiz Pérez", "900000001"),
    ("ana ruiz perez", "+51 900 000 001"),
    ("Ruiz Ana", "51900000001"),
    ("ANA RUÍZ", "900-000-001"),
])
def test_con_los_datos_de_la_reserva_se_ve_con_su_codigo(reserva, nombre, telefono):
    """Mayusculas, tildes, orden y el 51 de Peru no importan; el apellido materno puede faltar."""
    rt = whatsapp()
    texto = consultar(reserva.id, rt, nombre, telefono)
    assert reserva.id in texto and reserva.fecha in texto and "verificada con el nombre y el teléfono" in texto
    assert "guardrail_autorizacion" not in rt.context.datos


@pytest.mark.parametrize("nombre, telefono", [
    ("Ana", "900000001"),                    # solo el primer nombre: lo sabe cualquiera
    ("Ana Ruiz", "900000009"),               # otro telefono
    ("Luis Ruiz", "900000001"),              # otro nombre
    ("Ana Ruiz Pérez Gómez", "900000001"),   # una palabra que no esta en la reserva
])
def test_con_un_dato_equivocado_no_se_ve_y_no_dice_cual_fallo(reserva, nombre, telefono):
    """La respuesta es la misma para cualquier dato equivocado."""
    texto = consultar(reserva.id, whatsapp(), nombre, telefono)
    assert texto == tools.DATOS_NO_COINCIDEN and reserva.fecha not in texto


def test_un_codigo_inexistente_responde_igual_que_uno_con_datos_equivocados(reserva):
    """No se puede usar la verificacion para averiguar que codigos existen."""
    assert consultar("R-ZZZZZZ", whatsapp(), "Ana Ruiz", "900000001") == tools.DATOS_NO_COINCIDEN


def test_verla_no_la_vuelve_de_esta_conversacion(reserva):
    """Verificada, se ve; pero cambiarla o cancelarla desde el numero nuevo sigue denegado."""
    rt = whatsapp()
    assert reserva.id in consultar(reserva.id, rt, "Ana Ruiz", "900000001")
    assert not autorizacion.es_propietario(rt.context.sesion_id, reserva.id)
    assert tools.cancelar_reserva.func(reserva.id, rt) == autorizacion.DENEGADO
    assert reserva.id not in tools.buscar_mis_reservas.func(rt)


def test_al_tercer_fallo_la_conversacion_ya_no_verifica_aunque_luego_acierte(reserva):
    """Tres intentos fallidos por conversacion en 24 horas; despues, ni con los datos correctos."""
    rt = whatsapp()
    assert consultar(reserva.id, rt, "Luis Ruiz", "900000001") == tools.DATOS_NO_COINCIDEN
    assert consultar(reserva.id, rt, "Luis Ruiz", "900000001") == tools.DATOS_NO_COINCIDEN
    assert consultar(reserva.id, rt, "Luis Ruiz", "900000001") == tools.VERIFICACION_BLOQUEADA
    assert consultar(reserva.id, rt, "Ana Ruiz", "900000001") == tools.VERIFICACION_BLOQUEADA


def test_los_fallos_contra_un_codigo_desde_varios_numeros_tambien_lo_bloquean(reserva):
    """Cambiar de numero no da intentos nuevos contra la misma reserva: el tope por codigo es 5."""
    for i in range(autorizacion.MAX_VERIFICACIONES_FALLIDAS_POR_RESERVA):
        consultar(reserva.id, whatsapp(f"5190000010{i}"), "Luis Ruiz", "900000001")
    assert consultar(reserva.id, whatsapp("51900000199"), "Ana Ruiz", "900000001") == tools.VERIFICACION_BLOQUEADA


def test_los_fallos_de_hace_mas_de_un_dia_ya_no_cuentan(reserva, servicio):
    """Al dia siguiente el cliente puede volver a intentarlo."""
    ayer = autorizacion.time.time() - autorizacion.VENTANA_VERIFICACIONES_SEGUNDOS - 60
    for _ in range(autorizacion.MAX_VERIFICACIONES_FALLIDAS_POR_SESION):
        autorizacion.verificar_con_datos("whatsapp-51900000002", reserva.id, "Luis", "900000001", servicio, ahora=ayer)
    assert reserva.id in consultar(reserva.id, whatsapp(), "Ana Ruiz", "900000001")


def test_la_reserva_propia_y_la_del_numero_se_siguen_viendo_sin_datos(reserva):
    """La verificacion por datos es solo para otro numero: la propia y la del mismo numero no la necesitan."""
    assert "verificada" not in consultar(reserva.id, whatsapp(NUMERO_PERDIDO))


def test_el_prompt_dice_como_verificar_una_reserva_de_otro_numero():
    """El agente pide los tres datos en un mensaje y, si fallan, no dice cual."""
    from app.agentes.prompts import PROMPT_RESERVAS

    plano = " ".join(PROMPT_RESERVAS.split())
    assert "pidele en un mensaje el codigo R-, el nombre y el telefono con los que reservo" in plano
    assert "Si los datos no coinciden, no digas cual fallo" in plano
