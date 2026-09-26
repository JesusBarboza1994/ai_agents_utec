"""Reloj de Lima, tool de fecha y validacion dia/fecha; sin LLM ni base de datos."""
from datetime import date, datetime, timezone
from types import SimpleNamespace

import pytest

from app.agentes import autorizacion, base, fecha
from app.agentes import incidencias as agente_incidencias
from app.agentes import reservas as agente_reservas
from app.agentes.contexto import ContextoConversacion
from app.agentes.tools import fecha_tools
from app.agentes.tools import reservas_tools as tools
from app.orquestador import informacion
from app.reservas.servicio_json import ServicioReservasJSON

# 2026-10-06 02:00 UTC = lunes 2026-10-05 21:00 en Lima: el servidor ya esta en "manana".
# Es una fecha futura a proposito: con la fecha real del servidor estas pruebas fallarian.
INSTANTE = datetime(2026, 10, 6, 2, 0, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def reloj_fijo(monkeypatch):
    """Fija el instante del reloj de Lima para que las fechas de las pruebas no dependan del dia real."""
    monkeypatch.setattr(fecha, "_reloj", lambda: INSTANTE)


@pytest.fixture
def servicio(tmp_path, monkeypatch):
    """Servicio de reservas JSON temporal conectado a las tools."""
    servicio = ServicioReservasJSON(archivo_reservas=tmp_path / "reservas.json")
    monkeypatch.setattr(tools, "servicio_reservas", lambda: servicio)
    return servicio


def runtime(sesion="whatsapp-51999111222"):
    """Runtime simulado con sesion identificada y contexto vacio."""
    return SimpleNamespace(context=ContextoConversacion(sesion_id=sesion))


def test_hoy_es_la_fecha_de_lima_y_no_la_del_servidor():
    """Verifica que a las 21:00 de Lima hoy sigue siendo lunes aunque en UTC ya sea martes."""
    assert fecha.hoy() == date(2026, 10, 5)
    assert fecha.nombre_dia(fecha.hoy()) == "lunes"


def test_dia_declarado_ignora_tildes_y_mayusculas():
    """Verifica que se reconoce el dia escrito de cualquier forma y None si no hay ninguno."""
    assert fecha.dia_declarado("el Sábado") == "sabado"
    assert fecha.dia_declarado("este viernes, por favor") == "viernes"
    assert fecha.dia_declarado("mañana") is None
    assert fecha.dia_declarado("") is None


def test_contradiccion_dia_fecha():
    """Verifica que 'viernes' con el 10 de octubre (sabado) devuelve la contradiccion y no elige."""
    texto = fecha.contradiccion_dia("viernes", "2026-10-10")
    assert "viernes" in texto and "sábado" in texto and "no elijas" in texto
    assert fecha.contradiccion_dia("sabado", "2026-10-10") is None
    assert fecha.contradiccion_dia("", "2026-10-10") is None
    assert fecha.contradiccion_dia("viernes", "no-es-fecha") is None


def test_proximos_dias_empieza_manana():
    """Verifica que la lista de proximos dias arranca en manana segun Lima."""
    assert fecha.proximos_dias(2) == [("martes", date(2026, 10, 6)), ("miércoles", date(2026, 10, 7))]


def test_tool_de_fecha_responde_con_la_hora_de_lima():
    """Verifica que get_current_datetime resuelve hoy y manana con el reloj de Lima."""
    texto = fecha_tools.get_current_datetime.func(runtime())
    assert "Hoy es lunes 2026-10-05, 21:00 (hora de Lima)" in texto
    assert "Mañana es martes 2026-10-06" in texto


def test_consultar_disponibilidad_rechaza_contradiccion_sin_consultar(monkeypatch):
    """Verifica que un dia y fecha que no coinciden no llegan al servicio y quedan marcados."""
    def no_debe_llamarse():
        """Falla la prueba si la tool consulta el servicio pese a la contradiccion."""
        raise AssertionError("consulto el servicio")
    monkeypatch.setattr(tools, "servicio_reservas", no_debe_llamarse)
    rt = runtime()
    texto = tools.consultar_disponibilidad.func("2026-10-10", "20:00", 4, rt, dia_semana="viernes")
    assert "cuál de los dos" in texto
    assert rt.context.datos["guardrail_fecha"]["estado"] == "contradiccion"


def test_crear_reserva_con_contradiccion_no_deja_propuesta(servicio):
    """Verifica que la contradiccion dia/fecha no prepara el resumen CONFIRMO ni escribe."""
    rt = runtime()
    texto = tools.crear_reserva.func(
        "Cliente ficticio", "900000001", "2026-10-10", "20:00", 4, rt, dia_semana="viernes",
    )
    assert "CONFIRMO" not in texto
    assert "confirmacion_pendiente" not in rt.context.datos
    assert servicio.buscar_reservas_de("900000001") == []


def test_modificar_reserva_con_contradiccion_no_prepara_cambio(servicio):
    """Verifica que modificar tambien compara el dia con la nueva fecha."""
    reserva = servicio.crear_reserva("Cliente ficticio", "900000001", "2026-10-10", "20:00", 2, "")
    autorizacion.vincular("whatsapp-51999111222", reserva.id)
    texto = tools.modificar_reserva.func(
        reserva.id, runtime(), fecha="2026-10-09", dia_semana="lunes",
    )
    assert "CONFIRMO" not in texto and "no cae en la fecha" in texto


def test_hoy_de_lima_no_se_rechaza_como_fecha_pasada(servicio, monkeypatch):
    """Verifica que reservar para hoy a las 21:00 de Lima funciona aunque UTC ya sea manana.

    El reloj se adelanta a las 20:30 de Lima (01:30 UTC del dia siguiente): sigue siendo "manana"
    en UTC, y el turno de las 21:00 todavia no empezo."""
    monkeypatch.setattr(fecha, "_reloj", lambda: INSTANTE.replace(hour=1, minute=30))
    rt = runtime()
    texto = tools.crear_reserva.func(
        "Cliente ficticio", "900000001", "2026-10-05", "21:00", 2, rt, dia_semana="lunes",
    )
    assert "CONFIRMO" in texto


def test_ayer_de_lima_si_es_fecha_pasada(servicio):
    """Verifica que una fecha anterior a hoy en Lima se rechaza en la tool y no consulta disponibilidad."""
    texto = tools.consultar_disponibilidad.func("2026-10-04", "20:00", 2, runtime())
    assert "no esté en el pasado" in texto
    assert "no esté en el pasado" in tools.crear_reserva.func(
        "Cliente ficticio", "900000001", "2026-10-04", "20:00", 2, runtime(),
    )


def test_autorizacion_usa_el_reloj_de_lima_y_no_la_fecha_del_proceso(servicio, monkeypatch):
    """Verifica que la validacion del servidor no toma date.today(): con Lima en el 15/09 el 18/09 no es pasado."""
    monkeypatch.setattr(fecha, "_reloj", lambda: datetime(2026, 9, 16, 2, 0, tzinfo=timezone.utc))
    resumen = autorizacion.proponer(runtime().context, "crear", {
        "nombre": "Cliente ficticio", "telefono": "900000001", "fecha": "2026-09-18",
        "hora": "20:00", "personas": 2, "zona": "", "notas": "",
    }, servicio)
    assert "CONFIRMO" in resumen


def test_la_fecha_viaja_en_cada_turno_y_no_en_el_system_prompt(monkeypatch):
    """Verifica que la fecha de Lima se antepone a cada mensaje y el prompt del agente no la congela."""
    creado = {}
    monkeypatch.setattr("app.agentes.base.resolver_modelo", lambda **_: object())
    monkeypatch.setattr("langchain.agents.create_agent", lambda **kwargs: creado.update(kwargs))
    base.construir_agente("PROMPT", [])
    assert creado["system_prompt"] == "PROMPT"

    recibido = {}

    class AgenteFalso:
        """Agente que guarda lo que recibe y responde con un texto fijo."""
        def invoke(self, estado, config=None, context=None):
            """Guarda los mensajes del turno y devuelve una respuesta simulada."""
            recibido["mensajes"] = estado["messages"]
            return {"messages": [SimpleNamespace(content="listo")]}

    monkeypatch.setattr(base, "ficha_del_cliente", lambda sesion: "")
    assert base.ejecutar(AgenteFalso(), "quiero mesa manana", "webchat-1") == "listo"
    ultimo = recibido["mensajes"][-1]["content"]
    assert "lunes 2026-10-05, 21:00 (hora de Lima)" in ultimo
    assert ultimo.endswith("quiero mesa manana")


def test_los_tres_agentes_tienen_la_tool_de_fecha():
    """Verifica que reservas, incidencias e informacion pueden consultar la fecha."""
    for tools_del_agente in (agente_reservas.TOOLS, agente_incidencias.TOOLS, informacion.TOOLS):
        assert "get_current_datetime" in [t.name for t in tools_del_agente]
