"""
Implementacion del Gestor de Reservas sobre SQLite (ver ACUERDOS_EQUIPO.md 7.1).

Reemplaza a `ServicioReservasJSON` para la demostracion: dos escrituras
simultaneas (el webhook de WhatsApp y el webchat pueden llegar a la vez)
no se pisan porque cada `crear_reserva`/`modificar_reserva` corre dentro de
una transaccion `BEGIN IMMEDIATE`, que serializa a los escritores.

Mismas reglas de negocio que la version JSON (turnos validos, una mesa
reservada bloquea su turno completo, mesa mas ajustada primero) para que
`tests/test_reservas.py` pase igual contra las dos implementaciones.

El archivo `.db` no se sube a git: lo genera `seed.py` a partir de
`datos/mesas.json`, que sigue siendo la unica fuente de verdad sobre las
mesas del local (el agente no las inventa).
"""

import sqlite3
import uuid
from pathlib import Path

from ..contratos import OpcionDisponibilidad, Reserva

CARPETA_DATOS = Path(__file__).parent / "datos"
ARCHIVO_DB = CARPETA_DATOS / "clemente.db"

TURNOS_VALIDOS = ["12:00", "13:00", "14:00", "19:00", "20:00", "21:00", "22:00"]

_ESQUEMA = """
CREATE TABLE IF NOT EXISTS mesas (
    id TEXT PRIMARY KEY,
    zona TEXT NOT NULL,
    capacidad INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS reservas (
    id TEXT PRIMARY KEY,
    nombre TEXT NOT NULL,
    telefono TEXT NOT NULL,
    fecha TEXT NOT NULL,
    hora TEXT NOT NULL,
    personas INTEGER NOT NULL,
    zona TEXT NOT NULL,
    mesa_id TEXT NOT NULL,
    estado TEXT NOT NULL,
    notas TEXT NOT NULL DEFAULT '',
    creada TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_reservas_turno ON reservas(fecha, hora, mesa_id);
CREATE INDEX IF NOT EXISTS idx_reservas_telefono ON reservas(telefono);
"""


class ServicioReservasSQLite:
    def __init__(self, archivo_db: Path | None = None) -> None:
        self.archivo_db = archivo_db or ARCHIVO_DB
        if not self.archivo_db.exists():
            raise FileNotFoundError(
                f"No existe {self.archivo_db}. Corre `python -m app.reservas.seed` primero."
            )

    def _conectar(self) -> sqlite3.Connection:
        con = sqlite3.connect(self.archivo_db, timeout=10)
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA foreign_keys = ON")
        return con

    # ------------------------------ consultas ------------------------------

    def consultar_disponibilidad(
        self, fecha: str, hora: str, personas: int, zona: str | None = None,
        excluir_reserva_id: str | None = None,
    ) -> list[OpcionDisponibilidad]:
        if hora not in TURNOS_VALIDOS:
            return []

        with self._conectar() as con:
            ocupadas = {
                r["mesa_id"]
                for r in con.execute(
                    "SELECT mesa_id FROM reservas WHERE fecha=? AND hora=? "
                    "AND estado != 'cancelada' AND id != ?",
                    (fecha, hora, excluir_reserva_id or ""),
                )
            }
            mesas = con.execute(
                "SELECT id, zona, capacidad FROM mesas ORDER BY capacidad ASC"
            ).fetchall()

        opciones = []
        for mesa in mesas:
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
        return opciones

    def obtener_reserva(self, reserva_id: str) -> Reserva | None:
        with self._conectar() as con:
            fila = con.execute(
                "SELECT * FROM reservas WHERE id=?", (reserva_id,)
            ).fetchone()
        return Reserva(**dict(fila)) if fila else None

    def buscar_reservas_de(self, telefono: str) -> list[Reserva]:
        with self._conectar() as con:
            filas = con.execute(
                "SELECT * FROM reservas WHERE telefono=?", (telefono,)
            ).fetchall()
        return [Reserva(**dict(f)) for f in filas]

    # ------------------------------ escrituras -----------------------------
    # `BEGIN IMMEDIATE` toma el lock de escritura antes de leer disponibilidad:
    # si dos peticiones llegan a la vez, la segunda espera a que la primera
    # confirme o falle, en vez de que ambas vean la mesa libre y se pisen.

    def crear_reserva(
        self, nombre: str, telefono: str, fecha: str, hora: str,
        personas: int, zona: str, notas: str = "",
    ) -> Reserva:
        con = self._conectar()
        try:
            con.execute("BEGIN IMMEDIATE")
            opciones = self.consultar_disponibilidad(fecha, hora, personas, zona)
            if not opciones:
                con.rollback()
                raise ValueError(
                    f"Sin mesas para {personas} personas el {fecha} a las {hora}"
                    + (f" en {zona}" if zona else "")
                )
            reserva = Reserva(
                id=f"R-{uuid.uuid4().hex[:6].upper()}",
                nombre=nombre, telefono=telefono, fecha=fecha, hora=hora,
                personas=personas, zona=opciones[0].zona, mesa_id=opciones[0].mesa_id,
                notas=notas,
            )
            con.execute(
                "INSERT INTO reservas (id, nombre, telefono, fecha, hora, personas, "
                "zona, mesa_id, estado, notas, creada) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (reserva.id, reserva.nombre, reserva.telefono, reserva.fecha,
                 reserva.hora, reserva.personas, reserva.zona, reserva.mesa_id,
                 reserva.estado, reserva.notas, reserva.creada),
            )
            con.commit()
            return reserva
        finally:
            con.close()

    def modificar_reserva(
        self, reserva_id: str, fecha: str | None = None, hora: str | None = None,
        personas: int | None = None,
    ) -> Reserva | None:
        con = self._conectar()
        try:
            con.execute("BEGIN IMMEDIATE")
            fila = con.execute(
                "SELECT * FROM reservas WHERE id=? AND estado != 'cancelada'",
                (reserva_id,),
            ).fetchone()
            if fila is None:
                con.rollback()
                return None

            nueva_fecha = fecha or fila["fecha"]
            nueva_hora = hora or fila["hora"]
            nuevas_personas = personas or fila["personas"]

            opciones = self.consultar_disponibilidad(
                nueva_fecha, nueva_hora, nuevas_personas, excluir_reserva_id=reserva_id
            )
            if not opciones:
                con.rollback()
                raise ValueError("No hay disponibilidad para ese cambio")

            con.execute(
                "UPDATE reservas SET fecha=?, hora=?, personas=?, mesa_id=?, zona=?, "
                "estado='modificada' WHERE id=?",
                (nueva_fecha, nueva_hora, nuevas_personas,
                 opciones[0].mesa_id, opciones[0].zona, reserva_id),
            )
            con.commit()
            return self.obtener_reserva(reserva_id)
        finally:
            con.close()

    def cancelar_reserva(self, reserva_id: str) -> Reserva | None:
        con = self._conectar()
        try:
            con.execute("BEGIN IMMEDIATE")
            fila = con.execute(
                "SELECT * FROM reservas WHERE id=?", (reserva_id,)
            ).fetchone()
            if fila is None:
                con.rollback()
                return None
            con.execute("UPDATE reservas SET estado='cancelada' WHERE id=?", (reserva_id,))
            con.commit()
            return self.obtener_reserva(reserva_id)
        finally:
            con.close()
