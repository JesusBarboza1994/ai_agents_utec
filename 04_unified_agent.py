"""
04_unified_agent.py
---------------------------------
AGENTE UNIFICADO DE RESERVAS (Model-Based + Goal-Based + Utility-Based)
Aplicado a: "Clemente Reservations" — agente conversacional de reservas de
restaurante (ver agent_card_profile_reserva_v2.html).

Por qué existe este archivo (a diferencia de 01/02/03):
Los tres agentes anteriores separan, con fines pedagógicos, las tres
capacidades que el profile card pide (memoria, meta, recomendación) en
tres scripts independientes. Este archivo las COLAPSA en un SOLO agente,
que es la arquitectura natural para producción: una única conversación
coherente que sostiene la memoria (model-based), persigue la meta de una
reserva confirmada (goal-based) y, cuando la hora exacta no está libre,
recomienda alternativas RANKEADAS por utilidad (utility-based) en vez de
listar sin criterio.

Diseño clave discutido:
- Verificar disponibilidad es OBJETIVO (¿hay mesa sí/no?): idéntico para
  cualquier cliente, no requiere ranking.
- Recomendar entre VARIAS alternativas es donde entra la utilidad. El
  score combina 3 señales y se ADAPTA solo:
    * cliente CONOCIDO -> hora pedida + zona_favorita (long-term) + capacidad
    * cliente NUEVO    -> hora pedida + capacidad (zona en valor neutro)
  Así la recomendación es útil incluso sin historial, y mejora cuando el
  cliente ya tiene perfil guardado en long-term memory.
- Encima del flujo deliberativo viven REGLAS REFLEXIVAS (guardrails) que
  disparan siempre: sin confirmación explícita no se registra; alergia o
  caso especial -> escalar de inmediato.

Este archivo es completamente autocontenido: no depende de otros archivos
de la carpeta (solo de librerías externas).

Ejecutar:
    ollama pull llama3.2
    python 04_unified_agent.py
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
    ("2026-07-19", "20:00", "M3"),   # terraza para 2 tomada a la hora pedida
    ("2026-07-19", "20:00", "M1"),
    ("2026-07-19", "20:30", "M4"),
    ("2026-07-19", "21:00", "M5"),
}

# "Base de datos" de clientes -> long-term memory que persiste ENTRE
# conversaciones (no solo dentro de una sesión).
PERFILES_CLIENTES = {
    "+51999111222": {
        "nombre": "Marcela Torres",
        "alergias": ["mariscos"],
        "zona_favorita": "terraza",
        "historial": ["2026-05-02: mesa terraza, 2 personas"],
    }
}


def _minutos(hora: str) -> int:
    h, m = hora.split(":")
    return int(h) * 60 + int(m)


def _mesa_libre(fecha: str, hora: str, mesa_id: str) -> bool:
    return (fecha, hora, mesa_id) not in RESERVAS_OCUPADAS


def _combinaciones_libres(fecha: str, personas: int):
    """Todas las combinaciones turno+mesa con capacidad suficiente y libres."""
    for hora in TURNOS_VALIDOS:
        for mesa_id, info in MESAS.items():
            if info["capacidad"] < personas:
                continue
            if not _mesa_libre(fecha, hora, mesa_id):
                continue
            yield hora, mesa_id, info


def _calcular_utilidad(
    hora: str, info: dict, personas: int,
    hora_preferida: Optional[str], zona_favorita: Optional[str],
    peso_horario: float, peso_zona: float, peso_ajuste_capacidad: float,
) -> dict:
    """Combina cercanía de horario + afinidad de zona + ajuste de capacidad
    en un único score de utilidad (0 a 1, mayor es mejor).

    FALLBACK cliente nuevo: si no hay zona_favorita conocida, score_zona
    toma un valor neutro y el ranking se decide por horario + capacidad.
    Así la recomendación funciona con o sin historial del cliente."""
    if hora_preferida:
        delta = abs(_minutos(hora) - _minutos(hora_preferida))
        score_horario = max(0.0, 1 - delta / 180.0)  # 3h de diferencia -> 0
    else:
        score_horario = 0.5  # sin preferencia, neutro

    if zona_favorita:
        score_zona = 1.0 if info["zona"] == zona_favorita else 0.4
    else:
        score_zona = 0.7  # cliente nuevo / sin preferencia: neutro positivo

    # Penaliza usar una mesa mucho más grande de lo necesario (una mesa de 8
    # para 2 bloquea capacidad valiosa del local).
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


# --- Estado del agente: aquí vive el MODELO INTERNO del mundo --------------


def _fusionar_dict(izquierda: dict, derecha: dict) -> dict:
    """Reducer: combina escrituras de estado en vez de perderlas."""
    combinado = dict(izquierda or {})
    combinado.update(derecha or {})
    return combinado


class ClementeState(AgentState):
    """Extiende el estado estándar con el modelo interno de la conversación."""
    perfil_cliente: Annotated[dict, _fusionar_dict]             # long-term memory
    borrador_reserva: Annotated[dict, _fusionar_dict]           # short-term memory
    disponibilidad_consultada: Annotated[dict, _fusionar_dict]  # qué ya se percibió


def _zona_favorita_de(state: dict, telefono: Optional[str]) -> Optional[str]:
    """Lee la zona favorita del perfil ya cargado en el modelo interno."""
    if not telefono:
        return None
    perfil = state.get("perfil_cliente", {}).get(telefono)
    return perfil.get("zona_favorita") if perfil else None


# --- Tools que perciben/actúan Y actualizan el modelo interno --------------

@tool
def consultar_perfil_cliente(
    telefono: str,
    state: Annotated[dict, InjectedState],
    tool_call_id: Annotated[str, InjectedToolCallId],
) -> Command:
    """Carga la long-term memory del cliente (nombre, alergias, zona
    favorita, historial) por número de teléfono. Debe llamarse al inicio
    de la conversación para no volver a preguntar datos ya conocidos y
    para que la recomendación pueda ponderar la zona favorita."""
    perfil = PERFILES_CLIENTES.get(telefono)
    if perfil is None:
        perfil = {"nombre": None, "alergias": [], "zona_favorita": None, "historial": []}
        contenido = f"Cliente {telefono} NUEVO, sin historial previo (la recomendación usará solo hora + capacidad)."
    else:
        contenido = f"Perfil cargado para {telefono}: {perfil}"
    return Command(update={
        "perfil_cliente": {telefono: perfil},
        "messages": [ToolMessage(contenido, tool_call_id=tool_call_id)],
    })


@tool
def resumen_disponibilidad_dia(fecha: str) -> str:
    """Orientación TEMPRANA: dado SOLO una fecha (cuando el cliente aún no
    dijo cuántas personas ni la hora exacta), devuelve las franjas/turnos de
    ese día que tienen ALGUNA mesa libre, para orientar al cliente mientras
    se le piden los datos que faltan.

    NO es una confirmación de mesa: la disponibilidad exacta depende del
    tamaño del grupo (una franja con mesas de 2 libres no sirve para 8). Por
    eso muestra las ventanas abiertas, no mesas concretas, y siempre debe ir
    acompañada de la pregunta por las personas y la hora."""
    turnos_con_hueco = [
        hora for hora in TURNOS_VALIDOS
        if any(_mesa_libre(fecha, hora, mesa_id) for mesa_id in MESAS)
    ]
    if not turnos_con_hueco:
        return f"El {fecha} no tenemos ningún turno con mesas libres. Convendría escalar o proponer otra fecha."
    return (
        f"El {fecha} tenemos turnos con disponibilidad (orientativa, sin confirmar mesa aún): "
        f"{turnos_con_hueco}. Falta saber cuántas personas y la hora para confirmar mesa exacta."
    )


@tool
def verificar_disponibilidad(
    fecha: str,
    hora: str,
    personas: int,
    zona: Optional[str],
    state: Annotated[dict, InjectedState],
    tool_call_id: Annotated[str, InjectedToolCallId],
) -> Command:
    """Verifica disponibilidad EN TIEMPO REAL para la combinación EXACTA
    pedida (obligatorio antes de confirmar, guardrail de criticidad). Esto
    es objetivo (¿hay mesa sí/no?), no una recomendación. Si no hay para lo
    exacto, el siguiente paso es `buscar_alternativas`."""
    libres = []
    for mesa_id, info in MESAS.items():
        if info["capacidad"] < personas:
            continue
        if zona and info["zona"] != zona:
            continue
        if not _mesa_libre(fecha, hora, mesa_id):
            continue
        libres.append(mesa_id)
    clave = f"{fecha}|{hora}|{personas}|{zona or 'cualquiera'}"
    if libres:
        contenido = f"Disponible el {fecha} {hora} para {personas} personas (zona={zona or 'cualquiera'}): mesas {libres}."
    else:
        contenido = f"SIN disponibilidad exacta el {fecha} {hora} para {personas} (zona={zona or 'cualquiera'}). Usa `buscar_alternativas`."
    disponibilidad = dict(state.get("disponibilidad_consultada", {}))
    disponibilidad[clave] = libres
    return Command(update={
        "disponibilidad_consultada": disponibilidad,
        "messages": [ToolMessage(contenido, tool_call_id=tool_call_id)],
    })


@tool
def buscar_alternativas(
    fecha: str,
    personas: int,
    state: Annotated[dict, InjectedState],
    tool_call_id: Annotated[str, InjectedToolCallId],
    telefono: Optional[str] = None,
    hora_preferida: Optional[str] = None,
    peso_horario: float = 0.4,
    peso_zona: float = 0.3,
    peso_ajuste_capacidad: float = 0.3,
    top_n: int = 4,
) -> Command:
    """Cuando la hora/zona exacta pedida no está libre, busca las mejores
    alternativas disponibles ese día y las devuelve RANKEADAS por utilidad
    (no solo por cercanía de hora). El score combina hora pedida + zona
    favorita del cliente (si está en su perfil) + ajuste de capacidad.

    Se ADAPTA solo: si el cliente es nuevo (sin zona_favorita en el perfil),
    la zona pesa neutro y el orden lo deciden hora + capacidad. Devuelve
    VARIAS opciones, no una, para que el cliente elija.

    Si el cliente prioriza algo explícitamente ("lo antes posible" /
    "siempre en mi zona"), ajusta los pesos antes de llamar: los pesos
    deben sumar aprox. 1.0."""
    zona_favorita = _zona_favorita_de(state, telefono)

    evaluadas = []
    for hora, mesa_id, info in _combinaciones_libres(fecha, personas):
        r = _calcular_utilidad(
            hora, info, personas, hora_preferida, zona_favorita,
            peso_horario, peso_zona, peso_ajuste_capacidad,
        )
        evaluadas.append((r["utilidad"], hora, mesa_id, info["zona"], r))

    if not evaluadas:
        contenido = (
            f"Sin ninguna alternativa el {fecha} para {personas} personas. "
            "No se puede alcanzar la meta por vía normal: usa `escalar_a_staff`."
        )
        return Command(update={"messages": [ToolMessage(contenido, tool_call_id=tool_call_id)]})

    evaluadas.sort(key=lambda e: e[0], reverse=True)
    perfil_nota = (
        f"zona favorita '{zona_favorita}' ponderada" if zona_favorita
        else "cliente sin zona favorita conocida (ranking por hora + capacidad)"
    )
    lineas = [
        f"- {hora} / mesa {mesa_id} / zona {zona} -> utilidad={u} "
        f"(hora={r['score_horario']}, zona={r['score_zona']}, capacidad={r['score_ajuste_capacidad']})"
        for u, hora, mesa_id, zona, r in evaluadas[:top_n]
    ]
    contenido = (
        f"Alternativas para el {fecha}, {personas} personas ({perfil_nota}), "
        f"ordenadas por utilidad de mayor a menor:\n" + "\n".join(lineas)
    )
    return Command(update={"messages": [ToolMessage(contenido, tool_call_id=tool_call_id)]})


@tool
def actualizar_borrador_reserva(
    state: Annotated[dict, InjectedState],
    tool_call_id: Annotated[str, InjectedToolCallId],
    fecha: Optional[str] = None,
    hora: Optional[str] = None,
    personas: Optional[int] = None,
    zona: Optional[str] = None,
    ocasion: Optional[str] = None,
    notas: Optional[str] = None,
    opcion_elegida: Optional[str] = None,
) -> Command:
    """Actualiza la short-term memory del borrador de reserva en curso con
    los datos que el cliente vaya dando (fecha, hora, personas, zona,
    ocasión, notas, opción elegida), para no volver a preguntarlos."""
    borrador = dict(state.get("borrador_reserva", {}))
    for campo, valor in [
        ("fecha", fecha), ("hora", hora), ("personas", personas), ("zona", zona),
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
def confirmar_reserva(
    telefono: str,
    fecha: str,
    hora: str,
    mesa_id: str,
    personas: int,
    state: Annotated[dict, InjectedState],
    tool_call_id: Annotated[str, InjectedToolCallId],
) -> Command:
    """Registra la reserva como PENDIENTE. SOLO debe llamarse DESPUÉS de que
    el cliente haya dado una confirmación EXPLÍCITA sobre una combinación
    fecha+hora+mesa concreta (guardrail de confirmación explícita). Revalida
    la disponibilidad en el momento porque el mundo pudo cambiar."""
    if mesa_id not in MESAS:
        return Command(update={"messages": [ToolMessage(f"Mesa {mesa_id} no existe.", tool_call_id=tool_call_id)]})
    if MESAS[mesa_id]["capacidad"] < personas:
        return Command(update={"messages": [ToolMessage(
            f"La mesa {mesa_id} no tiene capacidad para {personas} personas.", tool_call_id=tool_call_id)]})
    if not _mesa_libre(fecha, hora, mesa_id):
        return Command(update={"messages": [ToolMessage(
            f"La mesa {mesa_id} ya no está libre el {fecha} {hora}: replanifica con `buscar_alternativas`.",
            tool_call_id=tool_call_id)]})

    RESERVAS_OCUPADAS.add((fecha, hora, mesa_id))
    borrador = state.get("borrador_reserva", {})
    contenido = (
        f"Reserva PENDIENTE confirmada para {telefono}: {fecha} {hora}, mesa {mesa_id}, "
        f"{personas} personas. Detalle: {borrador}. "
        "Estado: pendiente de validación del equipo del restaurante. Meta alcanzada."
    )
    return Command(update={"messages": [ToolMessage(contenido, tool_call_id=tool_call_id)]})


@tool
def escalar_a_staff(
    motivo: str,
    state: Annotated[dict, InjectedState],
    tool_call_id: Annotated[str, InjectedToolCallId],
) -> Command:
    """Escala inmediatamente al equipo del restaurante (alergias, casos
    especiales, sin disponibilidad tras varios intentos, o cualquier evento
    que el agente no pueda resolver), adjuntando todo el contexto conocido."""
    contenido = (
        f"[ESCALADO A STAFF] Motivo: {motivo}. "
        f"Perfil conocido: {state.get('perfil_cliente')}. "
        f"Borrador actual: {state.get('borrador_reserva')}."
    )
    return Command(update={"messages": [ToolMessage(contenido, tool_call_id=tool_call_id)]})


# --- Few-shot: ejemplos de sesiones anteriores ------------------------------
# Ilustran el flujo unificado completo: usar la memoria de la conversación,
# perseguir la meta, y recomendar alternativas rankeadas cuando no hay lo
# exacto, sin volver a pedir datos ya dados en ESTA conversación.

EJEMPLOS_SESIONES_ANTERIORES = """
Sesión anterior #1 (no hay lo exacto -> recomienda alternativas rankeadas):
Cliente: "Somos 2 el 2026-07-19 a las 20:00, en terraza. Mi número es +51999111222."
Clemente: carga el perfil (zona favorita: terraza), verifica 20:00 en terraza -> ocupada.
          Busca alternativas rankeadas por utilidad y ofrece VARIAS: "A las 20:00 no queda
          terraza. Te propongo, de mejor a peor encaje: 20:30 en terraza, 19:30 en terraza,
          o 20:00 en salón. ¿Cuál prefieres?" (NO vuelve a preguntar personas/fecha: ya las tiene)
Cliente: "La de 20:30 en terraza."
Clemente: "¿Confirmas 2 personas el 2026-07-19 a las 20:30, mesa en terraza?"
Cliente: "Sí." -> Clemente llama a `confirmar_reserva`.

Sesión anterior #2 (cliente nuevo -> utilidad sin zona favorita):
Cliente nuevo pide una hora ocupada. Clemente recomienda alternativas ordenadas solo por
hora cercana + ajuste de capacidad (sin ponderar zona, porque no hay perfil), y ofrece varias.

Sesión anterior #3 (guardrail reflexivo):
Cliente menciona una alergia relevante o un caso especial -> Clemente usa `escalar_a_staff`
de inmediato con el contexto, sin intentar resolverlo por su cuenta.
"""


@dynamic_prompt
def prompt_con_modelo_interno(request: ModelRequest) -> str:
    """Inyecta el modelo interno (perfil + borrador + disponibilidad ya
    consultada) en cada paso, para que el agente recuerde en vez de volver a
    preguntar, persiga la meta y recomiende con criterio."""
    perfil = request.state.get("perfil_cliente", {})
    borrador = request.state.get("borrador_reserva", {})
    disponibilidad = request.state.get("disponibilidad_consultada", {})
    return (
        "Eres el agente conversacional de reservas del restaurante Clemente. "
        "Continúas una conversación ya iniciada (WhatsApp/Instagram/Webchat): NO "
        "reinicies el contexto en cada mensaje.\n\n"
        "Tu META explícita es conseguir una RESERVA PENDIENTE CONFIRMADA que satisfaga "
        "al cliente respetando las políticas del restaurante; si no es posible, ESCALAR "
        "al staff en vez de fallar en silencio o inventar una solución.\n\n"
        "Ejemplos de sesiones anteriores (few-shot):\n"
        f"{EJEMPLOS_SESIONES_ANTERIORES}\n"
        "MODELO INTERNO ACTUAL (memoria de esta gestión):\n"
        f"- Perfil de cliente (long-term memory): {perfil or 'aún no consultado'}\n"
        f"- Borrador de reserva (short-term memory): {borrador or 'vacío'}\n"
        f"- Disponibilidad ya verificada en esta conversación: {disponibilidad or 'ninguna aún'}\n\n"
        "Flujo y reglas:\n"
        "0. REGLA REACTIVA DE ORIENTACIÓN: si el cliente da una fecha pero aún NO sabes "
        "   cuántas personas (o la hora), llama a `resumen_disponibilidad_dia` y ofrécele "
        "   las franjas abiertas de ese día MIENTRAS le pides en el mismo mensaje el número "
        "   de personas y la hora. Deja claro que la mesa exacta se confirma cuando sepas el "
        "   tamaño del grupo (no prometas una mesa sin conocer los pax).\n"
        "1. Si no conoces el perfil del cliente, usa `consultar_perfil_cliente` primero "
        "   (lo necesitas para ponderar la zona favorita en las recomendaciones).\n"
        "2. Nunca vuelvas a preguntar una alergia, preferencia o dato que ya esté en el "
        "   perfil o en el borrador conocidos.\n"
        "3. Usa `verificar_disponibilidad` para la combinación EXACTA que pidió el cliente. "
        "   Esto es objetivo (hay/no hay), no una recomendación.\n"
        "4. Si NO hay disponibilidad exacta, NO te rindas ni respondas 'no hay' sin más: "
        "   usa `buscar_alternativas` y ofrece al cliente VARIAS opciones (no una sola), "
        "   explicando por qué las recomiendas en ese orden (el trade-off entre hora, zona "
        "   y tamaño de mesa). Si el cliente prioriza algo ('lo antes posible', 'siempre en "
        "   mi zona'), ajusta los pesos antes de buscar.\n"
        "5. Usa `actualizar_borrador_reserva` cada vez que el cliente confirme un dato.\n"
        "6. Exige confirmación EXPLÍCITA del cliente sobre una combinación concreta "
        "   (fecha+hora+mesa) antes de `confirmar_reserva`. Nunca confirmes lo que el "
        "   cliente no aceptó explícitamente.\n"
        "7. Si detectas una alergia relevante, un caso especial, o no hay forma de alcanzar "
        "   la meta tras varios intentos, usa `escalar_a_staff` de inmediato."
    )


# --- Definición del agente ---------------------------------------------------

agent = create_agent(
    model="ollama:llama3.2",
    tools=[
        consultar_perfil_cliente,
        resumen_disponibilidad_dia,
        verificar_disponibilidad,
        buscar_alternativas,
        actualizar_borrador_reserva,
        confirmar_reserva,
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

    Los `cast(...)` son necesarios porque `create_agent(...)` (langchain
    1.3.x) tipa `.invoke()` de forma fija contra InputAgentState/
    OutputAgentState y no contra el `state_schema` personalizado, aunque en
    runtime el grafo sí acepta y devuelve el ClementeState completo."""
    nuevo_estado: ClementeState = {
        **estado,
        "messages": estado["messages"] + [HumanMessage(content=mensaje)],
    }
    resultado = agent.invoke(cast(Any, nuevo_estado))
    return cast(ClementeState, resultado)


if __name__ == "__main__":
    estado = estado_inicial()

    # Cliente CONOCIDO (+51999111222, zona favorita terraza) pide una hora en
    # terraza que está ocupada -> el agente debe recomendar alternativas
    # rankeadas ponderando la terraza, sin volver a pedir datos ya dados.
    turnos = [
        "Hola, soy +51999111222. Quiero reservar para 2 personas el 2026-07-19 a las 20:00 en la terraza.",
        "¿Qué alternativas me das entonces?",
        "Perfecto, confirmo la primera opción que me recomendaste.",
    ]
    for mensaje in turnos:
        print(f"\n>>> Cliente: {mensaje}")
        estado = continuar_conversacion(mensaje, estado)
        print(f"<<< Clemente: {estado['messages'][-1].content}")

    print("\nModelo interno final:", {
        "perfil_cliente": estado.get("perfil_cliente"),
        "borrador_reserva": estado.get("borrador_reserva"),
    })
