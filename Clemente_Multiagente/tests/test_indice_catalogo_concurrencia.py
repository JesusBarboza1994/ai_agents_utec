"""El indice local del catalogo se abre una sola vez aunque dos herramientas lo pidan a la vez; sin modelo ni Chroma real.

Con el motor de Chroma local, `buscar_en_catalogo` y `consultar_politica` corren en paralelo y ambas llegan a abrir el
indice en la primera pregunta tras arrancar. Chroma no admite abrir el mismo directorio dos veces a la vez (falla con
`KeyError` sobre la ruta o con `AttributeError: ... 'bindings'`), y el cliente veia "no se pudo consultar el catalogo".
"""
import sys
import threading
import time
import types

from app.agentes.rag import indice_catalogo


def test_varias_busquedas_a_la_vez_abren_el_indice_una_sola_vez(monkeypatch):
    """Cuatro hilos piden el indice recien arrancado: Chroma se construye una vez y todos reciben el mismo objeto."""
    construcciones = []

    class ChromaFalso:
        """Chroma de mentira: tarda en abrirse, como el real, y anota cada construccion."""

        def __init__(self, **kwargs):
            """Anota la construccion y espera un poco para dar tiempo a que otro hilo entre."""
            construcciones.append(kwargs["persist_directory"])
            time.sleep(0.2)
            self._collection = types.SimpleNamespace(count=lambda: 1)

    monkeypatch.setattr(indice_catalogo, "_vector_store", None)
    monkeypatch.setattr(indice_catalogo, "resolver_embeddings", lambda: None)
    monkeypatch.setattr(indice_catalogo, "nombre_embeddings", lambda: "prueba")
    monkeypatch.setitem(sys.modules, "langchain_chroma", types.SimpleNamespace(Chroma=ChromaFalso))
    obtenidos = []
    hilos = [threading.Thread(target=lambda: obtenidos.append(indice_catalogo.construir_o_cargar_indice()))
             for _ in range(4)]

    for hilo in hilos:
        hilo.start()
    for hilo in hilos:
        hilo.join()

    assert len(construcciones) == 1
    assert len(obtenidos) == 4 and all(indice is obtenidos[0] for indice in obtenidos)
