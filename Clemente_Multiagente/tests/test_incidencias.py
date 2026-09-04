"""
Pruebas del registro de incidencias.

La regla del Entregable 01 que se verifica aqui: una incidencia nace abierta,
con responsable y plazo, y no la cierra el agente.
"""


def test_incidencia_nace_abierta_con_plazo(servicio_incidencias):
    incidencia = servicio_incidencias.crear_incidencia(
        "demo-1", "Espere 40 minutos con reserva confirmada", tipo="espera"
    )
    assert incidencia.estado == "abierta"
    assert incidencia.responsable == "staff"
    assert incidencia.plazo_horas == 4          # plazo del tipo "espera"


def test_tipo_desconocido_cae_en_otro(servicio_incidencias):
    incidencia = servicio_incidencias.crear_incidencia("demo-1", "algo raro", tipo="inventado")
    assert incidencia.tipo == "otro"
    assert incidencia.plazo_horas == 24


def test_listar_filtra_por_estado(servicio_incidencias):
    a = servicio_incidencias.crear_incidencia("demo-1", "plato frio", tipo="producto")
    servicio_incidencias.crear_incidencia("demo-2", "mala atencion", tipo="servicio")
    servicio_incidencias.cerrar_incidencia(a.id, "se ofrecio disculpa y cortesia")

    assert len(servicio_incidencias.listar_incidencias("abierta")) == 1
    assert len(servicio_incidencias.listar_incidencias("cerrada")) == 1
    assert len(servicio_incidencias.listar_incidencias()) == 2
