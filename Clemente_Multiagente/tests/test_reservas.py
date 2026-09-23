"""
Pruebas del Gestor de Reservas.

Son el contrato de Miguel escrito como codigo: si su implementacion futura
las pasa, los agentes seguiran funcionando sin cambios.
"""

from datetime import date, timedelta

import pytest

# Relativa a hoy a proposito: con la validacion de "fecha no puede estar en
# el pasado" (validaciones.py), una fecha fija se hubiera vuelto invalida
# sola con el paso del tiempo y roto la suite sin que nadie tocara nada.
FECHA = str(date.today() + timedelta(days=3))


def test_hay_disponibilidad_en_turno_valido(servicio_reservas):
    opciones = servicio_reservas.consultar_disponibilidad(FECHA, "20:00", 4)
    assert opciones
    assert all(o.capacidad >= 4 for o in opciones)


def test_no_hay_disponibilidad_fuera_de_turno(servicio_reservas):
    assert servicio_reservas.consultar_disponibilidad(FECHA, "17:30", 2) == []


def test_asigna_la_mesa_mas_ajustada(servicio_reservas):
    """Verifica que asigna la mesa mas ajustada."""
    reserva = servicio_reservas.crear_reserva(
        "Ana", "999111222", FECHA, "20:00", 2, "salon"
    )
    assert reserva.mesa_id in {"M01", "M02"}   # mesas de 2, no la de 8


def test_una_mesa_no_se_reserva_dos_veces(servicio_reservas):
    libres_antes = servicio_reservas.consultar_disponibilidad(FECHA, "20:00", 2)
    servicio_reservas.crear_reserva("Ana", "999111222", FECHA, "20:00", 2, "salon")
    libres_despues = servicio_reservas.consultar_disponibilidad(FECHA, "20:00", 2)
    assert len(libres_despues) == len(libres_antes) - 1


def test_cancelar_libera_la_mesa(servicio_reservas):
    """Verifica que cancelar libera la mesa."""
    reserva = servicio_reservas.crear_reserva(
        "Ana", "999111222", FECHA, "20:00", 2, "salon"
    )
    servicio_reservas.cancelar_reserva(reserva.id)
    libres = [
        o.mesa_id
        for o in servicio_reservas.consultar_disponibilidad(FECHA, "20:00", 2)
    ]
    assert reserva.mesa_id in libres


def test_modificar_hora_conserva_la_reserva(servicio_reservas):
    """Verifica que modificar hora conserva la reserva."""
    reserva = servicio_reservas.crear_reserva(
        "Ana", "999111222", FECHA, "20:00", 2, "salon"
    )
    modificada = servicio_reservas.modificar_reserva(reserva.id, hora="21:00")
    assert modificada is not None
    assert modificada.hora == "21:00"
    assert modificada.estado == "modificada"


def test_sin_mesa_para_el_grupo_lanza_error(servicio_reservas):
    """Verifica que sin mesa para el grupo lanza error."""
    with pytest.raises(ValueError):
        servicio_reservas.crear_reserva("Grupo", "999111222", FECHA, "20:00", 30, "")


def test_datos_invalidos_lanzan_error_sin_escribir_nada(servicio_reservas):
    with pytest.raises(ValueError):
        servicio_reservas.crear_reserva("Ana", "999111222", FECHA, "17:30", 2, "salon")
    assert servicio_reservas.consultar_disponibilidad(FECHA, "20:00", 2)  # nada quedo ocupado


def test_crear_reserva_es_idempotente_para_el_mismo_pedido(servicio_reservas):
    """Mismo telefono+fecha+hora+personas dos veces = una sola reserva, no dos
    mesas ocupadas. Simula un reintento de webhook o un doble tap."""
    r1 = servicio_reservas.crear_reserva("Ana", "999111222", FECHA, "20:00", 2, "salon")
    r2 = servicio_reservas.crear_reserva("Ana", "999111222", FECHA, "20:00", 2, "salon")
    assert r1.id == r2.id
    assert r1.mesa_id == r2.mesa_id


def test_idempotencia_no_bloquea_un_pedido_distinto(servicio_reservas):
    r1 = servicio_reservas.crear_reserva("Ana", "999111222", FECHA, "20:00", 2, "salon")
    r2 = servicio_reservas.crear_reserva("Ana", "999111222", FECHA, "20:00", 4, "salon")
    assert r1.id != r2.id
