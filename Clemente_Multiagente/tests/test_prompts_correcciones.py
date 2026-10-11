"""Correcciones puntuales de los prompts (revision de Christian, F1 y F6 a F11): siguen escritas; sin modelo."""
from app.agentes import fecha
from app.agentes.prompts import (
    FICHA_DEL_RESTAURANTE, HORARIO_DE_ATENCION, PROMPT_INCIDENCIAS, PROMPT_ORQUESTADOR,
    PROMPT_RESERVAS, TELEFONO_RESTAURANTE,
)
from app.orquestador.grafo import PROMPT_PLANIFICADOR


def _plano(texto):
    """El prompt en una sola linea, para buscar frases sin depender de donde se corta el renglon."""
    return " ".join(texto.split())


def test_el_horario_de_los_prompts_sale_de_la_misma_tabla_que_las_validaciones():
    """F1: la ficha y reservas muestran el horario de fecha.HORARIO, no uno escrito a mano."""
    assert fecha.texto_horario() in FICHA_DEL_RESTAURANTE
    assert HORARIO_DE_ATENCION in PROMPT_RESERVAS
    assert "el domingo, solo 12:00, 13:00 y 14:00" in HORARIO_DE_ATENCION


def test_reservas_revisa_el_horario_antes_de_pedir_datos():
    """F1: el horario se aplica a reservas nuevas y cambios, no a ver o cancelar."""
    plano = _plano(PROMPT_RESERVAS)
    assert "ANTES de pedir datos" in plano
    assert "Ver o cancelar una reserva que ya existe no se rechaza por horario" in plano


def test_el_telefono_del_restaurante_es_el_acordado():
    """El contacto es una sola constante y la ficha la usa."""
    assert TELEFONO_RESTAURANTE == "+51 940070695"
    assert TELEFONO_RESTAURANTE in FICHA_DEL_RESTAURANTE
    assert "555-0142" not in FICHA_DEL_RESTAURANTE


def test_la_confirmacion_es_solo_confirmo():
    """F6: ya no se pide un "si" previo; se prepara con los datos y la disponibilidad."""
    plano = _plano(PROMPT_RESERVAS)
    assert "esperas el si" not in plano
    assert 'No pidas un "si" previo' in plano


def test_el_acceso_denegado_ofrece_una_salida():
    """F7: no es un callejon sin salida y no revela si la reserva existe."""
    plano = _plano(PROMPT_RESERVAS)
    assert "verificarla con el local" not in plano
    assert "no confirmes ni niegues que esa reserva exista" in plano


def test_pedir_una_persona_tiene_regla_en_reservas_y_en_el_planificador():
    """F8: el orquestador escala directo (escalar_humano); reservas conserva escalar_a_staff como respaldo."""
    assert "pide hablar con una persona del restaurante, llamas a `escalar_a_staff`" in _plano(PROMPT_RESERVAS)
    plano = _plano(PROMPT_PLANIFICADOR)
    assert "pide_humano: pide hablar con una persona" in plano and "escalar_humano: pide_humano sin reclamo" in plano


def test_incidencias_no_promete_anotar_sin_herramienta():
    """F9: no hay herramienta para anotar despues de registrar; la compensacion va en la descripcion."""
    plano = _plano(PROMPT_INCIDENCIAS)
    assert "lo anotas en la incidencia" not in plano and "las anotas en la incidencia" not in plano
    assert "la incluyes en la descripcion al llamar a registrar_incidencia" in plano


def test_informacion_da_el_contacto_en_vez_de_prometer():
    """F10: sin herramienta para registrar, informacion da telefono y correo."""
    plano = _plano(PROMPT_ORQUESTADOR)
    assert "ofreces consultarlo con el equipo" not in plano
    assert "le das el telefono y el correo" in plano


def test_incidencias_sabe_consultar_un_caso_existente():
    """F11: con el codigo consulta el estado y se detiene, sin registrar otro caso."""
    plano = _plano(PROMPT_INCIDENCIAS)
    assert "`consultar_incidencia`" in plano and "no registras otro caso" in plano


def test_el_planificador_conoce_el_horario_y_marca_el_dia_cerrado():
    """F1 en el planificador: recibe el horario y marca la restriccion para la tarea de reservas."""
    plano = _plano(PROMPT_PLANIFICADOR)
    assert HORARIO_DE_ATENCION in PROMPT_PLANIFICADOR
    assert "dia_cerrado o fuera_de_horario" in plano and "SIEMPRE lleva el paso 'reservas'" in plano
