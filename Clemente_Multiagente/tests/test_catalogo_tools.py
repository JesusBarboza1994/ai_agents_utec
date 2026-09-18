"""
Las tools de catalogo frente a los dos backends del RAG (Chroma y Azure AI Search).

El PR #9 hizo el backend configurable por `RAG_BACKEND` sin agregar pruebas.
Lo que se cubre aqui es el borde que si es nuestro: que la tool no dependa
del backend, que un error remoto no llegue al modelo con URLs o cuerpos HTTP,
y que el conmutador por variable de entorno realmente cambie de camino. Sin
red, sin Ollama, sin Azure.
"""

from app.contratos import Fragmento


class _RuntimeFalso:
    """Imita lo unico que las tools usan del ToolRuntime que inyecta create_agent."""

    def __init__(self, contexto):
        """Expone el contexto recibido mediante el atributo context que leen las tools."""
        self.context = contexto


def _runtime(sesion="t-rag"):
    """Runtime falso con una sesion identificable para buscar sus trazas."""
    from app.agentes.contexto import ContextoConversacion

    return _RuntimeFalso(ContextoConversacion(sesion_id=sesion))


def test_un_error_del_indice_no_le_llega_al_modelo_pero_queda_en_la_traza(monkeypatch):
    """
    Con Azure el error trae el endpoint y el nombre del indice. Antes la tool
    devolvia `No se pudo consultar el catalogo (<error>)` y el modelo podia
    repetirle eso al cliente.
    """
    from app.agentes.tools import catalogo_tools
    from app.observabilidad import trazas

    def explotar(*_args, **_kwargs):
        """Simula un fallo del SDK de Azure con datos internos en el mensaje."""
        raise RuntimeError("HttpResponseError https://clemente.search.windows.net/indexes/catalogo-clemente 403")

    monkeypatch.setattr(catalogo_tools, "buscar", explotar)

    salida = catalogo_tools.buscar_en_catalogo.func(pregunta="hay estacionamiento?", runtime=_runtime())

    assert salida == catalogo_tools.FALLO_CATALOGO
    assert "search.windows.net" not in salida and "403" not in salida
    errores = [t for t in trazas.ultimas_trazas(sesion_id="t-rag") if t.evento == "rag_error"]
    assert len(errores) == 1
    assert "search.windows.net" in errores[0].detalle["error"]


def test_consultar_politica_tampoco_filtra_el_error(monkeypatch):
    """Verifica que consultar politica tampoco filtra el error."""
    from app.agentes.tools import catalogo_tools

    def explotar(*_args, **_kwargs):
        """Simula que el indice local no esta construido."""
        raise FileNotFoundError("chroma_index/colección no existe")

    monkeypatch.setattr(catalogo_tools, "buscar", explotar)

    salida = catalogo_tools.consultar_politica.func(tema="cancelacion", runtime=_runtime("t-pol"))

    assert salida == catalogo_tools.FALLO_CATALOGO


def test_los_fragmentos_de_azure_se_citan_igual_que_los_de_chroma(monkeypatch):
    """Azure devuelve `documento > seccion` como fuente y el chunk limpio; la cita es la misma."""
    from app.agentes.tools import catalogo_tools

    monkeypatch.setattr(catalogo_tools, "buscar", lambda pregunta, k: [
        Fragmento(texto="Se puede cancelar hasta 24 horas antes.", fuente="politicas.md > Cancelacion", score=0.9),
        Fragmento(texto="Sin costo hasta el dia anterior.", fuente="politicas.md", score=0.7),
    ])

    salida = catalogo_tools.consultar_politica.func(tema="cancelacion", runtime=_runtime())

    assert salida == (
        "[politicas.md > Cancelacion] Se puede cancelar hasta 24 horas antes.\n\n"
        "[politicas.md] Sin costo hasta el dia anterior."
    )


def test_sin_resultados_la_tool_lo_dice_sin_inventar(monkeypatch):
    """Verifica que sin resultados la tool lo dice sin inventar."""
    from app.agentes.tools import catalogo_tools

    monkeypatch.setattr(catalogo_tools, "buscar", lambda pregunta, k: [])

    assert "no tiene respuesta" in catalogo_tools.buscar_en_catalogo.func(pregunta="wifi?", runtime=_runtime())
    assert "No hay politica publicada sobre mascotas" in catalogo_tools.consultar_politica.func(tema="mascotas", runtime=_runtime())


def test_rag_backend_conmuta_a_azure_search_por_variable_de_entorno(monkeypatch):
    """El conmutador del PR #9: con RAG_BACKEND=azure_search no se toca Chroma."""
    from app.agentes.rag import indice

    llamadas = []
    monkeypatch.setattr(indice, "_buscar_azure_search", lambda pregunta, k: llamadas.append(("azure", pregunta, k)) or [])

    def chroma_no(*_args, **_kwargs):
        """Falla si el camino Chroma se usa con el backend de Azure activo."""
        raise AssertionError("no se debe construir el indice Chroma con RAG_BACKEND=azure_search")

    monkeypatch.setattr(indice, "construir_o_cargar_indice", chroma_no)

    monkeypatch.setenv("RAG_BACKEND", "azure_search")
    assert indice.buscar("horario", k=2) == []
    assert llamadas == [("azure", "horario", 2)]

    monkeypatch.setenv("RAG_BACKEND", "chroma")
    try:
        indice.buscar("horario", k=2)
    except AssertionError as error:
        assert "Chroma" in str(error)
    else:
        raise AssertionError("con RAG_BACKEND=chroma debia ir por Chroma")
