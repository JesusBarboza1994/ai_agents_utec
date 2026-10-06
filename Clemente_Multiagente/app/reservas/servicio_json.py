"""
Implementacion de referencia del Gestor de Reservas, sobre archivos JSON.

Es deliberadamente simple: sirve para que los otros cuatro frentes puedan
trabajar HOY contra datos reales sin esperar la version definitiva. Miguel
puede reemplazarla por completo (base de datos, API del restaurante, POS)
mientras respete `ServicioReservas` de `app/contratos.py`.

Modelo de datos del restaurante:
  * mesas.json     -- mapa de mesas declarado por la operacion (NO lo inventa el agente)
  * reservas.json  -- reservas creadas (se genera solo; esta en .gitignore)
"""

import json
import uuid
from pathlib import Path

from ..contratos import OpcionDisponibilidad, Reserva
from ..datos import carpeta_de_datos
from .validaciones import (
    TURNOS_VALIDOS,
    clave_idempotencia,
    validar_cambio_turno,
    validar_datos_reserva,
)

CARPETA_DATOS = Path(__file__).parent / "datos"
ARCHIVO_MESAS = CARPETA_DATOS / "mesas.json"
ARCHIVO_RESERVAS = carpeta_de_datos(CARPETA_DATOS) / "reservas.json"

# Una mesa reservada bloquea su turno completo (no hay solapamiento parcial).
DURACION_TURNO_HORAS = 2


class ServicioReservasJSON:
    """Implementa disponibilidad y reservas sobre el mapa de mesas y un archivo JSON.

    La autorizacion por sesion pertenece a otra capa; estos metodos no la
    comprueban. La lectura y escritura de JSON no constituyen una transaccion
    con bloqueo entre procesos."""
    def __init__(self, archivo_reservas: Path | None = None) -> None:
        """Selecciona el archivo de reservas y carga las mesas desde ARCHIVO_MESAS.

        Los errores del mapa de mesas se propagan; no crea reservas al instanciarse."""
        self.archivo_reservas = archivo_reservas or ARCHIVO_RESERVAS
        self.mesas = json.loads(ARCHIVO_MESAS.read_text(encoding="utf-8"))["mesas"]

    # ---------------------------- persistencia ----------------------------

    def _leer(self) -> list[dict]:
        """Carga las reservas del JSON o devuelve lista vacia si el archivo no existe.

        Los errores de lectura y JSON mal formado se propagan."""
        if not self.archivo_reservas.exists():
            return []
        return json.loads(self.archivo_reservas.read_text(encoding="utf-8"))

    def _escribir(self, reservas: list[dict]) -> None:
        """Sobrescribe el JSON de reservas en UTF-8, creando la carpeta si es necesario."""
        self.archivo_reservas.parent.mkdir(parents=True, exist_ok=True)
        self.archivo_reservas.write_text(
            json.dumps(reservas, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    # ------------------------------ consultas ------------------------------

    def consultar_disponibilidad(
        self, fecha: str, hora: str, personas: int, zona: str | None = None,
        excluir_reserva_id: str | None = None,
    ) -> list[OpcionDisponibilidad]:
        """
        Mesas libres para ese turno. `excluir_reserva_id` libera la mesa de una
        reserva concreta: hace falta al MODIFICAR, para que la reserva no
        compita contra si misma por su propia mesa.
        """
        if hora not in TURNOS_VALIDOS:
            return []

        ocupadas = {
            r["mesa_id"]
            for r in self._leer()
            if r["fecha"] == fecha and r["hora"] == hora
            and r["estado"] != "cancelada" and r["id"] != excluir_reserva_id
        }

        opciones = []
        for mesa in self.mesas:
            if mesa["id"] in ocupadas:
                continue
            if mesa["capacidad"] < personas:
                continue
            if zona and mesa["zona"] != zona:
                continue
            opciones.append(
                OpcionDisponibilidad(
                    fecha=fecha, hora=hora, zona=mesa["zona"],
                    mesa_id=mesa["id"], capacidad=mesa["capacidad"],
                )
            )

        # Mesa mas ajustada primero: no dar una mesa de 8 a una pareja.
        opciones.sort(key=lambda o: o.capacidad)
        return opciones

    def obtener_reserva(self, reserva_id: str) -> Reserva | None:
        """Busca una reserva por id y devuelve su dataclass, o None si no existe."""
        for r in self._leer():
            if r["id"] == reserva_id:
                return Reserva(**r)
        return None

    def buscar_reservas_de(self, telefono: str) -> list[Reserva]:
        """Devuelve las reservas del telefono exacto, incluidas las canceladas.

        No comprueba propiedad de sesion: el acceso del cliente se protege en las tools."""
        return [Reserva(**r) for r in self._leer() if r["telefono"] == telefono]

    # ------------------------------ escrituras -----------------------------

    def crear_reserva(
        self, nombre: str, telefono: str, fecha: str, hora: str,
        personas: int, zona: str, notas: str = "",
    ) -> Reserva:
        """Valida y sanea los datos, y persiste la reserva; una clave de idempotencia repetida devuelve la existente sin duplicar."""
        datos = validar_datos_reserva(
            nombre=nombre, telefono=telefono, fecha=fecha, hora=hora,
            personas=personas, zona=zona, notas=notas,
        )
        clave = clave_idempotencia(datos["telefono"], datos["fecha"], datos["hora"], datos["personas"])

        reservas = self._leer()
        existente = next(
            (r for r in reservas if r.get("idempotency_key") == clave and r["estado"] != "cancelada"),
            None,
        )
        if existente is not None:
            return Reserva(**existente)

        opciones = self.consultar_disponibilidad(
            datos["fecha"], datos["hora"], datos["personas"], datos["zona"] or None,
        )
        if not opciones:
            raise ValueError(
                f"Sin mesas para {datos['personas']} personas el {datos['fecha']} a las {datos['hora']}"
                + (f" en {datos['zona']}" if datos["zona"] else "")
            )

        reserva = Reserva(
            id=f"R-{uuid.uuid4().hex[:6].upper()}",
            nombre=datos["nombre"], telefono=datos["telefono"], fecha=datos["fecha"],
            hora=datos["hora"], personas=datos["personas"], zona=opciones[0].zona,
            mesa_id=opciones[0].mesa_id, notas=datos["notas"], idempotency_key=clave,
        )
        reservas.append(reserva.__dict__)
        self._escribir(reservas)
        return reserva

    def modificar_reserva(
        self, reserva_id: str, fecha: str | None = None, hora: str | None = None,
        personas: int | None = None,
    ) -> Reserva | None:
        """Modifica una reserva no cancelada y vuelve a comprobar disponibilidad.

        Conserva los valores omitidos y excluye la propia reserva de las mesas
        ocupadas; puede reasignar mesa y zona. Persiste estado modificada y devuelve
        Reserva, o None si no hay registro vigente; sin mesa lanza ValueError."""
        reservas = self._leer()
        for r in reservas:
            if r["id"] != reserva_id or r["estado"] == "cancelada":
                continue
            nueva_fecha = fecha or r["fecha"]
            nueva_hora = hora or r["hora"]
            nuevas_personas = personas or r["personas"]
            validar_cambio_turno(fecha=nueva_fecha, hora=nueva_hora, personas=nuevas_personas)

            # Verificacion doble: no se confirma un cambio sin mesa real detras.
            opciones = self.consultar_disponibilidad(
                nueva_fecha, nueva_hora, nuevas_personas, excluir_reserva_id=reserva_id
            )
            if not opciones:
                raise ValueError("No hay disponibilidad para ese cambio")

            r.update(
                fecha=nueva_fecha, hora=nueva_hora, personas=nuevas_personas,
                mesa_id=opciones[0].mesa_id, zona=opciones[0].zona, estado="modificada",
            )
            self._escribir(reservas)
            return Reserva(**r)
        return None

    def cancelar_reserva(self, reserva_id: str) -> Reserva | None:
        """Persiste estado cancelada para el id recibido y devuelve el registro.

        Devuelve None si no existe; cancelar libera la mesa para consultas posteriores."""
        reservas = self._leer()
        for r in reservas:
            if r["id"] == reserva_id:
                r["estado"] = "cancelada"
                self._escribir(reservas)
                return Reserva(**r)
        return None
