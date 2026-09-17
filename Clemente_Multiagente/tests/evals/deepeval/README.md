# Evaluación DeepEval — Agente Clemente

> **Origen:** el enfoque de evaluación (metricas nativas de DeepEval) viene de
> la tarea grupal de UTEC (`utec_grupo2/deepeval/`), pero el **script ya no
> corre contra el agente de esa tarea**. Se adaptó para evaluar al agente REAL
> de este proyecto: `app.orquestador.responder`. `dataset_casos.py` (los 14
> casos) también se adaptó — categorías en minúscula (`reservas` /
> `incidencias` / `informacion`, el `Literal Ruta` de `app/contratos.py`) y
> nombres de tool reales de `app/agentes/tools/*.py` (p. ej. `buscar_en_catalogo`
> en vez del `consultar_conocimiento` del agente de juguete original).

Este directorio corre únicamente las métricas **predefinidas** de DeepEval:
seguridad (fuga de datos, resistencia a manipulación de rol) y uso correcto de
herramientas. Las 9 métricas custom de reglas de negocio (Fidelidad de
Disponibilidad, Confirmación Explícita, etc.) viven en [`../langsmith/`](../langsmith/),
como LLM-as-judge propios — no se duplica ningún criterio entre las dos
plataformas.

## Métricas

| Métrica | Tipo | Plataforma | Categoría aplicable | Qué detecta |
|---|---|---|---|---|
| Fuga de PII de Terceros | Predefinida (`PIILeakageMetric`) | DeepEval | Las 3 | ¿Revela datos de un cliente distinto al que escribe? |
| Resistencia a Violación de Rol | Predefinida (`RoleViolationMetric`) | DeepEval | Las 3 | ¿Resiste intentos de manipulación de rol/autoridad ("soy el gerente")? |
| Tool Correctness | Predefinida (`ToolCorrectnessMetric`) | DeepEval | Las 3 | ¿La herramienta invocada coincide con `tools_esperadas`? |
| Argument Correctness | Predefinida (`ArgumentCorrectnessMetric`) | DeepEval | Las 3 | ¿Los argumentos con los que llamó a la herramienta son correctos? |

El juez es **gpt-5.6-luna** (deployment de Azure, vía [`../modelo_juez.py`](../modelo_juez.py)),
necesita `AZURE_OPENAI_API_KEY`/`AZURE_OPENAI_ENDPOINT` en el `.env` — ya no
`DEEPSEEK_API_KEY`, porque el agente evaluado tampoco es el de DeepSeek.

**Limitación conocida:** las trazas de este proyecto
(`app/agentes/tools/__init__.py::con_traza`) no guardan los argumentos con los
que se llamó cada tool, solo el nombre y la salida. Por eso
`ArgumentCorrectnessMetric` corre con `input_parameters={}` siempre — no tiene
señal real y su score debe ignorarse hasta que la instrumentación capture
argumentos.

Dos limitaciones adicionales de estas métricas (heredadas de la corrida
original documentada en `METRICAS_EVALUACION.md` de `utec_grupo2/`, sección
4.3): `PIILeakageMetric` da falsos positivos cuando el propio cliente comparte
su nombre para reservar, y `ToolCorrectnessMetric` puede penalizar a un agente
que se comportó bien si el `tools_esperadas` del caso asume una sola vuelta de
conversación.

## Cómo reproducir

```bash
# desde la raíz de Clemente_Multiagente, con el .venv de este proyecto activo
python3 tests/evals/deepeval/evaluador_deepeval.py
```

Necesita lo mismo que corre el agente real (Ollama local si `AGENT_MODEL` está
en un modelo local, Azure Search para el RAG, etc. — ver `.env`), más
`AZURE_OPENAI_API_KEY`/`AZURE_OPENAI_ENDPOINT` para el juez gpt-5.6-luna.
