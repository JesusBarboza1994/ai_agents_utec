"""Al arrancar, Clemente avisa de lo que falta y solo se nota mas tarde; sin modelo."""
import logging

from app import create_app


def test_sin_clave_de_sesion_avisa_al_arrancar(monkeypatch, caplog):
    """Sin CLEMENTE_SECRET_KEY cada reinicio invalida las sesiones del webchat: el arranque lo dice en el registro."""
    monkeypatch.delenv("CLEMENTE_SECRET_KEY", raising=False)
    with caplog.at_level(logging.WARNING, logger="clemente"):
        create_app()
    assert "CLEMENTE_SECRET_KEY" in caplog.text and "sesiones del webchat" in caplog.text


def test_con_clave_de_sesion_no_avisa(monkeypatch, caplog):
    """Con la clave definida no hay aviso."""
    monkeypatch.setenv("CLEMENTE_SECRET_KEY", "x" * 64)
    with caplog.at_level(logging.WARNING, logger="clemente"):
        create_app()
    assert "CLEMENTE_SECRET_KEY" not in caplog.text
