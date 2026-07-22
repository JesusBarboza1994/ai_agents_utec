"""
02_goal_based_agent.py
--------------------------
AGENTE BASADO EN OBJETIVOS (Goal-Based Agent)
(IBM: https://www.ibm.com/think/topics/goal-based-agent)

Aplicado a: "Clemente Reservations" — agente conversacional de reservas de
restaurante (ver agent_card_profile_reserva_v2.html).

Por qué este tipo de agente encaja con la Autonomy Dimension y la
Criticality Dimension del profile card:
La Autonomy Dimension define al agente como "Semi-autonomous": evalúa
disponibilidad, RECOMIENDA horarios, GUÍA la reserva hasta crear una
solicitud pendiente, pero ESCALA los casos especiales. Eso no es una
reacción a un único estímulo (reflejo) ni solo "recordar" (modelo
interno): es perseguir una META explícita -- "reserva confirmada y
registrada, respetando políticas" -- razonando varios pasos hacia
adelante: si la hora pedida no está libre, hay que REPLANIFICAR
buscando alternativas antes de darse por vencido. Además, la
Criticality Dimension exige guardrails que solo tienen sentido en un
flujo dirigido a una meta: confirmación explícita antes de crear/
modificar/cancelar, y escalar a un humano "después de varios intentos
fallidos". Este archivo modela exactamente ese ciclo: intento ->
replanificación -> reintento -> escalamiento si la meta no se alcanza.

Este agente es complementario al modelo interno (memoria) de
01_model_based_reflex_agent.py: aquí el foco es el RAZONAMIENTO hacia la
meta, no la persistencia de estado, siguiendo la misma separación de
responsabilidades que distingue 02_model_based_reflex_agent.py de
03_goal_based_agent.py en /Examples.

Este archivo es completamente autocontenido: no depende de otros
archivos de la carpeta (solo de librerías externas).

Ejecutar:
    ollama pull llama3.2
    python 02_goal_based_agent.py
"""

from langchain.agents import create_agent
from langchain.tools import tool

# --- "Entorno" simulado: restaurante Clemente -------------------------------

MESAS = {
    "M1": {"zona": "salon", "capacidad": 2},
    "M2": {"zona": "salon", "capacidad": 4},
    "M3": {"zona": "terraza", "capacidad": 2},
    "M4": {"zona": "terraza", "capacidad": 6},
    "M5": {"zona": "barra", "capacidad": 2},
    "M6": {"zona": "salon", "capacidad": 8},
}

TURNOS_VALIDOS = [
    "12:30", "13:00", "13:30", "14:00",
    "19:30", "20:00", "20:30", "21:00", "21:30",
]

# Ocupación ya existente de otros clientes.
RESERVAS_OCUPADAS = {
    ("2026-07-19", "20:00", "M2"),
    ("2026-07-19", "20:30", "M4"),
    ("2026-07-19", "21:00", "M5"),
    ("2026-07-19", "21:00", "M1"),
    ("2026-07-19", "20:30", "M1"),
}


def _minutos(hora: str) -> int:
    h, m = hora.split(":")
    return int(h) * 60 + int(m)


def _mesas_libres(fecha: str, hora: str, personas: int, zona: str | None = None):
    libres = []
    for mesa_id, info in MESAS.items():
        if info["capacidad"] < personas:
            continue
        if zona and info["zona"] != zona:
            continue
        if (fecha, hora, mesa_id) in RESERVAS_OCUPADAS:
            continue
        libres.append((mesa_id, info))
    return libres


# --- Tools que percibe/acciona el agente -----------------------------------

@tool
def buscar_alternativas_disponibles(
    fecha: str, personas: int,
    hora_preferida: str | None = None,
    zona_preferida: str | None = None,
) -> str:
    """Busca TODAS las combinaciones turno+mesa disponibles ese día para la
    cantidad de personas pedida, ordenadas por cercanía a la hora
    preferida. Es la 'planificación' del agente: si la hora exacta pedida
    no está libre, esta tool permite encontrar el camino más cercano a la
    meta (una reserva viable) en vez de rendirse de inmediato."""
    resultados = []
    for hora in TURNOS_VALIDOS:
        for mesa_id, info in _mesas_libres(fecha, hora, personas, zona_preferida):
            resultados.append((hora, mesa_id, info["zona"]))

    if not resultados:
        return f"Sin ninguna alternativa disponible el {fecha} para {personas} personas (zona={zona_preferida or 'cualquiera'})."

    if hora_preferida:
        resultados.sort(key=lambda r: abs(_minutos(r[0]) - _minutos(hora_preferida)))

    resumen = "\n".join(f"- {h} / mesa {m} / zona {z}" for h, m, z in resultados[:6])
    return f"Alternativas encontradas para el {fecha} (ordenadas por cercanía a {hora_preferida or 'sin preferencia'}):\n{resumen}"


@tool
def confirmar_reserva(fecha: str, hora: str, mesa_id: str, personas: int, telefono: str) -> str:
    """Registra la reserva como PENDIENTE. SOLO debe llamarse después de que
    el cliente haya dado una confirmación EXPLÍCITA (por ejemplo 'sí',
    'confirmo', 'dale') sobre una combinación fecha+hora+mesa concreta:
    este es el guardrail de confirmación explícita del profile card."""
    if mesa_id not in MESAS:
        return f"Mesa {mesa_id} no existe."
    if (fecha, hora, mesa_id) in RESERVAS_OCUPADAS:
        return f"La mesa {mesa_id} ya no está disponible el {fecha} {hora}: hay que replanificar con `buscar_alternativas_disponibles`."
    if MESAS[mesa_id]["capacidad"] < personas:
        return f"La mesa {mesa_id} no tiene capacidad para {personas} personas."
    RESERVAS_OCUPADAS.add((fecha, hora, mesa_id))
    return (
        f"Reserva PENDIENTE confirmada y registrada: {fecha} {hora}, mesa {mesa_id}, "
        f"{personas} personas, cliente {telefono}. Meta alcanzada."
    )


@tool
def escalar_a_staff(motivo: str, contexto: str) -> str:
    """Escala al equipo del restaurante cuando la meta (reserva confirmada)
    no se puede alcanzar por vía normal: sin disponibilidad tras varios
    intentos, alergias/condiciones médicas relevantes, grupos grandes
    fuera de política, o cualquier caso especial."""
    return f"[ESCALADO A STAFF] Motivo: {motivo}. Contexto acumulado de la conversación: {contexto}"


# --- Few-shot: ejemplos de sesiones anteriores ------------------------------
# Ilustran el comportamiento esperado de la short-term memory DENTRO de una
# misma conversación: perseguir la meta sin volver a pedir datos que el
# cliente ya dio en ESTA conversación.

EJEMPLOS_SESIONES_ANTERIORES = """
Sesión anterior #1 (persigue la meta usando la memoria de la conversación):
Cliente: "Quiero mesa para 4 personas el 2026-07-19, preferimos las 20:00."
Clemente: busca alternativas, no hay a las 20:00, propone 19:30 y 21:30.
Cliente: "Dame la de las 21:30."
Clemente: "¿Confirmas mesa para 4 personas el 2026-07-19 a las 21:30?" (NO vuelve a preguntar cuántas personas son ni la fecha: ya las tiene del primer turno de ESTA conversación)
Cliente: "Sí, confirmo."
Clemente: llama a `confirmar_reserva` con los datos ya conocidos.

Sesión anterior #2 (escalamiento tras fallos repetidos):
Cliente pide una hora sin disponibilidad; se le proponen alternativas y ninguna le sirve tras un par de intentos.
Clemente: usa `escalar_a_staff` citando el contexto ya conversado, en vez de seguir intentando indefinidamente.
"""


# --- Definición del agente ---------------------------------------------------

SYSTEM_PROMPT = f"""
Eres el agente de reservas del restaurante Clemente. Tu META explícita es
conseguir una RESERVA PENDIENTE CONFIRMADA que satisfaga al cliente
respetando las políticas del restaurante -- o, si eso no es posible,
ESCALAR al staff en vez de fallar en silencio o inventar una solución.

Persigue la meta con este razonamiento, paso a paso (no reacciones solo al
último mensaje, planifica hacia adelante):
1. Identifica el objetivo del cliente: fecha, personas, hora preferida y
   zona preferida (si la da).
2. Llama a `buscar_alternativas_disponibles` para ver qué combinaciones
   turno+mesa son viables ese día.
3. Si la hora exacta pedida no aparece entre los resultados, NO te rindas:
   propón al cliente las 2-3 alternativas más cercanas encontradas por la
   tool (esto es replanificar hacia la meta, no simplemente decir "no hay").
4. Antes de `confirmar_reserva`, exige que el cliente dé una confirmación
   EXPLÍCITA sobre una combinación concreta (fecha, hora, mesa). Nunca
   confirmes una reserva que el cliente no aceptó explícitamente.
5. Si tras proponer alternativas el cliente sigue sin encontrar nada que le
   sirva, o el caso incluye algo especial (alergia relevante, grupo grande,
   evento fuera de política), usa `escalar_a_staff` con el motivo y el
   contexto acumulado de la conversación, en vez de seguir intentando
   indefinidamente.

Ejemplos de sesiones anteriores (few-shot) que ilustran cómo debes usar tu
memoria de corto plazo dentro de esta misma conversación:
{EJEMPLOS_SESIONES_ANTERIORES}
"""

agent = create_agent(
    model="ollama:llama3.2",
    tools=[buscar_alternativas_disponibles, confirmar_reserva, escalar_a_staff],
    system_prompt=SYSTEM_PROMPT,
)


def continuar_conversacion(mensaje: str, historial: list) -> tuple[str, list]:
    """Envía un nuevo turno REUTILIZANDO el historial de mensajes anterior
    (short-term memory de la conversación): el agente puede razonar sobre
    la meta usando datos dados en turnos previos, sin que el llamador
    tenga que repetirlos."""
    mensajes = historial + [{"role": "user", "content": mensaje}]
    resultado = agent.invoke({"messages": mensajes})
    return resultado["messages"][-1].content, resultado["messages"]


if __name__ == "__main__":
    historial: list = []

    turnos = [
        "Quiero una mesa para 4 el 2026-07-19 a las 20:00, de preferencia en la terraza.",
        "Esa hora no me la diste como disponible, ¿cuál es la alternativa más cercana?",
        "Dale, confirmo esa opción. Mi teléfono es +51988777666.",
    ]
    for mensaje in turnos:
        print(f"\n>>> Cliente: {mensaje}")
        respuesta, historial = continuar_conversacion(mensaje, historial)
        print(f"<<< Clemente: {respuesta}")
