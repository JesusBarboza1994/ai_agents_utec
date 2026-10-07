"""
Evaluacion de Clemente con DeepEval -- Sesion 22.

Es el escalon siguiente de `evaluar.py`. Aquel compara cadenas de texto y sirve
para lo binario (a que agente fue el mensaje, aparece el codigo de reserva).
Este juzga con un LLM lo que una busqueda de texto no puede ver: si el agente
prometio una mesa sin consultarla, si insinuo una compensacion sin usar la
palabra "descuento", si invento un dato que no esta en el catalogo.

    python -m tests.eval.deepeval_evaluar                    # todo
    python -m tests.eval.deepeval_evaluar --solo incidencias-espera
    python -m tests.eval.deepeval_evaluar --agente reservas
    python -m tests.eval.deepeval_evaluar --si               # sin preguntar

OJO CON EL COSTO: cada turno son dos gastos, no uno -- la respuesta del agente
y el juicio del juez. El script lo estima y pide confirmacion antes de gastar.

Deja el detalle en `tests/eval/resultados/deepeval_<fecha>.json` y un informe
legible en `.md`, que es lo que va al anexo del Modulo 8.
"""

import argparse
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent.parent
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from .juez import advertir_si_se_juzga_a_si_mismo, construir_juez, nombre_del_juez  # noqa: E402
from .metricas import METRICAS_POR_AGENTE, construir_metricas   # noqa: E402

from app.llm import modelo_activo  # noqa: E402

CASOS = Path(__file__).parent / "casos.json"
RESULTADOS = Path(__file__).parent / "resultados"

# Un turno evaluado = 1 respuesta del agente + N juicios del juez. Cada juicio
# de GEval es una llamada con la respuesta y los pasos de evaluacion adentro.
# Estos numeros salen de medir la sesion del 2026-09-06 y son aproximados.
COSTO_RESPUESTA = {"claude-opus-5": 0.060, "claude-sonnet-5": 0.024, "claude-haiku-4-5": 0.012}
COSTO_JUICIO = {"claude-opus-5": 0.020, "claude-sonnet-5": 0.008, "claude-haiku-4-5": 0.004}


def _contexto_recuperado(pregunta: str) -> list[str]:
    """
    Fragmentos que el RAG devuelve para esa pregunta.

    Se consulta el recuperador por separado en vez de interceptar la llamada
    que hace el agente. Es una aproximacion -- el agente puede reformular la
    consulta antes de buscar -- pero mide el mismo indice con la misma pregunta
    del cliente, y no cuesta nada porque los embeddings son locales.
    """
    from app.agentes.rag.indice import buscar

    return [f"[{f.fuente}] {f.texto}" for f in buscar(pregunta)]


def _tools_del_turno(sesion_id: str, desde: int):
    """
    Herramientas que el agente llamo en este turno, sacadas de nuestras trazas.

    Sin esto el juez solo ve el texto de la respuesta, y penaliza como "promesa
    sin respaldo" una afirmacion de disponibilidad que SI se consulto -- porque
    no tiene forma de saber que se llamo a `consultar_disponibilidad`. Fue el
    error de la primera corrida del 2026-09-07: el 0.00 no era del agente, era
    de la metrica.

    `desde` es el numero de trazas que ya existian antes del turno, para no
    arrastrar las herramientas de los turnos anteriores del mismo guion.
    """
    from deepeval.test_case import ToolCall

    from app.observabilidad.trazas import ultimas_trazas

    llamadas = []
    for t in ultimas_trazas(limite=200, sesion_id=sesion_id)[desde:]:
        if t.evento == "tool":
            llamadas.append(ToolCall(
                name=t.detalle.get("tool", "desconocida"),
                description=f"estado={t.detalle.get('estado', '?')} ({t.duracion_ms:.0f} ms)",
                # La SALIDA es lo que permite distinguir "consulto y reporto
                # fielmente" de "consulto y despues invento". Sin ella, el juez
                # penalizo con 0.60 una respuesta correcta que decia "hay lugar
                # en salon o terraza", porque no podia ver que la herramienta
                # habia devuelto exactamente esas dos zonas.
                output=t.detalle.get("salida", ""),
            ))
        elif t.evento == "ficha":
            # No es una tool que el modelo haya llamado: es informacion que el
            # sistema le inyecta al inicio del turno. Se declara asi, con su
            # nombre, para que el juez sepa de donde salieron los datos del
            # cliente y no los tome por inventados.
            llamadas.append(ToolCall(
                name="ficha_del_cliente",
                description="inyectada por el sistema al inicio del turno, no llamada por el modelo",
                output=t.detalle.get("ficha", ""),
            ))
        elif t.evento == "escalado":
            llamadas.append(ToolCall(
                name="cierre_orquestador",
                description="Evento del servidor posterior a las tools: ticket efectivamente registrado, no invocado por el modelo",
                output=json.dumps(t.detalle, ensure_ascii=False),
            ))
        elif t.evento == "operacion":
            llamadas.append(ToolCall(
                name="confirmacion_servidor",
                description="Operacion validada y ejecutada por el servidor tras confirmacion explicita",
                output=json.dumps(t.detalle, ensure_ascii=False),
            ))
    return llamadas


def _caso_de_prueba(mensaje: str, respuesta: str, agente: str, esperada: str | None,
                    tools: list | None = None):
    """Construye LLMTestCase con entrada, respuesta, referencia y herramientas observadas.

    Solo informacion incorpora contexto recuperado; esta recuperacion es
    posterior al turno y no acredita por si sola lo que vio el agente."""
    from deepeval.test_case import LLMTestCase

    return LLMTestCase(
        input=mensaje,
        actual_output=respuesta,
        expected_output=esperada,
        tools_called=tools or [],
        # Solo el Agente de Conocimiento se mide contra el catalogo; pedirle
        # contexto a los otros dos seria comparar contra algo que no usan.
        retrieval_context=_contexto_recuperado(mensaje) if agente == "informacion" else None,
    )


def evaluar(guiones: list[dict], metricas: dict) -> dict:
    """Ejecuta guiones contra el orquestador y mide las metricas asignadas a cada ruta.

    Conserva historial, extrae tools de trazas y devuelve detalle y agregados.
    Separa errores del juez de juicios validos y propaga PresupuestoAgotado.
    Consume APIs del asistente y del juez."""
    from app.contratos import MensajeEntrante
    from app.orquestador import responder

    detalle, resumen_metricas = [], {}

    for guion in guiones:
        sesion = guion.get("sesion_fija") or f"deepeval-{guion['id']}-{int(time.time())}"
        historial: list[dict] = []
        print(f"\n### {guion['id']}")

        for turno in guion["turnos"]:
            from app.observabilidad.trazas import ultimas_trazas
            antes = len(ultimas_trazas(limite=200, sesion_id=sesion))

            respuesta = responder(
                MensajeEntrante(sesion_id=sesion, texto=turno["mensaje"], canal="eval"),
                historial=historial,
            )
            historial.append({"role": "user", "content": turno["mensaje"]})
            historial.append({"role": "assistant", "content": respuesta.texto})

            # Las metricas se eligen por el agente que REALMENTE atendio, no por
            # el esperado: si el ruteo fallo, igual queremos saber si lo que dijo
            # respetaba sus limites.
            nombres = METRICAS_POR_AGENTE.get(respuesta.agente, [])
            tools = _tools_del_turno(sesion, antes)
            caso = _caso_de_prueba(
                turno["mensaje"], respuesta.texto, respuesta.agente,
                turno.get("respuesta_esperada"), tools,
            )

            usadas = ", ".join(t.name for t in tools) or "ninguna"
            print(f"  [{respuesta.agente}] {turno['mensaje'][:55]}   tools: {usadas}")
            juicios = {}
            for nombre in nombres:
                metrica = metricas[nombre]
                try:
                    metrica.measure(caso)
                except Exception as error:
                    # Conservar un fallo del juez como error, nunca como aprobado.
                    # Si el control de costo rechazo una llamada, detener la etapa.
                    from tests.seguridad.presupuesto import PresupuestoAgotado
                    causa = error
                    while causa is not None:
                        if isinstance(causa, PresupuestoAgotado):
                            raise
                        causa = causa.__cause__
                    juicios[nombre] = {"error": type(error).__name__, "aprobo": False,
                                      "razon": "El juez no produjo un resultado valido; requiere revision"}
                    print(f"      ERROR {nombre}: {type(error).__name__}")
                    continue
                aprobo = metrica.score >= metrica.threshold
                juicios[nombre] = {
                    "score": round(metrica.score, 3),
                    "umbral": metrica.threshold,
                    "aprobo": aprobo,
                    "razon": metrica.reason,
                }
                resumen = resumen_metricas.setdefault(nombre, {"casos": 0, "aprobados": 0, "suma": 0.0})
                resumen["casos"] += 1
                resumen["aprobados"] += aprobo
                resumen["suma"] += metrica.score
                print(f"      {'OK ' if aprobo else 'MAL'} {nombre}: {metrica.score:.2f}")
                if not aprobo:
                    print(f"          {metrica.reason}")

            detalle.append({
                "guion": guion["id"],
                "mensaje": turno["mensaje"],
                "agente": respuesta.agente,
                "ruta_esperada": turno.get("ruta_esperada"),
                "ruteo_correcto": respuesta.agente == turno.get("ruta_esperada"),
                "respuesta": respuesta.texto,
                "escalado": respuesta.escalado,
                "tools_llamadas": [t.name for t in tools],
                "juicios": juicios,
            })

    return {
        "momento": datetime.now().isoformat(timespec="seconds"),
        "modelo_evaluado": modelo_activo(),
        "modelo_juez": nombre_del_juez(),
        "turnos": len(detalle),
        "metricas": {
            nombre: {
                "casos": d["casos"],
                "aprobados": d["aprobados"],
                "tasa_aprobacion": round(d["aprobados"] / d["casos"], 3),
                "score_promedio": round(d["suma"] / d["casos"], 3),
            }
            for nombre, d in resumen_metricas.items()
        },
        "detalle": detalle,
    }


def escribir_informe(informe: dict, destino: Path) -> None:
    """Informe legible para el anexo. El JSON queda para reprocesar."""
    lineas = [
        "# Evaluacion de Clemente con DeepEval",
        "",
        f"**Fecha:** {informe['momento']}  ",
        f"**Modelo evaluado:** `{informe['modelo_evaluado']}`  ",
        f"**Modelo juez:** `{informe['modelo_juez']}`  ",
        f"**Turnos:** {informe['turnos']}",
        "",
        "El juez se declara junto al resultado porque un LLM-as-judge tiene sesgos "
        "conocidos (prefiere respuestas largas, favorece a su propia familia de "
        "modelos, varia entre corridas). Un puntaje sin decir quien juzgo no es "
        "interpretable.",
        "",
        "> **Sesgo de auto-preferencia:** juez y evaluado son el MISMO modelo en esta "
        "corrida, asi que los puntajes estan probablemente inflados. Repetir con "
        "`--juez` apuntando a otro modelo antes de citar estos numeros."
        if informe["modelo_juez"] == informe["modelo_evaluado"] else
        "Juez y modelo evaluado son distintos. Esto no elimina los sesgos ni "
        "los errores de evaluacion; los resultados requieren revision contra evidencia.",
        "",
        "## Resultados por metrica",
        "",
        "| Metrica | Casos | Aprobados | Tasa | Score promedio |",
        "|---|---|---|---|---|",
    ]
    for nombre, d in sorted(informe["metricas"].items()):
        lineas.append(
            f"| {nombre} | {d['casos']} | {d['aprobados']} | "
            f"{d['tasa_aprobacion']:.0%} | {d['score_promedio']:.2f} |"
        )

    fallas = [
        (t, nombre, j)
        for t in informe["detalle"]
        for nombre, j in t["juicios"].items()
        if not j["aprobo"]
    ]
    lineas += ["", f"## Casos que no aprobaron ({len(fallas)})", ""]
    if not fallas:
        lineas.append("Ninguno.")
    for turno, nombre, juicio in fallas:
        puntuacion = f"{juicio['score']:.2f}" if "score" in juicio else f"error del juez ({juicio['error']})"
        lineas += [
            f"### `{turno['guion']}` — {nombre}: {puntuacion}",
            "",
            f"**Mensaje del cliente:** {turno['mensaje']}",
            "",
            f"**Respondio ({turno['agente']}):** {turno['respuesta']}",
            "",
            f"**Por que fallo:** {juicio['razon']}",
            "",
        ]
    destino.write_text("\n".join(lineas), encoding="utf-8")


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
    """Selecciona modelo, juez y guiones de la CLI y guarda la evaluacion DeepEval.

    Muestra estimacion de gasto y pide inicio salvo --si; consume APIs reales."""
    parser = argparse.ArgumentParser(description="Evaluacion de Clemente con DeepEval")
    parser.add_argument("--modelo", help="modelo de esta corrida; cambia tambien de proveedor")
    parser.add_argument("--juez", help="modelo que califica (por defecto, el mismo que responde)")
    parser.add_argument("--solo", help="un unico guion por su id")
    parser.add_argument("--agente", choices=["reservas", "incidencias", "informacion"],
                        help="solo los guiones cuya ruta esperada sea ese agente")
    parser.add_argument("--si", action="store_true", help="no pedir confirmacion")
    args = parser.parse_args()

    if args.modelo:
        _fijar_modelo(args.modelo)
    if args.juez:
        os.environ["JUEZ_MODEL"] = args.juez

    from app.config import Config
    Config.desde_entorno()

    datos = json.loads(CASOS.read_text(encoding="utf-8"))
    guiones = datos["guiones"]
    if args.solo:
        guiones = [g for g in guiones if g["id"] == args.solo]
    if args.agente:
        guiones = [g for g in guiones
                   if any(t.get("ruta_esperada") == args.agente for t in g["turnos"])]
    if not guiones:
        sys.exit(f"Ningun guion coincide. Ids: {[g['id'] for g in datos['guiones']]}")

    turnos = sum(len(g["turnos"]) for g in guiones)
    modelo = modelo_activo()
    juez = nombre_del_juez()
    # Dos metricas por turno en promedio (la de limite del agente y la de voz).
    costo = turnos * (COSTO_RESPUESTA.get(modelo, 0.05) + 2 * COSTO_JUICIO.get(juez, 0.02))

    print(f"{len(guiones)} guiones, {turnos} turnos.")
    print(f"Responde: {modelo}   |   Juzga: {juez}")
    aviso = advertir_si_se_juzga_a_si_mismo()
    if aviso:
        print(aviso)
    print(f"Costo aproximado: ${costo:.2f}  (respuestas + juicios; el real lo dice LangSmith)")
    if not args.si and input("Continuar? [s/N] ").strip().lower() not in {"s", "si", "y"}:
        sys.exit("Cancelado, no se gasto nada.")

    informe = evaluar(guiones, construir_metricas(construir_juez()))

    print("\n" + "=" * 70)
    for nombre, d in sorted(informe["metricas"].items()):
        print(f"  {nombre:38} {d['tasa_aprobacion']:.0%}  (score {d['score_promedio']:.2f})")

    RESULTADOS.mkdir(parents=True, exist_ok=True)
    marca = f"{datetime.now():%Y%m%d_%H%M%S}"
    (RESULTADOS / f"deepeval_{marca}.json").write_text(
        json.dumps(informe, ensure_ascii=False, indent=2), encoding="utf-8")
    escribir_informe(informe, RESULTADOS / f"deepeval_{marca}.md")
    print(f"\nInforme: tests/eval/resultados/deepeval_{marca}.md")


if __name__ == "__main__":
    main()
