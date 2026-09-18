"""
Redaccion de spans de LangSmith (A8 / paso 8 del plan del 18/09).

No se conecta a LangSmith: comprueba que el cliente que LangChain va a usar
es el redactado y que su `hide_inputs`/`hide_outputs` limpian lo que
`pii.py` conoce. Que cada span real quede limpio se verifica a mano con un
proyecto de prueba; esto garantiza que el gancho esta puesto.
"""

import langsmith.run_trees as rt
import pytest

from app.seguridad import trazado


@pytest.fixture(autouse=True)
def cliente_limpio(monkeypatch):
    """Deja el cliente global de langsmith vacio antes y despues de cada prueba."""
    monkeypatch.setenv("LANGSMITH_API_KEY", "ls-prueba-local")
    monkeypatch.setattr(rt, "_CLIENT", None)
    yield
    monkeypatch.setattr(rt, "_CLIENT", None)


def test_langchain_toma_el_cliente_redactado():
    """Verifica que langchain toma el cliente redactado."""
    from langchain_core.tracers.langchain import get_client

    assert trazado.activar_redaccion() == "cliente"
    cliente = get_client()
    assert cliente._hide_inputs is trazado.ocultar
    assert cliente._hide_outputs is trazado.ocultar
    # Idempotente: no crea otro cliente ni pierde el ya instalado.
    assert trazado.activar_redaccion() == "cliente"
    assert get_client() is cliente


def test_lo_que_sale_al_span_va_redactado():
    """Verifica que lo que sale al span va redactado."""
    payload = {
        "messages": [{"role": "user", "content": "soy Ana, mi celular es 999111222 y mi correo ana@mail.com"}],
        "tool_args": {"telefono": "+51 999111222", "tarjeta": "4111 1111 1111 1111"},
    }

    limpio = trazado.ocultar(payload)

    assert "999111222" not in str(limpio)
    assert "ana@mail.com" not in str(limpio)
    assert "4111" not in str(limpio)
    assert limpio["tool_args"]["telefono"] == "[REDACTED_TELEFONO]"
    assert "[REDACTED_TARJETA]" in limpio["tool_args"]["tarjeta"]


def test_configurar_observabilidad_instala_la_redaccion_cuando_hay_clave(monkeypatch):
    """El gancho vive en `configurar_observabilidad`: con tracing y clave, el cliente queda redactado."""
    from app import create_app
    from app.config import Config

    monkeypatch.setenv("LANGSMITH_TRACING", "true")
    create_app(Config(langsmith_tracing=True))

    assert getattr(rt._CLIENT, "_hide_inputs", None) is trazado.ocultar
