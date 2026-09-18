-- Estado de los agentes (Christian, Jean): lo que hasta el PR #10 vivia en
-- archivos del proceso (app/agentes/datos/*.sqlite3 y *.json) y se perdia en
-- cada redeploy. Prefijo `agentes_` para no interferir con customers/chats/
-- messages (Jesus) ni mesas/reservas (Marc). Mismo pool y mismo mecanismo de
-- migraciones que esas tablas (app/db/connection.py, app/db/migrate.py).

-- Propiedad: que sesion (identidad del canal) puede leer/modificar que reserva.
-- Se escribe solo cuando el servidor ejecuto la creacion; nunca por telefono dicho.
CREATE TABLE IF NOT EXISTS agentes_propietarios (
    reserva TEXT PRIMARY KEY,
    sesion  TEXT NOT NULL,
    creada  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_agentes_propietarios_sesion ON agentes_propietarios (sesion);

-- Propuesta pendiente de confirmacion: una por sesion, token de un uso con vigencia.
-- Se consume con DELETE ... RETURNING: dos replicas no pueden ejecutarla dos veces.
CREATE TABLE IF NOT EXISTS agentes_propuestas (
    sesion TEXT PRIMARY KEY,
    codigo TEXT NOT NULL,
    accion TEXT NOT NULL,
    datos  JSONB NOT NULL,
    vence  TIMESTAMPTZ NOT NULL
);

-- Perfil auxiliar del cliente (nombre, alergias, preferencias). Clave = identidad
-- del servidor (telefono autenticado del canal o sesion), no un telefono declarado.
CREATE TABLE IF NOT EXISTS agentes_perfiles (
    clave       TEXT PRIMARY KEY,
    perfil      JSONB NOT NULL,
    actualizado TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Cola de revision humana (HITL): solicitudes pausadas a la espera del personal.
CREATE TABLE IF NOT EXISTS agentes_revisiones (
    sesion    TEXT PRIMARY KEY,
    canal     TEXT NOT NULL,
    solicitud JSONB NOT NULL,
    creada    TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Resolucion HITL que todavia no se le entrego al cliente: el panel del personal
-- no envia WhatsApp; se entrega en el siguiente turno del cliente y se borra.
CREATE TABLE IF NOT EXISTS agentes_resoluciones (
    sesion   TEXT PRIMARY KEY,
    decision TEXT NOT NULL,
    texto    TEXT NOT NULL,
    creada   TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Continuidad del hilo: ultimo agente que atendio y ticket abierto de la sesion.
CREATE TABLE IF NOT EXISTS agentes_continuidad (
    sesion             TEXT PRIMARY KEY,
    ultimo_agente      TEXT NOT NULL DEFAULT '',
    incidencia_abierta TEXT,
    actualizado        TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Rechazos recientes por sesion (autorizacion denegada, confirmacion invalida):
-- alimentan la degradacion por abuso. Se consultan por ventana de tiempo.
CREATE TABLE IF NOT EXISTS agentes_rechazos (
    id      BIGSERIAL PRIMARY KEY,
    sesion  TEXT NOT NULL,
    motivo  TEXT NOT NULL,
    momento TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_agentes_rechazos_sesion ON agentes_rechazos (sesion, momento);
