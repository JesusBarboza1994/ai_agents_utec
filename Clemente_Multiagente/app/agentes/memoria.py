"""
Memoria de largo plazo del cliente -- responsables: Christian, Jean.

Es la memoria que el Agent Profile Card v3 declara (nombre, telefono,
preferencias, alergias, historial). Se distingue de la memoria de corto
plazo (`app/communication/services/sesiones.py`, el historial del hilo).

Identidad (acuerdo 2.2 del plan del 18/09): la clave del perfil es la
identidad del SERVIDOR -- el telefono autenticado por el canal cuando la
sesion es `whatsapp-<numero>`, o la propia sesion firmada del webchat --,
nunca un telefono que el cliente escribio en el mensaje. Conocer un numero
no abre el perfil de otra persona; la continuidad entre canales distintos
requiere una verificacion que hoy no existe, y se dice asi.

Donde vive: `clientes.json` local, o la tabla `agentes_perfiles` del Postgres
compartido (ver `almacen.py`). La ficha que arma `ficha_del_cliente()` se
inyecta en cada turno del agente.
"""

from datetime import datetime
from typing import Any

from . import almacen
from .contexto import telefono_de

ARCHIVO = almacen.carpeta_datos() / "clientes.json"
CAMPOS_LISTA = {"alergia": "alergias", "preferencia": "preferencias"}


def _leer_todos() -> dict[str, dict]:
    """Carga los perfiles del JSON local; devuelve un diccionario vacio si falta o no puede leerse."""
    import json

    if not ARCHIVO.exists():
        return {}
    try:
        return json.loads(ARCHIVO.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _escribir_todos(clientes: dict[str, dict]) -> None:
    """Guarda todos los perfiles en JSON UTF-8; ignora OSError para no interrumpir el chat."""
    import json

    try:
        ARCHIVO.parent.mkdir(parents=True, exist_ok=True)
        ARCHIVO.write_text(json.dumps(clientes, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError:
        pass    # la memoria es una mejora, nunca un motivo para no responderle al cliente


def _clave(sesion_id: str, telefono: str | None = None) -> str | None:
    """Identidad del servidor: telefono autenticado del canal o la sesion; nunca un telefono declarado.

    `telefono` se acepta por compatibilidad de firma y se ignora para la clave."""
    if not sesion_id or sesion_id == "desconocida":
        return None
    return telefono_de(sesion_id) or sesion_id


def _leer_perfil(clave: str) -> dict | None:
    """Perfil de la clave en el backend activo, o None."""
    if almacen.es_postgres():
        return almacen.pg_leer_perfil(clave)
    return _leer_todos().get(clave)


def _guardar_perfil(clave: str, perfil: dict) -> None:
    """Crea o reemplaza el perfil de la clave en el backend activo."""
    if almacen.es_postgres():
        almacen.pg_guardar_perfil(clave, perfil)
        return
    clientes = _leer_todos()
    clientes[clave] = perfil
    _escribir_todos(clientes)


def _sin_repetidos(valores: list[str]) -> list[str]:
    """Lista sin duplicados (ignorando mayusculas y espacios), en orden de aparicion."""
    vistos: dict[str, str] = {}
    for valor in valores:
        limpio = str(valor).strip()
        if limpio and limpio.lower() not in vistos:
            vistos[limpio.lower()] = limpio
    return list(vistos.values())


def recordar(
    sesion_id: str, nombre: str | None = None, telefono: str | None = None,
    alergias: list[str] | None = None, preferencias: list[str] | None = None, **extras: Any,
) -> None:
    """Guarda o actualiza lo que sabemos del cliente. Se llama desde las tools.

    El telefono se guarda como dato del perfil, no como su clave. Alergias y
    preferencias se acumulan sin repetir."""
    clave = _clave(sesion_id)
    if not clave:
        return

    perfil = _leer_perfil(clave) or {"visto_por_primera_vez": datetime.now().isoformat(timespec="seconds")}
    if nombre:
        perfil["nombre"] = nombre
    if telefono:
        perfil["telefono"] = telefono
    for campo, valores in (("alergias", alergias), ("preferencias", preferencias)):
        if valores:
            perfil[campo] = _sin_repetidos(list(perfil.get(campo, [])) + list(valores))
    for campo, valor in extras.items():
        if valor:
            perfil[campo] = valor
    perfil["ultima_conversacion"] = datetime.now().isoformat(timespec="seconds")
    perfil["sesiones"] = sorted(set(perfil.get("sesiones", []) + [sesion_id]))[-5:]
    _guardar_perfil(clave, perfil)


def anotar(sesion_id: str, campo: str, valor: str) -> dict | None:
    """Anota un dato declarado (alergia, preferencia o nombre) y devuelve el perfil resultante.

    Devuelve None si la sesion no tiene identidad; un campo desconocido produce ValueError."""
    if campo == "nombre":
        recordar(sesion_id, nombre=valor)
    elif campo in CAMPOS_LISTA:
        recordar(sesion_id, **{CAMPOS_LISTA[campo]: [valor]})
    else:
        raise ValueError(f"Campo de perfil desconocido: {campo!r}")
    return perfil_de(sesion_id)


def perfil_de(sesion_id: str, telefono: str | None = None) -> dict | None:
    """Busca el perfil por la identidad del servidor de sesion_id; devuelve None si falta."""
    clave = _clave(sesion_id, telefono)
    return _leer_perfil(clave) if clave else None


def ficha_del_cliente(sesion_id: str) -> str:
    """Resume reservas vigentes vinculadas por el servidor y datos declarados del perfil.

    Hasta tres reservas no canceladas (via autorizacion y servicio), mas
    alergias y preferencias anotadas. No concede identidad por telefono ni
    lee el perfil como prueba de propiedad. Si el servicio de reservas falla
    por infraestructura, la ficha omite las reservas en vez de tumbar el turno."""
    from ..reservas import obtener_servicio
    from .autorizacion import reservas_propias
    from .servicios import ServicioNoDisponible

    partes = []
    try:
        reservas = [r for r in reservas_propias(sesion_id, obtener_servicio()) if r.estado != "cancelada"]
    except ServicioNoDisponible:
        reservas = []
    if reservas:
        partes.append("; ".join(
            f"{r.id}: {r.nombre}, {r.fecha} a las {r.hora}, {r.personas} personas, zona {r.zona}"
            for r in reservas[-3:]
        ))
    perfil = perfil_de(sesion_id) or {}
    if perfil.get("alergias"):
        partes.append(
            "alergias declaradas por el cliente en conversaciones anteriores, deben confirmarse "
            f"al reservar y al llegar: {', '.join(perfil['alergias'])}"
        )
    if perfil.get("preferencias"):
        partes.append(f"preferencias declaradas: {', '.join(perfil['preferencias'])}")
    return " | ".join(partes)
