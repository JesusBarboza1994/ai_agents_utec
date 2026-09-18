"""
Tool de perfil del cliente (`update_customer` del plan, seccion 3.2).

Una alergia dicha en el chat y no capturada era la observacion: el agente
la leia, respondia "perfecto" y no quedaba en ningun lado. Esta tool la
anota en el perfil auxiliar ligado a la identidad del canal (no a un
telefono declarado) para que la ficha del siguiente turno la traiga.

Lo que NO promete: que la cocina ya lo sabe. El texto que devuelve obliga a
repetir la alergia al reservar (campo `notas`) y al llegar; una anotacion en
un perfil no es un control de seguridad alimentaria.
"""

from langchain.tools import ToolRuntime, tool

from . import con_traza

from .. import memoria

CAMPOS = ("alergia", "preferencia", "nombre")
LARGO_MAXIMO = 120


@tool
@con_traza
def anotar_dato_cliente(campo: str, valor: str, runtime: ToolRuntime) -> str:
    """Guarda un dato que el cliente declaro sobre si mismo para no volver a pedirselo:
    una alergia, una preferencia (zona, ocasion) o su nombre. Usar apenas lo mencione.
    No sustituye ponerlo en `notas` de la reserva ni avisar en el local.

    Args:
        campo: "alergia", "preferencia" o "nombre".
        valor: el dato tal como lo dijo el cliente, corto (por ejemplo "mani", "terraza").
    """
    campo = (campo or "").strip().lower()
    valor = (valor or "").strip()
    if campo not in CAMPOS:
        return f"Campo no admitido: usa {', '.join(CAMPOS)}."
    if not valor or len(valor) > LARGO_MAXIMO:
        return "Indica un valor corto y concreto para anotar."

    perfil = memoria.anotar(runtime.context.sesion_id, campo, valor)
    if perfil is None:
        return "No se pudo anotar: la conversación no tiene una identidad reconocible."

    runtime.context.datos["perfil_actualizado"] = {"campo": campo, "valor": valor}
    if campo == "alergia":
        return (
            f"Anotado: alergia a {valor} en el perfil de esta conversación. "
            "Al preparar una reserva inclúyela en `notas` y dile al cliente que la repita "
            "al mozo al llegar: la cocina la confirma en persona, no por este chat."
        )
    return f"Anotado: {campo} = {valor} en el perfil de esta conversación."
