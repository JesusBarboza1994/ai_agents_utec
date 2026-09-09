import asyncio
import json

import httpx
import pytest

from tests.seguridad.presupuesto import Presupuesto, PresupuestoAgotado


def test_limite_impide_salida_y_persiste_entre_etapas(tmp_path):
    archivo = tmp_path / "costo.json"
    presupuesto = Presupuesto(archivo, limite=0.001)
    enviado = []
    cliente = httpx.Client(transport=httpx.MockTransport(lambda r: enviado.append(r)))
    with presupuesto.activo(), pytest.raises(PresupuestoAgotado):
        cliente.post("https://api.openai.com/v1/chat/completions", json={"model": "gpt-5.6-terra"})
    assert enviado == []


@pytest.mark.parametrize("asincrono", [False, True])
def test_token_cap_y_uso_reportado(tmp_path, asincrono):
    archivo = tmp_path / "costo.json"
    def respuesta(r):
        assert json.loads(r.content)["max_completion_tokens"] == 2048
        assert "api-key-secreta" not in archivo.read_text()
        return httpx.Response(200, json={"usage": {"prompt_tokens": 100, "completion_tokens": 50}})
    presupuesto = Presupuesto(archivo)
    with presupuesto.activo():
        if asincrono:
            async def llamada():
                async with httpx.AsyncClient(transport=httpx.MockTransport(respuesta)) as cliente:
                    await cliente.post("https://api.openai.com/v1/chat/completions",
                        json={"model": "gpt-5.6-terra"}, headers={"Authorization": "api-key-secreta"})
            asyncio.run(llamada())
        else:
            with httpx.Client(transport=httpx.MockTransport(respuesta)) as cliente:
                cliente.post("https://api.openai.com/v1/chat/completions", json={"model": "gpt-5.6-terra"})
    assert Presupuesto(archivo).datos["cargos"][0]["usd"] == pytest.approx(0.0008)


def test_error_conserva_reserva(tmp_path):
    archivo = tmp_path / "costo.json"
    presupuesto = Presupuesto(archivo)
    with presupuesto.activo(), httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(500))) as cliente:
        cliente.post("https://api.anthropic.com/v1/messages", json={"model": "claude-sonnet-5"})
    assert presupuesto.datos["cargos"][0]["estado"] == "reservado"
    assert presupuesto.datos["cargos"][0]["usd"] > 0


def test_intercepta_sdk_instalado_httpx2(tmp_path):
    import httpx2
    from openai import OpenAI
    presupuesto = Presupuesto(tmp_path / "costo.json", limite=0.001)
    cliente = OpenAI(api_key="ficticia", max_retries=0,
                     http_client=httpx2.Client(transport=httpx2.MockTransport(
                         lambda r: pytest.fail("No debe salir una solicitud sin presupuesto"))))
    with presupuesto.activo(), pytest.raises(Exception) as fallo:
        cliente.chat.completions.create(model="gpt-5.6-terra", messages=[{"role": "user", "content": "hola"}])
    assert isinstance(fallo.value.__cause__, PresupuestoAgotado)
