"""La pagina del webchat ofrece las pruebas en vivo solo en local; en produccion se esconden y el panel del personal queda."""
import pytest

from app import create_app


@pytest.fixture
def cliente(monkeypatch):
    """Una app de prueba en local: sin CLEMENTE_ENTORNO."""
    monkeypatch.delenv("CLEMENTE_ENTORNO", raising=False)
    return create_app().test_client()


def test_en_local_la_pagina_ofrece_las_pruebas_en_vivo(cliente):
    """En tu computadora la pagina trae el contenedor de pruebas y carga su archivo de casos."""
    html = cliente.get("/").get_data(as_text=True)
    assert 'id="pruebas"' in html
    assert "/static/js/pruebas_en_vivo.js" in html


def test_el_archivo_de_las_pruebas_se_sirve(cliente):
    """La ruta del script existe: sin esto la pagina mostraria el contenedor vacio."""
    respuesta = cliente.get("/static/js/pruebas_en_vivo.js")
    assert respuesta.status_code == 200
    assert b"window.PruebasEnVivo" in respuesta.data


def test_en_produccion_la_pagina_esconde_las_pruebas_pero_deja_el_panel_del_personal(cliente, monkeypatch):
    """Con CLEMENTE_ENTORNO=produccion no hay consola de pruebas para el publico; la revision humana sigue."""
    monkeypatch.setenv("CLEMENTE_ENTORNO", "produccion")
    html = cliente.get("/").get_data(as_text=True)
    assert 'id="pruebas"' not in html
    assert "pruebas_en_vivo.js" not in html
    assert "staff-revisiones" in html and "CLEMENTE_HITL_TOKEN" in html
