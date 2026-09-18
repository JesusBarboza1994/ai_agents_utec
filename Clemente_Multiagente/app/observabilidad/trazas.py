"""
Observabilidad de Clemente -- responsable: Adrian.

Dos niveles, a proposito:

  * **LangSmith** (Sesiones 19-20): traza automatica de cada llamada al LLM y a
    cada tool. No hay que instrumentar nada, basta con las variables de entorno
    LANGSMITH_TRACING / LANGSMITH_API_KEY / LANGSMITH_PROJECT.
  * **Trazas propias**: eventos de negocio que LangSmith no conoce -- que ruta
    eligio el enrutador y por que, cuanto tardo cada agente, cuantos casos se
    escalaron. Es lo que alimenta las metricas del informe final.

Hoy las trazas viven en memoria (buffer circular). Adrian puede cambiar el
destino (archivo, SQLite, LangSmith como run custom) tocando solo `registrar`.
"""

import json
import logging
import os
import time
from collections import deque
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any

from ..contratos import Traza

MAXIMO_TRAZAS = 500
_trazas: deque[Traza] = deque(maxlen=MAXIMO_TRAZAS)

# Las trazas viven en memoria y se pierden al reiniciar; LangSmith depende de
# tener clave y conexion. Este archivo es el registro que queda pase lo que
# pase: una linea JSON por turno, con el texto real de la conversacion.
ARCHIVO_CONVERSACIONES = Path(__file__).parent / "datos" / "conversaciones.jsonl"

log = logging.getLogger("clemente")


def configurar_observabilidad(app, config) -> None:
    """Se llama una vez desde `create_app()`."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
    )

    if config.langsmith_tracing and os.getenv("LANGSMITH_API_KEY"):
        os.environ["LANGSMITH_TRACING"] = "true"
        os.environ["LANGCHAIN_TRACING_V2"] = "true"   # compatibilidad con langchain<1
        os.environ["LANGSMITH_PROJECT"] = config.langsmith_project
        # A8: los spans automaticos (prompt, tools, salidas) pasan por la
        # redaccion PII antes de salir del proceso (app/seguridad/trazado.py).
        from ..seguridad.trazado import activar_redaccion
        modo_redaccion = activar_redaccion()
        log.info("LangSmith activo -- proyecto %s (redaccion: %s)", config.langsmith_project, modo_redaccion)
    elif config.langsmith_tracing:
        # Pedido pero sin clave: se apaga en vez de fallar en cada llamada.
        os.environ["LANGSMITH_TRACING"] = "false"
        log.warning(
            "LANGSMITH_TRACING=true pero falta LANGSMITH_API_KEY: "
            "las trazas NO se estan enviando a LangSmith"
        )
    else:
        log.info("LangSmith desactivado (LANGSMITH_TRACING=false)")

    log.info("Clemente iniciado con %s (%s)", config.agent_model, config.modelo)
    if config.falta_credencial:
        log.warning(
            "Falta %s en el .env: el agente no podra responder hasta que se defina",
            config.falta_credencial,
        )


def registrar(
    evento: str, sesion_id: str, agente: str = "",
    detalle: dict[str, Any] | None = None, duracion_ms: float = 0.0,
) -> Traza:
    """Registra un evento de negocio. Es la unica forma de escribir una traza."""
    from ..seguridad.pii import redactar_pii

    traza = Traza(
        evento=evento, sesion_id=sesion_id, agente=agente,
        detalle=redactar_pii(detalle or {}), duracion_ms=round(duracion_ms, 1),
    )
    _trazas.append(traza)
    log.info(
        "[%s] sesion=%s agente=%s %sms %s",
        evento, sesion_id, agente or "-", traza.duracion_ms, traza.detalle,
    )
    return traza


@contextmanager
def cronometro(evento: str, sesion_id: str, agente: str = "", **detalle):
    """Mide cuanto tarda un bloque y lo deja registrado, pase lo que pase dentro."""
    inicio = time.perf_counter()
    try:
        yield
    except Exception as error:
        registrar(
            "error", sesion_id, agente=agente,
            detalle={**detalle, "error": str(error)},
            duracion_ms=(time.perf_counter() - inicio) * 1000,
        )
        raise
    else:
        registrar(
            evento, sesion_id, agente=agente, detalle=detalle,
            duracion_ms=(time.perf_counter() - inicio) * 1000,
        )


def registrar_conversacion(
    sesion_id: str, mensaje: str, respuesta: str, agente: str,
    canal: str = "webchat", motivo_ruta: str = "", escalado: bool = False,
    duracion_ms: float = 0.0, plan: list[str] | None = None,
) -> None:
    """
    Escribe un turno completo (lo que dijo el cliente y lo que respondio Clemente)
    en `datos/conversaciones.jsonl`.

    `plan` guarda TODOS los pasos del turno, no solo el agente que lo cerro.
    Sin el, un turno atendido por dos agentes es indistinguible de uno atendido
    por uno solo en cuanto se reinicia el servidor -- y el plan es justamente lo
    que hay que poder demostrar de la arquitectura nueva. Es el mismo tipo de
    hueco que ya tuvimos con la ficha del cliente: el dato existia en ejecucion y
    no quedaba en el registro.

    Nunca puede tumbar una respuesta: si el disco falla, se registra el problema
    y la conversacion sigue. Por eso el try/except amplio.
    """
    from ..llm import modelo_activo

    turno = {
        "momento": datetime.now().isoformat(timespec="seconds"),
        "sesion_id": sesion_id,
        "canal": canal,
        "mensaje": mensaje,
        "agente": agente,
        # Los pasos en orden. Con un solo paso queda la lista de uno, no vacia:
        # asi el que lea el registro no tiene que adivinar si es que no hubo plan
        # o es que nadie lo anoto.
        "plan": list(plan) if plan else ([agente] if agente else []),
        "motivo_ruta": motivo_ruta,
        "respuesta": respuesta,
        "escalado": escalado,
        "duracion_ms": round(duracion_ms, 1),
        # `modelo_activo()` respeta AGENT_MODEL. Antes se leia
        # `ANTHROPIC_MODEL or OPENAI_MODEL`, que con las dos definidas en el
        # `.env` escribia el modelo equivocado en cada turno.
        "modelo": modelo_activo(),
    }
    try:
        ARCHIVO_CONVERSACIONES.parent.mkdir(parents=True, exist_ok=True)
        with ARCHIVO_CONVERSACIONES.open("a", encoding="utf-8") as archivo:
            print(json.dumps(turno, ensure_ascii=False), file=archivo)
    except OSError as error:
        log.warning("No se pudo escribir el registro de conversacion: %s", error)


def leer_conversaciones(limite: int = 100, sesion_id: str | None = None) -> list[dict]:
    """Ultimos turnos registrados, del mas antiguo al mas reciente."""
    if not ARCHIVO_CONVERSACIONES.exists():
        return []
    turnos = []
    with ARCHIVO_CONVERSACIONES.open(encoding="utf-8") as archivo:
        for linea in archivo:
            linea = linea.strip()
            if not linea:
                continue
            try:
                turno = json.loads(linea)
            except json.JSONDecodeError:
                continue
            if sesion_id is None or turno.get("sesion_id") == sesion_id:
                turnos.append(turno)
    return turnos[-limite:]


def ultimas_trazas(limite: int = 50, sesion_id: str | None = None) -> list[Traza]:
    """Devuelve las ultimas trazas en memoria, filtradas opcionalmente por sesion_id.

    No lee el historial persistido y pierde estos eventos al reiniciar el proceso."""
    trazas = [t for t in _trazas if sesion_id is None or t.sesion_id == sesion_id]
    return trazas[-limite:]


def metricas() -> dict[str, Any]:
    """
    Metricas del informe final (Modulo 8). El desglose por herramienta y los
    contadores de escalamiento y guardrail siguen la tabla de la guia de Jean
    (seccion 7.2 y 7.3). Falta el costo por conversacion, que sale de LangSmith.
    """
    respuestas = [t for t in _trazas if t.evento == "respuesta"]
    # El evento se llamaba "ruteo" cuando el orquestador era un enrutador. Al
    # pasar a "plan" (2026-09-07) esta linea siguio buscando el nombre viejo y
    # `ruteos_por_agente` quedo devolviendo {} sin que nada fallara. Se aceptan
    # los dos nombres para no perder las trazas de una version anterior que
    # sigan en el buffer.
    planes = [t for t in _trazas if t.evento in ("plan", "ruteo")]
    errores = [t for t in _trazas if t.evento == "error"]

    # Cada paso del plan cuenta para su agente: un turno de dos pasos suma en
    # los dos. Es lo que hay que contar para saber cuanto trabaja cada agente,
    # que no es lo mismo que cuantos turnos hubo.
    por_agente: dict[str, int] = {}
    for traza in planes:
        for paso in traza.detalle.get("plan") or ([traza.agente] if traza.agente else []):
            por_agente[paso] = por_agente.get(paso, 0) + 1

    # Cuantos turnos necesitaron mas de un agente. Es LA metrica que justifica
    # haber pasado de enrutador a orquestador: si sale 0 siempre, el plan no
    # esta haciendo nada que un router no hiciera.
    de_varios_pasos = sum(1 for t in planes if len(t.detalle.get("plan") or []) > 1)

    latencias = [t.duracion_ms for t in respuestas if t.duracion_ms]

    # Herramientas: cuantas veces se llamo cada una, cuanto tarda y cuantas fallan.
    # Lo emite el decorador `con_traza` de app/agentes/tools/__init__.py.
    por_tool: dict[str, dict[str, Any]] = {}
    for traza in (t for t in _trazas if t.evento == "tool"):
        nombre = traza.detalle.get("tool", "?")
        fila = por_tool.setdefault(nombre, {"llamadas": 0, "errores": 0, "ms": []})
        fila["llamadas"] += 1
        fila["errores"] += traza.detalle.get("estado") == "error"
        if traza.duracion_ms:
            fila["ms"].append(traza.duracion_ms)
    for fila in por_tool.values():
        tiempos = fila.pop("ms")
        fila["ms_promedio"] = round(sum(tiempos) / len(tiempos), 1) if tiempos else 0.0

    return {
        "conversaciones": len({t.sesion_id for t in _trazas}),
        "mensajes_atendidos": len(respuestas),
        "turnos_planificados": len(planes),
        "pasos_por_agente": por_agente,
        "turnos_de_varios_pasos": de_varios_pasos,
        "errores": len(errores),
        "latencia_media_ms": round(sum(latencias) / len(latencias), 1) if latencias else 0.0,
        "tools": por_tool,
        "escalamientos": sum(1 for t in _trazas if t.evento == "escalado"),
        "respuestas_descartadas_por_guardrail": sum(
            1 for t in _trazas
            if t.evento == "guardrail"
            or (t.evento in {"guardrail_input", "guardrail_output"}
                and not t.detalle.get("permitido", True))
        ),
        "guardrails_ai_bloqueos": sum(
            1 for t in _trazas
            if t.evento in {"guardrail_input", "guardrail_output"}
            and not t.detalle.get("permitido", True)
        ),
        "guardrails_ai_errores": sum(1 for t in _trazas if t.evento == "guardrail_error"),
    }
