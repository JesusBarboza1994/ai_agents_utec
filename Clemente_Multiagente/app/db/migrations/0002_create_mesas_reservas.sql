-- Mesas: catalogo fijo del local. Fuente de verdad operativa
-- (app/reservas/datos/mesas.json); el agente nunca las inventa.
-- `seed.py` hace el upsert de este catalogo, no esta migracion.
CREATE TABLE IF NOT EXISTS mesas (
    id TEXT PRIMARY KEY,
    zona TEXT NOT NULL,
    capacidad INTEGER NOT NULL
);

-- Reservas: fecha/hora quedan como TEXT porque son turnos de negocio fijos
-- ("2026-09-12", "20:00"), no timestamps arbitrarios -- mismo shape que la
-- version JSON/SQLite que reemplaza, para no arrastrar bugs de conversion.
CREATE TABLE IF NOT EXISTS reservas (
    id TEXT PRIMARY KEY,
    nombre TEXT NOT NULL,
    telefono TEXT NOT NULL,
    fecha TEXT NOT NULL,
    hora TEXT NOT NULL,
    personas INTEGER NOT NULL,
    zona TEXT NOT NULL,
    mesa_id TEXT NOT NULL REFERENCES mesas(id),
    estado TEXT NOT NULL DEFAULT 'confirmada',
    notas TEXT NOT NULL DEFAULT '',
    creada TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_reservas_turno ON reservas (fecha, hora, mesa_id);
CREATE INDEX IF NOT EXISTS idx_reservas_telefono ON reservas (telefono);
