"""
Metricas de calidad de Clemente -- Sesion 22 (Evaluacion Comparativa).

Aqui viven las metricas de juicio, separadas del script que las corre, por la
misma razon por la que los prompts viven en `app/agentes/prompts.py`: son el
criterio de lo que consideramos una buena respuesta, y ese criterio se discute,
se versiona y se cita en el informe.

Dos familias:

* **GEval** -- juicio con LLM sobre reglas que no se pueden verificar con una
  busqueda de texto. Nuestro evaluador anterior (`evaluar.py`) compara cadenas:
  detecta "descuento" pero se le escapa "algo le vamos a compensar". GEval si
  lo entiende, porque razona sobre el significado.
* **ContextualPrecisionMetric** -- metrica de RAG lista para usar. Mide si los
  fragmentos que recupero Chroma que SI son relevantes quedaron arriba en el
  ranking. Es la metrica del recuperador, no del redactor.

Una desviacion respecto del laboratorio de la sesion, dicha en voz alta: el
laboratorio usa `criteria=` (una frase libre) y aqui se usa `evaluation_steps=`
(pasos explicitos). Las dos son de DeepEval; los pasos dan resultados mas
estables entre corridas, que es lo que necesitamos para comparar antes y despues
de tocar un prompt. Donde el criterio es de matiz, se deja `criteria=`.

Todas las metricas reciben el juez de `juez.py`, porque DeepEval usaria GPT-4 y
el proyecto corre sobre Anthropic.
"""

from .juez import construir_juez

# Umbral de aprobacion. 0.8 es exigente a proposito en las dos metricas de
# limite: prometer una mesa que no existe o insinuar una compensacion son
# errores que llegan al cliente y cuestan dinero real al restaurante.
UMBRAL_ESTRICTO = 0.8
UMBRAL_NORMAL = 0.7


def _rubrica(mal: str, regular: str, bien: str):
    """
    Escala explicita para GEval, de 0 a 10.

    Corregido el 2026-09-07. La primera version metia la escala DENTRO de los
    pasos de evaluacion ("puntua 1.0 si..., 0.0 si..."), y el resultado fue una
    metrica invalida: el juez razonaba correctamente -- "no hay ninguna promesa
    sin respaldo" -- y aun asi devolvia 0.10. Razonamiento y puntaje quedaban
    desacoplados.

    El parametro `rubric` es el mecanismo que DeepEval trae para esto: los pasos
    describen QUE mirar y la rubrica define COMO puntuarlo. No se mezclan.
    """
    from deepeval.metrics.g_eval.g_eval import Rubric

    return [
        Rubric(score_range=(0, 3), expected_outcome=mal),
        Rubric(score_range=(4, 7), expected_outcome=regular),
        Rubric(score_range=(8, 10), expected_outcome=bien),
    ]


def metrica_no_promete_de_mas(juez=None):
    """
    El limite del Agente de Reservas: nunca comprometer capacidad sin haberla
    consultado. Es el error mas caro del sistema -- termina en un cliente
    parado en la puerta del restaurante un sabado a las 20:00.
    """
    from deepeval.metrics import GEval
    from deepeval.test_case import LLMTestCaseParams

    return GEval(
        name="No promete lo que no puede cumplir",
        evaluation_steps=[
            "Mira primero las herramientas que se llamaron. Si aparece "
            "`consultar_disponibilidad`, la afirmacion sobre si hay mesa SI esta "
            "respaldada: el agente consulto el sistema antes de responder.",
            "Busca en la respuesta toda afirmacion sobre disponibilidad de mesa, "
            "confirmacion de una reserva, horario o capacidad del local.",
            "Es una falta afirmar o negar que hay mesa para una fecha y hora "
            "concretas SIN que se haya llamado a `consultar_disponibilidad`.",
            "Es una falta dar por confirmada una reserva nueva sin un codigo "
            "(formato R-XXXXXX) y sin confirmacion explicita del cliente.",
            "Es una falta prometer como garantizado algo que depende de terceros: "
            "una zona concreta, un horario especial, atender a un grupo grande.",
            "NO es una falta consultar, pedir los datos que faltan, derivar al equipo "
            "del restaurante, ni informar sobre reservas YA existentes que tienen su "
            "codigo: eso es exactamente lo que debe hacer.",
        ],
        rubric=_rubrica(
            mal="La respuesta compromete capacidad del local sin verificarla: afirma que "
                "hay mesa sin consultar, o da por cerrada una reserva que no lo esta.",
            regular="No compromete capacidad, pero deja al cliente con una expectativa "
                    "ambigua sobre si algo quedo asegurado o no.",
            bien="Toda afirmacion sobre disponibilidad o reservas esta respaldada por una "
                 "consulta o por un codigo existente, o bien el agente pide lo que falta "
                 "y deriva sin prometer nada.",
        ),
        evaluation_params=[
            LLMTestCaseParams.INPUT,
            LLMTestCaseParams.ACTUAL_OUTPUT,
            # Sin esto el juez no puede saber si la tool se llamo, y penaliza
            # respuestas correctas por algo que no tiene forma de observar.
            LLMTestCaseParams.TOOLS_CALLED,
        ],
        model=juez or construir_juez(),
        threshold=UMBRAL_ESTRICTO,
    )


def metrica_no_ofrece_compensacion(juez=None):
    """
    El limite del Agente de Incidencias: registra el reclamo, no lo resuelve.
    Decidir una compensacion es una facultad del restaurante, no del asistente.

    Esta metrica existe porque la verificacion por palabras no alcanza: capta
    "descuento" y "cortesia", pero no "algo vamos a hacer por usted", que para
    el cliente significa exactamente lo mismo.
    """
    from deepeval.metrics import GEval
    from deepeval.test_case import LLMTestCaseParams

    return GEval(
        name="No ofrece compensacion",
        evaluation_steps=[
            "Busca en la respuesta cualquier ofrecimiento de beneficio al cliente: "
            "descuento, cortesia, plato o bebida gratis, invitacion, promocion, "
            "devolucion, o una insinuacion equivalente como 'algo vamos a hacer por "
            "usted' o 'lo vamos a compensar'.",
            "Un ofrecimiento cuenta aunque sea condicional, vago o presentado como una "
            "posibilidad: para el cliente sigue siendo una promesa.",
            "NO es una falta reconocer lo ocurrido, disculparse, registrar el reclamo, "
            "dar un codigo de incidencia o indicar un plazo de respuesta.",
            "NO es una falta decir que una persona del restaurante revisara el caso.",
        ],
        rubric=_rubrica(
            mal="Ofrece un beneficio concreto al cliente: descuento, cortesia, algo gratis "
                "o una devolucion.",
            regular="No ofrece nada concreto pero insinua que habra una compensacion, "
                    "dejando al cliente esperando algo.",
            bien="Reconoce lo ocurrido y registra el caso sin ofrecer ni insinuar ningun "
                 "beneficio; la decision queda en manos del restaurante.",
        ),
        evaluation_params=[LLMTestCaseParams.ACTUAL_OUTPUT],
        model=juez or construir_juez(),
        threshold=UMBRAL_ESTRICTO,
    )


def metrica_fiel_al_catalogo(juez=None):
    """
    El limite del Agente de Conocimiento: responder solo desde el catalogo
    validado. Es la regresion directa del 2026-09-03, cuando el modelo local
    invento que el estacionamiento era "en la calle principal, gratuito".

    Compara la respuesta contra los fragmentos que el RAG realmente recupero,
    no contra el conocimiento general del juez.
    """
    from deepeval.metrics import GEval
    from deepeval.test_case import LLMTestCaseParams

    return GEval(
        name="Fiel al catalogo",
        evaluation_steps=[
            "Compara cada dato concreto de la respuesta -- horarios, direcciones, "
            "precios, platos, condiciones, plazos -- contra el contexto recuperado.",
            "Es una falta todo dato que no aparezca en el contexto, aunque suene "
            "plausible o sea cierto en el mundo real.",
            "Es una falta contradecir el contexto.",
            "NO es una falta decir que el catalogo no cubre la pregunta y ofrecer "
            "consultarlo con el equipo: esa es la respuesta correcta cuando falta "
            "el dato.",
        ],
        rubric=_rubrica(
            mal="Afirma datos del restaurante que no estan en el contexto recuperado, o lo "
                "contradice.",
            regular="Todo lo que dice esta en el contexto, pero lo interpreta o lo amplia "
                    "mas alla de lo que el catalogo respalda.",
            bien="Cada dato concreto sale del contexto recuperado; si algo no esta, lo dice "
                 "en vez de completarlo.",
        ),
        evaluation_params=[
            LLMTestCaseParams.INPUT,
            LLMTestCaseParams.ACTUAL_OUTPUT,
            LLMTestCaseParams.RETRIEVAL_CONTEXT,
        ],
        model=juez or construir_juez(),
        threshold=UMBRAL_ESTRICTO,
    )


def metrica_tono_clemente(juez=None):
    """
    Metrica de matiz, no de limite: aqui `criteria=` en texto libre funciona
    mejor que una lista de pasos, igual que en el laboratorio de la sesion.
    """
    from deepeval.metrics import GEval
    from deepeval.test_case import LLMTestCaseParams

    return GEval(
        name="Voz de Clemente",
        criteria=(
            "Evalua si la respuesta suena a una persona del restaurante escribiendo "
            "por chat: espanol peruano, cordial y directo, dos o tres frases. "
            "Penaliza que se presente como asistente virtual o modelo de lenguaje, "
            "que mencione 'agentes', 'sistema' o 'herramientas', que hable de otro "
            "agente o corrija respuestas anteriores, y que se extienda de mas. "
            "El canal real es WhatsApp: las listas con vinetas y el texto en negrita "
            "de Markdown delatan que no escribe una persona. "
            "Para el cliente hay una sola conversacion con una sola persona."
        ),
        rubric=_rubrica(
            mal="Se presenta como asistente virtual, menciona agentes o herramientas, o "
                "corrige lo que dijo antes: el cliente nota que habla con un sistema.",
            regular="El tono es correcto pero el formato no es de chat: listas con vinetas, "
                    "negritas o una respuesta mucho mas larga de tres frases.",
            bien="Suena a una persona del restaurante escribiendo por WhatsApp: corto, "
                 "cordial, directo y sin formato de documento.",
        ),
        evaluation_params=[LLMTestCaseParams.ACTUAL_OUTPUT],
        model=juez or construir_juez(),
        threshold=UMBRAL_NORMAL,
    )


def metrica_precision_contextual(juez=None):
    """
    Calidad del recuperador del RAG (`ContextualPrecisionMetric`).

    Mide si los fragmentos relevantes quedaron ARRIBA en el ranking de Chroma.
    Es la metrica que dice si el *chunking* por encabezado que adoptamos el
    2026-09-06 sirvio de algo, y la unica que evalua el buscador en vez del
    redactor. Necesita `expected_output` en el caso de prueba.
    """
    from deepeval.metrics import ContextualPrecisionMetric

    return ContextualPrecisionMetric(
        threshold=UMBRAL_NORMAL,
        model=juez or construir_juez(),
        include_reason=True,
    )


# Que metrica se le aplica a cada agente. Aplicarlas todas a todo seria pagar
# de mas: al Agente de Conocimiento no le corresponde que se le mida si promete
# mesas, porque no puede reservar.
METRICAS_POR_AGENTE = {
    "reservas": ["No promete lo que no puede cumplir", "Voz de Clemente"],
    "incidencias": ["No ofrece compensacion", "Voz de Clemente"],
    "informacion": ["Fiel al catalogo", "Voz de Clemente"],
}


def construir_metricas(juez=None) -> dict:
    """Todas las metricas de juicio, indexadas por nombre. Un solo juez para todas."""
    juez = juez or construir_juez()
    metricas = [
        metrica_no_promete_de_mas(juez),
        metrica_no_ofrece_compensacion(juez),
        metrica_fiel_al_catalogo(juez),
        metrica_tono_clemente(juez),
    ]
    return {metrica.name: metrica for metrica in metricas}
