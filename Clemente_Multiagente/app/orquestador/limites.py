"""
Limites por conversacion: tamano del mensaje, frecuencia y un turno a la vez.

Sin esto, cada mensaje arranca una ejecucion completa (planificador, agente,
herramientas) sin importar cuantos lleguen ni cuan largos sean. Los tres
limites se aplican ANTES de tocar el modelo, y solo miran la conversacion que
escribe: un cliente que abusa se limita a si mismo.

Viven en la memoria del proceso. Con una sola replica (como hoy) alcanza; con
varias, cada replica llevaria su propia cuenta y el turno unico no se
garantizaria entre replicas. Los limites por numero de telefono o por IP
pertenecen a la capa de comunicacion.
"""

import os
import threading
import time
from collections import deque
from contextlib import contextmanager

MENSAJE_LARGO = "Tu mensaje es demasiado largo para leerlo bien. ¿Me lo cuentas en pocas líneas?"
MENSAJE_RAPIDO = "Estás escribiendo muy rápido y no puedo seguirte. Dame un momento y vuelve a escribirme."
MENSAJE_OCUPADO = "Sigo con tu mensaje anterior. Cuando te responda, escríbeme de nuevo."

VENTANA_SEGUNDOS = 60
ESPERA_TURNO_SEGUNDOS = 90

_guarda = threading.Lock()
_recientes: dict[str, deque] = {}
_turnos: dict[str, list] = {}


def maximo_caracteres() -> int:
    """Largo maximo de un mensaje (CLEMENTE_MAX_CARACTERES_MENSAJE, 2000)."""
    return int(os.getenv("CLEMENTE_MAX_CARACTERES_MENSAJE", "2000"))


def maximo_por_minuto() -> int:
    """Mensajes por conversacion y minuto antes de limitar (CLEMENTE_MAX_MENSAJES_MINUTO, 12)."""
    return int(os.getenv("CLEMENTE_MAX_MENSAJES_MINUTO", "12"))


def demasiado_largo(texto: str) -> bool:
    """True si el mensaje supera el largo maximo."""
    return len(texto or "") > maximo_caracteres()


def excede_frecuencia(sesion_id: str) -> bool:
    """Cuenta este mensaje y dice si la conversacion supero el maximo del ultimo minuto.

    Los mensajes limitados tambien cuentan: quien insiste sigue limitado mientras insista."""
    ahora = time.monotonic()
    with _guarda:
        cola = _recientes.setdefault(sesion_id, deque())
        while cola and ahora - cola[0] > VENTANA_SEGUNDOS:
            cola.popleft()
        cola.append(ahora)
        if len(_recientes) > 5000:
            for sid in [s for s, c in _recientes.items() if not c or ahora - c[-1] > VENTANA_SEGUNDOS]:
                del _recientes[sid]
        return len(cola) > maximo_por_minuto()


@contextmanager
def un_turno_a_la_vez(sesion_id: str):
    """Serializa los turnos de una misma conversacion; cede True si obtuvo el turno, False si vencio la espera.

    Dos mensajes simultaneos de un cliente ya no leen y escriben a la vez la
    propuesta, la continuidad ni el ticket. Otras conversaciones no se bloquean."""
    with _guarda:
        entrada = _turnos.setdefault(sesion_id, [threading.Lock(), 0])
        entrada[1] += 1
    obtenido = entrada[0].acquire(timeout=ESPERA_TURNO_SEGUNDOS)
    try:
        yield obtenido
    finally:
        if obtenido:
            entrada[0].release()
        with _guarda:
            entrada[1] -= 1
            if entrada[1] == 0:
                _turnos.pop(sesion_id, None)


def reiniciar() -> None:
    """Vacia los contadores y turnos en memoria; lo usan las pruebas."""
    with _guarda:
        _recientes.clear()
        _turnos.clear()
