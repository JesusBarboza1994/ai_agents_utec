"""
Agente de Reservas y Capacidad.

Es el unico de los tres que escribe un compromiso que el restaurante tendra
que honrar en sala; por eso es el que mas control lleva encima: doble
verificacion de disponibilidad, confirmacion explicita del cliente y limite
duro de grupo antes de escalar.
"""

import logging
from datetime import date, timedelta

from ..observabilidad.trazas import registrar
from ..reservas.validaciones import (
    DIAS_MAX_A_FUTURO, TELEFONO_RE, TURNOS_VALIDOS, ReservaInvalida, validar_nombre,
)
from . import fecha as reloj
from .base import construir_agente, ejecutar, id_de_hilo, reanudar_revision
from .contexto import ContextoConversacion
from .prompts import PROMPT_RESERVAS
from .tools.catalogo_tools import consultar_politica
from .tools.cliente_tools import actualizar_datos_cliente
from .tools.fecha_tools import get_current_datetime
from .tools.reservas_tools import (
    LIMITE_GRUPO_AUTONOMO,
    buscar_mis_reservas,
    cancelar_reserva,
    consultar_disponibilidad,
    consultar_reserva_por_codigo,
    crear_reserva,
    escalar_a_staff,
    modificar_reserva,
    solicitar_excepcion_grupo,
)

log = logging.getLogger("clemente")

FLUJO = "reservas"

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
    global _agente
    if _agente is None:
        from langchain.agents.middleware import HumanInTheLoopMiddleware

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
            checkpointer=_obtener_checkpointer(),
        )
    return _agente


def _obtener_checkpointer():
    """SqliteSaver de los hilos de reservas, creado una sola vez y sin instanciar el modelo.

    Separarlo del agente permite revisar o liberar una pausa (cancelacion del
    cliente, vencimiento, reinicio) sin construir el modelo ni llamar a la API."""
    global _checkpointer
    if _checkpointer is None:
        import sqlite3
        from pathlib import Path
        from langgraph.checkpoint.sqlite import SqliteSaver
        from ..datos import carpeta_de_datos

        archivo = carpeta_de_datos(Path(__file__).resolve().parent / "datos") / "hitl_checkpoints.sqlite3"
        archivo.parent.mkdir(parents=True, exist_ok=True)
        _checkpointer = SqliteSaver(sqlite3.connect(archivo, check_same_thread=False))
    return _checkpointer


def tiene_hilo_guardado(sesion_id: str) -> bool:
    """True si queda un checkpoint del hilo de reservas de la sesion.

    `ejecutar` borra el checkpoint al terminar cada turno sin pausa, asi que entre
    turnos solo sobrevive el de un hilo que espera la decision del staff. Si no se
    puede leer, devuelve False y no se toca nada."""
    try:
        return _obtener_checkpointer().get_tuple(
            {"configurable": {"thread_id": id_de_hilo(FLUJO, sesion_id)}}
        ) is not None
    except Exception as error:
        log.warning("No se pudo leer el hilo de reservas: %s", type(error).__name__)
        return False


def liberar_pausa(sesion_id: str) -> bool:
    """Borra el checkpoint del hilo de reservas de una sola sesion; True si quedo borrado.

    Libera un hilo que esperaba al staff sin reanudar al agente: no se llama al
    modelo ni a ninguna herramienta. Un fallo se registra y devuelve False, para
    que quien llama no anuncie una cancelacion que no ocurrio."""
    try:
        _obtener_checkpointer().delete_thread(id_de_hilo(FLUJO, sesion_id))
        return True
    except Exception as error:
        log.warning("No se pudo liberar el hilo de reservas: %s", type(error).__name__)
        return False


def _argumentos_de_la_solicitud(solicitud) -> list[dict] | None:
    """Argumentos de cada pedido de excepcion de la interrupcion, o None si la forma no es la esperada.

    Solo reconoce pedidos de `solicitar_excepcion_grupo` con `args` como dict; ante
    cualquier otra forma no se prevalida y la solicitud se encola como siempre."""
    if not isinstance(solicitud, dict):
        return None
    pedidos = solicitud.get("action_requests")
    if not isinstance(pedidos, list) or not pedidos:
        return None
    argumentos = []
    for pedido in pedidos:
        if (not isinstance(pedido, dict) or pedido.get("name") != "solicitar_excepcion_grupo"
                or not isinstance(pedido.get("args"), dict)):
            return None
        argumentos.append(pedido["args"])
    return argumentos


def _motivo_rechazo_excepcion(args: dict) -> str | None:
    """Texto para el cliente si la solicitud de grupo no puede pasar al staff; None si es valida.

    Aplica solo controles compatibles con una excepcion: formato y dia de la fecha,
    fecha no pasada y dentro de la politica, turno valido y dentro de horario, que el
    grupo realmente supere el limite y que haya nombre y telefono. No usa
    `validar_cambio_turno` (exige de 1 a 10 personas) ni la anticipacion minima,
    que decide el staff."""
    texto_fecha = str(args.get("fecha") or "")
    hora = str(args.get("hora") or "")
    try:
        fecha = date.fromisoformat(texto_fecha)
    except ValueError:
        return "Para pasar tu solicitud al equipo necesito la fecha exacta. ¿Para qué día sería?"
    contradiccion = reloj.contradiccion_dia(str(args.get("dia_semana") or ""), texto_fecha)
    if contradiccion:
        return (f"El {texto_fecha} cae {reloj.nombre_dia(fecha)} y no coincide con el día que me dijiste. "
                "¿Cuál de los dos es el correcto?")
    if fecha < reloj.hoy():
        return "Esa fecha ya pasó, así que no pude pasar tu solicitud al equipo. ¿Para qué día la necesitas?"
    if fecha > reloj.hoy() + timedelta(days=DIAS_MAX_A_FUTURO):
        return (f"Solo tomamos solicitudes hasta {DIAS_MAX_A_FUTURO} días adelante. "
                "¿Te parece una fecha más cercana?")
    if hora not in TURNOS_VALIDOS:
        return f"Los turnos que se reservan son {', '.join(TURNOS_VALIDOS)}. ¿Cuál prefieres?"
    if fecha == reloj.hoy() and hora <= reloj.ahora().strftime("%H:%M"):
        return "Ese horario de hoy ya pasó. ¿Te parece otro turno u otro día?"
    if not reloj.HORARIO[fecha.weekday()]:
        return (f"Los {reloj.nombre_dia(fecha)} el restaurante no atiende, así que no pude pasar tu "
                "solicitud al equipo. ¿Te parece otro día?")
    if not reloj.turno_atendido(fecha.weekday(), hora):
        turnos = ", ".join(reloj.turnos_del_dia(fecha.weekday(), TURNOS_VALIDOS))
        return (f"Ese {reloj.nombre_dia(fecha)} a las {hora} el restaurante no atiende; ese día los turnos "
                f"son {turnos}. ¿Te parece alguno?")
    try:
        personas = int(args.get("personas"))
    except (TypeError, ValueError):
        return "¿Cuántas personas serían en total?"
    if personas <= LIMITE_GRUPO_AUTONOMO:
        return (f"Para {personas} personas no hace falta que lo apruebe el equipo: puedo revisar la "
                "disponibilidad ahora mismo. ¿Lo hago?")
    try:
        validar_nombre(str(args.get("nombre") or ""))
    except ReservaInvalida:
        return "Para pasar tu solicitud al equipo necesito tu nombre. ¿A nombre de quién sería?"
    telefono = "".join(c for c in str(args.get("telefono") or "") if c not in " ().-")
    if not TELEFONO_RE.match(telefono):
        return "Para pasar tu solicitud al equipo necesito un teléfono de contacto. ¿Me lo compartes?"
    return None


def _descartar_excepcion_invalida(sesion_id: str, contexto: ContextoConversacion) -> str | None:
    """Si la solicitud pausada es invalida, la descarta sin llamar al modelo y devuelve el texto para el cliente.

    Devuelve None si la solicitud es valida, si su forma no es la esperada o si no se
    pudo borrar la pausa: en esos casos se encola como siempre y decide el staff."""
    revision = contexto.datos.get("revision_humana") or {}
    if revision.get("estado") != "pendiente":
        return None
    argumentos = _argumentos_de_la_solicitud(revision.get("solicitud"))
    if argumentos is None:
        return None
    motivo = next((m for m in map(_motivo_rechazo_excepcion, argumentos) if m), None)
    if motivo is None:
        return None
    if not liberar_pausa(sesion_id):
        registrar("prevalidacion_no_aplicada", sesion_id, agente=FLUJO, detalle={"motivo": motivo})
        return None
    contexto.datos.pop("revision_humana", None)
    escalamiento = contexto.datos.get("escalamiento") or {}
    if str(escalamiento.get("origen", "")).startswith("reservas"):
        # La misma solicitud invalida no puede llegar al staff por otra via en este turno.
        contexto.escalado = False
        contexto.datos.pop("escalamiento", None)
    registrar("hitl_rechazo_automatico", sesion_id, agente=FLUJO, detalle={"motivo": motivo})
    return motivo


def responder(
    texto: str, sesion_id: str, historial: list[dict] | None = None,
    contexto: ContextoConversacion | None = None,
) -> str:
    """Ejecuta el agente de reservas con texto, sesion, historial y contexto.

    Devuelve texto o el fallback si el modelo escribe una tool como texto;
    una interrupcion HITL valida queda registrada en contexto para la cola del
    personal. Una solicitud de grupo invalida (dia cerrado, fecha pasada, datos
    faltantes) se descarta antes de llegar al staff y se responde un texto fijo.
    Los errores de invocacion se propagan al orquestador."""
    contexto = contexto or ContextoConversacion(sesion_id=sesion_id)
    respuesta = ejecutar(
        obtener_agente(), texto, sesion_id, historial, contexto=contexto,
        fallback="Perdona, se me cruzo la linea. Me confirmas fecha, hora y cuantas personas son?",
        flujo=FLUJO,
    )
    return _descartar_excepcion_invalida(sesion_id, contexto) or respuesta


def resolver_revision(sesion_id: str, decision: dict, contexto: ContextoConversacion) -> str:
    """Reanuda el agente de reservas pausado en sesion_id con la decision del personal.

    Usa el checkpoint del mismo hilo y el contexto de negocio recibido;
    devuelve el texto producido por reanudar_revision."""
    return reanudar_revision(obtener_agente(), sesion_id, decision, contexto, FLUJO)


def reiniciar() -> None:
    """Fuerza reconstruir el agente. Lo usan los tests y el banco de modelos:
    el modelo se resuelve al construirlo, asi que cambiar de modelo sin esto
    seguiria corriendo el anterior."""
    global _agente
    _agente = None
