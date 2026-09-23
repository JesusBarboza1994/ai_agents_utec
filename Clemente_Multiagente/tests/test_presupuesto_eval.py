"""Pruebas del presupuesto persistente y de la intercepcion HTTP con peticiones simuladas."""

import asyncio
import json

import httpx
import pytest

from tests.seguridad.presupuesto import Presupuesto, PresupuestoAgotado


def test_limite_impide_salida_y_persiste_entre_etapas(tmp_path):
    """Verifica que limite impide salida y persiste entre etapas."""
    archivo = tmp_path / "costo.json"
    presupuesto = Presupuesto(archivo, limite=0.001)
    enviado = []
    cliente = httpx.Client(transport=httpx.MockTransport(lambda r: enviado.append(r)))
    with presupuesto.activo(), pytest.raises(PresupuestoAgotado):
        cliente.post("https://api.openai.com/v1/chat/completions", json={"model": "gpt-5.6-terra"})
    assert enviado == []


@pytest.mark.parametrize("asincrono", [False, True])
def test_token_cap_y_uso_reportado(tmp_path, asincrono):
    """Comprueba el limite de 2048 tokens y el cargo por uso reportado en ambos transportes."""
    archivo = tmp_path / "costo.json"
    def respuesta(r):
        """Construye una respuesta HTTP simulada con uso de tokens para comprobar cargos."""
        assert json.loads(r.content)["max_completion_tokens"] == 2048
        assert "api-key-secreta" not in archivo.read_text()
        return httpx.Response(200, json={"usage": {"prompt_tokens": 100, "completion_tokens": 50}})
    presupuesto = Presupuesto(archivo)
    with presupuesto.activo():
        if asincrono:
            async def llamada():
                """Envia una peticion asincrona al transporte simulado bajo el presupuesto activo."""
                async with httpx.AsyncClient(transport=httpx.MockTransport(respuesta)) as cliente:
                    await cliente.post("https://api.openai.com/v1/chat/completions",
                        json={"model": "gpt-5.6-terra"}, headers={"Authorization": "api-key-secreta"})
            asyncio.run(llamada())
        else:
            with httpx.Client(transport=httpx.MockTransport(respuesta)) as cliente:
                cliente.post("https://api.openai.com/v1/chat/completions", json={"model": "gpt-5.6-terra"})
    assert Presupuesto(archivo).datos["cargos"][0]["usd"] == pytest.approx(0.0008)


def test_error_conserva_reserva(tmp_path):
    """Verifica que error conserva reserva."""
    archivo = tmp_path / "costo.json"
    presupuesto = Presupuesto(archivo)
    with presupuesto.activo(), httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(500))) as cliente:
        cliente.post("https://api.anthropic.com/v1/messages", json={"model": "claude-sonnet-5"})
    assert presupuesto.datos["cargos"][0]["estado"] == "reservado"
    assert presupuesto.datos["cargos"][0]["usd"] > 0


def test_intercepta_sdk_instalado_httpx2(tmp_path):
    """Verifica que intercepta sdk instalado httpx2."""
    import httpx2
    from openai import OpenAI
    presupuesto = Presupuesto(tmp_path / "costo.json", limite=0.001)
    cliente = OpenAI(api_key="ficticia", max_retries=0,
                     http_client=httpx2.Client(transport=httpx2.MockTransport(
                         lambda r: pytest.fail("No debe salir una solicitud sin presupuesto"))))
    with presupuesto.activo(), pytest.raises(Exception) as fallo:
        cliente.chat.completions.create(model="gpt-5.6-terra", messages=[{"role": "user", "content": "hola"}])
    # El SDK puede propagar el bloqueo directamente o envolverlo como causa.
    assert isinstance(fallo.value, PresupuestoAgotado) or isinstance(fallo.value.__cause__, PresupuestoAgotado)
