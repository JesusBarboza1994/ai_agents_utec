"""Repite solo juicios invalidos de una evaluacion, sobre respuestas congeladas."""
import asyncio
import json
import os

from .entorno import guardar_json


def ejecutar(destino):
    """Reevalua solo juicios con error de la corrida previa y guarda resultados incrementalmente.

    Conserva la respuesta original del objetivo, exige schema al juez y
    consume su API; no vuelve a ejecutar el ataque contra el asistente."""
    from deepteam.test_case import RTTestCase
    from tests.eval.juez import construir_juez
    from .red_team_reservas import construir_escenarios
    origen = destino.parent / "completo_repeticion/evaluacion.json"
    datos = json.loads(origen.read_text(encoding="utf-8"))
    os.environ["CLEMENTE_JUEZ_EXIGIR_ESQUEMA"] = "1"
    juez = construir_juez("claude-sonnet-5")
    vulnerabilidades, _ = construir_escenarios(False)
    resultados = []
    for indice, crudo in enumerate(datos["test_cases"]):
        if not crudo.get("error"):
            continue
        vuln = next(v for v in vulnerabilidades if v.get_name() == crudo["vulnerability"])
        datos_caso = dict(crudo)
        datos_caso["vulnerability_type"] = next(t for t in vuln.types if t.value == crudo["vulnerability_type"])
        caso = RTTestCase.model_validate(datos_caso)
        caso.error = None
        vuln.evaluation_model = juez
        metrica = vuln._get_metric(caso.vulnerability_type)
        fila = {"indice_original": indice, "tipo": crudo["vulnerability_type"],
                "ataque": crudo["attack_method"], "respuesta_congelada": crudo["actual_output"]}
        try:
            asyncio.run(metrica.a_measure(caso))
            fila.update(score=metrica.score, reason=metrica.reason)
        except Exception as error:
            fila["error"] = type(error).__name__
        resultados.append(fila)
        guardar_json(destino / "juicios_repetidos.json", resultados)
        print("Juicio", indice, "score", fila.get("score"), "error", fila.get("error"), flush=True)
