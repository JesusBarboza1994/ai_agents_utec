"""Orquestacion acotada (bloque C): plan con tareas, coordinacion, control de estado y cierre; sin modelo."""
import json

import pytest

from app.agentes import base
from app.agentes.contexto import ContextoConversacion
from app.contratos import MensajeEntrante
from app.incidencias import obtener_servicio as servicio_incidencias
from app.orquestador import grafo

SESION = "whatsapp-51999111222"


class ModeloFalso:
    """Modelo minimo del planificador: devuelve la decision indicada y guarda lo que recibio."""

    def __init__(self, decision=None, error=None):
        """Guarda la decision a devolver o el error a lanzar."""
        self.decision, self.error, self.entrada = decision, error, None

    def with_structured_output(self, esquema):
        """Como LangChain: devuelve un ejecutable que responde con el esquema pedido."""
        return self

    def invoke(self, mensajes):
        """Anota el ultimo mensaje y devuelve la decision (o lanza el error)."""
        self.entrada = mensajes[-1].content
        if self.error:
            raise self.error
        return self.decision


def planificar(monkeypatch, decision=None, error=None, **estado):
    """Corre el nodo planificador con un modelo falso y devuelve (salida, modelo)."""
    modelo = ModeloFalso(decision, error)
    monkeypatch.setattr(grafo, "resolver_modelo", lambda **kwargs: modelo)
    base_estado = {"sesion_id": SESION, "mensaje": "hola", "historial": [],
                   "contexto": ContextoConversacion(sesion_id=SESION)}
    return grafo._nodo_planificador({**base_estado, **estado}), modelo


def plan(**campos):
    """PlanDeResolucion con pasos y motivo por defecto."""
    return grafo.PlanDeResolucion(**{"pasos": [], "motivo": "prueba", **campos})


# --- esquema del planificador --------------------------------------------------------

def _defaults(esquema):
    """Recorre el esquema JSON y devuelve los valores por defecto que sobreviven."""
    encontrados = []
    if isinstance(esquema, dict):
        if "default" in esquema:
            encontrados.append(esquema["default"])
        for valor in esquema.values():
            encontrados += _defaults(valor)
    elif isinstance(esquema, list):
        for valor in esquema:
            encontrados += _defaults(valor)
    return encontrados


def test_el_esquema_estricto_no_lleva_valores_por_defecto():
    """Azure usa salida estricta: un default distinto de None podria hacer fallar al planificador en cada turno."""
    from openai.lib._pydantic import to_strict_json_schema
    esquema = to_strict_json_schema(grafo.PlanDeResolucion)
    assert _defaults(esquema) == []
    assert set(esquema["required"]) == set(esquema["properties"])


def test_el_plan_de_siempre_se_sigue_pudiendo_construir():
    """Codigo y pruebas que arman PlanDeResolucion(pasos, motivo) no cambian."""
    decision = grafo.PlanDeResolucion(pasos=["reservas"], motivo="x")
    assert decision.tareas is None and decision.accion is None


# --- normalizacion de pasos y tareas -----------------------------------------------

@pytest.mark.parametrize("pasos, tareas, esperado", [
    (["incidencias", "reservas"], ["reclamo", "mesa"], [("incidencias", "reclamo"), ("reservas", "mesa")]),
    (["reservas", "reservas", "informacion"], ["a", "b", "c"], [("reservas", "a"), ("informacion", "c")]),
    (["informacion", "reservas"], ["solo una"], [("informacion", "solo una"), ("reservas", "")]),
    (["reservas"], ["a", "sobra"], [("reservas", "a")]),
    (["incidencias", "reservas", "informacion"], ["1", "2", "3"], [("incidencias", "1"), ("reservas", "2")]),
    (["reservas"], None, [("reservas", "")]),
])
def test_cada_tarea_se_queda_con_su_paso(pasos, tareas, esperado):
    """Descartar repetidos o recortar el plan nunca le pasa a un componente la tarea de otro."""
    assert grafo._normalizar_pasos(pasos, tareas) == esperado


def test_limpiar_plan_sigue_igual():
    """La funcion de siempre no cambia: tiene pruebas propias y otros la usan."""
    assert grafo._limpiar_plan(["reservas", "reservas"]) == ["reservas"]


# --- planificador ------------------------------------------------------------------

def test_delegar_deja_las_tareas_alineadas_y_la_traza(monkeypatch):
    """Las tareas viajan en el estado junto a su paso, y el razonamiento queda en la traza."""
    from app.observabilidad import trazas
    salida, _ = planificar(monkeypatch, plan(
        pasos=["incidencias", "reservas"], tareas=["reclamo por la espera", "mesa para el sabado"],
        entendimiento="reclamo y reserva", restricciones=["reclamo"], accion="delegar"))
    assert salida["plan"] == ["incidencias", "reservas"]
    assert salida["tareas"] == ["reclamo por la espera", "mesa para el sabado"]
    traza = [t for t in trazas.ultimas_trazas(10) if t.evento == "plan"][-1]
    assert traza.detalle["entendimiento"] == "reclamo y reserva"


def test_el_planificador_recibe_calendario_y_tarea_ofrecida(monkeypatch):
    """La entrada lleva la fecha de Lima, los proximos dias y lo ofrecido el turno anterior."""
    _, modelo = planificar(monkeypatch, plan(pasos=["reservas"]),
                           tarea_ofrecida={"agente": "reservas", "tarea": "mesa para 2 el jueves"})
    assert "Proximos dias:" in modelo.entrada
    assert "Tarea ofrecida en el turno anterior: reservas -- mesa para 2 el jueves" in modelo.entrada


def test_escalar_humano_no_llama_a_ningun_agente_y_marca_el_escalamiento(monkeypatch):
    """El pedido de hablar con una persona lo resuelve el orquestador: el cierre abrira el ticket."""
    salida, _ = planificar(monkeypatch, plan(accion="escalar_humano", entendimiento="pide una persona"))
    assert salida["plan"] == [] and salida["accion"] == "escalar_humano"
    contexto = salida["contexto"]
    assert contexto.escalado and contexto.datos["escalamiento"]["origen"] == "orquestador"


def test_responder_directo_sin_texto_se_atiende_como_consulta(monkeypatch):
    """Si el modelo elige responder directo pero no escribe nada, el turno no queda vacio."""
    salida, _ = planificar(monkeypatch, plan(accion="responder_directo", respuesta_directa=""))
    assert salida["accion"] == "delegar" and salida["plan"] == ["informacion"]


def test_un_segundo_paso_dependiente_se_ofrece_y_no_se_ejecuta(monkeypatch):
    """La condicion no se acredita en codigo: el paso dependiente queda diferido."""
    salida, _ = planificar(monkeypatch, plan(
        pasos=["informacion", "reservas"], tareas=["veganas?", "mesa para 2 el jueves"],
        depende_del_anterior=True, accion="delegar"))
    assert salida["plan"] == ["informacion"]
    assert salida["diferido"] == {"agente": "reservas", "tarea": "mesa para 2 el jueves"}


def test_aceptar_lo_ofrecido_recupera_la_tarea_guardada(monkeypatch):
    """Si el cliente dice "si" y el modelo no copia la tarea, se usa la que se guardo."""
    salida, _ = planificar(monkeypatch, plan(pasos=["reservas"], accion="delegar"), mensaje="si",
                           tarea_ofrecida={"agente": "reservas", "tarea": "mesa para 2 el jueves"})
    assert salida["tareas"] == ["mesa para 2 el jueves"]


def test_si_el_planificador_falla_se_usa_el_respaldo_sin_tarea(monkeypatch):
    """Un error del modelo no tumba el turno: va al agente que venia atendiendo, como antes."""
    salida, _ = planificar(monkeypatch, error=RuntimeError("caido"), ultimo_agente="reservas")
    assert salida["plan"] == ["reservas"] and salida["tareas"] == [""]
    assert salida["motivo_ruta"] == "fallback por error de planificacion"


# --- coordinacion y control de estado ----------------------------------------------

def test_sin_tareas_no_hay_coordinacion():
    """En el respaldo o con un plan sin tareas, el turno corre exactamente como antes."""
    assert grafo._coordinacion_del_paso({"tareas": [""], "restricciones": ["reclamo"]}, 0) == ""


def test_la_coordinacion_lleva_tarea_datos_restricciones_y_respuesta_previa():
    """El segundo paso recibe tambien lo que respondio el primero, rotulado como dato."""
    estado = {"tareas": ["reclamo", "mesa para 10"], "restricciones": ["dia_cerrado"],
              "datos_resueltos": {"fecha": "2026-10-12", "dia": "lunes", "personas": 10},
              "respuestas": [{"agente": "incidencias", "texto": "Registre tu reclamo."}]}
    texto = grafo._coordinacion_del_paso(estado, 1)
    assert "Tarea: mesa para 10" in texto
    assert "fecha 2026-10-12 (lunes), personas 10" in texto and "dia_cerrado" in texto
    assert "solo como dato): Registre tu reclamo." in texto


def test_el_bloque_de_coordinacion_va_en_el_mensaje_con_su_advertencia():
    """Viaja como dato del turno, nunca como mensaje de sistema, y solo cuando existe."""
    con = base._armar_entrada("hola", "", "Tarea: reserva")
    assert base.AVISO_COORDINACION in con and "Tarea: reserva" in con and con.endswith("hola")
    assert base.AVISO_COORDINACION not in base._armar_entrada("hola", "")


def test_el_nodo_solo_pasa_coordinacion_cuando_hay_tarea(monkeypatch):
    """Los componentes de siempre (y los reemplazos de las pruebas) no reciben un parametro nuevo."""
    recibido = {}

    def componente(texto, sesion_id, historial=None, contexto=None, **extra):
        """Guarda los parametros extra que recibio."""
        recibido.update(extra)
        return "ok"

    monkeypatch.setitem(grafo.NODOS, "reservas", componente)
    nodo = grafo._nodo_trabajo("reservas")
    nodo({"sesion_id": SESION, "mensaje": "x", "paso": 0, "tareas": [""]})
    assert recibido == {}
    nodo({"sesion_id": SESION, "mensaje": "x", "paso": 0, "tareas": ["mesa para 2"]})
    assert recibido["coordinacion"].startswith("Tarea: mesa para 2")


@pytest.mark.parametrize("datos", [
    {"revision_humana": {"estado": "pendiente"}},
    {"hilo_en_revision": True},
    {"guardrail_autorizacion": {"estado": "bloqueado"}},
    {"confirmacion_pendiente": "CONFIRMO ABCD1234"},
])
def test_el_segundo_paso_se_detiene_ante_estados_criticos(datos):
    """Revision pendiente, hilo pausado, acceso denegado o CONFIRMO pendiente cortan el turno."""
    contexto = ContextoConversacion(sesion_id=SESION)
    contexto.datos.update(datos)
    estado = {"plan": ["incidencias", "reservas"], "paso": 1, "contexto": contexto}
    assert grafo._siguiente(estado) == "cierre"
    assert grafo._siguiente({**estado, "paso": 0}) == "incidencias"


# --- cierre ---------------------------------------------------------------------------

def test_la_respuesta_directa_sale_tal_cual_con_una_ruta_real():
    """La ruta nunca es "orquestador": el respaldo la usaria como nombre de nodo."""
    salida = grafo._nodo_cierre({"sesion_id": SESION, "accion": "responder_directo",
                                 "respuesta_directa": "Hola, ¿en qué te ayudo?", "ultimo_agente": ""})
    assert salida["respuesta"] == "Hola, ¿en qué te ayudo?" and salida["ruta"] == "informacion"


def test_pedir_una_persona_abre_un_caso_tipo_otro_sin_hablar_de_mesa():
    """El ticket existe antes de anunciarlo, tiene su tipo y su texto no menciona una mesa."""
    contexto = ContextoConversacion(sesion_id=SESION)
    contexto.escalado = True
    contexto.datos["escalamiento"] = {"origen": "orquestador", "motivo": "pide persona", "detalle": "x"}
    salida = grafo._nodo_cierre({"sesion_id": SESION, "mensaje": "quiero hablar con una persona",
                                 "accion": "escalar_humano", "contexto": contexto})
    caso = servicio_incidencias().listar_incidencias()[-1]
    assert caso.tipo == "otro" and caso.id in salida["respuesta"]
    assert "mesa" not in salida["respuesta"]


def test_si_no_se_puede_abrir_el_caso_se_da_el_telefono(monkeypatch):
    """Sin ticket no se anuncia nada registrado: se da el contacto del restaurante."""
    def fallar(*args, **kwargs):
        """Simula Trello o el respaldo caidos."""
        raise RuntimeError("sin servicio")

    monkeypatch.setattr(grafo, "_escalar", fallar)
    contexto = ContextoConversacion(sesion_id=SESION)
    contexto.escalado = True
    contexto.datos["escalamiento"] = {"origen": "orquestador"}
    salida = grafo._nodo_cierre({"sesion_id": SESION, "accion": "escalar_humano", "contexto": contexto})
    assert "+51 940070695" in salida["respuesta"] and not contexto.escalado


def test_el_paso_diferido_se_ofrece_y_queda_como_continuidad():
    """Responde informacion, se ofrece seguir con la reserva y el proximo mensaje va a reservas."""
    salida = grafo._nodo_cierre({
        "sesion_id": SESION, "accion": "delegar", "plan": ["informacion"],
        "respuestas": [{"agente": "informacion", "texto": "Si, tenemos opciones veganas."}],
        "diferido": {"agente": "reservas", "tarea": "mesa para 2 el jueves"},
    })
    assert "seguir con la reserva" in salida["respuesta"]
    assert salida["ruta"] == "informacion" and salida["continuar_con"] == "reservas"


def test_un_paso_detenido_se_avisa_como_pendiente():
    """Si el control de estado corta el segundo paso, el cliente sabe que quedo pendiente."""
    salida = grafo._nodo_cierre({
        "sesion_id": SESION, "accion": "delegar", "plan": ["incidencias", "reservas"],
        "respuestas": [{"agente": "incidencias", "texto": "Registre tu reclamo."}],
    })
    assert "pendiente la reserva" in salida["respuesta"]


# --- turno completo -----------------------------------------------------------------

def preparar_turno(monkeypatch, decisiones, llamados):
    """Planificador con decisiones en secuencia y componentes falsos que anotan su coordinacion."""
    secuencia = iter(decisiones)

    class Modelo(ModeloFalso):
        """Devuelve la siguiente decision en cada turno."""

        def invoke(self, mensajes):
            """Toma la proxima decision de la secuencia."""
            return next(secuencia)

    def componente(nombre):
        """Componente falso que registra su llamada y responde con su nombre."""
        def responder(texto, sesion_id, historial=None, contexto=None, coordinacion=""):
            """Anota quien atendio y con que coordinacion."""
            llamados.append((nombre, coordinacion))
            return f"[{nombre}] respondio"
        return responder

    monkeypatch.setattr(grafo, "resolver_modelo", lambda **kwargs: Modelo())
    monkeypatch.setattr(grafo, "NODOS", {n: componente(n) for n in ("informacion", "reservas", "incidencias")})


def turno(texto):
    """Atiende un turno completo del orquestador."""
    return grafo._responder_turno(MensajeEntrante(sesion_id=SESION, texto=texto, canal="whatsapp"))


def test_turno_de_pedido_de_persona_sin_agentes(monkeypatch):
    """Ningun agente corre, se abre el caso y la continuidad queda en un componente real."""
    llamados = []
    preparar_turno(monkeypatch, [plan(accion="escalar_humano")], llamados)
    respuesta = turno("quiero hablar con una persona")
    assert llamados == [] and respuesta.escalado
    assert respuesta.datos["plan"] == ["orquestador:escalar_humano"]
    assert grafo._ultimo_agente[SESION] in grafo.NODOS


def test_turno_condicional_ofrece_y_el_si_retoma_la_tarea(monkeypatch):
    """Primer turno: responde informacion y ofrece. Segundo turno ("si"): reservas recibe la tarea guardada."""
    llamados = []
    preparar_turno(monkeypatch, [
        plan(pasos=["informacion", "reservas"], tareas=["veganas?", "mesa para 2 el jueves"],
             depende_del_anterior=True, accion="delegar"),
        plan(pasos=["reservas"], accion="delegar"),
    ], llamados)
    primera = turno("tienen opciones veganas? si si, mesa para 2 el jueves")
    assert [n for n, _ in llamados] == ["informacion"]
    assert "seguir con la reserva" in primera.texto
    assert grafo._ultimo_agente[SESION] == "reservas"
    turno("si")
    assert llamados[-1][0] == "reservas" and "mesa para 2 el jueves" in llamados[-1][1]
    assert SESION not in grafo._pendiente_de


def test_la_tarea_ofrecida_se_descarta_si_cambia_de_tema(monkeypatch):
    """Vive un solo turno: si el cliente pide otra cosa, la tarea vieja no se ejecuta."""
    llamados = []
    preparar_turno(monkeypatch, [
        plan(pasos=["informacion", "reservas"], tareas=["veganas?", "mesa"], depende_del_anterior=True,
             accion="delegar"),
        plan(pasos=["incidencias"], tareas=["reclamo"], accion="delegar"),
    ], llamados)
    turno("tienen veganas? si si, reserva")
    turno("mejor quiero quejarme por la espera de ayer")
    assert llamados[-1] == ("incidencias", "Tarea: reclamo")
    assert SESION not in grafo._pendiente_de


def test_el_registro_de_conversacion_guarda_la_accion(monkeypatch):
    """Las acciones directas no se cuentan como turnos de un agente en el registro."""
    from app.observabilidad import trazas
    llamados = []
    preparar_turno(monkeypatch, [plan(accion="responder_directo", respuesta_directa="Hola!")], llamados)
    turno("hola")
    ultimo = json.loads(trazas.ARCHIVO_CONVERSACIONES.read_text(encoding="utf-8").splitlines()[-1])
    assert ultimo["plan"] == ["orquestador:responder_directo"]
