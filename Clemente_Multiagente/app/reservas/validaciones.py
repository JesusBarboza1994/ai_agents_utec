"""
Validacion y saneamiento de datos de reserva -- capa compartida por las
implementaciones de ServicioReservas (json, postgres) y por
app/agentes/autorizacion.py.

Por que existe: hasta ahora la unica validacion vivia en
app/agentes/autorizacion.py::proponer(), la capa que arma el resumen antes
del "CONFIRMO". Eso protege solo el camino LLM -> agente -> confirmacion.
Cualquier otro caller -- los endpoints de depuracion en
app/reservas/rutas.py, o WhatsApp el dia que llm_bridge deje de ser un mock
-- podia escribir en la base sin pasar por ningun chequeo.

nombre y notas se acotan en longitud y se limpian de caracteres de control
a proposito: ambos viajan de vuelta al LLM en cada turno futuro via
app/agentes/memoria.py::ficha_del_cliente(), asi que no son solo "datos
sucios" -- son superficie de inyeccion de prompt persistente.
"""

from __future__ import annotations

import hashlib
import re
import unicodedata
from datetime import date, timedelta

TURNOS_VALIDOS = ["12:00", "13:00", "14:00", "19:00", "20:00", "21:00", "22:00"]
ZONAS_VALIDAS = {"", "salon", "terraza", "barra"}

PERSONAS_MIN = 1
PERSONAS_MAX = 10
# Lo que dice la politica del restaurante (app/agentes/rag/documentos/03_politicas.md): hasta 30 dias de
# anticipacion y minimo 2 horas antes del turno. El agente se lo dice al cliente, asi que el codigo lo cumple.
DIAS_MAX_A_FUTURO = 30
HORAS_MIN_DE_ANTICIPACION = 2
NOMBRE_MAX = 100
NOTAS_MAX = 300
TELEFONO_RE = re.compile(r"^\+?[0-9]{7,15}$")
# Un nombre son letras (con tildes y enie), espacios, apostrofos, puntos y guiones: "Maria Jose", "O'Brien",
# "Jean-Luc", "Ana Ruiz Jr.". Sin esto un nombre como <script>...</script> o una frase con instrucciones se
# guardaba y volvia crudo en resumenes, tickets y en la ficha que lee el modelo.
NOMBRE_RE = re.compile(r"^[^\W\d_](?:[^\W\d_]|[ '.\-])*$")


class ReservaInvalida(ValueError):
    """Datos de reserva que no cumplen las reglas de negocio o de seguridad.

    Subclase de ValueError a proposito: el codigo que hoy atrapa
    ValueError (autorizacion.confirmar, las tools del agente) sigue
    funcionando sin cambios, pero quien quiera un mensaje especifico puede
    distinguirla con `except ReservaInvalida`.
    """


def _sanear_texto(valor: str, *, maximo: int, campo: str) -> str:
    """Recorta espacios y quita caracteres de control (categoria Unicode 'C'),
    conservando saltos de linea y tabs. Limite de longitud aplicado DESPUES
    de limpiar, para que rellenar con caracteres de control no lo evada."""
    limpio = "".join(c for c in valor if unicodedata.category(c)[0] != "C" or c in "\n\t")
    limpio = limpio.strip()
    if len(limpio) > maximo:
        raise ReservaInvalida(f"{campo} supera los {maximo} caracteres permitidos.")
    return limpio


def _validar_turno(fecha: str, hora: str, personas: int) -> None:
    """Comprueba turno, cantidad de personas y que la fecha tenga formato valido, no sea pasada (hora de Lima) ni exceda DIAS_MAX_A_FUTURO.

    Si la fecha es hoy, el turno tampoco puede haber empezado ya en Lima ni empezar en menos de
    HORAS_MIN_DE_ANTICIPACION horas."""
    if hora not in TURNOS_VALIDOS:
        raise ReservaInvalida(
            f"'{hora}' no es un turno valido. Turnos disponibles: {', '.join(TURNOS_VALIDOS)}."
        )
    if not isinstance(personas, int) or isinstance(personas, bool) or not (
        PERSONAS_MIN <= personas <= PERSONAS_MAX
    ):
        raise ReservaInvalida(
            f"El numero de personas debe ser un entero entre {PERSONAS_MIN} y {PERSONAS_MAX}."
        )
    try:
        fecha_obj = date.fromisoformat(fecha)
    except (ValueError, TypeError):
        raise ReservaInvalida("La fecha debe tener formato YYYY-MM-DD.")
    # Import diferido (no al tope del modulo): app.agentes importa, en cadena,
    # de vuelta a app.reservas.validaciones (via autorizacion.py). Al tope
    # del modulo eso rompe con ImportError circular si algo importa
    # validaciones.py primero; aqui adentro ya no hay ciclo porque para
    # cuando esta funcion se llama, todos los modulos terminaron de cargar.
    from ..agentes import fecha as reloj
    hoy = reloj.hoy()
    if fecha_obj < hoy:
        raise ReservaInvalida("La fecha no puede estar en el pasado.")
    if fecha_obj > hoy + timedelta(days=DIAS_MAX_A_FUTURO):
        raise ReservaInvalida(f"Solo se aceptan reservas hasta {DIAS_MAX_A_FUTURO} dias a futuro.")
    if fecha_obj == hoy:
        ahora = reloj.ahora()
        horas, minutos = (int(parte) for parte in hora.split(":"))
        minutos_para_el_turno = (horas * 60 + minutos) - (ahora.hour * 60 + ahora.minute)
        if minutos_para_el_turno <= 0:
            raise ReservaInvalida("Ese horario de hoy ya paso. Elige un turno mas tarde u otro dia.")
        if minutos_para_el_turno < HORAS_MIN_DE_ANTICIPACION * 60:
            raise ReservaInvalida(
                f"Las reservas se hacen con al menos {HORAS_MIN_DE_ANTICIPACION} horas de anticipacion: "
                "ese turno empieza demasiado pronto. Elige un turno mas tarde u otro dia.")


def validar_cambio_turno(*, fecha: str, hora: str, personas: int) -> None:
    """Subconjunto de validar_datos_reserva para modificar_reserva, que no
    trae nombre/telefono/notas -- solo el turno cambia."""
    _validar_turno(fecha, hora, personas)


def validar_datos_reserva(
    *, nombre: str, telefono: str, fecha: str, hora: str, personas: int,
    zona: str = "", notas: str = "",
) -> dict:
    """Valida y devuelve los datos saneados, listos para persistir.

    Lanza ReservaInvalida con un mensaje legible para mostrar directo al
    cliente (via el agente) o en la respuesta HTTP 400 de los endpoints de
    depuracion.
    """
    _validar_turno(fecha, hora, personas)

    telefono = (telefono or "").strip()
    if not TELEFONO_RE.match(telefono):
        raise ReservaInvalida(
            "El telefono debe tener entre 7 y 15 digitos, opcionalmente con '+' inicial."
        )

    nombre = _sanear_texto(nombre or "", maximo=NOMBRE_MAX, campo="El nombre")
    if not nombre:
        raise ReservaInvalida("El nombre no puede estar vacio.")
    if not NOMBRE_RE.match(nombre):
        raise ReservaInvalida("El nombre solo puede llevar letras, espacios, apostrofos, puntos y guiones.")

    notas = _sanear_texto(notas or "", maximo=NOTAS_MAX, campo="Las notas")

    zona = (zona or "").strip()
    if zona not in ZONAS_VALIDAS:
        raise ReservaInvalida(f"'{zona}' no es una zona valida (salon, terraza o barra).")

    return {
        "nombre": nombre, "telefono": telefono, "fecha": fecha, "hora": hora,
        "personas": personas, "zona": zona, "notas": notas,
    }


def clave_idempotencia(telefono: str, fecha: str, hora: str, personas: int) -> str:
    """Clave natural de deduplicacion: mismo cliente + mismo turno + mismo
    tamano de grupo se consideran el mismo pedido de reserva. No depende de
    que el caller mande ningun header -- se calcula siempre igual, asi que
    un reintento de webhook o un doble tap producen la misma clave sin
    coordinacion extra."""
    base = f"{(telefono or '').strip()}|{fecha}|{hora}|{personas}"
    return hashlib.sha256(base.encode("utf-8")).hexdigest()[:32]
