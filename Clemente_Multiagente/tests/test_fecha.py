"""
Fecha, hora y dia de la semana: el reloj de Lima y la validacion del servidor.

Observacion A7 de la reunion del 17/09: "manana" y "el viernes 13" se
resolvian de memoria, con la fecha del servidor (UTC en Azure) congelada al
construir el agente. Aqui se prueba que el reloj es de Lima, que la tool lo
expone de forma determinista y que una contradiccion dia/fecha NO deja una
propuesta que se pueda confirmar. Todas corren sin modelo ni credencial.
"""

from datetime import datetime, timezone

import pytest

from app.agentes import fecha as reloj


class _RuntimeFalso:
    """Imita lo unico que las tools usan del ToolRuntime que inyecta create_agent."""

    def __init__(self, contexto):
        """Expone el contexto recibido mediante el atributo context que leen las tools."""
        self.context = contexto


class _ServicioQueNoDebeEscribir:
    """Servicio de reservas que falla si alguien intenta consultarlo o escribir."""

    def consultar_disponibilidad(self, *_args, **_kwargs):
        """Falla: con una contradiccion de fecha no debe consultarse disponibilidad."""
        raise AssertionError("no se debe consultar disponibilidad con una fecha contradictoria")

    def obtener_reserva(self, *_args, **_kwargs):
        """Falla: la prueba no espera lecturas de reservas."""
        raise AssertionError("no se debe leer una reserva")


class _ServicioConMesa:
    """Servicio minimo que siempre tiene una mesa libre; solo sirve para preparar propuestas."""

    def consultar_disponibilidad(self, *_args, **_kwargs):
        """Devuelve una opcion para que `proponer` llegue a generar el resumen."""
        return [object()]


def _fijar(monkeypatch, instante_utc: datetime) -> None:
    """Fija el reloj del modulo en un instante UTC; `ahora()` lo convierte a Lima."""
    monkeypatch.setattr(reloj, "_reloj", lambda: instante_utc)


# --------------------------------------------------------------------------
# El reloj
# --------------------------------------------------------------------------

def test_el_reloj_es_de_lima_y_no_del_servidor(monkeypatch):
    """
    A las 03:30 UTC del martes 22 todavia es lunes 21 a las 22:30 en Lima.

    Es exactamente la franja (19:00-24:00 de Lima) en la que `date.today()`
    en un servidor UTC adelantaba un dia.
    """
    _fijar(monkeypatch, datetime(2026, 9, 22, 3, 30, tzinfo=timezone.utc))

    assert reloj.hoy().isoformat() == "2026-09-21"
    assert reloj.nombre_dia(reloj.hoy()) == "lunes"
    assert reloj.describir_ahora() == "lunes 2026-09-21, 22:30 (hora de Lima)"


def test_dia_declarado_tolera_tildes_mayusculas_y_articulos():
    """Verifica que dia declarado tolera tildes mayusculas y articulos."""
    assert reloj.dia_declarado("Sábado") == "sabado"
    assert reloj.dia_declarado("el viernes") == "viernes"
    assert reloj.dia_declarado("este Miércoles, por favor") == "miercoles"
    assert reloj.dia_declarado("") is None
    assert reloj.dia_declarado("el finde") is None


@pytest.mark.parametrize(
    "dia, fecha_iso, contradice",
    [
        ("viernes", "2026-09-25", False),   # el 25/09/2026 es viernes
        ("sábado", "2026-09-25", True),
        ("Viernes", "2026-09-26", True),    # el 26 es sabado
        ("", "2026-09-25", False),          # sin dia no hay que comparar
        ("viernes", "no-es-fecha", False),  # la fecha invalida la rechaza otra validacion
    ],
)
def test_contradiccion_entre_dia_y_fecha(dia, fecha_iso, contradice):
    """Verifica que contradiccion entre dia y fecha."""
    aviso = reloj.contradiccion_dia(dia, fecha_iso)
    assert bool(aviso) is contradice
    if aviso:
        # El servidor pide preguntar; nunca elige uno de los dos.
        assert "Pregunta al cliente" in aviso
        assert fecha_iso in aviso


def test_la_tool_devuelve_hoy_manana_y_los_proximos_dias(monkeypatch):
    """La tool es determinista y trae la zona: el modelo no tiene que calcular nada."""
    from app.agentes.contexto import ContextoConversacion
    from app.agentes.tools.fecha_tools import get_current_datetime

    _fijar(monkeypatch, datetime(2026, 9, 21, 19, 5, tzinfo=reloj.ZONA))

    salida = get_current_datetime.func(runtime=_RuntimeFalso(ContextoConversacion(sesion_id="t-f")))

    assert "Hoy es lunes 2026-09-21, 19:05 (hora de Lima)" in salida
    assert "Mañana es martes 2026-09-22" in salida
    assert "domingo 2026-09-27" in salida
    # El modelo no le pasa argumentos: solo el runtime, que el no ve.
    assert get_current_datetime.args == {}


# --------------------------------------------------------------------------
# Lo que hace cumplir el servidor
# --------------------------------------------------------------------------

def test_una_contradiccion_no_deja_propuesta_que_confirmar(tmp_path, monkeypatch):
    """
    "El viernes 26" cuando el 26 es sabado: no se prepara nada, no hay codigo
    CONFIRMO, y queda registrado en el contexto y en la traza.
    """
    from app.agentes import autorizacion
    from app.agentes.contexto import ContextoConversacion
    from app.observabilidad import trazas

    _fijar(monkeypatch, datetime(2026, 9, 21, 12, 0, tzinfo=reloj.ZONA))
    contexto = ContextoConversacion(sesion_id="web-fecha-1")

    texto = autorizacion.proponer(contexto, "crear", {
        "nombre": "Ana", "telefono": "999111222", "fecha": "2026-09-26", "hora": "20:00",
        "personas": 4, "zona": "", "notas": "", "dia_semana": "viernes",
    }, _ServicioQueNoDebeEscribir())

    assert "CONFIRMO" not in texto
    assert "sábado" in texto
    assert contexto.datos["guardrail_fecha"]["estado"] == "contradiccion"
    assert "confirmacion_pendiente" not in contexto.datos
    assert any(t.evento == "guardrail_fecha" for t in trazas.ultimas_trazas(sesion_id="web-fecha-1"))
    # Y el servidor tampoco acepta un CONFIRMO de la nada.
    assert autorizacion.confirmar("web-fecha-1", "CONFIRMO ABCD1234", _ServicioQueNoDebeEscribir())[1] == {}


def test_dia_y_fecha_coherentes_preparan_la_reserva_sin_filtrar_el_dia(monkeypatch):
    """`dia_semana` solo valida: nunca viaja al servicio como parametro de la reserva."""
    import json

    from app.agentes import autorizacion
    from app.agentes.contexto import ContextoConversacion

    _fijar(monkeypatch, datetime(2026, 9, 21, 12, 0, tzinfo=reloj.ZONA))
    contexto = ContextoConversacion(sesion_id="web-fecha-2")

    texto = autorizacion.proponer(contexto, "crear", {
        "nombre": "Ana", "telefono": "999111222", "fecha": "2026-09-25", "hora": "20:00",
        "personas": 4, "zona": "", "notas": "", "dia_semana": "viernes",
    }, _ServicioConMesa())

    assert "CONFIRMO" in texto
    with autorizacion._db() as db:
        guardado = json.loads(db.execute("SELECT datos FROM propuestas WHERE sesion=?", ("web-fecha-2",)).fetchone()[0])
    assert "dia_semana" not in guardado


def test_fecha_pasada_se_mide_en_hora_de_lima(monkeypatch):
    """
    Cruce de medianoche: a las 03:00 UTC del 22, en Lima todavia es el 21.
    Una reserva para "hoy 21" tiene que aceptarse; una para el 20, no.
    """
    from app.agentes import autorizacion
    from app.agentes.contexto import ContextoConversacion

    _fijar(monkeypatch, datetime(2026, 9, 22, 3, 0, tzinfo=timezone.utc))

    def proponer(fecha_iso):
        """Prepara una reserva de prueba para la fecha dada y devuelve el texto del servidor."""
        return autorizacion.proponer(ContextoConversacion(sesion_id="web-fecha-3"), "crear", {
            "nombre": "Ana", "telefono": "999111222", "fecha": fecha_iso, "hora": "21:00",
            "personas": 2, "zona": "", "notas": "",
        }, _ServicioConMesa())

    assert "CONFIRMO" in proponer("2026-09-21")
    assert "pasado" in proponer("2026-09-20")


def test_consultar_disponibilidad_no_consulta_con_dia_contradictorio(monkeypatch):
    """La contradiccion se corta antes de tocar el servicio de reservas."""
    from app.agentes.contexto import ContextoConversacion
    from app.agentes.tools import reservas_tools

    monkeypatch.setattr(reservas_tools, "servicio_reservas", lambda: _ServicioQueNoDebeEscribir())
    contexto = ContextoConversacion(sesion_id="web-fecha-4")

    salida = reservas_tools.consultar_disponibilidad.func(
        fecha="2026-09-26", hora="20:00", personas=4, dia_semana="viernes",
        runtime=_RuntimeFalso(contexto),
    )

    assert "Pregunta al cliente" in salida
    assert contexto.datos["guardrail_fecha"]["dia_declarado"] == "viernes"


def test_cada_turno_lleva_la_fecha_de_lima_y_la_ficha_solo_si_existe(monkeypatch):
    """La fecha ya no vive en el system prompt congelado: viaja pegada al mensaje."""
    from app.agentes import base

    _fijar(monkeypatch, datetime(2026, 9, 21, 12, 0, tzinfo=reloj.ZONA))

    sin_ficha = base._armar_entrada("hay mesa mañana?", "")
    con_ficha = base._armar_entrada("hay mesa mañana?", "R-1: Ana, 2026-09-25 a las 20:00")

    assert sin_ficha.startswith("[fecha y hora actuales del sistema, dato interno: es hoy: lunes 2026-09-21, 12:00 (hora de Lima)]")
    assert sin_ficha.endswith("hay mesa mañana?")
    assert "ficha del cliente" not in sin_ficha
    assert "ficha del cliente" in con_ficha and "R-1" in con_ficha
