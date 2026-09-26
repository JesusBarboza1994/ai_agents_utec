"""Los errores de Trello no dejan la clave ni el token en el registro; sin red ni credenciales reales."""
import logging

import pytest

from app.incidencias.alertas import describir_error
from app.incidencias.servicio_trello import ServicioIncidenciasTrello

URL_CON_SECRETOS = "401 Client Error: Unauthorized for url: https://api.trello.com/1/cards?key=CLAVE-SECRETA&token=TOKEN-SECRETO&idList=abc"


def test_describir_error_tapa_la_clave_y_el_token_y_conserva_lo_util():
    """El mensaje sigue diciendo que fue un 401 en la API de Trello, pero sin la clave ni el token."""
    texto = describir_error(RuntimeError(URL_CON_SECRETOS))
    assert "CLAVE-SECRETA" not in texto and "TOKEN-SECRETO" not in texto
    assert "401" in texto and "api.trello.com" in texto and "key=***" in texto


def test_un_error_de_trello_no_escribe_secretos_en_el_registro(servicio_incidencias, monkeypatch, caplog):
    """Al crear un reclamo con Trello caido queda el aviso en el registro, sin la clave ni el token."""
    servicio = ServicioIncidenciasTrello(tablero="Prueba", espejo=servicio_incidencias)
    monkeypatch.setattr(servicio, "_pedir", lambda *a, **k: (_ for _ in ()).throw(RuntimeError(URL_CON_SECRETOS)))
    with caplog.at_level(logging.WARNING, logger="clemente"):
        incidencia = servicio.crear_incidencia("web-x", "El plato llego frio", "producto")
    assert incidencia.id.startswith("I-")
    assert "NO llego a Trello" in caplog.text
    assert "CLAVE-SECRETA" not in caplog.text and "TOKEN-SECRETO" not in caplog.text
