"""Una operacion a la vez: un pedido al equipo sin atender detiene las reservas nuevas; sin modelo.

El bloqueo lo hace cumplir el servidor, no el prompt. Se levanta cuando el equipo atiende o cierra el caso, cuando el
cliente lo retira con CANCELAR SOLICITUD, o a las 24 horas. Los reclamos no cuentan, y modificar o cancelar una reserva
que ya existe tampoco se bloquea.
"""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app.agentes import autorizacion, casos_abiertos, fecha
from app.agentes import reservas as agente_reservas
from app.agentes.contexto import ContextoConversacion
from app.agentes.tools import reservas_tools as tools
from app.contratos import MensajeEntrante
from app.incidencias import obtener_servicio
from app.orquestador import grafo
from app.reservas.servicio_json import ServicioReservasJSON

# Martes 2026-10-06 21:00 en Lima, para que el sabado 2026-10-10 sea una fecha valida sin depender del dia de la suite.
INSTANTE = datetime(2026, 10, 7, 2, 0, tzinfo=timezone.utc)
SESION = "whatsapp-51999111222"
PEDIDO = "[escalado desde orquestador] Solicita atencion de una persona\nMensaje del cliente: quiero hablar con alguien"
VALIDA = {"nombre": "Ana Ruiz", "telefono": "999111222", "fecha": "2026-10-10",
          "hora": "20:00", "personas": 12, "dia_semana": "sabado"}


@pytest.fixture(autouse=True)
def reloj_fijo(monkeypatch):
    """Fija el reloj de Lima: las reservas del 2026-10-10 dejan de ser validas a partir del 11 de octubre."""
    monkeypatch.setattr(fecha, "_reloj", lambda: INSTANTE)


@pytest.fixture
def servicio(tmp_path, monkeypatch):
    """Servicio de reservas en un archivo temporal, conectado a las herramientas."""
    temporal = ServicioReservasJSON(archivo_reservas=tmp_path / "reservas_de_la_prueba.json")
    monkeypatch.setattr(tools, "servicio_reservas", lambda: temporal)
    monkeypatch.setattr(grafo, "servicio_reservas", lambda: temporal)
    return temporal


@pytest.fixture
def hilos(monkeypatch):
    """Reemplaza el checkpoint de reservas por un registro en memoria de hilos pausados."""
    estado = {"pausados": set(), "liberados": []}

    def liberar(sesion_id):
        """Borra el hilo simulado."""
        estado["pausados"].discard(sesion_id)
        estado["liberados"].append(sesion_id)
        return True

    monkeypatch.setattr(agente_reservas, "liberar_pausa", liberar)
    monkeypatch.setattr(agente_reservas, "tiene_hilo_guardado", lambda sid: sid in estado["pausados"])
    return estado


@pytest.fixture
def sin_modelo(monkeypatch):
    """Un grafo que falla si se invoca: CANCELAR SOLICITUD y las confirmaciones las resuelve el servidor."""
    class Grafo:
        """Grafo que no debe llegar a ejecutarse."""

        def invoke(self, estado):
            """Falla: el comando no pasa por el planificador."""
            raise AssertionError("este mensaje no debe llegar al modelo")

    monkeypatch.setattr(grafo, "obtener_grafo", lambda: Grafo())


def runtime(sesion=SESION):
    """Runtime simulado de una herramienta, con la conversacion indicada."""
    return SimpleNamespace(context=ContextoConversacion(sesion_id=sesion))


def reservar(rt=None, sesion=SESION, nombre="Ana Prueba", telefono="900000001"):
    """Pide preparar una reserva de 2 personas el sabado 2026-10-10 a las 20:00."""
    return tools.crear_reserva.func(nombre, telefono, "2026-10-10", "20:00", 2, rt or runtime(sesion))


def abrir_pedido(sesion=SESION, descripcion=PEDIDO):
    """Deja abierto el caso que crea el orquestador cuando el cliente pide hablar con alguien; devuelve su codigo."""
    caso = obtener_servicio().crear_incidencia(sesion_id=sesion, descripcion=descripcion, tipo="otro")
    grafo._escalado_de[sesion] = caso.id
    return caso.id


def turno(texto):
    """Un turno completo del orquestador."""
    return grafo._responder_turno(MensajeEntrante(sesion_id=SESION, texto=texto, canal="whatsapp"))


def hay_propuesta():
    """True si hay un resumen guardado esperando confirmacion."""
    with autorizacion._db() as db:
        return db.execute("SELECT 1 FROM propuestas WHERE sesion=?", (SESION,)).fetchone() is not None


# --- el bloqueo ---------------------------------------------------------------------------------------------------

def test_sin_pedidos_abiertos_la_reserva_se_prepara_normal(servicio):
    """Control: sin nada abierto, el resumen sale."""
    assert "escribe CONFIRMO" in reservar()


def test_con_un_pedido_sin_atender_no_se_prepara_otra_reserva(servicio):
    """El cliente lee el codigo de su pedido y como salir; no queda ningun resumen que confirmar."""
    codigo = abrir_pedido()
    rt = runtime()
    texto = reservar(rt)
    assert texto == casos_abiertos.BLOQUEO_POR_CASO_ABIERTO.format(codigo=codigo)
    assert "CANCELAR SOLICITUD" in texto and codigo in texto
    assert rt.context.datos["operacion_bloqueada"] == texto and not hay_propuesta()
    assert autorizacion.confirmar(SESION, "confirmo", servicio)[0] == autorizacion.SIN_RESUMEN_PENDIENTE
    assert servicio.buscar_reservas_de("900000001") == []


def test_un_reclamo_no_bloquea(servicio):
    """Solo cuentan los pedidos que se escalan al equipo; un plato frio no deja a nadie sin reservar."""
    abrir_pedido(descripcion="El plato llego frio y tardaron 40 minutos")
    assert "escribe CONFIRMO" in reservar()


def test_el_pedido_de_otra_conversacion_no_bloquea(servicio):
    """Cada conversacion se limita a si misma."""
    abrir_pedido(sesion="whatsapp-51888000111")
    assert "escribe CONFIRMO" in reservar()


def test_cuando_el_equipo_cierra_el_caso_ya_no_bloquea(servicio):
    """Con la tarjeta resuelta el cliente puede reservar otra vez."""
    codigo = abrir_pedido()
    assert reservar() == casos_abiertos.BLOQUEO_POR_CASO_ABIERTO.format(codigo=codigo)
    obtener_servicio().cerrar_incidencia(codigo, "atendido")
    assert "escribe CONFIRMO" in reservar()


def test_pasadas_24_horas_el_pedido_ya_no_bloquea(servicio):
    """Un pedido que nadie atendio en un dia no deja al cliente sin poder reservar para siempre."""
    codigo = abrir_pedido()
    casos = obtener_servicio()._leer()
    for caso in casos:
        caso["creada"] = (datetime.now() - timedelta(hours=25)).isoformat(timespec="seconds")
    obtener_servicio()._escribir(casos)
    assert "escribe CONFIRMO" in reservar()
    assert codigo


def test_modificar_o_cancelar_una_reserva_que_ya_existe_no_se_bloquea(servicio):
    """Cancelar libera mesas: es la salida, no el problema."""
    reservar()
    autorizacion.confirmar(SESION, "confirmo", servicio)
    existente = servicio.buscar_reservas_de("900000001")[0]
    abrir_pedido()
    rt = runtime()
    texto = tools.cancelar_reserva.func(existente.id, rt)
    assert "escribe CONFIRMO" in texto and "operacion_bloqueada" not in rt.context.datos


# --- como se sale --------------------------------------------------------------------------------------------------

def test_cancelar_solicitud_retira_el_pedido_y_libera_las_reservas(servicio, hilos, sin_modelo):
    """El cliente escribe el comando y, sin pasar por el modelo, vuelve a poder reservar."""
    codigo = abrir_pedido()
    assert reservar() == casos_abiertos.BLOQUEO_POR_CASO_ABIERTO.format(codigo=codigo)
    assert turno("CANCELAR SOLICITUD").texto == grafo.PEDIDO_AL_EQUIPO_RETIRADO.format(codigo=codigo)
    assert "escribe CONFIRMO" in reservar()


def test_un_dato_nuevo_despues_de_retirarlo_vuelve_a_bloquear(servicio, hilos, sin_modelo):
    """Si el cliente vuelve a pedir una persona despues de retirar, el pedido vuelve a contar."""
    codigo = abrir_pedido()
    turno("CANCELAR SOLICITUD")
    assert "escribe CONFIRMO" in reservar()
    contexto = ContextoConversacion(sesion_id=SESION)
    assert grafo._escalar(SESION, {"origen": "orquestador", "motivo": "x", "detalle": "y"}, "otra vez", contexto) == codigo
    assert reservar() == casos_abiertos.BLOQUEO_POR_CASO_ABIERTO.format(codigo=codigo)


def test_la_marca_mas_reciente_decide_si_el_pedido_cuenta(servicio):
    """Retirado y vuelto a pedir, o al reves, cuenta lo ultimo que quedo escrito en la tarjeta."""
    def con(*notas):
        """Descripcion de un pedido con las notas indicadas, en orden."""
        return PEDIDO + "".join(f"\n[nota 2026-10-11 10:00] {n}" for n in notas)

    retirado, nuevo = casos_abiertos.MARCA_PEDIDO_RETIRADO, casos_abiertos.MARCA_DATO_NUEVO
    for notas, bloquea in [((), True), ((retirado,), False), ((retirado, nuevo), True), ((nuevo, retirado), False)]:
        obtener_servicio()._escribir([])
        caso = obtener_servicio().crear_incidencia(sesion_id=SESION, descripcion=con(*notas), tipo="otro")
        assert (casos_abiertos.caso_de_atencion_abierto(SESION) == caso.id) is bloquea, notas


# --- el texto que lee el cliente y los grupos grandes -----------------------------------------------------------

def test_el_cliente_lee_el_aviso_fijo_y_no_el_texto_del_modelo():
    """El orquestador reemplaza lo que escribio el agente por el aviso del servidor."""
    contexto = ContextoConversacion(sesion_id=SESION)
    aviso = casos_abiertos.BLOQUEO_POR_CASO_ABIERTO.format(codigo="I-ABC123")
    contexto.datos["operacion_bloqueada"] = aviso
    estado = {"sesion_id": SESION, "mensaje": "quiero reservar", "accion": "delegar",
              "respuestas": [{"agente": "reservas", "texto": "Claro, ya te la preparo"}], "contexto": contexto}
    assert grafo._nodo_cierre(estado)["respuesta"] == aviso


def contexto_pausado():
    """Contexto de un turno en el que el agente pidio una excepcion de grupo y el hilo quedo pausado."""
    contexto = ContextoConversacion(sesion_id=SESION)
    contexto.escalado = True
    contexto.datos["escalamiento"] = {"origen": "reservas_hitl", "motivo": "grupo"}
    contexto.datos["revision_humana"] = {"estado": "pendiente", "flujo": "reservas", "solicitud": {
        "action_requests": [{"name": "solicitar_excepcion_grupo", "args": VALIDA, "description": "Revisar"}]}}
    return contexto


def test_un_grupo_valido_sin_pedidos_abiertos_pasa_al_personal(hilos):
    """Control: la solicitud queda pausada para el personal."""
    hilos["pausados"].add(SESION)
    contexto = contexto_pausado()
    assert agente_reservas._descartar_excepcion_invalida(SESION, contexto) is None
    assert SESION in hilos["pausados"] and contexto.datos["revision_humana"]["estado"] == "pendiente"


def test_un_grupo_valido_no_pasa_al_personal_si_hay_un_pedido_sin_atender(hilos):
    """La solicitud se descarta antes de llegar a la cola, con el aviso de siempre, y el hilo se libera."""
    codigo = abrir_pedido()
    hilos["pausados"].add(SESION)
    contexto = contexto_pausado()
    texto = agente_reservas._descartar_excepcion_invalida(SESION, contexto)
    assert texto == casos_abiertos.BLOQUEO_POR_CASO_ABIERTO.format(codigo=codigo)
    assert "revision_humana" not in contexto.datos and not contexto.escalado
    assert SESION not in hilos["pausados"]

