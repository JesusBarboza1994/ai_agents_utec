"""La pagina del webchat ofrece las pruebas en vivo solo en local; en produccion se esconden y el panel del personal queda."""
import dataclasses

import pytest

from app import create_app


@pytest.fixture
def cliente(monkeypatch):
    """Una app de prueba en local: sin CLEMENTE_ENTORNO y sin clave del personal."""
    monkeypatch.delenv("CLEMENTE_ENTORNO", raising=False)
    monkeypatch.delenv("CLEMENTE_HITL_TOKEN", raising=False)
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


def test_en_local_sin_clave_del_personal_la_pagina_lo_avisa(cliente):
    """Sin CLEMENTE_HITL_TOKEN el panel siempre diria «No autorizado»: la pagina explica por que."""
    assert "no tiene CLEMENTE_HITL_TOKEN definido" in cliente.get("/").get_data(as_text=True)


def test_con_clave_del_personal_la_pagina_no_avisa(cliente):
    """Con la clave definida no hay aviso."""
    app = cliente.application
    app.config["CLEMENTE"] = dataclasses.replace(app.config["CLEMENTE"], hitl_token="token-staff")
    assert "no tiene CLEMENTE_HITL_TOKEN definido" not in cliente.get("/").get_data(as_text=True)


def test_en_produccion_la_pagina_no_dice_si_la_clave_esta_definida(cliente, monkeypatch):
    """El aviso de la clave es una ayuda de desarrollo: al publico no se le cuenta como esta configurado el servidor."""
    monkeypatch.setenv("CLEMENTE_ENTORNO", "produccion")
    assert "no tiene CLEMENTE_HITL_TOKEN definido" not in cliente.get("/").get_data(as_text=True)
