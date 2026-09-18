"""
Degradacion por abuso -- responsables: Christian, Jean (seccion 3.2 del plan).

Cuenta los rechazos del servidor por sesion (autorizacion denegada,
confirmacion invalida) dentro de una ventana. Un error humano aislado no
pasa nada; al superar el maximo, el orquestador responde con un texto fijo
sin invocar al modelo durante la ventana: intentos repetidos de adivinar
codigos o reservas ajenas no consumen razonamiento ilimitado, y la
degradacion queda trazada.

Limita coste y superficie, no identidad: la identidad la da el canal. El
limite por frecuencia de mensajes (rate limit HTTP) pertenece a la capa de
comunicacion y no se implementa aqui.
"""

import os

from ..observabilidad.trazas import registrar
from . import almacen

MENSAJE_DEGRADADO = (
    "Hubo varios intentos rechazados en esta conversación. Por seguridad, durante unos "
    "minutos no puedo gestionar reservas ni reclamos por aquí; si necesitas algo urgente, "
    "comunícate directamente con el restaurante."
)


def maximo_rechazos() -> int:
    """Rechazos permitidos en la ventana antes de degradar (CLEMENTE_MAX_RECHAZOS, 5)."""
    return int(os.getenv("CLEMENTE_MAX_RECHAZOS", "5"))


def ventana_segundos() -> int:
    """Tamano de la ventana de conteo en segundos (CLEMENTE_ABUSO_VENTANA, 600)."""
    return int(os.getenv("CLEMENTE_ABUSO_VENTANA", "600"))


def registrar_rechazo(sesion_id: str, motivo: str) -> int:
    """Anota un rechazo de la sesion y devuelve cuantos lleva en la ventana."""
    almacen.registrar_rechazo(sesion_id, motivo)
    total = almacen.contar_rechazos(sesion_id, ventana_segundos())
    registrar("rechazo", sesion_id, detalle={"motivo": motivo, "en_ventana": total})
    return total


def degradado(sesion_id: str) -> bool:
    """True si la sesion supero el maximo de rechazos en la ventana; deja traza al degradar."""
    total = almacen.contar_rechazos(sesion_id, ventana_segundos())
    if total < maximo_rechazos():
        return False
    registrar("abuso_degradado", sesion_id, detalle={"rechazos": total, "ventana_s": ventana_segundos()})
    return True
