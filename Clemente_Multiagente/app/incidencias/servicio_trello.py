"""
Registro de incidencias sobre Trello -- el sistema donde el staff realmente trabaja.

Por que existe este archivo
---------------------------
Boris, asesoria del 2026-09-07 [04:44]: "de nuevo estamos siendo un poco
abstractos. No hay una definicion de tool a hoy. Porque para crear el ticket
necesitas un soporte como, no se, Trello, o Jira".

Y el criterio con el que eligio Trello [05:59]: "necesitas una herramienta de
persistencia, de seguimiento y a la vez notificacion. Y ahorita estoy viendo que
Trello podria ser las tres".

Eso es exactamente lo que faltaba. Hasta ahora el agente le decia al cliente que
"una persona del restaurante continuara la coordinacion" y **no habia nadie
recibiendo nada**: la incidencia era una fila en un JSON que ningun humano miraba.
La tarjeta de Trello proporciona una vista para el personal. Esta implementacion
crea tarjetas sin asignar miembros ni comprobar entrega de notificaciones;
esas acciones dependen de la configuracion operativa del tablero. No debe
anunciarse que una persona fue notificada solo porque existe un codigo local.

Doble escritura, y por que
---------------------------
Este servicio guarda en los dos lados: local (JSON) y Trello.

  * **Trello manda en el ESTADO.** La tarjeta se mueve de lista cuando una persona
    la trabaja, asi que preguntar por el estado es preguntarle a Trello.
  * **El JSON local manda en la DISPONIBILIDAD.** Si Trello no responde -- sin red,
    token vencido, tablero renombrado --, la incidencia igual queda registrada y el
    cliente igual recibe su codigo. Perder el reclamo de un cliente porque un
    servicio externo esta caido no es una opcion.

Las dos copias se unen por el codigo `I-XXXXXX`, que viaja en el titulo de la
tarjeta. No es una fuente de verdad duplicada: son dos vistas del mismo caso, una
para el agente y otra para la persona que lo atiende.
"""

import logging
import os
from datetime import datetime, timedelta, timezone

from ..contratos import Incidencia
from .alertas import avisar_sin_tarjeta, describir_error
from .servicio_json import PLAZOS_HORAS, ServicioIncidenciasJSON

log = logging.getLogger("clemente.trello")

API = "https://api.trello.com/1"
TIEMPO_LIMITE = 10  # segundos; el cliente esta esperando una respuesta en el chat

# Nombre de la lista donde nace todo ticket nuevo, y el mapa de vuelta desde el
# nombre de la lista al estado del contrato. Si el restaurante renombra sus
# listas, esto es lo unico que hay que tocar.
LISTA_INICIAL = "Pendiente"
ESTADO_POR_LISTA = {
    "pendiente": "abierta",
    "en atencion": "en_curso",
    "en atención": "en_curso",
    "esperando cliente": "en_curso",
    "resuelto": "cerrada",
}


def credenciales() -> tuple[str, str]:
    """Clave y token de Trello. Nunca se imprimen ni se registran en una traza."""
    return os.getenv("TRELLO_API_KEY", ""), os.getenv("TRELLO_TOKEN", "")


def hay_credenciales() -> bool:
    """Devuelve si clave y token de Trello estan definidos, sin comprobar su validez remota."""
    clave, token = credenciales()
    return bool(clave and token)


class ServicioIncidenciasTrello:
    """
    Implementa `ServicioIncidencias` (app/contratos.py) contra un tablero de Trello.

    Mantiene la misma firma que `ServicioIncidenciasJSON`, asi que los agentes y
    las tools no se enteran de cual de los dos esta activo.
    """

    def __init__(self, tablero: str | None = None, espejo: ServicioIncidenciasJSON | None = None):
        """Configura el nombre del tablero, respaldo JSON y caches de listas y etiquetas.

        El tablero se descubre en la primera operacion que lo necesita."""
        self.tablero_nombre = tablero or os.getenv("TRELLO_TABLERO", "Incidencias Clemente")
        self.espejo = espejo or ServicioIncidenciasJSON()
        self._tablero_id: str | None = None
        self._listas: dict[str, str] = {}     # nombre en minusculas -> id
        self._etiquetas: dict[str, str] = {}  # nombre en minusculas -> id

    # ---------------------------- HTTP ------------------------------------

    def _pedir(self, metodo: str, ruta: str, **parametros):
        """Hace una peticion a la API de Trello con credenciales y timeout.

        Devuelve JSON o diccionario vacio si no hay cuerpo; propaga errores HTTP
        y lanza RuntimeError cuando faltan las credenciales."""
        import requests

        clave, token = credenciales()
        if not (clave and token):
            raise RuntimeError("faltan TRELLO_API_KEY o TRELLO_TOKEN en el .env")

        respuesta = requests.request(
            metodo, f"{API}{ruta}",
            params={"key": clave, "token": token, **parametros},
            timeout=TIEMPO_LIMITE,
        )
        respuesta.raise_for_status()
        return respuesta.json() if respuesta.content else {}

    # ------------------------- descubrimiento -----------------------------

    def _cargar_tablero(self) -> None:
        """Resuelve una sola vez el id del tablero, sus listas y sus etiquetas."""
        if self._tablero_id:
            return

        tableros = self._pedir("GET", "/members/me/boards", fields="name")
        buscado = self.tablero_nombre.strip().lower()
        for tablero in tableros:
            if tablero.get("name", "").strip().lower() == buscado:
                self._tablero_id = tablero["id"]
                break
        else:
            disponibles = ", ".join(t.get("name", "?") for t in tableros) or "(ninguno)"
            raise RuntimeError(
                f"no existe un tablero llamado {self.tablero_nombre!r}. "
                f"Tableros visibles con este token: {disponibles}"
            )

        self._listas = {
            l["name"].strip().lower(): l["id"]
            for l in self._pedir("GET", f"/boards/{self._tablero_id}/lists")
        }
        self._etiquetas = {
            e["name"].strip().lower(): e["id"]
            for e in self._pedir("GET", f"/boards/{self._tablero_id}/labels")
            if e.get("name")
        }

    def verificar(self) -> dict:
        """
        Comprueba que el tablero esta como el codigo espera. La usa el comando
        `python -m app.incidencias.servicio_trello --verificar`.

        Revisa las dos cosas que tienen que coincidir con el codigo: los nombres
        de las listas (de ahi sale el estado de la incidencia) y los de las
        etiquetas (que son los tipos declarados en `contratos.Incidencia`).
        """
        self._cargar_tablero()
        faltantes = [
            nombre for nombre in ("pendiente", "en atencion", "esperando cliente", "resuelto")
            if nombre not in self._listas and nombre.replace("atencion", "atención") not in self._listas
        ]
        return {
            "tablero": self.tablero_nombre,
            "listas": sorted(self._listas),
            "etiquetas": sorted(self._etiquetas),
            "listas_faltantes": faltantes,
            "etiquetas_faltantes": sorted(set(PLAZOS_HORAS) - set(self._etiquetas)),
            "etiquetas_de_mas": sorted(set(self._etiquetas) - set(PLAZOS_HORAS)),
        }

    # ---------------------- contrato ServicioIncidencias -------------------

    def crear_incidencia(
        self, sesion_id: str, descripcion: str, tipo: str = "otro",
        reserva_id: str | None = None,
    ) -> Incidencia:
        # Primero el registro local: es el que garantiza que el cliente reciba un
        # codigo aunque Trello este caido.
        """Persiste primero el caso en JSON e intenta crear su tarjeta en la lista Pendiente.

        Agrega codigo, descripcion, vencimiento y etiqueta cuando esta disponible.
        Si Trello falla registra una advertencia y devuelve el caso local: el codigo
        no demuestra por si solo que se haya creado una tarjeta o notificado al staff."""
        incidencia = self.espejo.crear_incidencia(sesion_id, descripcion, tipo, reserva_id)

        try:
            self._cargar_tablero()
            id_lista = self._listas.get(LISTA_INICIAL.lower())
            if not id_lista:
                raise RuntimeError(f"el tablero no tiene una lista {LISTA_INICIAL!r}")

            vence = datetime.now(timezone.utc) + timedelta(hours=incidencia.plazo_horas)
            etiqueta = self._etiquetas.get(incidencia.tipo.lower())
            if not etiqueta:
                # La tarjeta se crea igual, pero sin etiqueta el tablero pierde el
                # filtro por tipo. Se avisa en vez de fallar en silencio: el caso
                # tipico es que el tablero use otro nombre para el mismo tipo.
                log.warning(
                    "el tablero no tiene una etiqueta %r; la tarjeta %s va sin etiquetar. "
                    "Etiquetas que espera el codigo: %s",
                    incidencia.tipo, incidencia.id, ", ".join(sorted(PLAZOS_HORAS)),
                )

            tarjeta = self._pedir(
                "POST", "/cards",
                idList=id_lista,
                name=f"{incidencia.id} · {incidencia.tipo} · {descripcion[:60]}",
                desc=(
                    f"**Codigo:** {incidencia.id}\n"
                    f"**Sesion:** {sesion_id}\n"
                    f"**Tipo:** {incidencia.tipo}\n"
                    f"**Reserva relacionada:** {reserva_id or '(ninguna)'}\n"
                    f"**Plazo:** {incidencia.plazo_horas} horas\n\n"
                    f"{descripcion}\n\n"
                    f"_Creada por Clemente el {incidencia.creada}._"
                ),
                due=vence.isoformat(),
                idLabels=etiqueta or "",
            )
            log.info("incidencia %s -> tarjeta Trello %s", incidencia.id, tarjeta.get("shortUrl"))
        except Exception as error:
            # No se relanza: el reclamo del cliente ya quedo registrado y eso es
            # lo que no se puede perder. Queda el aviso para que alguien lo vea.
            avisar_sin_tarjeta(incidencia.id, sesion_id, error)

        return incidencia

    def listar_incidencias(self, estado: str | None = None) -> list[Incidencia]:
        """
        El estado lo manda Trello: es donde una persona mueve la tarjeta.

        Si Trello no responde se devuelve el registro local, que tendra el estado
        con el que nacio la incidencia. Es informacion vieja, no informacion
        falsa, y es mejor que un error en medio de una conversacion.
        """
        locales = self.espejo.listar_incidencias()
        try:
            self._cargar_tablero()
            lista_por_id = {v: k for k, v in self._listas.items()}
            tarjetas = self._pedir(
                "GET", f"/boards/{self._tablero_id}/cards", fields="name,idList"
            )
            estado_por_codigo = {}
            for tarjeta in tarjetas:
                codigo = tarjeta.get("name", "").split("·")[0].strip()
                nombre_lista = lista_por_id.get(tarjeta.get("idList"), "")
                estado_por_codigo[codigo] = ESTADO_POR_LISTA.get(nombre_lista, "abierta")

            for incidencia in locales:
                if incidencia.id in estado_por_codigo:
                    incidencia.estado = estado_por_codigo[incidencia.id]
        except Exception as error:
            log.warning("no se pudo leer el estado desde Trello (%s)", describir_error(error))

        return [i for i in locales if estado is None or i.estado == estado]

    def _tarjeta_de(self, incidencia_id: str) -> dict | None:
        """Busca la tarjeta cuyo titulo comienza con incidencia_id; devuelve None si no existe.

        Carga el tablero y propaga errores de la API."""
        self._cargar_tablero()
        buscado = incidencia_id.strip().upper()
        for tarjeta in self._pedir("GET", f"/boards/{self._tablero_id}/cards", fields="name"):
            if tarjeta.get("name", "").split("·")[0].strip() == buscado:
                return tarjeta
        return None

    def anotar(self, incidencia_id: str, texto: str) -> bool:
        """Comentario en la tarjeta: es donde el staff lo va a leer."""
        self.espejo.anotar(incidencia_id, texto)
        try:
            tarjeta = self._tarjeta_de(incidencia_id)
            if tarjeta is None:
                return False
            self._pedir("POST", f"/cards/{tarjeta['id']}/actions/comments", text=texto)
            return True
        except Exception as error:
            log.warning("no se pudo anotar en %s (%s)", incidencia_id, describir_error(error))
            return False

    def cerrar_incidencia(self, incidencia_id: str, nota_cierre: str = "") -> Incidencia | None:
        """
        Cierre desde el panel del staff. Ningun agente tiene tool para esto.

        Mueve la tarjeta a "Resuelto" y ademas cierra el registro local, para que
        las dos vistas queden diciendo lo mismo.
        """
        incidencia = self.espejo.cerrar_incidencia(incidencia_id, nota_cierre)
        try:
            self._cargar_tablero()
            destino = self._listas.get("resuelto")
            tarjetas = self._pedir("GET", f"/boards/{self._tablero_id}/cards", fields="name")
            for tarjeta in tarjetas:
                if tarjeta.get("name", "").split("·")[0].strip() == incidencia_id:
                    self._pedir("PUT", f"/cards/{tarjeta['id']}", idList=destino)
                    if nota_cierre:
                        self._pedir("POST", f"/cards/{tarjeta['id']}/actions/comments",
                                    text=f"Cierre: {nota_cierre}")
                    break
        except Exception as error:
            log.warning("no se pudo cerrar %s en Trello (%s)", incidencia_id, describir_error(error))
        return incidencia


if __name__ == "__main__":
    # python -m app.incidencias.servicio_trello --verificar
    #     comprueba que el tablero existe y tiene las listas que el codigo espera
    # python -m app.incidencias.servicio_trello --prueba
    #     crea una tarjeta de prueba de verdad (usa una sola, luego borrala a mano)
    import json
    import sys

    from ..config import Config

    Config.desde_entorno()
    logging.basicConfig(level=logging.INFO, format="%(levelname)-7s | %(message)s")

    if not hay_credenciales():
        print("Faltan TRELLO_API_KEY y/o TRELLO_TOKEN en clemente/.env")
        raise SystemExit(1)

    servicio = ServicioIncidenciasTrello()
    try:
        print(json.dumps(servicio.verificar(), ensure_ascii=False, indent=2))
    except Exception as error:
        print(f"ERROR: {error}")
        raise SystemExit(1)

    if "--prueba" in sys.argv:
        creada = servicio.crear_incidencia(
            sesion_id="prueba-local",
            descripcion="Ticket de prueba creado por Clemente para verificar la integracion.",
            tipo="otro",
        )
        print(f"Creada {creada.id}. Revisa la lista '{LISTA_INICIAL}' del tablero.")
        print(f"Plazos por tipo: {PLAZOS_HORAS}")
