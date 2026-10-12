"""El correo de contacto del restaurante se muestra al cliente; el correo de una persona se sigue tapando.

Caso real (2026-10-11): Clemente respondio "puedes consultar al equipo al +51 940070695 o [REDACTED_EMAIL]". Las dos
capas de PII (el middleware del agente y la redaccion final del canal) tapaban tambien el correo publico del restaurante.
"""
from pathlib import Path

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from app.agentes import prompts
from app.seguridad import pii

PUBLICO = prompts.CORREO_RESTAURANTE
PRIVADO = "ana.perez@gmail.com"
DOC_CONTACTO = Path(__file__).resolve().parents[1] / "app" / "agentes" / "rag" / "documentos" / "01_horarios_y_ubicacion.md"


def test_la_redaccion_final_deja_el_correo_del_restaurante_y_tapa_el_de_una_persona():
    """Es la que corre sobre cada respuesta antes de mandarla por WhatsApp o el webchat."""
    texto = pii.redactar_pii(f"Escribe a {PUBLICO}; tu correo {PRIVADO} quedo anotado.", incluir_telefono=False)
    assert PUBLICO in texto and PRIVADO not in texto and "[REDACTED_EMAIL]" in texto


def test_el_correo_del_restaurante_se_reconoce_con_mayusculas():
    """El modelo puede escribirlo con mayusculas y sigue siendo el mismo correo."""
    assert "Reservas@Clemente.demo" in pii.redactar_pii("Escribe a Reservas@Clemente.demo")


def test_otro_correo_del_mismo_dominio_se_sigue_tapando():
    """Solo el correo de contacto es publico, no cualquiera que termine en el dominio del restaurante."""
    assert "gerencia@clemente.demo" not in pii.redactar_pii("Escribe a gerencia@clemente.demo")


def test_el_detector_marca_solo_los_correos_privados_con_su_posicion():
    """El middleware reemplaza por posicion: inicio y fin tienen que caer justo sobre el correo."""
    texto = f"{PUBLICO} y {PRIVADO}"
    encontrados = pii.detectar_correos_privados(texto)
    assert [(c["type"], c["value"]) for c in encontrados] == [("email", PRIVADO)]
    assert texto[encontrados[0]["start"]:encontrados[0]["end"]] == PRIVADO


def test_la_respuesta_del_modelo_conserva_el_correo_del_restaurante():
    """El middleware del agente revisa lo que escribe el modelo: el contacto pasa, el de una persona no."""
    middleware = pii.middleware_pii()[0]
    estado = {"messages": [AIMessage(f"Escribe a {PUBLICO} o a {PRIVADO}")]}
    texto = middleware.after_model(estado, None)["messages"][0].content
    assert PUBLICO in texto and PRIVADO not in texto


def test_el_catalogo_y_el_mensaje_del_cliente_pasan_por_el_mismo_criterio():
    """Lo que devuelve el catalogo conserva el contacto; el correo que escribe el cliente se tapa."""
    middleware = pii.middleware_pii()[0]
    llamada = AIMessage("", tool_calls=[{"name": "buscar_catalogo", "args": {}, "id": "t1"}])
    estado = {"messages": [HumanMessage(f"mi correo es {PRIVADO}"), llamada,
                           ToolMessage(f"Contacto: {PUBLICO}", tool_call_id="t1")]}
    mensajes = middleware.before_model(estado, None)["messages"]
    assert PRIVADO not in mensajes[0].content
    assert PUBLICO in mensajes[2].content


def test_el_correo_publico_es_el_mismo_en_el_prompt_el_catalogo_y_la_seguridad():
    """Si alguien cambia el correo en un solo lugar, el nuevo volveria a salir tapado."""
    assert PUBLICO in pii.CORREOS_PUBLICOS
    assert PUBLICO in prompts.FICHA_DEL_RESTAURANTE
    assert PUBLICO in DOC_CONTACTO.read_text(encoding="utf-8")
