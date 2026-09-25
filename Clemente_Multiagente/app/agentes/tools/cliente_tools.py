"""
Tool para guardar datos del cliente que el mismo da en pleno chat (nombre,
apellido, DNI, telefono de contacto, una mascota...) para que comunicacion los
lea despues via `customers_repository.get_customer` y arme el `customer` que le
pasa a Clemente en el proximo turno.

Lo que esta tool NUNCA debe aceptar ni reenviar: numero de tarjeta,
contrasena o token. Eso ya se bloquea antes de llegar aqui
(`app/seguridad/pii.py::pii_prohibida`, PATRONES_BLOQUEO["tarjeta"]) -- si
algun dia se necesita cobrar por este canal, es una decision del equipo
completo (pasarela de pago con link, nunca tarjeta cruda por chat), no algo
que se resuelve agregandole un parametro a esta tool.

Donde escribe: nombre y apellido en sus columnas; todo lo demas en el jsonb
`data`. NUNCA en la columna `phone`: esa es el numero con el que el canal
autentico al cliente, no el que alguien dijo en una conversacion
(`customers_repository.get_customer`). El telefono que da el cliente va en
`data["telefono_contacto"]`.
"""

import re
import unicodedata

from langchain.tools import ToolRuntime, tool

from . import con_traza, limpiar_texto
from ..contexto import chat_key_de
from ...db.repositories import customers_repository
from ...reservas.validaciones import TELEFONO_RE
from ...seguridad.pii import pii_prohibida

# Datos sueltos que la tool acepta guardar en `data`. Lista cerrada a proposito: lo
# que se guarda vuelve a leerlo el modelo en la ficha de cada turno, y una clave
# libre dejaria a un cliente escribir ahi lo que quiera para siempre. Para
# aceptar otro dato se agrega aqui y se nombra en el prompt de reservas.
DATOS_PERMITIDOS = ("mascota", "cumpleanos", "preferencia_zona")

_LARGO_MAXIMO_DATO = 80


def _clave_de_dato(dato: str) -> str:
    """Minusculas, sin tildes y con guion bajo en vez de espacios: "Cumpleaños" -> "cumpleanos"."""
    sin_tildes = "".join(c for c in unicodedata.normalize("NFD", dato or "") if unicodedata.category(c) != "Mn")
    return re.sub(r"[^a-z0-9]+", "_", sin_tildes.lower()).strip("_")


def _telefono_limpio(texto: str) -> str:
    """El telefono sin espacios, guiones ni parentesis; cadena vacia si no tiene forma de telefono."""
    limpio = re.sub(r"[\s().-]", "", limpiar_texto(texto, 30))
    return limpio if TELEFONO_RE.match(limpio) else ""


@tool
@con_traza
def actualizar_datos_cliente(
    runtime: ToolRuntime, nombre: str = "", apellido: str = "", dni: str = "",
    telefono_contacto: str = "", dato: str = "", valor: str = "",
) -> str:
    """Guarda o actualiza datos que el cliente dio el mismo en este chat.

    Usar cuando el cliente dice su nombre, apellido, DNI o un telefono de contacto, o
    cuenta algo suyo que sirve para atenderlo mejor (una mascota, su cumpleanos). Se
    llama sin anunciarlo. Se puede pasar mas de un dato en la misma llamada.

    NUNCA pedir ni aceptar numero de tarjeta, contrasena o token: ese tipo de
    dato se bloquea antes de llegar a esta tool y no debe pedirse por este canal.

    Args:
        nombre: nombre de pila que el cliente dio, vacio si no lo dio.
        apellido: apellido que el cliente dio, vacio si no lo dio.
        dni: documento de identidad que el cliente dio, vacio si no lo dio.
        telefono_contacto: telefono para contactarlo por una reserva, si lo dio. No es el
            numero con el que el canal lo identifica: ese el sistema ya lo tiene.
        dato: un dato suelto del cliente; uno de: mascota, cumpleanos, preferencia_zona.
        valor: el valor de ese dato tal como lo dijo el cliente ("perro", "12 de marzo").
            Si el cliente lo dijo a medias ("tengo una mascota"), pregunta y guarda despues.
    """
    chat_key = runtime.context.chat_key or chat_key_de(runtime.context.sesion_id)
    if not chat_key:
        # Webchat sin telefono todavia, o sesion "desconocida": no hay fila de
        # `customers` a la que escribir. No es un error del cliente ni del
        # modelo, asi que no se propaga como excepcion.
        return "No hay un chat identificado todavia para guardar ese dato."

    avisos: list[str] = []
    data: dict[str, str] = {}
    if dni:
        data["dni"] = limpiar_texto(dni, 20)
    if telefono_contacto:
        telefono = _telefono_limpio(telefono_contacto)
        if telefono:
            data["telefono_contacto"] = telefono
        else:
            avisos.append("El telefono no parece valido (de 7 a 15 digitos): pidele que lo repita.")
    if dato or valor:
        clave, contenido = _clave_de_dato(dato), limpiar_texto(valor, _LARGO_MAXIMO_DATO)
        if clave not in DATOS_PERMITIDOS:
            avisos.append(f"Ese dato no se guarda. Solo se guardan: {', '.join(DATOS_PERMITIDOS)}.")
        elif not contenido:
            avisos.append(f"Falta el valor de {clave}: preguntaselo al cliente y guardalo cuando lo diga.")
        elif pii_prohibida(f"{clave}: {contenido}"):
            avisos.append("Ese contenido no se puede guardar por este canal.")
        else:
            data[clave] = contenido

    nombre, apellido = limpiar_texto(nombre, 60), limpiar_texto(apellido, 60)
    if not (nombre or apellido or data):
        return " ".join(avisos) or "No hay ningun dato para guardar."

    customers_repository.get_or_create_customer(chat_key)
    customers_repository.update_customer(
        chat_key,
        first_name=nombre or None,
        last_name=apellido or None,
        data=data or None,
    )
    return " ".join(["Datos del cliente actualizados.", *avisos])
