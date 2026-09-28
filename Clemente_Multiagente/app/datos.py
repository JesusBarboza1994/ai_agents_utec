"""Dónde guarda Clemente los archivos que escribe: dueños de reservas, revisiones pendientes, reclamos de respaldo, etc."""

import os
from pathlib import Path


def carpeta_de_datos(por_defecto: Path) -> Path:
    """Carpeta para esos archivos: CLEMENTE_DATOS_DIR si esta definida y, si no, `por_defecto` (junto al codigo).

    En Azure la carpeta de la aplicacion se borra en cada reinicio o despliegue: apuntar CLEMENTE_DATOS_DIR a un
    volumen persistente (por ejemplo /mnt/datos) conserva quien es duena de cada reserva y las revisiones pendientes."""
    elegida = os.getenv("CLEMENTE_DATOS_DIR", "").strip()
    if not elegida:
        return por_defecto
    carpeta = Path(elegida)
    carpeta.mkdir(parents=True, exist_ok=True)
    return carpeta
