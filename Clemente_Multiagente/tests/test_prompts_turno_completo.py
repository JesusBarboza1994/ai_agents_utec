"""Las reglas que hacen que un turno no termine a medias ni repita la excepcion de grupo siguen escritas; sin modelo.

Se midieron con el modelo real: sin ellas el agente de reservas cerraba el turno tras guardar el nombre del cliente
(respuestas vacias o "voy a revisar...") y, con una regla solo a medias, volvia a pedir la excepcion de grupo
despues de que el personal la aprobara. Que el modelo las cumpla se mide con la bateria; aqui solo se protege que
sigan en el prompt.
"""
import pytest

from app.agentes.prompts import PROMPT_INCIDENCIAS, PROMPT_ORQUESTADOR, PROMPT_RESERVAS


def _plano(texto):
    """El prompt en una sola linea, para buscar frases sin depender de donde se corta el renglon."""
    return " ".join(texto.split())


@pytest.mark.parametrize("prompt", [PROMPT_ORQUESTADOR, PROMPT_RESERVAS, PROMPT_INCIDENCIAS])
def test_los_tres_agentes_siguen_tras_el_resultado_de_una_herramienta(prompt):
    """El bloque de decision dice que el turno no termina con la primera herramienta, y el de accion manda volver a decidir."""
    plano = _plano(prompt)

    assert "Elige UNA accion por vuelta" in plano
    assert "no termina con la primera herramienta" in plano
    assert "Despues vuelve a <decide>" in plano


@pytest.mark.parametrize("prompt", [PROMPT_ORQUESTADOR, PROMPT_RESERVAS, PROMPT_INCIDENCIAS])
def test_los_tres_agentes_no_responden_vacio(prompt):
    """El bloque de parada prohibe responder con texto vacio."""
    assert "Nunca respondas con texto vacio" in _plano(prompt)


def test_reservas_no_termina_anunciando_lo_que_va_a_hacer():
    """Una frase como 'voy a revisar la disponibilidad' no es una respuesta: se ejecuta la herramienta o se responde."""
    plano = _plano(PROMPT_RESERVAS)

    assert "solo anuncie lo que vas a hacer" in plano
    assert "o ejecutas la herramienta o respondes con su resultado" in plano


def test_reservas_sigue_tras_guardar_datos_o_consultar_la_disponibilidad():
    """Guardar el nombre del cliente o consultar la disponibilidad no cierra el turno: falta preparar la reserva."""
    plano = _plano(PROMPT_RESERVAS)

    assert "guardar un dato del cliente o consultar la disponibilidad no es el final del turno" in plano
    assert "Datos del cliente actualizados, o disponibilidad consultada: no es el final" in plano


def test_reservas_no_pregunta_la_zona():
    """La zona es opcional: si el cliente no la nombra, va vacia y la herramienta asigna una disponible."""
    assert "No preguntes la zona" in _plano(PROMPT_RESERVAS)


def test_el_planificador_no_confunde_un_grupo_grande_con_pedir_una_persona():
    """'Envialo al equipo' de un grupo de mas de 8 va a reservas (pausa para el personal), no a un reclamo."""
    from app.orquestador.grafo import PROMPT_PLANIFICADOR

    plano = _plano(PROMPT_PLANIFICADOR)

    assert "NO es pide_humano el pedido de mesa de un grupo de mas de 8 personas" in plano
    assert "ese pedido es de 'reservas'" in plano


def test_con_los_cinco_datos_la_excepcion_de_grupo_se_pide_en_ese_turno():
    """Un grupo de mas de 8 con todos los datos pausa en el primer mensaje: sin preguntas previas ni 'ya anote'."""
    plano = _plano(PROMPT_RESERVAS)

    assert "ejecuta solicitar_excepcion_grupo EN ESE MISMO TURNO" in plano
    assert "sin preguntar antes por alergias, ocasion ni zona" in plano
    assert "Nunca digas que quedo anotado o registrado antes de haberla ejecutado" in plano


def test_la_excepcion_de_grupo_se_pide_una_sola_vez():
    """Tras la decision del personal el agente no repite la excepcion (eso producia una segunda interrupcion)."""
    plano = _plano(PROMPT_RESERVAS)

    assert "Se ejecuta UNA sola vez" in plano and "no la repitas" in plano
    assert "El resultado trae la decision del equipo sobre el grupo" in plano
    assert "No vuelvas a ejecutar solicitar_excepcion_grupo ni escalar_a_staff" in plano
    assert "cuando el equipo ya decidio sobre el grupo" in plano
