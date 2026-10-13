"""Turnos que bloqueo un control: no se le vuelven a mostrar al modelo.

El canal guarda cada mensaje del cliente antes de revisarlo, para que un fallo del modelo no haga desaparecer lo que
dijo. Por eso un "ignora tus instrucciones" queda en el historial aunque Guardrails lo haya rechazado, y se reenviaba
al planificador y a los agentes en cada turno siguiente: no aporta nada a la conversacion y puede hacer que el filtro de
contenido de Azure rechace un pedido inocente que llega despues. El turno se reconoce por la respuesta fija que dejo el
control, que tambien queda guardada; asi no hace falta marcar nada en la base.
"""

# Un control rechazo lo que escribio el cliente: se quita el turno entero, su mensaje y la respuesta.
RESPUESTA_GUARDRAILS = ("No puedo procesar instrucciones que intenten modificar o evadir "
                        "las reglas de seguridad. Reformula tu consulta sobre el restaurante.")
RESPUESTA_PII = "No envíes tarjetas, contraseñas, tokens ni claves por este canal."
TURNO_BLOQUEADO = frozenset({RESPUESTA_GUARDRAILS, RESPUESTA_PII})

# Respuestas que no dicen nada de lo conversado: se quita la respuesta y se conserva lo que pidio el cliente.
ERROR_DEL_TURNO = ("Perdón, tuve un problema para responderte. Puede que tu pedido sí se haya procesado, así que "
                   "antes de repetirlo confírmalo con el restaurante o escríbeme de nuevo en un momento.")
SALIDA_BLOQUEADA = "Perdón, no pude armar una buena respuesta esta vez. ¿Me lo cuentas de otra forma?"
# Textos anteriores (hasta 2026-10-12): siguen guardados en conversaciones viejas y hay que seguir reconociendolos.
_ERROR_DEL_TURNO_ANTERIOR = ("Disculpa, no puedo procesar tu mensaje en este momento. "
                             "No puedo asegurar que la operación se haya completado. "
                             "Consulta al restaurante antes de repetirla; tampoco puedo confirmar el envío de un aviso.")
_SALIDA_BLOQUEADA_ANTERIOR = "No puedo generar una respuesta apropiada en este momento."
SIN_CONTENIDO = frozenset({ERROR_DEL_TURNO, SALIDA_BLOQUEADA, _ERROR_DEL_TURNO_ANTERIOR, _SALIDA_BLOQUEADA_ANTERIOR})


def _texto(mensaje: dict) -> str:
    """El texto de un mensaje del historial; vacio si su contenido no es texto (por ejemplo, partes multimodales)."""
    contenido = mensaje.get("content")
    return contenido.strip() if isinstance(contenido, str) else ""


def sin_turnos_bloqueados(historial: list[dict]) -> list[dict]:
    """El historial sin los turnos que bloqueo un control, en el mismo orden.

    Ante una respuesta de TURNO_BLOQUEADO se quitan esa respuesta y los mensajes del cliente que la provocaron (texto,
    foto o audio seguidos). Ante una de SIN_CONTENIDO solo se quita la respuesta. No modifica la lista recibida."""
    limpio: list[dict] = []
    for mensaje in historial:
        if mensaje.get("role") == "assistant":
            texto = _texto(mensaje)
            if texto in TURNO_BLOQUEADO:
                while limpio and limpio[-1].get("role") == "user":
                    limpio.pop()
                continue
            if texto in SIN_CONTENIDO:
                continue
        limpio.append(mensaje)
    return limpio
