"""
Orquestador de Clemente: grafo LangGraph con topologia *Supervisor*.
Responsables: Christian, Jean.

    START -> planificador -> [ informacion | reservas | incidencias ]* -> cierre -> END

De enrutador a orquestador (2026-09-07)
---------------------------------------
Hasta esta fecha este modulo era un **router**: clasificaba el mensaje en una de
tres rutas, despachaba a UN agente y terminaba. En la asesoria, Boris pidio que
subiera de categoria, y dijo con que condicion [10:48]:

    "Eso se le puede decir a un router, y lo bautizaste ahora orquestador. Y le
    dices: ahora no es solo dirigir, sino que tiene que definir un plan de
    resolucion. Entonces ahi si ya se vuelve orquestador."

Lo que cambio, en concreto, son tres cosas:

1. **Planifica.** `_nodo_planificador` no devuelve una ruta sino una lista
   ordenada de pasos. Casi siempre es uno; cuando el mensaje trae dos cosas
   ("espere 40 minutos y ahora quiero mesa para el sabado") son dos, en el orden
   que corresponde. Antes ese caso se perdia: la regla de prioridad mandaba todo
   a incidencias y la reserva se caia del turno.

2. **Responde el mismo.** El agente de Conocimiento se elimino y su alcance subio
   aqui: el orquestador contesta las preguntas de informacion del restaurante con
   sus propias tools de lectura. Boris [12:09]: "va a servir de proxy a cualquier
   pedido de informacion del restaurante". Ver `informacion.py`.

3. **Es el unico punto de salida.** Ningun agente escala por su cuenta: levanta la
   mano en el contexto y `_nodo_cierre` abre el ticket, lo notifica y lo registra.
   Boris [12:39]: "el que administra la comunicacion es el orquestador, porque si
   no, como persiste en el log. Al final, el unico punto de salida".

Por que supervisor y no una red de agentes hablando entre si: los alcances tienen
costos de error muy distintos, y un unico punto de decision es tambien un unico
punto donde auditar por que se eligio un agente.

**El planificador ve la conversacion, no solo el ultimo mensaje.** En la prueba
del 2026-09-06, clasificar cada mensaje aislado mando 4 de 6 turnos al agente
equivocado: "y si no tengo el telefono?" o "numero de personas", sueltos, no
tienen ninguna senal de reserva. Por eso recibe el resumen del hilo y el agente
que venia atendiendo, con una regla explicita de continuidad.
"""

import sys
import time
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field
from typing_extensions import TypedDict

from ..agentes import AGENTES
from ..agentes.contexto import ContextoConversacion
from ..contratos import MensajeEntrante, RespuestaClemente
from ..incidencias import obtener_servicio as servicio_incidencias
from ..llm import extraer_texto, resolver_modelo
from ..observabilidad.trazas import cronometro, registrar, registrar_conversacion
from . import informacion

# Cuantos turnos del hilo ve el planificador. Suficiente para entender de que se
# esta hablando, sin pagar el contexto completo en cada clasificacion.
TURNOS_PARA_ENRUTAR = 6

# Tope de pasos por turno. Dos es lo que pidio Boris con su ejemplo (customer
# care y despues reserva) y es tambien el limite de lo que un cliente puede
# seguir en un solo mensaje de chat. Un plan mas largo casi siempre significa que
# el modelo entendio de mas, no que el cliente pidio mas.
PASOS_MAXIMOS = 2

# Los nodos que pueden aparecer en un plan. `informacion` NO es un agente: es el
# propio orquestador respondiendo (por eso no esta en el registro `AGENTES`).
NODOS = {"informacion": informacion.responder, **AGENTES}

# Ultimo agente que atendio cada sesion. Vive en el orquestador para no cambiar
# el contrato con la capa de comunicacion (Jesus): responder(entrante, historial).
_ultimo_agente: dict[str, str] = {}

# Caso ya escalado en cada sesion: sesion_id -> codigo de la incidencia abierta.
# Evita abrir una tarjeta nueva cada vez que el agente vuelve a levantar la mano
# dentro del mismo hilo (ver `_escalar`).
_escalado_de: dict[str, str] = {}


class EstadoConversacion(TypedDict, total=False):
    """
    Estado compartido que viaja por el grafo.

    Los campos son opcionales porque el grafo no siempre se invoca desde
    `responder()`: en LangGraph Studio se lanza a mano, y ahi lo unico que se
    escribe es `mensaje`. Los nodos completan lo que falte.
    """

    sesion_id: str
    mensaje: str
    historial: list[dict]
    ultimo_agente: str
    contexto: ContextoConversacion

    # --- lo que produce el planificador ---
    plan: list[str]          # pasos en orden, p. ej. ["incidencias", "reservas"]
    paso: int                # cual de esos pasos toca ahora
    motivo_ruta: str

    # --- lo que producen los nodos de trabajo ---
    respuestas: list[dict]   # [{"agente": "reservas", "texto": "..."}]

    # --- lo que arma el cierre ---
    ruta: str                # agente que cierra el turno (para metricas y UI)
    respuesta: str           # texto unico que ve el cliente


class PlanDeResolucion(BaseModel):
    """Salida forzada del planificador: a quien llamar y en que orden."""

    pasos: list[Literal["informacion", "reservas", "incidencias"]] = Field(
        ...,
        description=(
            "Pasos en el orden en que hay que atenderlos. Casi siempre UNO. Dos solo "
            "si el mensaje trae dos pedidos distintos que no se pueden atender juntos. "
            "'informacion': pregunta datos generales del restaurante (horarios, "
            "direccion, carta, estacionamiento, opciones vegetarianas, politicas, "
            "promociones). 'reservas': quiere consultar disponibilidad, reservar, "
            "cambiar o cancelar una mesa, o pregunta por una reserva suya. "
            "'incidencias': se queja de algo que YA ocurrio (espera, mal servicio, un "
            "plato, una reserva que no aparecio, un reclamo sin respuesta)."
        ),
    )
    motivo: str = Field(..., description="Una frase corta explicando el plan")


PROMPT_PLANIFICADOR = """Eres el orquestador de un restaurante. No le respondes al cliente:
armas el plan de resolucion del ULTIMO mensaje y nada mas.

Devuelves los pasos en el orden en que hay que atenderlos. Lo normal es UN paso.

Cuando son dos: el mensaje trae dos pedidos distintos y atender solo uno dejaria al
cliente sin respuesta a la mitad de lo que escribio. El caso tipico es la queja que
termina pidiendo una mesa: primero 'incidencias', despues 'reservas'. Lo que ya salio
mal se atiende antes que lo que viene. Si el cliente pregunta un dato general y ademas
quiere reservar, primero 'informacion' y despues 'reservas': el dato puede cambiar lo
que quiera reservar.

Nunca pongas dos veces el mismo paso, y nunca pongas mas de dos.

REGLA DE CONTINUIDAD, tan importante como las anteriores: la conversacion es un hilo.
Si el ultimo mensaje es una continuacion de lo que se venia hablando -- responde a una
pregunta que hizo Clemente, aporta un dato suelto (un nombre, un telefono, una fecha, un
numero de personas, un codigo de reserva, un si o un no) o insiste en lo mismo --, el
plan es UN solo paso: el MISMO agente que venia atendiendo. Un dato suelto no cambia de
tema, lo completa. Solo cambias de agente si aparece una senal clara de otro alcance.

Ante la duda entre informacion y reserva, y sin hilo previo, elige 'informacion':
responder de mas sobre horarios cuesta una aclaracion; comprometer una mesa que no
existe cuesta un cliente parado en la puerta."""


PROMPT_SINTESIS = """Une estos mensajes de Clemente en UNO solo, como si siempre hubiera
sido una sola respuesta escrita de corrido por WhatsApp.

No agregues informacion que no este en los textos. No quites ningun dato concreto:
codigos, fechas, horas, plazos y numeros van tal cual, sin cambiar ni un caracter. No
inventes codigos. No uses listas, ni negritas, ni titulos. Que se lea como una sola
persona hablando, no como dos respuestas pegadas."""


_grafo = None


# Que responde Clemente si llega un turno sin texto. No es un error del
# cliente ni del sistema: simplemente no hay nada que atender.
#
# CONVENCION: el codigo de este proyecto se escribe sin tildes (comentarios,
# nombres, docstrings), pero el texto que LEE EL CLIENTE si las lleva. Todo lo
# demas que ve el cliente lo redacta el modelo, con tildes; una frase nuestra
# sin ellas al lado de una suya delata que hay dos autores. Se noto en el
# experimento del 2026-09-08: "Tu codigo de caso es..." pegado despues de
# "La mesa todavia no esta confirmada" escrito por el agente.
SIN_MENSAJE = "No me llegó ningún mensaje. Escribime qué necesitás y te ayudo."


def _sesion_de(estado: EstadoConversacion) -> str:
    """Sesion del estado, con nombre propio cuando el grafo se lanza desde Studio."""
    return estado.get("sesion_id") or "studio"


def _mensaje_de(estado: EstadoConversacion) -> str:
    """
    Texto del turno, o cadena vacia.

    Se lee siempre por aqui y nunca con `estado["mensaje"]`: el estado puede
    llegar incompleto -- desde Studio se envia a mano, y un webhook mal armado
    puede mandar el campo vacio. Un turno sin texto se contesta, no se cae.
    """
    return (estado.get("mensaje") or "").strip()


def _resumen_del_hilo(historial: list[dict]) -> str:
    if not historial:
        return "(sin conversacion previa)"
    lineas = []
    for mensaje in historial[-TURNOS_PARA_ENRUTAR:]:
        quien = "Cliente" if mensaje.get("role") == "user" else "Clemente"
        lineas.append(f"{quien}: {str(mensaje.get('content', ''))[:220]}")
    return "\n".join(lineas)


def _limpiar_plan(pasos: list[str]) -> list[str]:
    """
    Deja el plan en algo ejecutable: sin repetidos, sin desconocidos y con tope.

    El modelo devuelve salida estructurada, asi que los valores son validos por
    construccion; lo que no garantiza el esquema es que no repita un paso ni que
    respete el limite. Eso se hace aqui, en codigo, no pidiendoselo al prompt.
    """
    vistos: list[str] = []
    for paso in pasos:
        if paso in NODOS and paso not in vistos:
            vistos.append(paso)
    return vistos[:PASOS_MAXIMOS]


# ------------------------------- nodos -------------------------------------

def _nodo_planificador(estado: EstadoConversacion) -> dict:
    from langchain_core.messages import HumanMessage, SystemMessage

    mensaje = _mensaje_de(estado)
    if not mensaje:
        # Sin texto no hay nada que planificar, y llamar al modelo seria gastar
        # por nada. El plan vacio cae directo al cierre.
        registrar("plan", _sesion_de(estado),
                  detalle={"plan": [], "motivo": "turno sin texto"})
        return {"plan": [], "paso": 0, "motivo_ruta": "turno sin texto", "respuestas": []}

    venia_de = estado.get("ultimo_agente") or "ninguno"
    entrada = (
        f"Conversacion previa:\n{_resumen_del_hilo(estado.get('historial') or [])}\n\n"
        f"Agente que venia atendiendo: {venia_de}\n\n"
        f"ULTIMO MENSAJE DEL CLIENTE (el que hay que planificar):\n{mensaje}"
    )

    modelo = resolver_modelo(temperature=0.0, rol="enrutador").with_structured_output(
        PlanDeResolucion
    )
    try:
        decision = modelo.invoke([
            SystemMessage(content=PROMPT_PLANIFICADOR),
            HumanMessage(content=entrada),
        ])
        plan, motivo = _limpiar_plan(decision.pasos), decision.motivo
    except Exception as error:
        # Un planificador caido no puede tumbar la conversacion: se cae al agente
        # que venia atendiendo, y si no habia, al mas barato de equivocarse.
        plan = [estado.get("ultimo_agente") or "informacion"]
        motivo = f"fallback por error de planificacion: {error}"

    if not plan:
        plan, motivo = ["informacion"], f"{motivo} (plan vacio, se atiende como consulta)"

    registrar(
        "plan", _sesion_de(estado), agente=plan[0],
        detalle={"plan": plan, "motivo": motivo, "venia_de": venia_de},
    )
    return {"plan": plan, "paso": 0, "motivo_ruta": motivo, "respuestas": []}


def _nodo_trabajo(nombre: str):
    """Fabrica el nodo de un paso del plan: mismo cuerpo para todos."""

    def nodo(estado: EstadoConversacion) -> dict:
        sesion = _sesion_de(estado)
        mensaje = _mensaje_de(estado)
        # Lanzado desde Studio no viene contexto: se arma uno para que las tools
        # reciban igual su `sesion_id` y el escalamiento siga teniendo donde volver.
        contexto = estado.get("contexto") or ContextoConversacion(sesion_id=sesion, canal="studio")

        with cronometro("respuesta", sesion, agente=nombre):
            texto = NODOS[nombre](
                mensaje, sesion, estado.get("historial") or [], contexto=contexto,
            )

        return {
            "respuestas": (estado.get("respuestas") or []) + [
                {"agente": nombre, "texto": texto}
            ],
            "paso": estado.get("paso", 0) + 1,
            "contexto": contexto,
        }

    return nodo


def _siguiente(estado: EstadoConversacion) -> str:
    """Que sigue: el proximo paso del plan, o el cierre si ya no quedan."""
    plan = estado.get("plan") or []
    paso = estado.get("paso", 0)
    if paso < len(plan) and paso < PASOS_MAXIMOS:
        return plan[paso]
    return "cierre"


def _sintetizar(respuestas: list[dict], sesion: str) -> str:
    """
    Un solo mensaje a partir de varios.

    Con una sola respuesta NO se llama al modelo: se deja pasar el texto tal cual.
    Es deliberado y es lo mas importante de esta funcion -- reescribir la
    confirmacion de una reserva es arriesgar el codigo y la hora por nada, y
    ademas seria pagar una llamada extra en el 90% de los turnos. La sintesis
    solo ocurre cuando el plan tuvo dos pasos.
    """
    if len(respuestas) == 1:
        return respuestas[0]["texto"]

    from langchain_core.messages import HumanMessage, SystemMessage

    pegado = "\n\n".join(r["texto"] for r in respuestas)
    try:
        modelo = resolver_modelo(temperature=0.0, rol="enrutador")
        salida = modelo.invoke([
            SystemMessage(content=PROMPT_SINTESIS),
            HumanMessage(content=pegado),
        ])
        texto = extraer_texto(salida)
        return texto or pegado
    except Exception as error:
        # Si la sintesis falla, el cliente recibe los dos textos pegados: feo,
        # pero completo. Perder una de las dos respuestas seria peor.
        registrar("error", sesion, detalle={"error": f"sintesis: {error}"})
        return pegado


def _escalar(sesion: str, escalamiento: dict, mensaje: str, contexto) -> str:
    """
    Abre el ticket del hilo, o le agrega el dato nuevo si ya habia uno.

    Un hilo escala UNA vez. Suena obvio y no lo era: el escalamiento de un grupo
    grande ocurre en dos turnos -- el agente reconoce el limite, pide nombre y
    telefono, y recien entonces escala --, asi que la senal viene levantada en
    los dos. Sin este control se abrian **dos tarjetas para el mismo caso**, con
    dos codigos distintos, y el staff terminaba con el mismo grupo por duplicado.
    Se detecto en el experimento del 2026-09-08.

    El dato del segundo turno no se pierde: entra como nota en la tarjeta que ya
    existe, que es donde la persona que atiende lo va a leer.
    """
    servicio = servicio_incidencias()
    detalle = f"{escalamiento.get('motivo', '')}: {escalamiento.get('detalle', '')}"

    abierto = _escalado_de.get(sesion)
    if abierto:
        servicio.anotar(abierto, f"[dato nuevo del cliente] {detalle}\nDijo: {mensaje}")
        contexto.datos["incidencia"] = {"id": abierto, "actualizada": True}
        return abierto

    incidencia = servicio.crear_incidencia(
        sesion_id=sesion,
        descripcion=(
            f"[escalado desde {escalamiento.get('origen', 'agente')}] {detalle}\n"
            f"Mensaje del cliente: {mensaje}"
        ),
        tipo="reserva",
    )
    _escalado_de[sesion] = incidencia.id
    contexto.datos["incidencia"] = incidencia.__dict__
    return incidencia.id


def _nodo_cierre(estado: EstadoConversacion) -> dict:
    """
    Punto UNICO de salida del orquestador.

    Aqui pasan, en este orden, las cuatro cosas que Boris pidio que no estuvieran
    repartidas entre los agentes: se junta la respuesta, se abre el ticket si
    alguien levanto la mano, se deja la traza y se decide con que etiqueta sale
    el turno.
    """
    sesion = _sesion_de(estado)
    respuestas = estado.get("respuestas") or []
    contexto = estado.get("contexto") or ContextoConversacion(sesion_id=sesion, canal="studio")

    if not respuestas:
        return {"respuesta": SIN_MENSAJE, "ruta": "informacion", "contexto": contexto}

    texto = _sintetizar(respuestas, sesion)

    # Escalamiento: el agente levanto la mano, el ticket lo abre el orquestador,
    # que es el unico que tiene el turno completo delante.
    escalamiento = contexto.datos.get("escalamiento")
    if contexto.escalado and escalamiento:
        codigo = _escalar(sesion, escalamiento, _mensaje_de(estado), contexto)
        registrar("escalado", sesion, agente=respuestas[-1]["agente"],
                  detalle={"incidencia": codigo, **escalamiento})
        # Solo se agrega el codigo si el agente no lo dijo ya. Antes se pegaba
        # siempre una frase completa ("tu caso quedo registrado y una persona te
        # va a contactar") encima de la del agente, que decia exactamente lo
        # mismo: el cliente leia la promesa dos veces.
        if codigo and codigo not in texto:
            texto = f"{texto} Tu código de caso es {codigo}."

    return {
        "respuesta": texto,
        # Con quien queda la conversacion: es lo que el proximo turno usara como
        # continuidad, asi que es el ULTIMO que hablo, no el primero.
        "ruta": respuestas[-1]["agente"],
        "contexto": contexto,
    }


def _construir_grafo():
    from langgraph.graph import END, START, StateGraph

    grafo = StateGraph(EstadoConversacion)
    grafo.add_node("planificador", _nodo_planificador)
    for nombre in NODOS:
        grafo.add_node(nombre, _nodo_trabajo(nombre))
    grafo.add_node("cierre", _nodo_cierre)

    grafo.add_edge(START, "planificador")

    # Desde el planificador y desde cada paso se vuelve a preguntar que sigue.
    # Eso es lo que permite encadenar dos agentes en un mismo turno sin que
    # ninguno de los dos sepa que existe el otro.
    #
    # De cada paso se declaran como destinos los OTROS pasos, nunca el mismo:
    # `_limpiar_plan` ya garantiza que un plan no repite agente, asi que una
    # arista de un nodo a si mismo seria un camino que no puede ocurrir. Se
    # excluye para que el diagrama del grafo no muestre bucles inexistentes --
    # el diagrama es material de sustentacion, tiene que describir el sistema
    # real y no todas las aristas que el codigo podria haber declarado.
    grafo.add_conditional_edges(
        "planificador", _siguiente,
        {nombre: nombre for nombre in NODOS} | {"cierre": "cierre"},
    )
    for nombre in NODOS:
        grafo.add_conditional_edges(
            nombre, _siguiente,
            {otro: otro for otro in NODOS if otro != nombre} | {"cierre": "cierre"},
        )

    grafo.add_edge("cierre", END)
    return grafo.compile()


def obtener_grafo():
    global _grafo
    if _grafo is None:
        _grafo = _construir_grafo()
    return _grafo


def reiniciar_grafo() -> None:
    """
    Fuerza reconstruir el grafo y los agentes: lo usan los tests y el banco de modelos.

    Sin esto, cambiar `ANTHROPIC_MODEL` u `OPENAI_MODEL` no cambia nada: los tres
    nodos se construyen una sola vez, y el modelo se resuelve al construirlos.
    """
    global _grafo
    _grafo = None
    informacion.reiniciar()
    for modulo in ("reservas", "incidencias"):
        __import__(f"app.agentes.{modulo}", fromlist=["reiniciar"]).reiniciar()
    _ultimo_agente.clear()


# ---------------------------- API del modulo -------------------------------

def responder(entrante: MensajeEntrante, historial: list[dict] | None = None) -> RespuestaClemente:
    """
    Punto de entrada del orquestador: lo unico que llama la capa de comunicacion.

    Devuelve siempre una RespuestaClemente, incluso ante error: un canal de chat
    no puede quedarse mudo.
    """
    contexto = ContextoConversacion(sesion_id=entrante.sesion_id, canal=entrante.canal)
    estado_inicial: EstadoConversacion = {
        "sesion_id": entrante.sesion_id,
        "mensaje": entrante.texto,
        "historial": historial or [],
        "ultimo_agente": _ultimo_agente.get(entrante.sesion_id, ""),
        "contexto": contexto,
        "plan": [],
        "paso": 0,
        "respuestas": [],
        "ruta": "",
        "motivo_ruta": "",
        "respuesta": "",
    }

    inicio = time.perf_counter()
    try:
        final = obtener_grafo().invoke(estado_inicial)
    except Exception as error:
        registrar("error", entrante.sesion_id, detalle={"error": str(error)})
        texto_error = (
            "Disculpa, no puedo procesar tu mensaje en este momento. "
            "Un integrante del equipo del restaurante te va a responder."
        )
        registrar_conversacion(
            sesion_id=entrante.sesion_id, mensaje=entrante.texto, respuesta=texto_error,
            agente="orquestador", canal=entrante.canal, motivo_ruta=f"error: {error}",
            escalado=True, duracion_ms=(time.perf_counter() - inicio) * 1000,
        )
        return RespuestaClemente(
            texto=texto_error,
            agente="orquestador",
            sesion_id=entrante.sesion_id,
            motivo_ruta=f"error: {error}",
            escalado=True,
        )

    plan = final.get("plan") or []
    _ultimo_agente[entrante.sesion_id] = final["ruta"]
    duracion = (time.perf_counter() - inicio) * 1000

    registrar_conversacion(
        sesion_id=entrante.sesion_id, mensaje=entrante.texto, respuesta=final["respuesta"],
        agente=final["ruta"], canal=entrante.canal, motivo_ruta=final["motivo_ruta"],
        escalado=contexto.escalado, duracion_ms=duracion, plan=plan,
    )

    return RespuestaClemente(
        texto=final["respuesta"],
        agente=final["ruta"],
        sesion_id=entrante.sesion_id,
        motivo_ruta=final["motivo_ruta"],
        escalado=contexto.escalado,
        # El plan completo viaja en `datos` para que la evaluacion y el panel
        # puedan ver que un turno se atendio en dos pasos, no solo con quien
        # termino.
        datos={**contexto.datos, "plan": plan},
    )


def olvidar_sesion(sesion_id: str) -> None:
    """
    Al reiniciar un hilo, el planificador deja de arrastrar el agente anterior.

    Tambien se olvida el caso escalado: un hilo nuevo con el mismo identificador
    es otra conversacion, y su escalamiento merece su propio ticket.
    """
    _ultimo_agente.pop(sesion_id, None)
    _escalado_de.pop(sesion_id, None)


def diagrama_mermaid() -> str:
    """
    El grafo tal como LangGraph lo compilo, en texto Mermaid.

    Se genera del grafo real, no de un dibujo a mano: si alguien agrega un nodo
    y se olvida de actualizar el README, este texto lo delata.
    """
    return obtener_grafo().get_graph().draw_mermaid()


def exportar_diagrama(destino: str = "grafo_clemente.png") -> str:
    """
    Exporta el diagrama del grafo (para el informe y la presentacion final).

    El PNG lo renderiza mermaid.ink, que es un servicio externo: si no hay red
    se guarda el `.mmd` al lado, que GitHub y VS Code dibujan igual.
    """
    grafo = obtener_grafo().get_graph()
    try:
        with open(destino, "wb") as archivo:
            archivo.write(grafo.draw_mermaid_png())
        return destino
    except Exception as error:
        alterno = str(Path(destino).with_suffix(".mmd"))
        Path(alterno).write_text(grafo.draw_mermaid(), encoding="utf-8")
        print(f"[grafo] No se pudo renderizar el PNG ({error}). Guardado como {alterno}.")
        return alterno


if __name__ == "__main__":
    # python -m app.orquestador.grafo            -> imprime el grafo en Mermaid
    # python -m app.orquestador.grafo --png      -> lo guarda como imagen
    from ..config import Config

    Config.desde_entorno()
    if "--png" in sys.argv:
        print(f"[grafo] Diagrama en {exportar_diagrama()}")
    else:
        print(diagrama_mermaid())
