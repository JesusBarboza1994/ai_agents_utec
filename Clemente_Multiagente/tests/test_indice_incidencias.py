"""Ingesta y busqueda de casos de incidencias: chunking jerarquico por seccion, ficha como metadata,
compensacion fuera del indice y recuperacion padre-hijo; sin red."""
from types import SimpleNamespace

import azure.search.documents
import azure.storage.blob

from app.agentes.rag import indice_incidencias

CASO = """# Caso I-4F2A91 — Espera de 40 minutos con reserva confirmada

**Caso de demostración sintético** del histórico de Clemente.

## Ficha del ticket

- **Código:** I-4F2A91
- **Tipo:** espera
- **Prioridad:** media
- **Canal:** WhatsApp
- **Fecha del hecho:** 2026-09-12 (viernes 20:00)
- **Plazo de atención:** 4 horas

## Ticket registrado

El cliente esperó 40 minutos.

## Solución aplicada por el restaurante

Se le asignó la siguiente mesa libre.

## Compensación aprobada por el personal

Postre de cortesía.
"""


def test_un_chunk_por_seccion_con_ficha_como_metadata():
    """Cada seccion `##` es un chunk con el titulo del caso antepuesto; la ficha y la intro no son chunks."""
    documentos, ids = indice_incidencias._cargar_casos([("caso_01_espera.md", CASO)])

    assert ids == ["caso_01_espera.md::Ticket registrado::0",
                   "caso_01_espera.md::Solución aplicada por el restaurante::0"]
    ticket = documentos[0]
    assert ticket.page_content.startswith(
        "Caso I-4F2A91 — Espera de 40 minutos con reserva confirmada\nTicket registrado\n")
    assert ticket.metadata["contenido"] == "El cliente esperó 40 minutos."
    assert all("demostración sintético" not in d.page_content for d in documentos)
    meta = ticket.metadata
    assert (meta["caso_id"], meta["tipo"], meta["prioridad"], meta["canal"]) == ("I-4F2A91", "espera", "media", "WhatsApp")
    assert meta["plazo_horas"] == 4


def test_la_compensacion_no_entra_al_indice_ni_al_caso_que_ve_el_agente():
    """La compensacion no es chunk y tampoco viaja en el caso padre: el asistente nunca la ofrece."""
    documentos, _ = indice_incidencias._cargar_casos([("caso_01_espera.md", CASO)])

    assert all("Postre de cortesía" not in d.page_content for d in documentos)
    padre = documentos[0].metadata["caso"]
    assert "Postre de cortesía" not in padre and "Compensación" not in padre
    assert "El cliente esperó 40 minutos." in padre and "Se le asignó la siguiente mesa libre." in padre


def test_ficha_incompleta_no_rompe():
    """Un caso sin titulo ni ficha se indexa igual, con esos campos vacios."""
    documentos, ids = indice_incidencias._cargar_casos([("carpeta/caso_02.md", "## Ticket registrado\n\nTexto libre.\n")])

    meta = documentos[0].metadata
    assert ids == ["carpeta/caso_02.md::Ticket registrado::0"]
    assert meta["plazo_horas"] is None and meta["canal"] == ""
    assert documentos[0].page_content.startswith("caso_02\nTicket registrado\n")


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


def test_indice_usa_analizador_en_espanol_y_guarda_el_caso_padre():
    """Texto con el analizador propio, vector de 1536 y el caso padre como campo devuelto pero no buscado."""
    indice = indice_incidencias._definir_indice()
    campos = {c.name: c for c in indice.fields}

    assert campos["content"].analyzer_name == indice_incidencias.ANALIZADOR
    assert campos["section"].analyzer_name == indice_incidencias.ANALIZADOR
    assert campos["content_vector"].vector_search_dimensions == 1536
    assert campos["tipo"].filterable
    assert not campos["caso"].searchable
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
    """Vector constante: basta para probar la carga y la busqueda sin red."""

    def embed_documents(self, textos):
        """Un vector por texto."""
        return [[0.0] * indice_incidencias.DIMENSION_VECTOR for _ in textos]

    def embed_query(self, texto):
        """Un vector para la consulta."""
        return [0.0] * indice_incidencias.DIMENSION_VECTOR


def _preparar(monkeypatch, azure):
    """Conecta indexar_casos a un indice falso y a embeddings falsos; devuelve los indices creados."""
    indices = SimpleNamespace(creados=[])
    indices.create_or_update_index = indices.creados.append
    monkeypatch.setattr(indice_incidencias, "_clientes", lambda: (indices, azure))
    monkeypatch.setattr(indice_incidencias, "resolver_embeddings", lambda: EmbeddingsFalsos())
    return indices


def test_reindexar_sube_las_secciones_y_borra_los_chunks_viejos(monkeypatch):
    """Se suben las secciones con ids estables y se borra lo que ya no existe (p. ej. el caso entero de antes)."""
    viejo = indice_incidencias._id_seguro("caso_01.md")   # id de la version de un chunk por caso
    azure = AzureFalso({viejo: {"id": viejo}})
    indices = _preparar(monkeypatch, azure)

    assert indice_incidencias.indexar_casos([("caso_01.md", CASO)]) == 2
    assert sorted(azure.docs) == sorted(indice_incidencias._id_seguro(f"caso_01.md::{s}::0")
                                        for s in ("Ticket registrado", "Solución aplicada por el restaurante"))
    assert all(d["tipo"] == "espera" and "Postre" not in d["caso"] for d in azure.docs.values())
    assert len(indices.creados) == 1


def test_contenedor_vacio_no_toca_el_indice(monkeypatch):
    """Si el Blob no trae casos, no se crea ni se vacia el indice."""
    existente = indice_incidencias._id_seguro("caso_01.md::Ticket registrado::0")
    azure = AzureFalso({existente: {"id": existente}})
    indices = _preparar(monkeypatch, azure)

    assert indice_incidencias.indexar_casos([]) == 0
    assert list(azure.docs) == [existente]
    assert indices.creados == []


def test_buscar_agrupa_por_caso_y_devuelve_el_padre(monkeypatch):
    """Varias secciones del mismo caso cuentan una vez; se devuelve el caso completo de los k primeros."""
    pedido = {}

    class BuscadorFalso:
        """SearchClient simulado: devuelve secciones ya ordenadas por relevancia."""

        def __init__(self, **_):
            """Ignora endpoint, indice y credencial."""

        def search(self, **kwargs):
            """Registra la consulta y devuelve tres secciones de dos casos y una de un tercero."""
            pedido.update(kwargs)
            return [
                {"document": "caso_04.md", "caso": "CASO 04 COMPLETO", "content": "s1", "@search.score": 0.033},
                {"document": "caso_04.md", "caso": "CASO 04 COMPLETO", "content": "s2", "@search.score": 0.032},
                {"document": "caso_28.md", "caso": "CASO 28 COMPLETO", "content": "s3", "@search.score": 0.031},
                {"document": "caso_17.md", "caso": "CASO 17 COMPLETO", "content": "s4", "@search.score": 0.030},
            ]

    monkeypatch.setenv("AZURE_SEARCH_ENDPOINT", "https://busqueda")
    monkeypatch.setenv("AZURE_SEARCH_API_KEY", "clave-de-prueba")
    monkeypatch.setattr(azure.search.documents, "SearchClient", BuscadorFalso)
    monkeypatch.setattr(indice_incidencias, "resolver_embeddings", lambda: EmbeddingsFalsos())

    casos = indice_incidencias.buscar_casos("me cobraron dos veces", k=2, tipo="servicio")

    assert [(c.fuente, c.texto) for c in casos] == [("caso_04.md", "CASO 04 COMPLETO"), ("caso_28.md", "CASO 28 COMPLETO")]
    assert pedido["top"] == 2 * indice_incidencias.CANDIDATOS_POR_CASO
    assert pedido["filter"] == "tipo eq 'servicio'"
