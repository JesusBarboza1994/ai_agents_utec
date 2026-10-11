"""Solicitudes al staff: prevalidacion antes de encolar y salida para el cliente que espera; sin modelo."""
from datetime import datetime, timezone

import pytest

from app.agentes import fecha
from app.agentes import reservas as agente_reservas
from app.agentes.base import AVISO_REVISION_PENDIENTE
from app.agentes.contexto import ContextoConversacion
from app.contratos import MensajeEntrante
from app.orquestador import grafo

# Martes 2026-10-06 21:00 en Lima.
INSTANTE = datetime(2026, 10, 7, 2, 0, tzinfo=timezone.utc)
SESION = "whatsapp-51999111222"
VALIDA = {"nombre": "Ana Ruiz", "telefono": "999111222", "fecha": "2026-10-10",
          "hora": "20:00", "personas": 12, "dia_semana": "sabado"}


@pytest.fixture(autouse=True)
def reloj_fijo(monkeypatch):
    """Fija el reloj de Lima para que las fechas no dependan del dia en que se corre la suite."""
    monkeypatch.setattr(fecha, "_reloj", lambda: INSTANTE)


@pytest.fixture
def hilos(monkeypatch):
    """Reemplaza el checkpoint de reservas por un registro en memoria de hilos pausados."""
    estado = {"pausados": set(), "borrar_falla": False, "borrados": []}

    def liberar(sesion_id):
        """Borra el hilo simulado, o falla si la prueba lo pide."""
        if estado["borrar_falla"]:
            return False
        estado["pausados"].discard(sesion_id)
        estado["borrados"].append(sesion_id)
        return True

    monkeypatch.setattr(agente_reservas, "liberar_pausa", liberar)
    monkeypatch.setattr(agente_reservas, "tiene_hilo_guardado", lambda sid: sid in estado["pausados"])
    return estado


def solicitud(**cambios):
    """Interrupcion de HITL como la arma LangChain, con los argumentos de la excepcion."""
    return {"action_requests": [{"name": "solicitar_excepcion_grupo", "args": {**VALIDA, **cambios},
                                 "description": "Revisar"}]}


def contexto_pausado(**cambios):
    """Contexto de un turno en el que el agente pidio una excepcion de grupo."""
    contexto = ContextoConversacion(sesion_id=SESION)
    contexto.datos["revision_humana"] = {"estado": "pendiente", "flujo": "reservas",
                                         "solicitud": solicitud(**cambios)}
    return contexto


# --- prevalidacion de la excepcion de grupo ---------------------------------------

@pytest.mark.parametrize("cambios, fragmento", [
    ({"fecha": "2026-10-12", "dia_semana": "lunes"}, "no atiende"),
    ({"fecha": "2026-10-11", "dia_semana": "domingo"}, "no atiende"),
    ({"fecha": "2026-10-05", "dia_semana": "lunes"}, "ya pasó"),
    ({"fecha": "2027-06-01", "dia_semana": ""}, "30 días"),
    ({"hora": "03:00"}, "turnos"),
    ({"dia_semana": "viernes"}, "no coincide"),
    ({"personas": 6}, "no hace falta"),
    ({"telefono": ""}, "teléfono"),
    ({"nombre": "<script>"}, "nombre"),
])
def test_la_excepcion_invalida_tiene_un_motivo(cambios, fragmento):
    """Cada control propio de una excepcion devuelve un texto para el cliente."""
    assert fragmento in agente_reservas._motivo_rechazo_excepcion({**VALIDA, **cambios})


def test_una_excepcion_valida_no_tiene_motivo():
    """Un grupo de 12 un sabado a las 20:00, con nombre y telefono, pasa al staff."""
    assert agente_reservas._motivo_rechazo_excepcion(VALIDA) is None


def test_mas_de_diez_personas_no_lo_frena_la_validacion_ordinaria():
    """La excepcion no usa el tope de 1 a 10 personas del flujo normal."""
    assert agente_reservas._motivo_rechazo_excepcion({**VALIDA, "personas": 25}) is None


def test_la_solicitud_invalida_no_llega_al_staff(hilos):
    """Se libera la pausa, se quita la revision del contexto y no queda ningun escalamiento."""
    hilos["pausados"].add(SESION)
    contexto = contexto_pausado(fecha="2026-10-12", dia_semana="lunes")
    contexto.escalado = True
    contexto.datos["escalamiento"] = {"origen": "reservas", "motivo": "grupo"}
    texto = agente_reservas._descartar_excepcion_invalida(SESION, contexto)
    assert "no atiende" in texto
    assert "revision_humana" not in contexto.datos
    assert not contexto.escalado and "escalamiento" not in contexto.datos
    assert SESION not in hilos["pausados"]


def test_la_solicitud_valida_queda_para_el_staff(hilos):
    """Una solicitud valida no se toca: sigue pendiente para aprobar o rechazar."""
    hilos["pausados"].add(SESION)
    contexto = contexto_pausado()
    assert agente_reservas._descartar_excepcion_invalida(SESION, contexto) is None
    assert contexto.datos["revision_humana"]["estado"] == "pendiente"
    assert SESION in hilos["pausados"]


def test_si_no_se_puede_borrar_la_pausa_se_encola_como_siempre(hilos):
    """Con el estado incierto no se anuncia nada: decide el staff, como hoy."""
    hilos["pausados"].add(SESION)
    hilos["borrar_falla"] = True
    contexto = contexto_pausado(fecha="2026-10-12", dia_semana="lunes")
    assert agente_reservas._descartar_excepcion_invalida(SESION, contexto) is None
    assert contexto.datos["revision_humana"]["estado"] == "pendiente"


@pytest.mark.parametrize("forma", [
    None, {}, {"action_requests": []},
    {"action_requests": [{"name": "otra_herramienta", "args": {}}]},
    {"action_requests": [{"name": "solicitar_excepcion_grupo", "args": "texto"}]},
])
def test_una_forma_inesperada_no_se_prevalida(hilos, forma):
    """Si la interrupcion no tiene la forma conocida, se encola tal cual y el panel la muestra completa."""
    contexto = ContextoConversacion(sesion_id=SESION)
    contexto.datos["revision_humana"] = {"estado": "pendiente", "solicitud": forma}
    assert agente_reservas._descartar_excepcion_invalida(SESION, contexto) is None


def test_varias_solicitudes_con_una_invalida_se_descartan_todas(hilos):
    """Varios pedidos en la misma pausa no es una forma soportada: si uno es invalido, no pasa ninguno."""
    hilos["pausados"].add(SESION)
    contexto = contexto_pausado()
    contexto.datos["revision_humana"]["solicitud"]["action_requests"].append(
        {"name": "solicitar_excepcion_grupo", "args": {**VALIDA, "fecha": "2026-10-12", "dia_semana": "lunes"}})
    assert "no atiende" in agente_reservas._descartar_excepcion_invalida(SESION, contexto)


def test_responder_devuelve_el_motivo_en_vez_del_aviso_de_revision(hilos, monkeypatch):
    """El agente pidio la excepcion para un lunes: el cliente recibe el motivo, no "en revision"."""
    def ejecutar_falso(agente, texto, sesion_id, historial=None, contexto=None, **kwargs):
        """Simula que el modelo llamo a solicitar_excepcion_grupo y LangChain pauso el hilo."""
        hilos["pausados"].add(sesion_id)
        contexto.datos["revision_humana"] = {"estado": "pendiente", "flujo": "reservas",
                                             "solicitud": solicitud(fecha="2026-10-12", dia_semana="lunes")}
        return "La solicitud necesita revisión del equipo del restaurante."

    monkeypatch.setattr(agente_reservas, "ejecutar", ejecutar_falso)
    monkeypatch.setattr(agente_reservas, "obtener_agente", lambda: object())
    contexto = ContextoConversacion(sesion_id=SESION)
    texto = agente_reservas.responder("somos 12 el lunes", SESION, [], contexto=contexto)
    assert "no atiende" in texto and "revision_humana" not in contexto.datos


# --- salida para el cliente que espera al staff -------------------------------------

def turno(texto, canal="whatsapp"):
    """Atiende un turno completo del orquestador, sin limites de frecuencia."""
    return grafo._responder_turno(MensajeEntrante(sesion_id=SESION, texto=texto, canal=canal))


def encolar(**extra):
    """Deja una solicitud en la cola del staff, como si la hubiera pausado el agente."""
    grafo._revisiones[SESION] = {"sesion_id": SESION, "contexto": None,
                                 "solicitud": solicitud(), "canal": "whatsapp", **extra}


def grafo_en_pausa(monkeypatch):
    """Simula el grafo de un turno cuyo hilo de reservas seguia pausado."""
    class Grafo:
        """Grafo minimo que responde el aviso de revision pendiente."""

        def invoke(self, estado):
            """Marca el contexto como hace ejecutar() con un hilo pausado."""
            estado["contexto"].datos["hilo_en_revision"] = True
            return {**estado, "respuesta": AVISO_REVISION_PENDIENTE, "ruta": "reservas",
                    "motivo_ruta": "continuidad"}

    monkeypatch.setattr(grafo, "obtener_grafo", lambda: Grafo())


def test_el_aviso_de_pausa_ofrece_la_salida():
    """Quien espera al staff sabe como retirar su solicitud."""
    assert "CANCELAR SOLICITUD" in AVISO_REVISION_PENDIENTE


@pytest.mark.parametrize("texto", ["CANCELAR SOLICITUD", "cancelar solicitud", "  Cancelar Solicitud. "])
def test_el_comando_se_reconoce_exacto(texto):
    """El comando ignora mayusculas, espacios y un punto final."""
    assert grafo._es_cancelar_solicitud(texto)


@pytest.mark.parametrize("texto", ["cancelar reserva", "quiero cancelar solicitud ya", "cancelar"])
def test_otras_frases_no_son_el_comando(texto):
    """Cancelar una reserva u otras frases siguen el flujo normal."""
    assert not grafo._es_cancelar_solicitud(texto)


def test_cancelar_solicitud_libera_el_hilo_y_vacia_la_cola(hilos):
    """El cliente retira su solicitud sin pasar por el modelo."""
    hilos["pausados"].add(SESION)
    encolar(creada=0)
    respuesta = turno("CANCELAR SOLICITUD")
    assert respuesta.texto == grafo.SOLICITUD_CANCELADA
    assert SESION not in grafo._revisiones and SESION not in hilos["pausados"]


def test_cancelar_solicitud_libera_una_pausa_huerfana(hilos):
    """Si la solicitud ya no esta en la cola pero el hilo sigue pausado, el comando igual lo libera."""
    hilos["pausados"].add(SESION)
    assert turno("CANCELAR SOLICITUD").texto == grafo.SOLICITUD_CANCELADA
    assert SESION not in hilos["pausados"]


def test_cancelar_sin_nada_pendiente_sigue_el_flujo_normal(hilos, monkeypatch):
    """Sin solicitud ni pausa, el comando no hace nada especial y responde el grafo."""
    llamado = {}

    class Grafo:
        """Grafo minimo que anota que fue invocado."""

        def invoke(self, estado):
            """Responde algo fijo."""
            llamado["si"] = True
            return {**estado, "respuesta": "flujo normal", "ruta": "informacion", "motivo_ruta": "x"}

    monkeypatch.setattr(grafo, "obtener_grafo", lambda: Grafo())
    assert turno("CANCELAR SOLICITUD").texto == "flujo normal" and llamado


def test_cancelar_mientras_el_staff_resuelve_no_toca_nada(hilos):
    """Si el staff ya tomo la solicitud, el hilo no se borra durante su reanudacion."""
    hilos["pausados"].add(SESION)
    grafo._resolviendo.add(SESION)
    try:
        assert turno("CANCELAR SOLICITUD").texto == grafo.SOLICITUD_EN_RESOLUCION
        assert SESION in hilos["pausados"]
    finally:
        grafo._resolviendo.discard(SESION)


def test_si_falla_el_borrado_no_se_anuncia_la_cancelacion(hilos):
    """La solicitud queda en la cola y el cliente sabe que no se cancelo."""
    hilos["pausados"].add(SESION)
    hilos["borrar_falla"] = True
    encolar(creada=0)
    assert turno("CANCELAR SOLICITUD").texto == grafo.NO_SE_PUDO_CANCELAR
    assert SESION in grafo._revisiones


def test_una_pausa_huerfana_se_libera_al_escribir(hilos, monkeypatch):
    """El caso de la captura: el hilo esperaba una decision que ya no estaba en la cola."""
    hilos["pausados"].add(SESION)
    grafo_en_pausa(monkeypatch)
    respuesta = turno("quiero hacer otra reserva")
    assert respuesta.texto == grafo.PAUSA_SIN_VIGENCIA
    assert SESION not in hilos["pausados"]


def test_una_pausa_vencida_se_libera_al_escribir(hilos, monkeypatch):
    """Pasado el plazo sin decision del staff, la solicitud se cierra y sale de la cola."""
    import time
    hilos["pausados"].add(SESION)
    encolar(creada=time.time() - grafo.VENCIMIENTO_REVISION_SEGUNDOS - 1)
    grafo_en_pausa(monkeypatch)
    assert turno("hola?").texto == grafo.PAUSA_SIN_VIGENCIA
    assert SESION not in grafo._revisiones


def test_una_pausa_vigente_sigue_esperando_al_staff(hilos, monkeypatch):
    """Dentro del plazo, el cliente sigue recibiendo el aviso con la salida."""
    import time
    hilos["pausados"].add(SESION)
    encolar(creada=time.time())
    grafo_en_pausa(monkeypatch)
    assert turno("hola?").texto == AVISO_REVISION_PENDIENTE
    assert SESION in grafo._revisiones and SESION in hilos["pausados"]


def test_una_solicitud_sin_fecha_de_creacion_empieza_a_contar_ahora(hilos, monkeypatch):
    """Las solicitudes guardadas antes de este cambio no vencen de golpe: se les pone la hora actual."""
    hilos["pausados"].add(SESION)
    encolar()
    grafo_en_pausa(monkeypatch)
    assert turno("hola?").texto == AVISO_REVISION_PENDIENTE
    assert "creada" in grafo._revisiones[SESION]


def test_el_reinicio_libera_tambien_la_pausa(hilos):
    """Reiniciar la sesion ya no deja el hilo esperando una decision que nadie puede tomar."""
    hilos["pausados"].add(SESION)
    encolar(creada=0)
    grafo.olvidar_sesion(SESION)
    assert SESION not in grafo._revisiones and SESION not in hilos["pausados"]


def test_una_revision_nueva_guarda_su_hora(hilos, monkeypatch):
    """Al encolar una solicitud se registra cuando se creo, para poder vencerla."""
    class Grafo:
        """Grafo minimo cuyo agente dejo una revision pendiente valida."""

        def invoke(self, estado):
            """Deja la revision en el contexto como hace ejecutar()."""
            estado["contexto"].datos["revision_humana"] = {"estado": "pendiente", "solicitud": solicitud()}
            return {**estado, "respuesta": "en revision", "ruta": "reservas", "motivo_ruta": "x"}

    monkeypatch.setattr(grafo, "obtener_grafo", lambda: Grafo())
    turno("somos 12 el sabado a las 8")
    assert isinstance(grafo._revisiones[SESION]["creada"], float)
