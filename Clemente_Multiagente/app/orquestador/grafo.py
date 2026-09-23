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
   mano en el contexto y `_nodo_cierre` registra el ticket y su resultado.
   El envio a Trello depende del backend; este modulo no envia una notificacion
   al cliente ni acredita que el personal haya recibido el caso.
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

import json
import sys
import threading
import time
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field
from typing_extensions import TypedDict

from ..agentes import AGENTES
from ..agentes import autorizacion
from ..reservas import obtener_servicio as servicio_reservas
from ..agentes.contexto import ContextoConversacion
from ..contratos import MensajeEntrante, RespuestaClemente
from ..incidencias import abiertas_de, obtener_servicio as servicio_incidencias
from ..llm import extraer_texto, resolver_modelo
from ..observabilidad.trazas import cronometro, registrar, registrar_conversacion
from ..seguridad.errores import registrar_error
from ..seguridad.pii import redactar_pii
from ..seguridad.trazado import contexto_de_trazado
from . import informacion, limites

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

# Revisiones pausadas por HumanInTheLoopMiddleware. El estado detallado del
# agente vive en su checkpointer; aquí se conserva el contexto de negocio que
# recibirá la tool cuando el staff reanude el mismo thread_id.
_revisiones: dict[str, dict] = {}
# Una revision se resuelve una sola vez: quien la reclama la saca de la cola bajo este candado.
_lock_revisiones = threading.Lock()
ARCHIVO_REVISIONES = Path(__file__).resolve().parent.parent / "agentes" / "datos" / "revisiones_hitl.json"
_revisiones_cargadas = False


def _cargar_revisiones() -> None:
    """Carga una sola vez las revisiones HITL persistidas al registro en memoria.

    Tolera archivo ausente, ilegible o JSON invalido; solo incorpora un
    diccionario. El checkpoint detallado del agente se guarda por separado."""
    global _revisiones_cargadas
    if _revisiones_cargadas:
        return
    try:
        datos = json.loads(ARCHIVO_REVISIONES.read_text(encoding="utf-8"))
        if isinstance(datos, dict):
            _revisiones.update(datos)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        pass
    _revisiones_cargadas = True


def _guardar_revisiones() -> None:
    """Persiste las revisiones mediante archivo temporal y reemplazo del JSON.

    Omite el objeto contexto, que no es serializable; los errores de escritura
    se propagan. Los datos de negocio serializables quedan en cada revision."""
    ARCHIVO_REVISIONES.parent.mkdir(parents=True, exist_ok=True)
    serializable = {
        sid: {clave: valor for clave, valor in item.items() if clave != "contexto"}
        for sid, item in _revisiones.items()
    }
    temporal = ARCHIVO_REVISIONES.with_suffix(".tmp")
    temporal.write_text(json.dumps(serializable, ensure_ascii=False, indent=2), encoding="utf-8")
    temporal.replace(ARCHIVO_REVISIONES)


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
    pendientes: list[str]    # temas que el tope de pasos dejo sin atender

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

Nunca pongas dos veces el mismo paso, y nunca pongas mas de dos. Si el mensaje trae mas
temas de los que caben en dos pasos, atiende los dos mas importantes y escribe en `motivo`
la palabra PENDIENTE: seguida de lo que quedo fuera, para que el cliente sepa que falta.

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
    """Resume los ultimos TURNOS_PARA_ENRUTAR mensajes para el planificador.

    Etiqueta Cliente o Clemente y recorta cada contenido a 220 caracteres;
    sin historial devuelve un marcador. No es un resumen generado por un LLM."""
    if not historial:
        return "(sin conversacion previa)"
    lineas = []
    for mensaje in historial[-TURNOS_PARA_ENRUTAR:]:
        quien = "Cliente" if mensaje.get("role") == "user" else "Clemente"
        lineas.append(f"{quien}: {str(mensaje.get('content', ''))[:220]}")
    return "\n".join(lineas)


# Como se nombra al cliente lo que quedo fuera del plan por el tope de pasos.
TEMA_PENDIENTE = {
    "informacion": "tu consulta sobre el restaurante",
    "reservas": "la reserva",
    "incidencias": "tu reclamo",
    "otros": "el resto de lo que me escribiste",
}


def _pendientes_de(pasos: list[str], plan: list[str], motivo: str) -> list[str]:
    """Temas que el tope dejo fuera: pasos validos que no entraron al plan, o lo que el planificador marco PENDIENTE.

    Antes se descartaban en silencio y la respuesta parecia haber atendido todo.
    Es la lista de lo que NO se hizo, no una priorizacion."""
    fuera = [p for p in dict.fromkeys(pasos) if p in NODOS and p not in plan]
    if not fuera and "PENDIENTE:" in (motivo or "").upper():
        fuera = ["otros"]
    return fuera


def _aviso_pendientes(pendientes: list[str]) -> str:
    """Frase para el cliente con lo que quedo fuera del turno; nunca afirma haberlo resuelto."""
    temas = [TEMA_PENDIENTE.get(p, p) for p in pendientes]
    lista = temas[0] if len(temas) == 1 else ", ".join(temas[:-1]) + " y " + temas[-1]
    return f"Me queda pendiente {lista}: escríbeme sobre eso y lo vemos enseguida."


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
    """Calcula el plan ordenado de resolucion del turno y devuelve la actualizacion del estado.

    Lee mensaje, historial, ultimo_agente y sesion_id. Solicita al modelo
    PlanDeResolucion, elimina pasos repetidos o desconocidos y limita el plan
    a PASOS_MAXIMOS. Escribe plan, paso=0, motivo_ruta y respuestas=[]; registra
    el plan para auditoria, sin responder al cliente ni ejecutar herramientas.

    Sin mensaje devuelve un plan vacio para ir al cierre sin llamar al modelo.
    Si falla la invocacion o procesamiento de la decision, usa ultimo_agente
    o informacion y registra el error. La construccion del modelo ocurre
    antes del try: sus errores se propagan al llamador."""
    from langchain_core.messages import HumanMessage, SystemMessage

    mensaje = _mensaje_de(estado)
    if not mensaje:
        # Sin texto no hay nada que planificar, y llamar al modelo seria gastar
        # por nada. El plan vacio cae directo al cierre.
        registrar("plan", _sesion_de(estado),
                  detalle={"plan": [], "motivo": "turno sin texto"})
        return {"plan": [], "paso": 0, "motivo_ruta": "turno sin texto", "pendientes": [], "respuestas": []}

    venia_de = estado.get("ultimo_agente") or "ninguno"
    entrada = (
        f"Conversacion previa:\n{_resumen_del_hilo(estado.get('historial') or [])}\n\n"
        f"Agente que venia atendiendo: {venia_de}\n\n"
        f"ULTIMO MENSAJE DEL CLIENTE (el que hay que planificar):\n{mensaje}"
    )

    modelo = resolver_modelo(temperature=0.0, rol="enrutador").with_structured_output(
        PlanDeResolucion
    )
    pendientes: list[str] = []
    try:
        decision = modelo.invoke([
            SystemMessage(content=PROMPT_PLANIFICADOR),
            HumanMessage(content=entrada),
        ])
        plan, motivo = _limpiar_plan(decision.pasos), decision.motivo
        pendientes = _pendientes_de(decision.pasos, plan, motivo)
    except Exception as error:
        # Un planificador caido no puede tumbar la conversacion: se cae al agente
        # que venia atendiendo, y si no habia, al mas barato de equivocarse.
        plan = [estado.get("ultimo_agente") or "informacion"]
        registrar_error(_sesion_de(estado), "planificacion", error)
        motivo = "fallback por error de planificacion"

    if not plan:
        plan, motivo = ["informacion"], f"{motivo} (plan vacio, se atiende como consulta)"

    registrar(
        "plan", _sesion_de(estado), agente=plan[0],
        detalle={"plan": plan, "motivo": motivo, "venia_de": venia_de, "pendientes": pendientes},
    )
    return {"plan": plan, "paso": 0, "motivo_ruta": motivo, "pendientes": pendientes, "respuestas": []}


def _nodo_trabajo(nombre: str):
    """Devuelve el nodo ejecutor para un nombre del registro NODOS.

    Se usa para registrar informacion, reservas e incidencias con el mismo
    contrato de estado. La funcion devuelta acumula texto, avanza paso y
    conserva contexto; _siguiente decide la transicion al terminar.
    Un nombre que no exista produce KeyError cuando se ejecuta el nodo.
    """

    def nodo(estado: EstadoConversacion) -> dict:
        """Ejecuta el componente capturado por nombre y devuelve el progreso del turno.

        Lee mensaje, historial, sesion_id y contexto del estado; si falta contexto
        crea uno para Studio. Llama NODOS[nombre], mide su duracion, agrega
        {agente, texto} a respuestas e incrementa paso. Comparte contexto de
        negocio entre pasos; no inserta la respuesta previa en el historial
        del siguiente agente. Los errores del componente se propagan."""
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
    """Selecciona la transicion condicional usando plan y paso, sin llamar al modelo.

    Devuelve plan[paso] mientras queden pasos y no se supere PASOS_MAXIMOS;
    en otro caso devuelve cierre. No modifica el estado. El plan debe estar
    normalizado por _limpiar_plan antes de llegar a esta funcion.
    """
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
        registrar_error(sesion, "sintesis", error)
        return pegado


def _escalamiento_previo(sesion: str) -> str | None:
    """Codigo del ticket de escalamiento que esta conversacion ya abrio, aunque el proceso se haya reiniciado."""
    for caso in abiertas_de(sesion, horas=24):
        if caso.descripcion.startswith("[escalado desde"):
            return caso.id
    return None


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

    abierto = _escalado_de.get(sesion) or _escalamiento_previo(sesion)
    if abierto:
        _escalado_de[sesion] = abierto
        if not servicio.anotar(abierto, f"[dato nuevo del cliente] {detalle}\nDijo: {mensaje}"):
            raise RuntimeError("No se pudo actualizar el caso existente")
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
    Construye la respuesta final del recorrido del grafo y gestiona escalamiento.

    Lee respuestas, sesion_id, mensaje y contexto. Devuelve respuesta, ruta
    y contexto; la ruta conserva el ultimo componente que atendio el turno.
    Sin respuestas devuelve SIN_MENSAJE. Si hay confirmacion_pendiente usa
    el resumen del servidor en lugar del texto de reservas; en otro caso
    sintetiza las respuestas con _sintetizar.

    Si contexto solicita escalamiento, _escalar crea o actualiza el caso y
    registra la traza. Sustituye promesas del modelo por el codigo devuelto,
    sin confirmar una mesa. Si falla, devuelve un aviso y desactiva escalado.
    Un codigo local no acredita entrega a Trello o notificacion al personal.
    La validacion de salida del canal se ejecuta despues, en _atender.
    """
    sesion = _sesion_de(estado)
    respuestas = estado.get("respuestas") or []
    contexto = estado.get("contexto") or ContextoConversacion(sesion_id=sesion, canal="studio")

    if not respuestas:
        return {"respuesta": SIN_MENSAJE, "ruta": "informacion", "contexto": contexto}

    pendiente = contexto.datos.get("confirmacion_pendiente")
    # El resumen autorizado lo escribe el servidor, nunca lo reescribe el LLM.
    if pendiente:
        otros = [r["texto"] for r in respuestas if r["agente"] != "reservas"]
        texto = " ".join(otros + [pendiente])
    else:
        texto = _sintetizar(respuestas, sesion)

    # Escalamiento: el agente levanto la mano, el ticket lo abre el orquestador,
    # que es el unico que tiene el turno completo delante.
    escalamiento = contexto.datos.get("escalamiento")
    if contexto.escalado and escalamiento:
        try:
            codigo = _escalar(sesion, escalamiento, _mensaje_de(estado), contexto)
        except Exception as error:
            registrar_error(sesion, "escalamiento", error)
            contexto.escalado = False
            texto = "No pude registrar el caso para el restaurante. No hay una mesa confirmada por este escalamiento. Contacta directamente al local."
            return {"respuesta": texto, "ruta": respuestas[-1]["agente"], "contexto": contexto}
        registrar("escalado", sesion, agente=respuestas[-1]["agente"],
                  detalle={"incidencia": codigo, **escalamiento})
        # Solo se agrega el codigo si el agente no lo dijo ya. Antes se pegaba
        # siempre una frase completa ("tu caso quedo registrado y una persona te
        # va a contactar") encima de la del agente, que decia exactamente lo
        # mismo: el cliente leia la promesa dos veces.
        # Sustituye la promesa del modelo: el codigo real existe recien aqui.
        texto = (f"Tu solicitud quedó registrada con el código {codigo}. "
                 "La mesa todavía no está confirmada. Puedes consultar el estado de tu caso al restaurante.")
        otros = [r["texto"] for r in respuestas if r["agente"] != "reservas"]
        if otros:
            texto = " ".join(otros + [texto])
        if pendiente:
            texto += " " + pendiente

    pendientes = estado.get("pendientes") or []
    if pendientes:
        texto = f"{texto} {_aviso_pendientes(pendientes)}"

    return {
        "respuesta": texto,
        # Con quien queda la conversacion: es lo que el proximo turno usara como
        # continuidad, asi que es el ULTIMO que hablo, no el primero.
        "ruta": respuestas[-1]["agente"],
        "contexto": contexto,
    }


def _construir_grafo():
    """Construye y compila el StateGraph que ejecuta la orquestacion.

    Registra planificador, componentes de NODOS y cierre. START conduce al
    planificador; _siguiente decide cada paso mediante aristas condicionales;
    cierre conduce a END. Devuelve el grafo compilado sin ejecutar modelos.
    El grafo externo no configura checkpointer; reservas configura el suyo."""
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
    """Devuelve el grafo compilado del proceso, construyendolo solo en la primera llamada."""
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
    limites.reiniciar()


# ---------------------------- API del modulo -------------------------------

def _respuesta_de_limite(entrante: MensajeEntrante, texto: str, motivo: str) -> RespuestaClemente:
    """Respuesta fija de seguridad para un mensaje limitado; no llama al modelo y deja traza."""
    registrar("limite", entrante.sesion_id, detalle={"motivo": motivo})
    return RespuestaClemente(
        texto=texto, agente="seguridad", sesion_id=entrante.sesion_id,
        motivo_ruta=f"limite: {motivo}", datos={"guardrail": "limite"},
    )


def responder(
    entrante: MensajeEntrante, historial: list[dict] | None = None,
    cliente: dict | None = None, chat_key: str | None = None,
) -> RespuestaClemente:
    """Punto de entrada del orquestador: lo unico que llama la capa de comunicacion.

    `cliente` es la ficha que comunicacion ya resolvio contra `customers` en
    Postgres (`customers_repository.get_customer`, columnas tipadas + jsonb
    `data` al mismo nivel); `chat_key` viaja aparte porque no siempre se puede
    derivar del `sesion_id` (ver `ContextoConversacion.chat_key`). Ninguno de
    los dos es obligatorio: sin ellos el turno sigue funcionando como hasta
    ahora, solo que el agente no trae identidad previa del cliente.

    Antes de gastar una llamada al modelo rechaza un mensaje demasiado largo o una
    rafaga de mensajes (ver `limites`), y serializa los turnos de una misma
    conversacion para que dos mensajes simultaneos no lean y escriban a la vez la
    propuesta, la continuidad ni el ticket. El turno en si esta en `_responder_turno`."""
    if limites.demasiado_largo(entrante.texto):
        return _respuesta_de_limite(entrante, limites.MENSAJE_LARGO, "mensaje demasiado largo")
    if limites.excede_frecuencia(entrante.sesion_id):
        return _respuesta_de_limite(entrante, limites.MENSAJE_RAPIDO, "demasiados mensajes por minuto")
    with limites.un_turno_a_la_vez(entrante.sesion_id) as turno:
        if not turno:
            return _respuesta_de_limite(entrante, limites.MENSAJE_OCUPADO, "turno anterior sin terminar")
        return _responder_turno(entrante, historial, cliente, chat_key)


def _responder_turno(
    entrante: MensajeEntrante, historial: list[dict] | None = None,
    cliente: dict | None = None, chat_key: str | None = None,
) -> RespuestaClemente:
    """
    Atiende un turno ya admitido por los limites de `responder`.

    Crea el contexto y estado del turno. Primero intenta confirmar un permiso
    exacto mediante autorizacion.confirmar: esa operacion no llama al LLM.
    Para texto conversacional descarta la propuesta anterior y ejecuta el
    grafo compilado. Actualiza continuidad, guarda revisiones HITL pendientes
    y registra el turno con el plan completo para auditoria.

    Devuelve RespuestaClemente con texto, ruta, motivo y datos de negocio.
    Captura errores del bloque de confirmacion/ejecucion y construye un aviso;
    errores posteriores de persistencia no estan cubiertos por ese bloque.
    El bloqueo PII y Guardrails AI del canal pertenecen a _atender: invocar
    esta funcion directamente no ejecuta esas validaciones HTTP.
    """
    contexto = ContextoConversacion(
        sesion_id=entrante.sesion_id, canal=entrante.canal,
        chat_key=chat_key or "", cliente=cliente or {},
    )
    estado_inicial: EstadoConversacion = {
        "sesion_id": entrante.sesion_id,
        "mensaje": entrante.texto,
        "historial": historial or [],
        "ultimo_agente": _ultimo_agente.get(entrante.sesion_id, ""),
        "contexto": contexto,
        "plan": [],
        "paso": 0,
        "pendientes": [],
        "respuestas": [],
        "ruta": "",
        "motivo_ruta": "",
        "respuesta": "",
    }

    inicio = time.perf_counter()
    try:
        confirmada = autorizacion.confirmar(entrante.sesion_id, entrante.texto, servicio_reservas())
        if confirmada is not None:
            texto, datos = confirmada
            contexto.datos.update(datos)
            final = {"respuesta": texto, "ruta": "reservas", "motivo_ruta": "confirmacion validada por el servidor", "plan": ["reservas"]}
            registrar("plan", entrante.sesion_id, agente="reservas", detalle={"plan": ["reservas"], "motivo": final["motivo_ruta"]})
            registrar("operacion", entrante.sesion_id, agente="reservas", detalle={"salida": texto, **datos})
        else:
            # Un nuevo pedido invalida el resumen anterior; no se confirma algo
            # que quedo atras en la conversacion. Las tools pueden proponer otro.
            autorizacion.descartar(entrante.sesion_id)
            with contexto_de_trazado():
                final = obtener_grafo().invoke(estado_inicial)
    except Exception as error:
        registrar_error(entrante.sesion_id, "turno", error)
        texto_error = (
            "Disculpa, no puedo procesar tu mensaje en este momento. "
            "No puedo asegurar que la operación se haya completado. "
            "Consulta al restaurante antes de repetirla; tampoco puedo confirmar el envío de un aviso."
        )
        registrar_conversacion(
            sesion_id=entrante.sesion_id, mensaje=redactar_pii(entrante.texto), respuesta=texto_error,
            agente="orquestador", canal=entrante.canal, motivo_ruta=f"error: {type(error).__name__}",
            escalado=False, duracion_ms=(time.perf_counter() - inicio) * 1000,
        )
        return RespuestaClemente(
            texto=texto_error,
            agente="orquestador",
            sesion_id=entrante.sesion_id,
            motivo_ruta="error de procesamiento",
            escalado=False,
        )

    plan = final.get("plan") or []
    revision = contexto.datos.get("revision_humana")
    if revision and revision.get("estado") == "pendiente":
        _cargar_revisiones()
        _revisiones[entrante.sesion_id] = {
            "sesion_id": entrante.sesion_id,
            "contexto": contexto,
            "solicitud": revision.get("solicitud", {}),
            "canal": entrante.canal,
        }
        _guardar_revisiones()
    _ultimo_agente[entrante.sesion_id] = final["ruta"]
    duracion = (time.perf_counter() - inicio) * 1000

    registrar_conversacion(
        sesion_id=entrante.sesion_id, mensaje=redactar_pii(entrante.texto), respuesta=redactar_pii(final["respuesta"]),
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
    _cargar_revisiones()
    if _revisiones.pop(sesion_id, None) is not None:
        _guardar_revisiones()
    autorizacion.descartar(sesion_id)


def revisiones_pendientes() -> list[dict]:
    """Vista serializable para el panel/API del staff; no expone objetos internos."""
    _cargar_revisiones()
    return [
        {"sesion_id": sid, "solicitud": item["solicitud"], "canal": item["canal"]}
        for sid, item in _revisiones.items()
    ]


def resolver_revision(sesion_id: str, decision: str, motivo: str = "") -> RespuestaClemente:
    """Aprueba o rechaza la ejecución pausada y termina el turno en el cierre único.

    Una revisión se resuelve UNA sola vez: se reclama sacándola de la cola bajo un
    candado antes de reanudar el agente. Un segundo approve, un reject posterior o
    dos peticiones simultáneas reciben KeyError (404) y no reanudan nada. Si la
    reanudación falla, la revisión vuelve a la cola para que el personal reintente."""
    with _lock_revisiones:
        _cargar_revisiones()
        pendiente = _revisiones.pop(sesion_id, None)
    if pendiente is None:
        raise KeyError("No existe una revisión pendiente para esa sesión")
    try:
        respuesta = _ejecutar_resolucion(sesion_id, decision, motivo, pendiente)
    except Exception:
        with _lock_revisiones:
            _revisiones[sesion_id] = pendiente
        raise
    _guardar_revisiones()
    return respuesta


def _ejecutar_resolucion(sesion_id: str, decision: str, motivo: str, pendiente: dict) -> RespuestaClemente:
    """Reanuda el agente con la decisión del personal y arma la respuesta de cierre.

    Recibe la revisión ya reclamada por `resolver_revision`; valida la decisión
    (approve o reject) y propaga los errores del agente."""
    if decision not in {"approve", "reject"}:
        raise ValueError("La decisión debe ser approve o reject")

    from ..agentes import reservas

    contexto = pendiente.get("contexto") or ContextoConversacion(
        sesion_id=sesion_id, canal=pendiente.get("canal", "webchat"),
    )
    decision_hitl = {"type": decision}
    if motivo:
        decision_hitl["message"] = motivo
    with contexto_de_trazado():
        texto_agente = reservas.resolver_revision(sesion_id, decision_hitl, contexto)
    contexto.datos["revision_humana"] = {
        "estado": "aprobada" if decision == "approve" else "rechazada",
        "flujo": "reservas", "decision": decision, "motivo": motivo,
    }
    final = _nodo_cierre({
        "sesion_id": sesion_id,
        "mensaje": f"decisión del staff: {decision}",
        "contexto": contexto,
        "respuestas": [{"agente": "reservas", "texto": texto_agente}],
    })
    registrar(
        "hitl_resuelto", sesion_id, agente="reservas",
        detalle={"decision": decision, "motivo": motivo},
    )
    return RespuestaClemente(
        texto=final["respuesta"], agente="reservas", sesion_id=sesion_id,
        motivo_ruta="revisión humana de excepción de capacidad",
        escalado=contexto.escalado, datos=contexto.datos,
    )


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
