"""
Lectura de los documentos fuente del RAG desde Azure Blob Storage.

Los dos indices toman sus archivos de la misma cuenta (AZURE_STORAGE_CONNECTION_STRING),
cada uno de su contenedor: el catalogo de AZURE_STORAGE_CONTAINER_CATALOGO y los
casos de incidencias de AZURE_STORAGE_CONTAINER_INCIDENCIAS. El Blob es la unica
fuente: editar un documento es subirlo al contenedor y reindexar.
"""

import os
from pathlib import PurePosixPath


def leer_contenedor(contenedor: str, extensiones: set[str]) -> list[tuple[str, bytes]]:
    """(nombre, bytes) de cada blob del contenedor con una de las extensiones, ordenados por nombre.

    Sin AZURE_STORAGE_CONNECTION_STRING lanza KeyError: sin fuente no se reindexa."""
    from azure.storage.blob import ContainerClient

    cliente = ContainerClient.from_connection_string(
        os.environ["AZURE_STORAGE_CONNECTION_STRING"], contenedor,
    )
    return sorted(
        (blob.name, cliente.download_blob(blob.name).readall())
        for blob in cliente.list_blobs()
        if PurePosixPath(blob.name).suffix.lower() in extensiones
    )
