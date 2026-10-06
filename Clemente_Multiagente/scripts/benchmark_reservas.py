"""
Prueba de carga reproducible del Gestor de Reservas, SIN pasar por el LLM.

Pega directo a las rutas de depuracion (app/reservas/rutas.py), asi que
mide la latencia real de la escritura (Postgres + el `SELECT ... FOR
UPDATE`) sin la latencia del modelo encima.

Requiere:
  - El servidor corriendo con CLEMENTE_DEBUG_ROUTES=1
    (`python run.py`, con esa variable en el .env o en el entorno).
  - Idealmente CLEMENTE_BACKEND_RESERVAS=postgres -- contra json el lock es
    a nivel de proceso, no demuestra nada sobre concurrencia real de DB.

Uso:
    python scripts/benchmark_reservas.py [URL_BASE] [--n N]

La URL por defecto es 127.0.0.1 y NO localhost: en Windows, `requests`
resuelve localhost por IPv6 (::1) primero y espera ~2 s antes de caer a IPv4,
lo que infla TODAS las latencias medidas (ver docs/VALIDACION_...).

Tres escenarios (A y B con N peticiones concurrentes, 15 por defecto; C secuencial):

  A. Anti-doble-booking: N clientes DISTINTOS piden la MISMA mesa/turno
     (personas=8, que en el catalogo demo solo cubre la mesa S01). Se
     espera que gane exactamente 1 y el resto reciba 400 "sin mesas" --
     nunca 2 reservas en la misma mesa/turno, nunca un 500.

  B. Idempotencia: N peticiones IDENTICAS (mismo telefono+fecha+hora+
     personas) en paralelo. Se espera que TODAS devuelvan el mismo id de
     reserva -- un reintento de webhook no debe duplicar nada.

  C. Escritura individual: N reservas creadas UNA POR UNA, sin concurrencia
     ni candado disputado. Es la latencia que veria un cliente real de
     WhatsApp, y sirve de linea base para leer A y B.
"""

from __future__ import annotations

import random
import statistics
import sys
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta

import requests

# Fecha al azar por corrida (dentro del limite de 30 dias de validaciones.py):
# las reservas de corridas anteriores quedan en la tabla, y repetir siempre la
# misma fecha/turno agotaria las mesas y falsearia los resultados.
FECHA = str(date.today() + timedelta(days=random.randint(5, 25)))


def _post(url: str, payload: dict) -> tuple[int, dict, float]:
    inicio = time.perf_counter()
    respuesta = requests.post(url, json=payload, timeout=30)
    duracion = time.perf_counter() - inicio
    try:
        cuerpo = respuesta.json()
    except ValueError:
        cuerpo = {}
    return respuesta.status_code, cuerpo, duracion


def _reportar_latencias(nombre: str, duraciones: list[float]) -> None:
    print(f"  latencia {nombre}: min={min(duraciones)*1000:.0f}ms "
          f"p50={statistics.median(duraciones)*1000:.0f}ms "
          f"max={max(duraciones)*1000:.0f}ms")


def escenario_anti_doble_booking(base_url: str, n: int) -> bool:
    print(f"\n=== A. Anti-doble-booking: {n} clientes distintos, misma mesa/turno ===")
    url = f"{base_url}/api/reservas"
    hora = "13:00"  # turno separado del escenario B para no interferir
    payloads = [
        {"nombre": f"Cliente {i}", "telefono": f"9{i:08d}", "fecha": FECHA,
         "hora": hora, "personas": 8, "zona": "salon"}  # 8 = solo cabe en S01
        for i in range(n)
    ]
    with ThreadPoolExecutor(max_workers=n) as pool:
        resultados = list(pool.map(lambda p: _post(url, p), payloads))

    exitosas = [r for r in resultados if r[0] == 201]
    rechazadas = [r for r in resultados if r[0] == 400]
    otros = [r for r in resultados if r[0] not in (201, 400)]
    _reportar_latencias("creacion", [r[2] for r in resultados])
    print(f"  201 creadas: {len(exitosas)} | 400 sin mesa: {len(rechazadas)} | otros: {len(otros)}")

    ok = len(exitosas) == 1 and not otros
    print("  RESULTADO:", "OK -- exactamente 1 gano la mesa" if ok else "FALLO -- revisar el lock")
    return ok


def escenario_idempotencia(base_url: str, n: int) -> bool:
    print(f"\n=== B. Idempotencia: {n} peticiones identicas en paralelo ===")
    url = f"{base_url}/api/reservas"
    telefono = f"9{uuid.uuid4().int % 10**8:08d}"
    payload = {"nombre": "Cliente Reintento", "telefono": telefono, "fecha": FECHA,
               "hora": "14:00", "personas": 2, "zona": "salon"}
    with ThreadPoolExecutor(max_workers=n) as pool:
        resultados = list(pool.map(lambda _: _post(url, payload), range(n)))

    exitosas = [r for r in resultados if r[0] == 201]
    ids = {r[1].get("id") for r in exitosas}
    _reportar_latencias("creacion", [r[2] for r in resultados])
    print(f"  201 devueltos: {len(exitosas)} | ids distintos: {ids}")

    ok = len(exitosas) == n and len(ids) == 1
    print("  RESULTADO:", "OK -- una sola reserva real" if ok else "FALLO -- se duplico o alguna peticion no confirmo")
    return ok


def escenario_escritura_individual(base_url: str, n: int) -> bool:
    print(f"\n=== C. Escritura individual: {n} reservas una por una, sin concurrencia ===")
    url = f"{base_url}/api/reservas"
    duraciones = []
    creadas = 0
    ids = []
    for i in range(n):
        payload = {"nombre": f"[PRUEBA] Individual {i}", "telefono": f"8{uuid.uuid4().int % 10**8:08d}",
                   "fecha": FECHA, "hora": "19:00", "personas": 2, "zona": "salon"}
        estado, cuerpo, duracion = _post(url, payload)
        duraciones.append(duracion)
        if estado == 201:
            creadas += 1
            ids.append(cuerpo["id"])
    _reportar_latencias("creacion", duraciones)
    print(f"  201 creadas: {creadas} de {n}")
    for reserva_id in ids:  # cancelar (UPDATE, no DELETE) para liberar mesas en corridas repetidas
        requests.post(f"{url}/{reserva_id}/cancelar", timeout=30)
    ok = creadas == n
    print("  RESULTADO:", "OK" if ok else "FALLO -- ninguna reserva se creo (sin mesas libres o error)")
    return ok


def _parsear_args(args: list[str]) -> tuple[str, int]:
    base_url = "http://127.0.0.1:5000"
    n = 15
    i = 0
    while i < len(args):
        if args[i] == "--n":
            n = int(args[i + 1])
            i += 2
        else:
            if not args[i].startswith("--"):
                base_url = args[i]
            i += 1
    return base_url.rstrip("/"), n


def main() -> None:
    base_url, n = _parsear_args(sys.argv[1:])

    try:
        salud = requests.get(f"{base_url}/api/reservas/disponibilidad", params={
            "fecha": FECHA, "hora": "12:00", "personas": 1,
        }, timeout=5)
    except requests.ConnectionError:
        raise SystemExit(
            f"No se pudo conectar a {base_url}. Levanta el servidor con "
            "CLEMENTE_DEBUG_ROUTES=1 (python run.py) antes de correr esto."
        )
    if salud.status_code == 404:
        raise SystemExit(
            "Las rutas de depuracion no estan registradas. "
            "Arranca el servidor con CLEMENTE_DEBUG_ROUTES=1 en el entorno."
        )

    resultados = [
        escenario_anti_doble_booking(base_url, n),
        escenario_idempotencia(base_url, n),
        escenario_escritura_individual(base_url, min(n, 5)),
    ]
    print("\n" + ("TODO OK" if all(resultados) else "HAY FALLOS -- revisar arriba"))
    raise SystemExit(0 if all(resultados) else 1)


if __name__ == "__main__":
    main()
