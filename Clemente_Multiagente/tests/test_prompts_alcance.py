"""Las reglas de alcance y de ruteo de los prompts no se pierden sin que un test lo note; sin modelo.

Que el modelo las cumpla se mide con el estres contra el modelo real (material_local/estres_completo.py)
y con el banco de ruteo (tests/eval/evaluar.py): aqui solo se protege que sigan escritas.
"""
import pytest

from app.agentes.prompts import PROMPT_INCIDENCIAS, PROMPT_ORQUESTADOR, PROMPT_RESERVAS
from app.orquestador.grafo import PROMPT_PLANIFICADOR


def _plano(texto):
    """El prompt en una sola linea, para buscar frases sin depender de donde se corta el renglon."""
    return " ".join(texto.split())


@pytest.mark.parametrize("prompt", [PROMPT_ORQUESTADOR, PROMPT_RESERVAS, PROMPT_INCIDENCIAS])
def test_los_tres_agentes_declinan_lo_que_no_es_del_restaurante(prompt):
    """Los tres agentes comparten la regla de alcance (viene en VOZ_CLEMENTE): examenes, codigo, poemas, noticias..."""
    plano = _plano(prompt)
    assert "Tu alcance es solo el restaurante" in plano
    assert "no lo haces ni en parte" in plano
    assert "atiendes el tuyo" in plano


def test_el_agente_de_informacion_no_promete_guardar_datos():
    """Solo reservas e incidencias tienen la herramienta que guarda: informacion no debe decir "tomo nota"."""
    plano = _plano(PROMPT_ORQUESTADOR)
    assert "No guardas datos del cliente" in plano and "nunca digas que anotas" in plano


def test_el_planificador_manda_los_pedidos_de_mesa_y_los_datos_del_cliente_a_reservas():
    """Un pedido de mesa lleva SIEMPRE el paso 'reservas' y un dato del cliente va a quien lo guarda."""
    plano = _plano(PROMPT_PLANIFICADOR)
    assert "SIEMPRE lleva el paso 'reservas'" in plano
    assert "es un dato para su ficha: va a 'reservas'" in plano
    assert "incluso si venia hablando con 'informacion'" in plano
