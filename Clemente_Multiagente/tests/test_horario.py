"""Horario de atencion: fuente unica en fecha.py y validacion en herramientas y autorizacion; sin LLM."""
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from app.agentes import autorizacion, fecha
from app.agentes.contexto import ContextoConversacion
from app.agentes.tools import reservas_tools as tools
from app.reservas.servicio_json import ServicioReservasJSON

# Martes 2026-10-06 21:00 en Lima. Fechas usadas: sabado 10, domingo 11 y lunes 12 de octubre.
INSTANTE = datetime(2026, 10, 7, 2, 0, tzinfo=timezone.utc)
SESION = "whatsapp-51999111222"
LUNES, DOMINGO, SABADO = "2026-10-12", "2026-10-11", "2026-10-10"


@pytest.fixture(autouse=True)
def reloj_fijo(monkeypatch):
    """Fija el reloj de Lima para que las fechas no dependan del dia en que se corre la suite."""
    monkeypatch.setattr(fecha, "_reloj", lambda: INSTANTE)


@pytest.fixture
def servicio(tmp_path, monkeypatch):
    """Servicio de reservas JSON temporal conectado a las herramientas."""
    servicio = ServicioReservasJSON(archivo_reservas=tmp_path / "reservas.json")
    monkeypatch.setattr(tools, "servicio_reservas", lambda: servicio)
    return servicio


def runtime():
    """Runtime simulado con la sesion de prueba y contexto vacio."""
    return SimpleNamespace(context=ContextoConversacion(sesion_id=SESION))


def reserva_propia(servicio, fecha_reserva, hora="20:00"):
    """Crea una reserva directo en el servicio (como haria la API REST) y la vincula a la sesion."""
    reserva = servicio.crear_reserva("Cliente ficticio", "900000001", fecha_reserva, hora, 2, "")
    autorizacion.vincular(SESION, reserva.id)
    return reserva


def test_el_texto_del_horario_sale_de_la_tabla():
    """El texto que leen los prompts se arma desde la misma tabla que usan las validaciones."""
    assert fecha.texto_horario() == (
        "lunes cerrado; martes a jueves 12:00-15:30 y 19:00-23:00; "
        "viernes y sabado 12:00-16:00 y 19:00-00:00; domingo 12:00-17:00"
    )


@pytest.mark.parametrize("fecha_pedida, hora, atiende", [
    (LUNES, "20:00", False),      # lunes cerrado
    (LUNES, None, False),         # sin hora igual se sabe que el lunes no atiende
    (DOMINGO, "20:00", False),    # el domingo cierra a las 17:00
    (DOMINGO, "14:00", True),
    ("2026-10-13", "22:00", True),  # martes: 22:00 queda a 45 minutos del cierre de las 23:00
    (SABADO, "22:00", True),
])
def test_fuera_de_horario(fecha_pedida, hora, atiende):
    """Dias cerrados y turnos fuera de franja devuelven un motivo; los atendidos devuelven None."""
    assert (fecha.fuera_de_horario(fecha_pedida, hora) is None) is atiende


def test_formatos_invalidos_no_los_juzga_el_horario():
    """Una fecha u hora mal escrita la reporta la validacion de turno, no el horario."""
    assert fecha.fuera_de_horario("no-es-fecha", "20:00") is None
    assert fecha.fuera_de_horario(SABADO, "ocho") is None


def test_el_domingo_solo_tiene_turnos_de_almuerzo():
    """De los turnos que se reservan, el domingo solo se atienden los de 12, 13 y 14 h."""
    turnos = ["12:00", "13:00", "14:00", "19:00", "20:00", "21:00", "22:00"]
    assert fecha.turnos_del_dia(6, turnos) == ["12:00", "13:00", "14:00"]
    assert fecha.turnos_del_dia(0, turnos) == []


def test_disponibilidad_rechaza_el_lunes_sin_consultar(servicio):
    """Un lunes no se consulta disponibilidad: se explica que el restaurante no atiende."""
    texto = tools.consultar_disponibilidad.func(LUNES, "20:00", 2, runtime())
    assert "no atiende los lunes" in texto and "Disponible" not in texto


def test_disponibilidad_rechaza_el_domingo_de_noche_y_acepta_el_almuerzo(servicio):
    """El domingo a las 20:00 se rechaza; a las 13:00 se consulta normalmente."""
    assert "no atiende" in tools.consultar_disponibilidad.func(DOMINGO, "20:00", 2, runtime())
    assert "Disponible" in tools.consultar_disponibilidad.func(DOMINGO, "13:00", 2, runtime())


def test_un_turno_inexistente_conserva_su_mensaje_de_turno(servicio):
    """A las 03:00 el motivo sigue siendo el turno invalido, no el horario."""
    texto = tools.consultar_disponibilidad.func(SABADO, "03:00", 2, runtime())
    assert "turno" in texto


def test_un_grupo_grande_para_un_lunes_no_se_desvia_al_staff(servicio):
    """El dia cerrado se revisa antes que el tamano del grupo: no se ofrece pedir una excepcion."""
    texto = tools.consultar_disponibilidad.func(LUNES, "20:00", 10, runtime())
    assert "no atiende los lunes" in texto and "solicitar_excepcion_grupo" not in texto


def test_crear_un_lunes_no_prepara_confirmo(servicio):
    """La herramienta de crear rechaza el lunes y no deja propuesta pendiente."""
    rt = runtime()
    texto = tools.crear_reserva.func("Cliente ficticio", "900000001", LUNES, "20:00", 2, rt)
    assert "CONFIRMO" not in texto and "confirmacion_pendiente" not in rt.context.datos


def test_proponer_rechaza_crear_un_lunes_aunque_no_pase_por_la_herramienta(servicio):
    """La validacion vive tambien en autorizacion: ningun camino prepara una reserva para un lunes."""
    resumen = autorizacion.proponer(runtime().context, "crear", {
        "nombre": "Cliente ficticio", "telefono": "900000001", "fecha": LUNES,
        "hora": "20:00", "personas": 2, "zona": "", "notas": "",
    }, servicio)
    assert "CONFIRMO" not in resumen and "no atiende los lunes" in resumen


def test_modificar_hacia_un_lunes_se_rechaza(servicio):
    """El destino de un cambio debe caer en el horario."""
    reserva = reserva_propia(servicio, SABADO)
    texto = tools.modificar_reserva.func(reserva.id, runtime(), fecha=LUNES)
    assert "CONFIRMO" not in texto and "no atiende los lunes" in texto


def test_cambiar_solo_la_hora_al_domingo_de_noche_se_rechaza(servicio):
    """Aunque la herramienta no reciba la fecha, proponer usa la de la reserva para validar el destino."""
    reserva = reserva_propia(servicio, DOMINGO, "13:00")
    texto = tools.modificar_reserva.func(reserva.id, runtime(), hora="20:00")
    assert "CONFIRMO" not in texto and "no atiende" in texto


def test_ver_y_cancelar_una_reserva_de_un_lunes_siguen_funcionando(servicio):
    """Una reserva que ya existe en un dia hoy cerrado se puede consultar y cancelar."""
    reserva = reserva_propia(servicio, LUNES)
    assert reserva.id in tools.consultar_reserva_por_codigo.func(reserva.id, runtime())
    assert "CONFIRMO" in tools.cancelar_reserva.func(reserva.id, runtime())


def test_la_excepcion_de_grupo_para_un_lunes_se_rechaza_al_ejecutarse(servicio):
    """Si el staff aprobara una solicitud para un lunes, la herramienta igual no abre el caso."""
    rt = runtime()
    texto = tools.solicitar_excepcion_grupo.func(
        "Cliente ficticio", "900000001", LUNES, "20:00", 10, rt,
    )
    assert "no atiende los lunes" in texto and not rt.context.escalado
