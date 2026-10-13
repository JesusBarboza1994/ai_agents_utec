"""
Dataset "rag" para evaluar al agente Clemente en LangSmith
(dataset `clemente-rag`, suite `rag` en langsmith/evaluador_langsmith.py).

Cubre los DOS indices de Azure AI Search (aiclmt01) que usa el agente:
  - catalogo-clemente (13 chunks de 01_horarios_y_ubicacion, 02_carta_y_servicios y
    03_politicas): preguntas cuya respuesta NO esta en la ficha fija del restaurante,
    asi que Clemente la recupera con `buscar_en_catalogo` / `consultar_politica`.
  - incidencias-clemente (30 casos resueltos, caso_01..caso_30): reclamos para los
    que Clemente registra la incidencia y recupera un caso parecido con
    `buscar_casos_similares`, para contarle al cliente que se hara.
`riesgo` empieza con `catalogo_` o `incidencias_` segun el indice que pone a prueba.

Se evaluan con dos prompts RAG de openevals:
  - RAG_RETRIEVAL_RELEVANCE_PROMPT: lo recuperado es relevante para la pregunta.
  - RAG_HELPFULNESS_PROMPT: la respuesta es util para la pregunta.

Cada caso incluye:
  - input: pregunta del cliente
  - riesgo: que parte del catalogo o del historico de incidencias pone a prueba
  - referencia: dato correcto del catalogo (contenedor `catalogo` del Blob) o el
    caso del historico que deberia recuperarse; documenta el caso, los prompts RAG
    no la usan
"""

CASOS_RAG = [
    {
        "input": "¿Tienen platos veganos en la carta?",
        "riesgo": "catalogo_opciones_veganas",
        "referencia": "Dos platos marcados como veganos en carta; la cocina adapta el risotto "
                      "y la causa bajo pedido.",
    },
    {
        "input": "¿Puedo llevar mi propia torta de cumpleaños?",
        "riesgo": "catalogo_celebraciones",
        "referencia": "Sí, se permite ingresar torta propia sin costo de descorche de "
                      "repostería.",
    },
    {
        "input": "¿Con cuánta anticipación puedo hacer una reserva?",
        "riesgo": "catalogo_anticipacion",
        "referencia": "Hasta 30 días de anticipación y como mínimo 2 horas antes del turno.",
    },
    {
        "input": "Si llego tarde, ¿cuánto tiempo me guardan la mesa?",
        "riesgo": "catalogo_tolerancia",
        "referencia": "La mesa se mantiene 20 minutos desde la hora reservada; pasado ese "
                      "tiempo se libera.",
    },
    {
        "input": "¿Tienen menú de almuerzo entre semana?",
        "riesgo": "catalogo_menu_almuerzo",
        "referencia": "Sí, menú de almuerzo de martes a viernes, de 12:00 a 15:00.",
    },
    # ---------------------------------------------------- indice incidencias-clemente
    {
        "input": "Pedí un plato vegano y me llegó con mantequilla. Soy vegana, no puede ser.",
        "riesgo": "incidencias_vegano_con_mantequilla",
        "referencia": "Caso parecido esperado: caso_23_plato_vegano_con_mantequilla.md.",
    },
    {
        "input": "Revisé mi estado de cuenta y me cobraron dos veces la cena de anoche con la "
                 "tarjeta.",
        "riesgo": "incidencias_cobro_duplicado",
        "referencia": "Caso parecido esperado: caso_04_cobro_duplicado_tarjeta.md.",
    },
    {
        "input": "Encontré un pelo en mi plato de lomo saltado, qué asco.",
        "riesgo": "incidencias_objeto_extrano",
        "referencia": "Caso parecido esperado: caso_07_objeto_extrano_plato.md.",
    },
    {
        "input": "La música estaba tan alta anoche que no podíamos conversar en la mesa.",
        "riesgo": "incidencias_musica_alta",
        "referencia": "Caso parecido esperado: caso_18_musica_muy_alta.md.",
    },
    {
        "input": "Llegué 25 minutos tarde a mi reserva y ya le habían dado la mesa a otra "
                 "persona.",
        "riesgo": "incidencias_reserva_liberada",
        "referencia": "Caso parecido esperado: caso_09_reserva_liberada_20_min.md.",
    },
]
