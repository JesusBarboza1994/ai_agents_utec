"""
Andamiaje comun de los tres agentes.

Todos se construyen igual (`create_agent` de LangChain 1.x, Sesion 12) y se
ejecutan igual. Lo unico que cambia entre ellos es su prompt de sistema y su
caja de tools -- que es exactamente la tesis del Entregable 01: tres agentes
distintos porque tienen distinto alcance y distinto costo de equivocarse, no
porque usen tecnologia distinta.

Aqui viven tres cosas transversales:
  1. el contexto de conversacion que reciben las tools (`context_schema`),
  2. la ficha del cliente de memoria de largo plazo, inyectada en cada turno,
  3. el guardrail de salida que descarta tool-calls escritas como texto.
"""

import hashlib
import json
import logging
import warnings

from ..llm import extraer_texto, resolver_modelo
from ..observabilidad.trazas import registrar
from . import fecha
from .contexto import ContextoConversacion
from .memoria import ficha_del_cliente
from .prompts import AVISO_FECHA, AVISO_FICHA

log = logging.getLogger("clemente")

# Historial que se le pasa a un agente: solo turnos de texto (user/assistant).
# Los mensajes de tool no viajan entre agentes porque cada uno tiene tools
# distintas y un mensaje de tool huerfano rompe la conversacion.
LIMITE_TURNOS_HISTORIAL = 12

# LangChain serializa el estado del grafo con Pydantic y avisa de que el campo
# `context` no es None. Es cosmetico -- el contexto SI llega a las tools, lo
# prueban tests/test_guardrails.py -- pero ensucia la consola de la demo.
warnings.filterwarnings("ignore", message=".*Pydantic serializer warnings.*", category=UserWarning)


def id_de_hilo(flujo: str, sesion_id: str) -> str:
    """Id del hilo del checkpoint: un hash de la sesion, para que el telefono no viaje a LangSmith.

    LangGraph copia el thread_id a la metadata de cada ejecucion y la metadata no
    pasa por la redaccion de `seguridad/trazado.py`. Es estable: reanudar una
    revision humana calcula el mismo id que el turno que la pauso."""
    return f"{flujo}:{hashlib.sha256(sesion_id.encode()).hexdigest()[:16]}"


def construir_agente(
    prompt_sistema: str, tools: list, temperature: float = 0.1,
    middleware: list | None = None, checkpointer=None,
):
    """
    Construye el agente LangChain con modelo, prompt y herramientas recibidos.

    `context_schema` es lo que permite que las tools reciban el `sesion_id` sin
    pedirselo al modelo, y que devuelvan `escalado` y `datos` al orquestador.

    La fecha NO va en el system prompt: el agente se construye una vez por
    proceso y quedaba congelada. Viaja en cada turno, ver `_armar_entrada`.
    """
    from langchain.agents import create_agent

    from ..seguridad.pii import middleware_pii

    return create_agent(
        model=resolver_modelo(temperature=temperature),
        system_prompt=prompt_sistema,
        tools=tools,
        context_schema=ContextoConversacion,
        middleware=[*middleware_pii(), *(middleware or [])],
        checkpointer=checkpointer,
    )


# Claves tipicas de una llamada a herramienta escrita como texto.
_CLAVES_DE_TOOL = {"name", "parameters", "arguments", "tool", "function", "tool_call"}

# Columnas tipadas de `cliente` que ya se nombran aparte en el texto de la
# ficha; el resto (el jsonb `data` desestructurado -- dni, alergias, etc.) se
# lista tal cual llega, porque esas claves las define la tool a discrecion.
_CAMPOS_CLIENTE_CON_ETIQUETA = {"first_name": "nombre", "last_name": "apellido", "phone": "telefono"}
_CAMPOS_CLIENTE_INTERNOS = {"id", "chat_key"}
# Claves de `data` con nombre propio en la ficha; las demas se muestran con el guion bajo como espacio.
_ETIQUETAS_DE_DATA = {"telefono_contacto": "telefono de contacto"}


def _texto_ficha_cliente(cliente: dict) -> str:
    """Ficha de identidad para el prompt, armada con el `cliente` que manda comunicacion.

    `cliente` es el dict de `customers_repository.get_customer`: columnas
    tipadas y el jsonb `data` desestructurado al mismo nivel. `id`/`chat_key`
    no se envian al modelo -- son datos internos de la fila, no algo que el
    cliente dijo. Cadena vacia si no hay nada que mostrar.
    """
    partes = [
        f"{etiqueta} {cliente[campo]}"
        for campo, etiqueta in _CAMPOS_CLIENTE_CON_ETIQUETA.items()
        if cliente.get(campo)
    ]
    partes += [
        f"{_ETIQUETAS_DE_DATA.get(clave, clave.replace('_', ' '))} {valor}" for clave, valor in cliente.items()
        if clave not in _CAMPOS_CLIENTE_CON_ETIQUETA and clave not in _CAMPOS_CLIENTE_INTERNOS and valor
    ]
    return f"Cliente conocido: {', '.join(partes)}." if partes else ""


def _parece_llamada_de_tool(texto: str) -> bool:
    """
    Detecta la falla mas comun de los modelos locales chicos (llama3.2): en vez
    de INVOCAR la herramienta, escriben la llamada como JSON en su respuesta --
    a veces con un nombre de tool que ni siquiera existe. Si eso llegara al
    cliente, veria basura tecnica en el chat.

    Es un guardrail de reflejo simple: no interpreta, solo corta.
    """
    limpio = texto.strip().strip("`").removeprefix("json").strip()
    if not limpio.startswith("{"):
        return False
    try:
        datos = json.loads(limpio)
    except json.JSONDecodeError:
        return False
    return isinstance(datos, dict) and bool(_CLAVES_DE_TOOL & set(datos))


def _armar_entrada(texto: str, ficha: str) -> str:
    """Antepone al mensaje los datos del sistema que el modelo no debe adivinar.

    Siempre la fecha y hora de Lima de este turno; la ficha del cliente solo
    cuando existe. Van pegados al mensaje y no al system prompt para que
    cambien turno a turno."""
    bloques = [f"[{AVISO_FECHA}: {fecha.describir_ahora()}]"]
    if ficha:
        bloques.append(f"[{AVISO_FICHA}: {ficha}]")
    bloques.append(texto)
    return "\n".join(bloques)


# Pasos que LangGraph deja dar a un agente en un turno antes de cortarlo. Con el middleware actual
# (PII y revision humana) cada vuelta modelo -> herramientas cuesta 7 pasos, mas 2 de arranque y cierre:
# n vueltas piden 7n + 2. Con 30 solo cabian 4 vueltas, y un camino normal de reserva (hora, disponibilidad,
# guardar datos, crear) llamado de a una herramienta por vez ya llegaba a 5 y el turno fallaba con
# GraphRecursionError. 45 deja 6 vueltas: sobra para un turno sano y un ciclo de reintentos igual se corta.
LIMITE_DE_PASOS = 45

# Lo que lee el cliente cuando escribe mientras su solicitud espera al staff.
AVISO_REVISION_PENDIENTE = (
    "Tu solicitud sigue en revisión del equipo del restaurante; apenas decidan te avisamos. "
    "Todavía no hay una mesa confirmada."
)


def _hilo_en_pausa(agente, config: dict) -> bool:
    """True si el hilo esta detenido esperando la decision del staff (revision humana pendiente).

    Un mensaje nuevo NO puede entrar en esa pausa: el hilo quedo con una llamada a herramienta sin
    respuesta y OpenAI rechaza la conversacion con un 400, lo que dejaba al cliente con un "no
    puedo procesar tu mensaje" hasta que el staff decidiera. Sin checkpoint o ante cualquier fallo
    al consultarlo devuelve False y el turno sigue su camino normal."""
    if getattr(agente, "checkpointer", None) is None or not hasattr(agente, "get_state"):
        return False
    try:
        return bool(agente.get_state(config).next)
    except Exception as error:
        log.warning("No se pudo leer el estado del hilo: %s", type(error).__name__)
        return False


def _olvidar_hilo(agente, config: dict) -> None:
    """Borra el checkpoint del hilo cuando el turno termino sin pausa para revision humana.

    El agente de Reservas guarda el estado de cada hilo para poder reanudarlo tras
    una pausa, pero ademas recibe el historial completo en cada turno: sin este
    borrado el estado acumulado se sumaba al historial reenviado y el modelo veia
    cada mensaje repetido (y pagaba por ello). Una pausa pendiente conserva su
    checkpoint hasta que se resuelve. Un fallo al borrar no interrumpe la respuesta."""
    guardado = getattr(agente, "checkpointer", None)
    if guardado is None:
        return
    try:
        guardado.delete_thread(config["configurable"]["thread_id"])
    except Exception as error:
        log.warning("No se pudo borrar el checkpoint del hilo: %s", type(error).__name__)


def ejecutar(
    agente, texto: str, sesion_id: str, historial: list[dict] | None = None,
    fallback: str = "Disculpa, no te entendi bien. Me lo repites?",
    contexto: ContextoConversacion | None = None, flujo: str = "agente",
) -> str:
    """
    Invoca al agente y devuelve solo su texto de respuesta.

    El `sesion_id` no entra al prompt: viaja en el contexto de ejecucion, que las
    tools leen con `runtime: ToolRuntime`. Lo que si se inyecta en el turno es la
    **ficha del cliente** (memoria de largo plazo): quien es y que reservas tiene,
    para que el agente no dependa de que el cliente repita sus datos en cada
    conversacion nueva.

    Recorta el historial, agrega la ficha de reservas propias y el mensaje
    actual, e invoca con recursion_limit=LIMITE_DE_PASOS y thread_id de flujo y sesion.
    Si hay interrupcion HITL, guarda la solicitud en contexto y devuelve
    un aviso de revision. Si el texto parece una llamada de tool, registra
    el guardrail y devuelve fallback. Los errores de invocacion se propagan:
    fallback no es un manejador general de excepciones.
    """
    contexto = contexto or ContextoConversacion(sesion_id=sesion_id)

    mensajes = list(historial or [])[-LIMITE_TURNOS_HISTORIAL:]
    # Dos fuentes de ficha: la identidad que ya resolvio comunicacion contra
    # Postgres (`contexto.cliente` -- nombre, telefono, lo que traiga `data`) y
    # las reservas propias vigentes, que se siguen consultando aparte porque
    # `ficha_del_cliente` no vive en la fila de `customers`.
    ficha_cliente = _texto_ficha_cliente(contexto.cliente) if contexto.cliente else ""
    ficha_reservas = ficha_del_cliente(sesion_id)
    ficha = " ".join(parte for parte in (ficha_cliente, ficha_reservas) if parte)
    # La instruccion de como tratar la ficha viaja PEGADA a la ficha, no en el
    # system prompt: si el cliente es nuevo no hay ficha, y entonces no se paga
    # ni un token explicando que hacer con algo que no llego. Es el recorte de
    # contexto que pidio Boris en la asesoria del 2026-09-07 [08:22].
    entrada = _armar_entrada(texto, ficha)
    if ficha:
        # La ficha entra por el prompt, no por una tool, asi que sin esta traza
        # el agente puede citar la reserva de un cliente y en el registro no
        # queda constancia de donde salio el dato. Lo senalo la evaluacion del
        # 2026-09-07: "no hay evidencia de que estos datos provengan de una
        # consulta real al sistema". La habia, pero no era auditable.
        registrar("ficha", sesion_id, detalle={"ficha": ficha})
    mensajes.append({"role": "user", "content": entrada})

    config = {
        "recursion_limit": LIMITE_DE_PASOS,
        "configurable": {"thread_id": id_de_hilo(flujo, sesion_id)},
    }
    if _hilo_en_pausa(agente, config):
        registrar("hitl_en_espera", sesion_id, agente=flujo,
                  detalle={"motivo": "mensaje nuevo mientras la revision humana esta pendiente"})
        return AVISO_REVISION_PENDIENTE
    resultado = agente.invoke({"messages": mensajes}, config=config, context=contexto)

    interrupciones = resultado.get("__interrupt__") or []
    if interrupciones:
        solicitud = interrupciones[0].value
        contexto.datos["revision_humana"] = {
            "estado": "pendiente",
            "flujo": flujo,
            "solicitud": solicitud,
        }
        registrar("hitl_pendiente", sesion_id, agente=flujo, detalle={"solicitud": solicitud})
        return (
            "La solicitud necesita revisión del equipo del restaurante. "
            "Todavía no hay una mesa confirmada; te avisaremos cuando el equipo decida."
        )
    respuesta = extraer_texto(resultado["messages"][-1])
    _olvidar_hilo(agente, config)

    if _parece_llamada_de_tool(respuesta):
        # Queda registrado: es la metrica que decide si el modelo alcanza para la
        # demo o hay que cambiarlo (ver ACUERDOS_EQUIPO.md, punto 7.3).
        registrar(
            "guardrail", sesion_id,
            detalle={"motivo": "el modelo escribio la tool en vez de invocarla",
                     "texto": respuesta[:200]},
        )
        return fallback

    return respuesta


def reanudar_revision(agente, sesion_id: str, decision: dict, contexto: ContextoConversacion,
                      flujo: str) -> str:
    """Reanuda el checkpoint del agente con Command(resume) y la decision recibida.

    Usa el thread_id de flujo y sesion y el mismo contexto de negocio.
    Devuelve el ultimo texto; una segunda interrupcion produce RuntimeError
    y los errores del agente se propagan. No abre tickets por si misma.
    """
    from langgraph.types import Command

    config = {
        "recursion_limit": LIMITE_DE_PASOS,
        "configurable": {"thread_id": id_de_hilo(flujo, sesion_id)},
    }
    resultado = agente.invoke(
        Command(resume={"decisions": [decision]}), config=config, context=contexto,
    )
    if resultado.get("__interrupt__"):
        raise RuntimeError("La revisión produjo una segunda interrupción inesperada")
    _olvidar_hilo(agente, config)
    return extraer_texto(resultado["messages"][-1])
