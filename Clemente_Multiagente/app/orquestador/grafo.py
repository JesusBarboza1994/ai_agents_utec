"""
Orquestador de Clemente -- STUB TEMPORAL.

La version definitiva es un grafo LangGraph con topologia *Supervisor*, donde
un nodo enrutador clasifica el mensaje con el modelo y despacha al agente que
corresponde. La suben Christian y Jean en la rama `feat/orquestador-ruteo`.

Mientras tanto, este reemplazo enruta por palabras clave, **sin llamar a
ningun modelo**. Sirve para que el resto del equipo pueda trabajar hoy:

  * Jesus puede probar el webhook de Twilio de punta a punta sin clave de API.
  * Miguel puede ver como los agentes van a consumir su gestor de reservas.
  * Adrian recibe trazas reales de ruteo, latencia y errores.

Lo que NO cambia cuando llegue la version real: la firma `responder()` y el
contrato `MensajeEntrante` -> `RespuestaClemente`. Por eso nadie tendra que
tocar su modulo el dia que se reemplace este archivo.
"""

from ..agentes import AGENTES
from ..contratos import MensajeEntrante, RespuestaClemente
from ..observabilidad.trazas import cronometro, registrar

# Orden de prioridad del Entregable 01: un reclamo sigue siendo un reclamo
# aunque el mismo mensaje tambien pida una mesa.
PALABRAS_INCIDENCIAS = (
    "reclamo", "queja", "espere", "esperamos", "demora", "demoro", "frio", "fria",
    "mal servicio", "no me atendieron", "no aparecia", "molesto", "molesta", "pesimo",
)
PALABRAS_RESERVAS = (
    "reserva", "reservar", "mesa", "mesas", "cancelar", "cambiar", "disponibilidad",
    "cupo", "somos", "personas",
)


def elegir_ruta(texto: str) -> tuple[str, str]:
    """Devuelve (ruta, motivo). Misma decision que tomara el enrutador real."""
    minusculas = texto.lower()

    for palabra in PALABRAS_INCIDENCIAS:
        if palabra in minusculas:
            return "incidencias", f"stub: menciona '{palabra}'"

    for palabra in PALABRAS_RESERVAS:
        if palabra in minusculas:
            return "reservas", f"stub: menciona '{palabra}'"

    # Igual que en la version real: ante la duda, el agente que nunca
    # compromete capacidad del local.
    return "conocimiento", "stub: sin senales de reclamo ni de reserva"


def responder(entrante: MensajeEntrante, historial: list[dict] | None = None) -> RespuestaClemente:
    """Punto de entrada del orquestador: lo unico que llama la capa de comunicacion."""
    ruta, motivo = elegir_ruta(entrante.texto)
    registrar("ruteo", entrante.sesion_id, agente=ruta, detalle={"motivo": motivo})

    try:
        with cronometro("respuesta", entrante.sesion_id, agente=ruta):
            texto = AGENTES[ruta](entrante.texto, entrante.sesion_id, historial or [])
    except Exception as error:
        registrar("error", entrante.sesion_id, agente=ruta, detalle={"error": str(error)})
        return RespuestaClemente(
            texto=(
                "Disculpa, no puedo procesar tu mensaje en este momento. "
                "Un integrante del equipo del restaurante te va a responder."
            ),
            agente="orquestador",
            sesion_id=entrante.sesion_id,
            motivo_ruta=f"error: {error}",
            escalado=True,
        )

    return RespuestaClemente(
        texto=texto, agente=ruta, sesion_id=entrante.sesion_id, motivo_ruta=motivo
    )
