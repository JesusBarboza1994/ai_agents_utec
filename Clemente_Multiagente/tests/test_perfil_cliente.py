"""
Perfil del cliente: identidad del servidor, alergias anotadas y la tool `anotar_dato_cliente`.

Observacion 3.2 del plan (alergia declarada y no capturada) y acuerdo 2.2
(un telefono escrito en el mensaje no concede identidad).
"""

from app.agentes import memoria
from app.agentes.contexto import ContextoConversacion
from app.agentes.tools.cliente_tools import anotar_dato_cliente


class _RuntimeFalso:
    """Imita lo unico que las tools usan del ToolRuntime que inyecta create_agent."""

    def __init__(self, contexto):
        """Expone el contexto recibido mediante el atributo context que leen las tools."""
        self.context = contexto


def test_un_telefono_declarado_no_abre_el_perfil_de_otro():
    """La clave es la identidad autenticada del canal; decir un numero no cambia de perfil."""
    memoria.recordar("whatsapp-951111111", nombre="Ana", alergias=["mani"])

    assert memoria.perfil_de("web-intruso", telefono="951111111") is None
    memoria.anotar("web-intruso", "alergia", "gluten")
    assert memoria.perfil_de("whatsapp-951111111")["alergias"] == ["mani"]
    assert memoria.perfil_de("web-intruso")["alergias"] == ["gluten"]


def test_el_telefono_dicho_se_guarda_como_dato_no_como_clave():
    """Verifica que el telefono dicho se guarda como dato no como clave."""
    memoria.recordar("web-abc", nombre="Luis", telefono="999888777")

    perfil = memoria.perfil_de("web-abc")
    assert perfil["telefono"] == "999888777"
    assert memoria.perfil_de("whatsapp-999888777") is None


def test_las_alergias_no_se_repiten_y_llegan_a_la_ficha():
    """Verifica que las alergias no se repiten y llegan a la ficha."""
    memoria.anotar("whatsapp-952222222", "alergia", "Mani")
    memoria.anotar("whatsapp-952222222", "alergia", "mani ")
    memoria.anotar("whatsapp-952222222", "preferencia", "terraza")

    ficha = memoria.ficha_del_cliente("whatsapp-952222222")

    assert memoria.perfil_de("whatsapp-952222222")["alergias"] == ["Mani"]
    assert "alergias declaradas" in ficha and "Mani" in ficha
    assert "deben confirmarse al reservar y al llegar" in ficha
    assert "preferencias declaradas: terraza" in ficha


def test_la_tool_anota_y_no_promete_que_la_cocina_ya_sabe():
    """Verifica que la tool anota y no promete que la cocina ya sabe."""
    contexto = ContextoConversacion(sesion_id="whatsapp-953333333")

    salida = anotar_dato_cliente.func(campo="Alergia", valor=" mariscos ", runtime=_RuntimeFalso(contexto))

    assert salida.startswith("Anotado: alergia a mariscos")
    assert "la repita" in salida and "no por este chat" in salida
    assert contexto.datos["perfil_actualizado"] == {"campo": "alergia", "valor": "mariscos"}
    assert memoria.perfil_de("whatsapp-953333333")["alergias"] == ["mariscos"]


def test_la_tool_rechaza_campos_y_valores_invalidos():
    """Verifica que la tool rechaza campos y valores invalidos."""
    runtime = _RuntimeFalso(ContextoConversacion(sesion_id="web-val"))

    assert anotar_dato_cliente.func(campo="tarjeta", valor="4111", runtime=runtime).startswith("Campo no admitido")
    assert anotar_dato_cliente.func(campo="alergia", valor="   ", runtime=runtime).startswith("Indica un valor")
    assert anotar_dato_cliente.func(campo="alergia", valor="x" * 200, runtime=runtime).startswith("Indica un valor")
    assert memoria.perfil_de("web-val") is None
    assert "No se pudo anotar" in anotar_dato_cliente.func(
        campo="nombre", valor="Ana", runtime=_RuntimeFalso(ContextoConversacion(sesion_id="desconocida")),
    )
