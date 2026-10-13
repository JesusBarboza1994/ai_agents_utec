"""Aviso al cliente cuando el personal aprueba o rechaza una revision humana (HITL).

Hasta ahora el endpoint del personal solo devolvia el texto al panel: el cliente no se
enteraba de la decision hasta volver a escribir. Este servicio la entrega por el canal de
ese cliente: a WhatsApp por el mismo canal de salida que usa el webhook (Twilio REST), y al
webchat dejandola en su bandeja (`bandeja_webchat`), que el chat del navegador recoge solo.

Reglas que conserva:
- El texto pasa por la misma validacion y redaccion de salida que cualquier respuesta
  del chat (`validar_salida`, `redactar_pii`), y lo que se guarda en `messages` va redactado.
- La decision del personal NO depende del aviso: se resuelve primero y se avisa despues.
  Un fallo del envio se devuelve al panel para que el personal lo sepa, nunca se silencia.
- La decision queda SIEMPRE en el hilo de la conversacion (haya salido el aviso o no): si no, el agente no sabe que el
  personal ya decidio y, al siguiente mensaje, vuelve a pedir la excepcion o abre un reclamo nuevo.
"""
from flask import current_app

from ...agentes.contexto import chat_key_de
from ...db.repositories import chats_repository, customers_repository, messages_repository
from ...orquestador.turnos_bloqueados import SALIDA_BLOQUEADA
from ...observabilidad.trazas import registrar
from ...seguridad.guardrails_ai import validar_salida
from ...seguridad.pii import redactar_pii
from . import bandeja_webchat, outbound_whatsapp_service
from .sesiones import obtener_sesion

ENVIADO = "enviado"
NO_ENVIADO = "no_enviado"

MOTIVO_BANDEJA = "no se pudo dejar el aviso en la bandeja del webchat: el cliente lo vera al escribir de nuevo"
MOTIVO_VENTANA = ("fuera de la ventana de 24 horas de WhatsApp: el cliente tiene que escribir de nuevo "
                  "o hace falta una plantilla aprobada")
MOTIVO_SIN_CREDENCIALES = "las credenciales de Twilio no estan configuradas en este servidor"
MOTIVO_RECHAZO = "Twilio rechazo el mensaje"
MOTIVO_ERROR = "error inesperado al enviar el mensaje"
TEXTO_SALIDA_BLOQUEADA = SALIDA_BLOQUEADA


def _motivo_del_fallo(error: Exception) -> str:
    """Motivo corto y legible para el panel, sin telefonos, credenciales ni el cuerpo crudo de Twilio."""
    if isinstance(error, outbound_whatsapp_service.WhatsAppSendError):
        detalle = str(error).lower()
        if "63016" in detalle or "outside the allowed window" in detalle:
            return MOTIVO_VENTANA
        if "not configured" in detalle:
            return MOTIVO_SIN_CREDENCIALES
        return MOTIVO_RECHAZO
    return MOTIVO_ERROR


def _texto_para_el_cliente(sesion_id: str, texto: str, config) -> str:
    """Aplica al aviso la misma salida que el chat: validacion de toxicidad y redaccion de datos personales.

    El telefono se deja visible, como en el resumen de una reserva: el cliente tiene que poder comprobarlo."""
    salida = validar_salida(texto, sesion_id, config)
    if not salida.permitido:
        return TEXTO_SALIDA_BLOQUEADA
    return redactar_pii(salida.texto, incluir_telefono=False)


def _guardar_en_historial(sesion_id: str, chat_key: str, texto: str, config, canal: str) -> None:
    """Guarda la decision como turno del asistente para que el siguiente mensaje del cliente la tenga en su hilo.

    Es lo ultimo que se hace y nunca interrumpe. Con base va a Postgres; sin base, a la sesion en memoria, que es de
    donde el chat lee el hilo en ese caso. Solo entra texto redactado, telefono incluido."""
    redactado = redactar_pii(texto)
    if not config.database_url:
        obtener_sesion(sesion_id, canal).agregar("assistant", redactado)
        return
    try:
        customer_id = customers_repository.get_or_create_customer(chat_key)
        chat_id = chats_repository.get_or_create_chat(chat_key, customer_id, channel=canal)
        messages_repository.append_message(chat_id, "assistant", redactado)
        chats_repository.touch(chat_id)
    except Exception as error:
        registrar("error", sesion_id,
                  detalle={"paso": "guardar_aviso_del_personal", "error": type(error).__name__})


def _avisar_al_webchat(sesion_id: str, cuerpo: str, config) -> dict:
    """Deja la decision en el hilo y en la bandeja del navegador; `no_enviado` si la bandeja no pudo guardarla."""
    _guardar_en_historial(sesion_id, sesion_id, cuerpo, config, "webchat")
    aviso_id = bandeja_webchat.depositar(sesion_id, cuerpo)
    if aviso_id is None:
        registrar("aviso_staff_fallido", sesion_id, detalle={"canal": "webchat", "motivo": MOTIVO_BANDEJA})
        return {"canal": "webchat", "estado": NO_ENVIADO, "motivo": MOTIVO_BANDEJA}
    registrar("aviso_staff_enviado", sesion_id, detalle={"canal": "webchat", "aviso_id": aviso_id})
    return {"canal": "webchat", "estado": ENVIADO, "motivo": "", "aviso_id": aviso_id}


def avisar_decision(sesion_id: str, texto: str) -> dict:
    """Envia por WhatsApp la decision del personal, la deja en el hilo y devuelve el resultado para el panel.

    Devuelve `{"canal", "estado", "motivo"}`; `estado` es `enviado` o `no_enviado` (con el motivo). En el webchat,
    `enviado` significa que quedo en la bandeja del navegador y se agrega `aviso_id`. La decision se guarda en el hilo
    en todos los casos. No lanza: el que resuelve ya decidio y el aviso es un efecto aparte."""
    chat_key = chat_key_de(sesion_id)
    config = current_app.config["CLEMENTE"]
    cuerpo = None
    try:
        cuerpo = _texto_para_el_cliente(sesion_id, texto, config)
        if not chat_key:
            return _avisar_al_webchat(sesion_id, cuerpo, config)
        sid = outbound_whatsapp_service.send_whatsapp_message(
            config.twilio_account_sid, config.twilio_auth_token,
            config.twilio_whatsapp_from, chat_key, cuerpo,
        )
    except Exception as error:
        motivo = _motivo_del_fallo(error)
        registrar("aviso_staff_fallido", sesion_id,
                  detalle={"canal": "whatsapp", "motivo": motivo, "error": type(error).__name__})
        if cuerpo and chat_key:
            _guardar_en_historial(sesion_id, chat_key, cuerpo, config, "whatsapp")
        return {"canal": "whatsapp" if chat_key else "webchat", "estado": NO_ENVIADO, "motivo": motivo}

    registrar("aviso_staff_enviado", sesion_id, detalle={"canal": "whatsapp", "message_sid": sid})
    _guardar_en_historial(sesion_id, chat_key, cuerpo, config, "whatsapp")
    return {"canal": "whatsapp", "estado": ENVIADO, "motivo": ""}
