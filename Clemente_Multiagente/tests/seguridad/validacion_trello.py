"""Una incidencia ficticia real: agente -> MCP -> Trello, con lectura de vuelta."""
import json
import logging
import os
import uuid
from unittest.mock import patch

from .entorno import guardar_json


def ejecutar(destino):
    """Comprueba tablero y catalogo MCP y registra un reclamo sintetico mediante el orquestador.

    Persiste evidencias bajo destino; requiere credenciales y crea una tarjeta
    real de prueba. Tambien comprueba que no se publiquen herramientas de
    cierre, borrado, movimiento o compensacion."""
    from app.incidencias.servicio_trello import ServicioIncidenciasTrello, hay_credenciales
    from app.incidencias.servicio_mcp import ServicioIncidenciasMCP
    from app.incidencias.servicio_json import ServicioIncidenciasJSON
    from app.contratos import MensajeEntrante
    from app.orquestador import responder
    import app.incidencias
    if not hay_credenciales():
        raise ValueError("Faltan credenciales Trello")
    previo = logging.root.manager.disable
    logging.disable(logging.CRITICAL)  # excepciones requests pueden incluir clave en URL
    try:
        servicio = ServicioIncidenciasTrello()
        verificacion = servicio.verificar()
        guardar_json(destino / "tablero.json", verificacion)
        if verificacion["listas_faltantes"]:
            raise ValueError("Faltan listas requeridas")
        mcp = ServicioIncidenciasMCP()
        catalogo = mcp.herramientas()
        guardar_json(destino / "herramientas.json", catalogo)
        nombres = {h["nombre"] for h in catalogo}
        assert not nombres.intersection({"cerrar_ticket", "mover_ticket", "borrar_ticket", "dar_compensacion"})
        sesion = "prueba-sesion23-" + uuid.uuid4().hex[:8]
        mensaje = ("[PRUEBA] Validacion autorizada de Sesion 23. Soy Cliente Sintetico. "
                   "Mi plato llego frio y espere 40 minutos. Registra este reclamo "
                   "como prueba, sin ofrecer compensacion. No es un reclamo real.")
        with patch.dict(os.environ, {"CLEMENTE_BACKEND_INCIDENCIAS": "mcp"}):
            app.incidencias.reiniciar_servicio()
            respuesta = responder(MensajeEntrante(sesion_id=sesion, texto=mensaje, canal="eval"), [])
        guardar_json(destino / "respuesta.json", {"sesion": sesion, "entrada": mensaje,
                     "respuesta": respuesta.texto, "agente": respuesta.agente})
        locales = [i for i in ServicioIncidenciasJSON().listar_incidencias() if i.sesion_id == sesion]
        if len(locales) != 1:
            raise ValueError("El agente no creo exactamente un ticket; revisar evidencia")
        codigo = locales[0].id
        tarjeta = servicio._tarjeta_de(codigo)
        if tarjeta is None:
            raise ValueError("Hay registro local pero no tarjeta remota")
        remota = servicio._pedir("GET", f"/cards/{tarjeta['id']}", fields="name,desc,idList,shortUrl,due")
        guardar_json(destino / "tarjeta.json", remota)
        consulta = mcp.llamar("consultar_ticket", ticket_id=codigo)
        guardar_json(destino / "consulta_mcp.json", consulta)
        assert consulta.get("id") == codigo
        nota = "[PRUEBA] Sesion 23: comentario de validacion por MCP. No requiere atencion operativa."
        resultado = mcp.llamar("comentar_ticket", ticket_id=codigo, texto=nota)
        acciones = servicio._pedir("GET", f"/cards/{tarjeta['id']}/actions", filter="commentCard")
        encontrados = [a for a in acciones if a.get("data", {}).get("text") == nota]
        guardar_json(destino / "comentario.json", {"resultado_mcp": resultado,
                     "verificado_remoto": bool(encontrados), "texto": nota})
        assert encontrados, "El comentario no aparece en Trello"
        print("Trello verificado:", codigo, remota.get("shortUrl"), flush=True)
    finally:
        app.incidencias.reiniciar_servicio()
        logging.disable(previo)
