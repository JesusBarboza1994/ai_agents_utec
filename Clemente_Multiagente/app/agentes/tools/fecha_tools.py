"""
Tool de fecha y hora, compartida por los tres agentes.

Es la unica forma trazable de que el modelo resuelva "manana" o "este
viernes": la respuesta viene del reloj del servidor en America/Lima y queda
registrada por `con_traza`, asi que la evaluacion puede comprobar que el
turno consulto la fecha en vez de calcularla de memoria.
"""

from langchain.tools import ToolRuntime, tool

from . import con_traza

from .. import fecha as reloj


@tool
@con_traza
def get_current_datetime(runtime: ToolRuntime) -> str:
    """Devuelve la fecha, el dia de la semana y la hora actuales del restaurante
    (zona America/Lima) y a que fecha cae cada uno de los proximos siete dias.
    Usar SIEMPRE antes de convertir "hoy", "manana", "este viernes" o cualquier
    referencia relativa en una fecha concreta; nunca calcular fechas de memoria.
    """
    proximos = reloj.proximos_dias()
    manana_nombre, manana_fecha = proximos[0]
    listado = ", ".join(f"{nombre} {fecha.isoformat()}" for nombre, fecha in proximos)
    return (
        f"Hoy es {reloj.describir_ahora()}. Mañana es {manana_nombre} "
        f"{manana_fecha.isoformat()}. Próximos días: {listado}."
    )
