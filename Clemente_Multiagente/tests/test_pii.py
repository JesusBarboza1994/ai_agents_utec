"""Pruebas de bloqueo y redaccion local de PII en texto, estructuras y trazas."""

from app.seguridad.pii import pii_prohibida, redactar_pii


def test_bloquea_tarjetas_y_secretos():
    """Verifica que bloquea tarjetas y secretos."""
    assert pii_prohibida("mi tarjeta es 4111 1111 1111 1111") == "tarjeta"
    assert pii_prohibida("api_key=secreto-super-largo-12345") == "secreto"


def test_redacta_pii_de_trazas_y_respuestas():
    """Verifica que redacta pii de trazas y respuestas."""
    texto = "DNI 12345678, correo ana@example.com y celular +51 987654321"
    limpio = redactar_pii(texto)
    assert "12345678" not in limpio
    assert "ana@example.com" not in limpio
    assert "987654321" not in limpio


def test_telefono_se_permite_para_operar_la_reserva():
    """Verifica que telefono se permite para operar la reserva."""
    assert pii_prohibida("Reserva para Ana, celular 987654321") is None


def test_registrar_nunca_guarda_pii_cruda():
    """Verifica que registrar nunca guarda pii cruda."""
    from app.observabilidad import trazas

    trazas.limpiar_trazas() if hasattr(trazas, "limpiar_trazas") else trazas._trazas.clear()
    registrada = trazas.registrar(
        "prueba_pii", "sesion", detalle={"texto": "ana@example.com 987654321"},
    )
    assert "ana@example.com" not in registrada.detalle["texto"]
    assert "987654321" not in registrada.detalle["texto"]
