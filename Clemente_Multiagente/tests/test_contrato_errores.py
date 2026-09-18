"""
Contrato de errores entre tools y el servicio de reservas de Marc (A9 del plan).

`ValueError` es regla de negocio y se traduce como antes. Cualquier otra
excepcion es infraestructura: la tool lo dice tal cual (nunca "sin
disponibilidad" ni "reservado"), lo deja en la traza y no reintenta una
escritura incierta. Sin modelo, sin base real.
"""

import re

from app.agentes import autorizacion, memoria
from app.agentes.contexto import ContextoConversacion
from app.agentes.tools import reservas_tools
from app.contratos import Reserva
from app.observabilidad import trazas


class _RuntimeFalso:
    """Imita lo unico que las tools usan del ToolRuntime que inyecta create_agent."""

    def __init__(self, contexto):
        """Expone el contexto recibido mediante el atributo context que leen las tools."""
        self.context = contexto


class _ServicioCaido:
    """Servicio de reservas cuya infraestructura fallo: toda llamada lanza un error no de negocio."""

    def _caer(self, *_args, **_kwargs):
        """Imita el error de psycopg2 cuando Postgres no responde."""
        raise RuntimeError("OperationalError: could not connect to server")

    consultar_disponibilidad = obtener_reserva = crear_reserva = modificar_reserva = cancelar_reserva = _caer


class _ServicioEscribeMal:
    """Lee bien pero falla al escribir: el caso de la escritura incierta."""

    def consultar_disponibilidad(self, *_args, **_kwargs):
        """Hay mesa: la propuesta se prepara sin problema."""
        return [object()]

    def crear_reserva(self, *_args, **_kwargs):
        """Postgres se cae justo al insertar."""
        raise RuntimeError("OperationalError: connection lost during INSERT")


class _ServicioSinMesa:
    """Regla de negocio: la mesa desaparecio entre el resumen y la confirmacion."""

    def consultar_disponibilidad(self, *_args, **_kwargs):
        """Al preparar todavia habia mesa."""
        return [object()]

    def crear_reserva(self, *_args, **_kwargs):
        """El contrato de Marc: sin mesa es ValueError."""
        raise ValueError("Sin mesas para 2 personas")


DATOS = {"nombre": "Ana", "telefono": "999111222", "fecha": "2026-12-04", "hora": "20:00",
         "personas": 2, "zona": "", "notas": ""}


def test_consultar_disponibilidad_no_confunde_base_caida_con_sin_mesa(monkeypatch):
    """Verifica que consultar disponibilidad no confunde base caida con sin mesa."""
    monkeypatch.setattr(reservas_tools, "servicio_reservas", lambda: _ServicioCaido())
    contexto = ContextoConversacion(sesion_id="web-err-1")

    salida = reservas_tools.consultar_disponibilidad.func(
        fecha="2026-12-04", hora="20:00", personas=2, runtime=_RuntimeFalso(contexto),
    )

    assert salida == autorizacion.NO_DISPONIBLE
    assert "Sin disponibilidad" not in salida
    assert contexto.datos["servicio_reservas"] == {"estado": "no_disponible", "operacion": "consultar_disponibilidad"}
    error = [t for t in trazas.ultimas_trazas(sesion_id="web-err-1") if t.evento == "servicio_error"]
    assert error and "OperationalError" in error[0].detalle["error"]


def test_preparar_con_la_base_caida_no_deja_propuesta():
    """Verifica que preparar con la base caida no deja propuesta."""
    contexto = ContextoConversacion(sesion_id="web-err-2")

    texto = autorizacion.proponer(contexto, "crear", DATOS, _ServicioCaido())

    assert texto == autorizacion.NO_DISPONIBLE
    assert "confirmacion_pendiente" not in contexto.datos
    assert autorizacion.confirmar("web-err-2", "CONFIRMO ABCD1234", _ServicioCaido())[0] == autorizacion.CONFIRMACION_INVALIDA


def test_una_escritura_que_falla_se_informa_incierta_y_no_se_reintenta():
    """El token ya se consumio: repetir el CONFIRMO no vuelve a escribir."""
    servicio = _ServicioEscribeMal()
    texto = autorizacion.proponer(ContextoConversacion(sesion_id="web-err-3"), "crear", DATOS, servicio)
    token = re.search(r"CONFIRMO [0-9A-F]{8}", texto)[0]

    primero = autorizacion.confirmar("web-err-3", token, servicio)
    segundo = autorizacion.confirmar("web-err-3", token, servicio)

    assert primero == (autorizacion.ESCRITURA_INCIERTA, {"operacion_incierta": "crear"})
    assert segundo == (autorizacion.CONFIRMACION_INVALIDA, {})
    assert any(t.evento == "escritura_incierta" for t in trazas.ultimas_trazas(sesion_id="web-err-3"))


def test_una_regla_de_negocio_sigue_siendo_un_rechazo_normal():
    """ValueError del servicio no es infraestructura: mensaje de siempre, sin traza de error."""
    servicio = _ServicioSinMesa()
    texto = autorizacion.proponer(ContextoConversacion(sesion_id="web-err-4"), "crear", DATOS, servicio)
    token = re.search(r"CONFIRMO [0-9A-F]{8}", texto)[0]

    resultado = autorizacion.confirmar("web-err-4", token, servicio)

    assert "la disponibilidad o los datos cambiaron" in resultado[0]
    assert resultado[1] == {}
    assert not any(t.evento in {"servicio_error", "escritura_incierta"} for t in trazas.ultimas_trazas(sesion_id="web-err-4"))


def test_la_ficha_omite_reservas_si_el_servicio_falla_pero_no_tumba_el_turno(monkeypatch):
    """Verifica que la ficha omite reservas si el servicio falla pero no tumba el turno."""
    autorizacion.vincular("web-err-5", "R-XYZ")
    memoria.anotar("web-err-5", "alergia", "mariscos")
    monkeypatch.setattr("app.reservas.obtener_servicio", lambda: _ServicioCaido())

    ficha = memoria.ficha_del_cliente("web-err-5")

    assert "R-XYZ" not in ficha
    assert "mariscos" in ficha


def test_consultar_por_codigo_con_la_base_caida_no_revela_ni_inventa(monkeypatch):
    """Verifica que consultar por codigo con la base caida no revela ni inventa."""
    autorizacion.vincular("web-err-6", "R-PROPIA")
    monkeypatch.setattr(reservas_tools, "servicio_reservas", lambda: _ServicioCaido())

    salida = reservas_tools.consultar_reserva_por_codigo.func(
        reserva_id="r-propia", runtime=_RuntimeFalso(ContextoConversacion(sesion_id="web-err-6")),
    )

    assert salida == autorizacion.NO_DISPONIBLE
