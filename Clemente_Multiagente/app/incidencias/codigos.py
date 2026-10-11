"""Codigos de los casos que el cliente recibe: `I-` para reclamos y `G-` para solicitudes de grupo.

Una solicitud de mas de 8 personas nace con su codigo `G-` cuando se pausa para que el personal la apruebe, y la
tarjeta de Trello que se abre despues de aprobarla lleva ese mismo codigo: el cliente, el panel del personal y el
tablero hablan del mismo caso. Los reclamos siguen con `I-`.
"""
import re
import uuid

PREFIJO_INCIDENCIA = "I"
PREFIJO_GRUPO = "G"
PREFIJOS = (PREFIJO_INCIDENCIA, PREFIJO_GRUPO)

# Seis caracteres hexadecimales en mayuscula tras el prefijo: lo que `nuevo_codigo` genera y lo unico que se acepta
# cuando alguien pide usar un codigo concreto.
CODIGO_VALIDO = re.compile(r"[IG]-[0-9A-F]{6}")


def nuevo_codigo(prefijo: str = PREFIJO_INCIDENCIA) -> str:
    """Genera un codigo `<prefijo>-XXXXXX`; un prefijo que no sea `I` ni `G` es un error de programacion."""
    if prefijo not in PREFIJOS:
        raise ValueError(f"Prefijo de codigo desconocido: {prefijo!r}")
    return f"{prefijo}-{uuid.uuid4().hex[:6].upper()}"


def codigo_admitido(codigo: str | None) -> bool:
    """True si `codigo` tiene la forma `I-XXXXXX` o `G-XXXXXX`; cualquier otra cosa se ignora y se genera uno nuevo."""
    return bool(codigo) and CODIGO_VALIDO.fullmatch(codigo) is not None
