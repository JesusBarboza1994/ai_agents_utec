"""Un pedido que el equipo ya resolvio en Trello no vuelve a bloquear cuando Trello no responde; sin red.

Caso real del 2026-10-12: I-54A4F4 estaba en "Resuelto", Trello no respondio en un turno y el registro local, que
guardaba el estado con que nacio el caso ("abierta"), bloqueo una reserva. Al turno siguiente Trello respondio y
CANCELAR SOLICITUD dijo que no habia nada en espera.
"""
from app.agentes import casos_abiertos
from app.incidencias.servicio_trello import ServicioIncidenciasTrello

SESION = "whatsapp-51999111222"
LISTAS = {"pendiente": "L1", "en atención": "L2", "resuelto": "L4"}


def _pedido_al_equipo(espejo) -> str:
    """Registra en local un pedido de hablar con una persona, como lo deja el orquestador, y devuelve su codigo."""
    return espejo.crear_incidencia(SESION, "[escalado desde orquestador] el cliente pide hablar con una persona", "otro").id


def _trello(espejo, monkeypatch, tarjetas):
    """Servicio de Trello sin red: el tablero tiene esas tarjetas, o falla si `tarjetas` es una excepcion."""
    servicio = ServicioIncidenciasTrello(tablero="Prueba", espejo=espejo)
    monkeypatch.setattr(servicio, "_cargar_tablero",
                        lambda: setattr(servicio, "_listas", LISTAS) or setattr(servicio, "_tablero_id", "T1"))

    def pedir(*_, **__):
        """Devuelve las tarjetas del tablero o lanza el error de red."""
        if isinstance(tarjetas, Exception):
            raise tarjetas
        return tarjetas

    monkeypatch.setattr(servicio, "_pedir", pedir)
    return servicio


def test_un_caso_resuelto_en_trello_sigue_cerrado_si_trello_deja_de_responder(servicio_incidencias, monkeypatch):
    """Primero Trello lo lee en Resuelto; despues no responde y el registro local ya dice cerrada, no abierta."""
    codigo = _pedido_al_equipo(servicio_incidencias)
    resuelto = [{"name": f"{codigo} · otro · pedido", "idList": "L4"}]

    assert _trello(servicio_incidencias, monkeypatch, resuelto).listar_incidencias("abierta") == []
    caido = _trello(servicio_incidencias, monkeypatch, TimeoutError("Trello no responde"))
    assert caido.listar_incidencias("abierta") == []
    assert [c.estado for c in caido.listar_incidencias()] == ["cerrada"]


def test_el_pedido_resuelto_ya_no_bloquea_las_reservas(servicio_incidencias, monkeypatch):
    """El bloqueo por caso abierto lee el registro local: con el estado de Trello guardado, ya no bloquea."""
    codigo = _pedido_al_equipo(servicio_incidencias)
    assert casos_abiertos.caso_de_atencion_abierto(SESION) == codigo

    _trello(servicio_incidencias, monkeypatch, [{"name": f"{codigo} · otro · pedido", "idList": "L4"}]).listar_incidencias()

    assert casos_abiertos.caso_de_atencion_abierto(SESION) is None


def test_un_caso_que_sigue_pendiente_sigue_bloqueando(servicio_incidencias, monkeypatch):
    """Guardar el estado no abre nada de mas: un pedido que sigue en Pendiente sigue contando."""
    codigo = _pedido_al_equipo(servicio_incidencias)
    _trello(servicio_incidencias, monkeypatch, [{"name": f"{codigo} · otro · pedido", "idList": "L1"}]).listar_incidencias()

    assert casos_abiertos.caso_de_atencion_abierto(SESION) == codigo


def test_sin_cambios_no_se_reescribe_el_registro(servicio_incidencias):
    """Si el estado ya es el mismo no se escribe el archivo: cada turno lee Trello y no tiene por que tocar el disco."""
    codigo = _pedido_al_equipo(servicio_incidencias)

    assert servicio_incidencias.actualizar_estados({codigo: "cerrada"}) == 1
    assert servicio_incidencias.actualizar_estados({codigo: "cerrada"}) == 0
    assert servicio_incidencias.actualizar_estados({"I-NOEXISTE": "cerrada"}) == 0
