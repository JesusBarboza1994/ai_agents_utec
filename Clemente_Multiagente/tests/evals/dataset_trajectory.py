"""
Dataset "trajectory" para evaluar al agente Clemente en LangSmith
(dataset `clemente-trajectory`, suite `trajectory` en langsmith/evaluador_langsmith.py).

Mide si Clemente elige las herramientas correctas, en orden y sin llamadas de
sobra, con TOOL_SELECTION_PROMPT de openevals. El juez recibe la trayectoria
del turno: mensaje del cliente, cada tool usada con su resultado y la
respuesta final. Las trazas del proyecto no guardan los argumentos de cada
tool, asi que el juez evalua QUE tools se usaron y en que orden, no con que
argumentos.

Cada caso incluye:
  - input: mensaje del cliente
  - riesgo: que decision de herramientas pone a prueba
  - referencia: secuencia de tools que pide el DISEÑO del agente (sus prompts en
    app/agentes/prompts.py), con el motivo. Se le pasa al juez como "reference
    tool sequence", que TOOL_SELECTION_PROMPT contempla en su rubrica. Sin ella el
    juez opina segun su propio criterio: el 2026-10-10 dio 0.0 al flujo de
    incidencias correcto (registrar y LUEGO buscar casos similares) porque le
    parecia mejor buscar antes.

"""

CASOS_TRAJECTORY = [
    {
        "input": "¿Tienen mesa para 4 el próximo sábado a las 20:00?",
        "riesgo": "consultar_disponibilidad",
        "referencia": "consultar_disponibilidad. Nunca afirma ni niega cupo sin llamarla antes.",
    },
    {
        "input": "¿Tienen platos veganos en la carta?",
        "riesgo": "buscar_en_catalogo",
        "referencia": "buscar_en_catalogo. La carta no está en la ficha fija del restaurante, "
                      "así que debe buscarla en el catálogo.",
    },
    {
        "input": "El plato llegó frío y nadie se acercó a la mesa en toda la noche.",
        "riesgo": "registrar_incidencia",
        "referencia": "registrar_incidencia -> buscar_casos_similares, en ese orden y en el "
                      "mismo turno. Primero registra el reclamo (con un tipo; si dudas, el "
                      "que mejor lo describa) y luego busca casos similares del histórico "
                      "con el mismo tipo, para contarle al cliente los pasos que el "
                      "restaurante suele dar. No usa tools de reservas.",
    },
    {
        "input": "¿Cuál es la dirección del restaurante?",
        "riesgo": "sin_tool_necesaria",
        "referencia": "Ninguna tool. La dirección está en la ficha fija del restaurante "
                      "(system prompt); llamar al catálogo sería una llamada de sobra.",
    },
    {
        "input": "Quiero cancelar mi reserva, el código es R-9K2M4P.",
        "riesgo": "reserva_por_codigo",
        "referencia": "consultar_reserva_por_codigo -> cancelar_reserva. Consulta la "
                      "reserva por su código antes de cancelarla; cancelar_reserva solo "
                      "PREPARA la cancelación y pide CONFIRMO. Si la reserva no existe o la "
                      "tool deniega el acceso, no sigue con cancelar_reserva.",
    },
]
