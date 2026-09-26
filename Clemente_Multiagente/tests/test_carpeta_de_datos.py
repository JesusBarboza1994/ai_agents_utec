"""Los archivos que Clemente escribe van a la carpeta que diga CLEMENTE_DATOS_DIR y sobreviven a un reinicio; sin modelo."""
import os
import subprocess
import sys
from pathlib import Path

import pytest

from app.datos import carpeta_de_datos

RAIZ = Path(__file__).resolve().parent.parent

# (modulo, constante con la ruta del archivo): todo lo que Clemente escribe en disco.
ARCHIVOS = [
    ("app.agentes.autorizacion", "ARCHIVO"),
    ("app.agentes.memoria", "ARCHIVO"),
    ("app.incidencias.servicio_json", "ARCHIVO"),
    ("app.observabilidad.trazas", "ARCHIVO_CONVERSACIONES"),
    ("app.reservas.servicio_json", "ARCHIVO_RESERVAS"),
    ("app.orquestador.grafo", "ARCHIVO_REVISIONES"),
]


def _python(codigo, datos_dir=None):
    """Corre `codigo` en un Python nuevo (como un reinicio de Clemente), con o sin CLEMENTE_DATOS_DIR, y devuelve su salida."""
    entorno = {**os.environ, "CLEMENTE_DATABASE_URL": ""}
    entorno.pop("CLEMENTE_DATOS_DIR", None)
    if datos_dir:
        entorno["CLEMENTE_DATOS_DIR"] = str(datos_dir)
    resultado = subprocess.run([sys.executable, "-c", codigo], cwd=RAIZ, env=entorno, capture_output=True, text=True, timeout=120)
    assert resultado.returncode == 0, resultado.stderr[-600:]
    return resultado.stdout.strip().splitlines()[-1]


def test_sin_la_variable_se_usa_la_carpeta_de_siempre(tmp_path, monkeypatch):
    """Sin CLEMENTE_DATOS_DIR nada cambia: se devuelve la carpeta por defecto."""
    monkeypatch.delenv("CLEMENTE_DATOS_DIR", raising=False)
    assert carpeta_de_datos(tmp_path / "datos") == tmp_path / "datos"


def test_con_la_variable_se_usa_esa_carpeta_y_se_crea_si_falta(tmp_path, monkeypatch):
    """Con CLEMENTE_DATOS_DIR se usa esa carpeta, y se crea si todavia no existe."""
    destino = tmp_path / "volumen" / "datos"
    monkeypatch.setenv("CLEMENTE_DATOS_DIR", str(destino))
    assert carpeta_de_datos(tmp_path / "otra") == destino and destino.is_dir()


@pytest.mark.parametrize("modulo, constante", ARCHIVOS)
def test_cada_archivo_que_clemente_escribe_respeta_la_carpeta_de_datos(tmp_path, modulo, constante):
    """Ningun archivo queda escrito dentro de la carpeta de la aplicacion cuando se define CLEMENTE_DATOS_DIR."""
    ruta = _python(f"import importlib; print(importlib.import_module('{modulo}').{constante})", tmp_path)
    assert Path(ruta).parent == tmp_path


def test_el_estado_de_las_reservas_sobrevive_a_un_reinicio(tmp_path):
    """Quien es duena de una reserva (lo que se pierde al reiniciar un contenedor) se conserva en la carpeta de datos."""
    _python("from app.agentes import autorizacion as a; a.vincular('web-duena', 'R-SOBREVIVE'); print('ok')", tmp_path)
    assert _python("from app.agentes import autorizacion as a; print(a.es_propietario('web-duena', 'R-SOBREVIVE'))", tmp_path) == "True"
    assert _python("from app.agentes import autorizacion as a; print(a.es_propietario('otra', 'R-SOBREVIVE'))", tmp_path) == "False"
