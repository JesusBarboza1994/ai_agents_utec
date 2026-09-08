"""
Evaluacion de Clemente contra el modelo real -- seccion 7.4 de la guia de Jean.

Esto NO es pytest y no vive con las pruebas de contrato a proposito: las de
`tests/` corren gratis en cada commit porque nunca llaman al modelo. Estas si
lo llaman, cuestan dinero, y por eso se ejecutan a mano y pidiendo confirmacion.

Uso:
    python tests/eval/evaluar.py                     # todos los guiones
    python tests/eval/evaluar.py --modelo claude-haiku-4-5
    python tests/eval/evaluar.py --solo reservas-continuidad-del-hilo
    python tests/eval/evaluar.py --si                # sin preguntar (para CI o repeticiones)

Que mide:
    * precision de enrutamiento, global y por agente (la metrica principal);
    * si la respuesta contiene lo que debe y no contiene lo que no debe
      (asi se detectan alucinaciones y compensaciones ofrecidas de mas);
    * si escalo cuando tenia que escalar;
    * latencia por turno, escalamientos y respuestas descartadas por el guardrail.

Deja el detalle en `tests/eval/resultados/<fecha>.json` para el anexo del informe.
"""

import argparse
import json
import os
import sys
import time
import unicodedata
from datetime import datetime
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(RAIZ))

from app.llm import modelo_activo  # noqa: E402

CASOS = Path(__file__).parent / "casos.json"
RESULTADOS = Path(__file__).parent / "resultados"

# Costo aproximado por turno, para avisar antes de gastar. Sale de medir la
# sesion del 2026-09-06: 45 llamadas al modelo y 125k tokens en 14 turnos.
COSTO_POR_TURNO = {
    "claude-opus-5": 0.060,
    "claude-sonnet-5": 0.024,
    "claude-haiku-4-5": 0.012,
}


def _normalizar(texto: str) -> str:
    """Minusculas y sin tildes: comparar 'politica' con 'política' no debe fallar."""
    sin_tildes = unicodedata.normalize("NFKD", texto.lower())
    return "".join(c for c in sin_tildes if not unicodedata.combining(c))


def _verificar_texto(respuesta: str, turno: dict) -> list[str]:
    """Devuelve la lista de incumplimientos de un turno (vacia si esta todo bien)."""
    fallas = []
    normalizada = _normalizar(respuesta)

    esperados = turno.get("debe_contener", [])
    if esperados:
        encontrados = [e for e in esperados if _normalizar(e) in normalizada]
        if turno.get("modo_contiene") == "alguno":
            if not encontrados:
                fallas.append(f"no menciona ninguno de {esperados}")
        else:
            faltantes = [e for e in esperados if e not in encontrados]
            if faltantes:
                fallas.append(f"no menciona {faltantes}")

    for prohibido in turno.get("no_debe_contener", []):
        if _normalizar(prohibido) in normalizada:
            fallas.append(f"menciona '{prohibido}', que tiene prohibido")

    return fallas


def evaluar(guiones: list[dict]) -> dict:
    from app.contratos import MensajeEntrante
    from app.observabilidad.trazas import metricas
    from app.orquestador import responder

    resultados = []
    aciertos = total = 0
    por_agente: dict[str, dict[str, int]] = {}

    for guion in guiones:
        sesion = guion.get("sesion_fija") or f"eval-{guion['id']}-{int(time.time())}"
        historial: list[dict] = []
        print(f"\n### {guion['id']}   ({guion.get('origen', 'sin origen')})")

        for turno in guion["turnos"]:
            inicio = time.perf_counter()
            respuesta = responder(
                MensajeEntrante(sesion_id=sesion, texto=turno["mensaje"], canal="eval"),
                historial=historial,
            )
            duracion = time.perf_counter() - inicio

            historial.append({"role": "user", "content": turno["mensaje"]})
            historial.append({"role": "assistant", "content": respuesta.texto})

            esperada = turno["ruta_esperada"]
            ruteo_ok = respuesta.agente == esperada
            fallas = _verificar_texto(respuesta.texto, turno)
            if "escalado_esperado" in turno and respuesta.escalado != turno["escalado_esperado"]:
                fallas.append(f"escalado={respuesta.escalado}, se esperaba {turno['escalado_esperado']}")

            total += 1
            aciertos += ruteo_ok
            cuenta = por_agente.setdefault(esperada, {"casos": 0, "aciertos": 0})
            cuenta["casos"] += 1
            cuenta["aciertos"] += ruteo_ok

            marca = "OK " if ruteo_ok and not fallas else "MAL"
            print(f"  {marca} [{respuesta.agente:13}/{esperada:13}] {duracion:5.1f}s  {turno['mensaje'][:60]}")
            for falla in fallas:
                print(f"      -> {falla}")
            if not ruteo_ok:
                print(f"      -> ruteo incorrecto. Motivo del enrutador: {respuesta.motivo_ruta[:110]}")

            resultados.append({
                "guion": guion["id"],
                "mensaje": turno["mensaje"],
                "ruta_esperada": esperada,
                "ruta_obtenida": respuesta.agente,
                "ruteo_correcto": ruteo_ok,
                "motivo_ruta": respuesta.motivo_ruta,
                "escalado": respuesta.escalado,
                "fallas_de_contenido": fallas,
                "duracion_s": round(duracion, 2),
                "respuesta": respuesta.texto,
            })

    return {
        "momento": datetime.now().isoformat(timespec="seconds"),
        "modelo": modelo_activo(),
        "turnos": total,
        "precision_ruteo": round(aciertos / total, 3) if total else 0.0,
        "precision_por_agente": {
            agente: round(d["aciertos"] / d["casos"], 3) for agente, d in por_agente.items()
        },
        "turnos_con_fallas_de_contenido": sum(1 for r in resultados if r["fallas_de_contenido"]),
        "metricas_del_sistema": metricas(),
        "detalle": resultados,
    }


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
    parser = argparse.ArgumentParser(description="Evaluacion de Clemente contra el modelo real")
    parser.add_argument("--modelo", help="modelo de esta corrida; cambia tambien de proveedor")
    parser.add_argument("--solo", help="ejecuta un unico guion por su id")
    parser.add_argument("--si", action="store_true", help="no pedir confirmacion antes de gastar")
    args = parser.parse_args()

    if args.modelo:
        _fijar_modelo(args.modelo)

    datos = json.loads(CASOS.read_text(encoding="utf-8"))
    guiones = datos["guiones"]
    if args.solo:
        guiones = [g for g in guiones if g["id"] == args.solo]
        if not guiones:
            sys.exit(f"No existe el guion '{args.solo}'. Ids: {[g['id'] for g in datos['guiones']]}")

    turnos = sum(len(g["turnos"]) for g in guiones)
    modelo = modelo_activo()
    costo = COSTO_POR_TURNO.get(modelo, 0.05) * turnos
    print(f"{len(guiones)} guiones, {turnos} turnos, modelo {modelo}.")
    print(f"Costo aproximado: ${costo:.2f}  (estimacion, el real lo dice LangSmith)")

    if not args.si and input("Continuar? [s/N] ").strip().lower() not in {"s", "si", "y"}:
        sys.exit("Cancelado, no se gasto nada.")

    informe = evaluar(guiones)

    print("\n" + "=" * 70)
    print(f"PRECISION DE RUTEO: {informe['precision_ruteo']:.0%}  ({informe['turnos']} turnos)")
    for agente, precision in sorted(informe["precision_por_agente"].items()):
        print(f"  {agente:14} {precision:.0%}")
    print(f"Turnos con fallas de contenido: {informe['turnos_con_fallas_de_contenido']}")
    print(f"Escalamientos: {informe['metricas_del_sistema'].get('escalamientos')}  |  "
          f"descartes del guardrail: {informe['metricas_del_sistema'].get('respuestas_descartadas_por_guardrail')}")

    RESULTADOS.mkdir(parents=True, exist_ok=True)
    destino = RESULTADOS / f"{datetime.now():%Y%m%d_%H%M%S}_{informe['modelo']}.json"
    destino.write_text(json.dumps(informe, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nDetalle completo: {destino.relative_to(RAIZ)}")


if __name__ == "__main__":
    main()
