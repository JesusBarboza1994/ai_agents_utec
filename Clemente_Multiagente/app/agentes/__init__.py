"""
Los tres agentes de Clemente -- responsables: Christian, Jean.

    reservas      -> Agente de Reservas y Capacidad
    incidencias   -> Agente de Incidencias y Experiencia
    conocimiento  -> Agente de Conocimiento (FAQs y politicas, con RAG)

Cada modulo expone una sola funcion publica, `responder(...)`, con la misma
firma. El orquestador (Jesus) no sabe nada mas de ellos: elige un nombre y
llama. Agregar un cuarto agente = un modulo mas con esa misma firma.
"""

from . import conocimiento, incidencias, reservas

# Registro que consume el orquestador. La clave es el valor del tipo `Ruta`
# en app/contratos.py -- si se agrega una ruta alla, se registra aca.
AGENTES = {
    "reservas": reservas.responder,
    "incidencias": incidencias.responder,
    "conocimiento": conocimiento.responder,
}

__all__ = ["AGENTES"]
