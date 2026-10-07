"""
Casos de incidencias resueltos -- segundo indice RAG, separado del catalogo.

Cada caso es un .md con el ticket que registro el agente y la solucion que le
dio el restaurante. El agente de Incidencias los consulta para orientar una
respuesta rapida cuando llega un reclamo parecido.

Viven solo en Azure. La ingesta la hace Azure AI Search con su propio
pipeline (Blob Storage `stclmt01/incidencias` -> indexer -> skillset de
embeddings -> indice `incidencias-clemente`): para agregar o editar un caso
basta subir el .md al contenedor. Aqui solo se consulta.

Requiere AZURE_SEARCH_ENDPOINT y AZURE_SEARCH_API_KEY, y que los embeddings de
la consulta sean los del skillset (text-embedding-3-small). Si algo falla, la
tool que lo llama lo informa y el reclamo se registra igual.
"""

import os

from ...contratos import Fragmento
from ...llm import resolver_embeddings


TIPOS = ("espera", "servicio", "producto", "reserva", "otro")


def buscar_casos(descripcion: str, k: int = 2, tipo: str = "") -> list[Fragmento]:
    """Casos resueltos parecidos al reclamo descrito, del mas al menos cercano.

    Busqueda hibrida (texto + vector). `tipo` (espera, servicio, producto, reserva
    u otro) acota los casos a ese tipo; vacio = todos."""
    from azure.core.credentials import AzureKeyCredential
    from azure.search.documents import SearchClient
    from azure.search.documents.models import VectorizedQuery

    cliente = SearchClient(
        endpoint=os.environ["AZURE_SEARCH_ENDPOINT"],
        index_name=os.getenv("AZURE_SEARCH_INDEX_INCIDENCIAS", "incidencias-clemente"),
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
