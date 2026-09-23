-- `reservas.zona` duplicaba `mesas.zona`: toda reserva tiene mesa_id, y la
-- mesa ya sabe su zona -- guardarla dos veces solo abria la puerta a que
-- quedaran desincronizadas (p.ej. tras mover una mesa de zona en `mesas`).
-- La zona de una reserva se obtiene ahora con JOIN a `mesas` (ver
-- app/reservas/servicio_postgres.py). El contrato `Reserva.zona` (ver
-- app/contratos.py) no cambia: lo sigue llevando el dataclass, solo cambia
-- de donde sale el valor.
ALTER TABLE reservas DROP COLUMN zona;
