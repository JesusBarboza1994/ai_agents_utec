"""
Tool para guardar datos del cliente que el mismo da en pleno chat (nombre,
apellido, DNI...) para que comunicacion los lea despues via
`customers_repository.get_customer` y arme el `customer` que le pasa a
Clemente en el proximo turno.

Lo que esta tool NUNCA debe aceptar ni reenviar: numero de tarjeta,
contrasena o token. Eso ya se bloquea antes de llegar aqui
(`app/seguridad/pii.py::pii_prohibida`, PATRONES_BLOQUEO["tarjeta"]) -- si
algun dia se necesita cobrar por este canal, es una decision del equipo
completo (pasarela de pago con link, nunca tarjeta cruda por chat), no algo
que se resuelve agregandole un parametro a esta tool.
"""

from langchain.tools import ToolRuntime, tool

from . import con_traza
from ..contexto import chat_key_de
from ...db.repositories import customers_repository


@tool
@con_traza
def actualizar_datos_cliente(
    runtime: ToolRuntime, nombre: str = "", apellido: str = "", dni: str = "",
) -> str:
    """Guarda o actualiza datos que el cliente dio el mismo en este chat.

    Usar cuando el cliente dice su nombre, apellido o DNI (por ejemplo,
    al iniciar una conversacion o al identificarse para una reserva).

    NUNCA pedir ni aceptar numero de tarjeta, contrasena o token: ese tipo de
    dato se bloquea antes de llegar a esta tool y no debe pedirse por este canal.

    Args:
        nombre: nombre de pila que el cliente dio, vacio si no lo dio.
        apellido: apellido que el cliente dio, vacio si no lo dio.
        dni: documento de identidad que el cliente dio, vacio si no lo dio.
    """
    chat_key = runtime.context.chat_key or chat_key_de(runtime.context.sesion_id)
    if not chat_key:
        # Webchat sin telefono todavia, o sesion "desconocida": no hay fila de
        # `customers` a la que escribir. No es un error del cliente ni del
        # modelo, asi que no se propaga como excepcion.
        return "No hay un chat identificado todavia para guardar ese dato."

    customers_repository.get_or_create_customer(chat_key)
    customers_repository.update_customer(
        chat_key,
        first_name=nombre or None,
        last_name=apellido or None,
        data={"dni": dni} if dni else None,
    )
    return "Datos del cliente actualizados."
