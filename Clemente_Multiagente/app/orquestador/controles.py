"""
Auditorias sobre la respuesta final del turno -- responsables: Christian, Jean.

Controles conversacionales de la seccion 3.2 del plan posterior a la reunion
del 17/09: observan lo que el modelo dijo y lo dejan en la traza. A proposito
NO bloquean: son heuristicas de expresion regular, y un "hola" cortes o la
frase "no puedo ofrecer descuentos" no pueden costarle la respuesta al
cliente. Lo que si garantizan es que un reinicio o una promesa quede
registrado con su sesion, para que la evaluacion y el personal lo vean.

Los controles duros (permisos, confirmacion, HITL) siguen siendo del
servidor y no dependen de estos patrones.
"""

import re

from ..observabilidad.trazas import registrar

_SALUDO = re.compile(
    r"^\s*[¡!]*\s*(hola|buenas|buenos d[ií]as|buenas tardes|buenas noches|bienvenid[oa]s?)\b",
    re.I,
)
_PRESENTACION = re.compile(
    r"(soy clemente|en qu[eé] (te |le |les |los )?puedo ayudar|c[oó]mo (te |le |les )?puedo ayudar|bienvenid)",
    re.I,
)
_PROMESA = re.compile(
    r"\b(te|le|les)\s+(regal\w*|invit\w*|ofre[zc]\w*|descont\w*|obsequi\w*)\b"
    r"|\b(descuento|descuentos|cortes[ií]a|gratis|sin costo|2x1|por cuenta de la casa|de regalo)\b",
    re.I,
)
_NEGACION = re.compile(r"\b(no|ni|nunca|tampoco|sin)\b", re.I)


def parece_reinicio(texto: str, historial: list[dict] | None) -> bool:
    """True si hay hilo previo y la respuesta saluda y se presenta como si fuera el primer mensaje.

    Un saludo solo no cuenta: hace falta ademas la presentacion o el
    "en que puedo ayudarte" que delata que el modelo olvido la tarea."""
    if not historial or not texto:
        return False
    return bool(_SALUDO.match(texto) and _PRESENTACION.search(texto))


def parece_promesa_no_autorizada(texto: str) -> bool:
    """True si alguna oracion ofrece un beneficio (descuento, cortesia, regalo) sin negarlo.

    Una negacion antes del beneficio en la misma oracion ("no puedo ofrecer
    descuentos") no cuenta. Es una heuristica: puede marcar una explicacion
    de politica como promesa; por eso solo se audita."""
    for oracion in re.split(r"(?<=[.!?])\s+", texto or ""):
        coincidencia = _PROMESA.search(oracion)
        if coincidencia and not _NEGACION.search(oracion[:coincidencia.start()]):
            return True
    return False


def auditar_salida(texto: str, historial: list[dict] | None, sesion_id: str, agente: str) -> list[str]:
    """Registra en la traza los controles que la respuesta dispara y devuelve sus nombres.

    Eventos posibles: "reinicio_detectado" y "promesa_no_autorizada". No
    modifica el texto; el llamador decide si hace algo mas con la lista."""
    eventos = []
    if parece_reinicio(texto, historial):
        eventos.append("reinicio_detectado")
    if parece_promesa_no_autorizada(texto):
        eventos.append("promesa_no_autorizada")
    for evento in eventos:
        registrar(evento, sesion_id, agente=agente, detalle={"texto": texto[:200]})
    return eventos
