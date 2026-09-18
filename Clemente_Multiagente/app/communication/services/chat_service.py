"""Flujo compartido de seguridad, orquestacion e historial para todos los canales."""
from flask import current_app
from ...contratos import MensajeEntrante, RespuestaClemente
from ...orquestador import responder as responder_orquestador
from ...orquestador.grafo import olvidar_sesion
from .sesiones import obtener_sesion, limpiar_sesion

def handle_incoming_message(entrante: MensajeEntrante):
    """Atiende el turno normalizado y aplica los controles del canal en orden.

    Recupera sesion, bloquea tarjetas/secretos y valida entrada externa antes
    de llamar al orquestador. Un rechazo devuelve respuesta de seguridad.
    Valida salida, sustituye texto rechazado y redacta PII antes de devolver
    la respuesta y guardar el historial. Guardrails AI puede permitir continuar
    cuando esta deshabilitado o no disponible; el bloqueo PII local sigue activo.
    """
    sesion = obtener_sesion(entrante.sesion_id, entrante.canal)
    if entrante.nombre_cliente:
        sesion.nombre_cliente = entrante.nombre_cliente
    if entrante.telefono:
        sesion.telefono = entrante.telefono

    from ...seguridad.guardrails_ai import validar_entrada, validar_salida
    from ...seguridad.pii import pii_prohibida, redactar_pii

    tipo_pii = pii_prohibida(entrante.texto)
    if tipo_pii:
        validacion = None
        respuesta = RespuestaClemente(
            texto="No envíes tarjetas, contraseñas, tokens ni claves por este canal.",
            agente="seguridad", sesion_id=entrante.sesion_id,
            motivo_ruta="PII o secreto bloqueado", datos={"guardrail": "PII"},
        )
    else:
        validacion = validar_entrada(
            entrante.texto, entrante.sesion_id, current_app.config["CLEMENTE"],
        )
    if validacion is not None and not validacion.permitido:
        respuesta = RespuestaClemente(
            texto=("No puedo procesar instrucciones que intenten modificar o evadir "
                   "las reglas de seguridad. Reformula tu consulta sobre el restaurante."),
            agente="seguridad", sesion_id=entrante.sesion_id,
            motivo_ruta="bloqueado por Guardrails AI",
            datos={"guardrail": "DetectJailbreak"},
        )
    elif validacion is not None:
        entrante.texto = validacion.texto
        respuesta = responder_orquestador(entrante, historial=sesion.historial)

    salida = validar_salida(
        respuesta.texto, entrante.sesion_id, current_app.config["CLEMENTE"],
    )
    if not salida.permitido:
        respuesta.texto = "No puedo generar una respuesta apropiada en este momento."
        respuesta.agente = "seguridad"
        respuesta.motivo_ruta = "salida bloqueada por toxicidad"
    else:
        respuesta.texto = redactar_pii(salida.texto)

    # El agente recibe el dato operativo en este turno, pero la memoria de chat
    # no conserva PII cruda para volver a inyectarla en turnos posteriores.
    sesion.agregar("user", redactar_pii(entrante.texto))
    sesion.agregar("assistant", respuesta.texto)
    sesion.ultimo_agente = respuesta.agente
    return respuesta


def reset_session(sesion_id: str) -> None:
    """Elimina historial y estado conversacional propio sin borrar reservas."""
    limpiar_sesion(sesion_id)
    olvidar_sesion(sesion_id)
