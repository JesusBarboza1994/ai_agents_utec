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
    """Mesa disponible para una fecha y hora, con zona, identificador y capacidad."""
    fecha: str                      # "2026-09-12"
    hora: str                       # "20:00"
    zona: str                       # "salon" | "terraza" | "barra"
    mesa_id: str
    capacidad: int


@dataclass
class Reserva:
    """Registro de reserva con contacto, mesa, turno, estado y fecha de creacion.

    La dataclass transporta datos; no valida disponibilidad ni autorizacion."""
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
    ) -> list[OpcionDisponibilidad]:
        """Devuelve mesas libres para fecha, hora y personas, filtradas opcionalmente por zona.

        excluir_reserva_id permite consultar un cambio sin bloquear la mesa propia."""
        ...

    def crear_reserva(
        self, nombre: str, telefono: str, fecha: str, hora: str,
        personas: int, zona: str, notas: str = "",
    ) -> Reserva:
        """Persiste una reserva y devuelve su registro; la falta de mesa produce ValueError.

        La capa de autorizacion debe comprobar el permiso antes de llamar al servicio."""
        ...

    def obtener_reserva(self, reserva_id: str) -> Reserva | None:
        """Devuelve la reserva identificada o None si no existe; no comprueba propiedad aqui."""
        ...

    def buscar_reservas_de(self, telefono: str) -> list[Reserva]:
        """Devuelve los registros del telefono indicado; el llamador debe comprobar autorizacion."""
        ...

    def modificar_reserva(
        self, reserva_id: str, fecha: str | None = None, hora: str | None = None,
        personas: int | None = None,
    ) -> Reserva | None:
        """Actualiza los campos recibidos de una reserva vigente, conservando los omitidos.

        Devuelve None si no existe o no se puede modificar; sin mesa produce ValueError."""
        ...

    def cancelar_reserva(self, reserva_id: str) -> Reserva | None:
        """Marca la reserva como cancelada y devuelve el registro, o None si no existe."""
        ...


# --------------------------------------------------------------------------
# 3. Agentes  <->  Incidencias
# --------------------------------------------------------------------------

@dataclass
class Incidencia:
    """Caso de atencion vinculado a una sesion, con tipo, estado, responsable y plazo.

    Puede referenciar una reserva; la dataclass no crea tickets externos."""
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
    """Contrato de creacion, consulta, anotacion y cierre de incidencias.

    Los backends JSON, Trello y MCP implementan estas firmas; que exista
    el metodo de cierre no significa que este expuesto como herramienta al agente."""
    def crear_incidencia(
        self, sesion_id: str, descripcion: str, tipo: str = "otro",
        reserva_id: str | None = None,
    ) -> Incidencia:
        """Registra un caso de la sesion y devuelve su codigo, estado inicial y plazo."""
        ...

    def listar_incidencias(self, estado: str | None = None) -> list[Incidencia]:
        """Devuelve los casos, filtrados por estado cuando se proporciona ese argumento."""
        ...

    def anotar(self, incidencia_id: str, texto: str) -> bool:
        """
        Agrega un dato a una incidencia ya abierta, sin cambiarle el estado.

        Existe porque un mismo caso puede recibir informacion en varios turnos:
        el cliente reclama, y dos mensajes despues da su telefono. Sin esto, la
        unica forma de guardar ese telefono era abrir un segundo ticket -- y el
        staff terminaba con dos tarjetas del mismo problema.
        """
        ...

    def cerrar_incidencia(self, incidencia_id: str, nota_cierre: str = "") -> Incidencia | None:
        """Cierra el caso con una nota opcional; devuelve el registro o None si no existe."""
        ...


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
