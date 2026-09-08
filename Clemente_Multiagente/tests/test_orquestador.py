"""
Pruebas del orquestador: el plan, el encadenamiento y el punto unico de salida.

Todas corren SIN credencial y SIN llamar al modelo. Lo que se prueba aqui es la
maquinaria del grafo -- que un plan de dos pasos se recorra entero, que no se
repita un agente, que la sintesis no gaste una llamada cuando hay una sola
respuesta. Si el modelo planifica bien o mal es otra cosa, y eso se mide en
`tests/eval/`, que si cuesta dinero.
"""

import pytest

from app.orquestador import grafo


# --------------------------------------------------------------------------
# El plan
# --------------------------------------------------------------------------

def test_el_plan_no_repite_agente_ni_pasa_del_tope():
    """
    El esquema de salida garantiza que los valores son validos, no que sean
    razonables: nada le impide al modelo devolver ["reservas", "reservas"] o
    cuatro pasos. Eso se corrige en codigo, no pidiendoselo al prompt.
    """
    assert grafo._limpiar_plan(["reservas", "reservas"]) == ["reservas"]
    assert grafo._limpiar_plan(["incidencias", "reservas", "informacion"]) == [
        "incidencias", "reservas",
    ]
    assert grafo._limpiar_plan(["pedidos", "reservas"]) == ["reservas"]
    assert grafo._limpiar_plan([]) == []


@pytest.mark.parametrize(
    "estado, esperado",
    [
        ({"plan": ["informacion"], "paso": 0}, "informacion"),
        ({"plan": ["informacion"], "paso": 1}, "cierre"),
        ({"plan": ["incidencias", "reservas"], "paso": 1}, "reservas"),
        ({"plan": ["incidencias", "reservas"], "paso": 2}, "cierre"),
        ({"plan": [], "paso": 0}, "cierre"),
    ],
)
def test_que_sigue_despues_de_cada_paso(estado, esperado):
    assert grafo._siguiente(estado) == esperado


# --------------------------------------------------------------------------
# El encadenamiento -- la capacidad nueva que pidio Boris
# --------------------------------------------------------------------------

def test_un_plan_de_dos_pasos_recorre_los_dos_agentes(monkeypatch):
    """
    El caso que antes se perdia: "espere 40 minutos y ahora quiero mesa el sabado".

    Con el router anterior la regla de prioridad mandaba todo a incidencias y la
    reserva se caia del turno. Ahora el turno pasa por los dos, en orden.
    """
    llamados = []

    def agente_falso(nombre):
        def responder(texto, sesion_id, historial=None, contexto=None):
            llamados.append(nombre)
            return f"[{nombre}] respondio"
        return responder

    monkeypatch.setattr(grafo, "NODOS", {
        "informacion": agente_falso("informacion"),
        "reservas": agente_falso("reservas"),
        "incidencias": agente_falso("incidencias"),
    })
    monkeypatch.setattr(grafo, "_nodo_planificador", lambda estado: {
        "plan": ["incidencias", "reservas"], "paso": 0,
        "motivo_ruta": "se queja y ademas pide mesa", "respuestas": [],
    })
    # La sintesis se saltea: aqui interesa el recorrido, no el texto final.
    monkeypatch.setattr(grafo, "_sintetizar", lambda respuestas, sesion: " ".join(
        r["texto"] for r in respuestas
    ))
    grafo.reiniciar_grafo()

    final = grafo.obtener_grafo().invoke({"sesion_id": "t-1", "mensaje": "espere 40 minutos y quiero mesa"})

    assert llamados == ["incidencias", "reservas"]
    assert "[incidencias]" in final["respuesta"] and "[reservas]" in final["respuesta"]
    # Con quien queda la conversacion para el turno siguiente: el ultimo que hablo.
    assert final["ruta"] == "reservas"
    grafo.reiniciar_grafo()


def test_una_sola_respuesta_no_paga_una_llamada_de_sintesis(monkeypatch):
    """
    Optimizacion deliberada, y la mas importante del nodo de cierre: reescribir
    una confirmacion de reserva es arriesgar el codigo y la hora sin ganar nada,
    y seria pagar un modelo de mas en la gran mayoria de los turnos.
    """
    def explotar(*_args, **_kwargs):
        raise AssertionError("no se debe llamar al modelo con una sola respuesta")

    monkeypatch.setattr(grafo, "resolver_modelo", explotar)

    texto = grafo._sintetizar([{"agente": "reservas", "texto": "Reserva R-ABC123 confirmada."}], "t-2")
    assert texto == "Reserva R-ABC123 confirmada."


def test_si_falla_la_sintesis_no_se_pierde_ninguna_respuesta(monkeypatch):
    """Dos textos pegados se leen feo; perder uno de los dos es peor."""
    def explotar(*_args, **_kwargs):
        raise RuntimeError("modelo caido")

    monkeypatch.setattr(grafo, "resolver_modelo", explotar)

    texto = grafo._sintetizar(
        [{"agente": "incidencias", "texto": "Anote tu reclamo."},
         {"agente": "reservas", "texto": "Tengo mesa el sabado."}],
        "t-3",
    )
    assert "Anote tu reclamo." in texto and "Tengo mesa el sabado." in texto


# --------------------------------------------------------------------------
# El punto unico de salida
# --------------------------------------------------------------------------

def test_sin_escalamiento_el_cierre_no_inventa_ticket(tmp_path, monkeypatch):
    """Solo se abre ticket si un agente levanto la mano. No por las dudas."""
    from app.agentes.contexto import ContextoConversacion
    from app.incidencias.servicio_json import ServicioIncidenciasJSON

    servicio = ServicioIncidenciasJSON(archivo=tmp_path / "incidencias.json")
    monkeypatch.setattr(grafo, "servicio_incidencias", lambda: servicio)

    contexto = ContextoConversacion(sesion_id="t-4")
    final = grafo._nodo_cierre({
        "sesion_id": "t-4", "mensaje": "a que hora abren?", "contexto": contexto,
        "respuestas": [{"agente": "informacion", "texto": "Abrimos de martes a domingo."}],
    })

    assert servicio.listar_incidencias() == []
    assert final["respuesta"] == "Abrimos de martes a domingo."
    assert final["ruta"] == "informacion"


def test_un_hilo_escala_una_sola_vez(tmp_path, monkeypatch):
    """
    Regresion del experimento del 2026-09-08.

    El escalamiento de un grupo grande ocurre en dos turnos -- el agente
    reconoce el limite, pide contacto, y recien entonces escala --, asi que la
    senal viene levantada en los dos. Sin control se abrian DOS tarjetas del
    mismo caso y el staff recibia el mismo grupo por duplicado.

    El dato del segundo turno no se pierde: entra como nota en la tarjeta que ya
    existe.
    """
    from app.agentes.contexto import ContextoConversacion
    from app.incidencias.servicio_json import ServicioIncidenciasJSON

    servicio = ServicioIncidenciasJSON(archivo=tmp_path / "incidencias.json")
    monkeypatch.setattr(grafo, "servicio_incidencias", lambda: servicio)
    grafo.olvidar_sesion("t-esc")

    def turno(mensaje, motivo):
        contexto = ContextoConversacion(sesion_id="t-esc")
        contexto.escalado = True
        contexto.datos["escalamiento"] = {"origen": "reservas", "motivo": motivo, "detalle": ""}
        return grafo._nodo_cierre({
            "sesion_id": "t-esc", "mensaje": mensaje, "contexto": contexto,
            "respuestas": [{"agente": "reservas", "texto": "Lo dejo anotado."}],
        })

    primero = turno("somos 14 el sabado", "grupo de 14 personas")
    segundo = turno("soy Christian, 956789900", "contacto del cliente")

    abiertas = servicio.listar_incidencias()
    assert len(abiertas) == 1, "se abrio una segunda tarjeta para el mismo caso"

    codigo = abiertas[0].id
    assert codigo in primero["respuesta"] and codigo in segundo["respuesta"]
    # El telefono del segundo turno tiene que haber quedado en el caso.
    assert "956789900" in abiertas[0].descripcion

    grafo.olvidar_sesion("t-esc")


def test_el_cierre_no_repite_un_codigo_que_el_agente_ya_dijo(tmp_path, monkeypatch):
    """
    Antes se pegaba siempre una frase completa encima de la del agente, que decia
    lo mismo: el cliente leia la promesa dos veces en el mismo mensaje.
    """
    from app.agentes.contexto import ContextoConversacion
    from app.incidencias.servicio_json import ServicioIncidenciasJSON

    servicio = ServicioIncidenciasJSON(archivo=tmp_path / "incidencias.json")
    monkeypatch.setattr(grafo, "servicio_incidencias", lambda: servicio)
    grafo.olvidar_sesion("t-dup")

    contexto = ContextoConversacion(sesion_id="t-dup")
    contexto.escalado = True
    contexto.datos["escalamiento"] = {"origen": "reservas", "motivo": "grupo grande", "detalle": ""}

    # Primero se abre el caso para conocer el codigo...
    codigo = grafo._escalar("t-dup", contexto.datos["escalamiento"], "somos 14", contexto)
    # ...y ahora el agente lo menciona por su cuenta en su respuesta.
    final = grafo._nodo_cierre({
        "sesion_id": "t-dup", "mensaje": "somos 14", "contexto": contexto,
        "respuestas": [{"agente": "reservas", "texto": f"Tu caso es el {codigo}, te contactamos."}],
    })

    assert final["respuesta"].count(codigo) == 1
    grafo.olvidar_sesion("t-dup")
