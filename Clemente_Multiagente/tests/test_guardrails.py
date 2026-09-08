"""
Guardrail contra la falla de tool-calling de los modelos locales chicos.

Con llama3.2 se reprodujo en la prueba de extremo a extremo: en el segundo
paso de una reserva el modelo escribio {"name": "reservar_mesa", ...} como
texto -- inventando ademas un nombre de tool inexistente. Eso no puede llegar
al cliente.
"""

from app.agentes.base import _parece_llamada_de_tool


def test_detecta_tool_escrita_como_texto():
    assert _parece_llamada_de_tool(
        '{"name": "reservar_mesa", "parameters": {"personas": "4"}}'
    )


def test_detecta_tool_dentro_de_un_bloque_de_codigo():
    assert _parece_llamada_de_tool('```json\n{"tool": "crear_reserva", "arguments": {}}\n```')


def test_una_respuesta_normal_no_es_falso_positivo():
    assert not _parece_llamada_de_tool(
        "Si, hay mesa para 4 el sabado a las 20:00. La reservo a tu nombre?"
    )


def test_un_json_que_no_es_una_tool_no_es_falso_positivo():
    assert not _parece_llamada_de_tool('{"reserva": "R-ABC123", "estado": "confirmada"}')


class _RuntimeFalso:
    """Imita lo unico que las tools usan del ToolRuntime que inyecta create_agent."""

    def __init__(self, contexto):
        self.context = contexto


def test_la_sesion_llega_a_la_tool_por_el_contexto(tmp_path, monkeypatch):
    """
    El sesion_id no se le pide al modelo: viaja en el contexto de ejecucion.

    Regresion del 2026-09-06: con un ContextVar, las tres incidencias quedaron
    con sesion_id "desconocida" porque LangChain corre las tools en otro hilo.
    """
    from app.agentes.contexto import ContextoConversacion
    from app.agentes.tools.incidencias_tools import registrar_incidencia
    from app.incidencias.servicio_json import ServicioIncidenciasJSON

    servicio = ServicioIncidenciasJSON(archivo=tmp_path / "incidencias.json")
    monkeypatch.setattr(
        "app.agentes.tools.incidencias_tools.servicio_incidencias", lambda: servicio
    )

    contexto = ContextoConversacion(sesion_id="whatsapp-51999111222", canal="whatsapp")
    registrar_incidencia.func(
        descripcion="espere 40 minutos", tipo="espera", runtime=_RuntimeFalso(contexto)
    )

    assert servicio.listar_incidencias()[0].sesion_id == "whatsapp-51999111222"


def test_escalar_levanta_la_mano_pero_no_abre_el_ticket():
    """
    Acuerdo 3 de la asesoria del 2026-09-07: ningun agente escala por su cuenta.

    `escalar_a_staff` marca el contexto y deja el motivo; el ticket lo abre el
    orquestador en su nodo de cierre, que es el unico punto de salida. Si esta
    tool volviera a crear la incidencia, habria tantos puntos de escalamiento
    como agentes y ninguno con la conversacion completa.
    """
    from app.agentes.contexto import ContextoConversacion
    from app.agentes.tools.reservas_tools import escalar_a_staff

    contexto = ContextoConversacion(sesion_id="demo-1")
    assert contexto.escalado is False

    escalar_a_staff.func(
        motivo="grupo de 14 personas", detalle="pide el sabado a las 21:00",
        runtime=_RuntimeFalso(contexto),
    )

    assert contexto.escalado is True
    assert contexto.datos["escalamiento"]["origen"] == "reservas"
    assert "14 personas" in contexto.datos["escalamiento"]["motivo"]
    # Lo que NO tiene que haber pasado todavia:
    assert "incidencia" not in contexto.datos


def test_el_cierre_del_orquestador_es_quien_abre_el_ticket(tmp_path, monkeypatch):
    """La otra mitad del Acuerdo 3: el nodo de cierre convierte la senal en ticket."""
    from app.agentes.contexto import ContextoConversacion
    from app.incidencias.servicio_json import ServicioIncidenciasJSON
    from app.orquestador import grafo

    servicio = ServicioIncidenciasJSON(archivo=tmp_path / "incidencias.json")
    monkeypatch.setattr(grafo, "servicio_incidencias", lambda: servicio)

    contexto = ContextoConversacion(sesion_id="demo-1")
    contexto.escalado = True
    contexto.datos["escalamiento"] = {
        "origen": "reservas", "motivo": "grupo de 14 personas",
        "detalle": "pide el sabado a las 21:00",
    }

    final = grafo._nodo_cierre({
        "sesion_id": "demo-1",
        "mensaje": "somos 14 el sabado",
        "contexto": contexto,
        "respuestas": [{"agente": "reservas", "texto": "Lo dejo anotado para el equipo."}],
    })

    creadas = servicio.listar_incidencias()
    assert len(creadas) == 1
    assert creadas[0].tipo == "reserva"
    # El cliente se entera del codigo, y el codigo es el mismo que quedo guardado.
    assert creadas[0].id in final["respuesta"]
    assert contexto.datos["incidencia"]["id"] == creadas[0].id


def test_el_telefono_sale_del_identificador_de_whatsapp():
    """Con WhatsApp el telefono ya lo sabe el sistema: no hay que pedirselo al cliente."""
    from app.agentes.contexto import telefono_de

    assert telefono_de("whatsapp-51999111222") == "51999111222"
    assert telefono_de("web-a1b2c3") is None


def test_la_ficha_recuerda_al_cliente_entre_conversaciones(tmp_path, monkeypatch):
    """Memoria de largo plazo: sobrevive al reinicio y a un sesion_id nuevo."""
    from app.agentes import memoria

    monkeypatch.setattr(memoria, "ARCHIVO", tmp_path / "clientes.json")

    memoria.recordar("whatsapp-956789900", nombre="Christian", telefono="956789900")

    # Otra sesion, otro dia, mismo telefono: el restaurante ya lo conoce.
    ficha = memoria.ficha_del_cliente("whatsapp-956789900")
    assert "Christian" in ficha and "956789900" in ficha
    assert memoria.ficha_del_cliente("web-desconocido") == ""


def test_un_turno_sin_texto_se_contesta_en_vez_de_caerse():
    """
    Regresion del 2026-09-07: al hacer opcionales los campos del estado para
    LangGraph Studio, el enrutador seguia leyendo `estado["mensaje"]` y un
    Submit con el campo vacio tumbaba la corrida con KeyError.

    Ademas no debe llamar al modelo: sin texto no hay nada que clasificar, y
    gastar en eso seria absurdo. Por eso esta prueba corre sin credencial.
    """
    from app.orquestador.grafo import SIN_MENSAJE, obtener_grafo

    for estado in ({}, {"mensaje": "   "}):
        final = obtener_grafo().invoke(estado)
        assert final["respuesta"] == SIN_MENSAJE
        assert final["motivo_ruta"] == "turno sin texto"
