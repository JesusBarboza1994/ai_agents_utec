"""
Dataset "quality" para evaluar al agente Clemente en LangSmith
(dataset `clemente-quality`, suite `quality` en langsmith/evaluador_langsmith.py).

Preguntas de informacion con una respuesta correcta conocida. Se evaluan con
tres prompts de openevals:
  - CORRECTNESS_PROMPT: compara la respuesta contra `referencia`.
  - HALLUCINATION_PROMPT: que no afirme nada que no este en el contexto (la ficha
    fija del restaurante + lo que devolvieron las tools en ese turno).
  - CONCISENESS_PROMPT: que responda sin relleno.

Por eso `referencia` aqui es LA RESPUESTA CORRECTA, sacada textual del
catalogo validado (app/agentes/rag/documentos/*.md) o de FICHA_DEL_RESTAURANTE
(app/agentes/prompts.py); si el catalogo cambia, hay que actualizarla.

Cada caso incluye:
  - input: pregunta del cliente
  - riesgo: que dato pone a prueba
  - referencia: respuesta correcta esperada
"""

CASOS_QUALITY = [
    {
        "input": "¿Hasta cuándo puedo cancelar mi reserva sin pagar nada?",
        "riesgo": "politica_cancelacion",
        "referencia": "La cancelación es libre y sin costo hasta 3 horas antes del turno "
                      "reservado.",
    },
    {
        "input": "Si llevo mi propia botella de vino, ¿cuánto me cobran?",
        "riesgo": "descorche",
        "referencia": "El descorche de vino cuesta S/ 40 por botella.",
    },
    {
        "input": "Soy celíaco, ¿tienen opciones sin gluten?",
        "riesgo": "sin_gluten_y_alergias",
        "referencia": "Hay platos marcados con 'SG', pero la cocina no tiene un área libre de "
                      "gluten certificada, así que no se garantiza la ausencia total de "
                      "trazas. La alergia o condición debe declararse al reservar y repetirse "
                      "al mozo al llegar.",
    },
    {
        "input": "¿A qué hora abren los domingos y hasta qué hora toman pedidos?",
        "riesgo": "horario_domingo",
        "referencia": "Los domingos abren solo de 12:00 a 17:00. La cocina toma el último "
                      "pedido 45 minutos antes de cerrar, es decir a las 16:15.",
    },
    {
        "input": "¿Hacen delivery a domicilio?",
        "riesgo": "servicio_inexistente",
        "referencia": "No, el restaurante no tiene servicio de delivery propio por ahora.",
    },
]
