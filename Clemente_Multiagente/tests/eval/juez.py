"""
Juez de las evaluaciones -- el modelo que califica, no el que atiende clientes.

Por que existe este archivo: DeepEval y DeepTeam usan **GPT-4 de OpenAI** como
juez por defecto, un modelo que el proyecto no usa. Hace falta decirles
explicitamente con que modelo juzgar, y la forma de hacerlo es implementar
`DeepEvalBaseLLM`.

Desde el 2026-09-08 hay clave de los dos proveedores, asi que `JUEZ_MODEL` puede
apuntar a un modelo de OpenAI mientras los agentes corren sobre Anthropic (o al
reves). Esa es la unica forma de sacarse de encima el sesgo de familia.

Se envuelve `resolver_modelo()` de `app/llm.py` a proposito, en vez de crear un
`ChatAnthropic` aparte: asi el juez respeta las mismas reglas que el resto del
proyecto -- entre ellas que los modelos Claude 4.6 en adelante rechazan el
parametro `temperature` -- y cambiar de proveedor sigue siendo una linea del
`.env`.

Una advertencia de la Sesion 22 que conviene tener presente: el juez tambien es
un modelo y **tambien se equivoca**. Sus sesgos conocidos son preferir respuestas
largas, favorecer al modelo de su propia familia y ser inconsistente entre
corridas. Por eso el juez se declara en el informe junto con el resultado: un
puntaje sin decir quien juzgo no significa nada.

Modelo del juez, en orden de preferencia:
    1. JUEZ_MODEL en el .env (para poder juzgar con un modelo distinto al evaluado)
    2. ANTHROPIC_MODEL
"""

import os
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent.parent
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from app.llm import extraer_texto, modelo_activo, resolver_modelo   # noqa: E402

VARIABLE_MODELO_JUEZ = "JUEZ_MODEL"

# Juez por defecto, y NO es el modelo que responde. Dos razones:
#
# 1. Un modelo tiende a premiar sus propias respuestas (*self-preference bias*):
#    juzgarse a si mismo infla el resultado y lo vuelve poco creible ante
#    cualquiera que lea el informe.
# 2. El juez deberia ser al menos tan capaz como el evaluado. Si Sonnet responde,
#    juzgar con Haiku seria pedirle a alguien que corrija un examen que no sabria
#    resolver.
#
# De ahi que el juez sea siempre el modelo mas capaz disponible, aunque los
# agentes corran con uno mas barato. Juzgar cuesta menos que responder: el juicio
# es un prompt corto con una salida corta.
MODELO_JUEZ_POR_DEFECTO = "claude-opus-5"


def _modelo_del_juez() -> str:
    return os.getenv(VARIABLE_MODELO_JUEZ) or MODELO_JUEZ_POR_DEFECTO


def advertir_si_se_juzga_a_si_mismo() -> str:
    """
    Devuelve la advertencia si juez y evaluado coinciden, o cadena vacia.

    No lo impide -- a veces es lo que se quiere, por presupuesto o para comparar
    contra una corrida anterior -- pero tiene que quedar dicho en pantalla y en
    el informe. Sigue siendo un limite conocido del LLM-as-judge (Sesion 22):
    aun con modelos distintos de la MISMA familia queda sesgo de familia. Lo
    unico que lo elimina del todo es un juez de otro proveedor -- y desde el
    2026-09-08 el proyecto SI tiene credencial de OpenAI, asi que juzgar con un
    GPT lo que responde Claude (o al reves) ya es posible y es la corrida mas
    creible para el informe.
    """
    evaluado = modelo_activo()
    if _modelo_del_juez() == evaluado:
        return (f"[aviso] El juez y el modelo evaluado son el mismo ({evaluado}). "
                f"Un modelo tiende a premiar sus propias respuestas: los puntajes "
                f"salen inflados. Usa --juez con otro modelo para la corrida del informe.")
    return ""


def construir_juez():
    """
    Devuelve el juez para DeepEval y DeepTeam.

    Se importa `DeepEvalBaseLLM` aqui dentro y no arriba para que este modulo se
    pueda importar sin tener DeepEval instalado -- util para las pruebas de
    contrato, que no deben depender de las librerias de evaluacion.
    """
    from deepeval.models import DeepEvalBaseLLM

    class JuezClemente(DeepEvalBaseLLM):
        """Adaptador de nuestro modelo de `app/llm.py` a la interfaz de DeepEval."""

        def __init__(self, nombre: str | None = None):
            self.nombre = nombre or _modelo_del_juez()
            # El juez califica: se le pide determinismo, no creatividad.
            # `resolver_modelo` decide si el modelo acepta `temperature`.
            #
            # `modelo=self.nombre` es lo que hace que el juez SEA el que dice
            # ser. Sin ese argumento -- como estuvo hasta el 2026-09-08 --
            # `resolver_modelo` leia el `.env` y devolvia el modelo que se
            # estaba evaluando: el informe declaraba un juez y usaba otro.
            self._modelo = resolver_modelo(temperature=0.0, modelo=self.nombre)

        def load_model(self):
            return self._modelo

        def generate(self, prompt: str, schema=None):
            """
            DeepEval pasa `schema` (una clase Pydantic) cuando necesita la
            respuesta estructurada -- que es como GEval obtiene el puntaje y la
            justificacion. Sin schema, devuelve texto plano.
            """
            if schema is not None:
                return self._modelo.with_structured_output(schema).invoke(prompt)
            return extraer_texto(self._modelo.invoke(prompt))

        async def a_generate(self, prompt: str, schema=None):
            if schema is not None:
                return await self._modelo.with_structured_output(schema).ainvoke(prompt)
            return extraer_texto(await self._modelo.ainvoke(prompt))

        def get_model_name(self) -> str:
            return self.nombre

    return JuezClemente()


def nombre_del_juez() -> str:
    """Para dejarlo escrito en el informe: quien califico."""
    return _modelo_del_juez()
