"""
Controles conversacionales de la seccion 3.2: plan recortado y auditorias de salida.

Ninguna de estas pruebas llama a un modelo. Lo que se comprueba es la
maquinaria: que un tercer tema no desaparece en silencio, que el cierre lo
dice sin afirmar haberlo resuelto, y que un reinicio o una promesa quedan en
la traza sin bloquear la respuesta.
"""

from app.orquestador import controles, grafo


# --------------------------------------------------------------------------
# Plan sobrecargado
# --------------------------------------------------------------------------

def test_el_tercer_tema_queda_en_pendientes_y_no_se_pierde():
    """Verifica que el tercer tema queda en pendientes y no se pierde."""
    pasos = ["incidencias", "reservas", "informacion"]
    plan = grafo._limpiar_plan(pasos)

    assert plan == ["incidencias", "reservas"]
    assert grafo._pasos_descartados(pasos, plan) == ["informacion"]
    # Repetidos y desconocidos no cuentan como pendientes: no son temas.
    assert grafo._pasos_descartados(["reservas", "reservas", "pedidos"], ["reservas"]) == []


def test_el_cierre_dice_que_quedo_pendiente_sin_afirmar_que_lo_resolvio(tmp_path, monkeypatch):
    """Verifica que el cierre dice que quedo pendiente sin afirmar que lo resolvio."""
    from app.agentes.contexto import ContextoConversacion

    # La sintesis se saltea: aqui interesa lo que el cierre agrega, no el modelo.
    monkeypatch.setattr(grafo, "_sintetizar", lambda respuestas, sesion: " ".join(
        r["texto"] for r in respuestas
    ))
    final = grafo._nodo_cierre({
        "sesion_id": "t-pend", "mensaje": "espere 40 min, quiero mesa y que hay de vegano?",
        "contexto": ContextoConversacion(sesion_id="t-pend"),
        "respuestas": [
            {"agente": "incidencias", "texto": "Anoté tu reclamo."},
            {"agente": "reservas", "texto": "Hay mesa el sábado."},
        ],
        "pendientes": ["informacion"],
    })

    assert final["respuesta"] == (
        "Anoté tu reclamo. Hay mesa el sábado. "
        "Me queda pendiente tu consulta sobre el restaurante: escríbeme sobre eso y lo vemos enseguida."
    )
    assert final["ruta"] == "reservas"


def test_sin_pendientes_el_cierre_no_agrega_nada():
    """Verifica que sin pendientes el cierre no agrega nada."""
    from app.agentes.contexto import ContextoConversacion

    final = grafo._nodo_cierre({
        "sesion_id": "t-nopend", "mensaje": "a que hora abren?",
        "contexto": ContextoConversacion(sesion_id="t-nopend"),
        "respuestas": [{"agente": "informacion", "texto": "Abrimos de martes a domingo."}],
    })

    assert final["respuesta"] == "Abrimos de martes a domingo."


def test_dos_pendientes_se_enumeran_en_una_sola_frase():
    """Verifica que dos pendientes se enumeran en una sola frase."""
    assert grafo._aviso_pendientes(["reservas", "informacion"]) == (
        "Me queda pendiente la reserva y tu consulta sobre el restaurante: "
        "escríbeme sobre eso y lo vemos enseguida."
    )


# --------------------------------------------------------------------------
# Reinicio con saludo generico
# --------------------------------------------------------------------------

def test_un_saludo_con_presentacion_sobre_un_hilo_activo_es_reinicio():
    """Verifica que un saludo con presentacion sobre un hilo activo es reinicio."""
    hilo = [{"role": "user", "content": "quiero mesa el sábado"},
            {"role": "assistant", "content": "Claro, para cuántas personas?"}]

    assert controles.parece_reinicio("¡Hola! Soy Clemente, en qué puedo ayudarte?", hilo)
    assert controles.parece_reinicio("Buenas tardes, bienvenido al restaurante Clemente.", hilo)


def test_un_hola_cortes_no_es_reinicio_por_si_solo():
    """El criterio de aceptacion: no bloquear cualquier 'hola' cortes. Ni contar lo que no lo es."""
    hilo = [{"role": "user", "content": "quiero mesa el sábado"}]

    assert not controles.parece_reinicio("Hola de nuevo, sí, para el sábado somos 4?", hilo)
    assert not controles.parece_reinicio("Para el sábado a las 20:00 tengo mesa.", hilo)
    # Sin hilo previo, presentarse es lo correcto.
    assert not controles.parece_reinicio("¡Hola! Soy Clemente, en qué puedo ayudarte?", [])


# --------------------------------------------------------------------------
# Promesa no autorizada
# --------------------------------------------------------------------------

def test_ofrecer_un_beneficio_se_detecta():
    """Verifica que ofrecer un beneficio se detecta."""
    assert controles.parece_promesa_no_autorizada("Lamento la espera. Te regalamos un postre en tu próxima visita.")
    assert controles.parece_promesa_no_autorizada("Tienes un descuento del 20% por las molestias.")
    assert controles.parece_promesa_no_autorizada("La próxima bebida va por cuenta de la casa.")


def test_negar_o_explicar_que_no_se_puede_no_es_promesa():
    """Verifica que negar o explicar que no se puede no es promesa."""
    assert not controles.parece_promesa_no_autorizada("No puedo ofrecer descuentos; lo anoto para que el restaurante lo evalúe.")
    assert not controles.parece_promesa_no_autorizada("Anoté tu reclamo, te responden en 24 horas.")
    assert not controles.parece_promesa_no_autorizada("Lo siento, no está en mis manos dar una cortesía.")


def test_la_auditoria_registra_pero_no_toca_el_texto(tmp_path, monkeypatch):
    """Verifica que la auditoria registra pero no toca el texto."""
    from app.observabilidad import trazas

    hilo = [{"role": "user", "content": "espere 40 minutos"}]
    texto = "¡Hola! Soy Clemente, en qué puedo ayudarte? Te regalamos un postre."

    eventos = controles.auditar_salida(texto, hilo, "t-aud", "incidencias")

    assert eventos == ["reinicio_detectado", "promesa_no_autorizada"]
    registrados = {t.evento for t in trazas.ultimas_trazas(sesion_id="t-aud")}
    assert {"reinicio_detectado", "promesa_no_autorizada"} <= registrados


def test_el_cierre_audita_la_respuesta_final(tmp_path, monkeypatch):
    """El unico punto de salida es donde se mira lo que el cliente va a leer."""
    from app.agentes.contexto import ContextoConversacion
    from app.observabilidad import trazas

    grafo._nodo_cierre({
        "sesion_id": "t-cierre-aud", "mensaje": "hola",
        "historial": [{"role": "user", "content": "quiero mesa"}],
        "contexto": ContextoConversacion(sesion_id="t-cierre-aud"),
        "respuestas": [{"agente": "reservas", "texto": "¡Hola! Soy Clemente, en qué puedo ayudarte?"}],
    })

    assert any(t.evento == "reinicio_detectado" for t in trazas.ultimas_trazas(sesion_id="t-cierre-aud"))
