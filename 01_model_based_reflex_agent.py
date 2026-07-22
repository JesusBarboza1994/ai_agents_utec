"""
01_model_based_reflex_agent.py
---------------------------------
AGENTE REFLEXIVO BASADO EN MODELO (Model-Based Reflex Agent)
(IBM: https://www.ibm.com/think/topics/model-based-reflex-agent)

Aplicado a: "Clemente Reservations" — agente conversacional de reservas de
restaurante (ver agent_card_profile_reserva_v2.html).

Por qué este es el ARQUETIPO NÚCLEO del sistema:
La Environment Definition del profile card exige de forma EXPLÍCITA dos
memorias -- Long Term Memory (perfil del cliente: nombre, teléfono,
preferencias, alergias, zona favorita, historial de reservas) y Short
Term Memory (fecha, hora, personas, ocasión, notas, opción elegida
durante la conversación) -- y el entorno es PARCIALMENTE OBSERVABLE: la
disponibilidad real del restaurante puede cambiar entre un mensaje y el
siguiente (otro comensal puede tomar la mesa mientras este cliente
decide). Un agente reflejo SIMPLE (sin memoria, como en
01_simple_reflex_agent.py de /Examples) no podría sostener "la
conversación ya iniciada con Clemente" que exige la Communication Layer,
ni evitar volver a preguntar una alergia ya conocida. Por eso se necesita
un MODELO INTERNO del mundo que persista durante la conversación (short
term) y entre conversaciones (long term).

Este archivo es completamente autocontenido: no depende de otros
archivos de la carpeta (solo de librerías externas), siguiendo la misma
convención que /Examples.

Ejecutar:
    ollama pull llama3.2
    python 01_model_based_reflex_agent.py
"""

from typing import Annotated, Any, Optional, cast

from langchain.agents import create_agent, AgentState
from langchain.agents.middleware import dynamic_prompt, ModelRequest
from langchain.tools import tool, InjectedState, InjectedToolCallId
from langchain_core.messages import HumanMessage, ToolMessage
from langgraph.types import Command

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

# Ocupación ya existente de OTROS clientes -> simula que el mundo cambia
# fuera del control del agente (observabilidad parcial).
RESERVAS_OCUPADAS = {
    ("2026-07-19", "20:00", "M2"),
    ("2026-07-19", "20:30", "M4"),
    ("2026-07-19", "21:00", "M5"),
}

# "Base de datos" de clientes -> long term memory que persiste ENTRE
# conversaciones (no solo dentro de una sesión).
PERFILES_CLIENTES = {
    "+51999111222": {
        "nombre": "Marcela Torres",
        "alergias": ["mariscos"],
        "zona_favorita": "terraza",
        "historial": ["2026-05-02: mesa terraza, 2 personas"],
    }
}


def _mesas_libres(fecha: str, hora: str, personas: int, zona: Optional[str] = None):
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


# --- Estado del agente: aquí vive el MODELO INTERNO del mundo --------------


def _fusionar_dict(izquierda: dict, derecha: dict) -> dict:
    """Reducer: combina escrituras concurrentes de estado en vez de perderlas
    (mismo patrón que 02_model_based_reflex_agent.py de /Examples)."""
    combinado = dict(izquierda or {})
    combinado.update(derecha or {})
    return combinado


class ClementeState(AgentState):
    """Extiende el estado estándar con el modelo interno de la conversación."""
    perfil_cliente: Annotated[dict, _fusionar_dict]          # long term memory
    borrador_reserva: Annotated[dict, _fusionar_dict]         # short term memory
    disponibilidad_consultada: Annotated[dict, _fusionar_dict]  # qué ya se verificó


# --- Tools que perciben/actúan Y actualizan el modelo interno --------------

@tool
def consultar_perfil_cliente(
    telefono: str,
    state: Annotated[dict, InjectedState],
    tool_call_id: Annotated[str, InjectedToolCallId],
) -> Command:
    """Carga la long-term memory del cliente (nombre, alergias, zona
    favorita, historial) por número de teléfono. Debe llamarse al inicio
    de la conversación para no volver a preguntar datos ya conocidos."""
    perfil = PERFILES_CLIENTES.get(telefono)
    if perfil is None:
        perfil = {"nombre": None, "alergias": [], "zona_favorita": None, "historial": []}
        contenido = f"Cliente {telefono} nuevo, sin historial previo."
    else:
        contenido = f"Perfil cargado para {telefono}: {perfil}"
    return Command(update={
        "perfil_cliente": {telefono: perfil},
        "messages": [ToolMessage(contenido, tool_call_id=tool_call_id)],
    })


@tool
def verificar_disponibilidad(
    fecha: str,
    hora: str,
    personas: int,
    zona: Optional[str],
    state: Annotated[dict, InjectedState],
    tool_call_id: Annotated[str, InjectedToolCallId],
) -> Command:
    """Verifica disponibilidad EN TIEMPO REAL (obligatorio antes de
    confirmar cualquier reserva, guardrail de criticidad). Actualiza el
    modelo interno con lo que el agente 'percibe' del mundo en este
    instante, ya que la ocupación real puede cambiar entre mensajes."""
    libres = _mesas_libres(fecha, hora, personas, zona)
    clave = f"{fecha}|{hora}|{personas}|{zona or 'cualquiera'}"
    resumen = [mesa_id for mesa_id, _ in libres]
    if resumen:
        contenido = f"Disponible el {fecha} {hora} para {personas} personas: mesas {resumen}."
    else:
        contenido = f"Sin disponibilidad el {fecha} {hora} para {personas} personas (zona={zona or 'cualquiera'})."
    disponibilidad = dict(state.get("disponibilidad_consultada", {}))
    disponibilidad[clave] = resumen
    return Command(update={
        "disponibilidad_consultada": disponibilidad,
        "messages": [ToolMessage(contenido, tool_call_id=tool_call_id)],
    })


@tool
def actualizar_borrador_reserva(
    state: Annotated[dict, InjectedState],
    tool_call_id: Annotated[str, InjectedToolCallId],
    fecha: Optional[str] = None,
    hora: Optional[str] = None,
    personas: Optional[int] = None,
    ocasion: Optional[str] = None,
    notas: Optional[str] = None,
    opcion_elegida: Optional[str] = None,
) -> Command:
    """Actualiza la short-term memory del borrador de reserva en curso con
    los datos que el cliente vaya confirmando durante la conversación
    (fecha, hora, personas, ocasión, notas, opción elegida)."""
    borrador = dict(state.get("borrador_reserva", {}))
    for campo, valor in [
        ("fecha", fecha), ("hora", hora), ("personas", personas),
        ("ocasion", ocasion), ("notas", notas), ("opcion_elegida", opcion_elegida),
    ]:
        if valor is not None:
            borrador[campo] = valor
    contenido = f"Borrador de reserva actualizado: {borrador}"
    return Command(update={
        "borrador_reserva": borrador,
        "messages": [ToolMessage(contenido, tool_call_id=tool_call_id)],
    })


@tool
def registrar_reserva_pendiente(
    telefono: str,
    mesa_id: str,
    state: Annotated[dict, InjectedState],
    tool_call_id: Annotated[str, InjectedToolCallId],
) -> Command:
    """Registra la reserva como PENDIENTE (requiere que el cliente ya haya
    dado confirmación explícita antes de llamar esta tool) con
    trazabilidad completa reserva-mesa-estado, según el guardrail de
    trazabilidad del profile card."""
    if mesa_id not in MESAS:
        contenido = f"Mesa {mesa_id} no existe."
        return Command(update={"messages": [ToolMessage(contenido, tool_call_id=tool_call_id)]})
    borrador = state.get("borrador_reserva", {})
    contenido = (
        f"Reserva PENDIENTE registrada para {telefono}: mesa {mesa_id}, {borrador}. "
        "Estado: pendiente de validación del equipo del restaurante."
    )
    return Command(update={"messages": [ToolMessage(contenido, tool_call_id=tool_call_id)]})


@tool
def escalar_a_staff(
    motivo: str,
    state: Annotated[dict, InjectedState],
    tool_call_id: Annotated[str, InjectedToolCallId],
) -> Command:
    """Escala inmediatamente al equipo del restaurante (alergias, casos
    especiales, o cualquier evento que el agente no pueda resolver),
    adjuntando todo el contexto ya conocido de la conversación."""
    contenido = (
        f"[ALERTA STAFF] Motivo: {motivo}. "
        f"Perfil conocido: {state.get('perfil_cliente')}. "
        f"Borrador actual: {state.get('borrador_reserva')}."
    )
    return Command(update={"messages": [ToolMessage(contenido, tool_call_id=tool_call_id)]})


# --- Few-shot: ejemplos de sesiones anteriores ------------------------------
# Ilustran el comportamiento esperado de la short-term memory DENTRO de una
# misma conversación. El agente debe imitar este patrón: nunca volver a
# preguntar un dato que el cliente ya dio en ESTA conversación.

EJEMPLOS_SESIONES_ANTERIORES = """
Sesión anterior #1:
Cliente: "Hola, somos 4 personas para el sábado a las 20:00, de preferencia en la terraza."
Clemente: "Perfecto, reviso terraza para 4 personas el sábado 20:00..."
[...varios turnos después...]
Cliente: "Mejor cámbialo a las 21:00."
Clemente: "Listo, muevo la reserva a las 21:00. Sigo con la mesa de 4 en terraza que ya me indicaste." (NO vuelve a preguntar personas ni zona: ya las tiene en el borrador de esta conversación)

Sesión anterior #2:
Cliente: "Reserva para 2, soy alérgica a los mariscos."
[...varios turnos después...]
Cliente: "¿Qué me recomiendan de plato de fondo?"
Clemente: recuerda la alergia mencionada antes en la MISMA conversación y evita sugerir mariscos, sin volver a preguntar.
"""


@dynamic_prompt
def prompt_con_modelo_interno(request: ModelRequest) -> str:
    """Inyecta el modelo interno (perfil + borrador + disponibilidad ya
    consultada) en cada paso, para que el agente 'recuerde' en vez de
    volver a preguntar o volver a verificar lo mismo innecesariamente."""
    perfil = request.state.get("perfil_cliente", {})
    borrador = request.state.get("borrador_reserva", {})
    disponibilidad = request.state.get("disponibilidad_consultada", {})
    return (
        "Eres el agente conversacional de reservas del restaurante Clemente. "
        "Continúas una conversación ya iniciada por WhatsApp/Messenger/Instagram/"
        "Webchat: NO reinicies el contexto en cada mensaje.\n\n"
        "Ejemplos de sesiones anteriores (few-shot) que ilustran cómo debes "
        "usar tu memoria de corto plazo dentro de esta misma conversación:\n"
        f"{EJEMPLOS_SESIONES_ANTERIORES}\n"
        f"MODELO INTERNO ACTUAL (memoria de esta gestión):\n"
        f"- Perfil de cliente conocido (long-term memory): {perfil or 'aún no consultado'}\n"
        f"- Borrador de reserva (short-term memory): {borrador or 'vacío'}\n"
        f"- Disponibilidad ya consultada en esta conversación: {disponibilidad or 'ninguna aún'}\n\n"
        "Reglas:\n"
        "1. Si no conoces el perfil del cliente, usa `consultar_perfil_cliente` primero.\n"
        "2. Nunca vuelvas a preguntar una alergia, preferencia o zona favorita que ya "
        "   esté en el perfil conocido.\n"
        "3. Antes de CONFIRMAR una reserva, siempre llama a `verificar_disponibilidad` "
        "   aunque ya la hayas consultado antes en la conversación (el mundo real "
        "   pudo haber cambiado): esto es un guardrail obligatorio de criticidad.\n"
        "4. Usa `actualizar_borrador_reserva` cada vez que el cliente confirme un dato.\n"
        "5. Pide confirmación EXPLÍCITA del cliente antes de `registrar_reserva_pendiente`.\n"
        "6. Si detectas una alergia relevante, un caso especial, o el cliente insiste "
        "   en algo fuera de política, usa `escalar_a_staff` de inmediato."
    )


# --- Definición del agente ---------------------------------------------------

agent = create_agent(
    model="ollama:llama3.2",
    tools=[
        consultar_perfil_cliente,
        verificar_disponibilidad,
        actualizar_borrador_reserva,
        registrar_reserva_pendiente,
        escalar_a_staff,
    ],
    middleware=[prompt_con_modelo_interno],
    state_schema=ClementeState,
)


def estado_inicial() -> ClementeState:
    return {"messages": [], "perfil_cliente": {}, "borrador_reserva": {}, "disponibilidad_consultada": {}}


def continuar_conversacion(mensaje: str, estado: ClementeState) -> ClementeState:
    """Envía un nuevo turno REUTILIZANDO el estado anterior (modelo interno
    acumulado), simulando una conversación continua multi-turno.

    Nota de tipado: se usa `HumanMessage` (no un dict crudo) porque
    `ClementeState.messages` hereda de `AgentState` el tipo `list[AnyMessage]`.
    Los `cast(...)` en la llamada a `.invoke()` son necesarios porque
    `create_agent(...)` (langchain 1.3.x) tipa `.invoke()` de forma FIJA
    contra `InputAgentState`/`OutputAgentState`, sin importar el
    `state_schema` personalizado que se le pase: `InputAgentState.messages`
    acepta `list[AnyMessage | dict[str, Any]]`, mientras que
    `ClementeState.messages` solo acepta `list[AnyMessage]`; al ser `list`
    invariante, ninguno de los dos es asignable al otro para el checker,
    aunque en runtime el grafo compilado sí acepta y devuelve el estado
    completo de `ClementeState` (confirmado al ejecutar el script)."""
    nuevo_estado: ClementeState = {
        **estado,
        "messages": estado["messages"] + [HumanMessage(content=mensaje)],
    }
    resultado = agent.invoke(cast(Any, nuevo_estado))
    return cast(ClementeState, resultado)


if __name__ == "__main__":
    estado = estado_inicial()

    turnos = [
        "Hola, soy +51999111222, quiero reservar para 2 personas el 2026-07-19 a las 20:00.",
        "¿Tienen algo en la terraza a esa hora?",
        "Perfecto, confirmo esa opción.",
    ]
    for mensaje in turnos:
        print(f"\n>>> Cliente: {mensaje}")
        estado = continuar_conversacion(mensaje, estado)
        print(f"<<< Clemente: {estado['messages'][-1].content}")

    print("\nModelo interno final:", {
        "perfil_cliente": estado.get("perfil_cliente"),
        "borrador_reserva": estado.get("borrador_reserva"),
    })
