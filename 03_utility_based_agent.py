"""
03_utility_based_agent.py
----------------------------
AGENTE BASADO EN UTILIDAD (Utility-Based Agent)
(IBM: https://www.ibm.com/think/topics/utility-based-agent)

Aplicado a: "Clemente Reservations" — agente conversacional de reservas de
restaurante (ver agent_card_profile_reserva_v2.html).

Por qué este tipo de agente encaja con la Context/Objectives Definition y
la Autonomy Dimension del profile card:
Los Objectives Definition piden explícitamente "ofrecer franjas horarias
disponibles" y la Autonomy Dimension dice que el agente "evalúa la
disponibilidad del local... y OFRECE RECOMENDACIONES de horarios
disponibles". Eso no es solo alcanzar una meta binaria (¿hay mesa o no?,
que ya cubre el agente basado en objetivos): cuando existen VARIAS
combinaciones válidas de mesa+horario, el agente debe compararlas y
recomendar la mejor, sopesando trade-offs -- igual que el ejemplo de
IBM de comparar vehículo+ruta. Aquí los trade-offs relevantes según el
profile card son: (1) cercanía a la hora que pidió el cliente, (2) si la
mesa está en su zona favorita (Long Term Memory), y (3) que la mesa no
quede sobredimensionada para el grupo (evitar ocupar una mesa de 8 para
2 personas, un mal uso de la capacidad del local).

Este agente es complementario a los otros dos: normalmente se invoca
DESPUÉS de que el agente basado en objetivos (02) encontró varias
alternativas viables, para decidir CUÁL recomendar primero.

Este archivo es completamente autocontenido: no depende de otros
archivos de la carpeta (solo de librerías externas).

Ejecutar:
    ollama pull llama3.2
    python 03_utility_based_agent.py
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

RESERVAS_OCUPADAS = {
    ("2026-07-19", "20:00", "M2"),
    ("2026-07-19", "21:00", "M5"),
}


def _minutos(hora: str) -> int:
    h, m = hora.split(":")
    return int(h) * 60 + int(m)


def _mesa_libre(fecha: str, hora: str, mesa_id: str) -> bool:
    return (fecha, hora, mesa_id) not in RESERVAS_OCUPADAS


def _calcular_utilidad(
    fecha: str, hora: str, mesa_id: str, personas: int,
    hora_preferida: str | None, zona_favorita: str | None,
    peso_horario: float, peso_zona: float, peso_ajuste_capacidad: float,
) -> dict:
    """Combina cercanía de horario + afinidad de zona + ajuste de capacidad
    en un único score de utilidad (0 a 1, mayor es mejor). Los pesos son
    configurables: si el cliente prioriza "lo antes posible" se sube
    peso_horario; si prioriza "siempre en mi zona de siempre" se sube
    peso_zona."""
    info = MESAS[mesa_id]

    if hora_preferida:
        delta = abs(_minutos(hora) - _minutos(hora_preferida))
        score_horario = max(0.0, 1 - delta / 180.0)  # 3h de diferencia -> score 0
    else:
        score_horario = 0.5  # sin preferencia, es neutro

    if zona_favorita:
        score_zona = 1.0 if info["zona"] == zona_favorita else 0.4
    else:
        score_zona = 0.7  # sin preferencia conocida, ligeramente positivo por defecto

    # Penaliza usar una mesa mucho más grande de lo necesario (mal uso del
    # local: una mesa de 8 para 2 personas bloquea capacidad valiosa).
    sobrante = info["capacidad"] - personas
    score_ajuste_capacidad = max(0.0, 1 - sobrante / info["capacidad"])

    utilidad = (
        peso_horario * score_horario
        + peso_zona * score_zona
        + peso_ajuste_capacidad * score_ajuste_capacidad
    )

    return {
        "score_horario": round(score_horario, 2),
        "score_zona": round(score_zona, 2),
        "score_ajuste_capacidad": round(score_ajuste_capacidad, 2),
        "utilidad": round(utilidad, 3),
    }


# --- Tools que percibe/acciona el agente -----------------------------------

@tool
def listar_opciones_reserva(fecha: str, personas: int, zona_preferida: str | None = None) -> str:
    """Lista las combinaciones turno+mesa disponibles ese día para la
    cantidad de personas pedida (antes de evaluar cuál recomendar)."""
    opciones = []
    for hora in TURNOS_VALIDOS:
        for mesa_id, info in MESAS.items():
            if info["capacidad"] < personas:
                continue
            if zona_preferida and info["zona"] != zona_preferida:
                continue
            if not _mesa_libre(fecha, hora, mesa_id):
                continue
            opciones.append(f"{hora} / {mesa_id} (zona {info['zona']}, capacidad {info['capacidad']})")
    if not opciones:
        return f"No hay combinaciones disponibles el {fecha} para {personas} personas."
    return "Opciones disponibles:\n" + "\n".join(f"- {o}" for o in opciones)


@tool
def evaluar_opcion_reserva(
    fecha: str, hora: str, mesa_id: str, personas: int,
    hora_preferida: str | None = None,
    zona_favorita: str | None = None,
    peso_horario: float = 0.4,
    peso_zona: float = 0.3,
    peso_ajuste_capacidad: float = 0.3,
) -> str:
    """Calcula la utilidad (0-1, mayor es mejor) de una combinación
    fecha+hora+mesa concreta, combinando cercanía a la hora preferida,
    afinidad con la zona favorita del cliente (Long Term Memory) y ajuste
    de capacidad de la mesa al tamaño del grupo. Los pesos deben sumar
    aprox. 1.0."""
    if mesa_id not in MESAS:
        return f"Mesa desconocida: {mesa_id}. Opciones: {list(MESAS)}"
    if MESAS[mesa_id]["capacidad"] < personas:
        return f"La mesa {mesa_id} no tiene capacidad para {personas} personas."
    if not _mesa_libre(fecha, hora, mesa_id):
        return f"La mesa {mesa_id} ya está ocupada el {fecha} {hora}."

    r = _calcular_utilidad(
        fecha, hora, mesa_id, personas, hora_preferida, zona_favorita,
        peso_horario, peso_zona, peso_ajuste_capacidad,
    )
    return (
        f"{hora} / {mesa_id} -> score_horario={r['score_horario']}, "
        f"score_zona={r['score_zona']}, score_ajuste_capacidad={r['score_ajuste_capacidad']}, "
        f"UTILIDAD={r['utilidad']}"
    )


# --- Few-shot: ejemplos de sesiones anteriores ------------------------------
# Ilustran el comportamiento esperado de la short-term memory DENTRO de una
# misma conversación: reevaluar la utilidad con nuevas preferencias sin
# volver a pedir datos que el cliente ya dio en ESTA conversación.

EJEMPLOS_SESIONES_ANTERIORES = """
Sesión anterior (ajusta la utilidad usando la memoria de la conversación):
Cliente: "Somos 2, nuestra zona favorita es la terraza, preferimos las 20:00 el 2026-07-19."
Clemente: evalúa varias combinaciones y recomienda la de mayor utilidad en terraza cerca de las 20:00.
Cliente: "En realidad prioriza que sea lo antes posible, no me importa tanto la zona."
Clemente: reevalúa con peso_horario más alto y peso_zona más bajo, SIN volver a preguntar cuántas personas son ni la fecha (ya las dio en esta misma conversación).
"""


# --- Definición del agente ---------------------------------------------------

SYSTEM_PROMPT = f"""
Eres el motor de recomendación de horarios del restaurante Clemente. NO te
conformas con encontrar "una" mesa disponible: debes EVALUAR varias
combinaciones de horario+mesa con `evaluar_opcion_reserva` y recomendar la
de mayor utilidad. Sigue estos pasos:
1. Llama a `listar_opciones_reserva` para ver las combinaciones disponibles
   ese día para el grupo.
2. Evalúa AL MENOS 3 combinaciones distintas con `evaluar_opcion_reserva`
   (si hay menos de 3 disponibles, evalúa todas las que existan).
3. Compara las utilidades obtenidas.
4. Recomienda la combinación de mayor utilidad, explicando el trade-off al
   cliente (por ejemplo, por qué no recomendaste la hora exacta pedida si
   una 15 minutos más tarde en su zona favorita tuvo mayor utilidad total).
Si el cliente da una preferencia explícita (por ejemplo "prioriza que sea
lo antes posible" o "prioriza que sea en mi zona de siempre"), ajusta los
pesos peso_horario/peso_zona/peso_ajuste_capacidad en consecuencia antes de
evaluar.

Ejemplos de sesiones anteriores (few-shot) que ilustran cómo debes usar tu
memoria de corto plazo dentro de esta misma conversación:
{EJEMPLOS_SESIONES_ANTERIORES}
"""

agent = create_agent(
    model="ollama:llama3.2",
    tools=[listar_opciones_reserva, evaluar_opcion_reserva],
    system_prompt=SYSTEM_PROMPT,
)


def continuar_conversacion(mensaje: str, historial: list) -> tuple[str, list]:
    """Envía un nuevo turno REUTILIZANDO el historial de mensajes anterior
    (short-term memory de la conversación): el agente puede reevaluar la
    utilidad usando preferencias dadas en turnos previos, sin que el
    llamador tenga que repetirlas."""
    mensajes = historial + [{"role": "user", "content": mensaje}]
    resultado = agent.invoke({"messages": mensajes})
    return resultado["messages"][-1].content, resultado["messages"]


if __name__ == "__main__":
    historial: list = []

    turnos = [
        "Somos 2 personas el 2026-07-19, preferimos las 20:00 y nuestra zona favorita es la terraza. ¿Qué me recomiendas?",
        "En realidad prioriza que sea lo antes posible, la zona ya no me importa tanto.",
    ]
    for mensaje in turnos:
        print(f"\n>>> Cliente: {mensaje}")
        respuesta, historial = continuar_conversacion(mensaje, historial)
        print(f"<<< Clemente: {respuesta}")
