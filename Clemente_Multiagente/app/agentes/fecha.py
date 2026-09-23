"""
Reloj del restaurante: fecha, hora y dia de la semana en America/Lima.

Hasta ahora la unica referencia temporal de los agentes era `date.today()`
pegado al system prompt al construir el agente. En Azure el proceso corre en
UTC, cinco horas adelante de Lima: entre las 19:00 y la medianoche el agente
creia que ya era "manana", y la fecha quedaba congelada hasta el siguiente
reinicio. Todo lo que necesite "hoy" pasa por aqui; `_reloj` es lo unico que
las pruebas reemplazan para fijar un instante.
"""

import unicodedata
from datetime import date, datetime, timedelta, timezone, tzinfo
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


def _zona_lima() -> tzinfo:
    """ZoneInfo de America/Lima; sin base de zonas (Windows, imagen slim) cae a UTC-5 fijo.

    Peru no tiene horario de verano, asi que el offset fijo es equivalente."""
    try:
        return ZoneInfo("America/Lima")
    except ZoneInfoNotFoundError:
        return timezone(timedelta(hours=-5), "America/Lima")


ZONA = _zona_lima()

# Indice = date.weekday(). Sin tildes para comparar, con tildes para el cliente.
DIAS = ("lunes", "martes", "miercoles", "jueves", "viernes", "sabado", "domingo")
DIAS_CON_TILDE = ("lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo")


def _reloj() -> datetime:
    """Instante actual con zona horaria de Lima; las pruebas lo reemplazan por uno fijo."""
    return datetime.now(ZONA)


def ahora() -> datetime:
    """Fecha y hora actuales en America/Lima, siempre con tzinfo."""
    return _reloj().astimezone(ZONA)


def hoy() -> date:
    """Fecha de hoy en Lima, no la del servidor."""
    return ahora().date()


def nombre_dia(fecha: date, con_tilde: bool = True) -> str:
    """Nombre en espanol del dia de la semana de `fecha`."""
    return (DIAS_CON_TILDE if con_tilde else DIAS)[fecha.weekday()]


def dia_declarado(texto: str) -> str | None:
    """Dia de la semana mencionado en `texto` ("el Sábado"), sin tilde, o None si no hay ninguno."""
    sin_tildes = "".join(
        c for c in unicodedata.normalize("NFD", texto or "") if unicodedata.category(c) != "Mn"
    ).lower()
    palabras = sin_tildes.replace(",", " ").split()
    return next((p for p in reversed(palabras) if p in DIAS), None)


def contradiccion_dia(dia: str, fecha_iso: str) -> str | None:
    """Mensaje para el agente si el dia declarado no cae en `fecha_iso`; None si coincide.

    Tambien devuelve None si no hay dia declarado o la fecha no es ISO valida:
    esos casos los rechaza la validacion de fecha, no esta. El texto manda
    preguntar al cliente; el servidor nunca elige entre los dos datos."""
    declarado = dia_declarado(dia)
    if not declarado:
        return None
    try:
        fecha = date.fromisoformat(fecha_iso)
    except (TypeError, ValueError):
        return None
    if nombre_dia(fecha, con_tilde=False) == declarado:
        return None
    return (
        f"El {DIAS_CON_TILDE[DIAS.index(declarado)]} no cae en la fecha {fecha_iso}, "
        f"que es {nombre_dia(fecha)}. Pregunta al cliente cuál de los dos es el correcto "
        "antes de continuar; no elijas por él. No se preparó ninguna operación."
    )


def es_pasada(fecha_iso: str) -> bool:
    """True si `fecha_iso` es anterior a hoy en Lima. Una fecha invalida lanza ValueError."""
    return date.fromisoformat(fecha_iso) < hoy()


def describir_ahora() -> str:
    """Fecha, dia y hora de este instante, como se le muestra al modelo en cada turno."""
    momento = ahora()
    return f"{nombre_dia(momento.date())} {momento.date().isoformat()}, {momento:%H:%M} (hora de Lima)"


def proximos_dias(cantidad: int = 7) -> list[tuple[str, date]]:
    """Los proximos `cantidad` dias a partir de manana, como pares (nombre, fecha)."""
    base = hoy()
    return [
        (nombre_dia(base + timedelta(days=i)), base + timedelta(days=i))
        for i in range(1, cantidad + 1)
    ]
