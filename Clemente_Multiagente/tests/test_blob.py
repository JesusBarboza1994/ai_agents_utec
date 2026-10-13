"""Lectura de documentos del RAG desde Blob: Entra ID por URL o connection string; sin red."""
from types import SimpleNamespace

import azure.identity
import azure.storage.blob
import pytest

from app.agentes.rag import blob


class ContenedorFalso:
    """Contenedor simulado: lista blobs y devuelve su contenido."""

    def __init__(self, archivos):
        """Guarda nombre -> bytes."""
        self.archivos = archivos

    def list_blobs(self):
        """Lista los blobs por nombre."""
        return [SimpleNamespace(name=n) for n in self.archivos]

    def download_blob(self, nombre):
        """Devuelve un objeto con readall(), como el SDK."""
        return SimpleNamespace(readall=lambda: self.archivos[nombre])


ARCHIVOS = {"b.md": b"segundo", "a.md": b"primero", "notas.txt": b"no"}


def test_sin_clave_usa_entra_id_sobre_la_url(monkeypatch):
    """Sin connection string se conecta a la URL de la cuenta con DefaultAzureCredential."""
    pedidos = {}

    def construir(account_url, container_name, credential):
        """Registra con que se construyo el cliente."""
        pedidos.update(url=account_url, contenedor=container_name, credencial=credential)
        return ContenedorFalso(ARCHIVOS)

    monkeypatch.delenv("AZURE_STORAGE_CONNECTION_STRING", raising=False)
    monkeypatch.setenv("AZURE_STORAGE_ACCOUNT_URL", "https://cuenta.blob.core.windows.net")
    monkeypatch.setattr(azure.identity, "DefaultAzureCredential", lambda: "credencial-entra")
    monkeypatch.setattr(azure.storage.blob, "ContainerClient", construir)

    assert blob.leer_contenedor("catalogo", {".md"}) == [("a.md", b"primero"), ("b.md", b"segundo")]
    assert pedidos == {"url": "https://cuenta.blob.core.windows.net", "contenedor": "catalogo",
                       "credencial": "credencial-entra"}


def test_connection_string_tiene_prioridad(monkeypatch):
    """Si hay connection string se usa esa, aunque tambien haya URL."""
    usados = []

    def desde_cadena(conexion, contenedor):
        """Registra la cadena y el contenedor."""
        usados.append((conexion, contenedor))
        return ContenedorFalso(ARCHIVOS)

    monkeypatch.setenv("AZURE_STORAGE_CONNECTION_STRING", "cadena-de-prueba")
    monkeypatch.setenv("AZURE_STORAGE_ACCOUNT_URL", "https://cuenta.blob.core.windows.net")
    monkeypatch.setattr(azure.storage.blob.ContainerClient, "from_connection_string", staticmethod(desde_cadena))

    assert [n for n, _ in blob.leer_contenedor("incidencias", {".md", ".txt"})] == ["a.md", "b.md", "notas.txt"]
    assert usados == [("cadena-de-prueba", "incidencias")]


def test_sin_configuracion_falla_con_mensaje_claro(monkeypatch):
    """Sin URL ni connection string no se reindexa: error explicito, no un indice vacio."""
    monkeypatch.delenv("AZURE_STORAGE_CONNECTION_STRING", raising=False)
    monkeypatch.delenv("AZURE_STORAGE_ACCOUNT_URL", raising=False)

    with pytest.raises(KeyError, match="AZURE_STORAGE_ACCOUNT_URL"):
        blob.leer_contenedor("catalogo", {".md"})
