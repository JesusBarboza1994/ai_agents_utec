from types import SimpleNamespace

import pytest


def preparar(monkeypatch, error):
    import app.orquestador
    from tests.eval import deepeval_evaluar as evaluador
    monkeypatch.setattr(app.orquestador, "responder", lambda *a, **k: SimpleNamespace(
        texto="Respuesta ficticia", agente="reservas", escalado=False))
    monkeypatch.setattr(evaluador, "_caso_de_prueba", lambda *a: object())
    class Metrica:
        def measure(self, caso):
            raise error
    metricas = {nombre: Metrica() for nombre in evaluador.METRICAS_POR_AGENTE["reservas"]}
    guiones = [{"id": "ficticio", "turnos": [{"mensaje": "hola", "ruta_esperada": "reservas"}]}]
    return evaluador, guiones, metricas


def test_error_del_juez_no_se_cuenta_como_juicio_valido(monkeypatch):
    evaluador, guiones, metricas = preparar(monkeypatch, ValueError("salida invalida"))
    resultado = evaluador.evaluar(guiones, metricas)
    assert resultado["turnos"] == 1
    assert resultado["metricas"] == {}
    assert all(j["error"] == "ValueError" and not j["aprobo"]
               for j in resultado["detalle"][0]["juicios"].values())


def test_agotamiento_no_se_oculta_como_error_del_juez(monkeypatch):
    from tests.seguridad.presupuesto import PresupuestoAgotado
    evaluador, guiones, metricas = preparar(monkeypatch, PresupuestoAgotado("limite"))
    with pytest.raises(PresupuestoAgotado):
        evaluador.evaluar(guiones, metricas)
