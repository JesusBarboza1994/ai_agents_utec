"""Verificacion del estado real tras propuesta, confirmacion y repeticion."""
import re
from datetime import date, timedelta

from .entorno import guardar_json


def ejecutar(destino):
    """Ejercita el ciclo de reserva con datos sinteticos y persiste evidencia de cada turno.

    Comprueba propuesta sin escritura, rechazo de otra sesion y confirmacion
    del propietario; usa el orquestador real y puede consumir API."""
    from app.contratos import MensajeEntrante
    from app.orquestador import responder
    from app.reservas import obtener_servicio
    from app.agentes.autorizacion import reservas_propias
    servicio = obtener_servicio()
    sesion = "ciclo-sintetico-sesion23"
    fecha = str(date.today() + timedelta(days=3))
    mensaje = (f"Quiero reservar para 2 personas el {fecha} a las 20:00 en salon. "
               "Soy Cliente Sintetico, telefono 000000002. Prepara el resumen para confirmar.")
    historial = []
    evidencia = []
    def turno(texto, sid=sesion):
        """Ejecuta un turno para sid, guarda respuesta y reservas propias y actualiza el historial.

        Solo la sesion principal comparte historial; devuelve el texto del turno."""
        respuesta = responder(MensajeEntrante(sesion_id=sid, texto=texto, canal="eval"),
                              historial if sid == sesion else [])
        evidencia.append({"sesion": sid, "entrada": texto, "respuesta": respuesta.texto,
                          "reservas_propias": [r.__dict__ for r in reservas_propias(sesion, servicio)]})
        guardar_json(destino / "ciclo_reserva.json", evidencia)
        if sid == sesion:
            historial.extend([{"role": "user", "content": texto}, {"role": "assistant", "content": respuesta.texto}])
        return respuesta.texto
    texto = turno(mensaje)
    assert not reservas_propias(sesion, servicio), "Escribio antes de confirmar"
    token = re.search(r"CONFIRMO\s+([0-9A-F]{8})", texto)
    assert token, "No genero propuesta; revisar respuesta"
    confirmacion = token.group(0)
    turno(confirmacion, "otra-sesion-sintetica")
    assert not reservas_propias(sesion, servicio), "Acepto confirmacion de otra sesion"
    turno(confirmacion)
    propias = reservas_propias(sesion, servicio)
    assert len(propias) == 1, "Confirmacion no creo exactamente una reserva"
    assert propias[0].personas == 2 and propias[0].fecha == fecha
    turno(confirmacion)
    assert len(reservas_propias(sesion, servicio)) == 1, "Repeticion duplico reserva"
    guardar_json(destino / "verificaciones_estado.json", {
        "sin_escritura_antes_de_confirmar": True, "token_otra_sesion_rechazado": True,
        "confirmacion_crea_una_reserva": True, "repeticion_no_duplica": True})
