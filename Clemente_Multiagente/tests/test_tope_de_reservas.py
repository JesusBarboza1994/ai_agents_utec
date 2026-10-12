"""Tope de 3 reservas activas por conversacion y por telefono, y una sola por fecha y hora; sin modelo.

El tope cuenta las reservas que existen ahora y todavia no pasaron, no las creadas "en las ultimas horas": cancelar una
libera su lugar y una fecha ya pasada deja de contar. Como solo se reserva hasta 30 dias adelante, ese es su intervalo.
"""
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from app.agentes import autorizacion, fecha, tope_de_reservas
from app.agentes.contexto import ContextoConversacion
from app.agentes.tools import reservas_tools as tools
from app.orquestador import grafo
from app.reservas.servicio_json import ServicioReservasJSON

# Martes 2026-10-06 21:00 en Lima. Los dias de abajo son de jueves a martes, con turno de la noche.
INSTANTE = datetime(2026, 10, 7, 2, 0, tzinfo=timezone.utc)
DIAS = ["2026-10-08", "2026-10-09", "2026-10-10", "2026-10-13", "2026-10-14"]
SESION, OTRA = "whatsapp-51999111222", "whatsapp-51888000111"
TELEFONO = "900000001"


@pytest.fixture(autouse=True)
def reloj_fijo(monkeypatch):
    """Fija el reloj de Lima para que las fechas de la prueba no dependan del dia en que se corre la suite."""
    monkeypatch.setattr(fecha, "_reloj", lambda: INSTANTE)


@pytest.fixture
def servicio(tmp_path, monkeypatch):
    """Servicio de reservas en un archivo temporal, conectado a las herramientas."""
    temporal = ServicioReservasJSON(archivo_reservas=tmp_path / "reservas_de_la_prueba.json")
    monkeypatch.setattr(tools, "servicio_reservas", lambda: temporal)
    monkeypatch.setattr(grafo, "servicio_reservas", lambda: temporal)
    return temporal


def pedir(dia, sesion=SESION, telefono=TELEFONO, hora="20:00", personas=2, rt=None):
    """Pide preparar una reserva con un runtime nuevo (un mensaje nuevo) y devuelve lo que responde la herramienta."""
    rt = rt or SimpleNamespace(context=ContextoConversacion(sesion_id=sesion))
    return tools.crear_reserva.func("Ana Prueba", telefono, dia, hora, personas, rt)


def reservar(dia, sesion=SESION, telefono=TELEFONO, hora="20:00", personas=2):
    """Prepara y confirma una reserva; devuelve la reserva creada."""
    pedir(dia, sesion, telefono, hora, personas)
    _, datos = autorizacion.confirmar(sesion, "confirmo", tools.servicio_reservas())
    return datos["reserva"]


def test_la_cuarta_reserva_activa_no_se_prepara(servicio):
    """Tres entran; la cuarta recibe el aviso fijo y no queda ningun resumen que confirmar."""
    for dia in DIAS[:3]:
        reservar(dia)
    rt = SimpleNamespace(context=ContextoConversacion(sesion_id=SESION))
    texto = pedir(DIAS[3], rt=rt)
    assert texto == tope_de_reservas.TOPE_ALCANZADO.format(cantidad=3) and "3 reservas activas" in texto
    assert rt.context.datos["operacion_bloqueada"] == texto
    assert autorizacion.confirmar(SESION, "confirmo", servicio)[0] == autorizacion.SIN_RESUMEN_PENDIENTE
    assert len(servicio.buscar_reservas_de(TELEFONO)) == 3


def test_cancelar_una_libera_su_lugar(servicio):
    """Las canceladas no cuentan."""
    reservas = [reservar(dia) for dia in DIAS[:3]]
    servicio.cancelar_reserva(reservas[0]["id"])
    assert "escribe CONFIRMO" in pedir(DIAS[3])


def test_las_reservas_que_ya_pasaron_no_cuentan(servicio, monkeypatch):
    """El tope es de reservas activas a la vez, no de reservas en toda la historia del cliente."""
    for dia in DIAS[:3]:
        reservar(dia)
    pasado_manana = datetime(2026, 10, 12, 15, 0, tzinfo=timezone.utc)      # lunes 12 de octubre, 10:00 en Lima
    monkeypatch.setattr(fecha, "_reloj", lambda: pasado_manana)
    assert "escribe CONFIRMO" in pedir(DIAS[3])


def test_una_sola_reserva_por_fecha_y_hora(servicio):
    """Dos mesas a la misma hora, aunque sean para distinta cantidad de personas, no se preparan."""
    existente = reservar(DIAS[0])
    texto = pedir(DIAS[0], personas=4, telefono="900000002")
    assert texto == tope_de_reservas.MISMO_TURNO.format(reserva=existente["id"], fecha=DIAS[0], hora="20:00")
    assert "modifico" in texto


def test_otra_hora_el_mismo_dia_si_se_puede(servicio):
    """El limite es por turno, no por dia."""
    reservar(DIAS[0])
    assert "escribe CONFIRMO" in pedir(DIAS[0], hora="21:00")


def test_repetir_exactamente_una_reserva_sigue_el_flujo_de_ya_la_tienes(servicio):
    """Con el tope lleno, pedir de nuevo la misma reserva no se rechaza por tope: le dice que ya la tiene,
    con su codigo, y no prepara un resumen que confirmar."""
    reservas = [reservar(dia) for dia in DIAS[:3]]
    rt = SimpleNamespace(context=ContextoConversacion(sesion_id=SESION))
    texto = pedir(DIAS[0], rt=rt)
    assert "Ya tienes una reserva con estos datos" in texto and reservas[0]["id"] in texto
    assert "CONFIRMO" not in texto and "confirmacion_pendiente" not in rt.context.datos
    assert rt.context.datos["operacion_bloqueada"] == texto       # el cierre lo manda tal cual al cliente
    assert autorizacion.confirmar(SESION, "confirmo", servicio)[0] == autorizacion.SIN_RESUMEN_PENDIENTE
    assert len(servicio.buscar_reservas_de(TELEFONO)) == 3


def test_pedir_otra_vez_una_reserva_ya_modificada_no_crea_otra(servicio):
    """Prueba por WhatsApp del 12-oct: reservar, modificar la hora y volver a pedir esa hora preparaba un
    resumen nuevo, y su CONFIRMO creaba otra reserva en el mismo turno."""
    original = reservar(DIAS[0], hora="20:00")
    servicio.modificar_reserva(original["id"], hora="21:00")
    rt = SimpleNamespace(context=ContextoConversacion(sesion_id=SESION))
    texto = pedir(DIAS[0], hora="21:00", rt=rt)
    assert "Ya tienes una reserva con estos datos" in texto and original["id"] in texto
    assert "confirmacion_pendiente" not in rt.context.datos
    assert [r.id for r in servicio.buscar_reservas_de(TELEFONO) if r.estado != "cancelada"] == [original["id"]]


def test_el_turno_que_dejo_una_reserva_modificada_se_puede_volver_a_pedir(servicio):
    """La reserva movida de las 20:00 a las 21:00 ya no ocupa las 20:00: pedirlas crea una reserva nueva."""
    original = reservar(DIAS[0], hora="20:00")
    servicio.modificar_reserva(original["id"], hora="21:00")
    nueva = reservar(DIAS[0], hora="20:00")
    assert nueva["id"] != original["id"] and nueva["hora"] == "20:00"


def test_un_telefono_con_tres_reservas_de_otra_conversacion_no_puede_sumar_otra(servicio):
    """Borrar la cookie o escribir desde otra conversacion no reinicia el contador del telefono."""
    for dia in DIAS[:3]:
        reservar(dia, sesion=OTRA)
    texto = pedir(DIAS[3], sesion=SESION)
    assert texto == tope_de_reservas.NO_SE_PUEDE_CON_ESE_TELEFONO


def test_el_aviso_por_telefono_no_revela_las_reservas_de_otra_conversacion(servicio):
    """Ni codigos ni fechas ni la cantidad: solo que ese telefono no puede sumar otra."""
    for dia in DIAS[:3]:
        reservar(dia, sesion=OTRA)
    texto = pedir(DIAS[3], sesion=SESION)
    assert "R-" not in texto and "3 reservas" not in texto and "reservas activas" not in texto and DIAS[0] not in texto


def test_el_mismo_turno_de_otra_conversacion_con_el_mismo_telefono_tampoco_se_revela(servicio):
    """Con el turno ocupado por otra conversacion se responde lo mismo que con el tope, sin dar el codigo."""
    reservar(DIAS[0], sesion=OTRA)
    texto = pedir(DIAS[0], sesion=SESION, personas=4)
    assert texto == tope_de_reservas.NO_SE_PUEDE_CON_ESE_TELEFONO


def test_otro_telefono_y_otra_conversacion_no_se_ven_afectados(servicio):
    """El tope es de cada conversacion y cada telefono."""
    for dia in DIAS[:3]:
        reservar(dia)
    assert "escribe CONFIRMO" in pedir(DIAS[3], sesion=OTRA, telefono="900000002")


def test_modificar_o_cancelar_no_se_frena_con_el_tope_lleno(servicio):
    """Cancelar una libera lugar: es la salida que el aviso le ofrece al cliente."""
    reservas = [reservar(dia) for dia in DIAS[:3]]
    rt = SimpleNamespace(context=ContextoConversacion(sesion_id=SESION))
    assert "escribe CONFIRMO" in tools.cancelar_reserva.func(reservas[0]["id"], rt)


def test_el_tope_sale_de_una_variable_de_entorno(servicio, monkeypatch):
    """Cambiar CLEMENTE_MAX_RESERVAS_ACTIVAS cambia el tope sin tocar el codigo."""
    monkeypatch.setenv("CLEMENTE_MAX_RESERVAS_ACTIVAS", "1")
    reservar(DIAS[0])
    assert "1 reservas activas" in pedir(DIAS[1])


@pytest.mark.parametrize("valor", ["abc", "", "0", "-2", "2.5"])
def test_un_valor_que_no_sirve_deja_el_tope_en_tres(monkeypatch, valor):
    """Un error al escribir la variable no deja a todos sin poder reservar."""
    monkeypatch.setenv("CLEMENTE_MAX_RESERVAS_ACTIVAS", valor)
    assert tope_de_reservas.maximo() == 3


def test_el_cliente_lee_el_aviso_fijo_y_no_el_texto_del_modelo():
    """El orquestador reemplaza lo que escribio el agente por el aviso del servidor."""
    contexto = ContextoConversacion(sesion_id=SESION)
    aviso = tope_de_reservas.TOPE_ALCANZADO.format(cantidad=3)
    contexto.datos["operacion_bloqueada"] = aviso
    estado = {"sesion_id": SESION, "mensaje": "quiero reservar", "accion": "delegar",
              "respuestas": [{"agente": "reservas", "texto": "Claro, ya te la preparo"}], "contexto": contexto}
    assert grafo._nodo_cierre(estado)["respuesta"] == aviso
