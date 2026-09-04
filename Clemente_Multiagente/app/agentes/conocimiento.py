"""
Agente de Conocimiento (FAQs y politicas) -- STUB TEMPORAL.

Implementacion real: Christian y Jean, rama `feat/agentes-conocimiento`.

El agente definitivo responde unicamente desde el catalogo validado del
restaurante, recuperado con RAG (indice Chroma sobre `rag/documentos/`, que
si estan en esta rama). Es la fuente unica de verdad de las politicas: los
otros dos agentes se las consultan a el en vez de mantener su propia copia.

Este stub solo respeta la firma para que el sistema completo arranque.
"""


def responder(texto: str, sesion_id: str, historial: list[dict] | None = None) -> str:
    return (
        "Puedo ayudarte con horarios, ubicacion, carta y politicas del restaurante. "
        "Estoy consultando la informacion y te respondo enseguida."
    )
