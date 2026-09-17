# Evaluación LangSmith — Agente Clemente

> **Origen:** el enfoque de evaluación (LLM-as-judge propio con 9 criterios de
> negocio + enrutamiento determinístico) viene de la tarea grupal de UTEC
> (`utec_grupo2/langsmith/`), pero el **script ya no corre contra el agente de
> esa tarea**. Se adaptó para evaluar al agente REAL de este proyecto:
> `app.orquestador.responder`. Las herramientas usadas por caso se leen de las
> trazas reales (`app.observabilidad.trazas`), no de los mensajes de un grafo
> LangGraph propio como en la versión original. `dataset_casos.py` (los 14
> casos, compartido con `../deepeval/`) también se adaptó: categorías en
> minúscula (`reservas` / `incidencias` / `informacion`, el `Literal Ruta` de
> `app/contratos.py`) y nombres de tool reales de `app/agentes/tools/*.py`.

Este directorio corre las **9 métricas custom** de reglas de negocio de
Clemente (LLM-as-judge propios, con salida estructurada vía LangChain
`with_structured_output`) más un evaluador determinístico de enrutamiento.
Estas métricas viven solo aquí y no se duplican en DeepEval. Las métricas
predefinidas de seguridad y uso de herramientas están en [`../deepeval/`](../deepeval/).

## Métricas

| Métrica | Tipo | Plataforma | Categoría aplicable | Qué detecta |
|---|---|---|---|---|
| Fidelidad de Disponibilidad | Custom (LLM-as-judge) | LangSmith | Reservas | ¿Afirma/niega disponibilidad sin haberla verificado? |
| Confirmación Explícita antes de Reservar | Custom (LLM-as-judge) | LangSmith | Reservas | ¿Reserva sin que el cliente haya confirmado todos los datos? |
| Escalamiento Correcto | Custom (LLM-as-judge) | LangSmith | Reservas, Información | ¿Escala cuando el caso excede lo que puede resolver solo? |
| Manejo de Incidencias sin Minimizar | Custom (LLM-as-judge) | LangSmith | Incidencias | ¿Reconoce la queja sin minimizar ni poner excusas? |
| No Ofrece Compensación No Aprobada | Custom (LLM-as-judge) | LangSmith | Incidencias | ¿Promete descuentos/compensaciones por su cuenta? |
| No Cierra Incidencias Prematuramente | Custom (LLM-as-judge) | LangSmith | Incidencias | ¿Da un caso por cerrado solo porque el cliente resta importancia? |
| Fidelidad al Catálogo (no alucina políticas) | Custom (LLM-as-judge) | LangSmith | Información | ¿Inventa horarios/políticas que no están en el catálogo? |
| Tono Profesional y Empático | Custom (LLM-as-judge) | LangSmith | Las 3 | ¿Es cordial, sin culpar al staff ni exponer procesos internos? |
| Enrutamiento Correcto | Predefinida (determinístico) | LangSmith | Las 3 | ¿Usó alguna herramienta esperada para la categoría del mensaje? (compara `tools_esperadas` vs. tool-call real, sin juez LLM) |

El juez es **gpt-5.6-luna** (deployment de Azure, vía [`../modelo_juez.py`](../modelo_juez.py)),
necesita `AZURE_OPENAI_API_KEY`/`AZURE_OPENAI_ENDPOINT` en el `.env` — ya no
`DEEPSEEK_API_KEY`. Cada evaluador solo se aplica a la categoría de caso a la
que corresponde, para no ensuciar el promedio con un 0 injustificado en un
caso donde la métrica no aplica.

## Cómo reproducir

```bash
# desde la raíz de Clemente_Multiagente, con el .venv de este proyecto activo
# .env con AZURE_OPENAI_API_KEY/AZURE_OPENAI_ENDPOINT (juez) y LANGSMITH_API_KEY
python3 tests/evals/langsmith/evaluador_langsmith.py
```

Sube/actualiza el dataset `clemente-casos-prueba` en LangSmith y corre el
experimento contra el agente real — necesita `LANGSMITH_API_KEY` (vacío en el
`.env` de este proyecto al momento de escribir esto).
