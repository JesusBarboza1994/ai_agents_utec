"""
Evaluador LangSmith para el agente Clemente
Proyecto Clemente - UTEC / Diseño e Implementación de Agentes IA - Grupo 02

Sube el dataset de casos de prueba a LangSmith, corre el agente sobre cada
caso y lo evalúa con:
  - Las 9 métricas custom de reglas de negocio (Fidelidad de Disponibilidad,
    Confirmación Explícita, Manejo de Incidencias, etc.) como LLM-as-judge propios
    (gpt-5.6-luna, structured output). Estas métricas viven SOLO aquí, no en
    evaluador_deepeval.py, para no evaluar dos veces el mismo criterio con dos
    prompts distintos — ver METRICAS_EVALUACION.md sección 4.
  - Un evaluador determinístico de enrutamiento (¿usó la herramienta correcta
    para la categoría del mensaje?).

Las métricas PREDEFINIDAS de DeepEval (seguridad, uso de herramientas) se evalúan por
separado en evaluador_deepeval.py.

El juez usa gpt-5.6-luna, el deployment de Azure del agente real de este
proyecto, a través de `../modelo_juez.py`, en vez del DeepSeek de la versión
original de la tarea grupal.

Adaptado para correr contra el agente REAL de este proyecto
(`app.orquestador.responder`), no contra el agente de juguete sobre DeepSeek de
la tarea grupal original. Las herramientas usadas se leen de las trazas reales
(`app.observabilidad.trazas`), no de los mensajes de un grafo de LangGraph
propio como en la version original.

Uso (desde la raíz del proyecto):
    python tests/evals/langsmith/evaluador_langsmith.py
"""

import json
import sys
import uuid
from datetime import datetime
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[3]
COMPARTIDOS = Path(__file__).resolve().parent.parent
for ruta in (RAIZ, COMPARTIDOS):
    if str(ruta) not in sys.path:
        sys.path.insert(0, str(ruta))

from pydantic import BaseModel, Field
from langsmith import Client

from dataset_casos import CASOS
from modelo_juez import chat_gpt_luna

from app.contratos import MensajeEntrante
from app.observabilidad.trazas import ultimas_trazas
from app.orquestador import responder

NOMBRE_DATASET = "clemente-casos-prueba"

client = Client()


# ============================================================================
# DATASET
# ============================================================================

def crear_o_recuperar_dataset() -> str:
    if client.has_dataset(dataset_name=NOMBRE_DATASET):
        dataset = client.read_dataset(dataset_name=NOMBRE_DATASET)
        client.delete_dataset(dataset_id=dataset.id)

    dataset = client.create_dataset(
        dataset_name=NOMBRE_DATASET,
        description="Casos de prueba del agente Clemente (reservas, incidencias, informacion) "
                     "derivados del documento de propuesta del Proyecto Clemente.",
    )
    client.create_examples(
        dataset_id=dataset.id,
        inputs=[{"mensaje": c["input"]} for c in CASOS],
        outputs=[
            {"categoria": c["categoria"], "riesgo": c["riesgo"], "referencia": c["referencia"]}
            for c in CASOS
        ],
    )
    return dataset.id


# ============================================================================
# TARGET: EJECUTAR EL AGENTE
# ============================================================================

def ejecutar_agente(inputs: dict) -> dict:
    """
    Corre el mensaje contra el orquestador real. Cada caso usa una sesion
    nueva porque son casos sueltos (sin hilo previo), a diferencia de los
    guiones multi-turno de `tests/eval/casos.json`.
    """
    mensaje = inputs["mensaje"]
    sesion = f"langsmith-utec-{uuid.uuid4().hex[:8]}"
    antes = len(ultimas_trazas(limite=200, sesion_id=sesion))
    respuesta = responder(MensajeEntrante(sesion_id=sesion, texto=mensaje, canal="eval"))
    herramientas_usadas = [
        t.detalle.get("tool", "desconocida")
        for t in ultimas_trazas(limite=200, sesion_id=sesion)[antes:]
        if t.evento == "tool"
    ]
    return {"respuesta": respuesta.texto, "herramientas_usadas": herramientas_usadas}


# ============================================================================
# EVALUADORES LLM-AS-JUDGE (gpt-5.6-luna, igual que el agente real)
# ============================================================================

class JuicioLLM(BaseModel):
    score: float = Field(description="Puntuación entre 0.0 (incumple) y 1.0 (cumple perfectamente)")
    razon: str = Field(description="Justificación breve en español, 1-2 frases")


JUEZ_ESTRUCTURADO = chat_gpt_luna(temperature=0.0).with_structured_output(
    JuicioLLM, method="function_calling"
)

CRITERIOS = {
    "fidelidad_disponibilidad": (
        {"reservas"},
        "El agente nunca afirma ni niega disponibilidad de mesas sin haberla verificado, "
        "y no inventa cupos que no existen.",
    ),
    "confirmacion_explicita": (
        {"reservas"},
        "El agente solo confirma o crea una reserva cuando el cliente ya dio confirmación "
        "explícita de fecha, hora, personas y nombre; si no, pide confirmación primero.",
    ),
    "escalamiento_correcto": (
        {"reservas", "informacion"},
        "Ante un caso que excede lo que el agente puede resolver solo (grupos muy grandes, "
        "conflictos, temas fuera de catálogo), el agente indica que escala a una persona del "
        "staff en vez de inventar una solución.",
    ),
    "manejo_incidencias": (
        {"incidencias"},
        "Frente a una queja, el agente reconoce lo ocurrido sin minimizar ni poner excusas, "
        "y registra el caso pidiendo solo el dato que falte.",
    ),
    "no_compensacion_no_aprobada": (
        {"incidencias"},
        "El agente evita ofrecer, prometer u otorgar descuentos o compensaciones como "
        "respuesta directa a una queja; como máximo dice que el staff evaluará el caso.",
    ),
    "no_cierre_prematuro": (
        {"incidencias"},
        "El agente evita dar por cerrado un caso de incidencia solo porque el cliente le resta "
        "importancia o la conversación parece terminar.",
    ),
    "fidelidad_catalogo": (
        {"informacion"},
        "La información entregada (horarios, ubicación, políticas, carta, servicios) "
        "corresponde exactamente al catálogo validado, sin inventar datos; si el tema no está "
        "en el catálogo, el agente lo dice en vez de aproximar una respuesta.",
    ),
    "tono_profesional": (
        {"reservas", "incidencias", "informacion"},
        "El tono es profesional, cordial y empático, sin atribuir culpas a empleados "
        "específicos ni comentar procesos internos del restaurante.",
    ),
}


def crear_evaluador_llm(nombre_metrica: str, categorias_aplicables: set, criterio: str):
    def evaluador(inputs: dict, outputs: dict, reference_outputs: dict) -> dict:
        if reference_outputs.get("categoria") not in categorias_aplicables:
            # Métrica no aplica a la categoría de este caso: se deja constancia
            # sin puntuar, para no ensuciar el promedio con un 0 injustificado.
            return {"key": nombre_metrica, "comment": "No aplica a esta categoría de caso"}
        prompt = f"""Eres un evaluador experto de agentes conversacionales para restaurantes.

Criterio a evaluar:
{criterio}

Mensaje del cliente:
{inputs.get("mensaje")}

Respuesta del agente Clemente:
{outputs.get("respuesta")}

Herramientas que usó el agente: {outputs.get("herramientas_usadas")}

Comportamiento esperado (referencia del caso):
{reference_outputs.get("referencia")}

Evalúa SOLO el criterio indicado arriba y da una puntuación entre 0.0 y 1.0."""
        juicio = JUEZ_ESTRUCTURADO.invoke(prompt)
        return {"key": nombre_metrica, "score": juicio.score, "comment": juicio.razon}

    return evaluador


HERRAMIENTA_ESPERADA_POR_CATEGORIA = {
    "reservas": {
        "consultar_disponibilidad", "crear_reserva", "buscar_mis_reservas",
        "consultar_reserva_por_codigo", "modificar_reserva", "cancelar_reserva",
        "escalar_a_staff",
    },
    "incidencias": {"registrar_incidencia", "consultar_incidencia", "verificar_reserva_del_reclamo"},
    "informacion": {"buscar_en_catalogo", "consultar_politica"},
}


def enrutamiento_correcto(inputs: dict, outputs: dict, reference_outputs: dict) -> dict:
    categoria = reference_outputs.get("categoria")
    usadas = set(outputs.get("herramientas_usadas", []))
    esperadas = HERRAMIENTA_ESPERADA_POR_CATEGORIA.get(categoria, set())
    acierto = bool(usadas & esperadas)
    return {
        "key": "enrutamiento_correcto",
        "score": 1.0 if acierto else 0.0,
        "comment": f"Categoría={categoria}. Herramientas usadas={sorted(usadas) or 'ninguna'}. "
                   f"Esperadas={sorted(esperadas)}.",
    }


def construir_evaluadores():
    evaluadores = [
        crear_evaluador_llm(nombre, categorias, criterio)
        for nombre, (categorias, criterio) in CRITERIOS.items()
    ]
    evaluadores.append(enrutamiento_correcto)
    return evaluadores


# ============================================================================
# MAIN
# ============================================================================

def main():
    print("=" * 80)
    print("EVALUACIÓN DEL AGENTE CLEMENTE - LANGSMITH")
    print("=" * 80)

    from app.config import Config
    Config.desde_entorno()

    print("\nCreando/actualizando dataset en LangSmith...")
    dataset_id = crear_o_recuperar_dataset()
    print(f"Dataset listo: {NOMBRE_DATASET} ({dataset_id})")

    print("\nEjecutando evaluate()... esto puede tardar unos minutos.")
    resultados = client.evaluate(
        ejecutar_agente,
        data=NOMBRE_DATASET,
        evaluators=construir_evaluadores(),
        experiment_prefix="clemente",
        description="Evaluación del agente Clemente sobre reglas de reservas, "
                     "incidencias e informacion del documento de propuesta.",
        max_concurrency=2,
    )

    filas = list(resultados)
    experiment_name = getattr(resultados, "experiment_name", None)
    print(f"\nExperimento: {experiment_name}")
    print(f"Casos evaluados: {len(filas)}")

    # Guardar un resumen local además del dashboard de LangSmith
    ruta_reportes = Path(__file__).parent / "reportes"
    ruta_reportes.mkdir(exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    ruta_resumen = ruta_reportes / f"resumen_langsmith_{timestamp}.json"

    resumen = []
    urls_compartidas = []
    for fila in filas:
        run = fila["run"]
        feedback = {fb.key: fb.score for fb in (fila.get("evaluation_results", {}).get("results", []) or [])}
        resumen.append({
            "run_id": str(run.id),
            "inputs": run.inputs,
            "outputs": run.outputs,
            "feedback": feedback,
        })
        try:
            url = client.share_run(run.id)
            urls_compartidas.append(str(url))
        except Exception as e:
            print(f"  (no se pudo compartir el run {run.id}: {e})")

    ruta_resumen.write_text(
        json.dumps(
            {
                "experiment_name": experiment_name,
                "dataset": NOMBRE_DATASET,
                "resultados": resumen,
                "urls_publicas_de_ejemplo": urls_compartidas,
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    print(f"\nResumen local guardado en: {ruta_resumen}")
    if urls_compartidas:
        print("\nURLs públicas de ejemplo (para captura de pantalla sin necesidad de login):")
        for url in urls_compartidas[:3]:
            print(f"  - {url}")
    print(f"\nAbre el proyecto en LangSmith para ver el dashboard completo del experimento "
          f"'{experiment_name}'.")


if __name__ == "__main__":
    main()
