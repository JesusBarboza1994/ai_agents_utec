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


# Horario de atencion: fuente unica para los prompts y las validaciones de reservas.
# Indice = date.weekday(); cada franja es (apertura, cierre) y "24:00" es la medianoche.
# El documento del RAG (01_horarios_y_ubicacion.md) repite este horario: si cambia, hay
# que actualizarlo y reindexar.
HORARIO = {
    0: (),
    1: (("12:00", "15:30"), ("19:00", "23:00")),
    2: (("12:00", "15:30"), ("19:00", "23:00")),
    3: (("12:00", "15:30"), ("19:00", "23:00")),
    4: (("12:00", "16:00"), ("19:00", "24:00")),
    5: (("12:00", "16:00"), ("19:00", "24:00")),
    6: (("12:00", "17:00"),),
}

# La cocina toma el ultimo pedido 45 minutos antes de cerrar: un turno que empiece
# despues de eso no se puede atender.
MINUTOS_ANTES_DEL_CIERRE = 45


def _minutos(hora: str) -> int:
    """Minutos desde la medianoche de una hora HH:MM; lanza ValueError si no tiene ese formato."""
    horas, minutos = hora.split(":")
    if len(horas) != 2 or len(minutos) != 2:
        raise ValueError(hora)
    return int(horas) * 60 + int(minutos)


def _franjas_texto(franjas: tuple) -> str:
    """Franjas de un dia como texto ("12:00-15:30 y 19:00-23:00"); la medianoche se muestra 00:00."""
    return " y ".join(f"{inicio}-{'00:00' if fin == '24:00' else fin}" for inicio, fin in franjas)


def texto_horario() -> str:
    """El horario de la semana en una linea, agrupando dias consecutivos con las mismas franjas."""
    grupos: list[tuple[list[int], tuple]] = []
    for dia in range(7):
        if grupos and grupos[-1][1] == HORARIO[dia]:
            grupos[-1][0].append(dia)
        else:
            grupos.append(([dia], HORARIO[dia]))
    partes = []
    for dias, franjas in grupos:
        if len(dias) == 1:
            nombre = DIAS[dias[0]]
        elif len(dias) == 2:
            nombre = f"{DIAS[dias[0]]} y {DIAS[dias[1]]}"
        else:
            nombre = f"{DIAS[dias[0]]} a {DIAS[dias[-1]]}"
        partes.append(f"{nombre} {_franjas_texto(franjas)}" if franjas else f"{nombre} cerrado")
    return "; ".join(partes)


def turno_atendido(dia_semana: int, hora: str) -> bool:
    """True si un turno que empieza a `hora` cae dentro de una franja del dia, con margen para la cocina."""
    try:
        minuto = _minutos(hora)
    except (AttributeError, ValueError):
        return False
    return any(
        _minutos(inicio) <= minuto <= _minutos(fin) - MINUTOS_ANTES_DEL_CIERRE
        for inicio, fin in HORARIO[dia_semana]
    )


def fuera_de_horario(fecha_iso: str, hora: str | None = None) -> str | None:
    """Mensaje para el agente si la fecha cae en un dia cerrado o el turno esta fuera de horario; None si se atiende.

    Sin hora solo revisa el dia. Una fecha u hora con formato invalido devuelve None:
    ese error lo reporta la validacion de turno con su propio mensaje."""
    try:
        fecha = date.fromisoformat(fecha_iso)
    except (TypeError, ValueError):
        return None
    franjas = HORARIO[fecha.weekday()]
    dia = nombre_dia(fecha)
    if not franjas:
        return (f"El restaurante no atiende los {dia} ({fecha_iso} es {dia}). Ofrece otro día; "
                "no se preparó ninguna operación.")
    if not hora:
        return None
    try:
        _minutos(hora)
    except (AttributeError, ValueError):
        return None
    if turno_atendido(fecha.weekday(), hora):
        return None
    return (f"A las {hora} del {dia} {fecha_iso} el restaurante no atiende: ese día el horario es "
            f"{_franjas_texto(franjas)}. Ofrece otro turno u otro día; no se preparó ninguna operación.")


def turnos_del_dia(dia_semana: int, turnos: list[str]) -> list[str]:
    """De una lista de turnos HH:MM, los que se atienden ese dia de la semana."""
    return [turno for turno in turnos if turno_atendido(dia_semana, turno)]


def calendario_para_planificador() -> str:
    """Fecha y hora de Lima y los proximos 7 dias con su nombre, como texto para el planificador."""
    dias = ", ".join(f"{nombre} {dia.isoformat()}" for nombre, dia in proximos_dias())
    return f"Hoy es {describir_ahora()}. Proximos dias: {dias}."
