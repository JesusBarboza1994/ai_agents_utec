"""Adaptador al servicio aislado de Guardrails AI.

Guardrails AI vive en otro proceso porque DetectJailbreak y la pila de
evaluacion del proyecto exigen versiones incompatibles de Click y
OpenTelemetry. Este adaptador mantiene esa dependencia fuera del agente.
"""

import os
from dataclasses import dataclass

import requests

from ..observabilidad.trazas import registrar


@dataclass(frozen=True)
class ResultadoEntrada:
    """Resultado del cliente de validacion: permiso, texto, motivo y disponibilidad.

    Se usa tambien para salida. permitido=True con disponible=False indica
    que no hubo validacion externa, no que el contenido haya sido aprobado por IA."""
    permitido: bool
    texto: str
    motivo: str = ""
    disponible: bool = True


def falla_cerrada() -> bool:
    """True si un fallo del validador de ENTRADA debe bloquear el mensaje (por defecto si).

    Se apaga con CLEMENTE_GUARDRAILS_FALLA_CERRADA=0. Solo aplica cuando el servicio
    esta configurado: sin URL el validador externo esta desactivado a proposito."""
    return os.getenv("CLEMENTE_GUARDRAILS_FALLA_CERRADA", "1") != "0"


def validar_entrada(texto: str, sesion_id: str, config) -> ResultadoEntrada:
    """Solicita al servicio Guardrails AI la validacion de entrada y registra su resultado.

    Devuelve ResultadoEntrada con el texto validado cuando se permite. Sin URL el
    validador esta desactivado y el mensaje continua (disponible=False). Con URL
    configurada, un timeout, un error HTTP o una respuesta ilegible BLOQUEAN el
    mensaje antes de llegar al modelo, salvo CLEMENTE_GUARDRAILS_FALLA_CERRADA=0.
    Esta funcion no ejecuta los controles PII locales: el canal debe aplicarlos aparte.
    """
    if not config.guardrails_url:
        return ResultadoEntrada(True, texto, "Guardrails AI deshabilitado", False)
    try:
        respuesta = requests.post(
            f"{config.guardrails_url.rstrip('/')}/validate/input",
            json={"text": texto},
            headers={"Authorization": f"Bearer {config.guardrails_token}"},
            timeout=config.guardrails_timeout,
        )
        respuesta.raise_for_status()
        datos = respuesta.json()
        permitido = bool(datos.get("valid", False))
        resultado = ResultadoEntrada(
            permitido=permitido,
            texto=str(datos.get("validated_output") or texto) if permitido else texto,
            motivo=str(datos.get("reason") or ""),
        )
        registrar(
            "guardrail_input", sesion_id, agente="guardrails_ai",
            detalle={"permitido": permitido, "motivo": resultado.motivo},
        )
        return resultado
    except (requests.RequestException, ValueError, TypeError) as error:
        cerrada = falla_cerrada()
        registrar(
            "guardrail_error", sesion_id, agente="guardrails_ai",
            detalle={"error": type(error).__name__,
                     "politica": "bloquea el mensaje" if cerrada else "fail-open con controles deterministas"},
        )
        return ResultadoEntrada(not cerrada, texto, "Validador no disponible", False)


def validar_salida(texto: str, sesion_id: str, config) -> ResultadoEntrada:
    """Solicita validacion de toxicidad de salida y devuelve la decision al canal.

    El canal sustituye el texto cuando permitido=False. Sin URL o ante fallo
    de transporte/respuesta devuelve permitido=True y disponible=False: no
    garantiza bloqueo de toxicidad cuando el servicio no esta disponible. Aqui
    NO falla cerrada, a diferencia de la entrada: el turno ya se ejecuto y
    tapar la respuesta dejaria una reserva hecha que el cliente nunca ve.
    Registra validacion o error; no redacta PII por si misma.
    """
    if not config.guardrails_url:
        return ResultadoEntrada(True, texto, "Guardrails AI deshabilitado", False)
    try:
        respuesta = requests.post(
            f"{config.guardrails_url.rstrip('/')}/validate/output", json={"text": texto},
            headers={"Authorization": f"Bearer {config.guardrails_token}"},
            timeout=config.guardrails_timeout,
        )
        respuesta.raise_for_status()
        datos = respuesta.json()
        permitido = bool(datos.get("valid", False))
        registrar("guardrail_output", sesion_id, agente="guardrails_ai",
                  detalle={"permitido": permitido, "motivo": datos.get("reason", "")})
        return ResultadoEntrada(permitido, str(datos.get("validated_output") or texto),
                                str(datos.get("reason") or ""))
    except (requests.RequestException, ValueError, TypeError) as error:
        registrar("guardrail_error", sesion_id, agente="guardrails_ai",
                  detalle={"error": type(error).__name__, "fase": "salida"})
        return ResultadoEntrada(True, texto, "Validador no disponible", False)
