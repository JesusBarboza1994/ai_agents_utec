"""Audita docstrings del proyecto sin importar la app ni llamar servicios externos.

Desde la carpeta Clemente_Multiagente:
    python docs/verificar_documentacion.py
    python docs/verificar_documentacion.py --indice docs/INDICE_CODIGO.md

Comprueba presencia de descripciones, sintaxis y cobertura de modulos, clases,
metodos y funciones, incluidas definiciones anidadas. No evalua automaticamente
la exactitud de la prosa ni sustituye las pruebas funcionales.
"""

import argparse
import ast
import os
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
TIPOS = (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)


def archivos_python(raiz: Path) -> list[Path]:
    """Enumera codigo propio de entrada, app, servicio, pruebas y utilidades documentales.

    Excluye caches, carpetas ocultas y dependencias; no recorre archivos de
    datos ni copias de otros proyectos del workspace.
    """
    archivos = list(raiz.glob('*.py'))
    for carpeta in ('app', 'guardrails_service', 'tests', 'docs'):
        archivos.extend((raiz / carpeta).rglob('*.py'))
    return sorted(p for p in archivos if not any(
        parte.startswith('.') or parte == '__pycache__'
        for parte in p.relative_to(raiz).parts
    ))


def definiciones(arbol: ast.AST, prefijo: str = '') -> list[tuple[str, ast.AST]]:
    """Devuelve nombres cualificados y nodos de clases y funciones en orden del codigo.

    Recorre tambien definiciones dentro de pruebas, closures, bloques if y
    clases, conservando el contexto del nombre para distinguir metodos.
    """
    salida = []
    for nodo in ast.iter_child_nodes(arbol):
        nombre = prefijo
        if isinstance(nodo, TIPOS):
            nombre = f'{prefijo}.{nodo.name}' if prefijo else nodo.name
            salida.append((nombre, nodo))
        salida.extend(definiciones(nodo, nombre))
    return salida


def auditar(raiz: Path) -> tuple[list[dict], list[str]]:
    """Lee y compila cada fuente y devuelve su inventario y los problemas detectados.

    Solo compila en memoria, sin ejecutar ni producir pyc. Reporta errores
    de lectura/sintaxis y docstrings ausentes o vacios por archivo y linea.
    """
    inventario, problemas = [], []
    for ruta in archivos_python(raiz):
        relativa = ruta.relative_to(raiz).as_posix()
        try:
            fuente = ruta.read_text(encoding='utf-8-sig')
            arbol = ast.parse(fuente, filename=relativa)
            compile(fuente, relativa, 'exec')
        except (OSError, UnicodeError, SyntaxError) as error:
            problemas.append(f'{relativa}: {error}')
            continue
        elementos = [('modulo', arbol), *definiciones(arbol)]
        registros = []
        for nombre, nodo in elementos:
            doc = ast.get_docstring(nodo) or ''
            linea = getattr(nodo, 'lineno', 1)
            if not doc.strip():
                problemas.append(f'{relativa}:{linea}: {nombre} sin descripcion')
            registros.append({'nombre': nombre, 'linea': linea,
                              'descripcion': doc.splitlines()[0] if doc.strip() else ''})
        inventario.append({'archivo': relativa, 'elementos': registros})
    return inventario, problemas


def escribir_indice(destino: Path, inventario: list[dict], problemas: list[str]) -> None:
    """Genera Markdown con cobertura y enlaces relativos a cada definicion del codigo.

    Las lineas corresponden a las fuentes del momento de generacion;
    regenerar el indice tras cambios. No interpreta la calidad de los docstrings.
    """
    total = sum(len(item['elementos']) for item in inventario)
    documentados = sum(bool(e['descripcion']) for item in inventario for e in item['elementos'])
    lineas = ['# Indice de documentacion del codigo', '',
              'Generado por `docs/verificar_documentacion.py`. Incluye codigo propio; excluye datos, caches y dependencias.', '',
              f'Archivos Python analizados: **{len(inventario)}**. Elementos con descripcion: **{documentados}/{total}**.', '',
              'Esta cobertura comprueba presencia de docstrings y sintaxis; no equivale a una prueba funcional ni garantiza por si sola la exactitud de cada descripcion.', '',
              'Para entender el recorrido, entradas, salidas y limites, consultar [GUIA_CODIGO.md](GUIA_CODIGO.md).', '']
    for item in inventario:
        archivo = item['archivo']
        lineas.extend([f'## {archivo}', '', '| Elemento | Descripcion |', '|---|---|'])
        for elemento in item['elementos']:
            nombre = elemento['nombre']
            resumen = elemento['descripcion'].replace('|', '\\|')
            # El indice habitual vive en docs/, a un nivel de la raiz del proyecto.
            enlace = Path(os.path.relpath(RAIZ / archivo, destino.parent)).as_posix()
            lineas.append(f"| [{nombre}]({enlace}#L{elemento['linea']}) | {resumen} |")
        lineas.append('')
    if problemas:
        lineas.extend(['## Problemas detectados', '', *[f'- {p}' for p in problemas], ''])
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text('\n'.join(lineas), encoding='utf-8')


def main() -> int:
    """Ejecuta la auditoria de CLI y retorna 1 si falta documentacion o falla la sintaxis.

    --indice escribe el inventario Markdown; sin esa opcion solo informa
    cobertura y problemas. No necesita instalar dependencias del proyecto.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--indice', type=Path, help='Destino opcional del inventario Markdown')
    args = parser.parse_args()
    inventario, problemas = auditar(RAIZ)
    total = sum(len(item['elementos']) for item in inventario)
    documentados = sum(bool(e['descripcion']) for item in inventario for e in item['elementos'])
    print(f'{len(inventario)} archivos; {documentados}/{total} elementos documentados; {len(problemas)} problemas.')
    for problema in problemas:
        print(problema)
    if args.indice:
        escribir_indice(args.indice.resolve(), inventario, problemas)
        print(f'Indice: {args.indice}')
    return int(bool(problemas))


if __name__ == '__main__':
    raise SystemExit(main())
