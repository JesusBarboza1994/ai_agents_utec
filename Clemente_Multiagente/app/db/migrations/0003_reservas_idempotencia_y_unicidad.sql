-- Cierra 2 brechas del gestor de reservas (ver ACUERDOS_EQUIPO.md 7.4):
--
-- 1. Idempotencia: un reintento de webhook de Twilio, un doble tap del
--    cliente o un timeout que reintenta puede mandar la misma solicitud de
--    reserva dos veces. `idempotency_key` es un hash determinista de
--    telefono+fecha+hora+personas (ver app/reservas/validaciones.py); el
--    indice unico parcial (solo sobre reservas activas, para no bloquear
--    una reserva nueva si la anterior con la misma clave fue cancelada)
--    es la garantia real bajo concurrencia -- el pre-chequeo en Python es
--    solo para no pelear el lock de mesas en el caso comun.
--
-- 2. Anti-doble-booking a nivel de base: hasta ahora la unica proteccion
--    contra reservar la misma mesa dos veces en el mismo turno era el
--    `SELECT ... FOR UPDATE` en la transaccion de la app. Este indice es
--    la red de seguridad si algun caller futuro (un script, una migracion
--    manual, un bug) escribe sin pasar por esa transaccion.
ALTER TABLE reservas ADD COLUMN IF NOT EXISTS idempotency_key TEXT NOT NULL DEFAULT '';

CREATE UNIQUE INDEX IF NOT EXISTS ux_reservas_idempotencia
    ON reservas (idempotency_key)
    WHERE estado <> 'cancelada' AND idempotency_key <> '';

CREATE UNIQUE INDEX IF NOT EXISTS ux_reservas_turno_mesa
    ON reservas (fecha, hora, mesa_id)
    WHERE estado <> 'cancelada';
