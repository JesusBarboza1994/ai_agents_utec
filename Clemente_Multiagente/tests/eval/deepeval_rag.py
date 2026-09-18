"""
Evaluacion del recuperador del RAG con ContextualPrecisionMetric -- Sesion 22.

Esto NO evalua lo que responde el Agente de Conocimiento: evalua el buscador
que hay debajo. La pregunta que responde es una sola:

    de los fragmentos que Chroma devolvio, los que de verdad servian
    para contestar, quedaron ARRIBA en el ranking?

Un recuperador puede traer el fragmento correcto en la cuarta posicion y aun
asi el agente responder bien, porque el modelo lee los cuatro. Pero es fragil:
el dia que se acorte la ventana o se baje `k`, se rompe. La precision
contextual mide esa fragilidad antes de que se convierta en una falla.

Es la metrica que dice si el *chunking* por encabezado que adoptamos el
2026-09-06 (decision 4 de la guia de Jean) sirvio de algo. Conviene guardar el
resultado para poder comparar si alguna vez se cambia la estrategia de corte.

**Es barato**: no ejecuta a los agentes, solo el recuperador (embeddings
locales, gratis) y el juez. Se puede correr seguido.

    python -m tests.eval.deepeval_rag
    python -m tests.eval.deepeval_rag --k 6      # probar otro tamano de recuperacion
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent.parent
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from .juez import construir_juez, nombre_del_juez   # noqa: E402
from .metricas import metrica_precision_contextual  # noqa: E402

CASOS = Path(__file__).parent / "casos.json"
RESULTADOS = Path(__file__).parent / "resultados"


def casos_de_catalogo() -> list[dict]:
    """Los turnos de Conocimiento que tienen respuesta de referencia escrita."""
    datos = json.loads(CASOS.read_text(encoding="utf-8"))
    return [
        {"guion": guion["id"], **turno}
        for guion in datos["guiones"]
        for turno in guion["turnos"]
        if turno.get("ruta_esperada") == "informacion" and turno.get("respuesta_esperada")
    ]


def evaluar(k: int) -> dict:
    """Recupera k fragmentos por pregunta y mide precision contextual con el juez.

    Devuelve fuentes, scores y agregado; usa la respuesta de referencia y
    no ejecuta el agente conversacional. Las llamadas al juez tienen costo."""
    from deepeval.test_case import LLMTestCase

    from app.agentes.rag.indice import buscar

    metrica = metrica_precision_contextual(construir_juez())
    resultados = []

    for caso in casos_de_catalogo():
        fragmentos = buscar(caso["mensaje"], k=k)
        contexto = [f"[{f.fuente}] {f.texto}" for f in fragmentos]

        # `actual_output` se rellena con la respuesta de referencia a proposito:
        # ContextualPrecision juzga el ranking del contexto frente a lo que se
        # esperaba responder, no la redaccion del agente. Poner aqui la respuesta
        # real mezclaria dos cosas distintas -- buscar mal y redactar mal.
        prueba = LLMTestCase(
            input=caso["mensaje"],
            actual_output=caso["respuesta_esperada"],
            expected_output=caso["respuesta_esperada"],
            retrieval_context=contexto,
        )
        metrica.measure(prueba)
        aprobo = metrica.score >= metrica.threshold

        print(f"  {'OK ' if aprobo else 'MAL'} {metrica.score:.2f}  {caso['mensaje'][:55]}")
        print(f"      fuentes: {', '.join(f.fuente for f in fragmentos)}")
        if not aprobo:
            print(f"      {metrica.reason}")

        resultados.append({
            "guion": caso["guion"],
            "pregunta": caso["mensaje"],
            "respuesta_esperada": caso["respuesta_esperada"],
            "fuentes_recuperadas": [f.fuente for f in fragmentos],
            "score": round(metrica.score, 3),
            "umbral": metrica.threshold,
            "aprobo": aprobo,
            "razon": metrica.reason,
        })

    aprobados = sum(r["aprobo"] for r in resultados)
    return {
        "momento": datetime.now().isoformat(timespec="seconds"),
        "metrica": "ContextualPrecisionMetric",
        "modelo_juez": nombre_del_juez(),
        "k": k,
        "estrategia_de_chunking": "MarkdownHeaderTextSplitter + corte por tamano (1200/120)",
        "casos": len(resultados),
        "aprobados": aprobados,
        "precision_promedio": round(sum(r["score"] for r in resultados) / len(resultados), 3)
        if resultados else 0.0,
        "detalle": resultados,
    }


def main() -> None:
    """Procesa k y juez, confirma el inicio salvo --si y persiste el informe de precision RAG."""
    parser = argparse.ArgumentParser(description="Precision contextual del RAG de Clemente")
    parser.add_argument("--k", type=int, default=4, help="fragmentos a recuperar (por defecto 4)")
    parser.add_argument("--juez", help="modelo que califica")
    parser.add_argument("--si", action="store_true", help="no pedir confirmacion")
    args = parser.parse_args()

    import os
    if args.juez:
        os.environ["JUEZ_MODEL"] = args.juez

    from app.config import Config
    Config.desde_entorno()

    casos = casos_de_catalogo()
    if not casos:
        sys.exit("No hay casos de Conocimiento con 'respuesta_esperada' en casos.json.")

    print(f"{len(casos)} preguntas de catalogo, k={args.k}, juez {nombre_del_juez()}.")
    print("Solo gasta el juez: el recuperador es local y no ejecuta a los agentes.")
    if not args.si and input("Continuar? [s/N] ").strip().lower() not in {"s", "si", "y"}:
        sys.exit("Cancelado, no se gasto nada.")

    informe = evaluar(args.k)
    print("\n" + "=" * 70)
    print(f"PRECISION CONTEXTUAL: {informe['precision_promedio']:.2f}  "
          f"({informe['aprobados']}/{informe['casos']} aprobados, k={informe['k']})")

    RESULTADOS.mkdir(parents=True, exist_ok=True)
    destino = RESULTADOS / f"rag_precision_{datetime.now():%Y%m%d_%H%M%S}_k{args.k}.json"
    destino.write_text(json.dumps(informe, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Detalle: {destino.relative_to(RAIZ)}")


if __name__ == "__main__":
    main()
