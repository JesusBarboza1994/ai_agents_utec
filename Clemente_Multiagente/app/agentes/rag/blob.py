"""
Lectura de los documentos fuente del RAG desde Azure Blob Storage.

Los dos indices toman sus archivos de la misma cuenta, cada uno de su
contenedor: el catalogo de AZURE_STORAGE_CONTAINER_CATALOGO y los casos de
incidencias de AZURE_STORAGE_CONTAINER_INCIDENCIAS. El Blob es la unica fuente:
editar un documento es subirlo al contenedor y reindexar.

Autenticacion, en este orden:
  1. AZURE_STORAGE_CONNECTION_STRING, si existe (clave de la cuenta).
  2. AZURE_STORAGE_ACCOUNT_URL (ej. https://stclmt01.blob.core.windows.net) con
     Entra ID via DefaultAzureCredential: el `az login` en local o el login OIDC
     del workflow en GitHub. Sin clave que guardar; la identidad necesita el rol
     "Storage Blob Data Reader" sobre la cuenta.
"""

import os
from pathlib import PurePosixPath


def _cliente_contenedor(contenedor: str):
    """ContainerClient con connection string o, si no hay, con Entra ID sobre la URL de la cuenta."""
    from azure.storage.blob import ContainerClient

    conexion = os.getenv("AZURE_STORAGE_CONNECTION_STRING")
    if conexion:
        return ContainerClient.from_connection_string(conexion, contenedor)
    url = os.getenv("AZURE_STORAGE_ACCOUNT_URL")
    if not url:
        raise KeyError(
            "Falta AZURE_STORAGE_ACCOUNT_URL (o AZURE_STORAGE_CONNECTION_STRING): "
            "sin fuente en el Blob no se reindexa."
        )
    from azure.identity import DefaultAzureCredential

    return ContainerClient(account_url=url, container_name=contenedor, credential=DefaultAzureCredential())


def leer_contenedor(contenedor: str, extensiones: set[str]) -> list[tuple[str, bytes]]:
    """(nombre, bytes) de cada blob del contenedor con una de las extensiones, ordenados por nombre."""
    cliente = _cliente_contenedor(contenedor)
    return sorted(
        (blob.name, cliente.download_blob(blob.name).readall())
        for blob in cliente.list_blobs()
        if PurePosixPath(blob.name).suffix.lower() in extensiones
    )
