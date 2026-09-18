"""
Indice vectorial (RAG) del catalogo validado del restaurante -- Sesion 13.

Recorre `documentos/` (horarios, carta, politicas, servicios), parte cada
archivo en chunks y los indexa en una coleccion Chroma persistente. El
Agente de Conocimiento solo llama a `buscar()`.

Embeddings: los define EMBEDDINGS_BACKEND en el .env (ollama por defecto,
openai como alternativa). Con Ollama hace falta una sola vez:
    ollama pull nomic-embed-text

Los vectores de dos modelos distintos no son comparables, asi que el nombre
del modelo forma parte del nombre de la coleccion: cambiar de backend crea un
indice nuevo en vez de mezclar vectores incompatibles en silencio.

Reconstruir el indice tras editar los documentos:
    python -m app.agentes.rag.indice --reindexar
"""

import shutil
import sys
from pathlib import Path

from ...contratos import Fragmento
from ...llm import nombre_embeddings, resolver_embeddings

CARPETA_DOCUMENTOS = Path(__file__).parent / "documentos"
CARPETA_INDICE = Path(__file__).parent / "chroma_index"
EXTENSIONES_ADMITIDAS = {".md", ".txt", ".pdf", ".docx"}

_vector_store = None


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

        if archivo.suffix.lower() == ".md":
            secciones = por_encabezado.split_text(texto)
        else:
            secciones = [Document(page_content=texto, metadata={})]

        for seccion in secciones:
            titulo = (
                seccion.metadata.get("subseccion")
                or seccion.metadata.get("seccion")
                or seccion.metadata.get("documento")
                or ""
            )
            # Una seccion larga se vuelve a partir; una corta queda en un solo fragmento.
            for i, chunk in enumerate(por_tamano.split_text(seccion.page_content)):
                # El titulo va dentro del texto indexado: ayuda a la busqueda
                # semantica y hace que el fragmento se explique solo al citarlo.
                cuerpo = f"{titulo}\n{chunk}" if titulo else chunk
                documentos.append(Document(
                    page_content=cuerpo,
                    metadata={"fuente": archivo.name, "seccion": titulo},
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
            print(f"[rag] Indexados {len(documentos)} chunks del catalogo.")

    return _vector_store


def buscar(pregunta: str, k: int = 4) -> list[Fragmento]:
    """Busqueda semantica sobre el catalogo validado del restaurante."""
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
    construir_o_cargar_indice(forzar_reindexado="--reindexar" in sys.argv)
    for fragmento in buscar("hasta cuando puedo cancelar una reserva"):
        print(f"- ({fragmento.fuente}) {fragmento.texto[:120]}...")
