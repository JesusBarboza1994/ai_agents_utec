"""Flujo compartido de todos los canales: identidad, persistencia, seguridad y orquestacion.

Unico camino hacia el orquestador y el LLM. Los adaptadores de canal -- el
webchat en `chat_controller`, WhatsApp en `whatsapp_service` -- solo traducen
su propio payload y llaman aqui: la fila de `customers`, la de `chats`, la
ventana de `messages` y los controles de seguridad son identicos para los dos.

El hilo vive en Postgres: el historial que ve el agente se lee de `messages`
y la memoria del proceso no participa. `sesiones.py` queda como respaldo de un
solo caso: cuando no hay `database_url` configurada (demo local, pruebas) no
hay de donde leer, y el hilo vuelve a vivir en RAM con el alcance de siempre.

Si la base esta configurada pero falla, el turno se responde igual y el fallo
queda trazado: un problema de almacenamiento no deja al cliente sin respuesta.

Lo que NO vive aqui: el estado del orquestador -- revisiones HITL, ultimo
agente, propuestas de reserva pendientes de confirmar -- sigue en memoria de
`orquestador/grafo.py`.
"""
from dataclasses import dataclass

from flask import current_app

from ...contratos import PREFIJO_IMAGEN, MensajeEntrante, RespuestaClemente
from ...db.repositories import chats_repository, customers_repository, messages_repository
from ...observabilidad.trazas import registrar
from ...orquestador import responder as responder_orquestador
from ...orquestador.grafo import olvidar_sesion
from ...seguridad.pii import pii_prohibida, redactar_pii
from .sesiones import MAXIMO_TURNOS, obtener_sesion, limpiar_sesion


@dataclass
class IdentidadCanal:
    """Lo que el canal sabe del remitente y que `MensajeEntrante` no transporta.

    `contratos.py` se toca solo en reunion de equipo, asi que los datos propios
    del transporte viajan aparte: la clave del hilo en el canal, el numero
    propio del negocio y el id que el proveedor le dio al mensaje. El webchat
    no tiene ninguno -- su hilo se identifica con el `sesion_id` de la cookie
    firmada, que es tambien su `chat_key`.
    """
    chat_key: str | None = None
    channel_number: str | None = None
    provider_message_id: str | None = None


def _configuracion():
    """Configuracion de Clemente del contexto Flask activo."""
    return current_app.config["CLEMENTE"]


def _abrir_chat(entrante: MensajeEntrante, identidad: IdentidadCanal, chat_key: str) -> str | None:
    """Resuelve cliente y chat en Postgres y devuelve el chat_id.

    Devuelve None -- y el turno sigue en memoria -- cuando no hay base
    configurada o cuando la base falla; en el segundo caso deja traza.
    """
    if not _configuracion().database_url:
        return None
    try:
        customer_id = customers_repository.get_or_create_customer(
            chat_key, first_name=entrante.nombre_cliente, phone=entrante.telefono,
        )
        return chats_repository.get_or_create_chat(
            chat_key, customer_id,
            channel=entrante.canal, channel_number=identidad.channel_number,
        )
    except Exception as error:
        registrar("error", entrante.sesion_id,
                  detalle={"paso": "abrir_chat", "error": type(error).__name__})
        return None


def _para_el_agente(rol: str, tipo: str, contenido: str) -> dict:
    """Una fila de `messages` como la recibe el agente.

    El texto se redacta; la URL de una imagen no: la genero Cloudinary, no la
    escribio el cliente, y redactarla la dejaria inservible."""
    if tipo == messages_repository.TYPE_IMAGE_URL:
        return {"role": rol, "content": f"{PREFIJO_IMAGEN} {contenido}"}
    return {"role": rol, "content": redactar_pii(contenido)}


def _historial(chat_id: str, sesion_id: str) -> list[dict]:
    """Ventana de contexto del hilo, leida de `messages` y ya redactada.

    Son los turnos ANTERIORES: se lee antes de guardar el mensaje que se esta
    atendiendo, porque ese ya viaja en `MensajeEntrante.texto` y el orquestador
    lo pone en el prompt por su cuenta. Leerla despues lo duplicaria.
    """
    try:
        recientes = messages_repository.get_recent_messages(
            chat_id, session_days=_configuracion().chat_session_days,
        )
    except Exception as error:
        registrar("error", sesion_id,
                  detalle={"paso": "leer_historial", "error": type(error).__name__})
        return []
    return [
        _para_el_agente(fila["role"], fila.get("type") or messages_repository.TYPE_TEXT, fila["content"])
        for fila in recientes
    ][-MAXIMO_TURNOS:]


def _ficha_del_cliente(chat_key: str, sesion_id: str) -> dict:
    """Lo guardado del cliente, con el jsonb `data` ya desestructurado al mismo nivel.

    Vacia cuando no hay base, cuando el cliente todavia no existe o cuando la
    consulta falla: conocer al cliente mejora el turno, nunca lo impide.
    """
    if not _configuracion().database_url:
        return {}
    try:
        return customers_repository.get_customer(chat_key) or {}
    except Exception as error:
        registrar("error", sesion_id,
                  detalle={"paso": "leer_cliente", "error": type(error).__name__})
        return {}


def _guardar(chat_id: str, sesion_id: str, rol: str, texto: str,
             *, provider_message_id: str | None = None,
             tipo: str = messages_repository.TYPE_TEXT) -> None:
    """Persiste un turno ya redactado; un fallo se traza y no interrumpe la conversacion."""
    try:
        messages_repository.append_message(
            chat_id, rol, texto, provider_message_id=provider_message_id, message_type=tipo,
        )
        chats_repository.touch(chat_id)
    except Exception as error:
        registrar("error", sesion_id,
                  detalle={"paso": "guardar_mensaje", "rol": rol, "error": type(error).__name__})


def handle_incoming_message(
    entrante: MensajeEntrante, identidad: IdentidadCanal | None = None,
) -> RespuestaClemente:
    """Atiende el turno normalizado de cualquier canal y aplica los controles en orden.

    Abre cliente y chat, lee de `messages` la ventana de turnos anteriores y
    persiste el mensaje del cliente ANTES de llamar al orquestador: en WhatsApp
    el ack a Twilio ya salio y no habra reintento, asi que un fallo del modelo
    no puede hacer desaparecer lo que dijo el cliente. El historial sale
    siempre de la base, no de la memoria del proceso.

    Despues bloquea tarjetas/secretos y valida la entrada antes de llamar al
    orquestador; un rechazo devuelve respuesta de seguridad. Valida la salida,
    sustituye texto rechazado y redacta PII antes de devolver la respuesta y
    guardar el turno. Guardrails AI puede permitir continuar cuando esta
    deshabilitado o no disponible; el bloqueo PII local sigue activo.

    Solo entra a Postgres texto redactado: el dato operativo crudo llega al
    agente en este turno y no vuelve a inyectarse en los siguientes.

    Cada imagen del turno (`entrante.imagenes`, URLs de Cloudinary) se guarda
    como su propia fila `image_url`. Las de ESTE turno viajan en
    `entrante.imagenes` y el agente las recibe como imagen; las de turnos
    pasados vuelven desde la base como texto con su URL (`_para_el_agente`).
    """
    identidad = identidad or IdentidadCanal()
    chat_key = identidad.chat_key or entrante.sesion_id
    chat_id = _abrir_chat(entrante, identidad, chat_key)
    imagenes_del_turno = [
        _para_el_agente("user", messages_repository.TYPE_IMAGE_URL, url) for url in entrante.imagenes
    ]

    sesion = None
    if chat_id:
        # Con base, el hilo es lo guardado: si quedaba una sesion en RAM de
        # antes de configurar Postgres, se descarta en vez de mezclarse.
        limpiar_sesion(entrante.sesion_id)
        historial = _historial(chat_id, entrante.sesion_id)
        for url in entrante.imagenes:
            _guardar(chat_id, entrante.sesion_id, "user", url,
                     provider_message_id=identidad.provider_message_id,
                     tipo=messages_repository.TYPE_IMAGE_URL)
        # Una imagen sin texto no deja ademas una fila de texto vacia.
        if entrante.texto or not entrante.imagenes:
            _guardar(chat_id, entrante.sesion_id, "user", redactar_pii(entrante.texto),
                     provider_message_id=identidad.provider_message_id)
    else:
        sesion = obtener_sesion(entrante.sesion_id, entrante.canal)
        if entrante.nombre_cliente:
            sesion.nombre_cliente = entrante.nombre_cliente
        if entrante.telefono:
            sesion.telefono = entrante.telefono
        historial = sesion.historial

    from ...seguridad.guardrails_ai import ResultadoEntrada, validar_entrada, validar_salida

    tipo_pii = pii_prohibida(entrante.texto)
    if tipo_pii:
        validacion = None
        respuesta = RespuestaClemente(
            texto="No envíes tarjetas, contraseñas, tokens ni claves por este canal.",
            agente="seguridad", sesion_id=entrante.sesion_id,
            motivo_ruta="PII o secreto bloqueado", datos={"guardrail": "PII"},
        )
    elif not entrante.texto and entrante.imagenes:
        # Solo imagen: no hay texto que validar, y el servicio de Guardrails
        # rechaza un texto vacio (400), que con falla cerrada bloquearia el turno.
        validacion = ResultadoEntrada(True, "", "sin texto: solo imagen", False)
    else:
        validacion = validar_entrada(
            entrante.texto, entrante.sesion_id, _configuracion(),
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
        cliente = _ficha_del_cliente(chat_key, entrante.sesion_id)
        respuesta = responder_orquestador(
            entrante, historial=historial, cliente=cliente, chat_key=chat_key,
        )

    salida = validar_salida(
        respuesta.texto, entrante.sesion_id, _configuracion(),
    )
    if not salida.permitido:
        respuesta.texto = "No puedo generar una respuesta apropiada en este momento."
        respuesta.agente = "seguridad"
        respuesta.motivo_ruta = "salida bloqueada por toxicidad"
    else:
        # El cliente ve su propio telefono: el resumen de la reserva tiene que dejarle comprobar que quedo bien
        # anotado. El resto de los datos personales (correo, DNI, IP) siguen tapados.
        respuesta.texto = redactar_pii(salida.texto, incluir_telefono=False)

    if chat_id:
        # Lo que se guarda sigue redactado, telefono incluido: solo entra a Postgres texto redactado.
        _guardar(chat_id, entrante.sesion_id, "assistant", redactar_pii(respuesta.texto))
    else:
        # El agente recibe el dato operativo en este turno, pero la memoria de
        # chat no conserva PII cruda para reinyectarla en turnos posteriores.
        for imagen in imagenes_del_turno:
            sesion.agregar(imagen["role"], imagen["content"])
        sesion.agregar("user", redactar_pii(entrante.texto))
        sesion.agregar("assistant", redactar_pii(respuesta.texto))
        sesion.ultimo_agente = respuesta.agente
    return respuesta


def reset_session(sesion_id: str) -> None:
    """Elimina historial y estado conversacional propio sin borrar reservas.

    Limpia la memoria del proceso y las propuestas pendientes del grafo. Los
    mensajes ya guardados en Postgres no se borran: son el registro del hilo.
    """
    limpiar_sesion(sesion_id)
    olvidar_sesion(sesion_id)
