"""
Memoria de largo plazo del cliente -- responsables: Christian, Jean.

Es la memoria que el Agent Profile Card v3 declara (nombre, telefono,
preferencias, historial) y que hasta ahora no existia: en la prueba del
2026-09-06 el agente no reconocia al cliente entre conversaciones aunque su
reserva estuviera guardada en disco.

Se distingue de la memoria de corto plazo (`app/comunicacion/sesiones.py`, el
historial del hilo, que vive en RAM y se pierde al reiniciar): esta se guarda en
disco y esta indexada por **telefono**, no por sesion. Por eso sobrevive al
reinicio del servidor, al cambio de pestana del webchat y al cierre del chat.

La ficha que arma `ficha_del_cliente()` se inyecta en cada turno del agente, en
vez de obligar al modelo a llamar tools para redescubrir a quien ya conoce.
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from .contexto import telefono_de

ARCHIVO = Path(__file__).parent / "datos" / "clientes.json"


def _leer() -> dict[str, dict]:
    if not ARCHIVO.exists():
        return {}
    try:
        return json.loads(ARCHIVO.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _escribir(clientes: dict[str, dict]) -> None:
    try:
        ARCHIVO.parent.mkdir(parents=True, exist_ok=True)
        ARCHIVO.write_text(json.dumps(clientes, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError:
        pass    # la memoria es una mejora, nunca un motivo para no responderle al cliente


def _clave(sesion_id: str, telefono: str | None = None) -> str | None:
    """Un cliente se identifica por telefono; si no hay, por la sesion del webchat."""
    return telefono or telefono_de(sesion_id) or (sesion_id if sesion_id != "desconocida" else None)


def recordar(
    sesion_id: str, nombre: str | None = None, telefono: str | None = None, **extras: Any
) -> None:
    """Guarda o actualiza lo que sabemos del cliente. Se llama desde las tools."""
    clave = _clave(sesion_id, telefono)
    if not clave:
        return

    clientes = _leer()
    perfil = clientes.get(clave, {"visto_por_primera_vez": datetime.now().isoformat(timespec="seconds")})
    if nombre:
        perfil["nombre"] = nombre
    if telefono:
        perfil["telefono"] = telefono
    for campo, valor in extras.items():
        if valor:
            perfil[campo] = valor
    perfil["ultima_conversacion"] = datetime.now().isoformat(timespec="seconds")
    perfil["sesiones"] = sorted(set(perfil.get("sesiones", []) + [sesion_id]))[-5:]

    clientes[clave] = perfil
    _escribir(clientes)


def perfil_de(sesion_id: str, telefono: str | None = None) -> dict | None:
    clave = _clave(sesion_id, telefono)
    return _leer().get(clave) if clave else None


def ficha_del_cliente(sesion_id: str) -> str:
    """
    Resumen de una linea que se inyecta en el turno del agente: quien es el
    cliente y que reservas vigentes tiene. Cadena vacia si no lo conocemos.
    """
    # No inferir identidad del prefijo whatsapp ni de un telefono dicho al LLM.
    # Solo se inyectan reservas vinculadas por el servidor a esta sesion.
    from .autorizacion import reservas_propias
    from ..reservas import obtener_servicio
    reservas = [r for r in reservas_propias(sesion_id, obtener_servicio()) if r.estado != "cancelada"]
    if not reservas:
        return ""
    return "; ".join(
        f"{r.id}: {r.nombre}, {r.fecha} a las {r.hora}, {r.personas} personas, zona {r.zona}"
        for r in reservas[-3:]
    )
