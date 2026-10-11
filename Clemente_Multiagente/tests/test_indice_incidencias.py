"""Ingesta de casos de incidencias desde Blob a Azure AI Search: un chunk por caso, ficha como metadata; sin red."""
from types import SimpleNamespace

import azure.storage.blob

from app.agentes.rag import indice_incidencias

CASO = """# Caso I-4F2A91 — Espera de 40 minutos con reserva confirmada

## Ficha del ticket

- **Código:** I-4F2A91
- **Tipo:** espera
- **Prioridad:** media
- **Canal:** WhatsApp
- **Fecha del hecho:** 2026-09-12 (viernes 20:00)
- **Plazo de atención:** 4 horas

## Ticket registrado

El cliente esperó 40 minutos.
"""


def test_un_chunk_por_caso_con_ficha():
    """Cada .md es un solo chunk completo y la ficha queda como metadata filtrable."""
    documentos, ids = indice_incidencias._cargar_casos([("caso_01_espera.md", CASO)])

    assert ids == ["caso_01_espera.md"]
    meta = documentos[0].metadata
    assert documentos[0].page_content == CASO
    assert meta["seccion"] == "Caso I-4F2A91 — Espera de 40 minutos con reserva confirmada"
    assert (meta["caso_id"], meta["tipo"], meta["prioridad"], meta["canal"]) == ("I-4F2A91", "espera", "media", "WhatsApp")
    assert meta["plazo_horas"] == 4


def test_ficha_incompleta_no_rompe():
    """Un caso sin titulo, plazo ni canal se indexa igual, con esos campos vacios."""
    documentos, _ = indice_incidencias._cargar_casos([("carpeta/caso_02.md", "Texto libre sin ficha.\n")])

    meta = documentos[0].metadata
    assert meta["seccion"] == "caso_02"
    assert meta["plazo_horas"] is None
    assert meta["canal"] == ""


class ContenedorFalso:
    """Contenedor de Blob simulado: lista blobs y devuelve su contenido."""

    def __init__(self, archivos):
        """Guarda nombre -> texto."""
        self.archivos = archivos

    def list_blobs(self):
        """Lista los blobs por nombre."""
        return [SimpleNamespace(name=n) for n in self.archivos]

    def download_blob(self, nombre):
        """Devuelve un objeto con readall(), como el SDK."""
        return SimpleNamespace(readall=lambda: self.archivos[nombre].encode("utf-8"))


def test_lee_solo_los_md_del_contenedor(monkeypatch):
    """Del Blob se toman los .md del contenedor configurado; el resto se ignora."""
    pedidos = []

    def conectar(conexion, contenedor):
        """Registra a que contenedor se conecta."""
        pedidos.append((conexion, contenedor))
        return ContenedorFalso({"caso_01.md": CASO, "leeme.txt": "no es un caso"})

    monkeypatch.setenv("AZURE_STORAGE_CONNECTION_STRING", "cadena-de-prueba")
    monkeypatch.setenv("AZURE_STORAGE_CONTAINER_INCIDENCIAS", "incidencias")
    monkeypatch.setattr(azure.storage.blob.ContainerClient, "from_connection_string", staticmethod(conectar))

    assert indice_incidencias._leer_casos_blob() == [("caso_01.md", CASO)]
    assert pedidos == [("cadena-de-prueba", "incidencias")]


def test_indice_usa_analizador_en_espanol():
    """Los campos de texto usan el analizador propio y el vector tiene 1536 dimensiones."""
    indice = indice_incidencias._definir_indice()
    campos = {c.name: c for c in indice.fields}

    assert campos["content"].analyzer_name == indice_incidencias.ANALIZADOR
    assert campos["section"].analyzer_name == indice_incidencias.ANALIZADOR
    assert campos["content_vector"].vector_search_dimensions == 1536
    assert campos["tipo"].filterable
    assert [a.name for a in indice.analyzers] == [indice_incidencias.ANALIZADOR]
    assert {f.name for f in indice.token_filters} == {"stop-es", "snowball-es"}


class AzureFalso:
    """Indice simulado: guarda documentos por id y admite subir, buscar ids y borrar."""

    def __init__(self, docs=None):
        """Empieza con los documentos dados."""
        self.docs = dict(docs or {})

    def merge_or_upload_documents(self, documents):
        """Sube o actualiza por id."""
        for d in documents:
            self.docs[d["id"]] = d
        return [SimpleNamespace(succeeded=True) for _ in documents]

    def search(self, search_text, select, top, skip=0):
        """Devuelve los ids paginados, como una busqueda vacia con select=id."""
        return [{"id": i} for i in sorted(self.docs)[skip:skip + top]]

    def delete_documents(self, documents):
        """Borra por id."""
        for d in documents:
            self.docs.pop(d["id"], None)


class EmbeddingsFalsos:
    """Vector constante: basta para probar la carga sin red."""

    def embed_documents(self, textos):
        """Un vector por texto."""
        return [[0.0] * indice_incidencias.DIMENSION_VECTOR for _ in textos]


def _preparar(monkeypatch, azure):
    """Conecta indexar_casos a un indice falso y a embeddings falsos; devuelve los indices creados."""
    indices = SimpleNamespace(creados=[])
    indices.create_or_update_index = indices.creados.append
    monkeypatch.setattr(indice_incidencias, "_clientes", lambda: (indices, azure))
    monkeypatch.setattr(indice_incidencias, "resolver_embeddings", lambda: EmbeddingsFalsos())
    return indices


def test_reindexar_sube_todo_y_borra_obsoletos(monkeypatch):
    """La carga usa el nombre del blob como id estable y borra los casos retirados."""
    viejo = indice_incidencias._id_seguro("caso_retirado.md")
    azure = AzureFalso({viejo: {"id": viejo}})
    indices = _preparar(monkeypatch, azure)

    assert indice_incidencias.indexar_casos([("caso_01.md", CASO)]) == 1
    assert list(azure.docs) == [indice_incidencias._id_seguro("caso_01.md")]
    assert azure.docs[indice_incidencias._id_seguro("caso_01.md")]["tipo"] == "espera"
    assert len(indices.creados) == 1


def test_contenedor_vacio_no_toca_el_indice(monkeypatch):
    """Si el Blob no trae casos, no se crea ni se vacia el indice."""
    existente = indice_incidencias._id_seguro("caso_01.md")
    azure = AzureFalso({existente: {"id": existente}})
    indices = _preparar(monkeypatch, azure)

    assert indice_incidencias.indexar_casos([]) == 0
    assert list(azure.docs) == [existente]
    assert indices.creados == []
