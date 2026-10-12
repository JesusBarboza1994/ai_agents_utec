"""Un numero largo es tarjeta solo si pasa Luhn y no es el id de WhatsApp de un cliente; sin red.

Caso real (2026-10-11): el BSUID whatsapp-PE.1028522870210512 salia en las trazas como PE.[REDACTED_TARJETA], y el
mismo patron bloqueaba cualquier mensaje con 13 a 19 digitos seguidos ("No envies tarjetas...").
"""
import pytest

from app.seguridad import pii

TARJETAS_DE_PRUEBA = ["4111 1111 1111 1111", "5555-5555-5555-4444", "4242424242424242", "378282246310005"]


@pytest.mark.parametrize("tarjeta", TARJETAS_DE_PRUEBA)
def test_una_tarjeta_real_se_sigue_bloqueando_y_tapando(tarjeta):
    """Visa, Mastercard y Amex con espacios, guiones o juntas: bloqueadas a la entrada y tapadas en las trazas."""
    texto = f"mi tarjeta es {tarjeta}"
    assert pii.pii_prohibida(texto) == "tarjeta"
    assert tarjeta not in pii.redactar_pii(texto) and "[REDACTED_TARJETA]" in pii.redactar_pii(texto)


@pytest.mark.parametrize("bsuid", ["PE.1028522870210512", "PE.2636615980132813", "PE.1611355547394174"])
def test_el_id_de_whatsapp_de_un_cliente_no_es_una_tarjeta(bsuid):
    """Los BSUID de los logs del 2026-10-11 se ven completos en las trazas."""
    sesion = f"whatsapp-{bsuid}"
    assert pii.redactar_pii({"sesion": sesion}) == {"sesion": sesion}
    assert pii.pii_prohibida(sesion) is None


def test_un_bsuid_que_pasa_luhn_por_casualidad_tampoco_es_tarjeta():
    """Uno de cada diez numeros pasa Luhn por azar: el prefijo de pais basta para reconocer el id."""
    assert pii._luhn_valido("4111111111111111")
    assert pii.redactar_pii("whatsapp-PE.4111111111111111") == "whatsapp-PE.4111111111111111"


def test_un_numero_largo_que_no_es_tarjeta_no_bloquea_el_mensaje():
    """Un codigo de pedido o de operacion de 16 digitos llega al agente."""
    codigo = "1028522870210512"
    assert not pii._luhn_valido(codigo)
    assert pii.pii_prohibida(f"mi codigo de pedido es {codigo}") is None
    assert codigo in pii.redactar_pii(f"mi codigo de pedido es {codigo}")


def test_los_secretos_se_siguen_bloqueando():
    """El cambio es solo de tarjetas: claves y tokens siguen bloqueados."""
    assert pii.pii_prohibida("mi api_key: sk-abcdefghijklmnopqrstuvwx") == "secreto"
