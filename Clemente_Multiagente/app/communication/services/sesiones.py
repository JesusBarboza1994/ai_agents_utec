"""
Memoria de conversacion por sesion -- responsable: Jesus.

Guarda el historial de cada hilo para que el agente no pierda el contexto
entre mensajes. Es memoria de CORTO PLAZO: solo turnos de texto, acotada, y
hoy en memoria del proceso (se pierde al reiniciar Flask).

Evolucion prevista (Sesion 9, memoria de largo plazo): mover esto a Redis o
SQLite y separar el perfil del cliente -- nombre, telefono, preferencias,
alergias -- que si debe sobrevivir a la conversacion.
"""

from dataclasses import dataclass, field

# Cuantos turnos se conservan por sesion. La ventana de contexto es un recurso
# escaso (Sesion 9): no se manda la conversacion entera en cada llamada.
MAXIMO_TURNOS = 20


@dataclass
class Sesion:
    """Datos e historial acotado de un hilo de chat, conservados en memoria del proceso."""
    sesion_id: str
    canal: str = "webchat"
    nombre_cliente: str | None = None
    telefono: str | None = None
    historial: list[dict] = field(default_factory=list)
    ultimo_agente: str = ""

    def agregar(self, rol: str, contenido: str) -> None:
        """Agrega rol y contenido al historial y conserva los ultimos MAXIMO_TURNOS mensajes."""
        self.historial.append({"role": rol, "content": contenido})
        if len(self.historial) > MAXIMO_TURNOS:
            self.historial = self.historial[-MAXIMO_TURNOS:]


_sesiones: dict[str, Sesion] = {}


def obtener_sesion(sesion_id: str, canal: str = "webchat") -> Sesion:
    """Devuelve la sesion en memoria o crea una con sesion_id y canal si no existe."""
    if sesion_id not in _sesiones:
        _sesiones[sesion_id] = Sesion(sesion_id=sesion_id, canal=canal)
    return _sesiones[sesion_id]


def limpiar_sesion(sesion_id: str) -> None:
    """Retira la sesion del registro en memoria; no falla si no existe ni borra reservas."""
    _sesiones.pop(sesion_id, None)


def sesiones_activas() -> list[str]:
    """Devuelve los identificadores de sesiones actualmente presentes en memoria."""
    return list(_sesiones)
