"""
Pruebas del Gestor de Reservas.

Son el contrato de Miguel escrito como codigo: si su implementacion futura
las pasa, los agentes seguiran funcionando sin cambios.
"""

import pytest


def test_hay_disponibilidad_en_turno_valido(servicio_reservas):
    opciones = servicio_reservas.consultar_disponibilidad("2026-09-12", "20:00", 4)
    assert opciones
    assert all(o.capacidad >= 4 for o in opciones)


def test_no_hay_disponibilidad_fuera_de_turno(servicio_reservas):
    assert servicio_reservas.consultar_disponibilidad("2026-09-12", "17:30", 2) == []


def test_asigna_la_mesa_mas_ajustada(servicio_reservas):
    reserva = servicio_reservas.crear_reserva(
        "Ana", "999111222", "2026-09-12", "20:00", 2, "salon"
    )
    assert reserva.mesa_id in {"M01", "M02"}   # mesas de 2, no la de 8


def test_una_mesa_no_se_reserva_dos_veces(servicio_reservas):
    libres_antes = servicio_reservas.consultar_disponibilidad("2026-09-12", "20:00", 2)
    servicio_reservas.crear_reserva("Ana", "999111222", "2026-09-12", "20:00", 2, "salon")
    libres_despues = servicio_reservas.consultar_disponibilidad("2026-09-12", "20:00", 2)
    assert len(libres_despues) == len(libres_antes) - 1


def test_cancelar_libera_la_mesa(servicio_reservas):
    reserva = servicio_reservas.crear_reserva(
        "Ana", "999111222", "2026-09-12", "20:00", 2, "salon"
    )
    servicio_reservas.cancelar_reserva(reserva.id)
    libres = [
        o.mesa_id
        for o in servicio_reservas.consultar_disponibilidad("2026-09-12", "20:00", 2)
    ]
    assert reserva.mesa_id in libres


def test_modificar_hora_conserva_la_reserva(servicio_reservas):
    reserva = servicio_reservas.crear_reserva(
        "Ana", "999111222", "2026-09-12", "20:00", 2, "salon"
    )
    modificada = servicio_reservas.modificar_reserva(reserva.id, hora="21:00")
    assert modificada is not None
    assert modificada.hora == "21:00"
    assert modificada.estado == "modificada"


def test_sin_mesa_para_el_grupo_lanza_error(servicio_reservas):
    with pytest.raises(ValueError):
        servicio_reservas.crear_reserva("Grupo", "999", "2026-09-12", "20:00", 30, "")
