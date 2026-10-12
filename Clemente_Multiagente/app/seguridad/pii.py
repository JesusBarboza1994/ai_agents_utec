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
    # Acepta el numero junto o con espacios/guiones ("963 351 432", "963-351-432"), como lo escriben los clientes.
    "telefono": re.compile(r"(?<!\d)(?:\+?51[ -]?)?9(?:[ -]?\d){8}(?!\d)"),
}
# El correo de contacto del restaurante no es un dato personal: el cliente tiene que poder leerlo para escribirle.
# Debe coincidir con CORREO_RESTAURANTE de app/agentes/prompts.py (lo comprueba una prueba).
CORREOS_PUBLICOS = frozenset({"reservas@clemente.demo"})


def _luhn_valido(digitos: str) -> bool:
    """True si la secuencia pasa la verificacion de Luhn, la que cumple todo numero de tarjeta real."""
    total = 0
    for posicion, caracter in enumerate(reversed(digitos)):
        digito = int(caracter)
        if posicion % 2:
            digito = digito * 2 - 9 if digito > 4 else digito * 2
        total += digito
    return total % 10 == 0


def _es_tarjeta(coincidencia: re.Match) -> bool:
    """Una secuencia de 13 a 19 digitos es tarjeta solo si pasa Luhn y no es el id de WhatsApp de un cliente.

    Sin esto el BSUID (whatsapp-PE.1028522870210512) salia como [REDACTED_TARJETA] en las trazas, y cualquier numero
    largo (un codigo de pedido, una operacion) bloqueaba el mensaje del cliente con "No envies tarjetas".
    El BSUID se reconoce por su prefijo de pais: dos letras y un punto pegados a los digitos."""
    inicio = coincidencia.start()
    if re.search(r"[A-Za-z]{2}\.$", coincidencia.string[max(0, inicio - 3):inicio]):
        return False
    return _luhn_valido(re.sub(r"\D", "", coincidencia.group()))


def pii_prohibida(texto: str) -> str | None:
    """Devuelve el primer tipo de tarjeta o secreto detectado por regex, o None.

    El telefono de contacto no se bloquea. Son patrones locales, no una
    garantia de deteccion de todos los datos sensibles posibles."""
    for tipo, patron in PATRONES_BLOQUEO.items():
        if tipo == "tarjeta":
            if any(_es_tarjeta(m) for m in patron.finditer(texto)):
                return tipo
        elif patron.search(texto):
            return tipo
    return None


def _es_publico(correo: str) -> bool:
    """True si el correo es el de contacto del restaurante, que se muestra tal cual."""
    return correo.lower() in CORREOS_PUBLICOS


def detectar_correos_privados(texto: str) -> list[dict]:
    """Correos del texto en el formato de PIIMiddleware (tipo, valor, inicio, fin), sin el del restaurante."""
    return [
        {"type": "email", "value": m.group(), "start": m.start(), "end": m.end()}
        for m in PATRONES_REDACTAR["email"].finditer(texto)
        if not _es_publico(m.group())
    ]


def redactar_pii(valor: Any, incluir_telefono: bool = True) -> Any:
    """Sustituye patrones de PII por marcadores en texto y estructuras anidadas.

    Recorre valores de dict, list y tuple; conserva claves y otros tipos.
    incluir_telefono=False permite conservar ese dato operativo. Devuelve
    una nueva estructura sin modificar la recibida; no redacta nombres propios
    ni el correo de contacto del restaurante (CORREOS_PUBLICOS)."""
    if isinstance(valor, str):
        resultado = valor
        patrones = {**PATRONES_BLOQUEO, **PATRONES_REDACTAR}
        for tipo, patron in patrones.items():
            if tipo == "telefono" and not incluir_telefono:
                continue
            if tipo == "email":
                resultado = patron.sub(
                    lambda m: m.group() if _es_publico(m.group()) else "[REDACTED_EMAIL]", resultado)
            elif tipo == "tarjeta":
                resultado = patron.sub(lambda m: "[REDACTED_TARJETA]" if _es_tarjeta(m) else m.group(), resultado)
            else:
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
    """PIIMiddleware protege correo y tarjetas en input, output y tools.

    El correo usa nuestro detector para dejar visible el del restaurante: el detector de LangChain lo tapaba en la
    respuesta y en el catalogo, y el cliente leia "[REDACTED_EMAIL]" donde debia ir el contacto."""
    from langchain.agents.middleware import PIIMiddleware

    comun = dict(strategy="redact", apply_to_input=True,
                 apply_to_output=True, apply_to_tool_results=True)
    return [PIIMiddleware("email", detector=detectar_correos_privados, **comun),
            PIIMiddleware("credit_card", **comun)]
