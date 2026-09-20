"""
Tools de los tres agentes -- responsables: Christian, Jean.

Una tool nunca habla con un archivo ni con una base de datos directamente:
llama al servicio correspondiente (`app/reservas`, `app/incidencias`,
`app/agentes/rag`). Ese es el limite que permite que Miguel cambie el motor de
reservas sin tocar ni un agente.

Aqui vive ademas `con_traza`, el decorador que instrumenta cada herramienta
(idea de la guia de Jean, seccion 7.2): sin el, las metricas del proyecto no
pueden decir cuantas tools se llamaron, cuales tardan ni cuales fallan.
"""

import functools
import logging
import time

from ...observabilidad.trazas import registrar
from ...seguridad.pii import redactar_pii

log = logging.getLogger("clemente")

# Cuanto de la respuesta de una tool se guarda en la traza. Es un recorte a
# proposito: alcanza para auditar que dijo la herramienta, sin convertir las
# trazas en una copia de la base de datos del restaurante.
LARGO_SALIDA_EN_TRAZA = 400


def limpiar_texto(valor, maximo: int) -> str:
    """Deja `valor` en una sola linea, sin caracteres de control ni invisibles, y con un largo maximo.

    Lo que el cliente escribe en un nombre, una nota o una descripcion se guarda y
    despues vuelve a leerlo el modelo (ficha, resumenes, tickets): acotarlo y
    quitarle saltos de linea reduce el espacio para instrucciones escondidas."""
    texto = "".join(c if c.isprintable() else " " for c in str(valor or ""))
    return " ".join(texto.split())[:maximo]


def con_traza(funcion):
    """
    Registra cada llamada a una tool: cuanto tardo, si fallo y en que sesion.

    Se aplica DEBAJO de `@tool`, para que LangChain siga viendo la firma y el
    docstring originales (que son el contrato que lee el modelo):

        @tool
        @con_traza
        def consultar_disponibilidad(...): ...

    El `sesion_id` sale del `runtime` que inyecta `create_agent`; si la tool no
    lo recibe, la traza queda igual pero sin hilo.
    """

    @functools.wraps(funcion)
    def envoltura(*args, **kwargs):
        """Ejecuta la herramienta original y registra nombre, resultado y duracion por sesion.

        Obtiene la sesion del runtime inyectado; si la herramienta falla, registra
        el error y lo propaga. Devuelve el resultado original sin modificarlo."""
        runtime = kwargs.get("runtime") or next(
            (a for a in args if hasattr(a, "context")), None
        )
        sesion = getattr(getattr(runtime, "context", None), "sesion_id", "desconocida")
        inicio = time.perf_counter()

        try:
            resultado = funcion(*args, **kwargs)
        except Exception as error:
            # Solo el tipo: el mensaje puede traer hosts o URLs y esta traza se lee desde /api/trazas.
            log.warning("tool %s fallo (sesion %s): %s: %s", funcion.__name__, sesion,
                        type(error).__name__, redactar_pii(str(error)))
            registrar(
                "tool", sesion,
                detalle={"tool": funcion.__name__, "estado": "error", "error": type(error).__name__},
                duracion_ms=(time.perf_counter() - inicio) * 1000,
            )
            raise

        registrar(
            "tool", sesion,
            detalle={
                "tool": funcion.__name__,
                "estado": "ok",
                # Que devolvio la tool, recortado. Sin esto la traza dice que se
                # llamo a `consultar_disponibilidad` pero no que respondio, y no
                # se puede distinguir "consulto y reporto fielmente" de "consulto
                # y luego invento". Lo pidio la evaluacion del 2026-09-07: el juez
                # penalizaba respuestas correctas por no poder verlo.
                "salida": str(resultado)[:LARGO_SALIDA_EN_TRAZA],
            },
            duracion_ms=(time.perf_counter() - inicio) * 1000,
        )
        return resultado

    return envoltura
