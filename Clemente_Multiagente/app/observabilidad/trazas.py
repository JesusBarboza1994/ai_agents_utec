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

import logging
import os
import time
from collections import deque
from contextlib import contextmanager
from typing import Any

from ..contratos import Traza

MAXIMO_TRAZAS = 500
_trazas: deque[Traza] = deque(maxlen=MAXIMO_TRAZAS)

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
        log.info("LangSmith activo -- proyecto %s", config.langsmith_project)
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
    traza = Traza(
        evento=evento, sesion_id=sesion_id, agente=agente,
        detalle=detalle or {}, duracion_ms=round(duracion_ms, 1),
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


def ultimas_trazas(limite: int = 50, sesion_id: str | None = None) -> list[Traza]:
    trazas = [t for t in _trazas if sesion_id is None or t.sesion_id == sesion_id]
    return trazas[-limite:]


def metricas() -> dict[str, Any]:
    """
    Metricas minimas para el informe final. Adrian las va a ampliar: aciertos de
    ruteo, tasa de escalamiento, latencia por agente, costo por conversacion.
    """
    respuestas = [t for t in _trazas if t.evento == "respuesta"]
    ruteos = [t for t in _trazas if t.evento == "ruteo"]
    errores = [t for t in _trazas if t.evento == "error"]

    por_agente: dict[str, int] = {}
    for traza in ruteos:
        por_agente[traza.agente] = por_agente.get(traza.agente, 0) + 1

    latencias = [t.duracion_ms for t in respuestas if t.duracion_ms]
    return {
        "conversaciones": len({t.sesion_id for t in _trazas}),
        "mensajes_atendidos": len(respuestas),
        "ruteos_por_agente": por_agente,
        "errores": len(errores),
        "latencia_media_ms": round(sum(latencias) / len(latencias), 1) if latencias else 0.0,
    }
