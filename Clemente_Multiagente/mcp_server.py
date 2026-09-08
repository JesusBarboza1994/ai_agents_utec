"""
Punto de entrada del servidor MCP de tickets, para las herramientas de linea de comandos.

Existe por la misma razon que `studio.py`: las utilidades externas
(`fastmcp inspect`, `fastmcp dev`, `fastmcp run`, el MCP Inspector) cargan el
archivo del servidor **suelto**, sin paquete padre, y ahi las importaciones
relativas de `app/incidencias/mcp_trello.py` (`from ..contratos import ...`)
fallan con "attempted relative import with no known parent package".

Este archivo agrega la raiz del proyecto al `sys.path`, importa el servidor con
ruta absoluta y lo vuelve a exponer. La logica no vive aqui: vive en
`app/incidencias/mcp_trello.py`, que es lo que usa la aplicacion.

    fastmcp inspect mcp_server.py:mcp     # que herramientas publica, en texto
    fastmcp dev     mcp_server.py:mcp     # el MCP Inspector: interfaz web
    fastmcp run     mcp_server.py:mcp     # levantarlo por stdio
"""

import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from app.config import Config  # noqa: E402
from app.incidencias.mcp_trello import mcp  # noqa: E402

# Carga el .env: sin esto el servidor no encuentra las credenciales de Trello y
# cae al registro local, que para inspeccionar da igual pero para probar no.
Config.desde_entorno()

__all__ = ["mcp"]
