"""
Indice `incidencias-clemente`: casos de incidencias resueltos -- segundo indice
RAG, separado del catalogo (`indice_catalogo.py`).

Cada caso es un .md con el ticket que registro el agente y la solucion que le
dio el restaurante. El agente de Incidencias los consulta para orientar una
respuesta rapida cuando llega un reclamo parecido.

Los .md viven en Azure Blob Storage (contenedor AZURE_STORAGE_CONTAINER_INCIDENCIAS,
por defecto "incidencias"), que es la unica fuente: agregar o editar un caso es
subir el .md al contenedor. La ingesta es la misma idea que la del catalogo:
este modulo los lee del Blob, los parte, vectoriza y sube al indice de Azure AI
Search. Reemplaza al pipeline nativo anterior (indexer -> skillset), que no
partia nada ni dejaba elegir el analizador de texto.

  - Chunking: un caso = un chunk. Ticket y solucion viajan juntos, que es lo
    que se recupera; la ficha (tipo, prioridad, canal, plazo) va como metadata
    filtrable.
  - Analizador propio en espanol (`es-clemente`) en los campos de texto: la
    busqueda es hibrida, y sin el, palabras como "me" o "la" contaban como
    coincidencia y las tildes separaban "fría" de "fria".

Requiere AZURE_SEARCH_ENDPOINT y AZURE_SEARCH_API_KEY, AZURE_STORAGE_CONNECTION_STRING
para reindexar, y los mismos embeddings en ingesta y consulta
(text-embedding-3-small). Si algo falla en la consulta, la tool que lo llama lo
informa y el reclamo se registra igual.

Los embeddings se piden por lotes: el deployment admite 10.000 tokens por
minuto y los 30 casos juntos lo superan, asi que una sola llamada recibia 429
en cada reintento.

Reindexar tras editar o agregar casos:
    python -m app.agentes.rag.indice_incidencias
Cambiar el analizador o el esquema exige borrar el indice antes: Azure no
cambia el analizador de un campo existente.
"""

import os
import re
import time
from pathlib import PurePosixPath

from ...contratos import Fragmento
from ...llm import resolver_embeddings
from .blob import leer_contenedor
from .indice_catalogo import _borrar_obsoletos_azure_search, _id_seguro

DIMENSION_VECTOR = 1536   # text-embedding-3-small, igual que el indice del catalogo
ANALIZADOR = "es-clemente"
LOTE_EMBEDDINGS = 6           # ~2.700 tokens por llamada, holgado frente a 10.000/min
ESPERA_LIMITE_S = 65          # el 429 de Azure OpenAI pide reintentar en 60 s
REINTENTOS_LIMITE = 5

TIPOS = ("espera", "servicio", "producto", "reserva", "otro")


def _nombre_indice() -> str:
    """Nombre del indice de casos (AZURE_SEARCH_INDEX_INCIDENCIAS)."""
    return os.getenv("AZURE_SEARCH_INDEX_INCIDENCIAS", "incidencias-clemente")


def _ficha(texto: str, clave: str) -> str:
    """Valor de una linea de la ficha del caso, p. ej. '- **Tipo:** espera'."""
    coincidencia = re.search(rf"^- \*\*{re.escape(clave)}:\*\*\s*(.+)$", texto, re.MULTILINE)
    return coincidencia.group(1).strip() if coincidencia else ""


def _leer_casos_blob() -> list[tuple[str, str]]:
    """(nombre, texto) de cada .md del contenedor de casos; sin connection string lanza KeyError."""
    contenedor = os.getenv("AZURE_STORAGE_CONTAINER_INCIDENCIAS", "incidencias")
    return [(nombre, contenido.decode("utf-8")) for nombre, contenido in leer_contenedor(contenedor, {".md"})]


def _cargar_casos(casos_crudos: list[tuple[str, str]] | None = None):
    """Un chunk por caso: el .md completo, con su titulo y su ficha como metadata.

    `casos_crudos` son pares (nombre, texto); por defecto se leen del Blob."""
    from langchain_core.documents import Document

    if casos_crudos is None:
        casos_crudos = _leer_casos_blob()
    documentos, ids = [], []
    for nombre, texto in sorted(casos_crudos):
        titulo = next((l.lstrip("# ").strip() for l in texto.splitlines() if l.startswith("# ")),
                      PurePosixPath(nombre).stem)
        plazo = re.search(r"\d+", _ficha(texto, "Plazo de atención"))
        documentos.append(Document(
            page_content=texto,
            metadata={
                "fuente": nombre,
                "seccion": titulo,
                "caso_id": _ficha(texto, "Código"),
                "tipo": _ficha(texto, "Tipo"),
                "prioridad": _ficha(texto, "Prioridad"),
                "canal": _ficha(texto, "Canal"),
                "plazo_horas": int(plazo.group()) if plazo else None,
                "fecha_hecho": _ficha(texto, "Fecha del hecho"),
            },
        ))
        ids.append(nombre)
    return documentos, ids


def _definir_indice():
    """Esquema del indice: texto con el analizador en espanol, ficha filtrable y vector HNSW."""
    from azure.search.documents.indexes.models import (
        CustomAnalyzer, HnswAlgorithmConfiguration, LexicalTokenizerName, SearchableField,
        SearchField, SearchFieldDataType, SearchIndex, SimpleField, SnowballTokenFilter,
        SnowballTokenFilterLanguage, StopwordsList, StopwordsTokenFilter, TokenFilterName,
        VectorSearch, VectorSearchProfile,
    )

    texto = SearchFieldDataType.String
    return SearchIndex(
        name=_nombre_indice(),
        fields=[
            SimpleField(name="id", type=texto, key=True),
            SimpleField(name="document", type=texto, filterable=True),
            SearchableField(name="section", type=texto, analyzer_name=ANALIZADOR),
            SearchableField(name="content", type=texto, analyzer_name=ANALIZADOR),
            SimpleField(name="caso_id", type=texto, filterable=True),
            SimpleField(name="tipo", type=texto, filterable=True),
            SimpleField(name="prioridad", type=texto, filterable=True),
            SimpleField(name="canal", type=texto, filterable=True),
            SimpleField(name="plazo_horas", type=SearchFieldDataType.Int32, filterable=True),
            SimpleField(name="fecha_hecho", type=texto),
            SearchField(
                name="content_vector",
                type=SearchFieldDataType.Collection(SearchFieldDataType.Single),
                searchable=True,
                vector_search_dimensions=DIMENSION_VECTOR,
                vector_search_profile_name="perfil-hnsw",
            ),
        ],
        vector_search=VectorSearch(
            algorithms=[HnswAlgorithmConfiguration(name="hnsw")],
            profiles=[VectorSearchProfile(name="perfil-hnsw", algorithm_configuration_name="hnsw")],
        ),
        # Minusculas, sin acentos, sin stopwords en espanol y stemming en espanol. Los
        # filtros con parametros se declaran aqui y el analizador los nombra.
        analyzers=[CustomAnalyzer(
            name=ANALIZADOR,
            tokenizer_name=LexicalTokenizerName.STANDARD,
            token_filters=[TokenFilterName.LOWERCASE, TokenFilterName.ASCII_FOLDING, "stop-es", "snowball-es"],
        )],
        token_filters=[
            StopwordsTokenFilter(name="stop-es", stopwords_list=StopwordsList.SPANISH),
            SnowballTokenFilter(name="snowball-es", language=SnowballTokenFilterLanguage.SPANISH),
        ],
    )


def _clientes():
    """Clientes de indices y de documentos de Azure AI Search; sin endpoint o clave lanza KeyError."""
    from azure.core.credentials import AzureKeyCredential
    from azure.search.documents import SearchClient
    from azure.search.documents.indexes import SearchIndexClient

    endpoint = os.environ["AZURE_SEARCH_ENDPOINT"]
    credencial = AzureKeyCredential(os.environ["AZURE_SEARCH_API_KEY"])
    return (
        SearchIndexClient(endpoint=endpoint, credential=credencial),
        SearchClient(endpoint=endpoint, index_name=_nombre_indice(), credential=credencial),
    )


def _vectorizar(textos: list[str]) -> list[list[float]]:
    """Embeddings por lotes de LOTE_EMBEDDINGS; ante un 429 espera y reintenta el mismo lote."""
    from openai import RateLimitError

    modelo = resolver_embeddings()
    vectores: list[list[float]] = []
    for inicio in range(0, len(textos), LOTE_EMBEDDINGS):
        lote = textos[inicio:inicio + LOTE_EMBEDDINGS]
        for intento in range(1, REINTENTOS_LIMITE + 1):
            try:
                vectores += modelo.embed_documents(lote)
                break
            except RateLimitError:
                if intento == REINTENTOS_LIMITE:
                    raise
                print(f"[rag] Limite de embeddings (429): espero {ESPERA_LIMITE_S} s y reintento.")
                time.sleep(ESPERA_LIMITE_S)
    return vectores


def indexar_casos(casos_crudos: list[tuple[str, str]] | None = None) -> int:
    """Crea el indice si falta y sube todos los casos; devuelve cuantos acepto Azure.

    Idempotente: mergeOrUpload sobre ids estables (el nombre del blob), y tras una
    carga completa borra los casos que ya no estan en el contenedor. Con el
    contenedor vacio no toca el indice."""
    documentos, ids = _cargar_casos(casos_crudos)
    if not documentos:
        return 0
    cliente_indices, cliente = _clientes()
    cliente_indices.create_or_update_index(_definir_indice())

    vectores = _vectorizar([d.page_content for d in documentos])
    acciones = [
        {
            "id": _id_seguro(id_caso),
            "document": d.metadata["fuente"],
            "section": d.metadata["seccion"],
            "content": d.page_content,
            "caso_id": d.metadata["caso_id"],
            "tipo": d.metadata["tipo"],
            "prioridad": d.metadata["prioridad"],
            "canal": d.metadata["canal"],
            "plazo_horas": d.metadata["plazo_horas"],
            "fecha_hecho": d.metadata["fecha_hecho"],
            "content_vector": vector,
        }
        for id_caso, d, vector in zip(ids, documentos, vectores)
    ]
    resultado = cliente.merge_or_upload_documents(documents=acciones)
    total = sum(1 for r in resultado if r.succeeded)
    print(f"[rag] Casos de incidencias: {total}/{len(documentos)} en {_nombre_indice()}.")
    if total == len(documentos):
        borrados = _borrar_obsoletos_azure_search(cliente, {_id_seguro(i) for i in ids})
        if borrados:
            print(f"[rag] Borrados {borrados} casos que ya no estan en el contenedor.")
    else:
        print("[rag] No se borraron casos obsoletos: la carga no fue completa.")
    return total


def buscar_casos(descripcion: str, k: int = 2, tipo: str = "") -> list[Fragmento]:
    """Casos resueltos parecidos al reclamo descrito, del mas al menos cercano.

    Busqueda hibrida (texto + vector). `tipo` (espera, servicio, producto, reserva
    u otro) acota los casos a ese tipo; vacio = todos."""
    from azure.core.credentials import AzureKeyCredential
    from azure.search.documents import SearchClient
    from azure.search.documents.models import VectorizedQuery

    cliente = SearchClient(
        endpoint=os.environ["AZURE_SEARCH_ENDPOINT"],
        index_name=_nombre_indice(),
        credential=AzureKeyCredential(os.environ["AZURE_SEARCH_API_KEY"]),
    )
    vector = resolver_embeddings().embed_query(descripcion)
    resultados = cliente.search(
        search_text=descripcion,
        vector_queries=[VectorizedQuery(vector=vector, k_nearest_neighbors=k, fields="content_vector")],
        select=["document", "content"],
        filter=f"tipo eq '{tipo}'" if tipo in TIPOS else None,
        top=k,
    )
    return [
        Fragmento(texto=r["content"], fuente=r["document"], score=float(r.get("@search.score", 0.0)))
        for r in resultados
    ]


if __name__ == "__main__":
    from ...config import Config   # carga el .env antes de resolver los embeddings

    Config.desde_entorno()
    indexar_casos()
    for fragmento in buscar_casos("me cobraron dos veces la tarjeta"):
        print(f"- ({fragmento.fuente}) score={fragmento.score:.3f}")
