"""Cuando un resumen vence sin CONFIRMO, el cliente recibe un aviso; sin red ni modelo.

Antes solo se enteraba si escribia CONFIRMO tarde. Aqui se prueba que cada resumen vencido se avisa una sola vez,
que no se avisa uno vigente ni uno de hace horas, que un CONFIRMO tardio sigue diciendo que vencio y que un "si"
despues del aviso sigue la conversacion en vez de confirmar.
"""
import time
from dataclasses import replace

import pytest

from app import create_app
from app.agentes import autorizacion
from app.communication.services import aviso_staff_service, bandeja_webchat, vencimiento_service


@pytest.fixture(autouse=True)
def sin_marcas(monkeypatch):
    """Cada prueba empieza sin conversaciones avisadas, y el hilo no se da por arrancado."""
    autorizacion._vencidas_avisadas.clear()
    monkeypatch.setattr(vencimiento_service, "_iniciado", False)
    yield
    autorizacion._vencidas_avisadas.clear()


def _resumen(sesion, accion="crear", vencio_hace=60):
    """Deja un resumen esperando CONFIRMO que vencio hace `vencio_hace` segundos (negativo: todavia vale)."""
    with autorizacion._db() as db:
        db.execute("INSERT OR REPLACE INTO propuestas VALUES (?, ?, ?, ?, ?)",
                   (sesion, "ABCDEF12", accion, "{}", time.time() - vencio_hace))


def _pendientes():
    """Sesiones con un resumen todavia guardado."""
    with autorizacion._db() as db:
        return {fila[0] for fila in db.execute("SELECT sesion FROM propuestas")}


def test_un_resumen_que_acaba_de_vencer_se_retira_una_sola_vez():
    """La primera revision lo saca para avisar; la siguiente ya no lo encuentra."""
    _resumen("web-a")
    assert autorizacion.retirar_vencidas() == [("web-a", "crear")]
    assert autorizacion.retirar_vencidas() == []
    assert "web-a" not in _pendientes()


def test_un_resumen_vigente_no_se_toca():
    """Faltan cinco minutos: sigue esperando el CONFIRMO."""
    _resumen("web-b", vencio_hace=-300)
    assert autorizacion.retirar_vencidas() == [] and "web-b" in _pendientes()


def test_uno_que_vencio_hace_horas_no_se_avisa():
    """Tras un reinicio no se avisa un resumen viejo; un CONFIRMO tardio sigue recibiendo que vencio."""
    _resumen("web-c", vencio_hace=3 * 3600)
    assert autorizacion.retirar_vencidas() == []
    assert autorizacion.confirmar("web-c", "CONFIRMO", None) == (autorizacion.RESUMEN_VENCIDO, {})


def test_un_confirmo_tardio_despues_del_aviso_dice_que_vencio():
    """Ya se le aviso: "no encuentro un resumen" lo confundiria, asi que se le repite que vencio."""
    _resumen("web-d")
    autorizacion.retirar_vencidas()
    assert autorizacion.confirmar("web-d", "CONFIRMO", None) == (autorizacion.RESUMEN_VENCIDO, {})


def test_un_si_despues_del_aviso_sigue_la_conversacion():
    """El aviso ofrece preparar otro resumen: un "si" es la respuesta a eso, no una confirmacion."""
    _resumen("web-e")
    autorizacion.retirar_vencidas()
    assert autorizacion.confirmar("web-e", "si", None) is None


def test_despues_de_otro_mensaje_vuelve_el_texto_de_siempre():
    """Si el cliente escribio otra cosa, un CONFIRMO suelto ya no se refiere al resumen vencido."""
    _resumen("web-f")
    autorizacion.retirar_vencidas()
    autorizacion.descartar("web-f")
    assert autorizacion.confirmar("web-f", "CONFIRMO", None)[0] == autorizacion.SIN_RESUMEN_PENDIENTE


def test_cada_resumen_vencido_recibe_el_aviso_de_su_operacion(monkeypatch):
    """Una reserva, un cambio y una cancelacion vencidos reciben cada uno su texto, por su conversacion."""
    avisos = []
    monkeypatch.setattr(aviso_staff_service, "avisar_decision",
                        lambda sesion, texto: avisos.append((sesion, texto)) or {"estado": "enviado", "motivo": ""})
    _resumen("whatsapp-51999111222", "crear")
    _resumen("whatsapp-51999111333", "modificar")
    _resumen("web-g", "cancelar")

    assert vencimiento_service.avisar_vencidas() == 3
    assert sorted(avisos) == sorted([
        ("whatsapp-51999111222", vencimiento_service.TEXTO_VENCIDO["crear"]),
        ("whatsapp-51999111333", vencimiento_service.TEXTO_VENCIDO["modificar"]),
        ("web-g", vencimiento_service.TEXTO_VENCIDO["cancelar"]),
    ])
    assert vencimiento_service.avisar_vencidas() == 0


def test_un_aviso_que_no_sale_no_se_cuenta_ni_se_repite(monkeypatch):
    """Si Twilio lo rechaza, queda trazado y no se reintenta: el cliente igual recibe RESUMEN_VENCIDO al confirmar."""
    monkeypatch.setattr(aviso_staff_service, "avisar_decision",
                        lambda sesion, texto: {"estado": "no_enviado", "motivo": "fuera de la ventana"})
    _resumen("whatsapp-51999111444")
    assert vencimiento_service.avisar_vencidas() == 0
    assert vencimiento_service.avisar_vencidas() == 0
    assert autorizacion.confirmar("whatsapp-51999111444", "CONFIRMO", None)[0] == autorizacion.RESUMEN_VENCIDO


def test_en_el_webchat_el_aviso_queda_en_la_bandeja_del_navegador(monkeypatch, tmp_path):
    """Con el aviso real: sin Twilio, el webchat lo recoge de su bandeja."""
    monkeypatch.setattr(bandeja_webchat, "ARCHIVO", tmp_path / "bandeja_webchat.json")
    app = create_app()
    app.config["CLEMENTE"] = replace(app.config["CLEMENTE"], database_url="", guardrails_url="")
    _resumen("web-h")
    with app.app_context():
        assert vencimiento_service.avisar_vencidas() == 1
    assert [m["texto"] for m in bandeja_webchat.recoger("web-h")] == [vencimiento_service.TEXTO_VENCIDO["crear"]]


def test_el_hilo_se_arranca_una_sola_vez(monkeypatch):
    """Llamar dos veces a iniciar no arranca dos hilos que avisarian dos veces."""
    arrancados = []

    class HiloFalso:
        """Anota el hilo en vez de arrancarlo: uno real seguiria corriendo durante el resto de la suite."""
        def __init__(self, **kwargs):
            """Guarda los argumentos del hilo."""
            self.kwargs = kwargs

        def start(self):
            """Anota el arranque."""
            arrancados.append(self.kwargs["name"])

    monkeypatch.setattr(vencimiento_service.threading, "Thread", HiloFalso)
    assert vencimiento_service.iniciar(object()) is True
    assert vencimiento_service.iniciar(object()) is False
    assert arrancados == ["avisos-de-vencimiento"]
