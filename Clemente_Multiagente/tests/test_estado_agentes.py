"""
Estado compartido de los agentes (paso 7 del plan del 18/09).

Cubre el almacen en sus dos backends, la atomicidad del token CONFIRMO bajo
concurrencia, la continuidad del hilo, la entrega diferida de resoluciones
HITL y la degradacion por abuso. Las pruebas Postgres usan el fixture
`estado_postgres` (Postgres local de pruebas, tablas `agentes_*`); sin base
local se saltan y corren en CI.
"""

import re
import threading
from concurrent.futures import ThreadPoolExecutor

import pytest

from app.agentes import abuso, almacen, autorizacion, memoria
from app.agentes.contexto import ContextoConversacion
from app.contratos import MensajeEntrante, Reserva
from app.orquestador import grafo


class _ServicioContador:
    """Servicio minimo que siempre tiene mesa y cuenta cuantas reservas escribio."""

    def __init__(self):
        """Arranca el contador protegido por un lock para usarlo desde varios hilos."""
        self.creadas = 0
        self._lock = threading.Lock()

    def consultar_disponibilidad(self, *_args, **_kwargs):
        """Siempre hay una opcion: lo que se prueba es el token, no la disponibilidad."""
        return [object()]

    def crear_reserva(self, nombre, telefono, fecha, hora, personas, zona, notas=""):
        """Escribe una reserva sintetica y la devuelve; cuenta la escritura."""
        with self._lock:
            self.creadas += 1
            numero = self.creadas
        return Reserva(id=f"R-CONC{numero:02d}", nombre=nombre, telefono=telefono, fecha=fecha,
                       hora=hora, personas=personas, zona=zona or "salon", mesa_id="M01", notas=notas)

    def obtener_reserva(self, reserva_id):
        """No hace falta para crear; devuelve None."""
        return None


DATOS_CREAR = {"nombre": "Ana", "telefono": "999111222", "fecha": "2026-12-04", "hora": "20:00",
               "personas": 2, "zona": "", "notas": ""}


def _token(texto: str) -> str:
    """Extrae el comando CONFIRMO del resumen del servidor."""
    return re.search(r"CONFIRMO [0-9A-F]{8}", texto)[0]


def _grafo_falso(texto="Claro, dime."):
    """Sustituto del grafo compilado que devuelve un cierre fijo sin modelo."""
    class Grafo:
        """Doble del grafo LangGraph con la forma minima de `final` que lee `responder`."""

        def invoke(self, _estado):
            """Devuelve un turno de informacion resuelto."""
            return {"respuesta": texto, "ruta": "informacion", "motivo_ruta": "prueba",
                    "plan": ["informacion"], "pendientes": []}
    return Grafo()


# --------------------------------------------------------------------------
# Seleccion de backend
# --------------------------------------------------------------------------

def test_el_backend_auto_sigue_al_de_reservas(monkeypatch):
    """Si las reservas viven en Postgres, el estado que las autoriza tambien."""
    monkeypatch.setenv("CLEMENTE_BACKEND_AGENTES", "auto")
    monkeypatch.setenv("CLEMENTE_BACKEND_RESERVAS", "postgres")
    assert almacen.backend_activo() == "postgres"
    monkeypatch.setenv("CLEMENTE_BACKEND_RESERVAS", "json")
    assert almacen.backend_activo() == "local"
    monkeypatch.setenv("CLEMENTE_BACKEND_AGENTES", "postgres")
    assert almacen.backend_activo() == "postgres"
    monkeypatch.setenv("CLEMENTE_BACKEND_AGENTES", "local")
    assert almacen.backend_activo() == "local"


def test_postgres_sin_contexto_flask_explica_como_arreglarlo(monkeypatch):
    """El pool de app/db exige app_context; el error debe decirlo, no fallar en Flask."""
    monkeypatch.setenv("CLEMENTE_BACKEND_AGENTES", "postgres")
    with pytest.raises(RuntimeError, match="app_context"):
        almacen.leer_continuidad("x")


def test_los_backends_efectivos_se_pueden_consultar(monkeypatch):
    """Lo que /api/salud expone: nunca desplegar creyendo que se escribe en Trello o Postgres."""
    monkeypatch.setenv("RAG_BACKEND", "azure_search")
    activos = almacen.backends_activos()
    assert activos["agentes"] == "local"
    assert activos["incidencias"] == "json"
    assert activos["rag"] == "azure_search"
    assert activos["reservas"] in {"json", "postgres"}


# --------------------------------------------------------------------------
# Backend local
# --------------------------------------------------------------------------

def test_continuidad_y_resolucion_en_memoria():
    """Verifica que continuidad y resolucion en memoria."""
    almacen.guardar_continuidad("s1", ultimo_agente="reservas")
    almacen.guardar_continuidad("s1", incidencia_abierta="I-ABC")
    assert almacen.leer_continuidad("s1") == {"ultimo_agente": "reservas", "incidencia_abierta": "I-ABC"}

    almacen.guardar_resolucion("s1", "approve", "El equipo aprobó tu mesa.")
    assert almacen.consumir_resolucion("s1") == {"decision": "approve", "texto": "El equipo aprobó tu mesa."}
    assert almacen.consumir_resolucion("s1") is None

    almacen.olvidar_continuidad("s1")
    assert almacen.leer_continuidad("s1") == {"ultimo_agente": "", "incidencia_abierta": None}


def test_los_rechazos_expiran_con_la_ventana(monkeypatch):
    """Un error humano aislado no acumula para siempre."""
    reloj = [1_000.0]
    monkeypatch.setattr(almacen, "_ahora", lambda: reloj[0])

    for _ in range(3):
        almacen.registrar_rechazo("s2", "confirmacion")
    assert almacen.contar_rechazos("s2", 600) == 3
    reloj[0] += 601
    assert almacen.contar_rechazos("s2", 600) == 0


def test_una_sola_confirmacion_gana_en_sqlite():
    """Ocho hilos con el mismo CONFIRMO: una reserva, un exito, siete rechazos."""
    servicio = _ServicioContador()
    texto = autorizacion.proponer(ContextoConversacion(sesion_id="carrera"), "crear", DATOS_CREAR, servicio)
    token = _token(texto)

    with ThreadPoolExecutor(max_workers=8) as hilos:
        resultados = list(hilos.map(lambda _: autorizacion.confirmar("carrera", token, servicio), range(8)))

    exitos = [r for r in resultados if "reserva" in r[1]]
    assert len(exitos) == 1
    assert servicio.creadas == 1
    assert all(r[0] == autorizacion.CONFIRMACION_INVALIDA for r in resultados if r is not exitos[0])


# --------------------------------------------------------------------------
# HITL diferido y abuso (backend local)
# --------------------------------------------------------------------------

def test_la_resolucion_hitl_se_entrega_en_el_siguiente_turno_una_sola_vez(tmp_path, monkeypatch):
    """El panel del staff no envia WhatsApp: el cliente se entera en su proximo mensaje."""
    from app.agentes import reservas
    from app.incidencias.servicio_json import ServicioIncidenciasJSON
    from app.observabilidad import trazas

    monkeypatch.setattr(grafo, "servicio_incidencias", lambda: ServicioIncidenciasJSON(archivo=tmp_path / "inc.json"))
    monkeypatch.setattr(reservas, "resolver_revision", lambda *_a: "El equipo no autorizó la excepción de capacidad.")
    grafo._revisiones["t-dif"] = {"sesion_id": "t-dif", "contexto": ContextoConversacion(sesion_id="t-dif"),
                                  "solicitud": {}, "canal": "webchat"}
    grafo.resolver_revision("t-dif", "reject", "sin capacidad")

    monkeypatch.setattr(grafo, "obtener_grafo", _grafo_falso)
    primero = grafo.responder(MensajeEntrante(sesion_id="t-dif", texto="hola, alguna novedad?"))
    segundo = grafo.responder(MensajeEntrante(sesion_id="t-dif", texto="ok"))

    assert primero.texto.startswith("Sobre tu solicitud anterior: El equipo no autorizó")
    assert primero.texto.endswith("Claro, dime.")
    assert primero.datos["resolucion_entregada"] == "reject"
    assert not segundo.texto.startswith("Sobre tu solicitud anterior")
    assert any(t.evento == "hitl_entregado" for t in trazas.ultimas_trazas(sesion_id="t-dif"))


def test_tras_el_maximo_de_rechazos_no_se_invoca_al_modelo(monkeypatch):
    """Adivinar tokens no puede consumir razonamiento ilimitado; otra sesion no se ve afectada."""
    from app.observabilidad import trazas

    monkeypatch.setenv("CLEMENTE_MAX_RECHAZOS", "3")
    monkeypatch.setattr(grafo, "obtener_grafo", lambda: pytest.fail("un turno degradado no invoca al grafo"))

    for _ in range(3):
        rechazo = grafo.responder(MensajeEntrante(sesion_id="abusivo", texto="CONFIRMO DEADBEEF"))
        assert rechazo.texto == autorizacion.CONFIRMACION_INVALIDA

    degradado = grafo.responder(MensajeEntrante(sesion_id="abusivo", texto="quiero una mesa"))

    assert degradado.agente == "seguridad"
    assert degradado.datos == {"guardrail": "abuso"}
    assert degradado.texto == abuso.MENSAJE_DEGRADADO
    assert any(t.evento == "abuso_degradado" for t in trazas.ultimas_trazas(sesion_id="abusivo"))
    assert not abuso.degradado("otra-sesion")


def test_una_operacion_incierta_no_cuenta_como_rechazo(monkeypatch):
    """Que la base falle al escribir no es culpa del cliente."""
    class EscribeMal(_ServicioContador):
        """Servicio cuya escritura falla por infraestructura."""

        def crear_reserva(self, *_a, **_k):
            """Simula Postgres caido justo al insertar."""
            raise RuntimeError("OperationalError: connection lost")

    servicio = EscribeMal()
    monkeypatch.setattr(grafo, "servicio_reservas", lambda: servicio)
    monkeypatch.setenv("CLEMENTE_MAX_RECHAZOS", "1")
    token = _token(autorizacion.proponer(ContextoConversacion(sesion_id="incierta"), "crear", DATOS_CREAR, servicio))

    respuesta = grafo.responder(MensajeEntrante(sesion_id="incierta", texto=token))

    assert respuesta.texto == autorizacion.ESCRITURA_INCIERTA
    assert respuesta.datos["operacion_incierta"] == "crear"
    assert not abuso.degradado("incierta")


# --------------------------------------------------------------------------
# Backend Postgres (tablas agentes_*)
# --------------------------------------------------------------------------

def test_postgres_guarda_propiedad_propuestas_perfil_revision_y_continuidad(estado_postgres):
    """Recorrido completo del almacen sobre las tablas agentes_* del Postgres local."""
    servicio = _ServicioContador()

    # Propiedad y token de un uso.
    autorizacion.vincular("web-pg", "R-PREVIA")
    assert autorizacion.es_propietario("web-pg", "R-PREVIA")
    assert not autorizacion.es_propietario("otra", "R-PREVIA")
    token = _token(autorizacion.proponer(ContextoConversacion(sesion_id="web-pg"), "crear", DATOS_CREAR, servicio))
    assert autorizacion.confirmar("intruso", token, servicio)[1] == {}
    exito = autorizacion.confirmar("web-pg", token, servicio)
    assert "reserva" in exito[1]
    assert autorizacion.es_propietario("web-pg", exito[1]["reserva"]["id"])
    assert autorizacion.confirmar("web-pg", token, servicio)[1] == {}

    # Perfil por identidad del servidor.
    memoria.anotar("web-pg", "alergia", "mani")
    memoria.anotar("web-pg", "alergia", "Mani")
    assert memoria.perfil_de("web-pg")["alergias"] == ["mani"]
    assert memoria.perfil_de("web-otro") is None

    # Cola HITL visible aunque el proceso pierda su diccionario.
    grafo._revisiones["web-pg"] = {"sesion_id": "web-pg", "contexto": ContextoConversacion(sesion_id="web-pg"),
                                   "solicitud": {"action_requests": []}, "canal": "whatsapp"}
    grafo._persistir_revision("web-pg")
    grafo._revisiones.clear()
    assert grafo.revisiones_pendientes() == [{"sesion_id": "web-pg", "solicitud": {"action_requests": []}, "canal": "whatsapp"}]
    grafo._retirar_revision("web-pg")
    assert grafo.revisiones_pendientes() == []

    # Continuidad, resolucion y rechazos.
    almacen.guardar_continuidad("web-pg", ultimo_agente="incidencias", incidencia_abierta="I-1")
    assert almacen.leer_continuidad("web-pg") == {"ultimo_agente": "incidencias", "incidencia_abierta": "I-1"}
    almacen.guardar_resolucion("web-pg", "approve", "Aprobado.")
    assert almacen.consumir_resolucion("web-pg") == {"decision": "approve", "texto": "Aprobado."}
    assert almacen.consumir_resolucion("web-pg") is None
    almacen.registrar_rechazo("web-pg", "confirmacion")
    assert almacen.contar_rechazos("web-pg", 600) == 1
    almacen.olvidar_continuidad("web-pg")
    assert almacen.leer_continuidad("web-pg")["ultimo_agente"] == ""


def test_postgres_una_sola_confirmacion_gana(estado_postgres):
    """Cuatro hilos (cada uno con su app_context) y el mismo token: una sola escritura."""
    servicio = _ServicioContador()
    token = _token(autorizacion.proponer(ContextoConversacion(sesion_id="carrera-pg"), "crear", DATOS_CREAR, servicio))

    def confirmar(_):
        """Confirma desde un hilo con contexto propio, como haria otra replica."""
        with estado_postgres.app_context():
            return autorizacion.confirmar("carrera-pg", token, servicio)

    with ThreadPoolExecutor(max_workers=4) as hilos:
        resultados = list(hilos.map(confirmar, range(4)))

    assert sum(1 for r in resultados if "reserva" in r[1]) == 1
    assert servicio.creadas == 1


def test_postgres_el_orquestador_conserva_continuidad_y_ticket_entre_procesos(estado_postgres, tmp_path, monkeypatch):
    """Lo que antes vivia en diccionarios del proceso ahora sobrevive a `reiniciar_grafo`."""
    from app.incidencias.servicio_json import ServicioIncidenciasJSON

    servicio = ServicioIncidenciasJSON(archivo=tmp_path / "inc.json")
    monkeypatch.setattr(grafo, "servicio_incidencias", lambda: servicio)
    contexto = ContextoConversacion(sesion_id="hilo-pg")
    contexto.escalado = True
    contexto.datos["escalamiento"] = {"origen": "reservas", "motivo": "grupo de 14", "detalle": ""}

    codigo = grafo._escalar("hilo-pg", contexto.datos["escalamiento"], "somos 14", contexto)
    grafo._guardar_ultimo_agente("hilo-pg", "reservas")
    grafo.reiniciar_grafo()          # simula otro proceso: los diccionarios se vacian

    assert grafo._ultimo_agente_de("hilo-pg") == "reservas"
    assert grafo._incidencia_abierta_de("hilo-pg") == codigo
    segundo = grafo._escalar("hilo-pg", contexto.datos["escalamiento"], "soy Ana, 999111222", contexto)
    assert segundo == codigo
    assert len(servicio.listar_incidencias()) == 1
