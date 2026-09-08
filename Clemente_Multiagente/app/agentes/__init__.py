"""
Los agentes especializados de Clemente -- responsables: Christian, Jean.

    reservas      -> Agente de Reservas y Capacidad
    incidencias   -> Agente de Incidencias y Experiencia (customer care)

Cada modulo expone una sola funcion publica, `responder(...)`, con la misma
firma. El orquestador elige un nombre y llama. Agregar un tercer agente =
un modulo mas con esa misma firma, registrado aqui.

Hasta el 2026-09-07 habia un tercero, `conocimiento`, que respondia las
preguntas frecuentes con RAG. Se elimino tras la asesoria con Boris: el
catalogo era "un RAG muy ligero" que no justificaba un agente con su propia
profile card, su propio nivel de autonomia y su propio nivel de criticidad.
Su conocimiento subio al orquestador (ver `app/orquestador/informacion.py`),
que ahora responde el mismo esas consultas. El RAG no desaparecio: cambio de
dueno. Detalle y citas en ASESORIA_01_BORIS_ACUERDOS.md, Acuerdo 1.
"""

from . import incidencias, reservas

# Registro que consume el orquestador. La clave es el valor del tipo `Ruta`
# en app/contratos.py -- si se agrega una ruta alla, se registra aca.
AGENTES = {
    "reservas": reservas.responder,
    "incidencias": incidencias.responder,
}

__all__ = ["AGENTES"]
