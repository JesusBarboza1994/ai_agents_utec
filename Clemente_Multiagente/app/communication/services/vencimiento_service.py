"""Aviso de resumen vencido: si el cliente no escribio CONFIRMO en 10 minutos, se le avisa que no se hizo nada.

Antes solo se enteraba si escribia CONFIRMO tarde ("Ese resumen vencio..."); si no escribia mas, podia creer que la
reserva estaba hecha. Un hilo revisa cada 30 segundos los resumenes vencidos y avisa por el mismo canal que usa la
decision del personal (aviso_staff_service): WhatsApp por Twilio, o la bandeja del webchat.

Reglas que conserva:
- Cada resumen se avisa una sola vez: autorizacion.retirar_vencidas lo saca de la tabla bajo el candado de confirmar.
- Solo se avisan los que vencieron en la ultima media hora: tras un reinicio no se avisa un resumen de ayer.
- El texto es fijo, sin modelo, pasa por la validacion de salida y queda en el hilo de la conversacion.
- Un fallo del envio se traza y no detiene el hilo.

Escala a cero: en Azure la app se apaga a los pocos minutos sin pedidos, antes de que venza un resumen de 10 minutos,
y un hilo apagado no avisa. Mientras haya un resumen esperando CONFIRMO, el hilo se pide a si mismo GET /api/salud
por la URL publica (mantener_despierta): ese pedido entra por el ingreso de Azure y cuenta como trafico, asi que la
replica sigue encendida hasta avisar. Sin resumenes pendientes no pide nada y la app vuelve a escalar a cero.
"""
import os
import threading
import time
import urllib.request

from ...observabilidad.trazas import registrar
from . import aviso_staff_service

INTERVALO_SEGUNDOS = 30
# Cada cuanto se pide /api/salud mientras hay un resumen pendiente; Azure apaga la replica tras ~5 minutos sin pedidos.
INTERVALO_DESPIERTO_SEGUNDOS = 60
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


def url_de_salud() -> str | None:
    """La URL publica de /api/salud de esta app en Azure Container Apps; None fuera de Azure, donde nada se apaga.

    Azure define CONTAINER_APP_NAME y CONTAINER_APP_ENV_DNS_SUFFIX en cada contenedor: juntos son el dominio de la app."""
    nombre = os.getenv("CONTAINER_APP_NAME", "").strip()
    sufijo = os.getenv("CONTAINER_APP_ENV_DNS_SUFFIX", "").strip()
    if not nombre or not sufijo:
        return None
    return f"https://{nombre}.{sufijo}/api/salud"


def mantener_despierta(url: str | None, pedir=urllib.request.urlopen) -> bool:
    """Si hay un resumen esperando CONFIRMO, pide `url` para que Azure no apague la replica; True si lo pidio.

    Un fallo se traza y devuelve False: el aviso sale igual si la replica sigue encendida por otro pedido."""
    from ...agentes import autorizacion

    if not url or not autorizacion.hay_resumenes_pendientes():
        return False
    try:
        with pedir(url, timeout=10):
            pass
    except Exception as error:
        registrar("error", "vencimientos", detalle={"paso": "mantener_despierta", "error": type(error).__name__})
        return False
    return True


def iniciar(app, intervalo: int = INTERVALO_SEGUNDOS) -> bool:
    """Arranca el hilo que avisa los resumenes vencidos; True si lo arranco, False si ya estaba corriendo."""
    global _iniciado
    with _candado:
        if _iniciado:
            return False
        _iniciado = True
    url = url_de_salud()

    def revisar() -> None:
        """Cada `intervalo` segundos avisa los resumenes vencidos y, si queda alguno pendiente, mantiene la replica."""
        ultimo_pedido = 0.0
        while True:
            time.sleep(intervalo)
            try:
                with app.app_context():
                    avisar_vencidas()
                if time.monotonic() - ultimo_pedido >= INTERVALO_DESPIERTO_SEGUNDOS and mantener_despierta(url):
                    ultimo_pedido = time.monotonic()
            except Exception as error:
                registrar("error", "vencimientos", detalle={"paso": "avisar_resumen_vencido",
                                                            "error": type(error).__name__})

    threading.Thread(target=revisar, name="avisos-de-vencimiento", daemon=True).start()
    return True
