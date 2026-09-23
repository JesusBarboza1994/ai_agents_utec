"""Regresiones del montaje: datos aislados y errores no contados como aprobados."""
import asyncio
import json
from types import SimpleNamespace

import pytest

from tests.seguridad.entorno import entorno_aislado
from tests.seguridad import red_team_reservas as redteam


def test_aislamiento_incluso_tras_error(tmp_path, monkeypatch):
    """Verifica que aislamiento incluso tras error."""
    from app.reservas import servicio_json as reservas
    from app.agentes import autorizacion
    from app.incidencias import backend_activo
    original = reservas.ARCHIVO_RESERVAS
    original.write_text("[]", encoding="utf-8")
    monkeypatch.setenv("CLEMENTE_BACKEND_INCIDENCIAS", "trello")
    aislado = tmp_path / "corrida"
    with pytest.raises(RuntimeError):
        with entorno_aislado(aislado):
            assert backend_activo() == "json"
            servicio = reservas.ServicioReservasJSON()
            semilla = json.loads((aislado / "semilla.json").read_text())
            reserva = servicio.obtener_reserva(semilla["reserva_id"])
            assert reserva.nombre == "CLIENTE SINTETICO CANARIO"
            assert not autorizacion.es_propietario("atacante", reserva.id)
            assert original.read_text() == "[]"
            raise RuntimeError("fallo simulado")
    assert reservas.ARCHIVO_RESERVAS == original
    assert backend_activo() == "trello"
    assert original.read_text() == "[]"


def test_error_del_objetivo_deja_evidencia_y_no_respuesta(tmp_path, monkeypatch):
    """Verifica que error del objetivo deja evidencia y no respuesta."""
    import app.orquestador
    from app.observabilidad.trazas import registrar
    def fallo(mensaje, historial):
        """Simula un fallo del objetivo o motor para comprobar conservacion de evidencias y errores."""
        registrar("error", mensaje.sesion_id, detalle={"error": "fallo simulado"})
        return SimpleNamespace(texto="No puedo atenderte")
    monkeypatch.setattr(app.orquestador, "responder", fallo)
    diario = tmp_path / "turnos.jsonl"
    callback = redteam.construir_callback("sistema", diario)
    with pytest.raises(RuntimeError, match="no se evalua"):
        asyncio.run(callback("hola"))
    eventos = [json.loads(linea) for linea in diario.read_text().splitlines()]
    assert [e["estado"] for e in eventos] == ["iniciado", "error"]
    assert eventos[0]["id"] == eventos[1]["id"]


def test_rechaza_historial_en_vez_de_ignorar_turnos():
    """Verifica que rechaza historial en vez de ignorar turnos."""
    callback = redteam.construir_callback("sistema")
    with pytest.raises(ValueError, match="un turno"):
        asyncio.run(callback("hola", ["turno previo"]))


def test_fallo_de_deepteam_conserva_casos_parciales(tmp_path, monkeypatch):
    """Verifica que fallo de deepteam conserva casos parciales."""
    import deepteam.red_teamer
    import tests.eval.juez
    monkeypatch.setattr(tests.eval.juez, "construir_juez", lambda modelo: object())
    class Motor:
        """Doble DeepTeam que conserva un ataque parcial y falla como si se agotara el saldo."""
        risk_assessment = None
        attack_simulator = SimpleNamespace(test_cases=[SimpleNamespace(model_dump=lambda **kw: {"input": "ataque sintetico"})])
        def __init__(self, **kw):
            """Comprueba que el motor simulado se configure sin concurrencia adicional."""
            assert kw["max_concurrent"] == 1
        def red_team(self, **kw):
            """Verifica opciones del montaje y lanza el agotamiento simulado tras conservar un caso."""
            assert kw["run_all_attacks"] is True
            assert kw["ignore_errors"] is False
            assert kw["_upload_to_confident"] is False
            assert kw["_print_assessment"] is False
            raise RuntimeError("saldo agotado simulado")
    monkeypatch.setattr(deepteam.red_teamer, "RedTeamer", Motor)
    with pytest.raises(RuntimeError, match="saldo agotado"):
        redteam.ejecutar(None, [], [], tmp_path)
    assert json.loads((tmp_path / "casos_simulados.json").read_text())[0]["input"] == "ataque sintetico"


def test_main_guarda_estado_error_antes_de_propagar(tmp_path, monkeypatch):
    """Verifica que main guarda estado error antes de propagar."""
    monkeypatch.setattr(redteam, "CARPETA_RESULTADOS", tmp_path)
    monkeypatch.setattr(redteam, "RAIZ", tmp_path)
    monkeypatch.setattr("sys.argv", ["redteam", "--humo", "--si"])
    def fallo(*args):
        """Simula un fallo del objetivo o motor para comprobar conservacion de evidencias y errores."""
        raise RuntimeError("fallo simulado")
    monkeypatch.setattr(redteam, "ejecutar", fallo)
    with pytest.raises(RuntimeError, match="fallo simulado"):
        redteam.main()
    manifiesto = json.loads(next(tmp_path.glob("*/corrida.json")).read_text())
    assert manifiesto["estado"] == "error"
    assert manifiesto["tipo_error"] == "RuntimeError"
    assert manifiesto["fin"]
