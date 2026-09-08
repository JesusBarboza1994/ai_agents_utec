"""
Punto de entrada de Clemente para LangGraph Studio.

Studio (la pestana de LangSmith) no dibuja el grafo a partir de las trazas:
se conecta a un servidor LangGraph y le pregunta que grafos expone. Ese
servidor se levanta en local con

    langgraph dev

que lee `langgraph.json`, y `langgraph.json` apunta al objeto `grafo` de este
archivo.

Por que un archivo aparte y no `app/orquestador/grafo.py` directamente: ese
modulo usa imports relativos (`from ..agentes import AGENTES`) y el cargador
de LangGraph importa el archivo suelto, fuera del paquete, con lo que esos
imports fallan. Aqui la importacion es absoluta desde la raiz del proyecto.

El grafo que se expone es EL MISMO que atiende el webchat y WhatsApp: Studio
no ve una copia hecha para la demo.
"""

from app.config import Config                                  # importa .env al cargarse
from app.observabilidad.trazas import configurar_observabilidad
from app.orquestador.grafo import obtener_grafo

_config = Config.desde_entorno()

# `configurar_observabilidad` no usa el primer parametro (es la app Flask):
# aqui solo interesa que deje LangSmith y el logging igual que en el servidor,
# para que lo que se pruebe en Studio caiga en el mismo proyecto de trazas.
configurar_observabilidad(None, _config)

grafo = obtener_grafo()
