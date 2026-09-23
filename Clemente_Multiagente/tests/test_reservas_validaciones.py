"""
Pruebas del modulo de validacion/saneamiento compartido de reservas.

Cubren los casos borde que motivaron el modulo: turnos fuera de catalogo,
fechas invalidas, telefonos con formato incorrecto, y texto libre
(nombre/notas) que hoy vuelve al LLM via ficha_del_cliente() sin limite de
longitud (vector de inyeccion de prompt persistente).
"""

from datetime import date, timedelta

import pytest

from app.reservas.validaciones import (
    NOMBRE_MAX,
    NOTAS_MAX,
    TURNOS_VALIDOS,
    ReservaInvalida,
    clave_idempotencia,
    validar_datos_reserva,
)

MAÑANA = str(date.today() + timedelta(days=1))


def _datos(**overrides):
    """Devuelve datos de reserva validos por defecto, sobreescribibles por caso de prueba."""
    base = dict(nombre="Ana", telefono="999111222", fecha=MAÑANA, hora="20:00",
                personas=2, zona="salon", notas="")
    base.update(overrides)
    return base


def test_datos_validos_se_aceptan_y_se_devuelven_saneados():
    """Verifica que datos validos se aceptan y se devuelven saneados."""
    resultado = validar_datos_reserva(**_datos())
    assert resultado["nombre"] == "Ana"
    assert resultado["telefono"] == "999111222"
    assert resultado["hora"] == "20:00"


def test_hora_fuera_de_turnos_validos_se_rechaza():
    """Verifica que una hora fuera de los turnos validos se rechaza."""
    with pytest.raises(ReservaInvalida, match="turno"):
        validar_datos_reserva(**_datos(hora="17:30"))


def test_todos_los_turnos_validos_se_aceptan():
    """Verifica que todos los turnos validos se aceptan."""
    for turno in TURNOS_VALIDOS:
        validar_datos_reserva(**_datos(hora=turno))


@pytest.mark.parametrize("personas", [0, -1, 11, 30])
def test_personas_fuera_de_rango_se_rechaza(personas):
    """Verifica que una cantidad de personas fuera de rango se rechaza."""
    with pytest.raises(ReservaInvalida, match="personas"):
        validar_datos_reserva(**_datos(personas=personas))


def test_personas_no_entero_se_rechaza():
    """Verifica que un valor de personas no entero se rechaza."""
    with pytest.raises(ReservaInvalida):
        validar_datos_reserva(**_datos(personas="dos"))


@pytest.mark.parametrize("personas", [1, 10])
def test_personas_en_los_limites_se_acepta(personas):
    """Verifica que las personas en los limites (1 y 10) se aceptan."""
    validar_datos_reserva(**_datos(personas=personas))


def test_fecha_en_el_pasado_se_rechaza():
    """Verifica que una fecha en el pasado se rechaza."""
    ayer = str(date.today() - timedelta(days=1))
    with pytest.raises(ReservaInvalida, match="pasado"):
        validar_datos_reserva(**_datos(fecha=ayer))


def test_fecha_hoy_se_acepta():
    """Verifica que la fecha de hoy se acepta."""
    validar_datos_reserva(**_datos(fecha=str(date.today())))


def test_fecha_muy_lejana_se_rechaza():
    """Verifica que una fecha mas alla de los dias maximos a futuro se rechaza."""
    lejos = str(date.today() + timedelta(days=91))
    with pytest.raises(ReservaInvalida, match="90"):
        validar_datos_reserva(**_datos(fecha=lejos))


def test_fecha_con_formato_invalido_se_rechaza():
    """Verifica que una fecha con formato invalido se rechaza."""
    with pytest.raises(ReservaInvalida, match="YYYY-MM-DD"):
        validar_datos_reserva(**_datos(fecha="12/09/2026"))


@pytest.mark.parametrize("telefono", ["abc123", "123", "", "  ", "99911122233344455"])
def test_telefono_con_formato_invalido_se_rechaza(telefono):
    """Verifica que un telefono con formato invalido se rechaza."""
    with pytest.raises(ReservaInvalida, match="[Tt]elefono"):
        validar_datos_reserva(**_datos(telefono=telefono))


@pytest.mark.parametrize("telefono", ["999111222", "+51999111222", "51999111222"])
def test_telefono_con_formato_valido_se_acepta(telefono):
    """Verifica que un telefono con formato valido se acepta."""
    validar_datos_reserva(**_datos(telefono=telefono))


def test_nombre_vacio_se_rechaza():
    """Verifica que un nombre vacio (o solo espacios) se rechaza."""
    with pytest.raises(ReservaInvalida, match="nombre"):
        validar_datos_reserva(**_datos(nombre="   "))


def test_nombre_demasiado_largo_se_rechaza():
    """Verifica que un nombre mas largo que NOMBRE_MAX se rechaza."""
    with pytest.raises(ReservaInvalida, match=str(NOMBRE_MAX)):
        validar_datos_reserva(**_datos(nombre="A" * (NOMBRE_MAX + 1)))


def test_nombre_en_el_limite_se_acepta():
    """Verifica que un nombre justo en NOMBRE_MAX se acepta."""
    validar_datos_reserva(**_datos(nombre="A" * NOMBRE_MAX))


def test_notas_demasiado_largas_se_rechazan():
    """Verifica que unas notas mas largas que NOTAS_MAX se rechazan."""
    with pytest.raises(ReservaInvalida, match=str(NOTAS_MAX)):
        validar_datos_reserva(**_datos(notas="x" * (NOTAS_MAX + 1)))


def test_notas_con_caracteres_de_control_se_limpian():
    """Verifica que los caracteres de control en las notas se limpian, conservando el texto legible."""
    resultado = validar_datos_reserva(**_datos(notas="alergia al mani\x00\x07 gracias"))
    assert "\x00" not in resultado["notas"]
    assert "\x07" not in resultado["notas"]
    assert "alergia al mani" in resultado["notas"]


def test_zona_desconocida_se_rechaza():
    """Verifica que una zona fuera del catalogo se rechaza."""
    with pytest.raises(ReservaInvalida, match="zona"):
        validar_datos_reserva(**_datos(zona="vip-secreta"))


def test_zona_vacia_se_acepta_como_sin_preferencia():
    """Verifica que una zona vacia se acepta como sin preferencia."""
    resultado = validar_datos_reserva(**_datos(zona=""))
    assert resultado["zona"] == ""


def test_clave_idempotencia_es_determinista():
    """Verifica que la clave de idempotencia es determinista para los mismos datos."""
    a = clave_idempotencia("999111222", MAÑANA, "20:00", 2)
    b = clave_idempotencia("999111222", MAÑANA, "20:00", 2)
    assert a == b


def test_clave_idempotencia_distingue_datos_distintos():
    """Verifica que la clave de idempotencia distingue datos distintos (personas)."""
    a = clave_idempotencia("999111222", MAÑANA, "20:00", 2)
    b = clave_idempotencia("999111222", MAÑANA, "20:00", 3)
    assert a != b
