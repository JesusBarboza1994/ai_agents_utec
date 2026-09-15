"""
Gestor de Reservas -- responsable: Miguel.

Punto de entrada del modulo: `obtener_servicio()` devuelve la implementacion
configurada en CLEMENTE_BACKEND_RESERVAS. Los agentes importan SOLO esta
funcion; nunca la clase concreta.
"""

import os

from ..contratos import ServicioReservas

_servicio: ServicioReservas | None = None


def obtener_servicio() -> ServicioReservas:
    """Singleton del servicio de reservas segun el backend configurado."""
    global _servicio
    if _servicio is None:
        backend = os.getenv("CLEMENTE_BACKEND_RESERVAS", "json")
        if backend == "json":
            from .servicio_json import ServicioReservasJSON
            _servicio = ServicioReservasJSON()
        elif backend == "sqlite":
            from .servicio_sqlite import ServicioReservasSQLite
            _servicio = ServicioReservasSQLite()
        else:
            raise ValueError(f"Backend de reservas desconocido: {backend!r}")
    return _servicio


def reiniciar_servicio() -> None:
    """Usado por las pruebas para forzar una instancia limpia."""
    global _servicio
    _servicio = None
