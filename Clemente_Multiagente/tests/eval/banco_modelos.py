"""
Banco de modelos: cuanto cuesta y cuanto tarda Clemente con cada LLM.

    python -m tests.eval.banco_modelos --modelos claude-sonnet-5,gpt-5.6-sol
    python -m tests.eval.banco_modelos --modelos claude-haiku-4-5,claude-sonnet-5,claude-opus-5,gpt-5.6-luna,gpt-5.6-sol,gpt-6-astra
    python -m tests.eval.banco_modelos --modelos gpt-5.6-sol --guiones informacion-horarios,reservas-disponibilidad

Que mide, y por que asi
-----------------------
Tres cosas por modelo, sobre EXACTAMENTE el mismo dataset (`casos.json`):

  * **Costo.** No se estima: se leen los tokens reales que devuelve la API
    (`usage_metadata` de cada llamada) y se multiplican por el precio publicado
    en `app/llm.py`. Si un modelo no tiene precio en esa tabla, se reportan sus
    tokens y el costo queda vacio -- antes vacio que inventado.
  * **Velocidad.** Tiempo de pared por turno, que es lo que siente el cliente en
    el chat. Se reporta la mediana y el peor turno, no solo el promedio: en un
    chat lo que molesta es el turno lento, y el promedio lo esconde.
  * **Calidad minima.** Los mismos evaluadores deterministas del experimento de
    LangSmith: si el alcance esperado se atendio, si el plan de dos pasos se
    cumplio, y si aparecio texto prohibido. Son gratis y evitan la conclusion
    tramposa de "el mas barato gano" cuando el mas barato en realidad respondia
    cualquier cosa.

Por que los tokens y no el numero de llamadas: los modelos Claude 4.7 en
adelante usan un tokenizador nuevo que produce alrededor de 30% mas tokens para
el mismo texto (documentado por Anthropic). Comparar precios por millon de
tokens entre casas sin medir los tokens reales de cada una da una conclusion
equivocada. Por eso el banco mide, no calcula.

ESTO GASTA DINERO DE VERDAD. Pide confirmacion antes de arrancar y muestra el
gasto acumulado al terminar.
"""

import argparse
import json
import os
import statistics
import sys
import time
from datetime import datetime
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent.parent
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

CASOS = Path(__file__).parent / "casos.json"
RESULTADOS = Path(__file__).parent / "resultados"

# Texto que Clemente no debe escribir nunca, venga del modelo que venga.
PROHIBIDO = ("como modelo de lenguaje", "soy una inteligencia artificial",
             "no tengo acceso", "**", "1.")

# "- " aparte, y con su propio chequeo: como substring simple daba falso
# positivo con los CODIGOS del proyecto (R- de una reserva, I- de un caso),
# que tambien son "letra-guion-espacio". Descubierto el 2026-09-08 comparando
# gpt-5.6-terra contra claude-sonnet-5: el "2" de texto prohibido de terra
# eran dos respuestas legitimas citando "R- o el telefono", no vinetas. Una
# vineta real va al INICIO de renglon; un codigo va pegado a una palabra antes.
def _tiene_vineta(texto: str) -> bool:
    """Detecta si texto comienza con una vineta Markdown o la contiene tras un salto de linea."""
    return texto.lstrip().startswith("- ") or "\n- " in texto


def backend_de(modelo: str) -> str:
    """De que proveedor es un ID de modelo. Sin adivinar: prefijos conocidos."""
    if modelo.startswith("claude"):
        return "claude"
    if modelo.startswith(("gpt", "o1", "o3", "o4")):
        return "openai"
    raise SystemExit(
        f"No se de que proveedor es {modelo!r}. Usa un ID que empiece con "
        f"'claude' o con 'gpt'/'o'."
    )


def activar(modelo: str) -> None:
    """
    Deja el proceso configurado para correr con este modelo.

    Escribe las variables de entorno y tira abajo los agentes ya construidos:
    el modelo se resuelve al construir el agente, asi que sin el reinicio el
    banco mediria tres veces el primer modelo.
    """
    from app.orquestador.grafo import reiniciar_grafo

    backend = backend_de(modelo)
    os.environ["AGENT_MODEL"] = backend
    if backend == "claude":
        os.environ["ANTHROPIC_MODEL"] = modelo
        os.environ.pop("ANTHROPIC_MODEL_ENRUTADOR", None)
    else:
        os.environ["OPENAI_MODEL"] = modelo
        os.environ.pop("OPENAI_MODEL_ENRUTADOR", None)
    reiniciar_grafo()


def credencial_de(backend: str) -> bool:
    """Comprueba presencia de la variable de credencial del backend, sin validar contra la API."""
    return bool(os.getenv("ANTHROPIC_API_KEY" if backend == "claude" else "OPENAI_API_KEY"))


# --------------------------------------------------------------------------
# La corrida
# --------------------------------------------------------------------------

def correr_modelo(modelo: str, guiones: list[dict]) -> dict:
    """Ejecuta todo el dataset con un modelo y devuelve sus numeros."""
    from langchain_core.callbacks import get_usage_metadata_callback

    from app.contratos import MensajeEntrante
    from app.llm import costo
    from app.orquestador import grafo

    activar(modelo)

    turnos_medidos = []
    aciertos_ruta = total_ruta = 0
    aciertos_plan = total_plan = 0
    prohibidos = 0
    errores = []

    with get_usage_metadata_callback() as uso:
        for guion in guiones:
            sesion = f"banco-{modelo}-{guion['id']}"
            grafo.olvidar_sesion(sesion)
            historial: list[dict] = []

            for turno in guion["turnos"]:
                inicio = time.perf_counter()
                try:
                    salida = grafo.responder(
                        MensajeEntrante(sesion_id=sesion, texto=turno["mensaje"], canal="banco"),
                        historial=historial,
                    )
                except Exception as error:
                    errores.append(f"{guion['id']}: {error}")
                    continue
                transcurrido = time.perf_counter() - inicio

                historial.append({"role": "user", "content": turno["mensaje"]})
                historial.append({"role": "assistant", "content": salida.texto})

                plan = salida.datos.get("plan") or [salida.agente]
                esperada = turno.get("ruta_esperada")
                if esperada:
                    total_ruta += 1
                    aciertos_ruta += esperada in plan
                plan_esperado = turno.get("plan_esperado")
                if plan_esperado:
                    total_plan += 1
                    aciertos_plan += list(plan) == list(plan_esperado)
                bajo = salida.texto.lower()
                if any(p in bajo for p in PROHIBIDO) or _tiene_vineta(salida.texto):
                    prohibidos += 1

                turnos_medidos.append({
                    "guion": guion["id"],
                    "mensaje": turno["mensaje"][:70],
                    "segundos": round(transcurrido, 2),
                    "plan": plan,
                    "esperada": esperada,
                    "respuesta": salida.texto[:200],
                })
                print(f"    {transcurrido:6.2f}s  {'/'.join(plan):<24} {turno['mensaje'][:48]}")

    # `usage_metadata` viene por modelo; el banco corre uno a la vez, asi que se
    # suman todas las entradas (el enrutador y los agentes pueden aparecer
    # separados si alguna vez se configuran distintos).
    entrada = sum(v.get("input_tokens", 0) for v in uso.usage_metadata.values())
    salida_tok = sum(v.get("output_tokens", 0) for v in uso.usage_metadata.values())
    segundos = [t["segundos"] for t in turnos_medidos]

    return {
        "modelo": modelo,
        "backend": backend_de(modelo),
        "turnos": len(turnos_medidos),
        "errores": errores,
        "tokens_entrada": entrada,
        "tokens_salida": salida_tok,
        # None, no 0, cuando no hay precio publicado para ese modelo.
        "costo_usd": costo(modelo, entrada, salida_tok),
        "segundos_mediana": round(statistics.median(segundos), 2) if segundos else None,
        "segundos_peor": round(max(segundos), 2) if segundos else None,
        "segundos_total": round(sum(segundos), 1) if segundos else None,
        "ruteo": f"{aciertos_ruta}/{total_ruta}" if total_ruta else "-",
        "ruteo_pct": round(100 * aciertos_ruta / total_ruta) if total_ruta else None,
        "plan": f"{aciertos_plan}/{total_plan}" if total_plan else "-",
        "texto_prohibido": prohibidos,
        "detalle": turnos_medidos,
        "medicion_de_tokens": "ok" if entrada else "NO SE PUDO MEDIR",
    }


# --------------------------------------------------------------------------
# El informe
# --------------------------------------------------------------------------

def tabla(resultados: list[dict]) -> str:
    """Renderiza resultados como tabla Markdown de calidad minima, tokens, costo y latencia."""
    filas = [
        "| Modelo | Turnos | Ruteo | Plan | Texto prohibido | Tokens entrada | Tokens salida | Costo USD | Mediana | Peor turno |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for r in resultados:
        costo_txt = f"{r['costo_usd']:.4f}" if r["costo_usd"] is not None else "sin precio publicado"
        filas.append(
            f"| `{r['modelo']}` | {r['turnos']} | {r['ruteo']} | {r['plan']} | "
            f"{r['texto_prohibido']} | {r['tokens_entrada']:,} | {r['tokens_salida']:,} | "
            f"{costo_txt} | {r['segundos_mediana']}s | {r['segundos_peor']}s |"
        )
    return "\n".join(filas)


def informe(resultados: list[dict], guiones: list[dict]) -> str:
    """Genera el informe Markdown con dataset, tabla comparativa, tarifas y limites de interpretacion."""
    from app.llm import PRECIOS_POR_MILLON

    turnos = sum(len(g["turnos"]) for g in guiones)
    lineas = [
        "# Banco de modelos de Clemente",
        "",
        f"**Fecha:** {datetime.now():%Y-%m-%d %H:%M}  ",
        f"**Dataset:** {len(guiones)} guiones, {turnos} turnos (`tests/eval/casos.json`)  ",
        f"**Modelos comparados:** {len(resultados)}",
        "",
        "Todos los modelos corrieron el MISMO dataset, en el mismo orden, con los mismos",
        "prompts. Los tokens son los que devolvio cada API, no una estimacion; el costo",
        "sale de multiplicarlos por el precio publicado. La mediana y el peor turno son",
        "tiempo de pared, que es lo que espera el cliente en el chat.",
        "",
        "## Resultados",
        "",
        tabla(resultados),
        "",
        "## Como leer esta tabla",
        "",
        "- **Ruteo** y **Plan** son cotas de calidad minima, no una evaluacion completa.",
        "  Un modelo puede acertar el 100% del ruteo y aun asi redactar mal: eso lo mide",
        "  `deepeval_evaluar.py` con el juez, que cuesta aparte.",
        "- **Texto prohibido** cuenta los turnos donde Clemente escribio como documento",
        "  (vinetas, negritas) o se delato como modelo. Cualquier valor distinto de 0 es",
        "  un problema de voz, no de costo.",
        "- **Costo** es el de ESTA corrida completa, no el de un mensaje. Para estimar el",
        "  costo mensual hay que dividirlo entre los turnos y multiplicar por el volumen",
        "  esperado.",
        "",
        "## Precios usados",
        "",
        "Por millon de tokens, verificados el 2026-09-07 en las paginas oficiales de",
        "Anthropic y OpenAI (ver `app/llm.py`).",
        "",
        "| Modelo | Entrada | Salida |",
        "|---|---|---|",
    ]
    usados = {r["modelo"] for r in resultados}
    for modelo, (entrada, salida) in sorted(PRECIOS_POR_MILLON.items(), key=lambda x: x[1][0]):
        marca = " ← medido aqui" if modelo in usados else ""
        lineas.append(f"| `{modelo}` | ${entrada} | ${salida}{marca} |")

    fallidos = [r for r in resultados if r["errores"]]
    if fallidos:
        lineas += ["", "## Errores durante la corrida", ""]
        for r in fallidos:
            for error in r["errores"]:
                lineas.append(f"- `{r['modelo']}`: {error}")

    sin_medir = [r["modelo"] for r in resultados if r["medicion_de_tokens"] != "ok"]
    if sin_medir:
        lineas += [
            "", "## Advertencia", "",
            "No se pudieron leer los tokens de: " + ", ".join(f"`{m}`" for m in sin_medir) + ".",
            "El costo de esos modelos NO es confiable en esta corrida.",
        ]
    return "\n".join(lineas) + "\n"


# --------------------------------------------------------------------------

def main() -> None:
    """Procesa modelos y guiones de la CLI, muestra costos y ejecuta la comparacion autorizada.

    Realiza llamadas a proveedores y guarda resultados; --si omite la pregunta de inicio."""
    from app.config import Config
    from app.llm import precio_de

    parser = argparse.ArgumentParser(description="Compara modelos en costo, velocidad y ruteo")
    parser.add_argument("--modelos", required=True,
                        help="IDs separados por coma, p. ej. claude-sonnet-5,gpt-5.6-sol")
    parser.add_argument("--guiones", default="",
                        help="IDs de guion separados por coma; por defecto, todos")
    parser.add_argument("--si", action="store_true", help="No preguntar antes de gastar")
    args = parser.parse_args()

    Config.desde_entorno()

    datos = json.loads(CASOS.read_text(encoding="utf-8"))
    guiones = datos["guiones"]
    if args.guiones:
        pedidos = {g.strip() for g in args.guiones.split(",")}
        guiones = [g for g in guiones if g["id"] in pedidos]
        faltan = pedidos - {g["id"] for g in guiones}
        if faltan:
            raise SystemExit(f"No existen estos guiones: {', '.join(sorted(faltan))}")

    modelos = [m.strip() for m in args.modelos.split(",") if m.strip()]
    turnos = sum(len(g["turnos"]) for g in guiones)

    print(f"Banco de modelos -- {len(modelos)} modelos x {len(guiones)} guiones "
          f"({turnos} turnos cada uno)\n")
    for modelo in modelos:
        backend = backend_de(modelo)
        tarifa = precio_de(modelo)
        estado = "credencial OK" if credencial_de(backend) else "SIN CREDENCIAL"
        precio = f"${tarifa[0]}/${tarifa[1]} por MTok" if tarifa else "sin precio publicado"
        print(f"  {modelo:<22} {backend:<8} {estado:<16} {precio}")
        if not credencial_de(backend):
            raise SystemExit(
                f"\nFalta la clave de {backend} en clemente/.env. "
                f"Agregala o saca {modelo} de la lista."
            )

    print(f"\nEsto ejecuta los agentes de verdad contra cada API y GASTA DINERO.")
    print(f"Referencia: una corrida completa de 17 turnos con claude-sonnet-5 ronda")
    print(f"los 0.10-0.20 dolares; con gpt-6-astra, unas 5 veces mas.")
    if not args.si and input("\nContinuar? [s/N] ").strip().lower() not in ("s", "si"):
        print("Cancelado. No se gasto nada.")
        return

    resultados = []
    for modelo in modelos:
        print(f"\n=== {modelo} ===")
        inicio = time.perf_counter()
        resultado = correr_modelo(modelo, guiones)
        resultado["segundos_corrida"] = round(time.perf_counter() - inicio, 1)
        resultados.append(resultado)
        gasto = resultado["costo_usd"]
        print(f"  -> {resultado['turnos']} turnos, ruteo {resultado['ruteo']}, "
              f"mediana {resultado['segundos_mediana']}s, "
              f"costo {f'${gasto:.4f}' if gasto is not None else 'sin precio'}")

    RESULTADOS.mkdir(parents=True, exist_ok=True)
    marca = datetime.now().strftime("%Y%m%d_%H%M%S")
    ruta_json = RESULTADOS / f"banco_modelos_{marca}.json"
    ruta_md = RESULTADOS / f"banco_modelos_{marca}.md"
    ruta_json.write_text(json.dumps(resultados, ensure_ascii=False, indent=2), encoding="utf-8")
    ruta_md.write_text(informe(resultados, guiones), encoding="utf-8")

    print("\n" + tabla(resultados))
    conocidos = [r["costo_usd"] for r in resultados if r["costo_usd"] is not None]
    if conocidos:
        print(f"\nGasto total de esta comparacion: ${sum(conocidos):.4f}")
    print(f"\nInforme:  {ruta_md}")
    print(f"Detalle:  {ruta_json}")


if __name__ == "__main__":
    main()
