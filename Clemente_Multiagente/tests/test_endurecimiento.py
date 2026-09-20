"""Endurecimiento de seguridad de la capa de agentes: errores, trazas y limites; sin LLM ni base de datos."""
import json
import logging
import time
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.agentes import base
from app.agentes.contexto import ContextoConversacion
from app.agentes.tools import catalogo_tools
from app.observabilidad import trazas
from app.seguridad import trazado


def runtime(sesion="whatsapp-51999111222"):
    """Runtime simulado con sesion identificada y contexto vacio."""
    return SimpleNamespace(context=ContextoConversacion(sesion_id=sesion))


# ---------------------------------------------------------------- errores hacia afuera

def test_el_error_del_catalogo_no_llega_al_modelo(monkeypatch, caplog):
    """Verifica que la tool devuelve un aviso generico y el detalle real queda solo en el log."""
    secreto = "https://interno.search.windows.net/indexes/catalogo?api-key=abc123"

    def cae(*_a, **_k):
        """Simula un fallo de Azure AI Search cuyo mensaje trae una URL interna."""
        raise RuntimeError(secreto)

    monkeypatch.setattr(catalogo_tools, "buscar", cae)
    trazas._trazas.clear()
    with caplog.at_level(logging.WARNING, logger="clemente"):
        texto = catalogo_tools.buscar_en_catalogo.func("horario", runtime())
        politica = catalogo_tools.consultar_politica.func("cancelacion", runtime())
    for salida in (texto, politica):
        assert "interno" not in salida and "abc123" not in salida
        assert salida == catalogo_tools.FALLO_CATALOGO
    assert all("interno" not in str(t.detalle) for t in trazas._trazas)
    assert "RuntimeError" in str([t.detalle for t in trazas._trazas if t.evento == "error"])
    assert "interno.search" in caplog.text


def test_una_tool_que_falla_deja_solo_el_tipo_en_la_traza():
    """Verifica que con_traza no copia el mensaje de la excepcion a la traza que se lee desde /api/trazas."""
    from app.agentes.tools import con_traza

    @con_traza
    def rota(runtime):
        """Tool de prueba que falla con un mensaje que trae un host interno."""
        raise ConnectionError("connection to server at db.prisma.io failed")

    trazas._trazas.clear()
    with pytest.raises(ConnectionError):
        rota(runtime())
    detalle = [t.detalle for t in trazas._trazas if t.evento == "tool"][-1]
    assert detalle["error"] == "ConnectionError" and "prisma" not in str(detalle)


# ---------------------------------------------------------------- LangSmith

def test_ocultar_redacta_lo_que_viaja_a_langsmith():
    """Verifica que el filtro de inputs y outputs tapa telefonos, correos y tarjetas anidados."""
    entrada = {"messages": [{"content": "mi cel es 987654321, ana@correo.com"}], "x": ["4111 1111 1111 1111"]}
    salida = str(trazado.ocultar(entrada))
    assert "987654321" not in salida and "ana@correo.com" not in salida and "4111" not in salida
    assert "REDACTED_TELEFONO" in salida


def test_sin_langsmith_no_se_instala_ningun_cliente(monkeypatch):
    """Verifica que con el trazado apagado no se crea cliente ni se cambia nada."""
    monkeypatch.setenv("LANGSMITH_TRACING", "false")
    with trazado.contexto_de_trazado():
        pass
    assert trazado.trazado_activo() is False


def test_langsmith_recibe_los_datos_redactados(monkeypatch):
    """Verifica de punta a punta que lo enviado a LangSmith, incluso en llamadas anidadas, sale redactado."""
    from langchain_core.runnables import RunnableLambda
    from langsmith import Client

    enviados = []

    def falso(method, url, *args, **kwargs):
        """Captura lo que el cliente de LangSmith intentaria enviar por HTTP."""
        dato = kwargs.get("data")
        enviados.append(dato.decode("utf-8", "ignore") if isinstance(dato, (bytes, bytearray)) else json.dumps(kwargs.get("json")))
        respuesta = MagicMock()
        respuesta.status_code = 200
        respuesta.json.return_value = {}
        return respuesta

    cliente = Client(api_url="http://localhost:9", api_key="x", hide_inputs=trazado.ocultar,
                     hide_outputs=trazado.ocultar, auto_batch_tracing=False)
    cliente.session = MagicMock()
    cliente.session.request.side_effect = falso
    monkeypatch.setattr(trazado, "_cliente", cliente)
    monkeypatch.setenv("LANGSMITH_TRACING", "true")
    monkeypatch.setenv("LANGSMITH_API_KEY", "x")

    hijo = RunnableLambda(lambda x: {"eco": x["texto"]})
    padre = RunnableLambda(lambda x: hijo.invoke(x))
    with trazado.contexto_de_trazado():
        padre.invoke({"texto": "mi telefono es 987654321 y mi correo ana@correo.com"})
    time.sleep(0.5)
    todo = " ".join(enviados)
    assert enviados and "987654321" not in todo and "ana@correo.com" not in todo
    assert "REDACTED_TELEFONO" in todo


def test_el_id_de_hilo_no_lleva_el_telefono_y_es_estable():
    """Verifica que el thread_id del checkpoint (que LangSmith recibe como metadata) no expone el telefono."""
    uno = base.id_de_hilo("reservas", "whatsapp-51999111222")
    assert "51999111222" not in uno and uno.startswith("reservas:")
    assert uno == base.id_de_hilo("reservas", "whatsapp-51999111222")
    assert uno != base.id_de_hilo("reservas", "whatsapp-51999111333")
    assert uno != base.id_de_hilo("incidencias", "whatsapp-51999111222")
