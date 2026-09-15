"""
Genera `datos/clemente.db` desde cero a partir de `datos/mesas.json`.

Se corre en cada maquina (desarrollo) o una vez en la maquina de la
demostracion. El `.db` esta en `.gitignore`: nadie lo sube, y correr este
script deja a cualquiera con el mismo punto de partida.

Uso:
    python -m app.reservas.seed              # solo mesas
    python -m app.reservas.seed --con-ejemplos  # + un par de reservas de muestra
"""

import argparse
import json
import sqlite3
import sys
from pathlib import Path

CARPETA_DATOS = Path(__file__).parent / "datos"
ARCHIVO_MESAS = CARPETA_DATOS / "mesas.json"
ARCHIVO_DB = CARPETA_DATOS / "clemente.db"

_ESQUEMA = """
CREATE TABLE mesas (
    id TEXT PRIMARY KEY,
    zona TEXT NOT NULL,
    capacidad INTEGER NOT NULL
);
CREATE TABLE reservas (
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
CREATE INDEX idx_reservas_turno ON reservas(fecha, hora, mesa_id);
CREATE INDEX idx_reservas_telefono ON reservas(telefono);
"""

_EJEMPLOS = [
    # id, nombre, telefono, fecha, hora, personas, zona, mesa_id, estado, notas, creada
    ("R-EJEMP1", "Marcela Rios", "999888777", "2026-09-20", "20:00", 4,
     "salon", "M03", "confirmada", "", "2026-09-14T10:00:00"),
    ("R-EJEMP2", "Diego Flores", "999111222", "2026-09-21", "13:00", 2,
     "terraza", "T01", "confirmada", "cumpleanos", "2026-09-14T10:05:00"),
]


def generar_en(archivo_db: Path, con_ejemplos: bool) -> None:
    archivo_db.parent.mkdir(parents=True, exist_ok=True)
    if archivo_db.exists():
        archivo_db.unlink()

    mesas = json.loads(ARCHIVO_MESAS.read_text(encoding="utf-8"))["mesas"]

    con = sqlite3.connect(archivo_db)
    try:
        con.executescript(_ESQUEMA)
        con.executemany(
            "INSERT INTO mesas (id, zona, capacidad) VALUES (?, ?, ?)",
            [(m["id"], m["zona"], m["capacidad"]) for m in mesas],
        )
        if con_ejemplos:
            con.executemany(
                "INSERT INTO reservas (id, nombre, telefono, fecha, hora, personas, "
                "zona, mesa_id, estado, notas, creada) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                _EJEMPLOS,
            )
        con.commit()
    finally:
        con.close()

    return len(mesas)


def generar(con_ejemplos: bool) -> None:
    n_mesas = generar_en(ARCHIVO_DB, con_ejemplos)
    print(f"OK: {ARCHIVO_DB} creado con {n_mesas} mesas"
          + (f" y {len(_EJEMPLOS)} reservas de ejemplo" if con_ejemplos else ""))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--con-ejemplos", action="store_true",
                         help="agrega un par de reservas de muestra para probar el chat")
    args = parser.parse_args(sys.argv[1:])
    generar(con_ejemplos=args.con_ejemplos)
