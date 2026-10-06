"""Al arrancar, Clemente avisa de lo que falta y solo se nota mas tarde; sin modelo."""
import logging

import pytest

from app import create_app
from app.arranque import ConfiguracionDeProduccionInvalida


def test_sin_clave_de_sesion_avisa_al_arrancar(monkeypatch, caplog):
    """Sin CLEMENTE_SECRET_KEY cada reinicio invalida las sesiones del webchat: el arranque lo dice en el registro."""
    monkeypatch.delenv("CLEMENTE_SECRET_KEY", raising=False)
    monkeypatch.delenv("CLEMENTE_ENTORNO", raising=False)
    with caplog.at_level(logging.WARNING, logger="clemente"):
        create_app()
    assert "CLEMENTE_SECRET_KEY" in caplog.text and "sesiones del webchat" in caplog.text


def test_con_clave_de_sesion_no_avisa(monkeypatch, caplog):
    """Con la clave definida no hay aviso."""
    monkeypatch.setenv("CLEMENTE_SECRET_KEY", "x" * 64)
    monkeypatch.delenv("CLEMENTE_ENTORNO", raising=False)
    with caplog.at_level(logging.WARNING, logger="clemente"):
        create_app()
    assert "CLEMENTE_SECRET_KEY" not in caplog.text


# --- produccion: CLEMENTE_ENTORNO=produccion exige lo que en Azure se pierde en silencio ---

CONFIGURACION_COMPLETA = {
    "CLEMENTE_ENTORNO": "produccion", "CLEMENTE_SECRET_KEY": "x" * 64, "CLEMENTE_BACKEND_RESERVAS": "postgres",
    "CLEMENTE_DATABASE_URL": "postgresql://usuario:clave@servidor:5432/clemente", "CLEMENTE_GUARDRAILS_URL": "http://guardrails",
    "CLEMENTE_GUARDRAILS_TOKEN": "t" * 40, "TRELLO_API_KEY": "k" * 32, "TRELLO_TOKEN": "t" * 64, "AGENT_MODEL": "openai",
    "OPENAI_API_KEY": "sk-prueba", "TWILIO_AUTH_TOKEN": "twilio",
}
VARIABLES_DE_PRODUCCION = [*CONFIGURACION_COMPLETA, "CLEMENTE_DATOS_DIR", "CLEMENTE_DEBUG_ROUTES",
                           "CLEMENTE_BACKEND_INCIDENCIAS", "CLEMENTE_GUARDRAILS_FALLA_CERRADA"]


@pytest.fixture
def produccion(monkeypatch, tmp_path):
    """Un entorno de produccion completo y valido; cada prueba le quita o le agrega lo que quiere comprobar."""
    for nombre in VARIABLES_DE_PRODUCCION:
        monkeypatch.delenv(nombre, raising=False)
    for nombre, valor in CONFIGURACION_COMPLETA.items():
        monkeypatch.setenv(nombre, valor)
    monkeypatch.setenv("CLEMENTE_DATOS_DIR", str(tmp_path / "datos"))
    return monkeypatch


def test_en_local_nada_bloquea_el_arranque(monkeypatch):
    """Sin CLEMENTE_ENTORNO (tu computadora) Clemente arranca aunque falte casi todo."""
    for nombre in VARIABLES_DE_PRODUCCION:
        monkeypatch.delenv(nombre, raising=False)
    create_app()


def test_produccion_con_todo_bien_arranca(produccion):
    """Con la configuracion completa, produccion arranca."""
    create_app()


def test_produccion_sin_configuracion_no_arranca_y_dice_todo_lo_que_falta(monkeypatch):
    """Sin nada configurado, el error nombra cada variable que falta para que quien despliega la arregle de una vez."""
    for nombre in VARIABLES_DE_PRODUCCION:
        monkeypatch.delenv(nombre, raising=False)
    monkeypatch.setenv("CLEMENTE_ENTORNO", "produccion")
    with pytest.raises(ConfiguracionDeProduccionInvalida) as error:
        create_app()
    texto = str(error.value)
    for esperado in ("CLEMENTE_SECRET_KEY", "'postgres'", "CLEMENTE_DATABASE_URL", "CLEMENTE_DATOS_DIR",
                     "CLEMENTE_GUARDRAILS_URL", "TRELLO_API_KEY"):
        assert esperado in texto, esperado


@pytest.mark.parametrize("variable, valor, debe_decir", [
    ("CLEMENTE_BACKEND_RESERVAS", "json", "postgres"),
    ("CLEMENTE_DEBUG_ROUTES", "1", "CLEMENTE_DEBUG_ROUTES"),
    ("CLEMENTE_BACKEND_INCIDENCIAS", "json", "TRELLO_API_KEY"),
])
def test_produccion_rechaza_las_configuraciones_inseguras_o_que_pierden_datos(produccion, variable, valor, debe_decir):
    """Reservas en JSON, rutas de depuracion abiertas o reclamos solo en archivo impiden arrancar en produccion."""
    produccion.setenv(variable, valor)
    with pytest.raises(ConfiguracionDeProduccionInvalida, match=debe_decir):
        create_app()


def test_produccion_con_guardrails_abierto_arranca_pero_avisa(produccion, caplog):
    """FALLA_CERRADA=0 no impide arrancar, pero queda el aviso de que Guardrails caido deja pasar los mensajes."""
    produccion.setenv("CLEMENTE_GUARDRAILS_FALLA_CERRADA", "0")
    with caplog.at_level(logging.WARNING, logger="clemente"):
        create_app()
    assert "FALLA_CERRADA=0" in caplog.text
