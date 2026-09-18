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

Dos escenarios, cada uno con N peticiones concurrentes (10-20 por defecto):

  A. Anti-doble-booking: N clientes DISTINTOS piden la MISMA mesa/turno
     (personas=8, que en el catalogo demo solo cubre la mesa S01). Se
     espera que gane exactamente 1 y el resto reciba 400 "sin mesas" --
     nunca 2 reservas en la misma mesa/turno, nunca un 500.

  B. Idempotencia: N peticiones IDENTICAS (mismo telefono+fecha+hora+
     personas) en paralelo. Se espera que TODAS devuelvan el mismo id de
     reserva -- un reintento de webhook no debe duplicar nada.
"""

from __future__ import annotations

import statistics
import sys
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta

import requests

FECHA = str(date.today() + timedelta(days=5))


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


def main() -> None:
    args = sys.argv[1:]
    base_url = next((a for a in args if not a.startswith("--")), "http://localhost:5000").rstrip("/")
    n = 15
    if "--n" in args:
        n = int(args[args.index("--n") + 1])

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
    ]
    print("\n" + ("TODO OK" if all(resultados) else "HAY FALLOS -- revisar arriba"))
    raise SystemExit(0 if all(resultados) else 1)


if __name__ == "__main__":
    main()
