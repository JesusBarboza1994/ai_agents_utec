"""Un reclamo que recibe codigo pero no llega a Trello deja aviso visible, y sus errores no filtran secretos; sin red."""
import logging

import pytest

from app import create_app
from app.incidencias import alertas
from app.incidencias.alertas import cantidad_sin_tarjeta, describir_error
from app.incidencias.servicio_mcp import ServicioIncidenciasMCP
from app.incidencias.servicio_trello import ServicioIncidenciasTrello
from app.observabilidad.trazas import ultimas_trazas

URL_CON_SECRETOS = "401 Client Error: Unauthorized for url: https://api.trello.com/1/cards?key=CLAVE-SECRETA&token=TOKEN-SECRETO&idList=abc"


@pytest.fixture(autouse=True)
def contador_limpio():
    """El contador vive en el proceso: cada prueba empieza y termina en cero."""
    alertas._sin_tarjeta.clear()
    yield
    alertas._sin_tarjeta.clear()


def _trello_caido(servicio_incidencias, monkeypatch):
    """Un servicio de Trello cuyas llamadas fallan con un error que trae la clave y el token en la direccion."""
    servicio = ServicioIncidenciasTrello(tablero="Prueba", espejo=servicio_incidencias)
    monkeypatch.setattr(servicio, "_pedir", lambda *a, **k: (_ for _ in ()).throw(RuntimeError(URL_CON_SECRETOS)))
    return servicio


def test_describir_error_tapa_la_clave_y_el_token_y_conserva_lo_util():
    """El mensaje sigue diciendo que fue un 401 en la API de Trello, pero sin la clave ni el token."""
    texto = describir_error(RuntimeError(URL_CON_SECRETOS))
    assert "CLAVE-SECRETA" not in texto and "TOKEN-SECRETO" not in texto
    assert "401" in texto and "api.trello.com" in texto and "key=***" in texto


def test_un_error_de_trello_no_escribe_secretos_en_el_registro(servicio_incidencias, monkeypatch, caplog):
    """Al crear un reclamo con Trello caido queda el aviso en el registro, sin la clave ni el token."""
    servicio = _trello_caido(servicio_incidencias, monkeypatch)
    with caplog.at_level(logging.WARNING, logger="clemente"):
        incidencia = servicio.crear_incidencia("web-x", "El plato llego frio", "producto")
    assert incidencia.id.startswith("I-")
    assert "NO llego a Trello" in caplog.text
    assert "CLAVE-SECRETA" not in caplog.text and "TOKEN-SECRETO" not in caplog.text


def test_un_reclamo_sin_tarjeta_deja_error_evento_y_contador(servicio_incidencias, monkeypatch, caplog):
    """Si Trello falla, el cliente conserva su codigo pero el equipo ve una linea ERROR, un evento y el contador."""
    servicio = _trello_caido(servicio_incidencias, monkeypatch)
    with caplog.at_level(logging.ERROR, logger="clemente"):
        incidencia = servicio.crear_incidencia("web-sin-tarjeta", "El plato llego frio", "producto")
    assert cantidad_sin_tarjeta() == 1
    assert any(r.levelno == logging.ERROR and incidencia.id in r.getMessage() for r in caplog.records)
    eventos = [t for t in ultimas_trazas(100, "web-sin-tarjeta") if t.evento == "incidencia_sin_tarjeta"]
    assert eventos and eventos[-1].detalle["incidencia"] == incidencia.id


def test_si_la_tarjeta_se_crea_no_hay_aviso(servicio_incidencias, monkeypatch):
    """Con Trello funcionando el contador queda en cero."""
    servicio = ServicioIncidenciasTrello(tablero="Prueba", espejo=servicio_incidencias)
    monkeypatch.setattr(servicio, "_cargar_tablero", lambda: setattr(servicio, "_listas", {"pendiente": "L1"}) or setattr(servicio, "_etiquetas", {"producto": "E1"}))
    monkeypatch.setattr(servicio, "_pedir", lambda *a, **k: {"shortUrl": "https://trello.com/c/x"})
    servicio.crear_incidencia("web-ok", "El plato llego frio", "producto")
    assert cantidad_sin_tarjeta() == 0


def test_si_el_servidor_mcp_no_responde_tambien_se_avisa(servicio_incidencias, monkeypatch):
    """Cuando ni siquiera responde el servidor MCP, el reclamo queda en el respaldo y el aviso tambien se da."""
    servicio = ServicioIncidenciasMCP(destino="no-existe", espejo=servicio_incidencias)
    monkeypatch.setattr(servicio, "llamar", lambda *a, **k: (_ for _ in ()).throw(ConnectionError("sin servidor")))
    incidencia = servicio.crear_incidencia("web-mcp", "El plato llego frio", "producto")
    assert incidencia.id.startswith("I-") and cantidad_sin_tarjeta() == 1


def test_salud_cuenta_los_reclamos_sin_tarjeta():
    """/api/salud arranca en cero y, despues de un reclamo sin tarjeta, lo dice con palabras."""
    cliente = create_app().test_client()
    antes = cliente.get("/api/salud").get_json()
    assert antes["incidencias_sin_tarjeta"] == 0 and antes["alertas"] == []
    alertas.avisar_sin_tarjeta("I-PRUEBA", "web-salud", RuntimeError("Trello no responde"))
    despues = cliente.get("/api/salud").get_json()
    assert despues["incidencias_sin_tarjeta"] == 1
    assert "no llegaron a Trello" in despues["alertas"][0]
