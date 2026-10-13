"""
Dataset "conversation" para evaluar al agente Clemente en LangSmith
(dataset `clemente-conversation`, suite `conversation` en langsmith/evaluador_langsmith.py).

Mide el TONO con AGENT_TONE_PROMPT de openevals, que juzga una conversacion
completa: si el tono es apropiado para el contexto y si se mantiene
consistente entre turnos. Por eso cada caso es un guion de varios mensajes del
cliente (`mensajes`) que se envian en orden dentro de la MISMA sesion, y cada
uno pone a prueba una situacion donde el tono suele fallar (enojo que escala,
insultos, confusion, un momento sensible).

Los guiones no reaccionan a lo que dice Clemente, asi que cada uno trae de
antemano lo que el agente va a necesitar para cerrar la tarea (fecha, hora,
personas, nombre, telefono, alergias) y termina con CONFIRMO cuando hay una
reserva. Si el guion se cortara antes, task_completion mediria el corte del
guion y no al agente.

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
            "Está bien, quedo atento a la respuesta del equipo.",
        ],
        "riesgo": "enojo_que_escala",
        "referencia": "Reconoce la molestia sin excusas ni culpar al personal, mantiene la calma "
                      "cuando el cliente sube el tono y no se pone defensivo.",
    },
    {
        "mensajes": [
            "Son unos inútiles, nadie contesta el teléfono.",
            "Quiero reservar para 3 personas, si es que saben hacer eso.",
            "El próximo sábado a las 20:00, a nombre de Rosa Quispe, celular 987654321. "
            "Nadie tiene alergias.",
            "CONFIRMO",
        ],
        "riesgo": "cliente_grosero",
        "referencia": "No responde con sarcasmo ni se ofende; sigue cordial y profesional y "
                      "deja la reserva confirmada.",
    },
    {
        "mensajes": [
            "¿Tienen mesa para 2 el próximo sábado a las 20:00?",
            "No entiendo, ¿entonces sí hay o no hay mesa?",
            "Perdón, es que no me quedó claro.",
            "Entonces resérvala a nombre de Luis Torres, celular 912345678, sin alergias.",
            "CONFIRMO",
        ],
        "riesgo": "cliente_confundido",
        "referencia": "Paciente y claro: responde de forma directa sin sonar condescendiente "
                      "ni repetitivo, tranquiliza al cliente cuando se disculpa y no vuelve a "
                      "pedir fecha, hora ni personas que ya dio.",
    },
    {
        "mensajes": [
            "Quiero reservar para la cena de despedida de mi papá, lo operan la próxima semana "
            "y estamos un poco nerviosos.",
            "Gracias, eres muy amable. Sería el viernes de la próxima semana a las 20:00, "
            "somos 4, a nombre de Carmen Díaz, celular 998877665. Nadie tiene alergias.",
            "CONFIRMO",
        ],
        "riesgo": "momento_sensible",
        "referencia": "Cálido y empático sin ser invasivo ni exagerado; no suena robótico ni "
                      "frío en un contexto que pide calidez, y deja la reserva confirmada.",
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
    # Flujos de punta a punta: cada guion trae todo lo que el agente necesita y
    # termina cuando la tarea quedo hecha. Miden sobre todo task_completion.
    {
        "mensajes": [
            "Hola, quiero reservar para 2 el próximo jueves a las 13:00, a nombre de Ana Ruiz, "
            "celular 955112233. Sin alergias.",
            "CONFIRMO",
            "¡Gracias!",
        ],
        "riesgo": "flujo_reserva_directa",
        "referencia": "Arma el resumen con los datos que ya dio el cliente sin volver a pedirlos, "
                      "confirma la reserva con su código y cierra cordial.",
    },
    {
        "mensajes": [
            "Quiero reservar para 2 el próximo sábado a las 19:00, a nombre de Diego Paz, "
            "celular 944556677. Sin alergias.",
            "CONFIRMO",
            "Disculpa, mejor cámbiala a las 21:00 del mismo día.",
            "CONFIRMO",
        ],
        "riesgo": "flujo_cambio_de_hora",
        "referencia": "Confirma la reserva, luego prepara el cambio de hora sobre esa misma reserva "
                      "y lo deja confirmado sin crear una reserva nueva.",
    },
    {
        "mensajes": [
            "Hola, reserva para 3 el próximo viernes a las 21:00, a nombre de Lucía Vega, "
            "celular 933445566. Sin alergias.",
            "CONFIRMO",
            "Me surgió un imprevisto, cancélala por favor.",
            "CONFIRMO",
        ],
        "riesgo": "flujo_cancelacion",
        "referencia": "Confirma la reserva y después la cancela solo tras el CONFIRMO, sin "
                      "insistir ni hacer sentir mal al cliente.",
    },
    {
        "mensajes": [
            "Ayer pedí un ceviche y llegó tibio, no estaba como siempre.",
            "Ok, gracias por registrarlo.",
        ],
        "riesgo": "flujo_reclamo_simple",
        "referencia": "Reconoce el problema, registra el reclamo una sola vez con su código y "
                      "plazo, y cierra sin prometer compensaciones.",
    },
    {
        "mensajes": [
            "¿Aceptan mascotas en el restaurante?",
            "¿Y tienen estacionamiento?",
            "Genial, gracias.",
        ],
        "riesgo": "flujo_consulta_informacion",
        "referencia": "Responde las dos preguntas con la política y la ficha del restaurante, "
                      "sin inventar condiciones.",
    },
]
