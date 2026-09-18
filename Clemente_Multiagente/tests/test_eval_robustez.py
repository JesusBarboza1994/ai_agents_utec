"""Pruebas del tratamiento de errores del juez y agotamiento de presupuesto, con dobles locales."""

from types import SimpleNamespace

import pytest


def preparar(monkeypatch, error):
    """Sustituye el asistente y la metrica para simular un error del juez en la evaluacion."""
    import app.orquestador
    from tests.eval import deepeval_evaluar as evaluador
    monkeypatch.setattr(app.orquestador, "responder", lambda *a, **k: SimpleNamespace(
        texto="Respuesta ficticia", agente="reservas", escalado=False))
    monkeypatch.setattr(evaluador, "_caso_de_prueba", lambda *a: object())
    class Metrica:
        """Metrica simulada que lanza el error configurado para comprobar su tratamiento."""
        def measure(self, caso):
            """Lanza el error configurado en lugar de producir un juicio valido."""
            raise error
    metricas = {nombre: Metrica() for nombre in evaluador.METRICAS_POR_AGENTE["reservas"]}
    guiones = [{"id": "ficticio", "turnos": [{"mensaje": "hola", "ruta_esperada": "reservas"}]}]
    return evaluador, guiones, metricas


def test_error_del_juez_no_se_cuenta_como_juicio_valido(monkeypatch):
    """Verifica que error del juez no se cuenta como juicio valido."""
    evaluador, guiones, metricas = preparar(monkeypatch, ValueError("salida invalida"))
    resultado = evaluador.evaluar(guiones, metricas)
    assert resultado["turnos"] == 1
    assert resultado["metricas"] == {}
    assert all(j["error"] == "ValueError" and not j["aprobo"]
               for j in resultado["detalle"][0]["juicios"].values())


def test_agotamiento_no_se_oculta_como_error_del_juez(monkeypatch):
    """Verifica que agotamiento no se oculta como error del juez."""
    from tests.seguridad.presupuesto import PresupuestoAgotado
    evaluador, guiones, metricas = preparar(monkeypatch, PresupuestoAgotado("limite"))
    with pytest.raises(PresupuestoAgotado):
        evaluador.evaluar(guiones, metricas)
