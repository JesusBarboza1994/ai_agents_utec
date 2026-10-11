"""Tope de reservas activas por conversacion y por telefono, y una sola por fecha y hora.

Sin esto, una conversacion (o un telefono) podia confirmar reservas una tras otra y llenar las mesas de varios turnos.
El tope no mira cuantas se crearon "en las ultimas horas": cuenta las que existen AHORA, no estan canceladas y todavia no
pasaron. Como el restaurante solo reserva hasta 30 dias adelante (DIAS_MAX_A_FUTURO), ese es el intervalo que abarca.
Cancelar una libera su lugar, y una reserva cuya fecha ya paso deja de contar.

Se cuenta de dos maneras, y alcanza con que una se pase:
- las reservas de ESTA conversacion (las que confirmo ella), y
- las que llevan el telefono que se esta dando, aunque las hiciera otra conversacion.
Lo primero se le explica al cliente con detalle; lo segundo no: no se revela que otro telefono o conversacion tiene
reservas, igual que en `RESERVA_REPETIDA_DE_OTRA_CONVERSACION`.

El tope sale de CLEMENTE_MAX_RESERVAS_ACTIVAS (3 por defecto); un valor que no es un numero positivo se ignora.
"""
import os

from .prompts import TELEFONO_RESTAURANTE

MAXIMO_POR_DEFECTO = 3

TOPE_ALCANZADO = (
    "Ya tienes {cantidad} reservas activas, que es el máximo a la vez. Si quieres hacer otra, cancela una de las que "
    "ya tienes; si necesitas algo especial, escríbele al restaurante al " + TELEFONO_RESTAURANTE + "."
)
MISMO_TURNO = (
    "Ya tienes la reserva {reserva} para el {fecha} a las {hora}, y solo puedo tener una por turno. Si quieres "
    "cambiarla, dime y la modifico."
)
NO_SE_PUEDE_CON_ESE_TELEFONO = (
    "No puedo registrar otra reserva con ese teléfono por ahora. Si necesitas una más, el restaurante puede ayudarte "
    "al " + TELEFONO_RESTAURANTE + "."
)


def maximo() -> int:
    """Reservas activas permitidas a la vez (CLEMENTE_MAX_RESERVAS_ACTIVAS); 3 si el valor no sirve."""
    try:
        valor = int(os.getenv("CLEMENTE_MAX_RESERVAS_ACTIVAS", str(MAXIMO_POR_DEFECTO)))
    except ValueError:
        return MAXIMO_POR_DEFECTO
    return valor if valor > 0 else MAXIMO_POR_DEFECTO


def _activas(reservas, hoy: str) -> list:
    """Las que no estan canceladas y cuya fecha es hoy o futura (las fechas son AAAA-MM-DD, se comparan como texto)."""
    return [r for r in reservas if r.estado != "cancelada" and r.fecha >= hoy]


def motivo_de_rechazo(propias, del_telefono, *, telefono: str, fecha: str, hora: str, personas: int, hoy: str) -> str | None:
    """El texto para el cliente si no se puede preparar otra reserva, o None si todavia cabe.

    `propias` son las reservas de esta conversacion y `del_telefono` las que llevan el telefono dado. Repetir exactamente
    una reserva que ya existe (mismo telefono, fecha, hora y personas) no cuenta: ese caso lo resuelve el flujo que avisa
    "ya tienes una reserva con estos datos" y no crea otra."""
    propias, del_telefono = _activas(propias, hoy), _activas(del_telefono, hoy)
    if any((r.telefono, r.fecha, r.hora, r.personas) == (telefono, fecha, hora, personas) for r in propias + del_telefono):
        return None
    for reserva in propias:
        if (reserva.fecha, reserva.hora) == (fecha, hora):
            return MISMO_TURNO.format(reserva=reserva.id, fecha=fecha, hora=hora)
    if any((r.fecha, r.hora) == (fecha, hora) for r in del_telefono):
        return NO_SE_PUEDE_CON_ESE_TELEFONO
    tope = maximo()
    if len(propias) >= tope:
        return TOPE_ALCANZADO.format(cantidad=len(propias))
    if len(del_telefono) >= tope:
        return NO_SE_PUEDE_CON_ESE_TELEFONO
    return None
