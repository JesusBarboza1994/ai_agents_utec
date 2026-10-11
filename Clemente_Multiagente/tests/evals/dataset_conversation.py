"""
Dataset "conversation" para evaluar al agente Clemente en LangSmith
(dataset `clemente-conversation`, suite `conversation` en langsmith/evaluador_langsmith.py).

Mide el TONO con AGENT_TONE_PROMPT de openevals, que juzga una conversacion
completa: si el tono es apropiado para el contexto y si se mantiene
consistente entre turnos. Por eso cada caso es un guion de varios mensajes del
cliente (`mensajes`) que se envian en orden dentro de la MISMA sesion, y cada
uno pone a prueba una situacion donde el tono suele fallar (enojo que escala,
insultos, confusion, un momento sensible).

Cada caso incluye:
  - mensajes: turnos del cliente, en orden
  - riesgo: situacion de tono que pone a prueba
  - referencia: tono esperado de Clemente (documenta el caso; AGENT_TONE_PROMPT
    no la usa, juzga solo la conversacion)

"""

CASOS_CONVERSATION = [
    {
        "mensajes": [
            "Llegué el sábado con reserva y no aparecía en su sistema. Me tuvieron 40 minutos "
            "parado en la puerta.",
            "¿Y eso es todo? ¿Un 'lo sentimos'? Es la segunda vez que me pasa con ustedes.",
        ],
        "riesgo": "enojo_que_escala",
        "referencia": "Reconoce la molestia sin excusas ni culpar al personal, mantiene la calma "
                      "cuando el cliente sube el tono y no se pone defensivo.",
    },
    {
        "mensajes": [
            "Son unos inútiles, nadie contesta el teléfono.",
            "Quiero reservar para 3 personas, si es que saben hacer eso.",
        ],
        "riesgo": "cliente_grosero",
        "referencia": "No responde con sarcasmo ni se ofende; sigue cordial y profesional y "
                      "avanza con la reserva.",
    },
    {
        "mensajes": [
            "¿Tienen mesa para 2 el próximo sábado a las 20:00?",
            "No entiendo, ¿entonces sí hay o no hay mesa?",
            "Perdón, es que no me quedó claro.",
        ],
        "riesgo": "cliente_confundido",
        "referencia": "Paciente y claro: responde de forma directa sin sonar condescendiente "
                      "ni repetitivo, y tranquiliza al cliente cuando se disculpa.",
    },
    {
        "mensajes": [
            "Quiero reservar para la cena de despedida de mi papá, lo operan la próxima semana "
            "y estamos un poco nerviosos.",
            "Gracias, eres muy amable.",
        ],
        "riesgo": "momento_sensible",
        "referencia": "Cálido y empático sin ser invasivo ni exagerado; no suena robótico ni "
                      "frío en un contexto que pide calidez.",
    },
    {
        "mensajes": [
            "Hola! ¿A qué hora abren los domingos?",
            "Genial, y ¿tienen opciones veganas?",
            "Perfecto, ¡muchas gracias!",
        ],
        "riesgo": "conversacion_casual",
        "referencia": "Amable y consistente en los tres turnos, sin cambios bruscos entre "
                      "formal y casual.",
    },
]
