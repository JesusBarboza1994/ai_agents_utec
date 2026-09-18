"""
El dataset de Clemente como experimento de LangSmith -- Sesion 22.

Diferencia con `deepeval_evaluar.py`, que evalua lo mismo: DeepEval deja el
resultado en un archivo de esta maquina; LangSmith lo deja en la nube, con
historial. Eso permite lo que un archivo suelto no permite:

* **comparar corridas lado a lado** -- Sonnet contra Opus, o el mismo modelo
  antes y despues de tocar un prompt, sobre exactamente los mismos casos;
* que los cinco veamos el mismo resultado sin pasarnos archivos;
* que cada caso quede enlazado a su traza completa, con las llamadas a
  herramientas adentro.

Es la parte de "evaluacion comparativa" que le da nombre a la sesion.

    python -m tests.eval.langsmith_experimento --subir      # crea o actualiza el dataset
    python -m tests.eval.langsmith_experimento              # corre el experimento
    python -m tests.eval.langsmith_experimento --modelo claude-opus-5 --etiqueta opus

Cada guion es UN ejemplo, no un turno. Es a proposito: la mitad de nuestros
casos son conversaciones de varios turnos donde el turno 2 solo tiene sentido
despues del turno 1 (la regla de continuidad del enrutador). Partirlos en
ejemplos sueltos destruiria justo lo que queremos medir.
"""

import argparse
import json
import os
import sys
import uuid
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent.parent
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from app.llm import modelo_activo  # noqa: E402

CASOS = Path(__file__).parent / "casos.json"
# Dataset por defecto. Es el de la arquitectura ACTUAL (orquestador con plan);
# `clemente-guiones` quedo como registro historico de la etapa de router, con
# sus corridas, y no se toca: los experimentos viejos solo son comparables
# contra la version del dataset con la que corrieron.
#
# Se cambia con --dataset. Renombrar guiones en `casos.json` no borra los
# viejos de la nube, asi que un renombrado masivo pide dataset nuevo en vez de
# ensuciar el anterior con ejemplos huerfanos que ya nadie puede aprobar.
NOMBRE_DATASET = "clemente-orquestador"


# --------------------------------------------------------------------------
# El dataset
# --------------------------------------------------------------------------

def subir_dataset(client, nombre: str = NOMBRE_DATASET) -> str:
    """
    Sincroniza `casos.json` con el dataset de LangSmith.

    Agrega los guiones nuevos y **actualiza los que cambiaron**. Esto ultimo no
    estaba al principio y era un error: el 2026-09-07 se corrigio el guion del
    grupo grande de uno a dos turnos y la version vieja se quedo en la nube, asi
    que el experimento habria seguido midiendo contra un criterio ya descartado.

    Actualizar un ejemplo NO borra las corridas anteriores, pero si cambia el
    criterio contra el que se compararon. Por eso avisa en pantalla cual cambio:
    si un experimento viejo de pronto luce mejor o peor, hay que saber por que.
    """
    datos = json.loads(CASOS.read_text(encoding="utf-8"))
    guiones = datos["guiones"]

    existente = next((d for d in client.list_datasets(dataset_name=nombre)), None)
    if existente is None:
        dataset = client.create_dataset(
            dataset_name=nombre,
            description=datos.get("descripcion", "Guiones de evaluacion de Clemente"),
        )
        print(f"Dataset creado: {dataset.id}")
        en_la_nube = {}
    else:
        dataset = existente
        en_la_nube = {
            e.inputs.get("guion"): e for e in client.list_examples(dataset_id=dataset.id)
        }
        print(f"Dataset existente: {dataset.id} ({len(en_la_nube)} guiones dentro)")

    nuevos = actualizados = 0
    for guion in guiones:
        entradas = {"guion": guion["id"], "turnos": guion["turnos"],
                    "sesion_fija": guion.get("sesion_fija")}
        salidas = {"rutas_esperadas": [t["ruta_esperada"] for t in guion["turnos"]],
                   # Solo algunos turnos declaran plan completo: los que traen dos
                   # pedidos en un mismo mensaje. En los demas queda None y el
                   # evaluador de plan los saltea.
                   "planes_esperados": [t.get("plan_esperado") for t in guion["turnos"]],
                   "origen": guion.get("origen", "")}

        anterior = en_la_nube.get(guion["id"])
        if anterior is None:
            client.create_example(
                dataset_id=dataset.id, inputs=entradas, outputs=salidas,
                metadata={"origen": guion.get("origen", "")},
            )
            nuevos += 1
        elif anterior.inputs.get("turnos") != guion["turnos"]:
            client.update_example(anterior.id, inputs=entradas, outputs=salidas)
            actualizados += 1
            print(f"  actualizado: {guion['id']} "
                  f"({len(anterior.inputs.get('turnos', []))} -> {len(guion['turnos'])} turnos)")

    sin_cambios = len(guiones) - nuevos - actualizados
    print(f"{nuevos} nuevos, {actualizados} actualizados, {sin_cambios} sin cambios.")
    return str(dataset.id)


# --------------------------------------------------------------------------
# Lo que se evalua
# --------------------------------------------------------------------------

def clemente(inputs: dict) -> dict:
    """Replica un guion completo contra el sistema real y devuelve lo que hizo."""
    from app.contratos import MensajeEntrante
    from app.orquestador import responder

    sesion = inputs.get("sesion_fija") or f"ls-{uuid.uuid4().hex[:8]}"
    historial: list[dict] = []
    rutas, planes, respuestas, escalados = [], [], [], []

    for turno in inputs["turnos"]:
        salida = responder(
            MensajeEntrante(sesion_id=sesion, texto=turno["mensaje"], canal="eval"),
            historial=historial,
        )
        historial.append({"role": "user", "content": turno["mensaje"]})
        historial.append({"role": "assistant", "content": salida.texto})
        rutas.append(salida.agente)
        # El plan completo del turno: desde el 2026-09-07 un turno puede pasar por
        # dos agentes, y `salida.agente` solo dice con cual termino.
        planes.append(salida.datos.get("plan", [salida.agente]))
        respuestas.append(salida.texto)
        escalados.append(salida.escalado)

    return {"rutas": rutas, "planes": planes, "respuestas": respuestas, "escalados": escalados}


# --------------------------------------------------------------------------
# Evaluadores
#
# Mezcla deliberada, como en el laboratorio de la sesion: los deterministas son
# gratis, instantaneos y no discuten -- se usan siempre que la pregunta tenga
# una respuesta objetiva. El juez con LLM se reserva para lo que no se puede
# verificar con una comparacion de texto.
# --------------------------------------------------------------------------

def precision_de_ruteo(outputs: dict, reference_outputs: dict) -> dict:
    """
    Determinista. La metrica principal del orquestador.

    Cambio del 2026-09-07: la pregunta ya no es "fue exactamente ese agente y
    ninguno otro", sino "el alcance esperado se atendio en este turno". Un turno
    puede pasar por dos agentes desde que el orquestador planifica, y exigir
    igualdad exacta marcaria como error justamente el caso que veniamos de
    arreglar (el reclamo que ademas pide mesa).
    """
    planes = outputs.get("planes") or [[r] for r in outputs.get("rutas", [])]
    esperadas = reference_outputs.get("rutas_esperadas", [])
    if not esperadas:
        return {"key": "precision_de_ruteo", "score": None, "comment": "sin referencia"}
    aciertos = sum(e in p for p, e in zip(planes, esperadas))
    return {
        "key": "precision_de_ruteo",
        "score": aciertos / len(esperadas),
        "comment": f"{aciertos}/{len(esperadas)}  planes={planes} esperadas={esperadas}",
    }


def plan_completo(outputs: dict, reference_outputs: dict) -> dict:
    """
    Determinista. Solo mira los turnos que traen DOS pedidos en un mismo mensaje.

    Es la metrica que justifica el cambio de router a orquestador: si sale bajo,
    el sistema esta volviendo a perder la mitad de lo que el cliente pidio, y
    entonces toda la complejidad extra del plan no se esta pagando sola.
    """
    esperados = reference_outputs.get("planes_esperados") or []
    planes = outputs.get("planes") or []
    pares = [(p, e) for p, e in zip(planes, esperados) if e]
    if not pares:
        return {"key": "plan_completo", "score": None,
                "comment": "este guion no declara plan de varios pasos"}
    aciertos = sum(list(p) == list(e) for p, e in pares)
    return {
        "key": "plan_completo",
        "score": aciertos / len(pares),
        "comment": f"{aciertos}/{len(pares)}  obtenidos={[p for p, _ in pares]} "
                   f"esperados={[e for _, e in pares]}",
    }


def sin_texto_prohibido(inputs: dict, outputs: dict) -> dict:
    """
    Determinista. Verifica los `no_debe_contener` del guion -- las palabras que
    marcan una alucinacion conocida o una compensacion ofrecida de mas.
    """
    import unicodedata

    def normalizar(texto: str) -> str:
        """Convierte texto a minusculas y elimina marcas diacriticas para la comparacion."""
        sin_tildes = unicodedata.normalize("NFKD", texto.lower())
        return "".join(c for c in sin_tildes if not unicodedata.combining(c))

    encontrados = []
    for turno, respuesta in zip(inputs["turnos"], outputs.get("respuestas", [])):
        for prohibido in turno.get("no_debe_contener", []):
            if normalizar(prohibido) in normalizar(respuesta):
                encontrados.append(prohibido)

    return {
        "key": "sin_texto_prohibido",
        "score": 0.0 if encontrados else 1.0,
        "comment": f"dijo {encontrados}" if encontrados else "limpio",
    }


def escala_cuando_debe(inputs: dict, outputs: dict) -> dict:
    """Determinista. Un grupo de mas de 10 personas no se cierra por chat."""
    esperados = [t.get("escalado_esperado") for t in inputs["turnos"]]
    if not any(e is not None for e in esperados):
        return {"key": "escala_cuando_debe", "score": None, "comment": "no aplica"}
    obtenidos = outputs.get("escalados", [])
    correctos = [o == e for o, e in zip(obtenidos, esperados) if e is not None]
    return {
        "key": "escala_cuando_debe",
        "score": sum(correctos) / len(correctos),
        "comment": f"escalados={obtenidos} esperados={esperados}",
    }


def respeta_sus_limites(inputs: dict, outputs: dict) -> dict:
    """
    Juez con LLM. Reutiliza las mismas metricas GEval de `metricas.py`, para que
    LangSmith y DeepEval no midan con reglas distintas y despues no se sepa
    a cual creerle.

    Cuesta dinero: se aplica solo al ultimo turno de cada guion, que es donde el
    agente ya tiene todo el contexto y donde se ve si respeto su limite.
    """
    from deepeval.test_case import LLMTestCase

    from .metricas import METRICAS_POR_AGENTE, construir_metricas

    respuestas = outputs.get("respuestas", [])
    rutas = outputs.get("rutas", [])
    if not respuestas:
        return {"key": "respeta_sus_limites", "score": None, "comment": "sin respuesta"}

    agente, respuesta = rutas[-1], respuestas[-1]
    nombres = [n for n in METRICAS_POR_AGENTE.get(agente, []) if n != "Voz de Clemente"]
    if not nombres:
        return {"key": "respeta_sus_limites", "score": None, "comment": f"sin metrica para {agente}"}

    metricas = construir_metricas()
    caso = LLMTestCase(input=inputs["turnos"][-1]["mensaje"], actual_output=respuesta)
    metrica = metricas[nombres[0]]
    metrica.measure(caso)
    return {"key": "respeta_sus_limites", "score": metrica.score, "comment": metrica.reason}


EVALUADORES_GRATIS = [precision_de_ruteo, plan_completo, sin_texto_prohibido, escala_cuando_debe]


# --------------------------------------------------------------------------

def _fijar_modelo(modelo: str) -> None:
    """
    Deja el proceso corriendo con este modelo, cambiando de casa si hace falta.

    Antes esto solo escribia ANTHROPIC_MODEL, asi que con `AGENT_MODEL=openai`
    en el `.env` la opcion `--modelo claude-opus-5` no hacia absolutamente nada
    y la corrida quedaba etiquetada con un modelo que nunca se uso.
    """
    from app.llm import proveedor_de

    proveedor = proveedor_de(modelo)
    os.environ["AGENT_MODEL"] = proveedor
    os.environ["ANTHROPIC_MODEL" if proveedor == "claude" else "OPENAI_MODEL"] = modelo


def main() -> None:
    """Procesa la CLI, publica el dataset y opcionalmente ejecuta el experimento en LangSmith.

    Requiere su credencial; --subir solo sincroniza datos y --con-juez agrega
    evaluacion LLM. Puede escribir datos externos y consumir APIs."""
    parser = argparse.ArgumentParser(description="Experimento de Clemente en LangSmith")
    parser.add_argument("--subir", action="store_true",
                        help="solo crear o actualizar el dataset, sin correr nada")
    parser.add_argument("--modelo", help="modelo de esta corrida; cambia tambien de proveedor")
    parser.add_argument("--dataset", default=NOMBRE_DATASET,
                        help=f"dataset de LangSmith (por defecto {NOMBRE_DATASET})")
    parser.add_argument("--etiqueta", default="", help="sufijo del nombre del experimento")
    parser.add_argument("--con-juez", action="store_true",
                        help="agrega el evaluador con LLM (cuesta mas)")
    parser.add_argument("--si", action="store_true", help="no pedir confirmacion")
    args = parser.parse_args()

    if args.modelo:
        _fijar_modelo(args.modelo)

    from langsmith import Client

    from app.config import Config
    Config.desde_entorno()

    if not os.getenv("LANGSMITH_API_KEY"):
        sys.exit("Falta LANGSMITH_API_KEY en el .env.")

    client = Client()

    if args.subir:
        subir_dataset(client, args.dataset)
        return

    # Subir es idempotente, asi que se hace siempre antes de correr: garantiza
    # que el experimento use la version vigente de los casos.
    subir_dataset(client, args.dataset)

    datos = json.loads(CASOS.read_text(encoding="utf-8"))
    turnos = sum(len(g["turnos"]) for g in datos["guiones"])
    modelo = modelo_activo()
    evaluadores = EVALUADORES_GRATIS + ([respeta_sus_limites] if args.con_juez else [])

    print(f"\nExperimento sobre '{args.dataset}': "
          f"{len(datos['guiones'])} guiones, {turnos} turnos, modelo {modelo}.")
    print(f"Evaluadores: {[e.__name__ for e in evaluadores]}")
    print("Esto ejecuta los agentes de verdad y gasta.")
    if not args.si and input("Continuar? [s/N] ").strip().lower() not in {"s", "si", "y"}:
        sys.exit("Cancelado, no se gasto nada.")

    prefijo = f"clemente-{args.etiqueta or modelo}"
    resultados = client.evaluate(
        clemente,
        data=args.dataset,
        evaluators=evaluadores,
        experiment_prefix=prefijo,
        metadata={"modelo": modelo, "frente": "agentes-orquestador"},
        max_concurrency=2,   # bajo a proposito: no gatillar limites de la API
    )

    print("\nExperimento terminado. Se compara con las corridas anteriores en:")
    print(f"  LangSmith > Datasets & Experiments > {args.dataset}")
    try:
        print(f"  {resultados}")
    except Exception:
        pass


if __name__ == "__main__":
    main()
