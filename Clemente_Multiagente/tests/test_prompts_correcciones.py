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
    assert "Revisa el pedido COMPLETO contra el horario cada vez que llega un dato" in plano
    assert "se rechaza con el horario de ese dia y otra opcion, antes de pedir datos" in plano
    assert "ver o cancelar una reserva que ya existe no se rechaza por horario" in plano


def test_el_telefono_del_restaurante_es_el_acordado():
    """El contacto es una sola constante y la ficha la usa."""
    assert TELEFONO_RESTAURANTE == "+51 940070695"
    assert TELEFONO_RESTAURANTE in FICHA_DEL_RESTAURANTE
    assert "555-0142" not in FICHA_DEL_RESTAURANTE


def test_el_panel_del_chat_y_el_catalogo_dan_el_mismo_telefono():
    """El panel lateral de la pagina y el documento del catalogo no pueden contradecir al telefono que da el agente."""
    from pathlib import Path

    app = Path(__file__).resolve().parent.parent / "app"
    panel = (app / "web" / "templates" / "chat.html").read_text(encoding="utf-8")
    catalogo = (app / "agentes" / "rag" / "documentos" / "01_horarios_y_ubicacion.md").read_text(encoding="utf-8")
    for texto in (panel, catalogo):
        assert TELEFONO_RESTAURANTE in texto and "555-0142" not in texto


def test_la_confirmacion_es_solo_confirmo():
    """F6: ya no se pide un "si" previo; se prepara con los datos y la disponibilidad."""
    plano = _plano(PROMPT_RESERVAS)
    assert "esperas el si" not in plano
    assert 'no pidas un "si" previo' in plano


def test_el_acceso_denegado_ofrece_una_salida():
    """F7: no es un callejon sin salida y no revela si la reserva existe."""
    plano = _plano(PROMPT_RESERVAS)
    assert "verificarla con el local" not in plano
    assert "no confirmes ni niegues que esa reserva exista" in plano


def test_pedir_una_persona_tiene_regla_en_reservas_y_en_el_planificador():
    """F8: el orquestador escala directo (escalar_humano); reservas conserva escalar_a_staff como respaldo."""
    plano_reservas = _plano(PROMPT_RESERVAS)
    assert "Si pide hablar con una persona, usa escalar_a_staff con el motivo y un resumen" in plano_reservas
    plano = _plano(PROMPT_PLANIFICADOR)
    assert "pide_humano: pide hablar con una persona" in plano and "escalar_humano: pide_humano sin reclamo" in plano


def test_incidencias_no_promete_anotar_sin_herramienta():
    """F9: no hay herramienta para anotar despues de registrar; la compensacion va en la descripcion."""
    plano = _plano(PROMPT_INCIDENCIAS)
    assert "lo anotas en la incidencia" not in plano and "las anotas en la incidencia" not in plano
    assert "pide hablar con una persona o una compensacion, incluyelo en la descripcion" in plano
    assert "No dices que actualizaste o anotaste algo que ninguna herramienta hizo" in plano


def test_informacion_da_el_contacto_en_vez_de_prometer():
    """F10: sin herramienta para registrar, informacion da telefono y correo."""
    plano = _plano(PROMPT_ORQUESTADOR)
    assert "ofreces consultarlo con el equipo" not in plano
    assert "le das el telefono y el correo" in plano


def test_incidencias_sabe_consultar_un_caso_existente():
    """F11: con el codigo consulta el estado y se detiene, sin registrar otro caso."""
    plano = _plano(PROMPT_INCIDENCIAS)
    assert "consulta su estado y detente: no registres otro caso" in plano


def test_la_voz_es_de_atencion_al_cliente_con_emojis_acotados():
    """Tono pedido por el equipo: calido y tuteando, con un emoji en la mayoria de los mensajes
    (uno como maximo), tambien junto a una alternativa, y nunca en un reclamo."""
    from app.agentes.prompts import VOZ_CLEMENTE
    plano = _plano(VOZ_CLEMENTE)
    assert "atencion al cliente" in plano and "tuteas con respeto" in plano
    assert "Usa un emoji en la mayoria de tus mensajes" in plano
    assert "el emoji acompana la alternativa" in plano
    assert "como maximo un emoji por mensaje" in plano
    # Un reclamo leve se reconoce con un solo emoji triste; uno grave, o una mala noticia sin alternativa, no lleva ninguno.
    assert "reconoces lo ocurrido con un solo 😔" in plano
    assert "Si el reclamo es grave (alergia, salud, seguridad, maltrato)" in plano and "no uses emojis" in plano
    assert "👍 al confirmar algo sencillo" in plano


def test_las_respuestas_directas_del_orquestador_cierran_con_un_emoji():
    """Saludos, gracias y despedidas los contesta el planificador, que no usa VOZ_CLEMENTE: lleva su propia regla."""
    plano = _plano(PROMPT_PLANIFICADOR)
    assert "cierra con un solo emoji al final" in plano
    assert "Un saludo junto a un pedido NO es respuesta directa" in plano


def test_los_textos_fijos_del_servidor_solo_llevan_emoji_donde_se_permite():
    """Los textos que escribe el codigo llevan emoji solo en una lista explicita y nunca mas de uno por texto.

    Resumenes con CONFIRMO, confirmaciones, avisos de pausa y cierre, codigos y errores los escribe el codigo, no el
    modelo. La voz de Clemente pide un emoji en lo positivo o neutro y ninguno en un rechazo, un error o un aviso de
    seguridad: por eso la lista es de nombres de constantes y cualquier otra cadena de agentes, orquestador y servicios
    de comunicacion (salvo los prompts, que nombran los emojis permitidos) falla si lleva uno. La lista no puede quedar
    desactualizada: cada nombre permitido tiene que existir y llevar un emoji."""
    import ast
    import re
    from pathlib import Path

    emoji = re.compile("[\U0001F000-\U0001FAFF☀-➿⭐⭕]")
    raiz = Path(__file__).resolve().parent.parent / "app"
    archivos = [p for p in (raiz / "agentes").rglob("*.py") if p.name != "prompts.py"]
    archivos += list((raiz / "orquestador").rglob("*.py"))
    archivos += list((raiz / "communication" / "services").glob("*.py"))
    prompts_permitidos = {"PROMPT_PLANIFICADOR"}
    con_emoji_permitido = {
        "SOLICITUD_CANCELADA", "SOLICITUD_CANCELADA_CON_CODIGO", "SOLICITUD_EN_RESOLUCION", "PAUSA_SIN_VIGENCIA",
        "SIN_MENSAJE", "ESCALAMIENTO_HUMANO", "ESCALAMIENTO_RESERVA", "ESCALAMIENTO_RESERVA_APROBADA",
        "PEDIDO_AL_EQUIPO_RETIRADO", "ESCALAMIENTO_HUMANO_WEBCHAT",
        "AVISO_REVISION_PENDIENTE", "AVISO_REVISION_PENDIENTE_CON_CODIGO", "SOLICITUD_EN_REVISION",
        "EMOJI_DEL_RESUMEN", "CIERRE_DE_LA_OPERACION", "TEXTO_CIERRE",
        "CIERRE_RECLAMO", "CIERRE_PEDIDO_DE_PERSONA", "CIERRE_CON_RESOLUCION", "TEXTO_VENCIDO",
    }

    def cadenas(nodo):
        """Cada cadena literal dentro de un nodo, con su linea."""
        return [(n.lineno, n.value) for n in ast.walk(nodo) if isinstance(n, ast.Constant) and isinstance(n.value, str)]

    prohibidos, encontrados, de_mas = [], {}, []
    for archivo in archivos:
        arbol = ast.parse(archivo.read_text(encoding="utf-8"))
        permitidas = []
        for nodo in arbol.body:
            if not isinstance(nodo, ast.Assign):
                continue
            nombres = {t.id for t in nodo.targets if isinstance(t, ast.Name)}
            if nombres & prompts_permitidos:
                permitidas += [id(n) for n in ast.walk(nodo)]
            elif nombres & con_emoji_permitido:
                permitidas += [id(n) for n in ast.walk(nodo)]
                for linea, texto in cadenas(nodo):
                    if emoji.search(texto):
                        encontrados[(nombres & con_emoji_permitido).pop()] = True
                    if len(emoji.findall(texto)) > 1:
                        de_mas.append(f"{archivo.relative_to(raiz)}:{linea}")
        for nodo in ast.walk(arbol):
            if id(nodo) in permitidas:
                continue
            if isinstance(nodo, ast.Constant) and isinstance(nodo.value, str) and emoji.search(nodo.value):
                prohibidos.append(f"{archivo.relative_to(raiz)}:{nodo.lineno}")

    assert archivos
    assert not prohibidos, f"emoji fuera de la lista permitida: {prohibidos}"
    assert not de_mas, f"mas de un emoji en un mismo texto: {de_mas}"
    assert set(encontrados) == con_emoji_permitido, f"la lista permitida esta desactualizada: {con_emoji_permitido - set(encontrados)}"


def test_los_rechazos_los_errores_y_la_seguridad_no_llevan_emoji():
    """Un rechazo, un error o un aviso de seguridad se leen sobrios: ninguno de estos textos lleva emoji."""
    import re

    from app.agentes import autorizacion, base, casos_abiertos, tope_de_reservas
    from app.communication.services import aviso_staff_service
    from app.orquestador import grafo

    emoji = re.compile("[\U0001F000-\U0001FAFF☀-➿⭐⭕]")
    sobrios = [
        autorizacion.DENEGADO, autorizacion.RESERVA_REPETIDA_DE_OTRA_CONVERSACION, autorizacion.SIN_RESUMEN_PENDIENTE,
        autorizacion.CODIGO_NO_COINCIDE, autorizacion.RESUMEN_VENCIDO, autorizacion.DEMASIADOS_INTENTOS,
        grafo.NO_SE_PUDO_CANCELAR, grafo.ESCALAMIENTO_HUMANO_FALLIDO, grafo.ESCALAMIENTO_RESERVA_FALLIDO,
        grafo.OFERTA_DIFERIDO, base.RESPALDO_TRAS_LA_REVISION, aviso_staff_service.TEXTO_SALIDA_BLOQUEADA,
        grafo.NO_SE_PUDO_RETIRAR_EL_PEDIDO, grafo.SIN_SOLICITUD_EN_ESPERA,
        autorizacion.OPERACION_YA_PREPARADA, autorizacion.AVISO_OPERACION_APLAZADA,
        casos_abiertos.BLOQUEO_POR_CASO_ABIERTO, tope_de_reservas.TOPE_ALCANZADO, tope_de_reservas.MISMO_TURNO,
        tope_de_reservas.NO_SE_PUEDE_CON_ESE_TELEFONO,
    ]

    assert all(not emoji.search(texto) for texto in sobrios)


def test_el_planificador_conoce_el_horario_y_marca_el_dia_cerrado():
    """F1 en el planificador: recibe el horario y marca la restriccion para la tarea de reservas."""
    plano = _plano(PROMPT_PLANIFICADOR)
    assert HORARIO_DE_ATENCION in PROMPT_PLANIFICADOR
    assert "dia_cerrado o fuera_de_horario" in plano and "SIEMPRE lleva el paso 'reservas'" in plano


def test_reservas_prepara_una_sola_operacion_por_mensaje():
    """Revision de Jean: el prompt pide una operacion por mensaje; el servidor lo hace cumplir aunque el modelo no obedezca."""
    plano = _plano(PROMPT_RESERVAS)
    assert "Una sola operacion por mensaje: no prepares dos a la vez (crear, modificar o cancelar)" in plano
    assert "la otra la haces despues de que la confirme" in plano


def test_reservas_pregunta_por_alergias_en_la_reserva_normal_y_no_en_el_grupo():
    """Revision de Jean: el prompt de informacion dice que la alergia se declara al reservar, asi que reservas la pregunta."""
    plano = _plano(PROMPT_RESERVAS)
    assert "agrega en esa misma frase una pregunta corta (alguna alergia u ocasion especial?)" in plano
    assert "Lo que cuente va en notas" in plano and "Se pregunta una sola vez" in plano
    assert "En los grupos de mas de 8 no se pregunta antes de pedir la excepcion" in plano


def test_reservas_da_el_codigo_al_mostrar_las_reservas():
    """2026-10-12: al pedir su historial el cliente recibia fecha y hora sin el codigo R-, que necesita para cambiarla.

    La regla de no mencionar codigos es solo para el pedido al equipo, cuyo codigo agrega el orquestador."""
    plano = _plano(PROMPT_RESERVAS)
    assert "Al mostrarle sus reservas, da el codigo R- de cada una tal como lo devolvio la herramienta" in plano
    assert "No menciones el codigo de ese pedido: lo agrega el orquestador" in plano
    assert "No menciones codigos:" not in plano
