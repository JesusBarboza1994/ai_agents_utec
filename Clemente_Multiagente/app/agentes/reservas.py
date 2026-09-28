"""
Agente de Reservas y Capacidad.

Es el unico de los tres que escribe un compromiso que el restaurante tendra
que honrar en sala; por eso es el que mas control lleva encima: doble
verificacion de disponibilidad, confirmacion explicita del cliente y limite
duro de grupo antes de escalar.
"""

from .base import construir_agente, ejecutar, reanudar_revision
from .contexto import ContextoConversacion
from .prompts import PROMPT_RESERVAS
from .tools.catalogo_tools import consultar_politica
from .tools.cliente_tools import actualizar_datos_cliente
from .tools.fecha_tools import get_current_datetime
from .tools.reservas_tools import (
    buscar_mis_reservas,
    cancelar_reserva,
    consultar_disponibilidad,
    consultar_reserva_por_codigo,
    crear_reserva,
    escalar_a_staff,
    modificar_reserva,
    solicitar_excepcion_grupo,
)

_checkpointer = None

TOOLS = [
    consultar_disponibilidad,
    crear_reserva,
    buscar_mis_reservas,
    consultar_reserva_por_codigo,   # el cliente suele traer el codigo, no el telefono
    modificar_reserva,
    cancelar_reserva,
    escalar_a_staff,
    solicitar_excepcion_grupo,
    actualizar_datos_cliente,   # guarda nombre/apellido/DNI que el cliente da al identificarse
    consultar_politica,   # fuente unica de verdad: no duplicamos las politicas aqui
    get_current_datetime,   # "manana" y "este viernes" salen del reloj de Lima, no del modelo
]

_agente = None


def obtener_agente():
    """Construye y reutiliza el agente de reservas con checkpoint SQLite y middleware HITL.

    Instancia el modelo en la primera llamada, no al importar. Configura
    solicitar_excepcion_grupo para interrumpirse antes de ejecutar y permite
    approve o reject. El checkpoint persiste el estado del hilo; no sustituye
    las reservas del servicio JSON ni los permisos de autorizacion.
    """
    global _agente, _checkpointer
    if _agente is None:
        import sqlite3
        from pathlib import Path
        from langchain.agents.middleware import HumanInTheLoopMiddleware
        from langgraph.checkpoint.sqlite import SqliteSaver
        from ..datos import carpeta_de_datos

        archivo = carpeta_de_datos(Path(__file__).resolve().parent / "datos") / "hitl_checkpoints.sqlite3"
        archivo.parent.mkdir(parents=True, exist_ok=True)
        conexion = sqlite3.connect(archivo, check_same_thread=False)
        _checkpointer = SqliteSaver(conexion)

        _agente = construir_agente(
            PROMPT_RESERVAS,
            TOOLS,
            middleware=[HumanInTheLoopMiddleware(
                interrupt_on={
                    "solicitar_excepcion_grupo": {
                        "allowed_decisions": ["approve", "reject"],
                        "description": "Revisar excepción de capacidad para un grupo grande",
                    }
                },
                description_prefix="Autorización del staff requerida",
            )],
            checkpointer=_checkpointer,
        )
    return _agente


def responder(
    texto: str, sesion_id: str, historial: list[dict] | None = None,
    contexto: ContextoConversacion | None = None,
) -> str:
    """Ejecuta el agente de reservas con texto, sesion, historial y contexto.

    Devuelve texto o el fallback si el modelo escribe una tool como texto;
    una interrupcion HITL queda registrada en contexto para la cola del
    personal. Los errores de invocacion se propagan al orquestador."""
    return ejecutar(
        obtener_agente(), texto, sesion_id, historial, contexto=contexto,
        fallback="Perdona, se me cruzo la linea. Me confirmas fecha, hora y cuantas personas son?",
        flujo="reservas",
    )


def resolver_revision(sesion_id: str, decision: dict, contexto: ContextoConversacion) -> str:
    """Reanuda el agente de reservas pausado en sesion_id con la decision del personal.

    Usa el checkpoint del mismo hilo y el contexto de negocio recibido;
    devuelve el texto producido por reanudar_revision."""
    return reanudar_revision(obtener_agente(), sesion_id, decision, contexto, "reservas")


def reiniciar() -> None:
    """Fuerza reconstruir el agente. Lo usan los tests y el banco de modelos:
    el modelo se resuelve al construirlo, asi que cambiar de modelo sin esto
    seguiria corriendo el anterior."""
    global _agente
    _agente = None
