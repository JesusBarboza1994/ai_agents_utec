"""
Los tickets de incidencia, hablados por MCP -- Sesion 16.

Este es el lado **cliente**: implementa el mismo contrato `ServicioIncidencias`
que los otros dos backends, pero en vez de llamar a la API de Trello por su
cuenta, le pide las herramientas al servidor MCP de `mcp_trello.py`.

Que gana el proyecto con la vuelta de mas
------------------------------------------
Podriamos llamar a Trello directamente -- de hecho `servicio_trello.py` lo hace,
y sigue ahi como respaldo. Meter el protocolo en el medio compra tres cosas:

1. **El limite de permisos deja de ser una promesa nuestra.** El servidor MCP no
   publica ninguna herramienta para cerrar un ticket ni para compensar. El agente
   no puede llamar lo que no existe del otro lado, y el catalogo de herramientas
   es lo primero que un cliente MCP pide al conectarse. Se puede *auditar* con
   `--listar`, sin leer nuestro codigo.
2. **Las herramientas se descubren, no se escriben.** Si manana el restaurante
   cambia Trello por Jira, cambia el servidor; el agente no se entera.
3. **Es lo que pidio el docente** [05:09] y es el contenido de la Sesion 16, que
   hasta ahora el proyecto final no estaba usando.

El transporte, y por que hay dos
---------------------------------
* Sin `TRELLO_MCP_URL`, el cliente se conecta al servidor **en memoria**: mismo
  proceso, sin puerto. Asi corren las pruebas, la evaluacion y el red team, que
  no pueden depender de que alguien haya levantado un servidor a mano.
* Con `TRELLO_MCP_URL` (por ejemplo `http://localhost:8100/mcp`), se conecta por
  HTTP a un servidor de verdad. Es como se muestra en la demostracion, y es lo
  que hace visible que hay un protocolo y dos procesos.

Las herramientas y el limite de permisos son identicos en los dos casos. Lo unico
que cambia es por donde viajan los mensajes.
"""

import asyncio
import logging
import os
from concurrent.futures import ThreadPoolExecutor

from ..contratos import Incidencia
from .servicio_json import ServicioIncidenciasJSON

log = logging.getLogger("clemente.mcp")


def _ejecutar(corutina):
    """
    Corre una corutina desde codigo sincrono, haya o no un bucle de eventos.

    Hace falta porque las tools de LangChain son sincronas y `fastmcp.Client` es
    asincrono. Si ya hay un bucle andando en este hilo -- pasa cuando el agente
    corre dentro de LangGraph -- no se puede usar `asyncio.run`, asi que la
    corutina se manda a un hilo aparte con su propio bucle.
    """
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(corutina)

    with ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(asyncio.run, corutina).result()


def destino_mcp():
    """A donde se conecta el cliente: una URL, o el servidor en memoria."""
    url = os.getenv("TRELLO_MCP_URL", "").strip()
    if url:
        return url
    from .mcp_trello import mcp

    return mcp


class ServicioIncidenciasMCP:
    """
    Implementa `ServicioIncidencias` (app/contratos.py) contra el servidor MCP.

    Misma firma que los otros dos backends: los agentes y sus tools no se enteran
    de cual esta activo.
    """

    def __init__(self, destino=None, espejo: ServicioIncidenciasJSON | None = None):
        self.destino = destino if destino is not None else destino_mcp()
        # Respaldo local, por la misma razon de siempre: si el servidor no
        # responde, el reclamo del cliente no se puede perder.
        self.espejo = espejo or ServicioIncidenciasJSON()

    # ------------------------------- protocolo ------------------------------

    async def _llamar_async(self, herramienta: str, argumentos: dict):
        from fastmcp import Client

        async with Client(self.destino) as cliente:
            resultado = await cliente.call_tool(herramienta, argumentos)
        # `data` trae la salida ya deserializada segun el esquema declarado por
        # la herramienta; si el servidor no la publica, se cae al contenido.
        datos = getattr(resultado, "data", None)
        if datos is None:
            datos = getattr(resultado, "structured_content", None)
        return datos

    def llamar(self, herramienta: str, **argumentos):
        return _ejecutar(self._llamar_async(herramienta, argumentos))

    def herramientas(self) -> list[dict]:
        """
        El catalogo que publica el servidor. Es la auditoria del limite de
        permisos: lo que no aparece aqui, el agente no lo puede hacer.
        """
        async def pedir():
            from fastmcp import Client

            async with Client(self.destino) as cliente:
                return [
                    {"nombre": h.name, "descripcion": (h.description or "").split("\n")[0]}
                    for h in await cliente.list_tools()
                ]

        return _ejecutar(pedir())

    # ------------------- contrato ServicioIncidencias -----------------------

    def crear_incidencia(
        self, sesion_id: str, descripcion: str, tipo: str = "otro",
        reserva_id: str | None = None,
    ) -> Incidencia:
        try:
            datos = self.llamar(
                "crear_ticket", descripcion=descripcion, sesion_id=sesion_id,
                tipo=tipo, reserva_id=reserva_id or "",
            )
            return Incidencia(**datos)
        except Exception as error:
            log.warning("el servidor MCP no respondio (%s): se registra en local", error)
            return self.espejo.crear_incidencia(sesion_id, descripcion, tipo, reserva_id)

    def listar_incidencias(self, estado: str | None = None) -> list[Incidencia]:
        try:
            return [Incidencia(**d) for d in self.llamar("listar_tickets", estado=estado or "")]
        except Exception as error:
            log.warning("el servidor MCP no respondio (%s): se lee del registro local", error)
            return self.espejo.listar_incidencias(estado)

    def anotar(self, incidencia_id: str, texto: str) -> bool:
        """Pasa por `comentar_ticket`, que es la cuarta herramienta del servidor."""
        try:
            self.llamar("comentar_ticket", ticket_id=incidencia_id, texto=texto)
            return True
        except Exception as error:
            log.warning("no se pudo anotar en %s por MCP (%s)", incidencia_id, error)
            return self.espejo.anotar(incidencia_id, texto)

    def cerrar_incidencia(self, incidencia_id: str, nota_cierre: str = "") -> Incidencia | None:
        """
        NO pasa por MCP, y es la decision de diseno de todo este modulo.

        El servidor no publica ninguna herramienta de cierre, a proposito: el
        cierre lo confirma una persona moviendo la tarjeta en su tablero. Este
        metodo existe solo porque el contrato `ServicioIncidencias` lo declara y
        lo usa el panel del staff -- nunca un agente, que no tiene ninguna tool
        que llegue hasta aca.
        """
        from .servicio_trello import ServicioIncidenciasTrello, hay_credenciales

        if hay_credenciales():
            return ServicioIncidenciasTrello(espejo=self.espejo).cerrar_incidencia(
                incidencia_id, nota_cierre
            )
        return self.espejo.cerrar_incidencia(incidencia_id, nota_cierre)


if __name__ == "__main__":
    # python -m app.incidencias.servicio_mcp --listar
    #     muestra el catalogo de herramientas que publica el servidor: es la
    #     forma de auditar el limite de permisos sin leer el codigo
    # python -m app.incidencias.servicio_mcp --prueba
    #     abre un ticket de verdad pasando por el protocolo
    import json
    import sys

    from ..config import Config

    Config.desde_entorno()
    logging.basicConfig(level=logging.INFO, format="%(levelname)-7s | %(message)s")

    servicio = ServicioIncidenciasMCP()
    destino = os.getenv("TRELLO_MCP_URL") or "servidor en memoria (mismo proceso)"
    print(f"Destino MCP: {destino}\n")

    publicadas = servicio.herramientas()
    print("Herramientas que PUBLICA el servidor:")
    for herramienta in publicadas:
        print(f"  + {herramienta['nombre']:20} {herramienta['descripcion'][:60]}")

    prohibidas = ["cerrar_ticket", "mover_ticket", "borrar_ticket", "dar_compensacion"]
    nombres = {h["nombre"] for h in publicadas}
    print("\nHerramientas que NO existen (limite de permisos, verificado):")
    for nombre in prohibidas:
        estado = "EXPUESTA -- REVISAR" if nombre in nombres else "no existe, correcto"
        print(f"  - {nombre:20} {estado}")

    if "--prueba" in sys.argv:
        creada = servicio.crear_incidencia(
            sesion_id="prueba-mcp",
            descripcion="Ticket de prueba creado a traves del servidor MCP.",
            tipo="otro",
        )
        print(f"\nCreado por MCP: {creada.id}")
        print(json.dumps(creada.__dict__, ensure_ascii=False, indent=2))
