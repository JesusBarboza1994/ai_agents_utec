"""
Indice vectorial (RAG) del catalogo validado del restaurante -- Sesion 13.

Recorre `documentos/` (horarios, carta, politicas, servicios), parte cada
archivo en chunks y los indexa. El Agente de Conocimiento solo llama a
`buscar()`.

Backend del indice: `RAG_BACKEND` en el .env.
  chroma        (default) -- coleccion Chroma persistente local.
  azure_search  -- push directo al indice de Azure AI Search via SDK, sin
                    Blob Storage ni indexer/skillset: este mismo script arma
                    los chunks y los empuja, igual que hoy hace con Chroma.

Embeddings: los define EMBEDDINGS_BACKEND en el .env (ollama por defecto,
openai como alternativa). Con Ollama hace falta una sola vez:
    ollama pull nomic-embed-text

Los vectores de dos modelos distintos no son comparables, asi que el nombre
del modelo forma parte del nombre de la coleccion de Chroma: cambiar de
backend crea un indice nuevo en vez de mezclar vectores incompatibles en
silencio. En Azure Search, el indice tiene una dimension de vector fija
(1536, text-embedding-3-small) -- cambiar de modelo de embeddings ahi
requiere recrear el indice a mano.

Reconstruir el indice tras editar los documentos:
    python -m app.agentes.rag.indice --reindexar
"""

import base64
import os
import shutil
import sys
from pathlib import Path

from ...contratos import Fragmento
from ...llm import nombre_embeddings, resolver_embeddings

CARPETA_DOCUMENTOS = Path(__file__).parent / "documentos"
CARPETA_INDICE = Path(__file__).parent / "chroma_index"
EXTENSIONES_ADMITIDAS = {".md", ".txt", ".pdf", ".docx"}

_vector_store = None
_azure_search_verificado = False


def _extraer_texto(ruta: Path) -> str:
    """Lee texto de TXT, Markdown, DOCX o PDF segun la extension de ruta.

    Devuelve cadena vacia para extensiones no admitidas; los errores de lectura
    o de los lectores de documentos se propagan."""
    sufijo = ruta.suffix.lower()
    if sufijo in {".md", ".txt"}:
        return ruta.read_text(encoding="utf-8", errors="ignore")
    if sufijo == ".docx":
        from docx import Document as DocumentoWord
        return "\n".join(p.text for p in DocumentoWord(ruta).paragraphs)
    if sufijo == ".pdf":
        from pypdf import PdfReader
        return "\n".join(pagina.extract_text() or "" for pagina in PdfReader(ruta).pages)
    return ""


# Se parte primero por encabezado de Markdown y solo despues por tamano
# (decision 4 de la guia de Jean): asi "Cancelaciones y cambios" viaja entera en
# un fragmento en vez de quedar cortada a la mitad por un limite de caracteres.
ENCABEZADOS = [("#", "documento"), ("##", "seccion"), ("###", "subseccion")]
TAMANO_MAXIMO = 1200
SOLAPE = 120


def _cargar_documentos():
    """Devuelve los documentos fragmentados y sus identificadores para el indice RAG.

    Recorre CARPETA_DOCUMENTOS en orden, omite archivos vacios o no admitidos,
    divide Markdown por encabezados y luego todos los textos por tamano con
    solape. Cada fragmento conserva fuente y seccion; no crea embeddings aqui."""
    from langchain_core.documents import Document
    from langchain_text_splitters import MarkdownHeaderTextSplitter, RecursiveCharacterTextSplitter

    por_encabezado = MarkdownHeaderTextSplitter(headers_to_split_on=ENCABEZADOS)
    por_tamano = RecursiveCharacterTextSplitter(chunk_size=TAMANO_MAXIMO, chunk_overlap=SOLAPE)
    documentos, ids = [], []

    for archivo in sorted(CARPETA_DOCUMENTOS.rglob("*")):
        if not archivo.is_file() or archivo.suffix.lower() not in EXTENSIONES_ADMITIDAS:
            continue
        texto = _extraer_texto(archivo)
        if not texto.strip():
            continue

        es_markdown = archivo.suffix.lower() == ".md"
        secciones = (
            por_encabezado.split_text(texto)
            if es_markdown
            else [Document(page_content=texto, metadata={})]
        )

        for seccion in secciones:
            titulo = (
                seccion.metadata.get("subseccion")
                or seccion.metadata.get("seccion")
                or seccion.metadata.get("documento")
                or ""
            )

            # Una seccion larga se vuelve a partir; una corta queda en un solo fragmento.
            for i, chunk in enumerate(por_tamano.split_text(seccion.page_content)):
                # El titulo va dentro del texto que se vectoriza: ayuda a la
                # busqueda semantica y hace que el fragmento se explique solo
                # al citarlo. `contenido` guarda el chunk limpio, sin ese
                # prefijo, para mostrarlo o guardarlo aparte (Azure Search).
                cuerpo = f"{titulo}\n{chunk}" if titulo else chunk
                documentos.append(Document(
                    page_content=cuerpo,
                    metadata={
                        "fuente": archivo.name,
                        "seccion": titulo,
                        "contenido": chunk,
                    },
                ))
                ids.append(f"{archivo.name}::{titulo or 'raiz'}::{i}")

    return documentos, ids


def construir_o_cargar_indice(forzar_reindexado: bool = False):
    """Devuelve la coleccion Chroma, construyendola la primera vez."""
    global _vector_store
    from langchain_chroma import Chroma

    if forzar_reindexado and CARPETA_INDICE.exists():
        shutil.rmtree(CARPETA_INDICE)
        _vector_store = None

    if _vector_store is not None:
        return _vector_store

    _vector_store = Chroma(
        collection_name=f"catalogo_clemente_{nombre_embeddings()}",
        embedding_function=resolver_embeddings(),
        persist_directory=str(CARPETA_INDICE),
    )

    if _vector_store._collection.count() == 0:
        documentos, ids = _cargar_documentos()
        if documentos:
            _vector_store.add_documents(documents=documentos, ids=ids)
            print(f"[rag] Indexados {len(documentos)} chunks del catalogo (chroma).")

    return _vector_store


def _id_seguro(id_crudo: str) -> str:
    """Azure Search solo acepta letras/digitos/_/-/= en la key -- se codifica el id legible."""
    return base64.urlsafe_b64encode(id_crudo.encode()).decode().rstrip("=")


def _cliente_azure_search():
    """SearchClient con AZURE_SEARCH_ENDPOINT/API_KEY/INDEX; sin endpoint o clave lanza KeyError."""
    from azure.core.credentials import AzureKeyCredential
    from azure.search.documents import SearchClient

    return SearchClient(
        endpoint=os.environ["AZURE_SEARCH_ENDPOINT"],
        index_name=os.getenv("AZURE_SEARCH_INDEX", "catalogo-clemente"),
        credential=AzureKeyCredential(os.environ["AZURE_SEARCH_API_KEY"]),
    )


def _empujar_a_azure_search(cliente, documentos) -> int:
    """Vectoriza los chunks y los sube con mergeOrUpload; devuelve cuantos acepto Azure. No borra los retirados."""
    embeddings = resolver_embeddings()
    vectores = embeddings.embed_documents([d.page_content for d in documentos])

    acciones = [
        {
            "id": _id_seguro(f"{d.metadata['fuente']}::{d.metadata['seccion']}::{i}"),
            "document": d.metadata["fuente"],
            "section": d.metadata["seccion"],
            "content": d.metadata["contenido"],
            "content_vector": vector,
        }
        for i, (d, vector) in enumerate(zip(documentos, vectores))
    ]
    resultado = cliente.merge_or_upload_documents(documents=acciones)
    return sum(1 for r in resultado if r.succeeded)


def indexar_en_azure_search(forzar: bool = False) -> int:
    """Reconstruye (o completa) el indice de Azure AI Search. Idempotente: usa
    mergeOrUpload, asi que correrlo de nuevo tras editar un documento actualiza
    solo lo que cambio en vez de duplicar."""
    documentos, _ = _cargar_documentos()
    if not documentos:
        return 0
    cliente = _cliente_azure_search()
    total = _empujar_a_azure_search(cliente, documentos)
    print(f"[rag] Empujados {total}/{len(documentos)} chunks a Azure AI Search.")
    return total


def _asegurar_azure_search_indexado():
    """Primera consulta del proceso: si el indice esta vacio, lo puebla -- misma
    logica de arranque perezoso que ya usa `construir_o_cargar_indice()` con
    Chroma (`_collection.count() == 0`)."""
    global _azure_search_verificado
    if _azure_search_verificado:
        return
    cliente = _cliente_azure_search()
    if cliente.get_document_count() == 0:
        documentos, _ = _cargar_documentos()
        if documentos:
            total = _empujar_a_azure_search(cliente, documentos)
            print(f"[rag] Indexados {total}/{len(documentos)} chunks del catalogo (azure_search).")
    _azure_search_verificado = True


def _buscar_azure_search(pregunta: str, k: int) -> list[Fragmento]:
    """Busqueda vectorial en Azure AI Search; los errores del SDK se propagan al llamador."""
    from azure.search.documents.models import VectorizedQuery

    _asegurar_azure_search_indexado()
    cliente = _cliente_azure_search()
    vector = resolver_embeddings().embed_query(pregunta)
    resultados = cliente.search(
        search_text=None,
        vector_queries=[VectorizedQuery(vector=vector, k_nearest_neighbors=k, fields="content_vector")],
        select=["document", "section", "content"],
        top=k,
    )
    return [
        Fragmento(
            texto=r["content"],
            fuente=f"{r['document']} > {r['section']}" if r.get("section") else r.get("document", "catalogo"),
            score=float(r.get("@search.score", 0.0)),
        )
        for r in resultados
    ]


def buscar(pregunta: str, k: int = 4) -> list[Fragmento]:
    """Busqueda semantica sobre el catalogo validado del restaurante."""
    if os.getenv("RAG_BACKEND", "chroma") == "azure_search":
        return _buscar_azure_search(pregunta, k)

    store = construir_o_cargar_indice()
    resultados = store.similarity_search_with_score(pregunta, k=k)
    return [
        Fragmento(
            texto=doc.page_content,
            fuente=(
                f"{doc.metadata.get('fuente', 'catalogo')} > {doc.metadata['seccion']}"
                if doc.metadata.get("seccion")
                else doc.metadata.get("fuente", "catalogo")
            ),
            score=float(score),
        )
        for doc, score in resultados
    ]


if __name__ == "__main__":
    from ...config import Config   # carga el .env antes de resolver los embeddings

    Config.desde_entorno()
    if os.getenv("RAG_BACKEND", "chroma") == "azure_search":
        indexar_en_azure_search()
    else:
        construir_o_cargar_indice(forzar_reindexado="--reindexar" in sys.argv)
    for fragmento in buscar("hasta cuando puedo cancelar una reserva"):
        print(f"- ({fragmento.fuente}) {fragmento.texto[:120]}...")
