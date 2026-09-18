# Clemente — asistente multiagente para restaurantes

> **Documentacion del codigo revisada el 2026-09-18.** Consulta la
> [guia de nodos, funciones, guardrails y limites reales](docs/GUIA_CODIGO.md)
> y el [indice de todas las definiciones Python](docs/INDICE_CODIGO.md).
> Estas referencias describen el codigo actual y prevalecen sobre las
> explicaciones historicas del flujo. Verifica cobertura y sintaxis con
> `python docs/verificar_documentacion.py`; esa auditoria no ejecuta pruebas funcionales.

## Índice

1. [Cómo funciona, en una página](#1-cómo-funciona-en-una-página)
   - [El orquestador y los dos agentes](#el-orquestador-y-los-dos-agentes)
   - [Cómo planifica el orquestador](#cómo-planifica-el-orquestador)
   - [Dos niveles de grafo y el patrón ReAct](#dos-niveles-de-grafo-y-el-patrón-react)
   - [Seguridad con Guardrails AI, PII y toxicidad](#seguridad-con-guardrails-ai-pii-y-toxicidad)
   - [Por qué LangGraph](#por-qué-langgraph-y-no-un-ifelif)
2. [Quién hace qué](#2-quién-hace-qué)
3. [Puesta en marcha](#3-puesta-en-marcha)
   - [3.1 Elección de modelo](#31-elección-de-modelo)
   - [3.2 Ver el grafo en LangGraph Studio](#32-ver-el-grafo-en-langgraph-studio)
   - [3.3 Todos los comandos](#33-todos-los-comandos-en-un-solo-lugar)
   - [3.4 Banco de modelos](#34-banco-de-modelos-cuánto-gasta-y-cuánto-tarda-cada-uno)
   - [Resultado medido](#resultado-medido-2026-09-08)
4. [API HTTP](#4-api-http)
5. [Qué ocurre con un mensaje, paso a paso](#5-qué-ocurre-con-un-mensaje-paso-a-paso)
6. [Contratos entre módulos](#6-contratos-entre-módulos)
7. [Datos y reglas de negocio](#7-datos-y-reglas-de-negocio)
8. [Tickets por MCP](#8-los-tickets-por-mcp-sesión-16)
   - [El camino completo de un reclamo](#el-camino-completo-de-un-reclamo)
   - [Por qué la vuelta de más](#por-qué-la-vuelta-de-más)
   - [Los dos transportes](#los-dos-transportes-y-por-qué-hacen-falta-los-dos)
   - [Los tres backends de incidencias](#los-tres-backends-de-incidencias)
   - [Comandos](#comandos)
   - [Cómo se ve el MCP](#cómo-se-ve-el-mcp)
   - [Lo que no se hizo](#lo-que-no-se-hizo-y-por-qué)
9. [Observabilidad](#9-observabilidad)
10. [Evaluación y seguridad](#10-evaluación-y-seguridad-módulo-8)
    - [10.1 El dataset](#101-el-dataset)
    - [10.2 Los cuatro corredores](#102-los-cuatro-corredores)
    - [10.3 El juez](#103-el-juez)
    - [10.4 Red teaming](#104-red-teaming)
11. [Estado y hallazgos](#11-estado-y-hallazgos)
    - [Prueba de extremo a extremo](#prueba-de-extremo-a-extremo-del-2026-09-03-modelo-local-llama32)
    - [Primera corrida de evaluación](#primera-corrida-de-evaluación-2026-09-07-claude-sonnet-5)
    - [Evaluación del evaluador](#el-evaluador-también-hay-que-evaluarlo)
    - [Segunda corrida](#segunda-corrida-los-hallazgos-que-sí-eran-del-agente)
    - [Estado medido al cierre](#estado-medido-al-cierre-del-2026-09-07)
    - [Primera medición de la arquitectura nueva](#primera-medición-de-la-arquitectura-nueva-2026-09-08-claude-sonnet-5)
    - [Defectos encontrados por la v1](#los-tres-defectos-que-encontró-la-v1-y-que-ninguna-prueba-de-contrato-veía)
    - [Giro de arquitectura](#el-giro-de-arquitectura-del-2026-09-07-asesoría-con-boris)
12. [Estructura del repositorio](#12-estructura-del-repositorio)
    - [12.1 Si buscas… está aquí](#121-si-buscas-está-aquí)
    - [12.2 El árbol completo](#122-el-árbol-completo)
13. [Documentos del proyecto](#13-documentos-del-proyecto)

> **Estado verificado — 2026-09-18.** Esta nota prevalece sobre las
> descripciones históricas de acceso y confirmación de este README.
> Validación actual: **193 pruebas aprobadas, sin fallos ni omisiones**, con Postgres aislado.
> Las cifras posteriores de 126 casos son históricas. Ver [cambios y validación del PR](docs/PR_GUARDRAILS.md).
> El informe de los pasos 1–3 es un antecedente histórico. Desde entonces se incorporaron
> `create_agent`, HIL persistente, Guardrails AI, PII, toxicidad y su representación en el webchat.
>
> Las tools de crear, modificar y cancelar ahora **preparan** una operación. El
> servidor muestra el resumen exacto y exige otro mensaje `CONFIRMO <código>`:
> permiso de un uso, ligado a la sesión, con vigencia de 10 minutos. La ejecución
> de esa confirmación no pasa por el modelo. Un mensaje distinto invalida la
> propuesta anterior; un cambio en la reserva exige un resumen nuevo.
>
> Las reservas se vinculan a la sesión que las creó. Saber un teléfono o código
> no permite recuperar reservas ajenas ni antiguas sin vínculo. La recuperación
> entre dispositivos necesita verificación por el restaurante; todavía no hay
> un flujo automatizado de recuperación de identidad.
>
> El webchat usa una cookie firmada: iniciar `/api/chat` sin `sesion_id` y
> conservar la cookie; usar después el identificador devuelto por el servidor.
> Las trazas, conversaciones y reinicios HTTP se limitan a esa sesión. El webhook
> de WhatsApp (`POST /api/webhook/whatsapp`) permanece deshabilitado salvo que
> se configure `CLEMENTE_DATABASE_URL`. La firma de Twilio es obligatoria: sin firma valida no se acepta la identidad ni se inicia procesamiento. El webhook comparte los guardrails del webchat.

Proyecto final del **Programa en Diseño e Implementación de Agentes IA** (UTEC Posgrado) — **Grupo 02**.
Implementa la evolución de la arquitectura declarada en el *Entregable 01*: **dos agentes
especializados** —Reservas e Incidencias— coordinados por un orquestador. El orquestador también
atiende las consultas de conocimiento mediante el RAG del catálogo. Todo se expone por un único
canal conversacional.

**Alcance cerrado del entregable:** dos agentes especializados (Reservas y Capacidad;
Incidencias y Experiencia) más las consultas de Conocimiento resueltas por el orquestador con
RAG. El flujo de pedidos, delivery y recojo del caso de estudio **queda fuera**. El canal previsto
es **WhatsApp vía Twilio**, con firma obligatoria y guardrails compartidos; el webchat incluido es
el canal actualmente disponible para desarrollar y demostrar el sistema.

---

## 1. Cómo funciona, en una página

Un servidor **Flask** recibe un mensaje, un **orquestador LangGraph** arma un plan de
resolución, ejecuta los pasos de ese plan —él mismo si es una consulta de información, o uno de
los dos agentes especializados si hay que tocar algo— y devuelve **una sola respuesta** por el
mismo canal. Todo el camino queda trazado.

> **Cambio de arquitectura del 2026-09-07.** Hasta esa fecha esto era un *router* de tres
> agentes. Tras la asesoría con Boris (registrada en el documento externo
> `ASESORIA_01_BORIS_ACUERDOS.md`)
> el enrutador pasó a orquestador con plan de resolución, el Agente de Conocimiento se eliminó
> y su alcance subió al orquestador, y los tickets de incidencias pasaron a Trello. Cada
> decisión de este README que cambió por eso está marcada con la cita y el minuto del video.

```mermaid
flowchart LR
    cliente(["Cliente del restaurante"])

    subgraph canal["CANAL REAL"]
        twilio["Twilio<br/>WhatsApp Business API"]
    end

    subgraph herramienta["HERRAMIENTA INTERNA - no es canal de produccion"]
        webchat["Webchat de desarrollo y demo<br/>GET /"]
    end

    subgraph comunicacion["COMUNICACION"]
        webhook["POST /api/webhook/whatsapp<br/>normaliza el payload de Twilio"]
        chatapi["POST /api/chat"]
        sesiones["Sesiones<br/>historial por sesion_id"]
    end

    subgraph orquestacion["ORQUESTADOR"]
        plan{"Planificador<br/>arma el plan de resolucion"}
        proxy["Responde el mismo<br/>informacion del restaurante"]
        cierre["Cierre<br/>punto UNICO de salida"]
    end

    subgraph agentes["AGENTES ESPECIALIZADOS"]
        reservas["Reservas y Capacidad"]
        incidencias["Incidencias y Experiencia<br/>customer care"]
    end

    subgraph servicios["SERVICIOS Y DATOS"]
        gestor[("Gestor de reservas<br/>mesas, turnos, disponibilidad")]
        registro[("Registro de incidencias")]
        trello["Trello via MCP<br/>persistencia, seguimiento, notificacion"]
        chroma[("Catalogo del restaurante<br/>indice Chroma")]
    end

    obs["OBSERVABILIDAD<br/>LangSmith + trazas propias + metricas"]

    cliente -->|"mensaje de WhatsApp"| twilio
    twilio --> webhook
    webchat --> chatapi
    webhook --> sesiones
    chatapi --> sesiones
    sesiones -->|"MensajeEntrante"| plan

    plan -->|"paso: informacion"| proxy
    plan -->|"paso: reservas"| reservas
    plan -->|"paso: incidencias"| incidencias

    proxy --> cierre
    reservas -->|"listo, o levanta la mano"| cierre
    incidencias --> cierre
    cierre -.->|"queda un paso del plan"| reservas

    proxy -->|"buscar_en_catalogo"| chroma
    reservas -->|"tools"| gestor
    incidencias -->|"registrar_incidencia"| registro
    incidencias -->|"verificar reserva"| gestor
    cierre -->|"abre el ticket del escalamiento"| registro
    registro --> trello
    reservas -.->|"consultar_politica"| chroma
    incidencias -.->|"consultar_politica"| chroma

    cierre -->|"UNA RespuestaClemente"| sesiones
    sesiones -->|"respuesta al cliente"| twilio

    plan -.->|"traza del plan"| obs
    agentes -.->|"latencia, errores"| obs
    cierre -.->|"escalamientos"| obs

    classDef jesus fill:#dbeafe,stroke:#2563eb,stroke-width:2px,color:#0f172a
    classDef cj fill:#dcfce7,stroke:#16a34a,stroke-width:2px,color:#0f172a
    classDef miguel fill:#fef3c7,stroke:#d97706,stroke-width:2px,color:#0f172a
    classDef adrian fill:#f3e8ff,stroke:#9333ea,stroke-width:2px,color:#0f172a
    classDef comun fill:#e2e8f0,stroke:#64748b,stroke-width:1px,color:#0f172a

    class twilio,webhook,chatapi,sesiones jesus
    class plan,proxy,cierre,reservas,incidencias,chroma cj
    class gestor miguel
    class obs adrian
    class webchat,registro,trello,cliente comun
```

**Colores = responsable.** Azul: Jesús (canal WhatsApp con Twilio, comunicación y sesiones).
Verde: Christian y Jean (orquestador, los dos agentes y el RAG). Ámbar: Miguel (gestor de
reservas). Morado: Adrián (observabilidad). Gris: piezas comunes del proyecto — entre ellas el
**webchat, que es una herramienta interna de desarrollo y demostración: no pasa por Twilio ni
forma parte del canal de producción**.

**Topología: *Supervisor*** (Sesión 15). Un solo punto decide quién actúa y un solo punto
responde; los agentes no se hablan entre sí ni escalan por su cuenta. Eso da un único lugar
donde auditar por qué se eligió cada agente, y hace que agregar un tercer agente sea un módulo
más, no un rediseño.

### El orquestador y los dos agentes

El orquestador **no es un cuarto agente**: no tiene alcance de negocio propio, no puede escribir
nada y no aparece en el registro `AGENTES`. Tiene tres trabajos.

| Trabajo | Qué hace | Dónde vive |
|---|---|---|
| **Planificar** | convierte el mensaje en una lista ordenada de pasos (casi siempre uno, como máximo dos) | `_nodo_planificador` |
| **Responder** | contesta él mismo las preguntas de información del restaurante — *proxy*, en palabras de Boris | `orquestador/informacion.py` |
| **Cerrar** | junta las respuestas en una sola, abre el ticket si alguien escaló, y deja la traza | `_nodo_cierre` |

Los dos agentes especializados se diferencian por **alcance y costo de equivocarse**, no por
tecnología: los dos se construyen igual (`create_agent` de LangChain) y solo cambian su *prompt*
de sistema y su caja de *tools*.

| Quién | Atiende | Tools | Límite duro (guardrail) |
|---|---|---|---|
| **Orquestador** (proxy) | horarios, ubicación, carta, servicios, políticas | `buscar_en_catalogo`, `consultar_politica` | las dos son de **lectura**: aunque el *prompt* falle, no tiene con qué reservar, cobrar ni cerrar un reclamo; no afirma ni niega cupo para una fecha |
| **Reservas y Capacidad** | disponibilidad, reservar, modificar, cancelar | `consultar_disponibilidad`, `crear_reserva`, `buscar_mis_reservas`, `consultar_reserva_por_codigo`, `modificar_reserva`, `cancelar_reserva`, `escalar_a_staff`, `consultar_politica` | no afirma disponibilidad sin consultarla; no registra sin confirmación explícita; grupos de más de 10 personas escalan al *staff*; **`escalar_a_staff` ya no abre el ticket**, solo levanta la mano |
| **Incidencias y Experiencia** (*customer care*) | lo que ya salió mal | `registrar_incidencia`, `consultar_incidencia`, `verificar_reserva_del_reclamo`, `consultar_politica` | **no existe** tool para cerrar una incidencia ni para dar compensaciones: no puede hacerlo aunque el *prompt* falle |

**Por qué desapareció el Agente de Conocimiento.** Boris, asesoría del 2026-09-07 **[07:27]**:
*"la verdad es un RAG muy ligero. Es algo que hasta se lo podrías poner en el system prompt a
cualquier agente"*. Y sobre dónde ponerlo, **[10:19]**: *"en el router, para que no esté
duplicado"*. El catálogo son tres documentos cortos: no sostenía un agente con su propia
*profile card*, su propio nivel de autonomía y su propio nivel de criticidad. **El RAG no
desapareció: cambió de dueño.**

### Cómo planifica el orquestador

```mermaid
flowchart TD
    msg["Ultimo mensaje del cliente"] --> q0{"Continua el hilo:<br/>un dato suelto, un si o un no,<br/>responde lo que Clemente pregunto"}
    q0 -->|"si"| mismo["UN paso:<br/>el mismo que venia atendiendo"]
    q0 -->|"no"| q1{"Menciona algo que YA salio mal:<br/>espera, error, molestia, reclamo previo"}
    q1 -->|"si"| q1b{"Ademas pide una mesa"}
    q1b -->|"si"| dos["DOS pasos:<br/>incidencias, despues reservas"]
    q1b -->|"no"| inc["Incidencias y Experiencia"]
    q1 -->|"no"| q2{"Pide, cambia o cancela una mesa"}
    q2 -->|"si"| res["Reservas y Capacidad"]
    q2 -->|"no"| info["Informacion: responde el orquestador"]

    err["Error del planificador"] -.->|"fallback: el agente del hilo,<br/>o informacion"| info

    classDef agente fill:#dcfce7,stroke:#16a34a,stroke-width:2px,color:#0f172a
    classDef pregunta fill:#f1f5f9,stroke:#64748b,color:#0f172a
    classDef fallo fill:#fee2e2,stroke:#dc2626,color:#0f172a
    class inc,res,info,dos,mismo agente
    class msg,q0,q1,q1b,q2 pregunta
    class err fallo
```

Lo que ya salió mal se atiende **antes** que lo que viene: un reclamo con una reserva dentro
sigue siendo, primero, un reclamo. Pero desde el cambio a orquestador **la reserva ya no se
pierde** — es el segundo paso del plan, no un pedido descartado. El *fallback* es `informacion`
porque es lo más barato de equivocarse: nunca compromete capacidad del local.

**El tope de dos pasos es deliberado.** Es el caso que describió Boris **[11:12]** (*"en qué
momento llamar al de customer care y luego al de reservas"*) y es también el límite de lo que un
cliente puede seguir en un solo mensaje de chat. Un plan más largo casi siempre significa que el
modelo entendió de más, no que el cliente pidió más. Lo garantiza `_limpiar_plan()` en código,
no el *prompt*.

**RAG** (*Retrieval-Augmented Generation*, generación aumentada por recuperación): el catálogo
del restaurante vive en `app/agentes/rag/documentos/` y se indexa en **Chroma**. Es la **fuente
única de verdad**: Reservas e Incidencias consultan las políticas ahí con `consultar_politica`
en lugar de llevar su propia copia en el *prompt*.

### Dos niveles de grafo, y el patrón ReAct

El proyecto tiene un grafo **dentro** de otro, y conviene no confundirlos:

| Nivel | Quién lo construye | Forma | Qué resuelve |
|---|---|---|---|
| **Orquestación** | nuestro `StateGraph` en `app/orquestador/grafo.py` | `START → planificador → [pasos]* → cierre → END` | qué hay que hacer con este mensaje, en qué orden, y con qué única respuesta se contesta |
| **Razonamiento de cada agente** | `create_agent` de LangChain, por dentro | **cíclica**: `model ⇄ tools` | cuántas herramientas hace falta llamar antes de poder responder |

Ese segundo nivel **es** el patrón **ReAct** (*Reasoning and Acting*, razonar y actuar): el modelo
piensa, llama una herramienta, **observa** el resultado y vuelve a pensar con esa observación
encima, hasta que puede responder. El ciclo no se escribe en el *prompt* — lo compila
`create_agent`. Lo que sí está en los *prompts* es la **disciplina** de ReAct, la regla de no
afirmar nada que no venga de una observación:

| Agente | Línea del *prompt* | Qué impone |
|---|---|---|
| Reservas | «nunca afirmas ni niegas disponibilidad sin haber llamado antes a `consultar_disponibilidad`» | prohíbe responder sin observación previa |
| Reservas | «las políticas las consultas con `consultar_politica`, no las citas de memoria» | fuerza la herramienta sobre el conocimiento del modelo |
| Orquestador (proxy) | «responde solo con lo que encontraste ahí» | ancla la respuesta al catálogo |
| Incidencias | registra con `registrar_incidencia` y **recién entonces** da el código | prohíbe inventar el código antes de tenerlo |

Lo que **a propósito no** está es el formato literal `Thought: / Action: / Observation:` del
artículo original de ReAct (2022). Ese andamiaje de texto existía porque los modelos de entonces
no tenían interfaz de llamada a herramientas: había que simular el ciclo escribiéndolo. Con
modelos que sí la tienen, pedirlo en el *prompt* empuja al modelo a **escribir** la llamada en vez
de **invocarla** — exactamente la falla que se documentó con `llama3.2` (sección 11) y la razón de
que exista el guardrail de salida en `app/agentes/base.py`.

### Seguridad con Guardrails AI, PII y toxicidad

El proyecto conserva todos sus controles deterministas y añade el framework que se trabajó en
la sesión 24 como defensa en profundidad. Antes del orquestador,
`app/seguridad/guardrails_ai.py` envía el mensaje al servicio aislado
`guardrails_service/`, que ejecuta `Guard().use(DetectJailbreak(...))`. Una detección positiva
termina el turno sin llamar al planificador, al modelo ni a ninguna tool. El resultado queda en
trazas como `guardrail_input`.

**Estado exacto de los guardrails implementados:**

| Guardrail | Tipo | Estado | Qué impide o controla |
|---|---|---|---|
| `DetectJailbreak` | Guardrails AI | **Implementado** | Bloquea intentos de jailbreak antes del orquestador, el LLM y las tools; también se evalúa con casos de prompt injection |
| `ToxicLanguage` + reglas en español | Guardrails AI + propio | **Implementado** | Bloquea amenazas, acoso grave y discriminación en entrada y salida; permite reclamos duros sin amenazas |
| `PIIMiddleware` | LangChain | **Implementado** | Redacta correos y tarjetas en entradas, salidas y resultados de tools |
| PII y secretos en el canal | Propio, determinista | **Implementado** | Bloquea tarjetas, API keys y credenciales; redacta correo, DNI, IP, MAC y teléfono en respuestas y trazas |
| Autorización por sesión | Propio, determinista | **Se conserva** | Impide consultar, modificar o cancelar reservas de otra sesión aunque se conozca el teléfono o código |
| Confirmación `CONFIRMO <código>` | Propio, determinista | **Se conserva** | Ninguna creación, modificación o cancelación se ejecuta directamente desde una respuesta del modelo |
| `HumanInTheLoopMiddleware` | LangChain | **Implementado** | Pausa solicitudes de más de 10 personas hasta que el *staff* las apruebe o rechace |
| Restricción de tools por agente | Propio, determinista | **Se conserva** | El orquestador no puede reservar y el agente de incidencias no puede cerrar casos ni conceder compensaciones |
| Disponibilidad y políticas con evidencia | Propio | **Se conserva** | Obliga a consultar las tools o el RAG antes de afirmar disponibilidad o citar una política |
| Detección de tools escritas como texto | Propio, salida | **Se conserva** | Descarta respuestas donde el modelo imprime una supuesta llamada en vez de ejecutar la tool |
| Cierre con evidencia del orquestador | Propio, salida | **Se conserva** | Evita anunciar reservas, tickets o escalamientos que no aparecen en el resultado real de las herramientas |
| Límite del plan | Propio, determinista | **Se conserva** | Elimina pasos repetidos y limita cada turno a dos pasos de agentes |

El teléfono y el nombre se permiten dentro del flujo autorizado porque son necesarios para una
reserva; no se muestran completos en respuestas ni trazas. El detector dedicado de *prompt
injection* continúa pendiente por la incompatibilidad de `rebuff` con Python 3.13.

Guardrails AI corre en un entorno separado porque `DetectJailbreak` instala una pila de
Hugging Face, Click y OpenTelemetry incompatible con DeepEval y la observabilidad del proceso
principal. El aislamiento también evita cargar varios modelos de clasificación dentro de cada
worker de Clemente. En Windows, el entorno y la caché usan rutas cortas para no superar el
límite de longitud de PyTorch. Las instrucciones reproducibles están en
`guardrails_service/README.md`.

La política de operación es explícita:

| Situación | Acción |
|---|---|
| El validador permite la entrada | Se usa `validated_output`, no el texto original |
| Detecta jailbreak o inyección | Se bloquea antes del LLM y se registra el motivo |
| Servicio caído o timeout | Se registra `guardrail_error` y continúa con los controles deterministas existentes |
| `CLEMENTE_GUARDRAILS_URL` vacío | Servicio externo deshabilitado; continúan activos los controles deterministas y `PIIMiddleware` |

El paquete `guardrails-ai-detect-prompt-injection` usado en el material no se instala: su
dependencia `rebuff>=0.1.1` no ofrece una distribución compatible con Python 3.13. La implementación
usa `DetectJailbreak` y mide también casos de inyección. No se baja la versión de Python exigida
por el curso ni se presenta el clasificador como una garantía absoluta.

### Por qué LangGraph y no un `if/elif`

Hasta el 2026-09-07 esta sección decía, con razón, que un `if/elif` daba el mismo
comportamiento: había una sola decisión y un solo agente por turno. **Con el orquestador ya no
es así**, y la diferencia se ve en el código:

- El destino de cada nodo **se decide en ejecución**, mirando el estado (`_siguiente` lee `plan`
  y `paso`), no en una cadena de `if` escrita de antemano.
- Un turno puede recorrer **dos nodos de trabajo** y volver a converger en uno solo de salida.
  Con `if/elif` habría que llevar a mano el índice del plan, acumular las respuestas y decidir
  el cierre: es reimplementar `StateGraph` peor.

A eso se suman las razones que ya valían antes:

1. **Ya está en el proyecto.** `create_agent` devuelve un grafo LangGraph compilado. La decisión
   no es "usar LangGraph o no", sino si el nivel de arriba también lo es.
2. **Cada nodo es un tramo propio en la traza.** En LangSmith se ven *planificador*, cada paso y
   *cierre* como tramos separados, con su tiempo y sus tokens, sin instrumentar nada a mano.
3. **Es inspeccionable en vivo** desde LangGraph Studio (sección 3.2), que es también cómo se
   sustenta la arquitectura en la presentación final.
4. **Agregar un tercer agente** es un nodo más y una entrada en `NODOS`: no se reescribe el
   despacho.
5. **Pausa decisiones sensibles.** El agente de reservas usa
   `HumanInTheLoopMiddleware`, un checkpointer SQLite e `interrupt()` para que el *staff*
   apruebe o rechace excepciones de capacidad antes de ejecutar la tool.

Para ser exactos sobre lo que **no** se está usando: no hay ejecución en paralelo de varios
agentes (los pasos del plan corren en secuencia). El checkpointer está acotado al agente de
reservas y a su revisión humana; la topología
sigue siendo la de **supervisor** de la Sesión 15.

## 2. Quién hace qué

| Frente | Responsable | Carpeta |
|---|---|---|
| Comunicación y conexión con WhatsApp (Twilio) | **Jesús** | `app/communication/` |
| Orquestador + los 2 agentes + RAG | **Christian, Jean** | `app/orquestador/`, `app/agentes/` |
| Gestor de reservas | **Miguel** | `app/reservas/` |
| Observabilidad | **Adrián** | `app/observabilidad/` |
| Registro de incidencias | Christian, Jean (provisional) | `app/incidencias/` |

**Archivos compartidos** — no se editan en solitario: `app/contratos.py`, `app/config.py`,
`app/llm.py`, `app/__init__.py`, `requirements.txt`, `.env.example`.

Reglas de trabajo, ramas y decisiones abiertas: [`ACUERDOS_EQUIPO.md`](ACUERDOS_EQUIPO.md).

## 3. Puesta en marcha

**Requisitos**

- **Python 3.13 o superior**, conforme a la configuración indicada en el curso. Para este
  proyecto se recomienda `>=3.13,<3.14` porque `chromadb` aún no publica *wheels* para 3.14.
- **Una clave de API**: `ANTHROPIC_API_KEY` u `OPENAI_API_KEY`. El razonamiento del agente corre
  sobre API — decisión del equipo, tomada tras medir que el modelo local inventaba datos
  (sección 11).
- **Ollama** solo para los *embeddings* del RAG, que siguen siendo locales y gratuitos:
  `ollama pull bge-m3`. Alternativa sin Ollama: `EMBEDDINGS_BACKEND=openai`.
- **Clave de LangSmith** (`LANGSMITH_API_KEY`) para la observabilidad compartida.

**Entorno validado — 10 de septiembre de 2026**

| Componente | Versión comprobada |
|---|---|
| Python | `3.13.5` |
| LangChain | `1.4.0` |
| LangGraph | `1.2.11` |
| LangChain Core | `1.6.1` |
| ChromaDB | `1.5.9` |

Los agentes usan la API vigente `langchain.agents.create_agent`; no utilizan el *pipelining*
antiguo. La suite local completa terminó con **126 casos aprobados, recopilados a partir de 113
funciones `test_*`** en este entorno. Las
versiones de la tabla describen el entorno efectivamente probado; `requirements.txt` conserva
rangos abiertos y por sí solo no reproduce necesariamente estas mismas versiones.

**Instalación**

```bash
cd clemente
python -m venv .venv
.venv\Scripts\activate            # Windows;  mac/linux: source .venv/bin/activate
pip install -r requirements.txt
copy .env.example .env            # mac/linux: cp .env.example .env
```

**Configuración mínima del `.env`**

```ini
AGENT_MODEL=openai                # Clemente responde con OpenAI
OPENAI_API_KEY=...
OPENAI_MODEL=gpt-5.6-terra
ANTHROPIC_API_KEY=...
ANTHROPIC_MODEL=claude-sonnet-5
JUEZ_MODEL=claude-sonnet-5        # juez independiente de DeepEval/DeepTeam
LANGSMITH_TRACING=true
LANGSMITH_API_KEY=...
LANGSMITH_PROJECT=clemente-grupo02
CLEMENTE_HITL_TOKEN=...           # token exclusivo de las rutas internas del staff
```

`AGENT_MODEL` elige al proveedor que atiende al cliente. Las variables de
Anthropic permanecen en el ejemplo porque `claude-sonnet-5` actúa como juez en
las evaluaciones; no hacen que Clemente responda con Claude mientras
`AGENT_MODEL=openai`.

### 3.1 Elección de modelo

Precio por millón de tokens, entrada / salida. **Verificado el 2026-09-07** en
[platform.claude.com/docs/en/about-claude/pricing](https://platform.claude.com/docs/en/about-claude/pricing)
y [developers.openai.com/api/docs/pricing](https://developers.openai.com/api/docs/pricing);
la misma tabla vive en código, en `PRECIOS_POR_MILLON` de `app/llm.py`.

| `AGENT_MODEL` | Modelo | Precio | Para qué |
|---|---|---|---|
| `openai` | `gpt-5.6-terra` | $2 / $12 | **el predeterminado del proyecto desde el 2026-09-08** — ver más abajo |
| `claude` | `claude-sonnet-5` | $2 / $10 | default anterior; empatado en calidad, 54% más caro (banco, sección 3.4) |
| `claude` | `claude-opus-5` | $5 / $25 | corrida final del informe y demostración |
| `claude` | `claude-haiku-4-5` | $1 / $5 | evaluaciones en lote; candidato para el planificador |
| `openai` | `gpt-6-astra` | $10 / $50 | el techo de OpenAI, y **el más caro de toda la tabla** — no usable con *tools*, ver sección 3.4 |
| `openai` | `gpt-5.6-sol` | $4 / $20 | equivalente de gama alta a Opus 5 |
| `openai` | `gpt-5.6-luna` | $0.20 / $1.20 | **el más barato con diferencia**; candidato al planificador |
| `llama3.2` | Ollama local | gratis | trabajar sin conexión o sin gastar crédito |

Los IDs de Claude van **sin sufijo de fecha** (`claude-sonnet-5`, no `claude-sonnet-5-2025…`).
Los de OpenAI tampoco llevan sufijo: es `gpt-6-astra`, no `gpt-6-astra-max` — lo que se llama
*max* es el nivel de razonamiento, un parámetro, no parte del identificador. Cambiar de proveedor
o de modelo es una línea del `.env`: no se toca el código de ningún agente.

**El precio de lista no decide nada por sí solo.** Los modelos Claude 4.7 en adelante usan un
tokenizador que produce alrededor de **30% más tokens para el mismo texto** (lo documenta la
propia página de precios de Anthropic). Comparar $/MTok entre casas sin medir los tokens reales
de cada una lleva a una conclusión equivocada. Por eso existe el banco de la sección 3.4, que
mide en vez de calcular.

**Capacidad contra precio, según un tercero.** Consultado el 2026-09-08 en
[Artificial Analysis](https://artificialanalysis.ai/models), que mide todos los modelos con la
misma batería y publica el resultado. El **índice** es su medida agregada de capacidad; el
**mezclado** es el costo por millón de tokens ponderando caché, entrada y salida en proporción
$0{,}7 : 0{,}2 : 0{,}1$.

| Modelo | Índice | tok/s | Mezclado | Ficha |
|---|---|---|---|---|
| `gpt-6-astra` | **53** | 62.5 | $7.70 | [ver](https://artificialanalysis.ai/models/gpt-6-astra) |
| `claude-opus-5` | 51 | 51.9 | $3.85 ᶜ | [ver](https://artificialanalysis.ai/models/claude-opus-5) |
| `gpt-5.6-sol` | 47 | 74.0 | $3.08 | [ver](https://artificialanalysis.ai/models/gpt-5-6-sol) |
| `gpt-5.6-terra` | 42 | 115.5 | $1.74 ᶜ | [ver](https://artificialanalysis.ai/models/gpt-5-6-terra) |
| `claude-sonnet-5` | 38 | 79.6 | $1.54 | [ver](https://artificialanalysis.ai/models/claude-sonnet-5) |
| `gpt-5.6-luna` | 38 | **121.5** | **$0.17** ᶜ | [ver](https://artificialanalysis.ai/models/gpt-5-6-luna) |
| `claude-haiku-4-5` | 15 | 80.6 | $0.77 | [ver](https://artificialanalysis.ai/models/claude-4-5-haiku) |

ᶜ El mezclado de estos tres no lo publica la página; se calculó con su misma fórmula, verificada
antes contra los cuatro valores que sí publica (dan exacto).

**Falta a propósito la columna de latencia.** La página mide 322 s en Astra, 183 s en Sonnet 5 y
0.79 s en Haiku 4.5, pero esos números salen de presets distintos —los primeros con razonamiento
al máximo, el último sin razonamiento— así que **no son comparables entre sí** y no predicen lo
que va a tardar Clemente con sus propios *prompts*. La latencia que importa es la del banco.

Tres lecturas que salen de esta tabla:

1. **`gpt-6-astra` no se justifica aquí.** Dos puntos de índice sobre Opus 5, al doble de precio.
   Para clasificar en un plan y redactar tres frases, no hay nada que compre esa diferencia.
2. **`gpt-5.6-luna` es el candidato para el planificador**: mismo índice que Sonnet 5, el más
   rápido de la tabla, y **nueve veces más barato** en mezclado. El planificador corre en cada
   turno, no usa herramientas y solo devuelve etiquetas: es exactamente donde eso vale.
3. **`gpt-5.6-terra` es el candidato para los agentes**: más índice que Sonnet 5 (42 contra 38) y
   más rápido (115 contra 80 tok/s) por un 12% más de costo mezclado.

**Cuidado con el índice.** Se mide con el razonamiento al máximo, así que un modelo barato que
razona mucho gasta pocos tokens *caros* pero **muchos tokens**. La tabla ordena candidatos; no
cierra la decisión. Eso lo hace el banco de la sección 3.4, corriendo nuestro dataset.

**Por qué Opus no es el predeterminado.** Lo que este sistema le pide al modelo es planificar en
uno o dos pasos, elegir la herramienta correcta y redactar tres frases con lo que la herramienta
devolvió. No hay razonamiento largo de varios pasos, que es donde Opus se separa: los límites
duros de Clemente son estructurales —qué *tools* existen y cuáles no— y no dependen de la
capacidad del modelo. Opus queda para la corrida final, donde el costo es una sola vez y conviene
el techo más alto.

**Por qué `gpt-5.6-terra` y no `claude-sonnet-5` como predeterminado (cambio del 2026-09-08).**
El banco de la sección 3.4, corriendo el dataset completo contra los dos:

| | Ruteo | Plan completo | Formato | Costo | Mediana | Peor turno |
|---|---|---|---|---|---|---|
| `gpt-5.6-terra` | 17/17 | 2/2 | limpio | **$0.1181** | **4.4s** | **8.39s** |
| `claude-sonnet-5` | 17/17 | 2/2 | limpio | $0.2552 | 5.02s | 12.43s |

**Empatados en cada métrica de calidad, y `gpt-5.6-terra` sale 54% más barato**, con mediana y
peor caso más rápidos. En este proyecto, para este trabajo concreto, no hay nada que la diferencia
de precio esté comprando. El cambio quedó en el `.env` (`AGENT_MODEL=openai`,
`OPENAI_MODEL=gpt-5.6-terra`); volver a Anthropic sigue siendo una línea.

Dos advertencias antes de repetir esta conclusión en el informe:

1. **Requirió un arreglo real, no solo medir.** Los cuatro modelos de OpenAI fallaban 0/17 al
   primer intento: la API rechaza combinar herramientas de función con razonamiento extendido en
   `/v1/chat/completions`. `app/llm.py` ahora construye estos modelos con `reasoning_effort="none"`
   — el costo es que dejan de razonar en varios pasos antes de responder, que es justamente lo que
   este trabajo no necesita (ver el párrafo de arriba). El detalle completo, reproducido con la API
   real, está en la bitácora.
2. **`gpt-6-astra` no entra en esta comparación.** Con reintentos confirmados (`none`, `low`),
   la propia API se contradice: exige razonamiento activo y no lo deja apagar, pero con
   razonamiento activo rechaza las herramientas de función en este endpoint. No es un parámetro
   que falte, es un límite real de `/v1/chat/completions` para este modelo; la única salida sería
   `/v1/responses`, fuera del alcance de esta corrección.

**Un modelo distinto para el planificador.** El planificador corre en **cada turno**, no usa
herramientas y su salida es una lista de etiquetas con `with_structured_output`. Es el candidato
natural a un modelo más barato, y por eso `resolver_modelo(rol="enrutador")` lee una variable
propia, en las dos casas:

```ini
ANTHROPIC_MODEL=claude-sonnet-5
ANTHROPIC_MODEL_ENRUTADOR=claude-haiku-4-5   # vacío = el mismo de arriba
# o, con OpenAI:
OPENAI_MODEL=gpt-5.6-terra
OPENAI_MODEL_ENRUTADOR=gpt-5.6-luna
```

No se activa por defecto **a propósito**: el ruteo es la pieza que ya falló una vez (sección 11)
y abaratarla sin medir sería cambiar costo por precisión a ciegas. La forma de decidirlo es el
banco de la sección 3.4.

**Sobre `temperature`:** los modelos Claude 4.6 en adelante —Opus 5 y Sonnet 5 incluidos—
eliminaron los parámetros de muestreo, y enviar `temperature` devuelve un error 400. Los modelos
de razonamiento de OpenAI (GPT-5 en adelante, GPT-6, serie *o*) tienen la misma restricción.
`app/llm.py` solo lo manda a los modelos que aún lo aceptan, en las dos casas.

**Ejecución y verificación**

```bash
python -m app.reservas.seed          # solo si usas CLEMENTE_BACKEND_RESERVAS=postgres
python run.py                     # http://localhost:5000
curl http://localhost:5000/api/salud
pytest -q                         # 126 casos (113 funciones), no llaman al modelo
```

`GET /api/salud` responde `{"estado": "sin_credencial", "falta": "ANTHROPIC_API_KEY"}` si el
`.env` está incompleto — arrancar sin clave es visible, no un misterio. Sin clave el chat no se
cae: responde con un mensaje de escalamiento y `escalado: true`.

El índice del RAG se construye solo en la primera consulta de información. Tras
editar los documentos del catálogo, o tras cambiar `EMBEDDINGS_BACKEND`:

```bash
python -m app.agentes.rag.indice --reindexar
```

### 3.2 Ver el grafo en LangGraph Studio

**LangGraph Studio** es el inspector visual del grafo: lo dibuja, resalta el camino que tomó cada
mensaje y deja abrir cada nodo para ver sus entradas y salidas. **No lee las trazas de LangSmith**
— se conecta a un servidor LangGraph corriendo y le pregunta qué grafos expone. Por eso el
proyecto, además de ser una aplicación Flask, se declara como aplicación LangGraph:

| Archivo | Papel |
|---|---|
| `langgraph.json` | manifiesto: declara el grafo `clemente` y de dónde leer el `.env` |
| `studio.py` | expone el grafo ya compilado. Es **el mismo** que atiende el webchat, no una copia hecha para la demostración |
| `pyproject.toml` | metadatos mínimos; el CLI los necesita para aceptar la carpeta como dependencia local |
| `requirements-dev.txt` | `langgraph-cli[inmem]`, separado para no cambiarle las dependencias de producción al resto del equipo |

```bash
pip install -r requirements-dev.txt
langgraph dev
```

El comando imprime la dirección de Studio; se abre en el navegador y muestra el grafo real:

```
🎨 Studio UI: https://smith.langchain.com/studio/?baseUrl=http://127.0.0.1:2024
```

Notas de uso:

- **Ver el grafo no cuesta; darle *Submit* sí** — Studio ejecuta el grafo de verdad contra la API.
- Todos los campos del estado son opcionales: basta escribir `Mensaje`. Los nodos completan
  `sesion_id`, `historial` y el contexto (`EstadoConversacion` es un `TypedDict` con
  `total=False` justamente para esto).
- Es un servidor aparte del de Flask, en el puerto 2024; pueden convivir los dos.
- Requiere `LANGSMITH_API_KEY` en el `.env`, y navegador basado en Chromium. En Safari hace falta
  `langgraph dev --tunnel`.

Para el informe y las diapositivas, el mismo grafo se exporta sin levantar nada:

```bash
python -m app.orquestador.grafo          # texto Mermaid, para pegar en un .md
python -m app.orquestador.grafo --png    # imagen; sin red cae a .mmd
```

Se genera **del grafo compilado**, no de un dibujo a mano: si alguien agrega un nodo y no
actualiza la documentación, la diferencia se nota.

### 3.3 Todos los comandos, en un solo lugar

Referencia rápida. Todos se ejecutan **desde `clemente/`**, y se usa el Python del entorno por
ruta completa para no depender de haber activado el `.venv` (en PowerShell, `Activate.ps1` suele
chocar con la política de ejecución):

```powershell
cd D:\...\Proyecto_Final\Entregable_Final\clemente
```

**Instalación**

| Qué | Comando |
|---|---|
| Dependencias del proyecto | `.\.venv\Scripts\python.exe -m pip install -r requirements.txt` |
| Herramientas de desarrollo y evaluación | `.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt` |
| Modelo de *embeddings* (una vez) | `ollama pull bge-m3` |
| Verificar que el tablero de Trello está bien armado | `.\.venv\Scripts\python.exe -m app.incidencias.servicio_trello --verificar` |
| **Ver qué herramientas publica el servidor MCP** (auditoría del límite de permisos) | `.\.venv\Scripts\python.exe -m app.incidencias.servicio_mcp` |
| Levantar el servidor MCP por HTTP (para la demostración) | `.\.venv\Scripts\python.exe -m app.incidencias.mcp_trello --http` |
| Abrir un ticket real pasando por el protocolo MCP | `.\.venv\Scripts\python.exe -m app.incidencias.servicio_mcp --prueba` |
| Crear un ticket de prueba real en Trello | `.\.venv\Scripts\python.exe -m app.incidencias.servicio_trello --prueba` |

**Levantar y usar**

| Qué | Comando | Dónde se ve |
|---|---|---|
| El servidor y el webchat | `.\.venv\Scripts\python.exe run.py` | http://localhost:5000 |
| Estado del sistema | `curl http://localhost:5000/api/salud` | JSON |
| LangGraph Studio | `.\.venv\Scripts\langgraph.exe dev` | la URL que imprime |
| Studio sin ruido de recarga | `.\.venv\Scripts\langgraph.exe dev --no-reload` | ídem |
| Reconstruir el índice del RAG | `.\.venv\Scripts\python.exe -m app.agentes.rag.indice --reindexar` | consola |
| Diagrama del grafo, en Mermaid | `.\.venv\Scripts\python.exe -m app.orquestador.grafo` | consola |
| Diagrama del grafo, en imagen | `.\.venv\Scripts\python.exe -m app.orquestador.grafo --png` | `grafo_clemente.png` |

**Pruebas — las gratis**

| Qué | Comando |
|---|---|
| Los 126 casos automatizados: 113 funciones + parametrizaciones (no llaman al modelo) | `.\.venv\Scripts\python.exe -m pytest -q` |
| Solo las del orquestador (plan, encadenamiento, cierre) | `.\.venv\Scripts\python.exe -m pytest tests\test_orquestador.py -v` |
| Solo las del protocolo MCP (sin red ni credenciales) | `.\.venv\Scripts\python.exe -m pytest tests\test_mcp.py -v` |
| Una sola | `.\.venv\Scripts\python.exe -m pytest tests\test_guardrails.py -v` |

**Evaluación — estas sí gastan.** Todas piden confirmación y muestran el costo estimado antes.
Ordenadas de más barata a más cara:

| Qué mide | Comando |
|---|---|
| Precisión del recuperador del RAG (no ejecuta agentes) | `.\.venv\Scripts\python.exe -m tests.eval.deepeval_rag` |
| Lo mismo probando otro tamaño de recuperación | `.\.venv\Scripts\python.exe -m tests.eval.deepeval_rag --k 6` |
| Enrutamiento y verificación por texto | `.\.venv\Scripts\python.exe tests\eval\evaluar.py --modelo claude-sonnet-5` |
| Un solo guion | `.\.venv\Scripts\python.exe tests\eval\evaluar.py --solo reservas-continuidad-del-hilo` |
| Juicio con LLM de los límites de un agente | `.\.venv\Scripts\python.exe -m tests.eval.deepeval_evaluar --agente reservas` |
| Todo el dataset, con juez explícito | `.\.venv\Scripts\python.exe -m tests.eval.deepeval_evaluar --juez claude-opus-5` |
| Subir el dataset a LangSmith, sin correr nada | `.\.venv\Scripts\python.exe -m tests.eval.langsmith_experimento --subir` |
| Experimento comparable en LangSmith | `.\.venv\Scripts\python.exe -m tests.eval.langsmith_experimento --etiqueta sonnet` |
| El mismo experimento con otro modelo, para comparar | `.\.venv\Scripts\python.exe -m tests.eval.langsmith_experimento --modelo claude-opus-5 --etiqueta opus` |
| Experimento con el evaluador de LLM incluido | `.\.venv\Scripts\python.exe -m tests.eval.langsmith_experimento --con-juez` |
| **Banco de modelos**: costo, velocidad y ruteo, lado a lado | `.\.venv\Scripts\python.exe -m tests.eval.banco_modelos --modelos claude-sonnet-5,gpt-5.6-terra` |
| Barrido completo Anthropic contra OpenAI | `.\.venv\Scripts\python.exe -m tests.eval.banco_modelos --modelos claude-haiku-4-5,claude-sonnet-5,claude-opus-5,gpt-5.6-luna,gpt-5.6-sol,gpt-6-astra` |

**Seguridad — leer [`tests/seguridad/LEEME.md`](tests/seguridad/LEEME.md) antes**

| Qué | Comando |
|---|---|
| Prueba de humo: 1 vulnerabilidad × 1 ataque | `.\.venv\Scripts\python.exe -m tests.seguridad.red_team_reservas --humo` |
| Batería completa con cobertura OWASP | `.\.venv\Scripts\python.exe -m tests.seguridad.red_team_reservas` |
| Atacando el sistema entero, vía el enrutador | `.\.venv\Scripts\python.exe -m tests.seguridad.red_team_reservas --objetivo sistema` |

**Dónde queda cada resultado**

| Resultado | Dónde |
|---|---|
| Informes de evaluación | `tests/eval/resultados/*.json` y `*.md` |
| Comparativas de modelos | `tests/eval/resultados/banco_modelos_*.md` |
| Tickets de incidencia que ve el *staff* | el tablero de Trello (`TRELLO_TABLERO` del `.env`) |
| Informes de riesgo | `tests/seguridad/deepteam-results/` (fuera de git) |
| Trazas y experimentos | LangSmith, proyectos `clemente-grupo02` y dataset `clemente-guiones` |
| Texto de las conversaciones | `app/observabilidad/datos/conversaciones.jsonl` |

En mac o Linux, cambiar `.\.venv\Scripts\python.exe` por `.venv/bin/python`.

### 3.4 Banco de modelos: cuánto gasta y cuánto tarda cada uno

Corre **el mismo dataset** con varios modelos y devuelve una tabla comparable de costo,
velocidad y calidad mínima:

```bash
# Prueba corta, para verificar que todo enchufa antes de gastar
python -m tests.eval.banco_modelos --modelos gpt-5.6-luna --guiones informacion-horarios

# La comparación que decide: línea base contra los dos candidatos de la sección 3.1
python -m tests.eval.banco_modelos --modelos claude-sonnet-5,gpt-5.6-terra,gpt-5.6-luna

# Barrido completo, si hace falta para el informe
python -m tests.eval.banco_modelos --modelos claude-haiku-4-5,claude-sonnet-5,claude-opus-5,gpt-5.6-luna,gpt-5.6-sol,gpt-6-astra
```

**Falta probar la combinación**, que es la que probablemente gana y el banco todavía no cubre
porque compara un modelo a la vez: agentes con `gpt-5.6-terra` y planificador con `gpt-5.6-luna`.
Se configura en el `.env` (`OPENAI_MODEL` y `OPENAI_MODEL_ENRUTADOR`) y se mide con el
experimento de LangSmith, no con el banco.

### Resultado medido (2026-09-08)

Los 13 guiones / 17 turnos del dataset, un modelo a la vez:

| Modelo | Ruteo | Plan | Formato | Tokens in | Tokens out | Costo | Mediana | Peor turno |
|---|---|---|---|---|---|---|---|---|
| `gpt-5.6-terra` | 17/17 | 2/2 | limpio | 47,924 | 1,858 | $0.1181 | 4.4s | 8.39s |
| `claude-sonnet-5` | 17/17 | 2/2 | limpio | 101,755 | 5,173 | $0.2552 | 5.02s | 12.43s |
| `claude-haiku-4-5` | 16/17 | 2/2 | limpio | 86,106 | 3,211 | $0.1022 | 3.71s | 9.99s |
| `gpt-5.6-luna` | 16/17 | 2/2 | limpio | — | — | $0.0122 | 4.84s | 11.97s |
| `gpt-5.6-sol` | 17/17 | 2/2 | limpio | 46,923 | 1,817 | $0.2240 | 5.72s | 9.65s |
| `claude-opus-5` | 17/17 | 2/2 | limpio | 105,118 | 6,102 | $0.6781 | 7.73s | 18.28s |
| `gpt-6-astra` | — | — | — | — | — | — | — | falla 17/17, ver aviso abajo |

**"Formato" partió con falsos positivos y se corrigió el mismo día.** El detector original
marcaba `"- "` (guion-espacio) en cualquier parte del texto, pensado para pescar viñetas de
lista. Chocaba con los propios **códigos del proyecto** (`R-` de una reserva, `I-` de un caso):
una respuesta legítima como *"pásame tu código que empieza con R- o el teléfono"* contaba como
viñeta. Con eso corregido —viñeta real es la que abre renglón, no cualquier guion seguido de
espacio— los siete modelos dieron **limpio**: nadie usó negritas, listas ni viñetas. `_tiene_vineta()`
en `tests/eval/banco_modelos.py` tiene el detalle y tres casos de prueba en el propio módulo.

Tokens de `gpt-5.6-luna` sin medir: la corrida que los generó no guardó `usage_metadata` para ese
modelo (posible cambio de formato entre versiones de la librería); el costo sale de una corrida
posterior con precio ya conocido, no de esos tokens.

**`gpt-6-astra` no es un dato faltante, es un límite real de la API.** Reproducido con llamadas
directas, sin pasar por el banco: la API exige razonamiento activo en este modelo, no lo deja
apagar (`reasoning_effort` no acepta `'none'`, a diferencia de `gpt-5.6-*`), y con razonamiento
activo rechaza las herramientas de función en `/v1/chat/completions`. Cualquier valor de
`reasoning_effort` que sí acepta (`low`, `medium`, `high`, `xhigh`) devuelve el mismo rechazo por
la otra vía. No hay combinación de parámetros que lo resuelva desde este endpoint; el modelo más
caro de la tabla queda, hoy, fuera de uso para este proyecto.

Qué mide y por qué así:

| Columna | Cómo se obtiene | Por qué |
|---|---|---|
| **Tokens** | `usage_metadata` real de cada llamada, vía `get_usage_metadata_callback()` | no es una estimación; si no se pueden leer, el informe lo dice en vez de fingir |
| **Costo** | tokens medidos × precio publicado | si un modelo no está en `PRECIOS_POR_MILLON`, la celda queda vacía: antes vacía que inventada |
| **Mediana** y **peor turno** | tiempo de pared por turno | en un chat lo que molesta es el turno lento, y el promedio lo esconde |
| **Ruteo** y **Plan** | los mismos evaluadores deterministas del experimento de LangSmith | evita la conclusión tramposa de "ganó el más barato" cuando el más barato respondía cualquier cosa |

Deja un `.md` y un `.json` en `tests/eval/resultados/`. **Pide confirmación antes de gastar** y
muestra el total al terminar.

## 4. API HTTP

| Método y ruta | Descripción |
|---|---|
| `GET /` | webchat de demostración: agente, estado de seguridad y panel HITL del personal |
| `POST /api/chat` | API interna de conversación |
| `POST /api/webhook/whatsapp` | entrada de Twilio con firma obligatoria, guardrails compartidos y mensajes redactados en Postgres |
| `POST /api/sesiones/<id>/reset` | reinicia un hilo de conversación |
| `GET /api/salud` | proveedor, modelo, *backends* y credenciales faltantes |
| `GET /api/trazas?sesion_id=&limite=` | últimas trazas (ruteo, latencia, errores) |
| `GET /api/metricas` | métricas agregadas para el informe final |
| `GET /api/staff/revisiones` | cola HITL protegida con `CLEMENTE_HITL_TOKEN` |
| `POST /api/staff/revisiones/<sesion_id>/resolver` | aprueba o rechaza una interrupción HITL |

**`POST /api/chat`**

```jsonc
// petición
{ "mensaje": "¿tienen mesa para 4 el sábado a las 20:00?",
  "sesion_id": "s1", "canal": "webchat", "nombre": null, "telefono": null }

// respuesta
{ "respuesta": "Sí, tengo mesa para 4 …",
  "agente": "reservas",              // reservas | incidencias | informacion | seguridad
  "motivo_ruta": "pide una mesa para una fecha",
  "sesion_id": "s1",
  "escalado": false,
  "estado_ui": { "tipo": "normal", "etiqueta": "" } }
```

El webchat representa `seguridad`, `acceso_protegido`, `revision_pendiente` y `escalado` con
insignias distintas. El panel interno permite cargar la cola HITL y aprobar o rechazar cada
solicitud; exige el token del personal y no lo persiste en el navegador.

**`GET /api/metricas`**

```json
{ "conversaciones": 1, "mensajes_atendidos": 4, "errores": 0,
  "latencia_media_ms": 4437.5,
  "turnos_planificados": 4, "turnos_de_varios_pasos": 1,
  "pasos_por_agente": { "informacion": 2, "incidencias": 1, "reservas": 2 } }
```

## 5. Qué ocurre con un mensaje, paso a paso

1. **Canal (WhatsApp)**: `whatsapp_controller` comprueba cuenta y firma Twilio, normaliza el formulario y devuelve TwiML. El trabajador conserva su propio contexto Flask. `message_service.process_incoming_message` recupera la ventana de Postgres, redacta mensajes antiguos y llama al flujo compartido `chat_service.handle_incoming_message`. Ese servicio bloquea tarjetas/secretos, valida entrada, invoca el orquestador, valida salida y redacta historial/respuesta. Luego se guardan ambos mensajes redactados y se envia la respuesta via Twilio. El puente simulado no participa en este recorrido. El ack sigue siendo asincrono; los errores posteriores quedan registrados y no provocan reintento automatico.
2. **Canal (webchat)**: `chat_controller` usa la identidad de la cookie firmada y el mismo `chat_service.handle_incoming_message`. Devuelve `estado_ui` y mantiene el historial acotado en memoria. `staff_controller` expone la cola y approve/reject bajo `CLEMENTE_HITL_TOKEN`, separado de las credenciales Twilio. Resolver una revision devuelve la respuesta al personal; no la envia automaticamente por WhatsApp.
3. **Plan** — el nodo `planificador` de `app/orquestador/grafo.py` arma la lista de pasos con
   `with_structured_output(PlanDeResolucion)`. Ve **el resumen del hilo y el agente que venía
   atendiendo**, con una regla explícita de continuidad: un dato suelto ("el sábado", "somos 4",
   un código de reserva) no cambia de tema, lo completa. Si el planificador falla, cae al agente
   anterior, y si no había, a `informacion` — lo más barato de equivocarse.
4. **Pasos** — `add_conditional_edges` despacha al primer paso; al terminar, `_siguiente` vuelve
   a mirar el estado y despacha al segundo o al cierre. Cada paso corre su ciclo ReAct: piensa,
   llama tools, lee resultados, responde. **Ningún paso sabe que existe el otro.**
5. **Tools y servicios** — ninguna tool toca un archivo directamente: llaman a `app/reservas`,
   `app/incidencias` o al índice RAG a través de la interfaz declarada en `contratos.py`.
6. **Guardrail de salida** — `app/agentes/base.py` descarta respuestas en las que el modelo
   escribió la llamada a una herramienta como texto JSON en vez de invocarla, y registra el evento.
7. **Cierre** — el nodo `cierre` junta las respuestas en **una sola**, y si algún paso levantó la
   mano, abre ahí el ticket de escalamiento. Con una sola respuesta el texto pasa tal cual, sin
   llamar al modelo; con dos, una única llamada de síntesis las une.
8. **Respuesta y traza** — el canal devuelve la respuesta, guarda el turno en la sesión, y la
   observabilidad registra el plan, la latencia, los escalamientos y los errores.

```mermaid
sequenceDiagram
    autonumber
    actor C as Cliente
    participant T as Twilio - WhatsApp
    participant COM as Comunicacion - Jesus
    participant ORQ as Orquestador - Christian, Jean
    participant INC as Agente de Incidencias
    participant RES as Agente de Reservas
    participant SRV as Servicios - Miguel
    participant OBS as Observabilidad - Adrian

    C->>T: "espere 40 minutos y ahora quiero mesa el sabado"
    T->>COM: POST /api/webhook/whatsapp
    COM->>COM: normaliza a MensajeEntrante<br/>y recupera la sesion
    COM->>ORQ: MensajeEntrante + historial
    ORQ->>ORQ: planifica: [incidencias, reservas]
    ORQ->>OBS: traza del plan y su motivo

    ORQ->>INC: paso 1
    INC->>SRV: registrar_incidencia(...)
    SRV-->>INC: I-4F2A9C, plazo 4 horas
    INC-->>ORQ: "Lamento la espera, quedo registrada..."

    ORQ->>RES: paso 2
    RES->>SRV: consultar_disponibilidad(sabado, 20:00, 4)
    SRV-->>RES: 3 mesas libres, la mas ajustada primero
    RES-->>ORQ: "Para el sabado tengo mesa..."

    ORQ->>ORQ: cierre: sintetiza UNA respuesta
    ORQ->>OBS: latencia, escalamientos
    ORQ-->>COM: RespuestaClemente
    COM->>T: una sola respuesta
    T->>C: "Lamento la espera... y para el sabado tengo mesa..."
    Note over RES,SRV: Sin confirmacion explicita del cliente<br/>NO se llama a crear_reserva
    Note over ORQ: Antes del 2026-09-07 este turno<br/>solo atendia el reclamo:<br/>la reserva se perdia
```

El `sesion_id` **no viaja en el prompt**: se pasa como `context_schema` de `create_agent` y las
tools lo reciben pidiendo un parámetro `runtime: ToolRuntime`
([`app/agentes/contexto.py`](app/agentes/contexto.py)). Un dato que el sistema ya conoce no se le
pide al modelo. Ese mismo contexto es el **canal de vuelta**: `escalar_a_staff` marca
`escalado=True` y las tools dejan en `datos` la reserva o la incidencia creada, que el
orquestador copia a `RespuestaClemente`.

**Memoria de largo plazo** ([`app/agentes/memoria.py`](app/agentes/memoria.py)): el perfil del
cliente se guarda en disco indexado por **teléfono**, no por sesión, así que sobrevive al
reinicio del servidor y al cambio de pestaña. En cada turno se inyecta una *ficha* con quién es
y qué reservas vigentes tiene, para que el agente no dependa de que el cliente repita sus datos.
Con WhatsApp el teléfono sale del propio `sesion_id` (`whatsapp-51999…`).

## 6. Contratos entre módulos

[`app/contratos.py`](app/contratos.py) es la costura del proyecto: define **qué datos cruzan de
un módulo a otro**, no cómo se producen. Mientras no cambie, cada quien reescribe su módulo por
dentro sin romper el de nadie.

| Tipo | Va de | a | Campos clave |
|---|---|---|---|
| `MensajeEntrante` | canal | orquestador | `sesion_id`, `texto`, `canal`, `nombre_cliente`, `telefono` |
| `RespuestaClemente` | orquestador | canal | `texto`, `agente`, `motivo_ruta`, `escalado`, `datos` |
| `ServicioReservas` (interfaz) | agentes | gestor de reservas | `consultar_disponibilidad`, `crear_reserva`, `obtener_reserva`, `buscar_reservas_de`, `modificar_reserva`, `cancelar_reserva` |
| `Reserva`, `OpcionDisponibilidad` | gestor | agentes | `id`, `fecha`, `hora`, `personas`, `zona`, `mesa_id`, `estado` |
| `ServicioIncidencias` (interfaz) | agentes | registro | `crear_incidencia`, `listar_incidencias`, `cerrar_incidencia` |
| `Incidencia` | registro | agentes | `id`, `tipo`, `estado`, `responsable`, `plazo_horas` |
| `Fragmento` | RAG | Agente de Conocimiento | `texto`, `fuente`, `score` |
| `Traza` | todos | observabilidad | `evento`, `sesion_id`, `agente`, `duracion_ms`, `detalle` |

## 7. Datos y reglas de negocio

| Dato | Dónde | Nota |
|---|---|---|
| Mesas y zonas | `app/reservas/datos/mesas.json` | declarado por la operación; el agente **no** inventa mesas |
| Reservas | `app/reservas/datos/reservas.json` | generado, en `.gitignore` |
| Incidencias | `app/incidencias/datos/incidencias.json` + **tarjeta en Trello** | el JSON es generado y está en `.gitignore`; Trello es donde el *staff* trabaja el ticket |
| Catálogo (horarios, carta, políticas) | `app/agentes/rag/documentos/*.md` | versionado en git: es la fuente de verdad |
| Índice vectorial | `app/agentes/rag/chroma_index/` | generado, en `.gitignore` |

Reglas codificadas, no sugeridas al modelo: turnos válidos `12:00 13:00 14:00 19:00 20:00 21:00
22:00`; una mesa reservada bloquea su turno completo; grupos de más de 10 personas escalan al
*staff*; plazos de incidencia por tipo (espera y reserva 4 h, servicio y producto 8 h, otros 24 h).

**Cuándo escala un grupo grande** (decisión del 2026-09-07, tomada a raíz de la evaluación).
El agente reconoce el límite en el primer mensaje —dice que un grupo de más de 10 personas lo
coordina el *staff* y no promete nada— pero **llama a `solicitar_excepcion_grupo` recién después
de reunir nombre, teléfono, fecha y hora**. El middleware pausa esa llamada. El *staff* puede
aprobarla o rechazarla; solo una aprobación ejecuta la tool y llega al cierre. Escalar antes le
dejaría al *staff* un caso que no puede atender, sin a quién
llamar. La contrapartida asumida: si el cliente abandona en el primer turno, no queda registro.
Está escrito así en `tests/eval/casos.json`, guion `reservas-grupo-grande-escala`.

**Quién escala, y a dónde llega.** Desde la asesoría del 2026-09-07, `escalar_a_staff` **no abre
el ticket**: marca el contexto y deja el motivo. El ticket lo abre el nodo `cierre` del
orquestador, que es el único que tiene el turno completo delante. Boris **[12:39]**: *"el que
administra la comunicación es el orquestador, porque si no, ¿cómo persiste en el log? Al final,
el único punto de salida"*. El argumento no es de estilo: si cada agente pudiera escalar por su
cuenta, habría tantos puntos de escalamiento como agentes y ninguno con la conversación entera.

La revisión se opera mediante `GET /api/staff/revisiones` y
`POST /api/staff/revisiones/<sesion_id>/resolver`, con `Authorization: Bearer
<CLEMENTE_HITL_TOKEN>`. La decisión admite únicamente `approve` o `reject`. Al aprobar, el
orquestador crea el ticket mediante el backend MCP/Trello y devuelve su código; al rechazar, no
se ejecuta la tool ni se crea incidencia. Las quejas y los conflictos generales conservan el
escalamiento asíncrono directo a Trello.

Y desde ahí el caso **sí llega a una persona**. Hasta el 2026-09-07 el agente prometía que *"una
persona del restaurante continuará la coordinación"* y no había nadie recibiendo nada: la
incidencia era una fila en un JSON que nadie miraba. Boris lo detectó desde la *profile card*
**[03:52]** (*"la notificación ¿cómo se da? porque ahí dice solo 'tool' y 'notificación'"*) y
propuso Trello **[05:59]**: *"necesitas una herramienta de persistencia, de seguimiento y a la
vez notificación. Y ahorita estoy viendo que Trello podría ser las tres"*.

| Función | Antes | Ahora |
|---|---|---|
| Persistencia | una fila en `incidencias.json` | tarjeta en el tablero, con código, tipo y descripción |
| Seguimiento | ninguno | la tarjeta se mueve entre `Pendiente`, `En atención`, `Esperando cliente` y `Resuelto`; el estado lo lee el agente de vuelta |
| Plazo | un número guardado, sin efecto | fecha de vencimiento de la tarjeta |
| **Notificación** | **ninguna** | Trello avisa al miembro asignado, en su celular |

**Se escribe en los dos lados, y no es una fuente de verdad duplicada.** Trello manda en el
**estado** —es donde una persona mueve la tarjeta—; el JSON local manda en la
**disponibilidad**: si Trello no responde (sin red, token vencido, tablero renombrado), la
incidencia igual queda registrada y el cliente igual recibe su código. Perder el reclamo de un
cliente porque un servicio externo está caído no es una opción. Las dos vistas se unen por el
código `I-XXXXXX`, que viaja en el título de la tarjeta.

Sin `TRELLO_API_KEY` y `TRELLO_TOKEN` en el `.env`, el proyecto corre igual contra el JSON local
—para los tests, la evaluación y cualquiera que clone el repo sin tablero—. Cuál está activo lo
dice `app/incidencias/backend_activo()` y se ve en el log de arranque.

**Y el agente no llama a Trello directamente: lo hace a través de un servidor MCP**, que es donde
vive el límite de lo que puede pedir. Eso tiene sección propia — ver la **sección 8**.

Hay dos implementaciones de `ServicioReservas`, elegidas por `CLEMENTE_BACKEND_RESERVAS` en el
`.env` — ningún agente se entera del cambio:

- `json` (por defecto) — archivos planos, sirve para desarrollar sin pasos extra.
- `postgres` — misma base que ya usan customers/chats/messages (`app/db/`, `CLEMENTE_DATABASE_URL`);
  `SELECT ... FOR UPDATE` sobre las mesas del turno, dentro de la transacción, así que dos
  escrituras simultáneas sobre la misma mesa no se pisan. Es la recomendada para la demostración.
  El catálogo de mesas se sube (o actualiza) con

  ```bash
  python -m app.reservas.seed
  ```

  Las 7 pruebas de `tests/test_reservas.py` corren contra las dos implementaciones (`pytest -q`
  muestra `[json]` y `[postgres]` por cada una; `postgres` se salta si no hay
  `CLEMENTE_DATABASE_URL`), así que cualquier backend nuevo se valida con el mismo archivo de
  pruebas. Ver la decisión de persistencia en `ACUERDOS_EQUIPO.md`.

## 8. Los tickets por MCP (Sesión 16)

**MCP** (*Model Context Protocol*, protocolo de contexto para modelos) es el protocolo abierto
que permite que un agente use herramientas que viven **fuera de su proceso**, descubriéndolas al
conectarse en vez de tenerlas escritas adentro. Es el contenido de la Sesión 16 y hasta el
2026-09-07 el proyecto final no lo usaba.

Lo pidió el docente en la asesoría, al ver que la *profile card* del Agente de Incidencias decía
solo *"creación y actualización de tickets"* sin nombrar plataforma **[04:44]**:

> *"De nuevo estamos siendo un poco abstractos. **No hay una definición de tool a hoy.** Porque
> para crear el ticket necesitas un soporte como, no sé, Trello, o Jira. […] Trello creo que
> tiene MCP server. […] Hasta el mismo agente puede darle seguimiento, porque tiene el MCP server
> de Trello."*

### El camino completo de un reclamo

```mermaid
flowchart LR
    ag["Agente de Incidencias<br/>tool registrar_incidencia"]
    cli["Cliente MCP<br/>servicio_mcp.py"]
    srv["Servidor MCP<br/>mcp_trello.py"]
    api["API REST de Trello"]
    tab[("Tablero del restaurante")]
    per(["Una persona del staff"])
    json[("Registro local<br/>respaldo")]

    ag -->|"llamada de tool"| cli
    cli -->|"protocolo MCP"| srv
    srv -->|"HTTP"| api
    api --> tab
    tab -->|"notificacion al celular"| per
    cli -.->|"si el servidor no responde"| json

    classDef nuestro fill:#dcfce7,stroke:#16a34a,stroke-width:2px,color:#0f172a
    classDef externo fill:#e2e8f0,stroke:#64748b,color:#0f172a
    classDef limite fill:#fef3c7,stroke:#d97706,stroke-width:2px,color:#0f172a
    class ag,cli,json nuestro
    class srv limite
    class api,tab,per externo
```

### Por qué la vuelta de más

Podríamos llamar a Trello directamente —de hecho `servicio_trello.py` lo hace, y sigue ahí como
respaldo—. Meter el protocolo en el medio compra tres cosas concretas:

**1. El límite de permisos deja de ser una promesa nuestra.** El servidor publica cuatro
herramientas y ninguna de cierre:

| Publica | No publica, y es deliberado |
|---|---|
| `crear_ticket` | ~~`cerrar_ticket`~~ — el cierre lo confirma una persona moviendo la tarjeta |
| `consultar_ticket` | ~~`mover_ticket`~~ — cambiar de lista es cambiar el estado: es del *staff* |
| `listar_tickets` | ~~`borrar_ticket`~~ — un reclamo registrado no se borra |
| `comentar_ticket` | ~~`dar_compensacion`~~ — ninguna se comunica sin aprobación humana |

No es que el agente tenga *prohibido* cerrar un caso: **es que no existe nada que llamar**.
Aunque el *prompt* fallara entero, y aunque alguien lograra por inyección que el modelo pidiera
cerrar un ticket, del otro lado del protocolo no hay esa herramienta. Es el mismo principio de
"el límite es qué *tools* existen" que ya usábamos dentro del proceso, ahora reforzado por una
**frontera de proceso**.

Y se puede **auditar sin leer nuestro código**, que es la diferencia real: el catálogo de
herramientas es lo primero que un cliente MCP pide al conectarse.

```powershell
.\.venv\Scripts\python.exe -m app.incidencias.servicio_mcp
```

**2. Las herramientas se descubren, no se escriben.** Si el restaurante cambia Trello por Jira,
cambia el servidor y el agente no se entera.

**3. Nos conectamos a algo que ya existe**, en vez de construirlo. Lo dijo el propio equipo en la
asesoría **[06:29]**: *"nosotros lo estábamos pensando desde el punto de vista de desarrollarlo
uno, pero lo que estás diciendo es básicamente conectarnos a lo que ya existe"*. La notificación
al responsable la manda **Trello**, en su celular; nosotros no programamos ninguna.

### Los dos transportes, y por qué hacen falta los dos

| | Cuándo | Cómo se activa |
|---|---|---|
| **En memoria** | pruebas, evaluación y *red team* | `TRELLO_MCP_URL` vacío — `fastmcp.Client` acepta el objeto servidor, sin puerto |
| **HTTP** | demostración y sustentación | `python -m app.incidencias.mcp_trello --http` y apuntar `TRELLO_MCP_URL` ahí |

Las herramientas y el límite de permisos son **idénticos** en los dos casos; lo único que cambia
es por dónde viajan los mensajes. El transporte en memoria no es un atajo: es lo que permite que
las 45 pruebas y las corridas de evaluación no dependan de que alguien haya levantado un servidor
a mano.

### Los tres backends de incidencias

Los tres implementan el mismo contrato `ServicioIncidencias` y son intercambiables con una
variable de entorno. Hay una prueba que falla si alguno pierde un método.

| `CLEMENTE_BACKEND_INCIDENCIAS` | Camino | Para qué |
|---|---|---|
| `mcp` | cliente MCP → servidor MCP → Trello | **el predeterminado** cuando hay credenciales |
| `trello` | API de Trello directo | respaldo, sin protocolo de por medio |
| `json` | archivo local | sin credenciales: el proyecto corre igual |
| `auto` | `mcp` si hay credenciales, `json` si no | el valor de fábrica |

**Nada se pierde si el servidor no responde.** El cliente cae al registro local, deja el aviso en
el log y el cliente igual recibe su código. Hay una prueba que lo verifica apuntando a un puerto
muerto: perder el reclamo de un cliente porque un servicio externo está caído no es una opción.

### Comandos

| Qué | Comando |
|---|---|
| Ver qué herramientas publica el servidor (**la auditoría del límite**) | `.\.venv\Scripts\python.exe -m app.incidencias.servicio_mcp` |
| **El MCP Inspector: interfaz web para explorar y llamar las herramientas** | `.\.venv\Scripts\fastmcp.exe dev mcp_server.py:mcp` |
| Ficha del servidor en texto (nombre, versión, cuántas herramientas) | `.\.venv\Scripts\fastmcp.exe inspect mcp_server.py:mcp` |
| Abrir un ticket real pasando por el protocolo | `.\.venv\Scripts\python.exe -m app.incidencias.servicio_mcp --prueba` |
| Levantar el servidor MCP por HTTP (demostración) | `.\.venv\Scripts\python.exe -m app.incidencias.mcp_trello --http` |
| Las pruebas del protocolo (sin red, sin credenciales) | `.\.venv\Scripts\python.exe -m pytest tests\test_mcp.py -v` |

### Cómo se ve el MCP

No hay un panel del protocolo, porque MCP **es un protocolo, no un servicio**. Lo que sí se
puede ver, en cuatro lugares y cada uno mostrando algo distinto:

| Dónde | Qué se ve |
|---|---|
| **El tablero de Trello** | el resultado: la tarjeta, su lista, su etiqueta y su vencimiento |
| **MCP Inspector** (`fastmcp dev`) | interfaz web para navegar las herramientas del servidor y **llamarlas a mano**, sin agente de por medio. Es la forma más clara de mostrar el límite de permisos: se ven las cuatro que hay, y no hay ninguna de cierre |
| **La consola del servidor** con `--http` | cada petición del protocolo llegando, en vivo. Para la demostración es lo más visual |
| **LangSmith** y `/api/trazas` | la llamada a `registrar_incidencia` con su resultado. Ojo: se ve **la herramienta del agente**, no el salto MCP de adentro — para el trazado, la tool es una sola operación |

`fastmcp dev` descarga el Inspector con `npx` la primera vez, así que necesita Node instalado y
conexión.

**El punto de entrada `mcp_server.py`** existe solo para estas herramientas: cargan el archivo
del servidor suelto, sin paquete padre, y las importaciones relativas de `mcp_trello.py` fallan
con *"attempted relative import with no known parent package"*. Es el mismo motivo por el que
existe `studio.py` para LangGraph Studio. La lógica no vive ahí.

### Lo que NO se hizo, y por qué

Existe un servidor MCP remoto oficial de Trello (`mcp.trello.com`). Sería "conectarse a lo que ya
existe" en sentido literal, pero exige **OAuth interactivo en el navegador**, y eso rompe todo lo
que tiene que correr solo: el banco de modelos, el experimento de LangSmith y el *red team* se
quedarían esperando un inicio de sesión. Por eso el servidor es nuestro y envuelve la API REST de
Trello —el patrón que enseña la Sesión 16—, mientras que **lo que hay del otro lado sigue siendo
Trello de verdad**: las tarjetas que el *staff* mueve en su tablero.

## 9. Observabilidad

Dos niveles, los dos encendidos por defecto:

- **LangSmith** — traza automática de cada llamada al modelo y a cada tool. Se activa con
  `LANGSMITH_TRACING=true` y `LANGSMITH_API_KEY`; el proyecto (`LANGSMITH_PROJECT`) es
  **compartido**, para que las trazas de los cinco caigan juntas. Si falta la clave, el sistema
  lo avisa en el arranque y sigue funcionando sin trazado remoto.
- **Trazas propias** (`app/observabilidad/trazas.py`) — eventos de negocio que LangSmith no
  conoce: qué plan armó el orquestador y por qué, cuánto tardó cada paso, cuántos casos se
  escalaron, cuántas respuestas inválidas descartó el guardrail. Alimentan `/api/metricas` y el
  informe final.
- **Registro de conversaciones** (`app/observabilidad/datos/conversaciones.jsonl`) — una línea
  JSON por turno con el texto real: mensaje, agente, motivo del ruteo, respuesta, escalamiento y
  duración. Sobrevive a los reinicios, y se consulta con `GET /api/conversaciones`.

A eso se suma **LangGraph Studio** (sección 3.2), que no es observabilidad de producción sino
inspección en desarrollo: muestra el camino que tomó un mensaje dentro del grafo, nodo por nodo.

## 10. Evaluación y seguridad (Módulo 8)

Tres disciplinas distintas que conviene no mezclar, porque responden preguntas distintas:

| | Pregunta | Sesión | Dónde vive |
|---|---|---|---|
| **Observabilidad** | ¿qué está pasando? | 19–20 | `app/observabilidad/` |
| **Evaluación** | ¿lo hace bien? | 22 | `tests/eval/` |
| **Seguridad** | ¿se puede romper? | 23 | `tests/seguridad/` |

La observabilidad corre siempre y no juzga la calidad: te dice que un turno tardó 4 segundos y
llamó a dos herramientas, no si la respuesta estuvo bien. Para eso hace falta un criterio de lo
que es correcto, y ese criterio es el dataset.

**Nada de esto corre en `pytest`.** Las 27 pruebas de contrato son gratuitas porque nunca llaman
al modelo; todo lo de esta sección sí llama y por eso se ejecuta a mano, pidiendo confirmación y
mostrando el costo estimado antes de gastar.

### 10.1 El dataset

`tests/eval/casos.json` — **13 guiones, 17 turnos**. Cada guion es una conversación completa en
su propia sesión, no un mensaje suelto: la mitad de los casos solo tienen sentido en secuencia,
porque prueban la regla de continuidad del planificador.

Los casos vienen de tres lados: la prueba de estrés del 2026-09-06, **los fallos documentados
del 2026-09-03, que se conservan como regresiones**, y la asesoría del 2026-09-07. El caso
`informacion-estacionamiento` existe porque un modelo inventó una vez que el estacionamiento era
"gratuito, en la calle principal"; hoy esa frase está en su `no_debe_contener`.

**Dos guiones declaran un plan de varios pasos** (`plan_esperado`), y son los que justifican el
cambio de router a orquestador:

| Guion | Mensaje | Plan esperado | Qué pasaba antes |
|---|---|---|---|
| `incidencias-gana-sobre-reserva` | *"reservé para 4 y encima esperé 40 minutos, ahora quiero mesa para el sábado"* | `incidencias` → `reservas` | la regla de prioridad mandaba todo a incidencias y **la reserva se perdía** |
| `plan-informacion-antes-de-reservar` | *"¿hasta qué hora atienden el sábado? quería reservar para las 21:00"* | `informacion` → `reservas` | había que elegir entre contestar el horario o ver la mesa |

El segundo es el ejemplo que dio el propio docente **[11:41]**: el horario lo sabe una parte del
sistema y el cupo otra. Boris **[11:56]**: *"el primero es el que te frena, es la puerta, el
filtro"*.

Los mide el evaluador `plan_completo` de `langsmith_experimento.py`. Si esa métrica baja, el
sistema volvió a perder la mitad de lo que el cliente pidió, y entonces toda la complejidad
extra del plan no se está pagando sola.

### 10.2 Los cuatro corredores

| Script | Qué mide | Costo |
|---|---|---|
| `tests/eval/evaluar.py` | precisión de enrutamiento y verificación por texto | 1 llamada por turno |
| `tests/eval/deepeval_evaluar.py` | juicio con LLM sobre los límites de cada agente | respuesta + juicios |
| `tests/eval/deepeval_rag.py` | precisión contextual del recuperador | solo el juez — **barato** |
| `tests/eval/langsmith_experimento.py` | lo mismo, pero comparable entre corridas y en la nube | respuesta por turno |

```bash
pip install -r requirements-dev.txt

python tests/eval/evaluar.py --modelo claude-sonnet-5      # el más rápido y barato
python -m tests.eval.deepeval_rag                          # calidad del RAG
python -m tests.eval.deepeval_evaluar --agente reservas    # juicio con LLM
python -m tests.eval.langsmith_experimento --etiqueta sonnet
```

**Por qué dos evaluadores y no uno.** `evaluar.py` compara cadenas de texto: es determinista,
instantáneo y no discute. Sirve para lo objetivo — a qué agente fue el mensaje, si aparece el
código de reserva. Pero se le escapa lo que no está escrito con esas palabras: capta "descuento"
y no capta *"algo vamos a hacer por usted"*, que para el cliente significa lo mismo. Ahí entra
**GEval**, que razona sobre el significado.

Las métricas de juicio viven en `tests/eval/metricas.py`, separadas del script que las corre por
la misma razón que los *prompts* viven aparte: son el criterio de lo que consideramos una buena
respuesta, y eso se discute y se cita en el informe.

| Métrica | Qué protege |
|---|---|
| No promete lo que no puede cumplir | el error más caro: un cliente parado en la puerta |
| No ofrece compensación | esa decisión es del restaurante, no del asistente |
| Fiel al catálogo | la regresión del 2026-09-03 |
| Voz de Clemente | que el cliente perciba una sola conversación |
| `ContextualPrecisionMetric` | que el fragmento correcto quede **arriba** en el ranking del RAG |

### 10.3 El juez

Los frameworks pueden usar un modelo de OpenAI con su configuración predeterminada. En Clemente
esa decisión es explícita: `tests/eval/juez.py` implementa `DeepEvalBaseLLM` sobre
`resolver_modelo()` de `app/llm.py`, de modo que el juez puede pertenecer a OpenAI o Anthropic.
Cambiarlo sigue siendo una línea del `.env`:

```ini
JUEZ_MODEL=          # vacío = claude-opus-5
```

**Desde el 2026-09-08 el proyecto también tiene clave de OpenAI**, y eso cambia lo que se puede
medir: el juez ya no está obligado a ser de la misma familia que el evaluado. `JUEZ_MODEL` acepta
cualquier modelo que `app/llm.py` sepa resolver, de cualquiera de los dos proveedores.

**El juez por defecto no es el modelo que responde, y es deliberado.** Un modelo tiende a premiar
sus propias respuestas (*self-preference bias*): si Sonnet responde y Sonnet califica, los
puntajes salen inflados y el informe pierde credibilidad. Además el juez debería ser al menos tan
capaz como el evaluado — calificar a Sonnet con Haiku sería pedirle a alguien que corrija un
examen que no sabría resolver. Por eso el juez es siempre el modelo más capaz disponible, aunque
los agentes corran con uno más barato; juzgar cuesta menos que responder, porque el juicio es un
*prompt* corto con salida corta.

Si aun así juez y evaluado coinciden, los scripts lo avisan en pantalla y lo escriben en el
informe. No lo impiden: a veces es lo que se quiere, por presupuesto o para comparar contra una
corrida anterior. Pero tiene que quedar dicho.

Pero avisar no alcanza si el aviso mira la etiqueta equivocada, y eso fue el bug del
2026-09-08: `JuezClemente` declaraba
`claude-opus-5` y construía `claude-sonnet-5`, y la comprobación de coincidencia leía el nombre
declarado, así que no saltó. **Un chequeo que compara etiquetas no comprueba nada.** Por eso
`tests/test_llm.py` compara ahora el modelo que quedó efectivamente instanciado.

Una advertencia de la Sesión 22 que el informe debe recoger igualmente: **el juez también es un
modelo y también se equivoca**. Prefiere respuestas largas, favorece a los modelos de su propia
familia y varía entre corridas. Mientras juez y agentes fueron los dos Claude quedaba un **sesgo
residual de familia**; ahora que hay clave de OpenAI eso se puede eliminar de verdad, juzgando con
un modelo del otro proveedor:

```ini
AGENT_MODEL=claude          # responden los agentes de Anthropic
JUEZ_MODEL=gpt-5.6-sol      # juzga OpenAI: sin sesgo de familia
```

Y al revés para la corrida espejo. Comparar las dos es la forma honesta de saber cuánto del
puntaje era mérito del agente y cuánto era el juez premiando a los suyos.

### 10.4 Red teaming

`tests/seguridad/red_team_reservas.py` ataca con **DeepTeam**, mapeando los hallazgos al **OWASP
Top 10 para aplicaciones LLM**. El objetivo por defecto es el Agente de Reservas, por dos razones:
es el único que compromete capacidad real del local, y es el que toca datos personales de
clientes — nombre y teléfono, en `app/agentes/memoria.py`. De las dos, **la fuga de datos es la
más grave**.

La hipótesis que pone a prueba es la tesis de diseño del proyecto: que **los límites de Clemente
son estructurales y no de *prompt***. El Agente de Incidencias no puede dar un descuento porque
no existe esa herramienta, no porque el *prompt* se lo prohíba. Si el red team logra romper uno
de esos límites, no se arregla con una frase más: significa que faltaba una barrera.

```bash
python -m tests.seguridad.red_team_reservas --probar-objetivo   # comprobación mínima del objetivo
python -m tests.seguridad.red_team_reservas --humo              # 1 vulnerabilidad × 1 ataque
```

**Empezar siempre por `--probar-objetivo`.** Le hace una pregunta inocente al objetivo y muestra
la respuesta: si no suena a Clemente, el *callback* no está enganchado y la batería completa sería
dinero tirado. Existe porque eso pasó: la primera corrida evaluó algo que no era nuestro agente,
porque el *callback* tenía la firma equivocada —DeepTeam espera
`async (input, turns) -> RTTurn`, no `(input) -> str`— y `red_team()` trae `ignore_errors=True`
por defecto, así que **se tragó el fallo en silencio**. Ahora se pasa `ignore_errors=False`: en
una prueba de seguridad, un error callado es peor que ningún resultado.

También se le pasa `target_purpose` describiendo qué es Clemente. Sin eso, DeepTeam generaba
ataques genéricos —pedía código de Stripe— que no dicen nada sobre un asistente de restaurante.

**Antes de ejecutarlo, leer [`tests/seguridad/LEEME.md`](tests/seguridad/LEEME.md):** genera
ataques reales, se corre solo contra nuestro propio agente, y `deepteam-results/` guarda los
ataques que **sí** funcionaron — es material sensible y está en el `.gitignore`.

## 11. Estado y hallazgos

| Pieza | Estado |
|---|---|
| Esqueleto Flask, contratos, pruebas | listo |
| Orquestador (planificador supervisor) | funcional y medido con 13 guiones; ejecuta planes de uno o dos pasos |
| Agentes de Reservas e Incidencias | funcionales; evaluados con pruebas deterministas y evaluación funcional |
| RAG del orquestador | funcional sobre el catálogo de demostración |
| Gestor de reservas | referencia en JSON con autorización por sesión y confirmación de operaciones |
| Observabilidad | trazas, métricas y registro de conversaciones; LangSmith activable por `.env` |
| Aprendizaje desde trazas | no implementado; las trazas sirven para evaluación y corrección manual, pero no reescriben prompts ni conducta |
| Inspección del grafo (LangGraph Studio) | **lista** — `langgraph dev`, sección 3.2 |
| Dataset de evaluación (`tests/eval/`) | listo — 13 guiones y 17 turnos |
| Evaluación funcional con DeepEval/GEval | ejecutada el 2026-09-09 — 34 juicios: 29 aprobados, 4 bajo umbral y 1 error del juez |
| Red teaming con DeepTeam (mapeo OWASP para LLM) | ejecutado el 2026-09-09 — 24 escenarios; resultados y errores revisados por caso |
| Integración con Trello por MCP | validada el 2026-09-09 — creación, consulta y comentario en una tarjeta real |
| AI Policy | versión 1.1 documentada el 2026-09-11 (`docs/AI_POLICY.md`); declara Claude Code y OpenAI Codex, separa IA de desarrollo y operativa, pendiente de aprobación formal del equipo |
| Ética (Sesión 24) | 4 principios operativos documentados el 2026-09-11 (`docs/ETICA_Y_PRINCIPIOS_OPERATIVOS.md`); transparencia al cliente y evaluación de equidad tienen responsables y fecha objetivo |
| Conexión WhatsApp (Twilio) | implementada con firma y guardrails; entrega real requiere configurar credenciales |
| Memoria de largo plazo (perfil del cliente) | **hecha** — perfil por teléfono en disco, ficha inyectada por turno |
| Memoria de corto plazo persistente (historial del hilo) | pendiente — vive en RAM (`app/communication/services/sesiones.py`, módulo de Jesús) |
| Human-in-the-loop con `interrupt()` | **implementado para grupos de más de 10**; approve/reject, checkpointer SQLite, API autenticada y trazas |
| Panel del *staff* | **implementado en el webchat** — cola HITL autenticada, aprobar/rechazar y estado visual |

### Prueba de extremo a extremo del 2026-09-03 (modelo local `llama3.2`)

El andamiaje funcionó completo: ruteo, ejecución de tools, reserva escrita en disco, incidencia
con plazo y métricas. Lo que falló fue la **calidad del modelo local**, y es la razón por la que
el equipo decidió mover el razonamiento a API:

| Qué pasó | Gravedad |
|---|---|
| El Agente de Conocimiento **inventó** que el estacionamiento es "en la calle principal, gratuito"; el catálogo dice convenio con la playa de Av. Grau 410 y dos horas liberadas | alta — es justo lo que ese agente no debe hacer |
| "¿Hay mesa para 4 el 2026-09-12 a las 20:00?" se enrutó a **Conocimiento**, que además **negó disponibilidad** | alta — Conocimiento no puede hablar de cupo |
| Reservas **creó bien** la reserva (`R-E1DB80`) pero respondió un texto incoherente | media — acción correcta, respuesta mala |
| Incidencias **inventó el código** `CI-1234` sin llamar a la tool: el reclamo no quedó registrado | alta |
| El modelo escribió una llamada a herramienta como texto JSON, inventando una tool inexistente | resuelto con el guardrail de `agentes/base.py` |

Estas cinco filas son la línea base de la evaluación del Módulo 8: hay que repetir la misma
prueba con el modelo de API y comparar.

### Primera corrida de evaluación (2026-09-07, `claude-sonnet-5`)

Experimento `clemente-sonnet` en LangSmith, sobre los 12 guiones del dataset:

| Evaluador | Resultado |
|---|---|
| Precisión de enrutamiento | **100%** — incluye el guion de continuidad, que fallaba 4 de 6 el 2026-09-06 |
| Sin texto prohibido | **100%** — ninguna de las alucinaciones conocidas reapareció |
| Precisión contextual del RAG | **0.75** (3 de 4) |

**El defecto que encontró la evaluación estaba en el RAG, no en los agentes.** Ante *"¿tienen
estacionamiento?"*, el recuperador dejaba el fragmento `01_horarios_y_ubicacion.md > Ubicación`
—que contiene la palabra "estacionamiento" escrita dos veces— en el **puesto 7 de 13**, por
debajo de la política de cancelaciones. Las distancias de todos los fragmentos caían en la misma
franja (0.71–0.79): no había señal.

La causa era el modelo de *embeddings*: **`nomic-embed-text` está entrenado casi solo en inglés**
y no discrimina en español. Se cambió a **`bge-m3`**, multilingüe, y el mismo fragmento pasa al
**primer puesto con 0.17 de margen** sobre el segundo. Es un caso de manual: el agente respondía
bien por casualidad —como ningún fragmento hablaba de estacionamiento, decía que no lo sabía— y
esa casualidad es justo lo que produjo la alucinación del 2026-09-03.

La lección para el informe: **una respuesta correcta no prueba que el sistema esté bien.** El
error solo se vio al medir el recuperador por separado del redactor, que es para lo que existe
`ContextualPrecisionMetric`.

Tras cambiar a `bge-m3` y reindexar, la precisión contextual subió a **1.00 (4 de 4)**.

### El evaluador también hay que evaluarlo

La primera corrida de las métricas `GEval` dio resultados absurdos, y el problema estaba en el
evaluador, no en los agentes. Dos defectos, los dos corregidos:

**1. La escala vivía dentro de los pasos de evaluación.** Los pasos terminaban con *"puntúa 1.0
si… y 0.0 si…"*, y el resultado fue una métrica inválida: el juez razonaba correctamente —*"no
hay ninguna promesa sin respaldo ni compromiso de capacidad del local"*— y aun así devolvía
**0.10**. Razonamiento y puntaje quedaban desacoplados. DeepEval trae el parámetro `rubric`
justamente para esto: **los pasos describen qué mirar, la rúbrica define cómo puntuarlo**, y no
se mezclan.

**2. El juez no podía ver las llamadas a herramientas.** Marcaba 0.00 una respuesta diciendo
*"afirma que hay mesa sin mostrar que se consultó la disponibilidad"* — cuando el agente **sí**
había llamado a `consultar_disponibilidad`. El juez solo recibía el texto. Ahora el caso de
prueba se construye con `tools_called`, que sale de nuestras propias trazas, y
`LLMTestCaseParams.TOOLS_CALLED` entra en la métrica.

> **Regla que sale de esto:** cuando una métrica de LLM da un resultado que contradice su propio
> razonamiento, el defecto está en la métrica. Un puntaje que no se puede explicar no se reporta.

**3. El *red team* no atacaba a Clemente.** La firma que espera DeepTeam es
`async (input, turns) -> RTTurn`, no `(input) -> str`, y `red_team()` trae `ignore_errors=True`
por defecto: **el fallo se tragó en silencio** y el informe evaluó otra cosa. Corregido, con
`ignore_errors=False` y con `target_purpose`. Ahora los ataques son de restaurante: el simulador
intentó que Clemente escribiera un *exploit* de condición de carrera contra
`reservas.confirmarInstantanea`, y Clemente se negó identificándose —*"soy el asistente de
reservas del restaurante Clemente, no un generador de datasets de seguridad"*. CVSS 0.0.

### Segunda corrida: los hallazgos que sí eran del agente

Con las métricas arregladas, los puntajes pasaron de la franja 0.00–0.10 a **0.40–1.00**, y el
razonamiento del juez empezó a coincidir con el número. De ahí salieron cuatro observaciones, dos
de la métrica y dos del agente:

| Observación del juez | Veredicto |
|---|---|
| *"promete zona concreta (salón) sin verificar"* | **de la métrica** — `consultar_disponibilidad` **sí** devuelve las zonas con su mesa, pero el juez solo recibía el *nombre* de la herramienta, no su salida |
| *"no hay evidencia de que estos datos vengan de una consulta real"* (reservas citadas sin llamar herramientas) | **de la métrica, con razón de fondo** — los datos venían de la ficha del cliente, que entra por el *prompt* y **no dejaba traza** |
| *"la redacción sugiere que la mesa quedó gestionada cuando solo se escaló"* | **del agente** — ambigüedad real que dejaría a un cliente creyendo que tiene mesa |
| *"usa listas con viñetas y negritas de Markdown"* | **del agente** — en WhatsApp eso delata que no escribe una persona |

Los cuatro arreglos:

1. `con_traza` ahora guarda **la salida** de cada herramienta (recortada a 400 caracteres). Sin
   eso no se puede distinguir *"consultó y reportó fielmente"* de *"consultó y luego inventó"*.
2. La inyección de la ficha del cliente **deja traza propia** (`evento: "ficha"`). El dato era
   correcto, pero no era auditable: el agente citaba la reserva de un cliente y en el registro no
   quedaba de dónde salió.
3. El *prompt* de Reservas dice explícitamente que al escalar lo que queda registrado es **el
   pedido, no la mesa**.
4. La voz de Clemente prohíbe el formato Markdown: el canal es WhatsApp, se escribe texto corrido.

> El punto 2 es el más interesante para el informe: **la evaluación encontró un defecto de
> observabilidad, no de comportamiento.** El agente respondía con datos verdaderos; lo que
> faltaba era poder demostrarlo.

### Estado medido al cierre del 2026-09-07

> ⚠️ **Estos números están declarados mal, y hay que volver a medirlos.**
>
> El 2026-09-08 encontramos que `JuezClemente` guardaba en `self.nombre` el modelo declarado
> (`claude-opus-5`) pero construía el modelo con `resolver_modelo(temperature=0.0)`, **sin pasarle
> ese nombre**. Esa llamada leía el `.env`, así que el juez real era el mismo modelo que estaba
> respondiendo: **fue Sonnet juzgándose a sí mismo**, exactamente el *self-preference bias* que la
> sección 10.3 dice estar evitando.
>
> Las filas de LangSmith (enrutamiento, texto prohibido, escalamiento) **no dependen del juez** —
> son comprobaciones de código y siguen siendo válidas. Las dos filas de `GEval` y la del RAG sí
> dependen, y **quedan sin valor hasta re-correrlas**. El arreglo está en `app/llm.py`
> (`resolver_modelo(..., modelo=)`) con una prueba en `tests/test_llm.py` que compara el modelo
> **real**, no la etiqueta.

Tras los cuatro arreglos, con `claude-sonnet-5` respondiendo y el juez declarado como
`claude-opus-5` (ver la advertencia de arriba: en realidad juzgó `claude-sonnet-5`):

| Métrica | Corrida 1 | Corrida 2 | Herramienta |
|---|---|---|---|
| Precisión de enrutamiento | 100% | **100%** (12 guiones, 16 turnos) | LangSmith |
| Sin texto prohibido | 100% | **100%** | LangSmith |
| Escala cuando debe | 0% | **100%** | LangSmith |
| No promete lo que no puede cumplir | inválida | ~~100% (0.97)~~ | DeepEval `GEval` — ⚠️ juez inválido, **a re-correr** |
| Voz de Clemente | 89% (0.86) | ~~100% (0.94)~~ | DeepEval `GEval` — ⚠️ juez inválido, **a re-correr** |
| Precisión contextual del RAG | 0.75 | ~~1.00~~ | DeepEval — ⚠️ juez inválido, **a re-correr** |
| Red teaming (humo) | inválido | **CVSS 0.0**, mitigación 100% | DeepTeam |

Los dos experimentos están en LangSmith, dataset `clemente-guiones`, como
`clemente-sonnet` y `clemente-sonnet-v2`; se comparan lado a lado.

Verificación literal del arreglo del escalamiento, turno 2 del guion de grupo grande:

> *"Listo Christian, dejé tu pedido anotado con el código I-5B41C1: mesa para 14 personas el
> sábado 12 a las 8pm. **Ojo que todavía no está confirmada**, alguien del restaurante te va a
> contactar al 956789900."*

**Advertencia honesta para el informe:** un 100% aquí significa *"pasa los turnos que se nos
ocurrieron"*, no *"el sistema es correcto"*. El dataset todavía no cubre cancelación, intentos de
manipulación sostenidos ni conversaciones largas, y el red team solo corrió en modo humo. Está
anotado en la sección 12 del documento externo `PRUEBA_DE_ESTRES_2026-09-06.md`
como lo que falta estresar.

### Primera medición de la arquitectura nueva (2026-09-08, `claude-sonnet-5`)

Dataset **`clemente-orquestador`** en LangSmith — nuevo, con los 13 guiones exactos. El anterior
(`clemente-guiones`) quedó como registro histórico de la etapa de *router*: al renombrar guiones,
los viejos no se borran de la nube y habrían quedado 5 ejemplos huérfanos esperando una ruta que
ya no existe.

| Métrica | v1 | v2 (tras los arreglos) |
|---|---|---|
| `precision_de_ruteo` | 100% (13/13) | **100%** (13/13) |
| `plan_completo` | 100% (2/2) | **100%** (2/2) |
| `sin_texto_prohibido` | 92.3% | **100%** |
| `escala_cuando_debe` | 50% | **100%** |
| Costo de la corrida | $0.2667 | $0.2641 |

**`plan_completo` al 100% es lo que justifica el cambio de arquitectura**: los dos guiones que
traen dos pedidos en un mismo mensaje se atendieron enteros, en el orden correcto. Con el router
anterior, uno de los dos pedidos se perdía.

#### Los tres defectos que encontró la v1, y que ninguna prueba de contrato veía

El experimento no falló por el modelo: falló por tres errores nuestros, los tres en el código
nuevo del orquestador.

1. **El agente escalaba en el primer turno.** La decisión del equipo era escalar *después* de
   pedir nombre y teléfono, y estaba escrita en el dataset y en este README — pero **no en el
   prompt**. Que la v1 anterior pasara al 100% fue suerte. Ahora la regla 4 de `PROMPT_RESERVAS`
   dice el orden explícitamente.
2. **Se abrían dos tickets para el mismo caso.** El escalamiento ocurre en dos turnos, así que la
   señal venía levantada en los dos y `_nodo_cierre` creaba una tarjeta cada vez. El *staff*
   habría recibido el mismo grupo por duplicado. Ahora un hilo escala una sola vez
   (`_escalar`), y el dato del segundo turno entra como **nota en la tarjeta que ya existe** —
   que es para lo que sirve `comentar_ticket`, la cuarta herramienta del servidor MCP.
3. **El cierre pegaba una frase que repetía lo que el agente ya había dicho.** El cliente leía la
   promesa dos veces en el mismo mensaje. Ahora solo se agrega el código, y únicamente si el
   agente no lo mencionó.

Y un cuarto, en el propio dataset: `no_debe_contener` incluía la palabra suelta **"confirmada"**,
que marcaba como fallo la respuesta **correcta** — el agente tiene que decir que la mesa *todavía
no está confirmada*, y esa frase contiene la palabra. Se cambió por frases completas que solo
pueden aparecer en una respuesta equivocada.

> Los cuatro tienen la misma forma: **una decisión que vivía en la documentación y no en el
> código**, o una comprobación que medía la letra en vez de la intención. Es exactamente lo que
> una evaluación sirve para encontrar, y ninguna de las 60 pruebas de contrato podía verlo.

### El giro de arquitectura del 2026-09-07 (asesoría con Boris)

Los números de la sección “Estado medido al cierre del 2026-09-07” corresponden a la
arquitectura **anterior**: tres agentes y un router. La sección “Primera medición de la
arquitectura nueva” y los reportes fechados el 2026-09-09 corresponden al orquestador actual.
Se conservan ambas mediciones para no mezclar resultados de versiones distintas.

Qué cambió, y qué se espera de cada cambio:

| Cambio | Efecto esperado en las métricas |
|---|---|
| El agente de Conocimiento desaparece; el orquestador responde información | menos latencia y menos tokens en las consultas de información: se ahorra la llamada de clasificación separada |
| El planificador puede devolver dos pasos | `plan_completo` pasa a existir; `incidencias-gana-sobre-reserva` deja de perder la reserva |
| `escalar_a_staff` ya no abre el ticket | el ticket queda con el turno completo adentro, no solo con el motivo |
| Los tickets van a Trello, por MCP | por primera vez una persona **recibe** el aviso; antes la promesa del agente no la cumplía nadie. Y el cierre pasa a ser estructuralmente imposible para el agente: el servidor no publica esa herramienta |
| `VOZ_CLEMENTE` recortado y la ficha del cliente con su instrucción pegada | menos tokens por turno, sobre todo con clientes nuevos (sin ficha) |

Lo que **no** cambió y sigue valiendo: los hallazgos del RAG (`bge-m3` contra `nomic-embed-text`),
el sesgo del juez, y las tres correcciones de instrumentación de la sección anterior. Esos eran
problemas de medición, no de arquitectura.

**Estado de verificación al 2026-09-10:**

1. Los 126 casos locales (113 funciones) cubren el plan, el encadenamiento, el punto único de salida, MCP,
   autorización, HIL, PII, Guardrails AI y los estados visuales del webchat.
2. El experimento de LangSmith de la arquitectura nueva quedó registrado como antecedente.
3. La evaluación funcional se repitió con DeepEval/GEval, usando `gpt-5.6-terra` como objetivo
   y `claude-sonnet-5` como juez. Los resultados están en
   [`docs/EVALUACION_FUNCIONAL_LLM_JUDGE.md`](docs/EVALUACION_FUNCIONAL_LLM_JUDGE.md).
4. DeepTeam ejecutó 24 escenarios contra Clemente. La implementación y las salvedades están en
   [`docs/EVALUACION_TECNICA_SEGURIDAD_MULTIAGENTE.md`](docs/EVALUACION_TECNICA_SEGURIDAD_MULTIAGENTE.md).
5. Trello se validó por MCP mediante creación, consulta y comentario de una tarjeta real; véase
   [`docs/VALIDACION_INTEGRACION_TRELLO.md`](docs/VALIDACION_INTEGRACION_TRELLO.md).
6. Quedan como ampliaciones una muestra mayor, la evaluación completa de cada paso en planes
   compuestos y repeticiones para medir variabilidad entre corridas y modelos.
7. El webchat muestra insignias de seguridad y revisión; el panel interno permite al personal
   consultar, aprobar y rechazar interrupciones HIL con su token exclusivo.

## 12. Estructura del repositorio

### 12.1 Si buscas… está aquí

| Busco… | Archivo |
|---|---|
| **Los *prompts*** (orquestador y los dos agentes) | `app/agentes/prompts.py` |
| **Los datos fijos del restaurante** que el orquestador sabe de memoria | `FICHA_DEL_RESTAURANTE` en `app/agentes/prompts.py` |
| **El catálogo del restaurante** (horarios, carta, políticas) | `app/agentes/rag/documentos/*.md` — **3 archivos, versionados en git** |
| **Las herramientas de cada agente** | `app/agentes/tools/{reservas,incidencias,catalogo}_tools.py` |
| **El orquestador respondiendo por sí mismo** (*proxy*) | `app/orquestador/informacion.py` |
| **El plan de resolución** (grafo y *prompt* del planificador) | `app/orquestador/grafo.py` |
| **Dónde se abre el ticket de escalamiento** | `_nodo_cierre` en `app/orquestador/grafo.py` |
| **El servidor MCP de tickets** (y el límite de permisos) | `app/incidencias/mcp_trello.py` |
| **El cliente MCP** que usan las tools del agente | `app/incidencias/servicio_mcp.py` |
| **La integración directa con Trello** (respaldo, sin MCP) | `app/incidencias/servicio_trello.py` |
| **El dataset de evaluación** | `tests/eval/casos.json` |
| **Los criterios de "buena respuesta"** | `tests/eval/metricas.py` |
| **Lo que pidió el docente y por qué** | documento externo `ASESORIA_01_BORIS_ACUERDOS.md` |
| **La transcripción de la asesoría** | documento externo `ASESORIA_01_BORIS_TRANSCRIPCION.md` |
| **Quién califica en las evaluaciones** | `tests/eval/juez.py` |
| **Los ataques de seguridad** | `tests/seguridad/red_team_reservas.py` |
| **La comparación de modelos** (costo, velocidad) | `tests/eval/banco_modelos.py` |
| **Qué modelo se usa, cómo se resuelve y cuánto cuesta** | `app/llm.py` (`PRECIOS_POR_MILLON`) |
| **Los contratos entre módulos** | `app/contratos.py` |
| **Las reglas de negocio codificadas** | `app/reservas/servicio_json.py` y `app/reservas/datos/mesas.json` |
| **El texto de las conversaciones reales** | `app/observabilidad/datos/conversaciones.jsonl` |
| **La memoria de largo plazo del cliente** | `app/agentes/memoria.py` + `app/agentes/datos/clientes.json` |
| **Los guardrails de PII** | `app/seguridad/pii.py` |
| **La conexión con Guardrails AI** | `app/seguridad/guardrails_ai.py` y `guardrails_service/` |
| **La cola y reanudación HITL** | `app/orquestador/grafo.py` y el panel en `app/web/templates/chat.html` |

### 12.2 El árbol completo

```
clemente/
  run.py                          punto de entrada del servidor Flask
  studio.py                       punto de entrada para LangGraph Studio
  mcp_server.py                   punto de entrada del servidor MCP para
                                  `fastmcp inspect` y el MCP Inspector
  langgraph.json                  manifiesto de la aplicación LangGraph
  pyproject.toml                  metadatos del paquete (los necesita langgraph-cli)
  requirements.txt                dependencias del proyecto        <- compartido
  requirements-dev.txt            langgraph-cli, deepeval, deepteam, sentry-sdk
  .env.example                    plantilla de configuración       <- compartido
  README.md                       este documento
  ACUERDOS_EQUIPO.md              reglas de trabajo y decisiones del equipo

  guardrails_service/             servicio aislado Guardrails AI
    app.py                        jailbreak + toxicidad de entrada y salida
    requirements.txt             dependencias aisladas del servicio
    README.md                     instalación y operación

  app/
    __init__.py                   create_app(): fábrica de la app + blueprints
    config.py                     configuración leída del .env     <- compartido
    llm.py                        resolución de modelo y embeddings <- compartido
    contratos.py                  costuras entre módulos           <- compartido

    seguridad/
      pii.py                      bloqueo/redacción de PII y PIIMiddleware
      guardrails_ai.py            adaptador HTTP de entrada y salida

    communication/                canales y controles compartidos
      controllers/                chat, WhatsApp y revision humana del personal
      routes/__init__.py          registro de endpoints
      services/chat_service.py    PII, entrada, orquestador, salida e historial
      services/message_service.py Postgres y flujo protegido de WhatsApp
      services/sesiones.py        historial acotado en memoria

    orquestador/                  ── CHRISTIAN, JEAN ────────────────────────
      grafo.py                    grafo LangGraph: planificador, pasos y cierre
      informacion.py              el orquestador respondiendo por sí mismo
                                  (proxy de información del restaurante)

    agentes/                      ── CHRISTIAN, JEAN ────────────────────────
      __init__.py                 registro AGENTES: nombre -> responder()
      prompts.py                  LOS PROMPTS DE SISTEMA + la ficha fija del
                                  restaurante que el orquestador sabe de memoria
      base.py                     construcción, ejecución, ficha del cliente
                                  y guardrail de salida — comunes a todos
      contexto.py                 ContextoConversacion: sesión hacia las tools,
                                  escalado y datos de vuelta al orquestador
      memoria.py                  memoria de largo plazo: perfil por teléfono
      reservas.py                 Agente de Reservas y Capacidad
      incidencias.py              Agente de Incidencias y Experiencia
                                  (customer care)
      datos/clientes.json         perfiles de clientes            (generado)
      tools/
        __init__.py               decorador con_traza: cronometra cada tool
        reservas_tools.py         7 tools: disponibilidad, crear, buscar por
                                  teléfono o por código, modificar, cancelar,
                                  escalar al staff (que ya NO abre el ticket:
                                  solo levanta la mano para el orquestador)
        incidencias_tools.py      3 tools: registrar, consultar, verificar la
                                  reserva del reclamo
        catalogo_tools.py         2 tools de LECTURA: buscar_en_catalogo y
                                  consultar_politica. Las usa el orquestador;
                                  `consultar_politica` la comparten los agentes
      rag/
        indice.py                 índice Chroma: chunking, indexado y búsqueda
        documentos/               EL CATÁLOGO VALIDADO — fuente única de verdad
          01_horarios_y_ubicacion.md   horarios, dirección, estacionamiento,
                                       accesibilidad, zonas del local
          02_carta_y_servicios.md      carta, opciones vegetarianas y veganas,
                                       alergias, servicios
          03_politicas.md              reservas, cancelaciones, reclamos y
                                       compensaciones, datos personales
        chroma_index/             índice vectorial                (generado)

    reservas/                     ── MIGUEL ─────────────────────────────────
      servicio_json.py            gestor de reservas de referencia
      datos/mesas.json            mesas y zonas declaradas por la operación
      datos/reservas.json         reservas                        (generado)

    incidencias/                  registro de incidencias (provisional, C+J)
      __init__.py                 elige backend: mcp / trello / json
      mcp_trello.py               SERVIDOR MCP de tickets (Sesión 16). Publica 4
                                  herramientas y NINGUNA de cierre: ahí vive el
                                  límite de permisos del agente
      servicio_mcp.py             cliente MCP — el camino por defecto
      servicio_json.py            registro local — garantiza que nada se pierda
      servicio_trello.py          API de Trello: persistencia, seguimiento y
                                  NOTIFICACIÓN al staff (Acuerdo 4)
      datos/incidencias.json                                      (generado)

    observabilidad/               ── ADRIÁN ─────────────────────────────────
      trazas.py                   eventos, métricas, LangSmith y el registro
                                  de conversaciones en disco
      rutas.py                    GET /api/salud, /trazas, /metricas,
                                  /conversaciones
      datos/conversaciones.jsonl  texto de cada turno             (generado)

    web/
      templates/chat.html         webchat, insignias de seguridad y panel HITL
      static/img/                 foto de la sala + LEEME.md

  tests/                          126 casos / 113 funciones — NO llaman al modelo
    conftest.py                   fixtures compartidas
    test_api.py                   endpoints HTTP y contratos de respuesta
    test_reservas.py              reglas del gestor de reservas
    test_incidencias.py           registro de incidencias y plazos
    test_guardrails.py            guardrail de salida, contexto, memoria de
                                  largo plazo y turno sin texto
    test_guardrails_ai.py         adapter, fallos, bloqueos y métricas del framework
    test_pii.py                   secretos, redacción y protección de trazas
    test_orquestador.py           el plan, el encadenamiento de dos agentes y
                                  el punto único de salida
    test_mcp.py                   el servidor MCP: que publique lo que debe y,
                                  sobre todo, que NO publique el cierre
    test_llm.py                   resolución de modelo, y que el juez sea el
                                  modelo que dice ser; el plan en el registro

    eval/                         EVALUACIÓN — esto sí cuesta (sección 10)
      casos.json                  el dataset: 13 guiones, 17 turnos
      juez.py                     el modelo que califica (DeepEvalBaseLLM)
      metricas.py                 métricas GEval + ContextualPrecisionMetric
      evaluar.py                  ruteo y verificación por texto
      deepeval_evaluar.py         juicio con LLM de los límites de cada agente
      deepeval_rag.py             calidad del recuperador del RAG
      langsmith_experimento.py    el dataset como experimento comparable
      banco_modelos.py            costo, velocidad y ruteo de cada modelo,
                                  Anthropic contra OpenAI, sobre el mismo dataset
      resultados/                 informes .json y .md            (generado)

    seguridad/                    RED TEAMING — leer LEEME.md antes
      LEEME.md                    aviso ético y legal de la Sesión 23
      red_team_reservas.py        DeepTeam + mapa OWASP Top 10 LLM
      deepteam-results/           ataques que funcionaron   (generado, sensible)
```

**(generado)** = no se versiona, está en el `.gitignore`. El catálogo del RAG **sí** se versiona:
es la fuente de verdad del restaurante y su historial de cambios importa.

## 13. Documentos del proyecto

**Dentro de `Clemente_Multiagente/`**

| Documento | Qué contiene |
|---|---|
| [`README.md`](README.md) | este archivo: arquitectura, puesta en marcha, comandos, evaluación |
| [`ACUERDOS_EQUIPO.md`](ACUERDOS_EQUIPO.md) | registro histórico del reparto de frentes, reglas de ramas y acuerdos iniciales |
| [`tests/seguridad/LEEME.md`](tests/seguridad/LEEME.md) | aviso ético del *red teaming* |
| [`app/web/static/img/LEEME.md`](app/web/static/img/LEEME.md) | cómo reemplazar la foto del webchat |
| [`docs/EVALUACION_TECNICA_SEGURIDAD_MULTIAGENTE.md`](docs/EVALUACION_TECNICA_SEGURIDAD_MULTIAGENTE.md) | implementación, ejecución y auditoría de DeepTeam |
| [`docs/EVALUACION_FUNCIONAL_LLM_JUDGE.md`](docs/EVALUACION_FUNCIONAL_LLM_JUDGE.md) | resultados de la evaluación funcional con DeepEval/GEval |
| [`docs/EVALUACION_TECNICA_FUNCIONAL_LLM_COMO_JUEZ.md`](docs/EVALUACION_TECNICA_FUNCIONAL_LLM_COMO_JUEZ.md) | diseño técnico del LLM como juez |
| [`docs/VALIDACION_INTEGRACION_TRELLO.md`](docs/VALIDACION_INTEGRACION_TRELLO.md) | evidencia de la prueba real de Trello por MCP |
| [`docs/AI_POLICY.md`](docs/AI_POLICY.md) | declaración de transparencia sobre uso de IA en el desarrollo (herramientas, tareas, verificación, límites) |
| [`docs/ETICA_Y_PRINCIPIOS_OPERATIVOS.md`](docs/ETICA_Y_PRINCIPIOS_OPERATIVOS.md) | 4 principios operativos (Sesión 24), clasificación bajo el D.S. N.º 115-2025-PCM y brechas declaradas (transparencia frente al cliente, equidad) |
| [`docs/TAREA_SESION_24_ETICA_CLEMENTE.md`](docs/TAREA_SESION_24_ETICA_CLEMENTE.md) | entregable académico de la tarea grupal: evaluación ética, 5 principios operativos, perfil del agente y brechas priorizadas |
| [`docs/REVISION_Y_CORRECCIONES_PASOS_1_3_2026-09-09.md`](docs/REVISION_Y_CORRECCIONES_PASOS_1_3_2026-09-09.md) | registro histórico de la integración y las correcciones iniciales |
| [`app/agentes/rag/documentos/01_horarios_y_ubicacion.md`](app/agentes/rag/documentos/01_horarios_y_ubicacion.md) | fuente de conocimiento del RAG sobre horarios, dirección y zonas del restaurante |
| [`app/agentes/rag/documentos/02_carta_y_servicios.md`](app/agentes/rag/documentos/02_carta_y_servicios.md) | fuente de conocimiento del RAG sobre carta, opciones alimentarias y servicios |
| [`app/agentes/rag/documentos/03_politicas.md`](app/agentes/rag/documentos/03_politicas.md) | fuente de conocimiento del RAG sobre reservas, cancelaciones, reclamos y datos personales |

**Documentos de contexto conservados fuera de este repositorio**

Los siguientes archivos pertenecen al material de trabajo del curso. No se incluyen en este
repositorio grupal y por eso se registran como referencias de texto, sin enlaces que GitHub no
pueda resolver.

| Documento | Qué contiene |
|---|---|
| `ASESORIA_01_BORIS_ACUERDOS.md` | **lo que pidió el docente el 2026-09-07**, con cita y minuto, y el plan de cambios |
| `ASESORIA_01_BORIS_TRANSCRIPCION.md` | la transcripción completa de esa asesoría, con marcas de tiempo |
| `BITACORA_AGENTES_Y_ORQUESTADOR.md` | **el registro día a día**: decisiones, errores y lecciones |
| `PRUEBA_DE_ESTRES_2026-09-06.md` | las 15 consultas del estrés, con el agente que atendió cada una |
| `AVANCE_AGENTES_PARA_JEAN.md` | resumen enviado a Jean y qué de su guía entró al código |
| `GUIA_IMPLEMENTACION_AGENTES_JEAN.md` | la guía de diseño que escribió Jean |
| `../Entregable N° 01 - GRUPO 02.docx` | definición del problema y de los tres agentes |
| `../../Idea - Clemente para Restaurantes Caso de Estudio.md` | caso de estudio original |
