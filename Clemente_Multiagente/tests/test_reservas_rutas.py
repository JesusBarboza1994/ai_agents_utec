"""
Pruebas del blueprint de depuracion de reservas (app/reservas/rutas.py).

Solo se registra con CLEMENTE_DEBUG_ROUTES=1 -- ver app/__init__.py. Corren
contra el backend json (el autouse `aislar_estado` de conftest.py ya lo
aisla en un tmp_path por prueba), sin agente ni LLM de por medio.
"""

from datetime import date, timedelta

import pytest

from app import create_app

FECHA = str(date.today() + timedelta(days=3))


@pytest.fixture
def cliente(monkeypatch):
    monkeypatch.setenv("CLEMENTE_DEBUG_ROUTES", "1")
    app = create_app()
    app.config["TESTING"] = True
    return app.test_client()


@pytest.fixture
def cliente_sin_flag(monkeypatch):
    monkeypatch.delenv("CLEMENTE_DEBUG_ROUTES", raising=False)
    app = create_app()
    app.config["TESTING"] = True
    return app.test_client()


def test_rutas_de_depuracion_no_existen_sin_el_flag(cliente_sin_flag):
    respuesta = cliente_sin_flag.post("/api/reservas", json={})
    assert respuesta.status_code == 404


def test_crear_reserva_valida_devuelve_201(cliente):
    respuesta = cliente.post("/api/reservas", json={
        "nombre": "Ana", "telefono": "999111222", "fecha": FECHA,
        "hora": "20:00", "personas": 2, "zona": "salon",
    })
    assert respuesta.status_code == 201
    datos = respuesta.get_json()
    assert datos["nombre"] == "Ana"
    assert datos["id"].startswith("R-")


def test_crear_reserva_con_hora_invalida_devuelve_400_con_mensaje(cliente):
    respuesta = cliente.post("/api/reservas", json={
        "nombre": "Ana", "telefono": "999111222", "fecha": FECHA,
        "hora": "17:30", "personas": 2, "zona": "salon",
    })
    assert respuesta.status_code == 400
    assert "turno" in respuesta.get_json()["error"]


def test_crear_reserva_dos_veces_es_idempotente_via_http(cliente):
    body = {"nombre": "Ana", "telefono": "999111222", "fecha": FECHA,
            "hora": "20:00", "personas": 2, "zona": "salon"}
    r1 = cliente.post("/api/reservas", json=body).get_json()
    r2 = cliente.post("/api/reservas", json=body).get_json()
    assert r1["id"] == r2["id"]


def test_consultar_disponibilidad(cliente):
    respuesta = cliente.get(f"/api/reservas/disponibilidad?fecha={FECHA}&hora=20:00&personas=4")
    assert respuesta.status_code == 200
    opciones = respuesta.get_json()
    assert opciones
    assert all(o["capacidad"] >= 4 for o in opciones)


def test_detalle_de_reserva_inexistente_devuelve_404(cliente):
    assert cliente.get("/api/reservas/R-NOEXISTE").status_code == 404


def test_crear_y_cancelar_reserva(cliente):
    creada = cliente.post("/api/reservas", json={
        "nombre": "Ana", "telefono": "999111222", "fecha": FECHA,
        "hora": "21:00", "personas": 2, "zona": "salon",
    }).get_json()
    cancelada = cliente.post(f"/api/reservas/{creada['id']}/cancelar")
    assert cancelada.status_code == 200
    assert cancelada.get_json()["estado"] == "cancelada"
