"""
Contrato de errores entre las tools y los servicios de negocio (A9 del plan).

Regla acordada con Marc (seccion 2.4 del plan del 18/09): el servicio de
reservas devuelve objetos/listas y senala una regla de negocio incumplida
con `ValueError` (sin mesa, datos invalidos). Cualquier OTRA excepcion
-- Postgres caido, pool sin contexto, timeout -- es un fallo de
infraestructura, y la tool no puede esconderlo como "sin disponibilidad" ni
como exito: lo traduce a un texto explicito, lo deja en la traza y marca el
contexto para que el canal y la evaluacion lo vean.
"""

from typing import Any, Callable

from ..observabilidad.trazas import registrar


class ServicioNoDisponible(RuntimeError):
    """El servicio de negocio fallo por infraestructura; la operacion no se hizo o no se sabe."""

    def __init__(self, operacion: str):
        """Guarda la operacion que fallo para que la tool arme su texto."""
        super().__init__(f"servicio no disponible en {operacion}")
        self.operacion = operacion


def intentar(contexto, operacion: str, funcion: Callable[..., Any], *args, **kwargs) -> Any:
    """Ejecuta una llamada al servicio distinguiendo regla de negocio de fallo de infraestructura.

    `ValueError` se propaga tal cual (es el contrato del servicio). Cualquier
    otra excepcion se registra completa en la traza `servicio_error`, deja
    `contexto.datos["servicio_reservas"]` y se convierte en
    ServicioNoDisponible, que las tools traducen a texto. `contexto` puede
    ser None cuando no hay turno (ficha, utilidades)."""
    try:
        return funcion(*args, **kwargs)
    except ValueError:
        raise
    except Exception as error:
        sesion = getattr(contexto, "sesion_id", "desconocida")
        registrar("servicio_error", sesion, agente="reservas",
                  detalle={"operacion": operacion, "error": f"{type(error).__name__}: {error}"[:300]})
        if contexto is not None:
            contexto.datos["servicio_reservas"] = {"estado": "no_disponible", "operacion": operacion}
        raise ServicioNoDisponible(operacion) from error
