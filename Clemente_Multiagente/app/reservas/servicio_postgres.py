"""
Implementacion del Gestor de Reservas sobre PostgreSQL (ver ACUERDOS_EQUIPO.md 7.1).

Reemplaza a `ServicioReservasSQLite`: usa el mismo pool/migraciones de
`app/db/` que ya corre para customers/chats/messages, en vez de un `.db`
aparte por maquina.

Mismas reglas de negocio que las versiones anteriores (turnos validos, una
mesa reservada bloquea su turno completo, mesa mas ajustada primero) para
que `tests/test_reservas.py` pase igual contra las tres implementaciones.

Bloqueo de escritores: en sqlite era `BEGIN IMMEDIATE` (todo el archivo).
Aca se hace `SELECT ... FOR UPDATE` sobre las filas de `mesas` candidatas al
turno, dentro de la misma transaccion que la lectura de disponibilidad y el
INSERT/UPDATE de la reserva -- dos escrituras simultaneas sobre el mismo
turno se serializan porque la segunda espera a que la primera libere el
lock de esas filas de `mesas`.

El catalogo de mesas (`datos/mesas.json`) se sigue subiendo con
`python -m app.reservas.seed`.
"""

import uuid
from datetime import datetime

import psycopg2.errors

from ..contratos import OpcionDisponibilidad, Reserva
from ..db.connection import connection
from .validaciones import TURNOS_VALIDOS, clave_idempotencia, validar_cambio_turno, validar_datos_reserva


class ServicioReservasPostgres:
    """Implementa el contrato de reservas en Postgres con bloqueo transaccional de mesas y consultas parametrizadas."""
    def consultar_disponibilidad(
        self, fecha: str, hora: str, personas: int, zona: str | None = None,
        excluir_reserva_id: str | None = None,
    ) -> list[OpcionDisponibilidad]:
        """Devuelve mesas libres del turno y capacidad solicitados; un horario no valido devuelve lista vacia."""
        if hora not in TURNOS_VALIDOS:
            return []

        with connection() as conn, conn.cursor() as cur:
            opciones = self._opciones_libres(
                cur, fecha, hora, personas, zona, excluir_reserva_id
            )
        return opciones

    def obtener_reserva(self, reserva_id: str) -> Reserva | None:
        """Consulta una reserva por identificador; devuelve None si no existe. La propiedad se valida en la capa de autorizacion."""
        with connection() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT r.id, r.nombre, r.telefono, r.fecha, r.hora, r.personas, m.zona, "
                "r.mesa_id, r.estado, r.notas, r.creada FROM reservas r "
                "JOIN mesas m ON m.id = r.mesa_id WHERE r.id = %s",
                (reserva_id,),
            )
            fila = cur.fetchone()
        return self._construir(fila) if fila else None

    def buscar_reservas_de(self, telefono: str) -> list[Reserva]:
        """Consulta reservas del telefono indicado; la capa de herramientas limita el acceso a la sesion propietaria."""
        with connection() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT r.id, r.nombre, r.telefono, r.fecha, r.hora, r.personas, m.zona, "
                "r.mesa_id, r.estado, r.notas, r.creada FROM reservas r "
                "JOIN mesas m ON m.id = r.mesa_id WHERE r.telefono = %s",
                (telefono,),
            )
            filas = cur.fetchall()
        return [self._construir(f) for f in filas]

    # ------------------------------ escrituras -----------------------------
    # El `SELECT ... FOR UPDATE` sobre `mesas` toma el lock antes de leer
    # disponibilidad: si dos peticiones llegan a la vez, la segunda espera a
    # que la primera confirme o falle, en vez de que ambas vean la mesa
    # libre y se pisen.

    def crear_reserva(
        self, nombre: str, telefono: str, fecha: str, hora: str,
        personas: int, zona: str, notas: str = "",
    ) -> Reserva:
        """Valida y sanea los datos y crea la reserva bajo lock de mesas; una clave de idempotencia repetida devuelve la existente sin duplicar ni bajo concurrencia real."""
        datos = validar_datos_reserva(
            nombre=nombre, telefono=telefono, fecha=fecha, hora=hora,
            personas=personas, zona=zona, notas=notas,
        )
        clave = clave_idempotencia(datos["telefono"], datos["fecha"], datos["hora"], datos["personas"])

        # Pre-chequeo barato, fuera del lock de mesas: cubre el caso comun
        # (reintento secuencial) sin pelear el lock. La garantia real bajo
        # concurrencia real es el indice unico parcial `ux_reservas_idempotencia`
        # (migracion 0003) -- si dos peticiones identicas pasan este SELECT a
        # la vez, el INSERT de la segunda revienta con UniqueViolation y el
        # except mas abajo la resuelve igual, sin duplicar.
        existente = self._reserva_activa_por_clave(clave)
        if existente is not None:
            return existente

        try:
            with connection() as conn, conn.cursor() as cur:
                opciones = self._opciones_libres(cur, datos["fecha"], datos["hora"], datos["personas"], datos["zona"] or None, None, lock=True)
                if not opciones:
                    raise ValueError(
                        f"Sin mesas para {datos['personas']} personas el {datos['fecha']} a las {datos['hora']}"
                        + (f" en {datos['zona']}" if datos["zona"] else "")
                    )

                reserva = Reserva(
                    id=f"R-{uuid.uuid4().hex[:6].upper()}",
                    nombre=datos["nombre"], telefono=datos["telefono"], fecha=datos["fecha"],
                    hora=datos["hora"], personas=datos["personas"], zona=opciones[0].zona,
                    mesa_id=opciones[0].mesa_id, notas=datos["notas"],
                    creada=datetime.now().isoformat(timespec="seconds"), idempotency_key=clave,
                )
                cur.execute(
                    "INSERT INTO reservas (id, nombre, telefono, fecha, hora, personas, "
                    "mesa_id, estado, notas, creada, idempotency_key) "
                    "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                    (reserva.id, reserva.nombre, reserva.telefono, reserva.fecha,
                     reserva.hora, reserva.personas, reserva.mesa_id,
                     reserva.estado, reserva.notas, reserva.creada, reserva.idempotency_key),
                )
                return reserva
        except psycopg2.errors.UniqueViolation:
            # Dos peticiones identicas pasaron el pre-chequeo a la vez: una
            # gano el indice unico, esta perdio. No es un error para quien
            # llamo -- es el mismo pedido, se devuelve la reserva que ya quedo.
            existente = self._reserva_activa_por_clave(clave)
            if existente is not None:
                return existente
            raise

    def _reserva_activa_por_clave(self, clave: str) -> Reserva | None:
        """Busca por idempotency_key una reserva no cancelada; None si no hay ninguna."""
        with connection() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT r.id, r.nombre, r.telefono, r.fecha, r.hora, r.personas, m.zona, "
                "r.mesa_id, r.estado, r.notas, r.creada FROM reservas r "
                "JOIN mesas m ON m.id = r.mesa_id "
                "WHERE r.idempotency_key = %s AND r.estado != 'cancelada'",
                (clave,),
            )
            fila = cur.fetchone()
        return self._construir(fila) if fila else None

    def modificar_reserva(
        self, reserva_id: str, fecha: str | None = None, hora: str | None = None,
        personas: int | None = None,
    ) -> Reserva | None:
        """Bloquea la reserva activa y mesas candidatas, verifica disponibilidad y actualiza fecha, turno y capacidad."""
        with connection() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT r.id, r.nombre, r.telefono, r.fecha, r.hora, r.personas, m.zona, "
                "r.mesa_id, r.estado, r.notas, r.creada FROM reservas r "
                "JOIN mesas m ON m.id = r.mesa_id "
                "WHERE r.id = %s AND r.estado != 'cancelada' FOR UPDATE",
                (reserva_id,),
            )
            fila = cur.fetchone()
            if fila is None:
                return None
            actual = self._construir(fila)

            nueva_fecha = fecha or actual.fecha
            nueva_hora = hora or actual.hora
            nuevas_personas = personas or actual.personas
            validar_cambio_turno(fecha=nueva_fecha, hora=nueva_hora, personas=nuevas_personas)

            opciones = self._opciones_libres(
                cur, nueva_fecha, nueva_hora, nuevas_personas,
                None, reserva_id, lock=True,
            )
            if not opciones:
                raise ValueError("No hay disponibilidad para ese cambio")

            cur.execute(
                "UPDATE reservas SET fecha=%s, hora=%s, personas=%s, mesa_id=%s, "
                "estado='modificada' WHERE id=%s",
                (nueva_fecha, nueva_hora, nuevas_personas, opciones[0].mesa_id, reserva_id),
            )
            cur.execute(
                "SELECT r.id, r.nombre, r.telefono, r.fecha, r.hora, r.personas, m.zona, "
                "r.mesa_id, r.estado, r.notas, r.creada FROM reservas r "
                "JOIN mesas m ON m.id = r.mesa_id WHERE r.id = %s",
                (reserva_id,),
            )
            return self._construir(cur.fetchone())

    def cancelar_reserva(self, reserva_id: str) -> Reserva | None:
        """Bloquea y marca una reserva cancelada; devuelve None si no existe."""
        with connection() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT id FROM reservas WHERE id = %s FOR UPDATE", (reserva_id,)
            )
            if cur.fetchone() is None:
                return None
            cur.execute("UPDATE reservas SET estado='cancelada' WHERE id=%s", (reserva_id,))
            cur.execute(
                "SELECT r.id, r.nombre, r.telefono, r.fecha, r.hora, r.personas, m.zona, "
                "r.mesa_id, r.estado, r.notas, r.creada FROM reservas r "
                "JOIN mesas m ON m.id = r.mesa_id WHERE r.id = %s",
                (reserva_id,),
            )
            return self._construir(cur.fetchone())

    # -------------------------------- interno -------------------------------

    def _opciones_libres(
        self, cur, fecha: str, hora: str, personas: int,
        zona: str | None, excluir_reserva_id: str | None, lock: bool = False,
    ) -> list[OpcionDisponibilidad]:
        """Filtra mesas por ocupacion, capacidad y zona; lock=True bloquea filas durante las escrituras."""
        cur.execute(
            "SELECT id, zona, capacidad FROM mesas ORDER BY capacidad ASC"
            + (" FOR UPDATE" if lock else "")
        )
        mesas = cur.fetchall()

        cur.execute(
            "SELECT mesa_id FROM reservas WHERE fecha = %s AND hora = %s "
            "AND estado != 'cancelada' AND id != %s",
            (fecha, hora, excluir_reserva_id or ""),
        )
        ocupadas = {row[0] for row in cur.fetchall()}

        opciones = []
        for mesa_id, mesa_zona, capacidad in mesas:
            if mesa_id in ocupadas:
                continue
            if capacidad < personas:
                continue
            if zona and mesa_zona != zona:
                continue
            opciones.append(
                OpcionDisponibilidad(
                    fecha=fecha, hora=hora, zona=mesa_zona,
                    mesa_id=mesa_id, capacidad=capacidad,
                )
            )
        return opciones

    @staticmethod
    def _construir(fila) -> Reserva:
        """Convierte una fila SQL en el contrato Reserva sin consultar servicios externos."""
        (id_, nombre, telefono, fecha, hora, personas, zona,
         mesa_id, estado, notas, creada) = fila
        return Reserva(
            id=id_, nombre=nombre, telefono=telefono, fecha=fecha, hora=hora,
            personas=personas, zona=zona, mesa_id=mesa_id, estado=estado,
            notas=notas, creada=creada,
        )
