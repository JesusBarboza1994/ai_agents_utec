"""Aviso de resumen vencido: si el cliente no escribio CONFIRMO en 10 minutos, se le avisa que no se hizo nada.

Antes solo se enteraba si escribia CONFIRMO tarde ("Ese resumen vencio..."); si no escribia mas, podia creer que la
reserva estaba hecha. Un hilo revisa cada 30 segundos los resumenes vencidos y avisa por el mismo canal que usa la
decision del personal (aviso_staff_service): WhatsApp por Twilio, o la bandeja del webchat.

Reglas que conserva:
- Cada resumen se avisa una sola vez: autorizacion.retirar_vencidas lo saca de la tabla bajo el candado de confirmar.
- Solo se avisan los que vencieron en la ultima media hora: tras un reinicio no se avisa un resumen de ayer.
- El texto es fijo, sin modelo, pasa por la validacion de salida y queda en el hilo de la conversacion.
- Un fallo del envio se traza y no detiene el hilo.
"""
import threading
import time

from ...observabilidad.trazas import registrar
from . import aviso_staff_service

INTERVALO_SEGUNDOS = 30
TEXTO_VENCIDO = {
    "crear": ("Pasaron 10 minutos sin tu CONFIRMO, así que el resumen de tu reserva venció y no se reservó nada. "
              "Si todavía quieres la mesa, escríbeme y te preparo uno nuevo 📅"),
    "modificar": ("Pasaron 10 minutos sin tu CONFIRMO, así que el cambio venció y tu reserva sigue como estaba. "
                  "Si todavía quieres cambiarla, escríbeme y te preparo uno nuevo 📅"),
    "cancelar": ("Pasaron 10 minutos sin tu CONFIRMO, así que la cancelación venció y tu reserva sigue en pie. "
                 "Si todavía quieres cancelarla, escríbeme y te preparo uno nuevo 📅"),
}
_iniciado = False
_candado = threading.Lock()


def avisar_vencidas() -> int:
    """Avisa a cada cliente cuyo resumen acaba de vencer y devuelve cuantos avisos salieron.

    Necesita un contexto de Flask, como el aviso del personal."""
    from ...agentes import autorizacion          # al usarlo: los servicios de comunicacion no cargan los agentes al importar

    enviados = 0
    for sesion, accion in autorizacion.retirar_vencidas():
        resultado = aviso_staff_service.avisar_decision(sesion, TEXTO_VENCIDO.get(accion, TEXTO_VENCIDO["crear"]))
        enviados += resultado["estado"] == aviso_staff_service.ENVIADO
        registrar("resumen_vencido_avisado", sesion, agente="reservas",
                  detalle={"accion": accion, "estado": resultado["estado"], "motivo": resultado["motivo"]})
    return enviados


def iniciar(app, intervalo: int = INTERVALO_SEGUNDOS) -> bool:
    """Arranca el hilo que avisa los resumenes vencidos; True si lo arranco, False si ya estaba corriendo."""
    global _iniciado
    with _candado:
        if _iniciado:
            return False
        _iniciado = True

    def revisar() -> None:
        """Cada `intervalo` segundos avisa los resumenes vencidos; un error se traza y el hilo sigue."""
        while True:
            time.sleep(intervalo)
            try:
                with app.app_context():
                    avisar_vencidas()
            except Exception as error:
                registrar("error", "vencimientos", detalle={"paso": "avisar_resumen_vencido",
                                                            "error": type(error).__name__})

    threading.Thread(target=revisar, name="avisos-de-vencimiento", daemon=True).start()
    return True
