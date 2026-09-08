"""
CONTRATOS: las costuras entre los cuatro frentes de trabajo del Grupo 02.

Este archivo es el unico que se toca ENTRE TODOS, y solo en reunion: define
que datos se pasan de un modulo a otro. Mientras estas firmas no cambien,
cada quien puede reescribir por dentro su modulo sin romper el de nadie.

    Canal / comunicacion (Jesus)      --MensajeEntrante-->  Orquestador
    Orquestador (Jesus)               --entrada de texto->  Agentes
    Agentes (Christian, Jean)         --llaman tools---->   Servicios
    Servicios de reservas (Miguel)    --Reserva/Opcion--->  Agentes
    Todo el flujo                     --Traza----------->   Observabilidad (Adrian)

Nota de diseno: son dataclasses planas, no modelos de ORM ni de Flask, para
que los agentes se puedan probar sin levantar el servidor web.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal, Protocol

# A donde puede ir un paso del plan del orquestador.
#
# CAMBIO ACORDADO EN LA ASESORIA DEL 2026-09-07 (Boris). Este archivo se toca
# entre todos, asi que queda dicho por que: la ruta `conocimiento` desaparecio
# porque desaparecio ese agente, y en su lugar esta `informacion`, que NO es un
# agente sino el propio orquestador respondiendo (ver
# `app/orquestador/informacion.py`). Quien consuma `RespuestaClemente.agente`
# -- comunicacion, observabilidad, el panel -- debe contemplar el valor nuevo.
Ruta = Literal["reservas", "incidencias", "informacion"]


# --------------------------------------------------------------------------
# 1. Comunicacion  <->  Orquestador
# --------------------------------------------------------------------------

@dataclass
class MensajeEntrante:
    """Lo que llega de cualquier canal, ya normalizado por Comunicacion."""

    sesion_id: str                  # hilo de conversacion (thread_id del agente)
    texto: str
    canal: str = "webchat"          # webchat (desarrollo) | whatsapp (Twilio)
    nombre_cliente: str | None = None
    telefono: str | None = None


@dataclass
class RespuestaClemente:
    """Lo que el orquestador devuelve al canal."""

    texto: str
    agente: Ruta | str              # que agente respondio (para la demo y las metricas)
    sesion_id: str
    motivo_ruta: str = ""           # por que el orquestador eligio ese agente
    escalado: bool = False          # True si hay que avisar a una persona
    datos: dict[str, Any] = field(default_factory=dict)  # reserva creada, incidencia, etc.


# --------------------------------------------------------------------------
# 2. Agentes  <->  Gestor de reservas  (Miguel)
# --------------------------------------------------------------------------

@dataclass
class OpcionDisponibilidad:
    fecha: str                      # "2026-09-12"
    hora: str                       # "20:00"
    zona: str                       # "salon" | "terraza" | "barra"
    mesa_id: str
    capacidad: int


@dataclass
class Reserva:
    id: str
    nombre: str
    telefono: str
    fecha: str
    hora: str
    personas: int
    zona: str
    mesa_id: str
    estado: Literal["confirmada", "cancelada", "modificada", "pendiente_staff"] = "confirmada"
    notas: str = ""
    creada: str = field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))


class ServicioReservas(Protocol):
    """
    Interfaz que implementa el Gestor de Reservas (Miguel).

    Los agentes solo conocen ESTOS metodos. Si manana las reservas viven en
    PostgreSQL, en una API externa o en el POS del restaurante, cambia la
    implementacion y ni un agente se entera.
    """

    def consultar_disponibilidad(
        self, fecha: str, hora: str, personas: int, zona: str | None = None,
        excluir_reserva_id: str | None = None,
    ) -> list[OpcionDisponibilidad]: ...

    def crear_reserva(
        self, nombre: str, telefono: str, fecha: str, hora: str,
        personas: int, zona: str, notas: str = "",
    ) -> Reserva: ...

    def obtener_reserva(self, reserva_id: str) -> Reserva | None: ...

    def buscar_reservas_de(self, telefono: str) -> list[Reserva]: ...

    def modificar_reserva(
        self, reserva_id: str, fecha: str | None = None, hora: str | None = None,
        personas: int | None = None,
    ) -> Reserva | None: ...

    def cancelar_reserva(self, reserva_id: str) -> Reserva | None: ...


# --------------------------------------------------------------------------
# 3. Agentes  <->  Incidencias
# --------------------------------------------------------------------------

@dataclass
class Incidencia:
    id: str
    sesion_id: str
    descripcion: str
    tipo: Literal["espera", "servicio", "producto", "reserva", "otro"] = "otro"
    reserva_id: str | None = None
    estado: Literal["abierta", "en_curso", "cerrada"] = "abierta"
    responsable: str = "staff"
    plazo_horas: int = 24
    creada: str = field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))


class ServicioIncidencias(Protocol):
    def crear_incidencia(
        self, sesion_id: str, descripcion: str, tipo: str = "otro",
        reserva_id: str | None = None,
    ) -> Incidencia: ...

    def listar_incidencias(self, estado: str | None = None) -> list[Incidencia]: ...

    def anotar(self, incidencia_id: str, texto: str) -> bool:
        """
        Agrega un dato a una incidencia ya abierta, sin cambiarle el estado.

        Existe porque un mismo caso puede recibir informacion en varios turnos:
        el cliente reclama, y dos mensajes despues da su telefono. Sin esto, la
        unica forma de guardar ese telefono era abrir un segundo ticket -- y el
        staff terminaba con dos tarjetas del mismo problema.
        """
        ...

    def cerrar_incidencia(self, incidencia_id: str, nota_cierre: str = "") -> Incidencia | None: ...


# --------------------------------------------------------------------------
# 4. Orquestador  <->  RAG del catalogo
# --------------------------------------------------------------------------

@dataclass
class Fragmento:
    """Un chunk recuperado del indice vectorial, con su fuente para citarla."""

    texto: str
    fuente: str
    score: float = 0.0


# --------------------------------------------------------------------------
# 5. Todo  ->  Observabilidad  (Adrian)
# --------------------------------------------------------------------------

@dataclass
class Traza:
    """Un evento observable del sistema. Adrian decide a donde se envia."""

    evento: str                     # "ruteo", "tool", "respuesta", "error"
    sesion_id: str
    agente: str = ""
    detalle: dict[str, Any] = field(default_factory=dict)
    duracion_ms: float = 0.0
    momento: str = field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))
