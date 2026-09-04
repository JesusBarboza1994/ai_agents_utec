"""
Registro de incidencias sobre archivo JSON.

Lo importante del Entregable 01: una incidencia no se cierra porque la
conversacion termino. Nace con estado, responsable y plazo, y solo el staff
la cierra. Este modulo garantiza esa parte -- el agente no puede cerrarla
por su cuenta porque su tool solo llama a `crear_incidencia` y `consultar`.
"""

import json
import uuid
from datetime import datetime
from pathlib import Path

from ..contratos import Incidencia

ARCHIVO = Path(__file__).parent / "datos" / "incidencias.json"

# Plazo de atencion por tipo, en horas (regla operativa, no del modelo).
PLAZOS_HORAS = {"espera": 4, "servicio": 8, "producto": 8, "reserva": 4, "otro": 24}


class ServicioIncidenciasJSON:
    def __init__(self, archivo: Path | None = None) -> None:
        self.archivo = archivo or ARCHIVO

    def _leer(self) -> list[dict]:
        if not self.archivo.exists():
            return []
        return json.loads(self.archivo.read_text(encoding="utf-8"))

    def _escribir(self, incidencias: list[dict]) -> None:
        self.archivo.parent.mkdir(parents=True, exist_ok=True)
        self.archivo.write_text(
            json.dumps(incidencias, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def crear_incidencia(
        self, sesion_id: str, descripcion: str, tipo: str = "otro",
        reserva_id: str | None = None,
    ) -> Incidencia:
        incidencia = Incidencia(
            id=f"I-{uuid.uuid4().hex[:6].upper()}",
            sesion_id=sesion_id,
            descripcion=descripcion,
            tipo=tipo if tipo in PLAZOS_HORAS else "otro",
            reserva_id=reserva_id,
            plazo_horas=PLAZOS_HORAS.get(tipo, 24),
        )
        registro = self._leer()
        registro.append(incidencia.__dict__)
        self._escribir(registro)
        return incidencia

    def listar_incidencias(self, estado: str | None = None) -> list[Incidencia]:
        return [
            Incidencia(**i) for i in self._leer()
            if estado is None or i["estado"] == estado
        ]

    def cerrar_incidencia(self, incidencia_id: str, nota_cierre: str = "") -> Incidencia | None:
        """Solo para el panel del staff: ningun agente tiene tool para esto."""
        registro = self._leer()
        for i in registro:
            if i["id"] == incidencia_id:
                i["estado"] = "cerrada"
                i["descripcion"] += f"\n[cierre {datetime.now():%Y-%m-%d %H:%M}] {nota_cierre}"
                self._escribir(registro)
                return Incidencia(**i)
        return None
