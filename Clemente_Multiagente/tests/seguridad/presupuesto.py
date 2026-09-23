"""Control conservador de llamadas HTTP de evaluacion, compartido entre etapas.

Solo un proceso por archivo. Reserva antes de enviar; si falta uso facturado o
hay error conserva la reserva. No sustituye la factura del proveedor.
"""
import json
import os
import asyncio
from contextlib import contextmanager, ExitStack
from threading import RLock
from unittest.mock import patch

import httpx

from .entorno import guardar_json

TARIFAS = {"gpt-5.6-terra": ("openai", 2, 12),
           "claude-sonnet-5": ("anthropic", 2, 10)}


class PresupuestoAgotado(RuntimeError):
    """Error que detiene la evaluacion antes de una llamada que excederia el limite reservado."""
    pass


class Presupuesto:
    """Control persistente de gasto estimado por proveedor para la campana de evaluacion.

    Reserva costo antes de enviar y lo ajusta con uso reportado; no sustituye
    la factura del proveedor ni intercepta transportes fuera de activo."""
    def __init__(self, archivo, limite=4.0):
        """Carga el libro de cargos existente o inicia uno con limite por proveedor y bloqueo local."""
        self.archivo = archivo
        self.lock = RLock()
        self.datos = json.loads(archivo.read_text()) if archivo.exists() else {
            "limite_por_proveedor": limite, "cargos": [],
            "nota": "Estimacion por tokens; reservas conservadas si no hay uso confirmado",
        }

    def preparar(self, request):
        """Valida la peticion, limita salida y reserva costo antes de enviarla al proveedor.

        Solo contempla modelos, hosts y endpoints declarados; rechaza streaming
        o configuraciones desconocidas con ValueError y exceso con PresupuestoAgotado.
        Devuelve peticion ajustada y cargo; hosts ajenos pasan sin cargo."""
        if request.url.host not in {"api.openai.com", "api.anthropic.com"}:
            return request, None
        datos = json.loads(request.content)
        modelo = datos.get("model")
        if modelo not in TARIFAS or datos.get("stream"):
            raise ValueError("Modelo o streaming no autorizado por el presupuesto de evaluacion")
        proveedor, entrada, salida = TARIFAS[modelo]
        if request.url.path not in {"/v1/messages", "/v1/chat/completions"}:
            raise ValueError("Endpoint no contemplado por el presupuesto")
        tope = 2048
        campo = "max_tokens" if proveedor == "anthropic" else "max_completion_tokens"
        datos.pop("max_tokens" if proveedor == "openai" else "max_completion_tokens", None)
        datos[campo] = tope
        contenido = json.dumps(datos, ensure_ascii=False).encode()
        # Cota deliberadamente holgada por bytes, incluyendo herramientas y
        # margen de serializacion del proveedor. No es un tokenizador exacto.
        reserva = ((2 * len(contenido) + 4096) * entrada + tope * salida) / 1_000_000
        with self.lock:
            total = sum(c["usd"] for c in self.datos["cargos"] if c["proveedor"] == proveedor)
            if total + reserva > self.datos["limite_por_proveedor"]:
                raise PresupuestoAgotado(f"Reserva de llamada supera limite de {proveedor}")
            cargo = {"proveedor": proveedor, "modelo": modelo, "usd": reserva,
                     "estado": "reservado", "reserva_usd": reserva,
                     "etapa": os.getenv("CLEMENTE_EVAL_ETAPA", "sin_etiqueta")}
            self.datos["cargos"].append(cargo)
            guardar_json(self.archivo, self.datos)
        headers = dict(request.headers)
        headers.pop("content-length", None)
        nuevo = type(request)(request.method, request.url, headers=headers,
                              content=contenido, extensions=request.extensions)
        return nuevo, cargo

    def cerrar(self, cargo, response):
        """Actualiza el cargo con HTTP y uso reportado y persiste el libro.

        Sin cargo no actua; si falla HTTP o falta uso mantiene la reserva estimada
        para no descontar gasto incierto."""
        if cargo is None:
            return
        with self.lock:
            cargo["http_status"] = response.status_code
            if response.is_success:
                cuerpo = response.json()
                cargo["modelo_respuesta"] = cuerpo.get("model")
                uso = cuerpo.get("usage", {})
                inp = uso.get("input_tokens", uso.get("prompt_tokens"))
                out = uso.get("output_tokens", uso.get("completion_tokens"))
                if inp is not None and out is not None:
                    _, precio_in, precio_out = TARIFAS[cargo["modelo"]]
                    # Cache Anthropic: lectura a tarifa normal, escritura a
                    # tarifa de cache 1h (la mayor), para no subestimar.
                    cache_write = uso.get("cache_creation_input_tokens", 0)
                    cache_read = uso.get("cache_read_input_tokens", 0)
                    cargo.update(estado="uso_reportado", uso=uso,
                        usd=((inp + cache_read + 2 * cache_write) * precio_in + out * precio_out) / 1_000_000)
            guardar_json(self.archivo, self.datos)

    @contextmanager
    def activo(self):
        """Intercepta temporalmente send de httpx y httpx2, sincrono y asincrono.

        Aplica preparar y cerrar mientras dura el contexto y restaura los metodos
        al salir. Si hay un loop inactivo, drena tareas pendientes y su executor."""
        import httpx2
        def envolver_sync(original):
            """Construye el wrapper sincrono que aplica la reserva y contabilizacion a send."""
            def enviar(cliente, request, **kwargs):
                """Reserva costo, envia con el transporte original y contabiliza el uso si hay cargo.

                Lee el cuerpo antes de cerrar el cargo; un error de envio conserva la reserva."""
                request, cargo = self.preparar(request)
                respuesta = original(cliente, request, **kwargs)
                if cargo is not None:
                    respuesta.read()
                    self.cerrar(cargo, respuesta)
                return respuesta
            return enviar
        def envolver_async(original):
            """Construye el wrapper asincrono que aplica la reserva y contabilizacion a send."""
            async def enviar(cliente, request, **kwargs):
                """Reserva costo, envia con el transporte original y contabiliza el uso si hay cargo.

                Lee el cuerpo antes de cerrar el cargo; un error de envio conserva la reserva."""
                request, cargo = self.preparar(request)
                respuesta = await original(cliente, request, **kwargs)
                if cargo is not None:
                    await respuesta.aread()
                    self.cerrar(cargo, respuesta)
                return respuesta
            return enviar
        with ExitStack() as pila:
            for modulo in (httpx, httpx2):
                pila.enter_context(patch.object(modulo.Client, "send", envolver_sync(modulo.Client.send)))
                pila.enter_context(patch.object(modulo.AsyncClient, "send", envolver_async(modulo.AsyncClient.send)))
            try:
                yield self
            finally:
                # DeepTeam puede dejar tareas pendientes si gather propaga un
                # error. Mantener la guardia instalada hasta que se drenen.
                try:
                    loop = asyncio.get_event_loop()
                except RuntimeError:
                    loop = None
                if loop is not None and not loop.is_closed() and not loop.is_running():
                    pendientes = asyncio.all_tasks(loop)
                    if pendientes:
                        async def drenar():
                            """Espera las tareas pendientes sin propagar sus excepciones y cierra el executor del loop."""
                            await asyncio.gather(*pendientes, return_exceptions=True)
                            await loop.shutdown_default_executor()
                        loop.run_until_complete(drenar())
