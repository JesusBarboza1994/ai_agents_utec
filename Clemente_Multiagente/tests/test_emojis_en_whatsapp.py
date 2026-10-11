"""Los emojis de los textos fijos llegan intactos a WhatsApp: viajan en UTF-8 a Twilio y ningun filtro de salida los toca.

Sin red ni modelo: se captura lo que se enviaria a Twilio y se comprueba, byte a byte, que el cuerpo del mensaje lleva
el mismo texto con su emoji, que la redaccion de datos personales no lo altera y que el aviso del personal lo conserva.
"""
from dataclasses import replace
from urllib.parse import parse_qs

import pytest
import requests

from app import create_app
from app.agentes import autorizacion, base
from app.communication.services import aviso_staff_service as aviso
from app.communication.services import cierre_trello_service as cierre
from app.communication.services import outbound_whatsapp_service as saliente
from app.orquestador import grafo
from app.seguridad.pii import redactar_pii

CODIGO = "G-ABC123"
# Todos los textos fijos con emoji, ya con sus datos de ejemplo.
TEXTOS = {
    "cancelada": grafo.SOLICITUD_CANCELADA_CON_CODIGO.format(codigo=CODIGO),
    "aprobada": grafo.ESCALAMIENTO_RESERVA_APROBADA.format(codigo=CODIGO),
    "pausa": base.SOLICITUD_EN_REVISION.format(codigo=CODIGO),
    "sigue_en_revision": base.AVISO_REVISION_PENDIENTE_CON_CODIGO.format(codigo=CODIGO),
    "cierre": cierre.TEXTO_CIERRE.format(codigo=CODIGO),
    "confirmada": "Listo, tu reserva R-ABC123 quedó confirmada: Ana, 2026-10-22 a las 20:00." + autorizacion.CIERRE_DE_LA_OPERACION["crear"],
    "resumen": "Esto es lo que voy a reservar: Ana. Todavía no está hecho " + autorizacion.EMOJI_DEL_RESUMEN["crear"],
}


@pytest.mark.parametrize("nombre", TEXTOS)
def test_el_cuerpo_viaja_a_twilio_en_utf8_con_su_emoji(monkeypatch, nombre):
    """El cuerpo que sale hacia Twilio, tal como lo codifica `requests`, se lee de vuelta identico, emoji incluido."""
    texto = TEXTOS[nombre]
    capturado = {}

    class RespuestaFalsa:
        """Respuesta de Twilio simulada: el mensaje se acepto y trae su identificador."""

        status_code = 201
        text = ""

        def json(self):
            """Cuerpo JSON de una respuesta exitosa de Twilio."""
            return {"sid": "SM123"}

    def post_falso(url, **kwargs):
        """Anota lo que se enviaria en vez de llamar a Twilio."""
        capturado.update(kwargs)
        return RespuestaFalsa()

    monkeypatch.setattr(saliente.requests, "post", post_falso)

    saliente.send_whatsapp_message("AC123", "secreto", "14155238886", "51999111222", texto)
    preparada = requests.Request("POST", "https://api.twilio.com/x", data=capturado["data"]).prepare()
    cuerpo = preparada.body if isinstance(preparada.body, str) else preparada.body.decode("ascii")

    assert parse_qs(cuerpo)["Body"] == [texto]
    assert "%F0%9F" in cuerpo or "%E2%9C%85" in cuerpo      # el emoji viaja como bytes UTF-8, no como signo de pregunta


@pytest.mark.parametrize("nombre", TEXTOS)
def test_la_redaccion_de_datos_personales_no_toca_el_emoji(nombre):
    """`redactar_pii` (la que corre sobre cada respuesta del chat) deja el texto y su emoji tal cual."""
    texto = TEXTOS[nombre]

    assert redactar_pii(texto, incluir_telefono=False) == texto


def test_el_aviso_del_personal_conserva_el_emoji_hasta_el_envio(monkeypatch, tmp_path):
    """La decision del personal pasa por validacion y redaccion de salida y sale por WhatsApp con su emoji."""
    enviados = []
    monkeypatch.setattr(saliente, "send_whatsapp_message",
                        lambda sid, token, desde, para, cuerpo: enviados.append(cuerpo) or "SM1")
    app = create_app()
    app.config["CLEMENTE"] = replace(
        app.config["CLEMENTE"], database_url="", guardrails_url="",
        twilio_account_sid="AC123", twilio_auth_token="secreto", twilio_whatsapp_from="14155238886",
    )

    with app.app_context():
        resultado = aviso.avisar_decision("whatsapp-51999111222", TEXTOS["aprobada"])

    assert resultado["estado"] == "enviado"
    assert enviados == [TEXTOS["aprobada"]]
