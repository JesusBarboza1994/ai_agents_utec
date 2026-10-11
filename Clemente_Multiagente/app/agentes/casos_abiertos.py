"""Una operacion a la vez: un pedido al equipo que nadie atendio detiene las reservas nuevas de esa conversacion.

Un cliente puede tener una sola cosa abierta con el restaurante. Mientras el equipo no atienda su pedido de hablar con una
persona (o su grupo grande ya aprobado), no se abre otra reserva ni otra solicitud de grupo; para seguir, el cliente
escribe CANCELAR SOLICITUD y el pedido se retira. Esto evita que una conversacion apile reservas, y que un pedido al
equipo quede enterrado debajo de otros.

Un caso deja de contar cuando el equipo lo atiende (la tarjeta pasa de "Pendiente" a "En atencion" o a "Resuelto"),
cuando el cliente lo retira, o a las 24 horas. Los reclamos (platos frios, esperas) no cuentan: solo los pedidos que el
orquestador o el agente de reservas escalan al equipo, que son los que empiezan con "[escalado desde".

Ver tambien: los grupos de mas de 8 que esperan la decision del personal ya detienen el hilo entero (ver `base.ejecutar`).
"""
from ..incidencias import abiertas_de

# Marcas que el orquestador deja en la tarjeta. El estado del pedido sale de cual quedo escrita al final.
MARCA_PEDIDO_RETIRADO = "[el cliente retiró su pedido]"
MARCA_DATO_NUEVO = "[dato nuevo del cliente]"
INICIO_DEL_CASO = "[escalado desde"
VENTANA_HORAS = 24

BLOQUEO_POR_CASO_ABIERTO = (
    "Todavía tienes el pedido {codigo} esperando al equipo del restaurante, y mientras no lo atiendan no puedo abrir "
    "otra reserva. Si ya no lo necesitas, escribe CANCELAR SOLICITUD y te ayudo con la reserva."
)


def caso_de_atencion_abierto(sesion_id: str) -> str | None:
    """Codigo del pedido al equipo que esta conversacion dejo abierto y nadie atendio, o None.

    Cuenta un caso "[escalado desde ...]" de las ultimas 24 horas que sigue en "Pendiente" y que el cliente no retiro.
    Si despues de retirarlo el cliente vuelve a pedir algo, el pedido vuelve a contar. Si el registro de casos no
    responde, no se bloquea nada: es preferible dejar reservar a trabar a un cliente por una falla ajena."""
    for caso in abiertas_de(sesion_id, horas=VENTANA_HORAS):
        descripcion = caso.descripcion or ""
        if not descripcion.startswith(INICIO_DEL_CASO):
            continue
        if descripcion.rfind(MARCA_PEDIDO_RETIRADO) > descripcion.rfind(MARCA_DATO_NUEVO):
            continue
        return caso.id
    return None
