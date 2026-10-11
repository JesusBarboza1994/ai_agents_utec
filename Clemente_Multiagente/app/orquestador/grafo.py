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
import re
import sys
import threading
import time
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field
from typing_extensions import TypedDict

from ..agentes import AGENTES
from ..agentes import autorizacion
from ..agentes import fecha as reloj
from ..agentes.prompts import HORARIO_DE_ATENCION, TELEFONO_RESTAURANTE
from ..reservas import obtener_servicio as servicio_reservas
from ..agentes.contexto import ContextoConversacion
from ..contratos import MensajeEntrante, RespuestaClemente
from ..incidencias import abiertas_de, obtener_servicio as servicio_incidencias
from ..llm import extraer_texto, resolver_modelo
from ..observabilidad.trazas import cronometro, registrar, registrar_conversacion
from ..seguridad.errores import registrar_error
from ..datos import carpeta_de_datos
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

# Paso que se le ofrecio al cliente en el turno anterior porque dependia de otro
# ("si tienen opciones veganas, reserva"): sesion_id -> {"agente", "tarea"}. Vive un
# solo turno: el siguiente lo usa si el cliente acepta y se descarta en cualquier caso.
# En memoria, como `_ultimo_agente`: un reinicio lo pierde y el planificador se guia
# por el hilo; cualquier operacion igual exige CONFIRMO.
_pendiente_de: dict[str, dict] = {}

# Revisiones pausadas por HumanInTheLoopMiddleware. El estado detallado del
# agente vive en su checkpointer; aquí se conserva el contexto de negocio que
# recibirá la tool cuando el staff reanude el mismo thread_id.
_revisiones: dict[str, dict] = {}
# Una revision se resuelve una sola vez: quien la reclama la saca de la cola bajo este candado.
_lock_revisiones = threading.Lock()
# Sesiones cuya revision esta reanudando el staff en este momento: su hilo no se toca.
_resolviendo: set[str] = set()

# Una pausa sin decision del staff vence: el cliente no puede quedar atrapado para siempre.
VENCIMIENTO_REVISION_SEGUNDOS = 24 * 60 * 60

# Comando exacto, como CONFIRMO, para que el cliente retire una solicitud que espera al staff.
# Es un comando y no una frase libre para no confundirlo con "cancelar mi reserva".
COMANDO_CANCELAR = re.compile(r"\s*CANCELAR\s+SOLICITUD\s*[.!]?\s*", re.IGNORECASE)
SOLICITUD_CANCELADA = "Listo, cancelé tu solicitud. ¿Te ayudo con otra reserva?"
SOLICITUD_EN_RESOLUCION = ("Tu solicitud ya la está resolviendo el equipo del restaurante; "
                           "en un momento tendrás la respuesta.")
NO_SE_PUDO_CANCELAR = ("No pude cancelar tu solicitud en este momento. Escríbeme de nuevo "
                       "CANCELAR SOLICITUD en unos minutos.")
PAUSA_SIN_VIGENCIA = ("Tu solicitud anterior al equipo ya no estaba vigente, así que la cerré. "
                      "¿Me cuentas de nuevo qué necesitas?")
ARCHIVO_REVISIONES = carpeta_de_datos(Path(__file__).resolve().parent.parent / "agentes" / "datos") / "revisiones_hitl.json"
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


def _es_cancelar_solicitud(texto: str) -> bool:
    """True si el mensaje es exactamente el comando CANCELAR SOLICITUD (sin importar mayusculas)."""
    return bool(COMANDO_CANCELAR.fullmatch(texto or ""))


def _cancelar_solicitud(sesion_id: str) -> str | None:
    """Retira la solicitud que espera al staff y libera el hilo; None si no habia ninguna.

    Funciona tambien con una pausa huerfana (hilo pausado sin entrada en la cola). Si el
    staff la esta resolviendo en este momento no toca nada. Si no se pudo borrar la
    pausa, la solicitud queda como estaba y se avisa sin anunciar la cancelacion."""
    from ..agentes import reservas

    with _lock_revisiones:
        _cargar_revisiones()
        if sesion_id in _resolviendo:
            return SOLICITUD_EN_RESOLUCION
        if sesion_id not in _revisiones and not reservas.tiene_hilo_guardado(sesion_id):
            return None
        if not reservas.liberar_pausa(sesion_id):
            registrar("error", sesion_id, detalle={"paso": "cancelar_solicitud"})
            return NO_SE_PUDO_CANCELAR
        retirada = _revisiones.pop(sesion_id, None)
    if retirada is not None:
        _guardar_revisiones()
    registrar("solicitud_cancelada", sesion_id, agente="reservas",
              detalle={"estaba_en_cola": retirada is not None})
    return SOLICITUD_CANCELADA


def _liberar_pausa_sin_vigencia(sesion_id: str) -> str | None:
    """Libera un hilo pausado cuya solicitud ya no puede resolverse; devuelve el texto para el cliente o None.

    Dos casos: la solicitud ya no esta en la cola (alguien reinicio la sesion o se
    perdio el archivo), o lleva mas de VENCIMIENTO_REVISION_SEGUNDOS sin decision. A
    una solicitud guardada antes de existir el vencimiento se le pone la hora de hoy."""
    from ..agentes import reservas

    ahora = time.time()
    with _lock_revisiones:
        _cargar_revisiones()
        if sesion_id in _resolviendo:
            return None
        pendiente = _revisiones.get(sesion_id)
        if pendiente is not None and "creada" not in pendiente:
            pendiente["creada"] = ahora
            _guardar_revisiones()
            return None
        if pendiente is not None and ahora - pendiente["creada"] < VENCIMIENTO_REVISION_SEGUNDOS:
            return None
        if not reservas.liberar_pausa(sesion_id):
            return None
        _revisiones.pop(sesion_id, None)
        _guardar_revisiones()
    registrar("pausa_liberada", sesion_id, agente="reservas",
              detalle={"motivo": "vencida" if pendiente is not None else "huerfana"})
    return PAUSA_SIN_VIGENCIA


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

    tarea_ofrecida: dict     # paso que se le ofrecio al cliente el turno anterior, si lo hay

    # --- lo que produce el planificador ---
    plan: list[str]          # pasos en orden, p. ej. ["incidencias", "reservas"]
    tareas: list[str]        # una tarea por paso, alineada con `plan` ("" = sin tarea)
    paso: int                # cual de esos pasos toca ahora
    motivo_ruta: str
    pendientes: list[str]    # temas que el tope de pasos dejo sin atender
    accion: str              # delegar | escalar_humano | responder_directo
    respuesta_directa: str   # texto del planificador cuando no hace falta un agente
    entendimiento: str
    restricciones: list[str]
    datos_resueltos: dict
    diferido: dict           # paso que depende del primero: se ofrece, no se ejecuta

    # --- lo que producen los nodos de trabajo ---
    respuestas: list[dict]   # [{"agente": "reservas", "texto": "..."}]

    # --- lo que arma el cierre ---
    ruta: str                # componente que respondio el turno (para metricas y UI)
    continuar_con: str       # componente que atiende el proximo mensaje (continuidad)
    respuesta: str           # texto unico que ve el cliente


Restriccion = Literal[
    "dia_cerrado", "fuera_de_horario", "grupo_grande", "pide_humano",
    "reclamo", "condicional", "fuera_de_alcance",
]


class DatosResueltos(BaseModel):
    """Datos del pedido que el planificador ya pudo fijar con el hilo y el calendario.

    Viajan en la tarea del componente; las herramientas los vuelven a validar."""

    fecha: str | None = Field(None, description="Fecha en formato AAAA-MM-DD, si se sabe")
    dia: str | None = Field(None, description="Dia de la semana de esa fecha")
    hora: str | None = Field(None, description="Hora en formato HH:MM, si se sabe")
    personas: int | None = Field(None, description="Numero de personas, si se sabe")


class PlanDeResolucion(BaseModel):
    """Salida forzada del planificador: que entendio, que decide y a quien delega.

    Los campos nuevos son opcionales con valor por defecto None A PROPOSITO: en Azure la
    salida estructurada es estricta y el SDK de OpenAI solo quita del esquema los valores
    por defecto None; uno como [] o "delegar" podria hacer que Azure rechace cada llamada.
    El codigo interpreta None como el valor por defecto. `pasos` y `motivo` siguen siendo
    obligatorios, asi que `PlanDeResolucion(pasos=[...], motivo=...)` funciona como antes."""

    entendimiento: str | None = Field(None, description="Que pide el cliente, en maximo 15 palabras")
    datos_resueltos: DatosResueltos | None = Field(None, description="Fecha, hora y personas ya fijadas")
    restricciones: list[Restriccion] | None = Field(None, description="Restricciones que aplican al pedido")
    accion: Literal["delegar", "escalar_humano", "responder_directo"] | None = Field(
        None, description="Como se atiende el mensaje",
    )
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
            "plato, una reserva que no aparecio, un reclamo sin respuesta). Vacio si la "
            "accion no es delegar."
        ),
    )
    tareas: list[str] | None = Field(None, description="Una tarea por paso, en el mismo orden")
    depende_del_anterior: bool | None = Field(
        None, description="True si el segundo paso depende de la respuesta del primero",
    )
    respuesta_directa: str | None = Field(None, description="Solo si la accion es responder_directo")
    motivo: str = Field(..., description="Una frase corta explicando el plan")


PROMPT_PLANIFICADOR = f"""Eres el orquestador de Clemente, restaurante en Barranco. No conversas con
el cliente: decides como se atiende su ULTIMO mensaje. Recibes el hilo reciente, el componente
que venia atendiendo, la tarea que se le ofrecio al cliente en el turno anterior (si la hay), la
fecha de Lima con los proximos dias y este horario:

{HORARIO_DE_ATENCION}

Componentes:
- informacion: datos generales del restaurante (horarios, direccion, carta, estacionamiento,
  opciones vegetarianas, politicas, promociones). Solo consulta.
- reservas: disponibilidad, reservar, modificar, cancelar o ver reservas propias; guarda los
  datos personales que el cliente cuenta.
- incidencias: reclamos por algo que ya ocurrio y consulta de reclamos anteriores.

1. Entiende. En `entendimiento`, maximo 15 palabras. En `datos_resueltos`, la fecha (AAAA-MM-DD
   y su dia), la hora y las personas que esten en el mensaje o en el hilo. Convierte "el lunes" o
   "manana" con el calendario que recibes, nunca de memoria. Si dudas, dejalo vacio.

2. Marca en `restricciones` las que apliquen:
   - dia_cerrado o fuera_de_horario: una reserva nueva o un cambio de reserva cae fuera del
     horario, sumando lo dicho antes en el hilo. Ver o cancelar una reserva existente no tiene
     esta restriccion.
   - grupo_grande: mas de 8 personas.
   - pide_humano: pide hablar con una persona, o acepta una oferta de Clemente de dejar su
     pedido al equipo.
   - reclamo: se queja de algo que ya ocurrio.
   - condicional: un pedido depende de la respuesta a otro ("si si", "si se puede").
   - fuera_de_alcance: algo que no es del restaurante.

3. Elige `accion`, la primera que aplique:
   a. escalar_humano: pide_humano sin reclamo. Si hay reclamo, delega a incidencias: el caso que
      registra es lo que ve el equipo.
   b. responder_directo: el mensaje es SOLO un saludo, un agradecimiento, una despedida o algo
      fuera de alcance, sin ningun pedido del restaurante. Escribe `respuesta_directa` en una o
      dos frases con la voz de Clemente: calida, tuteando con respeto. Si es fuera de alcance,
      declinalo y ofrece lo que si hace Clemente. Un saludo junto a un pedido NO es respuesta
      directa.
   c. delegar: todo lo demas.

4. Si delegas, arma `pasos` con los nombres de los componentes (uno o dos; nunca el mismo dos
   veces) y `tareas`, una por paso y en el mismo orden.
   - Cada tarea: una o dos frases con la parte del mensaje que atiende ese componente, los datos
     resueltos y las restricciones que lo afectan. Ejemplo: "Reserva para 10 el lunes
     2026-10-12. El restaurante no atiende los lunes: ofrecele otro dia antes de pedir datos."
   - Orden: lo que ya salio mal va antes que lo que viene; una pregunta que condiciona una
     reserva va antes de la reserva.
   - Si el segundo paso depende de la respuesta del primero, marca `depende_del_anterior`: ese
     paso no se hace en este turno, se le ofrece al cliente.
   - Tarea ofrecida en el turno anterior: si el cliente la acepta ("si", "dale", "ok"), un solo
     paso con ese componente y esa tarea. Si la rechaza o cambia de tema, ignorala y planifica
     el mensaje nuevo. Si no hay tarea ofrecida y no queda claro que acepta, la tarea del paso es
     pedirle que aclare.
   - Continuidad: si el mensaje completa lo que se venia hablando (un dato suelto, un nombre, un
     telefono, una fecha, un codigo, un si o un no), un solo paso con el componente que venia
     atendiendo. Cambia solo ante una senal clara de otro alcance o ante pide_humano.
   - Un pedido de mesa (reservar, cambiar o cancelar una reserva, ver las reservas propias)
     SIEMPRE lleva el paso 'reservas', aunque el mensaje traiga algo que no es del restaurante.
     Lo que no es del restaurante NO es un paso: el agente que atiende el pedido de mesa lo
     declina en una frase.
   - Cuando el cliente cuenta algo suyo sin preguntar nada (su nombre, un telefono, una mascota,
     su cumpleanos), es un dato para su ficha: va a 'reservas', que es quien lo guarda, incluso
     si venia hablando con 'informacion'. Si ademas pregunta por una politica (por ejemplo, si
     puede ir con su mascota), primero 'informacion' y despues 'reservas'.
   - IMAGENES: si el mensaje trae una imagen (lo indica la linea "[El cliente adjunto ...]") o
     pregunta por una imagen reciente del hilo ("[imagen del cliente] ..."), decides por lo que
     el cliente quiere hacer con ella, no por el componente que venia atendiendo; esta regla le gana a la
de continuidad. Si muestra algo que salio mal (un plato, la cuenta, el local) es 'incidencias';
     si pregunta que es, como es el local o la compara con el restaurante, es 'informacion'; solo
     es 'reservas' si la usa para su reserva. Una imagen ajena al restaurante va a 'informacion'.
   - Si hay mas temas de los que caben en dos pasos, atiende los dos mas importantes y escribe
     en `motivo` la palabra PENDIENTE: seguida de lo que quedo fuera.
   - Ante la duda entre informacion y reservas, sin hilo previo, elige 'informacion'.

`motivo`: una frase corta. Nunca afirmes disponibilidad, codigos ni politicas: eso lo resuelven
los componentes con sus herramientas."""


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
SIN_MENSAJE = "No me llegó ningún mensaje. Escríbeme qué necesitas y te ayudo."


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


def _normalizar_pasos(pasos: list[str], tareas: list[str] | None = None) -> list[tuple[str, str]]:
    """Pasos ejecutables con su tarea: sin repetidos, sin desconocidos, con tope y SIN separar paso y tarea.

    Cada tarea se une a su paso por la posicion que trajo el modelo ANTES de limpiar;
    asi descartar un repetido o recortar el plan nunca le pasa a un componente la
    tarea de otro. Si faltan tareas, el paso queda con tarea vacia (corre como antes);
    las tareas sobrantes se ignoran."""
    tareas = list(tareas or [])
    pares: list[tuple[str, str]] = []
    vistos: set[str] = set()
    for indice, paso in enumerate(pasos or []):
        if paso not in NODOS or paso in vistos:
            continue
        vistos.add(paso)
        tarea = tareas[indice] if indice < len(tareas) else ""
        pares.append((paso, str(tarea or "").strip()))
    return pares[:PASOS_MAXIMOS]


def _texto_de_datos(datos: dict) -> str:
    """Datos resueltos en una linea para la tarea ("fecha 2026-10-12 (lunes), hora 20:00, personas 10")."""
    partes = []
    if datos.get("fecha"):
        dia = f" ({datos['dia']})" if datos.get("dia") else ""
        partes.append(f"fecha {datos['fecha']}{dia}")
    if datos.get("hora"):
        partes.append(f"hora {datos['hora']}")
    if datos.get("personas"):
        partes.append(f"personas {datos['personas']}")
    return ", ".join(partes)


# ------------------------------- nodos -------------------------------------

def _nodo_planificador(estado: EstadoConversacion) -> dict:
    """Decide como se atiende el turno: entiende, marca restricciones, elige accion y delega con tareas.

    Lee mensaje, historial, ultimo_agente, tarea_ofrecida y sesion_id, y recibe el
    calendario de Lima. Pide al modelo PlanDeResolucion y lo normaliza en codigo:
    pasos con su tarea (sin repetidos, con tope), un segundo paso dependiente se
    difiere (se ofrece, no se ejecuta), y escalar_humano marca el escalamiento para
    que lo abra el cierre. No responde al cliente ni ejecuta herramientas.

    Sin mensaje devuelve un plan vacio para ir al cierre sin llamar al modelo.
    Si falla la invocacion o procesamiento de la decision, usa ultimo_agente
    o informacion sin tarea y registra el error. La construccion del modelo ocurre
    antes del try: sus errores se propagan al llamador."""
    from langchain_core.messages import HumanMessage, SystemMessage

    mensaje = _mensaje_de(estado)
    sesion = _sesion_de(estado)
    contexto = estado.get("contexto") or ContextoConversacion(sesion_id=sesion, canal="studio")
    imagenes = contexto.imagenes
    if not mensaje and not imagenes:
        # Sin texto ni imagen no hay nada que planificar, y llamar al modelo seria
        # gastar por nada. El plan vacio cae directo al cierre.
        registrar("plan", sesion, detalle={"plan": [], "motivo": "turno sin texto"})
        return {"plan": [], "tareas": [], "paso": 0, "motivo_ruta": "turno sin texto",
                "pendientes": [], "respuestas": [], "accion": "delegar", "contexto": contexto}

    venia_de = estado.get("ultimo_agente") or "ninguno"
    ofrecida = estado.get("tarea_ofrecida") or {}
    entrada = (
        f"{reloj.calendario_para_planificador()}\n\n"
        f"Conversacion previa:\n{_resumen_del_hilo(estado.get('historial') or [])}\n\n"
        f"Agente que venia atendiendo: {venia_de}\n\n"
    )
    if ofrecida.get("agente"):
        entrada += (f"Tarea ofrecida en el turno anterior: {ofrecida['agente']} -- "
                    f"{ofrecida.get('tarea') or 'continuar con lo que se venia hablando'}\n\n")
    entrada += f"ULTIMO MENSAJE DEL CLIENTE (el que hay que planificar):\n{mensaje or '(sin texto)'}"
    if imagenes:
        # El planificador no mira la imagen (es texto y barato); solo sabe que
        # existe. El agente elegido es el que la recibe y la ve.
        entrada += f"\n[El cliente adjunto {len(imagenes)} imagen(es) en este mensaje.]"

    modelo = resolver_modelo(temperature=0.0, rol="enrutador").with_structured_output(
        PlanDeResolucion
    )
    pendientes: list[str] = []
    entendimiento, restricciones, datos, respuesta_directa = "", [], {}, ""
    diferido: dict = {}
    try:
        decision = modelo.invoke([
            SystemMessage(content=PROMPT_PLANIFICADOR),
            HumanMessage(content=entrada),
        ])
        motivo = decision.motivo
        accion = decision.accion or "delegar"
        entendimiento = (decision.entendimiento or "").strip()
        restricciones = list(decision.restricciones or [])
        if decision.datos_resueltos is not None:
            datos = decision.datos_resueltos.model_dump(exclude_none=True)
        respuesta_directa = (decision.respuesta_directa or "").strip()
        if accion == "responder_directo" and not respuesta_directa:
            # Sin texto no hay respuesta directa: se atiende como un pedido mas.
            accion = "delegar"
        pares: list[tuple[str, str]] = []
        if accion == "delegar":
            pares = _normalizar_pasos(decision.pasos, decision.tareas)
            pendientes = _pendientes_de(decision.pasos, [paso for paso, _ in pares], motivo)
            if (len(pares) == 1 and not pares[0][1] and ofrecida.get("agente") == pares[0][0]):
                # Acepto lo que se le ofrecio: si el modelo no copio la tarea, se usa la guardada.
                pares = [(pares[0][0], ofrecida.get("tarea") or "")]
            if decision.depende_del_anterior and len(pares) == 2:
                # La condicion no se puede acreditar en codigo: el paso dependiente no se
                # ejecuta en este turno, se le ofrece al cliente.
                diferido = {"agente": pares[1][0], "tarea": pares[1][1]}
                pares = pares[:1]
    except Exception as error:
        # Un planificador caido no puede tumbar la conversacion: se cae al agente
        # que venia atendiendo, y si no habia, al mas barato de equivocarse.
        accion = "delegar"
        pares = [(estado.get("ultimo_agente") or "informacion", "")]
        registrar_error(sesion, "planificacion", error)
        motivo = "fallback por error de planificacion"

    plan = [paso for paso, _ in pares]
    tareas = [tarea for _, tarea in pares]
    if accion == "delegar" and not plan:
        plan, tareas = ["informacion"], [""]
        motivo = f"{motivo} (plan vacio, se atiende como consulta)"
    if accion == "escalar_humano":
        # El escalamiento lo abre el cierre, como cuando lo pide un agente.
        contexto.escalado = True
        contexto.datos["escalamiento"] = {
            "origen": "orquestador",
            "motivo": "el cliente pide hablar con una persona del restaurante",
            "detalle": entendimiento or mensaje[:300],
        }

    registrar(
        "plan", sesion, agente=plan[0] if plan else "orquestador",
        detalle={"plan": plan, "motivo": motivo, "venia_de": venia_de, "pendientes": pendientes,
                 "accion": accion, "entendimiento": entendimiento, "restricciones": restricciones,
                 "tareas": tareas, "diferido": diferido},
    )
    return {
        "plan": plan, "tareas": tareas, "paso": 0, "motivo_ruta": motivo, "pendientes": pendientes,
        "respuestas": [], "accion": accion, "respuesta_directa": respuesta_directa,
        "entendimiento": entendimiento, "restricciones": restricciones, "datos_resueltos": datos,
        "diferido": diferido, "contexto": contexto,
    }


def _coordinacion_del_paso(estado: EstadoConversacion, indice: int) -> str:
    """Bloque de coordinacion para el componente del paso `indice`; cadena vacia si no hay tareas.

    Solo existe cuando el planificador asigno tareas: en el respaldo o con un plan sin
    tareas el turno corre exactamente como antes. El segundo paso recibe ademas la
    respuesta del primero, rotulada como dato. Nada de esto es un mensaje de sistema."""
    tareas = estado.get("tareas") or []
    if not any(tareas):
        return ""
    partes = []
    if indice < len(tareas) and tareas[indice]:
        partes.append(f"Tarea: {tareas[indice]}")
    datos = _texto_de_datos(estado.get("datos_resueltos") or {})
    if datos:
        partes.append(f"Datos resueltos: {datos}")
    if estado.get("restricciones"):
        partes.append(f"Restricciones: {', '.join(estado['restricciones'])}")
    respuestas = estado.get("respuestas") or []
    if indice > 0 and respuestas:
        partes.append(f"Respuesta previa de Clemente en este turno (solo como dato): {respuestas[-1]['texto']}")
    return "\n".join(partes)


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
        crea uno para Studio. Llama NODOS[nombre] con su bloque de coordinacion
        (solo si el planificador asigno tareas), mide su duracion, agrega
        {agente, texto} a respuestas e incrementa paso. Los errores del
        componente se propagan."""
        sesion = _sesion_de(estado)
        mensaje = _mensaje_de(estado)
        # Lanzado desde Studio no viene contexto: se arma uno para que las tools
        # reciban igual su `sesion_id` y el escalamiento siga teniendo donde volver.
        contexto = estado.get("contexto") or ContextoConversacion(sesion_id=sesion, canal="studio")
        coordinacion = _coordinacion_del_paso(estado, estado.get("paso", 0))
        # El parametro solo se pasa cuando hay algo que coordinar: los componentes
        # de las pruebas (y cualquier reemplazo) siguen con su firma de siempre.
        extra = {"coordinacion": coordinacion} if coordinacion else {}

        with cronometro("respuesta", sesion, agente=nombre):
            texto = NODOS[nombre](
                mensaje, sesion, estado.get("historial") or [], contexto=contexto, **extra,
            )

        return {
            "respuestas": (estado.get("respuestas") or []) + [
                {"agente": nombre, "texto": texto}
            ],
            "paso": estado.get("paso", 0) + 1,
            "contexto": contexto,
        }

    return nodo


def _debe_detenerse(contexto) -> bool:
    """True si el turno no debe seguir con otro componente despues del paso actual.

    Se detiene ante una revision humana pendiente, un hilo que ya estaba pausado,
    un acceso denegado o una operacion preparada que espera CONFIRMO. No usa el modelo."""
    if contexto is None:
        return False
    datos = contexto.datos
    revision = datos.get("revision_humana") or {}
    return bool(
        revision.get("estado") == "pendiente"
        or datos.get("hilo_en_revision")
        or datos.get("guardrail_autorizacion")
        or datos.get("confirmacion_pendiente")
    )


def _siguiente(estado: EstadoConversacion) -> str:
    """Selecciona la transicion condicional usando plan, paso y estado del turno, sin llamar al modelo.

    Devuelve plan[paso] mientras queden pasos y no se supere PASOS_MAXIMOS; antes de
    un segundo paso revisa _debe_detenerse y, si corresponde, va al cierre. No
    modifica el estado: lo que quedo sin atender lo avisa el cierre."""
    plan = estado.get("plan") or []
    paso = estado.get("paso", 0)
    if paso < len(plan) and paso < PASOS_MAXIMOS:
        if paso > 0 and _debe_detenerse(estado.get("contexto")):
            return "cierre"
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
    existe, que es donde la persona que atiende lo va a leer. Un pedido de hablar
    con una persona (origen orquestador) se registra con tipo "otro": no es de mesa.
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

    origen = escalamiento.get("origen", "agente")
    incidencia = servicio.crear_incidencia(
        sesion_id=sesion,
        descripcion=(
            f"[escalado desde {origen}] {detalle}\n"
            f"Mensaje del cliente: {mensaje}"
        ),
        tipo="otro" if origen == "orquestador" else "reserva",
    )
    _escalado_de[sesion] = incidencia.id
    contexto.datos["incidencia"] = incidencia.__dict__
    return incidencia.id


# Textos fijos del cierre. Tutean, como el resto de textos que escribe el codigo.
ESCALAMIENTO_HUMANO = ("Tu pedido para hablar con una persona del restaurante quedó registrado con "
                       "el código {codigo}. El equipo lo va a revisar.")
ESCALAMIENTO_HUMANO_FALLIDO = ("No pude registrar tu pedido. Puedes comunicarte con el restaurante "
                               f"al {TELEFONO_RESTAURANTE}.")
ESCALAMIENTO_RESERVA = ("Tu solicitud quedó registrada con el código {codigo}. La mesa todavía no está "
                        "confirmada. Puedes consultar el estado de tu caso al restaurante.")
ESCALAMIENTO_RESERVA_FALLIDO = ("No pude registrar el caso para el restaurante. No hay una mesa confirmada "
                                "por este escalamiento. Contacta directamente al local.")
OFERTA_DIFERIDO = "Si con esa información quieres continuar con {tema}, avísame y lo vemos."


def _nodo_cierre(estado: EstadoConversacion) -> dict:
    """
    Construye la respuesta final del recorrido del grafo y gestiona escalamiento.

    Orden: respuesta directa del planificador; pedido de hablar con una persona
    (el texto lo arma el escalamiento); sin respuestas, SIN_MENSAJE; con
    respuestas, el resumen del servidor si hay confirmacion_pendiente o la
    sintesis. Despues el escalamiento (texto y tipo segun su origen), la oferta del
    paso diferido y el aviso de lo que quedo sin atender.

    Devuelve respuesta, ruta (quien respondio, para metricas y UI), continuar_con
    (quien atiende el proximo mensaje: el componente diferido, si lo hay) y
    contexto. La ruta siempre es un componente real, nunca "orquestador": el
    respaldo ante un error del planificador la usa como nombre de nodo.
    Un codigo local no acredita entrega a Trello o notificacion al personal.
    La validacion de salida del canal se ejecuta despues, en _atender.
    """
    sesion = _sesion_de(estado)
    respuestas = estado.get("respuestas") or []
    contexto = estado.get("contexto") or ContextoConversacion(sesion_id=sesion, canal="studio")
    accion = estado.get("accion") or "delegar"
    diferido = estado.get("diferido") or {}

    ruta = respuestas[-1]["agente"] if respuestas else (estado.get("ultimo_agente") or "informacion")
    if ruta not in NODOS:
        ruta = "informacion"
    continuar_con = diferido["agente"] if diferido.get("agente") in NODOS else ruta

    pendiente = contexto.datos.get("confirmacion_pendiente")
    if accion == "responder_directo":
        texto = estado.get("respuesta_directa") or SIN_MENSAJE
    elif accion == "escalar_humano":
        texto = ""
    elif not respuestas:
        return {"respuesta": SIN_MENSAJE, "ruta": "informacion", "continuar_con": ruta, "contexto": contexto}
    elif pendiente:
        # El resumen autorizado lo escribe el servidor, nunca lo reescribe el LLM.
        otros = [r["texto"] for r in respuestas if r["agente"] != "reservas"]
        texto = " ".join(otros + [pendiente])
    else:
        texto = _sintetizar(respuestas, sesion)

    # Escalamiento: quien lo pidio (un agente o el planificador) levanto la mano;
    # el ticket lo abre el cierre, que es el unico que tiene el turno completo delante.
    escalamiento = contexto.datos.get("escalamiento")
    if contexto.escalado and escalamiento:
        del_orquestador = escalamiento.get("origen") == "orquestador"
        try:
            codigo = _escalar(sesion, escalamiento, _mensaje_de(estado), contexto)
        except Exception as error:
            registrar_error(sesion, "escalamiento", error)
            contexto.escalado = False
            texto = ESCALAMIENTO_HUMANO_FALLIDO if del_orquestador else ESCALAMIENTO_RESERVA_FALLIDO
            return {"respuesta": texto, "ruta": ruta, "continuar_con": continuar_con, "contexto": contexto}
        registrar("escalado", sesion, agente="orquestador" if del_orquestador else ruta,
                  detalle={"incidencia": codigo, **escalamiento})
        # Sustituye la promesa del modelo: el codigo real existe recien aqui.
        if del_orquestador:
            texto = ESCALAMIENTO_HUMANO.format(codigo=codigo)
            otros = [r["texto"] for r in respuestas]
        else:
            texto = ESCALAMIENTO_RESERVA.format(codigo=codigo)
            otros = [r["texto"] for r in respuestas if r["agente"] != "reservas"]
        if otros:
            texto = " ".join(otros + [texto])
        if pendiente:
            texto += " " + pendiente

    if diferido.get("agente") in NODOS:
        tema = TEMA_PENDIENTE.get(diferido["agente"], TEMA_PENDIENTE["otros"])
        texto = f"{texto} {OFERTA_DIFERIDO.format(tema=tema)}"

    pendientes = list(estado.get("pendientes") or [])
    if accion == "delegar":
        # Un paso que el control de estado no dejo ejecutar tambien se avisa: no se descarta en silencio.
        pendientes += [p for p in (estado.get("plan") or [])[len(respuestas):] if p not in pendientes]
    if pendientes:
        texto = f"{texto} {_aviso_pendientes(pendientes)}"

    return {"respuesta": texto.strip(), "ruta": ruta, "continuar_con": continuar_con, "contexto": contexto}


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
    _pendiente_de.clear()
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
        imagenes=list(entrante.imagenes),
    )
    estado_inicial: EstadoConversacion = {
        "sesion_id": entrante.sesion_id,
        "mensaje": entrante.texto,
        "historial": historial or [],
        "ultimo_agente": _ultimo_agente.get(entrante.sesion_id, ""),
        # La tarea ofrecida vive un solo turno: se consume aqui, se use o no.
        "tarea_ofrecida": _pendiente_de.pop(entrante.sesion_id, None) or {},
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
        elif (_es_cancelar_solicitud(entrante.texto)
              and (cancelacion := _cancelar_solicitud(entrante.sesion_id)) is not None):
            # Como CONFIRMO: un comando exacto que el codigo resuelve sin modelo.
            final = {"respuesta": cancelacion, "ruta": "reservas",
                     "motivo_ruta": "solicitud al staff retirada por el cliente", "plan": ["reservas"]}
            registrar("plan", entrante.sesion_id, agente="reservas",
                      detalle={"plan": ["reservas"], "motivo": final["motivo_ruta"]})
        else:
            # Un nuevo pedido invalida el resumen anterior; no se confirma algo
            # que quedo atras en la conversacion. Las tools pueden proponer otro.
            autorizacion.descartar(entrante.sesion_id)
            with contexto_de_trazado():
                final = obtener_grafo().invoke(estado_inicial)
            if contexto.datos.get("hilo_en_revision"):
                # El hilo seguia esperando al staff. Si esa espera ya no tiene sentido
                # (solicitud vencida o perdida de la cola), se libera en vez de atrapar al cliente.
                liberada = _liberar_pausa_sin_vigencia(entrante.sesion_id)
                if liberada:
                    contexto.datos.pop("hilo_en_revision", None)
                    final = {**final, "respuesta": liberada}
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
    accion = final.get("accion") or "delegar"
    if not plan and accion != "delegar":
        # Una accion directa del orquestador queda registrada como tal, no como un turno de un agente.
        plan = [f"orquestador:{accion}"]
    diferido = final.get("diferido") or {}
    if diferido.get("agente"):
        _pendiente_de[entrante.sesion_id] = diferido
    revision = contexto.datos.get("revision_humana")
    if revision and revision.get("estado") == "pendiente":
        _cargar_revisiones()
        _revisiones[entrante.sesion_id] = {
            "sesion_id": entrante.sesion_id,
            "contexto": contexto,
            "solicitud": revision.get("solicitud", {}),
            "canal": entrante.canal,
            "creada": time.time(),
        }
        _guardar_revisiones()
    # Continuidad: quien atiende el proximo mensaje. Con un paso ofrecido es ese
    # componente, aunque este turno haya respondido otro.
    _ultimo_agente[entrante.sesion_id] = final.get("continuar_con") or final["ruta"]
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
    es otra conversacion, y su escalamiento merece su propio ticket. Y se libera
    la pausa del hilo de reservas: si solo se sacara la solicitud de la cola, el
    hilo quedaria esperando una decision que el staff ya no puede tomar. Una
    revision que el staff esta resolviendo en este momento no se toca.
    """
    from ..agentes import reservas

    _ultimo_agente.pop(sesion_id, None)
    _escalado_de.pop(sesion_id, None)
    _pendiente_de.pop(sesion_id, None)
    with _lock_revisiones:
        _cargar_revisiones()
        if sesion_id not in _resolviendo:
            retirada = _revisiones.pop(sesion_id, None)
            reservas.liberar_pausa(sesion_id)
        else:
            retirada = None
    if retirada is not None:
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
        if pendiente is not None:
            # Mientras se reanuda, ni la cancelacion del cliente ni el vencimiento tocan el hilo.
            _resolviendo.add(sesion_id)
    if pendiente is None:
        raise KeyError("No existe una revisión pendiente para esa sesión")
    try:
        respuesta = _ejecutar_resolucion(sesion_id, decision, motivo, pendiente)
    except Exception:
        with _lock_revisiones:
            _revisiones[sesion_id] = pendiente
            _resolviendo.discard(sesion_id)
        raise
    with _lock_revisiones:
        _resolviendo.discard(sesion_id)
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
