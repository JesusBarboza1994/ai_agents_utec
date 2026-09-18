"""
Almacen compartido del estado de los agentes -- responsables: Christian, Jean.

Observacion A3 / paso 7 del plan del 18/09: permisos, propuestas, perfiles,
cola HITL y continuidad vivian en archivos del proceso (SQLite y JSON en
`app/agentes/datos/`), que en Azure se pierden en cada redeploy y no se
comparten entre replicas. Este modulo pone esos datos en el MISMO Postgres y
el MISMO pool que ya usan customers/chats/messages (Jesus) y mesas/reservas
(Marc): `app/db/connection.py`, con las tablas `agentes_*` de la migracion
0003 para no interferir con las suyas.

Como se elige el backend (CLEMENTE_BACKEND_AGENTES):
    auto      (default) sigue a CLEMENTE_BACKEND_RESERVAS: postgres -> postgres,
              json -> local. Si las reservas viven en Postgres, el estado que
              las autoriza tambien.
    postgres  fuerza Postgres.
    local     fuerza archivos y memoria del proceso (pruebas, demo sin base).

Restriccion heredada del pool: Postgres exige un contexto Flask activo
(`with app.app_context()`), igual que el servicio de reservas de Marc. Los
canales ya lo tienen (request context del webchat, `app_context()` del
worker de WhatsApp) y LangChain propaga los contextvars a los hilos de las
tools, asi que en el recorrido normal no hay nada que hacer. Un corredor de
evaluacion que llame `orquestador.responder` sin app debe usar `local` o
abrir el contexto.

Que NO hace: no mueve el checkpoint LangGraph del agente de reservas (sigue
en SQLite bajo `CLEMENTE_DATOS_DIR`) ni sustituye las tablas de Marc.
"""

import json
import os
import secrets
import time
from collections import defaultdict, deque
from contextlib import contextmanager
from pathlib import Path
from typing import Any

BACKENDS = ("auto", "postgres", "local")


def carpeta_datos() -> Path:
    """Carpeta de los archivos locales del estado (SQLite/JSON/checkpoints).

    `CLEMENTE_DATOS_DIR` permite apuntarla a un volumen persistente en el
    despliegue; por defecto es `app/agentes/datos/`, como siempre."""
    configurada = os.getenv("CLEMENTE_DATOS_DIR", "").strip()
    return Path(configurada) if configurada else Path(__file__).resolve().parent / "datos"


def backend_activo() -> str:
    """Devuelve "postgres" o "local" segun CLEMENTE_BACKEND_AGENTES y, en auto, el backend de reservas."""
    pedido = os.getenv("CLEMENTE_BACKEND_AGENTES", "auto").lower()
    if pedido in ("postgres", "local"):
        return pedido
    return "postgres" if os.getenv("CLEMENTE_BACKEND_RESERVAS", "json") == "postgres" else "local"


def es_postgres() -> bool:
    """Atajo: True cuando el estado de los agentes se guarda en Postgres."""
    return backend_activo() == "postgres"


def backends_activos() -> dict[str, Any]:
    """Backends efectivos de reservas, incidencias, estado de agentes y RAG, para /api/salud.

    Lee configuracion; no abre conexiones ni prueba servicios remotos. Sirve
    para no desplegar creyendo que se escribe en Trello o Postgres cuando en
    realidad se escribe en un archivo local."""
    from ..incidencias import backend_activo as incidencias_backend

    return {
        "reservas": os.getenv("CLEMENTE_BACKEND_RESERVAS", "json"),
        "incidencias": incidencias_backend(),
        "incidencias_mcp_url": bool(os.getenv("TRELLO_MCP_URL")),
        "agentes": backend_activo(),
        "rag": os.getenv("RAG_BACKEND", "chroma"),
        "guardrails_externos": bool(os.getenv("CLEMENTE_GUARDRAILS_URL")),
        "datos_dir": str(carpeta_datos()),
    }


@contextmanager
def conexion():
    """Presta una conexion del pool compartido de `app/db`; requiere contexto Flask.

    Sin contexto lanza RuntimeError con la instruccion, en vez del error
    generico de Flask, porque es el fallo tipico de un script o evaluador."""
    from flask import has_app_context

    if not has_app_context():
        raise RuntimeError(
            "El almacen Postgres de agentes necesita un contexto Flask "
            "(with app.app_context()): asi lo exige app/db/connection.py. "
            "Para correr sin base usar CLEMENTE_BACKEND_AGENTES=local."
        )
    from ..db.connection import connection

    with connection() as conn:
        yield conn


def _json(valor: Any) -> str:
    """Serializa a JSON para columnas JSONB (psycopg2 no adapta dict solo)."""
    return json.dumps(valor, ensure_ascii=False)


def _dict(valor: Any) -> dict:
    """Devuelve el JSONB ya decodificado por psycopg2, o lo decodifica si vino como texto."""
    return valor if isinstance(valor, dict) else json.loads(valor)


# ------------------------------ propietarios ------------------------------

def pg_vincular(reserva_id: str, sesion: str) -> None:
    """Registra que `sesion` es duena de `reserva_id`; una reserva ya vinculada produce IntegrityError."""
    with conexion() as conn, conn.cursor() as cur:
        cur.execute("INSERT INTO agentes_propietarios (reserva, sesion) VALUES (%s, %s)", (reserva_id, sesion))


def pg_es_propietario(reserva_id: str, sesion: str) -> bool:
    """True si la tabla vincula exactamente esa reserva con esa sesion."""
    with conexion() as conn, conn.cursor() as cur:
        cur.execute("SELECT 1 FROM agentes_propietarios WHERE reserva=%s AND sesion=%s", (reserva_id, sesion))
        return cur.fetchone() is not None


def pg_reservas_de(sesion: str) -> list[str]:
    """Codigos de reserva vinculados a la sesion, en orden de vinculacion."""
    with conexion() as conn, conn.cursor() as cur:
        cur.execute("SELECT reserva FROM agentes_propietarios WHERE sesion=%s ORDER BY creada", (sesion,))
        return [fila[0] for fila in cur.fetchall()]


# ------------------------------- propuestas -------------------------------

def pg_guardar_propuesta(sesion: str, codigo: str, accion: str, datos: dict, vence_epoch: float) -> None:
    """Deja una unica propuesta pendiente por sesion (reemplaza la anterior)."""
    with conexion() as conn, conn.cursor() as cur:
        cur.execute(
            "INSERT INTO agentes_propuestas (sesion, codigo, accion, datos, vence) "
            "VALUES (%s, %s, %s, %s::jsonb, to_timestamp(%s)) "
            "ON CONFLICT (sesion) DO UPDATE SET codigo=EXCLUDED.codigo, accion=EXCLUDED.accion, "
            "datos=EXCLUDED.datos, vence=EXCLUDED.vence",
            (sesion, codigo, accion, _json(datos), vence_epoch),
        )


def pg_consumir_propuesta(sesion: str, codigo: str) -> tuple[str, dict] | None:
    """Consume la propuesta de la sesion si el codigo coincide y no vencio; None si no.

    Compara el token en tiempo constante y lo borra con `DELETE ... RETURNING`
    condicionado al mismo codigo y a la vigencia: si dos peticiones llegan a la
    vez, solo una recibe la fila. Es el equivalente del `BEGIN IMMEDIATE` local."""
    with conexion() as conn, conn.cursor() as cur:
        cur.execute("SELECT codigo FROM agentes_propuestas WHERE sesion=%s", (sesion,))
        fila = cur.fetchone()
        if not fila or not secrets.compare_digest(fila[0], codigo):
            return None
        cur.execute(
            "DELETE FROM agentes_propuestas WHERE sesion=%s AND codigo=%s AND vence > now() "
            "RETURNING accion, datos",
            (sesion, codigo),
        )
        consumida = cur.fetchone()
    if not consumida:
        return None
    return consumida[0], _dict(consumida[1])


def pg_descartar_propuesta(sesion: str) -> None:
    """Elimina la propuesta pendiente de la sesion sin tocar la propiedad."""
    with conexion() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM agentes_propuestas WHERE sesion=%s", (sesion,))


# -------------------------------- perfiles --------------------------------

def pg_leer_perfil(clave: str) -> dict | None:
    """Perfil JSON de la clave, o None si no existe."""
    with conexion() as conn, conn.cursor() as cur:
        cur.execute("SELECT perfil FROM agentes_perfiles WHERE clave=%s", (clave,))
        fila = cur.fetchone()
    return _dict(fila[0]) if fila else None


def pg_guardar_perfil(clave: str, perfil: dict) -> None:
    """Crea o reemplaza el perfil de la clave."""
    with conexion() as conn, conn.cursor() as cur:
        cur.execute(
            "INSERT INTO agentes_perfiles (clave, perfil, actualizado) VALUES (%s, %s::jsonb, now()) "
            "ON CONFLICT (clave) DO UPDATE SET perfil=EXCLUDED.perfil, actualizado=now()",
            (clave, _json(perfil)),
        )


# ------------------------------- revisiones -------------------------------

def pg_guardar_revision(sesion: str, canal: str, solicitud: dict) -> None:
    """Deja en cola la solicitud HITL de la sesion (una por sesion)."""
    with conexion() as conn, conn.cursor() as cur:
        cur.execute(
            "INSERT INTO agentes_revisiones (sesion, canal, solicitud) VALUES (%s, %s, %s::jsonb) "
            "ON CONFLICT (sesion) DO UPDATE SET canal=EXCLUDED.canal, solicitud=EXCLUDED.solicitud, creada=now()",
            (sesion, canal, _json(solicitud)),
        )


def pg_quitar_revision(sesion: str) -> None:
    """Retira la solicitud HITL de la sesion de la cola."""
    with conexion() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM agentes_revisiones WHERE sesion=%s", (sesion,))


def pg_listar_revisiones() -> dict[str, dict]:
    """Cola HITL completa: {sesion: {sesion_id, canal, solicitud}}, de la mas antigua a la mas nueva."""
    with conexion() as conn, conn.cursor() as cur:
        cur.execute("SELECT sesion, canal, solicitud FROM agentes_revisiones ORDER BY creada")
        filas = cur.fetchall()
    return {
        sesion: {"sesion_id": sesion, "canal": canal, "solicitud": _dict(solicitud)}
        for sesion, canal, solicitud in filas
    }


# --------------- resoluciones, continuidad y rechazos (ambos backends) ---------------
# El backend local vive en memoria del proceso: es lo que ya habia (los
# diccionarios de grafo.py) y alcanza para pruebas y demo de una replica.

_local_resoluciones: dict[str, dict] = {}
_local_continuidad: dict[str, dict] = {}
_local_rechazos: dict[str, deque] = defaultdict(deque)


def _ahora() -> float:
    """Reloj epoch del almacen local; las pruebas lo reemplazan."""
    return time.time()


def reiniciar_local() -> None:
    """Vacia el estado local en memoria; lo usan las pruebas entre casos."""
    _local_resoluciones.clear()
    _local_continuidad.clear()
    _local_rechazos.clear()


def guardar_resolucion(sesion: str, decision: str, texto: str) -> None:
    """Guarda la resolucion HITL que el cliente todavia no recibio (una por sesion)."""
    if es_postgres():
        with conexion() as conn, conn.cursor() as cur:
            cur.execute(
                "INSERT INTO agentes_resoluciones (sesion, decision, texto) VALUES (%s, %s, %s) "
                "ON CONFLICT (sesion) DO UPDATE SET decision=EXCLUDED.decision, texto=EXCLUDED.texto, creada=now()",
                (sesion, decision, texto),
            )
        return
    _local_resoluciones[sesion] = {"decision": decision, "texto": texto}


def consumir_resolucion(sesion: str) -> dict | None:
    """Devuelve y borra la resolucion pendiente de la sesion; None si no hay."""
    if es_postgres():
        with conexion() as conn, conn.cursor() as cur:
            cur.execute("DELETE FROM agentes_resoluciones WHERE sesion=%s RETURNING decision, texto", (sesion,))
            fila = cur.fetchone()
        return {"decision": fila[0], "texto": fila[1]} if fila else None
    return _local_resoluciones.pop(sesion, None)


def leer_continuidad(sesion: str) -> dict:
    """{ultimo_agente, incidencia_abierta} de la sesion; vacios si no hay registro."""
    if es_postgres():
        with conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT ultimo_agente, incidencia_abierta FROM agentes_continuidad WHERE sesion=%s", (sesion,))
            fila = cur.fetchone()
        if fila:
            return {"ultimo_agente": fila[0] or "", "incidencia_abierta": fila[1]}
        return {"ultimo_agente": "", "incidencia_abierta": None}
    return dict(_local_continuidad.get(sesion) or {"ultimo_agente": "", "incidencia_abierta": None})


def guardar_continuidad(sesion: str, ultimo_agente: str | None = None, incidencia_abierta: str | None = None) -> None:
    """Actualiza solo los campos recibidos (None = no tocar)."""
    actual = leer_continuidad(sesion)
    if ultimo_agente is not None:
        actual["ultimo_agente"] = ultimo_agente
    if incidencia_abierta is not None:
        actual["incidencia_abierta"] = incidencia_abierta
    if es_postgres():
        with conexion() as conn, conn.cursor() as cur:
            cur.execute(
                "INSERT INTO agentes_continuidad (sesion, ultimo_agente, incidencia_abierta) VALUES (%s, %s, %s) "
                "ON CONFLICT (sesion) DO UPDATE SET ultimo_agente=EXCLUDED.ultimo_agente, "
                "incidencia_abierta=EXCLUDED.incidencia_abierta, actualizado=now()",
                (sesion, actual["ultimo_agente"], actual["incidencia_abierta"]),
            )
        return
    _local_continuidad[sesion] = actual


def olvidar_continuidad(sesion: str) -> None:
    """Borra continuidad y resolucion pendiente de la sesion (reinicio de hilo)."""
    if es_postgres():
        with conexion() as conn, conn.cursor() as cur:
            cur.execute("DELETE FROM agentes_continuidad WHERE sesion=%s", (sesion,))
            cur.execute("DELETE FROM agentes_resoluciones WHERE sesion=%s", (sesion,))
        return
    _local_continuidad.pop(sesion, None)
    _local_resoluciones.pop(sesion, None)


def registrar_rechazo(sesion: str, motivo: str) -> None:
    """Anota un rechazo (autorizacion denegada, confirmacion invalida) para la ventana de abuso."""
    if es_postgres():
        with conexion() as conn, conn.cursor() as cur:
            cur.execute("INSERT INTO agentes_rechazos (sesion, motivo) VALUES (%s, %s)", (sesion, motivo))
        return
    _local_rechazos[sesion].append(_ahora())


def contar_rechazos(sesion: str, ventana_segundos: int) -> int:
    """Cuantos rechazos tuvo la sesion en los ultimos `ventana_segundos`."""
    if es_postgres():
        with conexion() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT count(*) FROM agentes_rechazos WHERE sesion=%s AND momento > now() - make_interval(secs => %s)",
                (sesion, ventana_segundos),
            )
            return int(cur.fetchone()[0])
    limite = _ahora() - ventana_segundos
    cola = _local_rechazos[sesion]
    while cola and cola[0] < limite:
        cola.popleft()
    return len(cola)
