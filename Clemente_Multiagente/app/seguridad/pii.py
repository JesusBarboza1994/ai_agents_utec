"""Política local de PII: protege secretos sin romper las reservas."""

import re
from typing import Any

PATRONES_BLOQUEO = {
    "tarjeta": re.compile(r"(?<!\d)(?:\d[ -]?){13,19}(?!\d)"),
    "secreto": re.compile(r"\b(?:sk-[A-Za-z0-9_-]{16,}|(?:api[_-]?key|token|password)\s*[:=]\s*\S+)", re.I),
}
PATRONES_REDACTAR = {
    "email": re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.I),
    "dni": re.compile(r"(?<!\d)\d{8}(?!\d)"),
    "ip": re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b"),
    "mac": re.compile(r"\b(?:[0-9A-F]{2}[:-]){5}[0-9A-F]{2}\b", re.I),
    "telefono": re.compile(r"(?<!\d)(?:\+?51[ -]?)?9\d{8}(?!\d)"),
}


def pii_prohibida(texto: str) -> str | None:
    """Devuelve el primer tipo de tarjeta o secreto detectado por regex, o None.

    El telefono de contacto no se bloquea. Son patrones locales, no una
    garantia de deteccion de todos los datos sensibles posibles."""
    for tipo, patron in PATRONES_BLOQUEO.items():
        if patron.search(texto):
            return tipo
    return None


def redactar_pii(valor: Any, incluir_telefono: bool = True) -> Any:
    """Sustituye patrones de PII por marcadores en texto y estructuras anidadas.

    Recorre valores de dict, list y tuple; conserva claves y otros tipos.
    incluir_telefono=False permite conservar ese dato operativo. Devuelve
    una nueva estructura sin modificar la recibida; no redacta nombres propios."""
    if isinstance(valor, str):
        resultado = valor
        patrones = {**PATRONES_BLOQUEO, **PATRONES_REDACTAR}
        for tipo, patron in patrones.items():
            if tipo == "telefono" and not incluir_telefono:
                continue
            resultado = patron.sub(f"[REDACTED_{tipo.upper()}]", resultado)
        return resultado
    if isinstance(valor, dict):
        return {k: redactar_pii(v, incluir_telefono) for k, v in valor.items()}
    if isinstance(valor, list):
        return [redactar_pii(v, incluir_telefono) for v in valor]
    if isinstance(valor, tuple):
        return tuple(redactar_pii(v, incluir_telefono) for v in valor)
    return valor


def middleware_pii() -> list:
    """PIIMiddleware protege correo y tarjetas en input, output y tools."""
    from langchain.agents.middleware import PIIMiddleware

    comun = dict(strategy="redact", apply_to_input=True,
                 apply_to_output=True, apply_to_tool_results=True)
    return [PIIMiddleware("email", **comun), PIIMiddleware("credit_card", **comun)]
