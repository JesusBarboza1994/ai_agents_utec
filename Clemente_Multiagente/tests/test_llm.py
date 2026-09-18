"""
Pruebas de la resolucion de modelo y del registro del turno.

Ninguna llama a una API: solo construyen el cliente y miran que modelo quedo
configurado. Las claves se falsean, para que la suite corra igual en una maquina
sin credenciales.

Todas estas pruebas existen por un error real del 2026-09-08. Vale la pena
contarlo porque explica por que miran cosas que parecen obvias:

`resolver_modelo()` no aceptaba un modelo explicito, asi que el juez de las
evaluaciones -- que calculaba bien su nombre -- construia el modelo leyendo el
`.env` y terminaba siendo **el mismo modelo que estaba evaluando**. Los informes
declaraban `claude-opus-5` como juez y en realidad juzgaba Sonnet a Sonnet: el
sesgo de auto-preferencia contra el que advierte ese mismo informe. Y la
advertencia automatica no saltaba, porque comparaba *nombres*.

De ahi la regla que siguen estas pruebas: **comparar el modelo real, nunca la
etiqueta.**
"""

import json

import pytest

from app.config import Config
from app.llm import modelo_activo, proveedor_de, resolver_modelo


@pytest.fixture(autouse=True)
def credenciales_falsas(monkeypatch):
    """Configura credenciales ficticias para construir modelos sin usar cuentas reales."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "clave-de-prueba")
    monkeypatch.setenv("OPENAI_API_KEY", "clave-de-prueba")


def id_real(cliente) -> str:
    """El modelo con el que quedo configurado el cliente, no el que dice el nombre."""
    return cliente.model_name if hasattr(cliente, "model_name") else cliente.model


def test_terra_es_el_modelo_predeterminado(monkeypatch):
    """README, Config y el constructor deben coincidir incluso sin `.env`."""
    monkeypatch.delenv("AGENT_MODEL", raising=False)
    monkeypatch.delenv("OPENAI_MODEL", raising=False)

    config = Config.desde_entorno()

    assert config.agent_model == "openai"
    assert config.modelo == "gpt-5.6-terra"
    assert modelo_activo() == "gpt-5.6-terra"
    assert id_real(resolver_modelo()) == "gpt-5.6-terra"


# --------------------------------------------------------------------------
# De que casa es cada modelo
# --------------------------------------------------------------------------

@pytest.mark.parametrize("modelo, esperado", [
    ("claude-opus-5", "claude"),
    ("claude-haiku-4-5", "claude"),
    ("gpt-6-astra", "openai"),
    ("gpt-5.6-luna", "openai"),
    ("o3-mini", "openai"),
])
def test_el_proveedor_sale_del_id_del_modelo(modelo, esperado):
    """Verifica que el proveedor sale del id del modelo."""
    assert proveedor_de(modelo) == esperado


def test_un_modelo_inventado_falla_en_vez_de_adivinar():
    """Adivinar la casa equivocada seria mandar la peticion a la API equivocada."""
    with pytest.raises(ValueError):
        proveedor_de("modelo-que-no-existe")


# --------------------------------------------------------------------------
# El modelo explicito gana sobre el .env  (la regresion del juez)
# --------------------------------------------------------------------------

def test_pedir_un_modelo_concreto_ignora_el_env(monkeypatch):
    """
    LA prueba de la regresion. Con el `.env` apuntando a OpenAI, pedir un modelo
    de Anthropic tiene que devolver ese modelo de Anthropic -- no el del `.env`.
    """
    monkeypatch.setenv("AGENT_MODEL", "openai")
    monkeypatch.setenv("OPENAI_MODEL", "gpt-5.6-terra")
    monkeypatch.setenv("ANTHROPIC_MODEL", "claude-sonnet-5")

    assert id_real(resolver_modelo(modelo="claude-opus-5")) == "claude-opus-5"
    assert id_real(resolver_modelo(modelo="gpt-5.6-luna")) == "gpt-5.6-luna"
    # Y sin pedir nada, manda el .env.
    assert id_real(resolver_modelo()) == "gpt-5.6-terra"


def test_el_modelo_del_enrutador_no_pisa_al_modelo_pedido(monkeypatch):
    """Un modelo explicito es una orden, no una preferencia que el rol pueda ganar."""
    monkeypatch.setenv("AGENT_MODEL", "claude")
    monkeypatch.setenv("ANTHROPIC_MODEL", "claude-sonnet-5")
    monkeypatch.setenv("ANTHROPIC_MODEL_ENRUTADOR", "claude-haiku-4-5")

    assert id_real(resolver_modelo(rol="enrutador")) == "claude-haiku-4-5"
    assert id_real(resolver_modelo(rol="enrutador", modelo="claude-opus-5")) == "claude-opus-5"


def _reasoning_effort_de(cliente):
    """Obtiene reasoning_effort del modelo construido para comprobar su configuracion."""
    return cliente.model_kwargs.get("reasoning_effort") or getattr(cliente, "reasoning_effort", None)


def test_los_modelos_gpt56_permiten_herramientas(monkeypatch):
    """
    Regresion del 2026-09-08: los cuatro modelos de OpenAI fallaban 0/17 en el
    banco de modelos, siempre con el mismo error generico del orquestador. La
    causa, reproducida con una sola llamada real: la API rechaza un turno con
    herramientas de funcion si el razonamiento extendido esta activo --

        "Function tools with reasoning_effort are not supported for
         gpt-5.6-terra in /v1/chat/completions. ... or set reasoning_effort
         to 'none'."

    Los tres nodos del proyecto usan herramientas, asi que sin esto NINGUN
    turno con OpenAI llegaba a responder. Aqui se comprueba que el cliente
    queda construido con `reasoning_effort="none"`, sin gastar en una llamada.
    """
    monkeypatch.setenv("AGENT_MODEL", "openai")

    for modelo in ("gpt-5.6-terra", "gpt-5.6-luna", "gpt-5.6-sol"):
        assert _reasoning_effort_de(resolver_modelo(modelo=modelo)) == "none", (
            f"{modelo} deberia construirse con reasoning_effort='none'"
        )

    # Un modelo que no es de razonamiento no debe llevar el parametro: no lo
    # acepta y no lo necesita.
    normal = resolver_modelo(modelo="gpt-4o-mini")
    assert _reasoning_effort_de(normal) is None


def test_gpt6_astra_no_recibe_reasoning_effort_none(monkeypatch):
    """
    Segunda vuelta de la misma regresion, con un giro: mandarle 'none' a
    gpt-6-astra NO lo arregla, lo rompe distinto. La API responde:

        "Unsupported value: 'reasoning_effort' does not support 'none' with
         this model. Supported values are: 'low', 'medium', 'high', 'xhigh'."

    Y probando esos cuatro valores con herramientas, vuelve el error original
    de arriba. Es un limite real de la API (gpt-6 exige razonamiento y no lo
    deja apagar, pero con razonamiento activo no admite tools en este
    endpoint), no algo que un parametro resuelva -- por eso el codigo NO le
    manda 'none': lo deja tal cual, para no reemplazar un error claro por uno
    que despista.
    """
    monkeypatch.setenv("AGENT_MODEL", "openai")

    assert _reasoning_effort_de(resolver_modelo(modelo="gpt-6-astra")) is None


def test_modelo_activo_respeta_el_backend(monkeypatch):
    """
    Con las dos variables definidas en el `.env` -- que es lo normal -- hay que
    devolver la del backend activo. Leer `ANTHROPIC_MODEL or OPENAI_MODEL`
    escribia el modelo equivocado en cada turno del registro.
    """
    monkeypatch.setenv("ANTHROPIC_MODEL", "claude-sonnet-5")
    monkeypatch.setenv("OPENAI_MODEL", "gpt-5.6-terra")

    monkeypatch.setenv("AGENT_MODEL", "openai")
    assert modelo_activo() == "gpt-5.6-terra"
    monkeypatch.setenv("AGENT_MODEL", "claude")
    assert modelo_activo() == "claude-sonnet-5"


def test_el_juez_es_el_modelo_que_dice_ser(monkeypatch):
    """
    El informe declara quien califico. Si el juez declarado y el real no
    coinciden, el informe miente sobre su propia metodologia -- que es lo que
    estuvo pasando hasta el 2026-09-08.
    """
    pytest.importorskip("deepeval")
    from tests.eval.juez import construir_juez, nombre_del_juez

    monkeypatch.setenv("AGENT_MODEL", "openai")       # el evaluado corre en OpenAI
    monkeypatch.setenv("OPENAI_MODEL", "gpt-5.6-terra")
    monkeypatch.setenv("JUEZ_MODEL", "claude-opus-5")  # el juez, en la otra casa

    juez = construir_juez()
    assert juez.get_model_name() == nombre_del_juez() == "claude-opus-5"
    assert id_real(juez.load_model()) == "claude-opus-5"


# --------------------------------------------------------------------------
# El plan queda escrito en el registro del turno
# --------------------------------------------------------------------------

def test_el_registro_del_turno_guarda_el_plan_completo(tmp_path, monkeypatch):
    """
    Un turno atendido por dos agentes tiene que poder distinguirse de uno
    atendido por uno solo despues de reiniciar el servidor. Sin esto, la
    capacidad nueva de la arquitectura no se puede demostrar con datos.
    """
    from app.observabilidad import trazas

    archivo = tmp_path / "conversaciones.jsonl"
    monkeypatch.setattr(trazas, "ARCHIVO_CONVERSACIONES", archivo)

    trazas.registrar_conversacion(
        sesion_id="s-1", mensaje="espere 40 minutos y quiero mesa el sabado",
        respuesta="Lamento la espera... y para el sabado tengo mesa...",
        agente="reservas", motivo_ruta="se queja y ademas pide mesa",
        plan=["incidencias", "reservas"],
    )

    turno = json.loads(archivo.read_text(encoding="utf-8").strip())
    assert turno["plan"] == ["incidencias", "reservas"]
    assert turno["agente"] == "reservas"      # con quien quedo la conversacion


def test_un_turno_de_un_solo_paso_igual_deja_su_plan(tmp_path, monkeypatch):
    """Lista de uno, no lista vacia: que no haya que adivinar si nadie lo anoto."""
    from app.observabilidad import trazas

    archivo = tmp_path / "conversaciones.jsonl"
    monkeypatch.setattr(trazas, "ARCHIVO_CONVERSACIONES", archivo)

    trazas.registrar_conversacion(
        sesion_id="s-2", mensaje="a que hora abren?", respuesta="De 12 a 17.",
        agente="informacion",
    )

    assert json.loads(archivo.read_text(encoding="utf-8").strip())["plan"] == ["informacion"]


# --------------------------------------------------------------------------
# Las metricas cuentan los pasos, no los turnos
# --------------------------------------------------------------------------

def test_las_metricas_cuentan_cada_paso_y_los_turnos_encadenados():
    """
    `pasos_por_agente` se llamaba `ruteos_por_agente` y buscaba un evento
    ("ruteo") que dejo de emitirse al pasar a orquestador: devolvia {} sin que
    nada fallara. Una metrica vacia es peor que una metrica ausente.
    """
    from app.observabilidad import trazas

    trazas.limpiar_trazas() if hasattr(trazas, "limpiar_trazas") else trazas._trazas.clear()
    trazas.registrar("plan", "s-1", agente="incidencias",
                     detalle={"plan": ["incidencias", "reservas"], "motivo": "dos pedidos"})
    trazas.registrar("plan", "s-2", agente="informacion",
                     detalle={"plan": ["informacion"], "motivo": "consulta"})

    m = trazas.metricas()
    assert m["turnos_planificados"] == 2
    assert m["turnos_de_varios_pasos"] == 1
    assert m["pasos_por_agente"] == {"incidencias": 1, "reservas": 1, "informacion": 1}
