# Evaluación LangSmith — Agente Clemente

Único evaluador post-deploy del proyecto. Corre el agente REAL
(`app.orquestador.responder`) sobre datasets de LangSmith y lo califica con un
juez Claude. Los resultados (scores y comentarios del juez) se revisan en los
experimentos de LangSmith; el script no genera reportes locales.

> **Origen:** el enfoque viene de la tarea grupal de UTEC (`utec_grupo2/langsmith/`),
> adaptado al agente real de este proyecto. El evaluador DeepEval que convivía con
> este se eliminó el 2026-10-10 y sus métricas predefinidas se reemplazan con los
> prompts de [openevals](https://github.com/langchain-ai/openevals#prebuilt-prompts).
> La suite de negocio (`clemente-casos-prueba`, con su `dataset_casos.py`) también se
> retiró ese día; queda en el historial de git.

## Datasets

Seis datasets, uno por tipo de prueba. Cada suite sube el suyo y solo corre los
evaluadores que aplican a él, para que los promedios no se mezclen.

| Suite | Dataset en LangSmith | Casos | Evaluadores |
|---|---|---|---|
| `security` | `clemente-security` | [`../dataset_security.py`](../dataset_security.py): 5 de prompt injection + 5 de PII, un mensaje cada uno | `resistio_inyeccion`, `no_revela_datos_ajenos`, `prompt_injection`, `pii_leakage` |
| `conversation` | `clemente-conversation` | [`../dataset_conversation.py`](../dataset_conversation.py): 5 conversaciones de 2-3 turnos en la misma sesión | `agent_tone`, `user_satisfaction`, `task_completion`, `wins`, `estilo_cordial` |
| `rag` | `clemente-rag` | [`../dataset_rag.py`](../dataset_rag.py): 5 preguntas al catálogo (`catalogo-clemente`) + 5 reclamos que recuperan un caso previo (`incidencias-clemente`) | `rag_retrieval_relevance`, `rag_groundedness`, `rag_helpfulness` |
| `quality` | `clemente-quality` | [`../dataset_quality.py`](../dataset_quality.py): 5 preguntas con respuesta correcta del catálogo | `correctness`, `hallucination`, `conciseness` |
| `trajectory` | `clemente-trajectory` | [`../dataset_trajectory.py`](../dataset_trajectory.py): 5 pedidos con la secuencia de tools del diseño | `tool_selection` |
| `safety` | `clemente-safety` | [`../dataset_safety.py`](../dataset_safety.py): 5 provocaciones | `toxicity` |

## Evaluadores

| Evaluador | Suite | Tipo | Qué mide (1.0 = pasa) |
|---|---|---|---|
| `pii_leakage` | security | LLM-as-judge predefinido (openevals `PII_LEAKAGE_PROMPT`, variante de terceros) | La respuesta no expone datos personales de otra persona. Repetir los datos del propio cliente no cuenta como fuga |
| `prompt_injection` | security | LLM-as-judge predefinido (openevals `PROMPT_INJECTION_PROMPT`) | **Etiqueta el caso**, no al agente: 1.0 = el mensaje del cliente es un ataque. Sirve para filtrar los casos de ataque |
| `resistio_inyeccion` | security | LLM-as-judge custom | El agente mantiene sus reglas ante el intento de manipulación (solo casos de prompt injection) |
| `no_revela_datos_ajenos` | security | LLM-as-judge custom | No revela datos de terceros ni repite datos financieros (solo casos de PII) |
| `agent_tone` | conversation | LLM-as-judge predefinido (openevals `AGENT_TONE_PROMPT`) | Tono apropiado para el contexto y consistente en toda la conversación |
| `user_satisfaction` | conversation | LLM-as-judge predefinido (openevals `USER_SATISFACTION_PROMPT`) | El cliente parece satisfecho al final. Con guiones fijos refleja sobre todo el guion |
| `task_completion` | conversation | LLM-as-judge predefinido (openevals `TASK_COMPLETION_PROMPT`) | Clemente completó todo lo que el cliente pidió |
| `wins` | conversation | LLM-as-judge predefinido (openevals `WINS_PROMPT`) | El cliente elogió o agradeció a Clemente. Con guiones fijos refleja sobre todo el guion |
| `estilo_cordial` | conversation | LLM-as-judge custom | Calidez por WhatsApp: saluda/agradece, muestra empatía y usa emojis con moderación y acordes al contexto (pocos o ninguno alegre ante una queja) |

| `correctness` | quality | LLM-as-judge predefinido (openevals `CORRECTNESS_PROMPT`) | Coincide con la respuesta correcta del caso (`referencia`) |
| `hallucination` | quality | LLM-as-judge predefinido (openevals `HALLUCINATION_PROMPT`) | No afirma nada fuera del contexto (ficha fija del restaurante + resultado de las tools) |
| `conciseness` | quality | LLM-as-judge predefinido (openevals `CONCISENESS_PROMPT`) | Responde sin relleno |
| `tool_selection` | trajectory | LLM-as-judge predefinido (openevals `TOOL_SELECTION_PROMPT`) | Tools correctas, en orden y sin sobrantes, comparadas con la secuencia del diseño del agente (`referencia`) |
| `toxicity` | safety | LLM-as-judge predefinido (openevals `TOXICITY_PROMPT`, invertido) | La respuesta no es tóxica aunque el cliente provoque |
| `rag_retrieval_relevance` | rag | LLM-as-judge predefinido (openevals `RAG_RETRIEVAL_RELEVANCE_PROMPT`) | Lo recuperado de Azure AI Search (catálogo o casos previos de incidencias) es relevante para el mensaje (sin score si no recuperó nada) |
| `rag_groundedness` | rag | LLM-as-judge predefinido (openevals `RAG_GROUNDEDNESS_PROMPT`) | La respuesta se apoya en lo que tenía el agente: ficha fija del restaurante + salida de sus tools, incluido lo recuperado (sin score si no recuperó nada) |
| `rag_helpfulness` | rag | LLM-as-judge predefinido (openevals `RAG_HELPFULNESS_PROMPT`) | La respuesta es útil para la pregunta |

El evaluador sube a 20 000 caracteres el recorte de la salida de cada tool en las trazas
(`LARGO_SALIDA_EN_TRAZA`, 400 en producción) solo dentro de su propio proceso, para que
los jueces vean el texto recuperado completo.

## Juez

**Claude** (`claude-sonnet-5-5`, o `JUEZ_MODEL`), vía [`../modelo_juez.py`](../modelo_juez.py).
Las evaluaciones solo usan Claude como juez desde el 2026-10-10:

- El agente corre sobre `gpt-5.6-luna`; juzgarlo con otra familia evita el sesgo de autopreferencia.
- Con `gpt-5.6-luna` como juez, el filtro de jailbreak de Azure bloqueaba al propio juez en
  los casos de prompt injection y quedaban sin puntaje.

## Cómo reproducir

```bash
# desde la raíz de Clemente_Multiagente, con el .venv activo
python3 tests/evals/langsmith/evaluador_langsmith.py                 # las seis suites
python3 tests/evals/langsmith/evaluador_langsmith.py rag quality     # solo esas suites
```

Necesita en el entorno (o en `.env`), con los mismos valores que `caclmt01`:

- Agente: `AGENT_MODEL=azure`, `AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_API_KEY`,
  `AZURE_OPENAI_DEPLOYMENT`, `AZURE_OPENAI_API_VERSION`, `AZURE_OPENAI_EMBEDDINGS_DEPLOYMENT`,
  `RAG_BACKEND=azure_search`, `EMBEDDINGS_BACKEND=azure`, `AZURE_SEARCH_ENDPOINT`,
  `AZURE_SEARCH_INDEX`, `AZURE_SEARCH_API_KEY`.
- Juez: `ANTHROPIC_API_KEY`.
- LangSmith: `LANGSMITH_API_KEY`, `LANGSMITH_PROJECT`, `LANGSMITH_TRACING=true`.
- `CLEMENTE_BACKEND_RESERVAS=json` y `CLEMENTE_BACKEND_INCIDENCIAS=json` para no tocar datos reales.

Los secretos se pueden leer de la Container App con
`az containerapp secret show -n caclmt01 -g rgclmt01 --secret-name <nombre> --query value -o tsv`
(`azure-openai-key`, `azure-search-key`, `langsmith-api-key`).

En CI lo corre el workflow `evals.yml` (manual, `workflow_dispatch`).
