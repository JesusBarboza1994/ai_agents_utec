-- Hasta esta version, modificar una reserva cambiaba fecha, hora o personas pero
-- dejaba `idempotency_key` con los datos de ANTES. Dos efectos:
--   1. Pedir de nuevo la reserva ya modificada no la encontraba y, con CONFIRMO,
--      creaba otra en el mismo turno (otra mesa).
--   2. Pedir el turno viejo devolvia la modificada como si fuera esa.
-- El codigo ya recalcula la clave al modificar; esta migracion corrige las filas
-- que quedaron con la clave vieja.
--
-- La clave es la de app/reservas/validaciones.py (clave_idempotencia):
-- sha256 de "telefono|fecha|hora|personas", primeros 32 caracteres en hex.
--
-- Corre al arrancar la app, asi que no puede fallar por un choque del indice
-- unico: primero se vacian las claves a corregir (el indice no mira las vacias)
-- y despues cada clave nueva se asigna a UNA sola fila, la mas antigua, y solo
-- si ninguna otra reserva activa la tiene ya. Una fila que no puede tomarla es
-- un duplicado que ya existe: queda con clave vacia y se revisa a mano.

CREATE TEMP TABLE _claves_corregidas ON COMMIT DROP AS
SELECT id, creada,
       left(encode(sha256(convert_to(btrim(telefono) || '|' || fecha || '|' || hora || '|' || personas::text,
                                     'UTF8')), 'hex'), 32) AS nueva
FROM reservas
WHERE estado <> 'cancelada' AND idempotency_key <> '';

DELETE FROM _claves_corregidas c USING reservas r
WHERE r.id = c.id AND r.idempotency_key = c.nueva;

UPDATE reservas SET idempotency_key = ''
WHERE id IN (SELECT id FROM _claves_corregidas);

UPDATE reservas r SET idempotency_key = k.nueva
FROM (SELECT DISTINCT ON (nueva) id, nueva FROM _claves_corregidas ORDER BY nueva, creada) k
WHERE r.id = k.id
  AND NOT EXISTS (SELECT 1 FROM reservas o
                  WHERE o.idempotency_key = k.nueva AND o.estado <> 'cancelada');
