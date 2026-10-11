"""La bandeja del webchat guarda lo que el servidor le dice al cliente sin que este haya escrito; sin modelo ni red.

Cuando el personal decide una solicitud de grupo o cierra el caso en Trello, el navegador de ese cliente tiene que
enterarse solo. Aqui se prueba que cada navegador ve unicamente lo suyo, que el acuse limpia lo ya mostrado, que la
bandeja no crece sin limite y que un archivo roto o un disco que falla nunca interrumpen a quien deposita.
"""
import json

import pytest

from app import create_app
from app.communication.services import bandeja_webchat as bandeja

SESION = "web-aaa111"
OTRA = "web-bbb222"


@pytest.fixture(autouse=True)
def archivo_temporal(monkeypatch, tmp_path):
    """Cada prueba usa su propio archivo de bandeja, nunca el de la carpeta de datos."""
    monkeypatch.setattr(bandeja, "ARCHIVO", tmp_path / "bandeja_webchat.json")


# --- depositar y recoger ---------------------------------------------------------------------

def test_lo_depositado_se_recoge_con_numero_creciente():
    """Los mensajes salen en orden y con un numero que solo sube."""
    primero = bandeja.depositar(SESION, "Tu solicitud G-ABC123 fue aprobada.")
    segundo = bandeja.depositar(SESION, "Tu caso I-ABC123 fue resuelto.")

    recogidos = bandeja.recoger(SESION)

    assert [m["texto"] for m in recogidos] == ["Tu solicitud G-ABC123 fue aprobada.", "Tu caso I-ABC123 fue resuelto."]
    assert [m["id"] for m in recogidos] == [primero, segundo] and primero < segundo
    assert all(m["hora"] for m in recogidos)


def test_cada_navegador_ve_solo_lo_suyo():
    """Un mensaje para una sesion no aparece en la bandeja de otra."""
    bandeja.depositar(SESION, "para el primero")
    bandeja.depositar(OTRA, "para el segundo")

    assert [m["texto"] for m in bandeja.recoger(SESION)] == ["para el primero"]
    assert [m["texto"] for m in bandeja.recoger(OTRA)] == ["para el segundo"]
    assert bandeja.recoger("web-ccc333") == []


def test_sin_acuse_el_mensaje_se_repite():
    """Si el navegador no acuso lo que mostro (por ejemplo, la respuesta se perdio), vuelve a recibirlo."""
    bandeja.depositar(SESION, "aviso")

    assert len(bandeja.recoger(SESION)) == 1
    assert len(bandeja.recoger(SESION)) == 1


def test_el_acuse_borra_lo_mostrado_y_deja_lo_nuevo():
    """`visto` borra hasta ese numero y devuelve solo lo posterior."""
    primero = bandeja.depositar(SESION, "uno")
    bandeja.depositar(SESION, "dos")

    restantes = bandeja.recoger(SESION, visto=primero)

    assert [m["texto"] for m in restantes] == ["dos"]
    assert [m["texto"] for m in bandeja.recoger(SESION)] == ["dos"]


def test_el_acuse_de_una_sesion_no_borra_la_de_otra():
    """Acusar en una sesion deja intacta la bandeja de las demas."""
    ultimo = bandeja.depositar(SESION, "mio")
    bandeja.depositar(OTRA, "ajeno")

    bandeja.recoger(SESION, visto=ultimo)

    assert [m["texto"] for m in bandeja.recoger(OTRA)] == ["ajeno"]


def test_olvidar_vacia_la_bandeja_de_esa_sesion():
    """Al reiniciar la conversacion, sus avisos pendientes desaparecen y los de otros se quedan."""
    bandeja.depositar(SESION, "viejo")
    bandeja.depositar(OTRA, "ajeno")

    bandeja.olvidar(SESION)

    assert bandeja.recoger(SESION) == []
    assert len(bandeja.recoger(OTRA)) == 1


# --- limites y fallos ------------------------------------------------------------------------

def test_cada_sesion_conserva_solo_los_ultimos_mensajes():
    """Una sesion que nunca acusa no llena la bandeja: quedan los ultimos MAXIMO_POR_SESION."""
    for n in range(bandeja.MAXIMO_POR_SESION + 5):
        bandeja.depositar(SESION, f"mensaje {n}")

    textos = [m["texto"] for m in bandeja.recoger(SESION)]

    assert len(textos) == bandeja.MAXIMO_POR_SESION
    assert textos[-1] == f"mensaje {bandeja.MAXIMO_POR_SESION + 4}" and "mensaje 0" not in textos


def test_la_bandeja_conserva_un_numero_acotado_de_sesiones(monkeypatch):
    """Si hay mas sesiones que MAXIMO_SESIONES se descartan las mas antiguas."""
    monkeypatch.setattr(bandeja, "MAXIMO_SESIONES", 3)
    for n in range(5):
        bandeja.depositar(f"web-{n}", "aviso")

    assert bandeja.recoger("web-0") == [] and bandeja.recoger("web-1") == []
    assert all(len(bandeja.recoger(f"web-{n}")) == 1 for n in (2, 3, 4))


def test_un_archivo_roto_no_rompe_y_se_recupera():
    """Con el archivo corrupto se lee como vacio y el siguiente deposito lo reescribe bien."""
    bandeja.ARCHIVO.write_text("{esto no es json", encoding="utf-8")

    assert bandeja.recoger(SESION) == []
    assert bandeja.depositar(SESION, "despues del fallo") is not None
    assert [m["texto"] for m in bandeja.recoger(SESION)] == ["despues del fallo"]


def test_si_no_se_puede_escribir_no_lanza_y_avisa_con_none(monkeypatch):
    """Un disco que falla no interrumpe a quien deposita: devuelve None para que lo sepa."""
    def falla(self, *args, **kwargs):
        """Simula un disco lleno o una carpeta sin permisos al escribir."""
        raise OSError("disco lleno")

    monkeypatch.setattr(type(bandeja.ARCHIVO), "write_text", falla)

    assert bandeja.depositar(SESION, "aviso") is None


def test_el_archivo_queda_como_json_valido():
    """El archivo en disco se puede leer aparte, para quien necesite revisarlo."""
    bandeja.depositar(SESION, "aviso")

    datos = json.loads(bandeja.ARCHIVO.read_text(encoding="utf-8"))

    assert datos["sesiones"][SESION][0]["texto"] == "aviso"


# --- el endpoint que consulta el navegador -----------------------------------------------------

@pytest.fixture
def navegador():
    """Cliente Flask que hace de un navegador con su cookie de sesion ya fijada."""
    app = create_app()
    app.config["TESTING"] = True
    cliente = app.test_client()
    with cliente.session_transaction() as sesion:
        sesion["clemente_sesion"] = SESION
    return cliente


def test_el_endpoint_entrega_solo_los_avisos_de_la_sesion_del_navegador(navegador):
    """La identidad sale de la cookie firmada: un navegador no puede pedir los avisos de otro."""
    bandeja.depositar(SESION, "mio")
    bandeja.depositar(OTRA, "ajeno")

    respuesta = navegador.get("/api/chat/avisos")

    assert respuesta.status_code == 200
    assert [a["texto"] for a in respuesta.get_json()["avisos"]] == ["mio"]


def test_el_endpoint_ignora_una_sesion_enviada_por_el_cliente(navegador):
    """Aunque el cliente mande `sesion_id` en la consulta, solo cuenta la cookie."""
    bandeja.depositar(OTRA, "ajeno")

    respuesta = navegador.get(f"/api/chat/avisos?sesion_id={OTRA}")

    assert respuesta.get_json()["avisos"] == []


def test_el_endpoint_acusa_con_visto(navegador):
    """Con `visto` se borra lo ya mostrado y solo vuelve lo posterior."""
    primero = bandeja.depositar(SESION, "uno")
    bandeja.depositar(SESION, "dos")

    respuesta = navegador.get(f"/api/chat/avisos?visto={primero}")

    assert [a["texto"] for a in respuesta.get_json()["avisos"]] == ["dos"]


@pytest.mark.parametrize("visto", ["abc", "-5", "1.5", ""])
def test_un_visto_invalido_se_trata_como_cero(navegador, visto):
    """Un acuse que no es un numero valido no rompe el endpoint ni borra nada."""
    bandeja.depositar(SESION, "aviso")

    respuesta = navegador.get(f"/api/chat/avisos?visto={visto}")

    assert respuesta.status_code == 200
    assert len(respuesta.get_json()["avisos"]) == 1


def test_un_navegador_nuevo_recibe_una_lista_vacia(navegador):
    """Sin avisos, la respuesta es una lista vacia y no un error."""
    assert navegador.get("/api/chat/avisos").get_json() == {"avisos": []}
