"""Campana autorizada: etapas independientes, evidencias y presupuesto comunes."""
import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

from .entorno import entorno_aislado, guardar_json
from .presupuesto import Presupuesto


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("etapa", choices=["conexion", "conexion_medida", "funcional", "ciclo", "humo", "completo", "completo_repeticion", "rejuzgar", "trello"])
    parser.add_argument("--env", type=Path, required=True)
    parser.add_argument("--destino", type=Path, required=True)
    parser.add_argument("--reanudar", action="store_true")
    args = parser.parse_args()
    for flujo in (sys.stdout, sys.stderr):
        if hasattr(flujo, "reconfigure"):
            flujo.reconfigure(encoding="utf-8", errors="backslashreplace")
    from dotenv import dotenv_values
    for clave, valor in dotenv_values(args.env).items():
        if valor is not None:
            os.environ[clave] = valor
    os.environ.update(AGENT_MODEL="openai", OPENAI_MODEL="gpt-5.6-terra",
        OPENAI_MODEL_ENRUTADOR="gpt-5.6-terra", JUEZ_MODEL="claude-sonnet-5",
        PYTHON_DOTENV_DISABLED="1", DEEPEVAL_TELEMETRY_OPT_OUT="YES",
        DEEPTEAM_TELEMETRY_OPT_OUT="YES",
        LANGSMITH_TRACING="false", LANGCHAIN_TRACING_V2="false",
        EMBEDDINGS_BACKEND="ollama", ANONYMIZED_TELEMETRY="false")
    os.environ["CLEMENTE_EVAL_ETAPA"] = args.etapa
    # No URLs alternativas: la guardia de costo cubre estos dos proveedores.
    for clave in ("OPENAI_BASE_URL", "ANTHROPIC_BASE_URL"):
        if os.getenv(clave):
            raise ValueError("Quitar endpoints alternativos para esta campana")
    destino = args.destino / args.etapa
    if (destino / "estado.json").exists() and not (args.reanudar and args.etapa in {"funcional", "rejuzgar"}):
        raise ValueError("Etapa ya iniciada; conservar evidencia y usar otro destino para repetir")
    estado = {"etapa": args.etapa, "estado": "iniciado",
              "agente": "gpt-5.6-terra", "juez": "claude-sonnet-5"}
    if args.reanudar:
        guardar_json(destino / "estado_anterior.json", json.loads((destino / "estado.json").read_text()))
    guardar_json(destino / "estado.json", estado)
    os.environ["CLEMENTE_EVAL_ERRORES"] = str(destino / "errores_juez.jsonl")
    presupuesto = Presupuesto(args.destino / "presupuesto.json")
    try:
        with presupuesto.activo(), entorno_aislado(destino / "datos"):
            if args.etapa.startswith("conexion"):
                from app.llm import resolver_modelo, extraer_texto
                respuestas = {}
                for modelo in ("gpt-5.6-terra", "claude-sonnet-5"):
                    respuesta = resolver_modelo(modelo=modelo).invoke("Responde unicamente OK.")
                    respuestas[modelo] = extraer_texto(respuesta)
                    guardar_json(destino / "modelos.json", respuestas)
                    print(modelo, respuestas[modelo], flush=True)
                from .red_team_reservas import construir_callback
                turno = asyncio.run(construir_callback("sistema", destino / "turnos.jsonl")(
                    "Hola, tienen estacionamiento?"))
                guardar_json(destino / "clemente.json", turno.model_dump(mode="json"))
                print(turno.content, flush=True)
            elif args.etapa == "funcional":
                funcional(destino)
            elif args.etapa == "ciclo":
                from .ciclo_reserva import ejecutar
                ejecutar(destino)
            elif args.etapa == "trello":
                trello(destino)
            elif args.etapa == "rejuzgar":
                from .rejuzgar import ejecutar
                ejecutar(destino)
            else:
                from .red_team_reservas import construir_callback, construir_escenarios, ejecutar, escribir_informe
                vulnerabilidades, ataques = construir_escenarios(args.etapa == "humo")
                evaluacion = ejecutar(construir_callback("sistema", destino / "turnos.jsonl"),
                                      vulnerabilidades, ataques, destino,
                                      tolerar_errores=args.etapa == "completo_repeticion",
                                      concurrencia=2 if args.etapa == "completo_repeticion" else 1)
                guardar_json(destino / "evaluacion.json", evaluacion.model_dump(mode="json"))
                escribir_informe(evaluacion, "sistema", destino / "informe.md")
            estado["estado"] = "completo"
    except BaseException as error:
        estado.update(estado="error", tipo_error=type(error).__name__)
        # Solo tipo: algunas excepciones HTTP incorporan URLs con credenciales.
        print("ETAPA INTERRUMPIDA:", type(error).__name__, flush=True)
    finally:
        guardar_json(destino / "estado.json", estado)
        totales = {p: sum(c["usd"] for c in presupuesto.datos["cargos"] if c["proveedor"] == p)
                   for p in ("openai", "anthropic")}
        print("Estado:", estado["estado"], "USD reportados o reservados:", totales, flush=True)
    if estado["estado"] != "completo":
        raise SystemExit(1)


def funcional(destino):
    from tests.eval.deepeval_evaluar import CASOS, evaluar
    from tests.eval.metricas import construir_metricas
    from app.agentes import autorizacion
    semilla = json.loads((destino / "datos/semilla.json").read_text())
    guiones = json.loads(CASOS.read_text(encoding="utf-8"))["guiones"]
    for guion in guiones:
        guion.pop("sesion_fija", None)
        for turno in guion["turnos"]:
            turno["mensaje"] = turno["mensaje"].replace("Christian Cajusol", "Cliente Sintetico")
            turno["mensaje"] = turno["mensaje"].replace("956789900", "000000001")
            turno["mensaje"] = turno["mensaje"].replace("R-51BA96", semilla["reserva_id"])
        if guion["id"] == "memoria-cliente-conocido":
            guion["sesion_fija"] = "victima-sintetica"
    guardar_json(destino / "guiones_utilizados.json", guiones)
    metricas = construir_metricas()
    previos = destino / "resultados.json"
    informes = json.loads(previos.read_text(encoding="utf-8")) if previos.exists() else []
    terminados = {r["guion"] for i in informes for r in i["detalle"]}
    for guion in guiones:
        if guion["id"] in terminados:
            continue
        informe = evaluar([guion], metricas)
        informes.append(informe)
        guardar_json(destino / "resultados.json", informes)
        print("GUION TERMINADO:", guion["id"], flush=True)


def trello(destino):
    # Implementacion de la etapa separada: no activa Trello en red teaming.
    from .validacion_trello import ejecutar
    ejecutar(destino)


if __name__ == "__main__":
    main()
