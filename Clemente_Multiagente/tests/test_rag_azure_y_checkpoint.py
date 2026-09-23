"""RAG de Azure con un indice falso (ids estables, borrado de obsoletos) y checkpoint sin historial repetido; sin red."""
import itertools
from types import SimpleNamespace

import pytest

from app.agentes import base
from app.agentes.rag import indice


class AzureFalso:
    """Indice de Azure AI Search simulado: guarda documentos por id y admite buscar, subir y borrar."""

    def __init__(self):
        """Empieza con un indice vacio."""
        self.docs = {}
        self.aceptar = True

    def merge_or_upload_documents(self, documents):
        """Sube o actualiza documentos por id, como mergeOrUpload; puede simular rechazos."""
        for d in documents:
            self.docs[d["id"]] = d["content"]
        return [SimpleNamespace(succeeded=self.aceptar) for _ in documents]

    def search(self, search_text, select, top, skip=0):
        """Devuelve los ids del indice paginados, como una busqueda vacia con select=id."""
        return [{"id": i} for i in sorted(self.docs)[skip:skip + top]]

    def delete_documents(self, documents):
        """Borra por id."""
        for d in documents:
            self.docs.pop(d["id"], None)

    def get_document_count(self):
        """Cantidad de documentos del indice."""
        return len(self.docs)


@pytest.fixture
def catalogo(tmp_path, monkeypatch):
    """Catalogo temporal con dos archivos, conectado a un Azure falso y a embeddings falsos."""
    (tmp_path / "a.md").write_text(
        "# Doc\n## Horarios\nAbrimos de martes a domingo.\n## Cancelacion\nSe cancela hasta 2 horas antes.\n", encoding="utf-8")
    (tmp_path / "b.md").write_text("# Carta\n## Platos\nCeviche y lomo saltado.\n", encoding="utf-8")
    azure = AzureFalso()
    monkeypatch.setattr(indice, "CARPETA_DOCUMENTOS", tmp_path)
    monkeypatch.setattr(indice, "_cliente_azure_search", lambda: azure)
    monkeypatch.setattr(indice, "resolver_embeddings",
                        lambda: SimpleNamespace(embed_documents=lambda textos: [[0.0] * 3 for _ in textos]))
    return tmp_path, azure


def test_reindexar_tras_agregar_una_seccion_no_duplica(catalogo):
    """Verifica que agregar una seccion al principio deja 4 chunks y no 7: los ids no dependen de la posicion global."""
    carpeta, azure = catalogo
    indice.indexar_en_azure_search()
    assert len(azure.docs) == 3
    (carpeta / "a.md").write_text(
        "# Doc\n## Estacionamiento\nHay convenio con la playa.\n## Horarios\nAbrimos de martes a domingo.\n"
        "## Cancelacion\nSe cancela hasta 2 horas antes.\n", encoding="utf-8")
    indice.indexar_en_azure_search()
    assert len(azure.docs) == 4
    assert sorted(azure.docs.values()).count("Abrimos de martes a domingo.") == 1


def test_editar_una_seccion_actualiza_en_lugar_de_duplicar(catalogo):
    """Verifica que cambiar el texto de una seccion reemplaza su version vieja."""
    carpeta, azure = catalogo
    indice.indexar_en_azure_search()
    (carpeta / "b.md").write_text("# Carta\n## Platos\nCeviche, lomo saltado y ají de gallina.\n", encoding="utf-8")
    indice.indexar_en_azure_search()
    assert len(azure.docs) == 3
    assert not any("Ceviche y lomo saltado." == v for v in azure.docs.values())
    assert any("ají de gallina" in v for v in azure.docs.values())


def test_una_seccion_retirada_se_borra_del_indice(catalogo):
    """Verifica que lo que ya no esta en el catalogo deja de poder recuperarse."""
    carpeta, azure = catalogo
    indice.indexar_en_azure_search()
    (carpeta / "b.md").unlink()
    indice.indexar_en_azure_search()
    assert len(azure.docs) == 2 and not any("Ceviche" in v for v in azure.docs.values())


def test_un_catalogo_vacio_no_vacia_el_indice(catalogo):
    """Verifica que un error de carpeta (sin documentos) no borra el indice existente."""
    carpeta, azure = catalogo
    indice.indexar_en_azure_search()
    for archivo in carpeta.glob("*.md"):
        archivo.unlink()
    assert indice.indexar_en_azure_search() == 0
    assert len(azure.docs) == 3


def test_una_carga_incompleta_no_borra_nada(catalogo):
    """Verifica que si Azure rechaza documentos no se borra lo anterior."""
    carpeta, azure = catalogo
    indice.indexar_en_azure_search()
    (carpeta / "b.md").unlink()
    azure.aceptar = False
    indice.indexar_en_azure_search()
    assert any("Ceviche" in v for v in azure.docs.values())


def test_dos_archivos_con_el_mismo_nombre_no_se_pisan(tmp_path, monkeypatch):
    """Verifica que un mismo nombre de archivo y seccion en dos carpetas genera ids distintos."""
    for carpeta in ("norte", "sur"):
        (tmp_path / carpeta).mkdir()
        (tmp_path / carpeta / "menu.md").write_text("# D" + chr(10) + "## Nota" + chr(10) + f"Texto de {carpeta}.", encoding="utf-8")
    monkeypatch.setattr(indice, "CARPETA_DOCUMENTOS", tmp_path)
    _, ids = indice._cargar_documentos()
    assert len(ids) == len(set(ids)) == 2


# ------------------------------------------------------------------ checkpoint sin historial repetido

def _agente_con_checkpoint(recibidos):
    """Agente real de LangChain con un modelo falso que anota cuantos mensajes recibe y un checkpoint en memoria."""
    from langchain.agents import create_agent
    from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
    from langchain_core.messages import AIMessage
    from langgraph.checkpoint.memory import InMemorySaver

    class Modelo(GenericFakeChatModel):
        """Modelo falso que registra el tamano de lo que recibe."""
        def bind_tools(self, *args, **kwargs):
            """Ignora las tools: esta prueba no las usa."""
            return self

        def _generate(self, messages, *args, **kwargs):
            """Anota cuantos mensajes llegaron y responde con un texto fijo."""
            recibidos.append(len(messages))
            return super()._generate(messages, *args, **kwargs)

    modelo = Modelo(messages=itertools.cycle([AIMessage(content="ok")]))
    return create_agent(model=modelo, tools=[], checkpointer=InMemorySaver())


def test_el_agente_no_ve_el_historial_repetido_turno_a_turno(monkeypatch):
    """Verifica que con checkpoint el modelo recibe solo el historial reenviado mas el mensaje nuevo, sin acumular copias."""
    monkeypatch.setattr(base, "ficha_del_cliente", lambda sesion: "")
    recibidos, historial, enviados = [], [], []
    agente = _agente_con_checkpoint(recibidos)
    for turno in range(1, 5):
        enviados.append(len(historial) + 1)
        base.ejecutar(agente, f"mensaje {turno}", "web-1", historial=list(historial))
        historial += [{"role": "user", "content": f"mensaje {turno}"}, {"role": "assistant", "content": "ok"}]
    assert recibidos == enviados


def test_borrar_el_hilo_no_falla_si_no_hay_checkpoint_o_no_se_puede_borrar():
    """Verifica que un agente sin checkpointer, o con uno que no sabe borrar, no interrumpe la respuesta."""
    base._olvidar_hilo(SimpleNamespace(), {"configurable": {"thread_id": "x"}})

    class SinBorrado:
        """Checkpointer que no sabe borrar hilos."""

    base._olvidar_hilo(SimpleNamespace(checkpointer=SinBorrado()), {"configurable": {"thread_id": "x"}})
