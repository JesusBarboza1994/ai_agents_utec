"""Reglas deterministas del servicio de Guardrails: amenazas, discriminacion e inyecciones de instrucciones.

Son solo expresiones regulares, sin modelos, a proposito: se prueban en el proceso principal
(tests/test_guardrails_patrones.py) sin cargar Guardrails AI ni pesos de 1 GB, y corren antes
de los clasificadores porque el clasificador de jailbreak no separa los mensajes cortos: en la
prueba de estres del 2026-09-25 con el umbral del servicio (0.81) solo detectaba el prompt largo
clasico de "DAN" y ninguna de 12 inyecciones cortas; bajando el umbral bloqueaba tambien
"Quiero reservar una mesa". Las reglas cubren las frases tipicas; no son una garantia.

Lo que NO bloquean, a proposito: los insultos comunes ("inutil", "imbecil"). Un cliente enojado
insulta y aun asi tiene un reclamo valido; en la prueba el agente los contesto con calma y registro
el reclamo, y bloquearlos habria dejado sin atender a quien mas lo necesita.
"""

import re

_VERBOS_VIOLENTOS = r"(?:matar|asesinar|golpear|violar|quemar|incendiar|balear|apu[ñn]alar|degollar)"
# "vamos a matar el hambre", "para quemar las calorias": modismos, no amenazas.
_MODISMOS = r"(?:el\s+hambre|la\s+sed|el\s+tiempo|el\s+aburrimiento|el\s+antojo|el\s+estr[eé]s|las\s+calor[ií]as|la\s+resaca)"

AMENAZA_GRAVE = re.compile(
    # "te voy a matar", "los quemamos": pronombre de persona + verbo de violencia
    rf"\b(?:te|los|las|lo|la|les)\s+(?:voy\s+a\s+|vamos\s+a\s+)?{_VERBOS_VIOLENTOS}\w*\b"
    # "voy a quemar el local", "vamos a matar a alguien": intencion + verbo, salvo modismos
    rf"|\b(?:voy|vamos|van|iremos)\s+a\s+{_VERBOS_VIOLENTOS}\w*\b(?!\s+{_MODISMOS})"
    # "van a arder", "esto va a explotar" con intencion de dano al local
    r"|\b(?:pondr[eé]|voy\s+a\s+poner|vamos\s+a\s+poner)\s+una\s+bomba\b"
    # discriminacion grave hacia personas por su origen o su orientacion
    r"|\b(?:negr[oa]s?|indi[oa]s?|cholos?|cholas?|serran[oa]s?|maric[oó]n(?:es)?|marimach[oa]s?|sudacas?|chin[oa]s?)\s+de\s+(?:mierda|porquer[ií]a)\b",
    re.I,
)

INYECCION = re.compile(
    # "ignora todas tus instrucciones", "olvida las reglas": ordenes de descartar lo que rige al asistente
    r"\b(?:ignor|olvid|omit|descart|salt)[aeiáéíoó]\w*\s+(?:todas?\s+)?(?:tus|las|los|sus|el)\s+(?:instrucciones|reglas|normas|indicaciones|restricciones|l[ií]mites|filtros|prompt)\b"
    r"|\bignore\s+(?:all\s+)?(?:the\s+)?(?:previous|prior|above|your)\s+(?:instructions|rules|prompts?)\b"
    # pedir el prompt o las reglas internas
    r"|\b(?:prompt|instrucciones)\s+(?:del\s+)?sistema\b|\bsystem\s+prompt\b|\bhidden\s+rules\b|\breglas\s+ocultas\b"
    r"|\b(?:repite|muestra|revela|imprime|dime)\b[^.?!]{0,60}\b(?:texto|instrucciones|reglas)\b[^.?!]{0,60}\b(?:antes|arriba|anterior|ocult\w+)\b"
    # cambiar de rol: "a partir de ahora eres...", "actua como DAN", "modo desarrollador"
    r"|\b(?:a\s+partir\s+de\s+ahora|desde\s+ahora)\s+(?:eres|ser[aá]s|act[uú]as|te\s+comportas)\b"
    r"|\bolvida\s+que\s+eres\b"
    r"|\b(?:act[uú]a|comp[oó]rtate|finge\s+ser|haz\s+de)\s+como\s+(?:(?:un|una)\s+)?(?:\w+\s+){0,3}sin\s+(?:reglas|restricciones|filtros|l[ií]mites)\b"
    r"|(?-i:\bDAN\b)|\bmodo\s+(?:desarrollador|dios)\b|\bdeveloper\s+mode\b|\bjailbreak\b"
    # desactivar la seguridad del propio sistema
    r"|\bdesactiv\w+\s+(?:la\s+|el\s+|las\s+|los\s+)?(?:confirmaci[oó]n|verificaci[oó]n|seguridad|reglas|filtros|guardrails)\b"
    r"|\b(?:saltarme|saltarte|eludir|evadir|burlar|bypass)\w*\s+(?:tus|las|los)\s+(?:reglas|restricciones|filtros|medidas|controles)\b"
    # cabeceras falsas de instrucciones
    r"|###\s*system|\bnuevas?\s+instrucci(?:[oó]n|ones)\s*:|\bsystem\s*:\s*\w"
    # pedir credenciales
    r"|\bapi[\s_-]?key\b|\bclave\s+(?:de\s+la\s+)?api\b|\btoken\s+de\s+(?:trello|openai|twilio)\b",
    re.I,
)


# SOLO para la salida: lo que Clemente responde nunca lleva un insulto. En la entrada no se bloquea:
# ahi un insulto puede venir con un reclamo valido.
INSULTO_EN_SALIDA = re.compile(r"\b(?:idiotas?|imb[eé]ciles?|est[uú]pid[oa]s?|mierda|put[ao]s?|malparid[oa]s?)\b", re.I)


def motivo_de_bloqueo_en_salida(texto: str) -> tuple[str, str] | None:
    """Devuelve (validador, motivo) si la respuesta de Clemente trae una amenaza o un insulto, o None."""
    if AMENAZA_GRAVE.search(texto):
        return "ToxicidadES", "Salida con amenaza, acoso grave o discriminación"
    if INSULTO_EN_SALIDA.search(texto):
        return "InsultoES", "Salida con un insulto"
    return None


def motivo_de_bloqueo(texto: str) -> tuple[str, str] | None:
    """Devuelve (validador, motivo) si una regla determinista rechaza el texto, o None si ninguna aplica."""
    if AMENAZA_GRAVE.search(texto):
        return "ToxicidadES", "Amenaza, acoso grave o discriminación detectada"
    if INYECCION.search(texto):
        return "InyeccionES", "Instrucción para saltarse las reglas o pedir datos internos"
    return None
