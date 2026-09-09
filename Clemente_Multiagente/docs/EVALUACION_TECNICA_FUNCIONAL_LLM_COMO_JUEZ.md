# Documentación técnica de la evaluación funcional con LLM como juez

## Propósito del documento

Esta evaluación mide si Clemente responde y actúa conforme a sus reglas de
negocio. No genera ataques. Su reporte de resultados está en
[`EVALUACION_FUNCIONAL_LLM_JUDGE.md`](EVALUACION_FUNCIONAL_LLM_JUDGE.md).

La evaluación usa DeepEval y métricas GEval. Clemente responde con
`gpt-5.6-terra`; `claude-sonnet-5` lee la entrada, la respuesta y la evidencia
del turno, y produce una puntuación y una explicación.

## Relación con la evaluación de seguridad

| Evaluación | Herramienta coordinadora | Finalidad | Uso del LLM juez |
|---|---|---|---|
| Funcional | DeepEval | Calidad, reglas de negocio, fidelidad y tono | Puntúa cada métrica GEval |
| Seguridad | DeepTeam | Generar ataques y medir resistencia | Genera ataques y puntúa vulnerabilidades |

Ambos flujos reutilizan el adaptador `tests/eval/juez.py`, pero no comparten
dataset, métricas ni resultados. Los 34 juicios funcionales no forman parte de
los 24 escenarios de DeepTeam.

## Archivos principales

| Archivo | Responsabilidad |
|---|---|
| `tests/eval/casos.json` | Dataset de 13 conversaciones y 17 turnos |
| `tests/eval/deepeval_evaluar.py` | Construye casos, ejecuta Clemente, llama a las métricas y guarda resultados |
| `tests/eval/metricas.py` | Define las métricas GEval, pasos, rúbricas y umbrales |
| `tests/eval/juez.py` | Implementa el adaptador `DeepEvalBaseLLM` para Claude u OpenAI |
| `tests/seguridad/campana.py` | Ejecuta la etapa `funcional` con aislamiento y presupuesto compartido |
| `tests/seguridad/entorno.py` | Sustituye datos operativos por archivos y SQLite temporales |
| `tests/seguridad/ciclo_reserva.py` | Comprueba efectos reales que el juez textual no puede acreditar |

## Dónde se llama a DeepEval

DeepEval no se invoca mediante una función global única. Sus componentes se
usan en dos niveles:

1. `tests/eval/metricas.py` importa `GEval` y construye cuatro métricas con el
   modelo devuelto por `construir_juez()`.
2. `tests/eval/deepeval_evaluar.py`, dentro de `evaluar()`, llama
   `metrica.measure(caso)` para cada métrica aplicable al agente que respondió.

La ejecución independiente termina en:

```python
informe = evaluar(guiones, construir_metricas(construir_juez()))
```

La campaña controlada llama al mismo `evaluar()` desde la función `funcional()`
de `tests/seguridad/campana.py`, procesando y guardando un guion a la vez.

Los puntos exactos se localizan con:

```powershell
rg -n "construir_metricas|metrica.measure|construir_juez" tests/eval tests/seguridad/campana.py
```

## Cómo funciona el adaptador del juez

`construir_juez()` define una clase que hereda de `DeepEvalBaseLLM`. Sus métodos
`generate()` y `a_generate()` llaman al modelo configurado. Cuando DeepEval
solicita una respuesta estructurada, el adaptador usa
`with_structured_output(schema)` para obtener los campos exigidos por la métrica.

En esta campaña se fijó `JUEZ_MODEL=claude-sonnet-5`, mientras Clemente utilizó
`OPENAI_MODEL=gpt-5.6-terra`. Separar proveedores reduce el riesgo de
autopreferencia, aunque no elimina los sesgos ni los errores del juez.

Si el juez devuelve una estructura inválida, `deepeval_evaluar.py` registra el
tipo de error y `aprobo=False`. Un error no recibe puntuación inventada y no se
incluye en el promedio de métricas válidas. Si el control de presupuesto detiene
una llamada, la excepción se propaga y la etapa se interrumpe.

## Construcción del caso evaluado

Por cada turno, el evaluador:

1. Envía un `MensajeEntrante` al orquestador con el historial del guion.
2. Guarda la respuesta de Clemente y actualiza el historial.
3. Obtiene las herramientas y eventos registrados desde el inicio del turno.
4. Agrega, según corresponda, la ficha del cliente, la confirmación ejecutada o
   el cierre del orquestador como evidencia del servidor.
5. Para preguntas de información, obtiene los fragmentos recuperados del
   catálogo y los pasa como `retrieval_context`.
6. Construye un `LLMTestCase` con entrada, salida, respuesta esperada,
   herramientas y contexto.
7. Selecciona las métricas según el agente que realmente respondió.

```text
casos.json
    ↓
orquestador de Clemente
    ↓
respuesta + trazas + herramientas + contexto RAG
    ↓
LLMTestCase de DeepEval
    ↓
GEval con Claude Sonnet 5
    ↓
score, umbral, aprobación y razón
```

## Métricas y umbrales

| Métrica | Agente | Qué revisa | Umbral |
|---|---|---|---:|
| No promete lo que no puede cumplir | Reservas | Que no afirme disponibilidad sin consultar y no confirme grupos fuera del alcance | 0.8 |
| No ofrece compensación | Incidencias | Que no conceda descuentos, cortesías o beneficios sin autoridad | 0.8 |
| Fiel al catálogo | Información | Que horarios, precios, políticas y servicios estén respaldados por el contexto | 0.8 |
| Voz de Clemente | Todos | Tono breve, cordial y apropiado para chat | 0.7 |

Las tres primeras usan pasos de evaluación y rúbricas explícitas. La métrica de
tono usa un criterio abierto porque evalúa estilo. Esta última es más subjetiva
y produjo dos observaciones que entran en tensión con mensajes transparentes de
seguridad o seguimiento.

## Adaptación del dataset a la autorización actual

El dataset histórico contenía un nombre, teléfono y código de reserva concretos.
La campaña los reemplaza en memoria por datos ficticios. El caso de memoria usa
la sesión propietaria de la reserva canario; el caso de continuidad utiliza el
mismo código desde otra sesión para verificar que el acceso se rechace.

Los guiones originales no se sobrescriben durante la campaña. La versión exacta
utilizada queda en `funcional/guiones_utilizados.json`.

## Resultados y evidencias

La campaña produjo 13 guiones, 17 turnos y 34 intentos de juicio:

- 29 juicios aprobaron su umbral;
- 4 quedaron por debajo del umbral;
- 1 terminó con `ValidationError` y no se contó como aprobado.

Los resultados detallados están en:

| Evidencia | Contenido |
|---|---|
| `funcional/resultados.json` | Respuesta, agente, herramientas y juicios por turno |
| `funcional/guiones_utilizados.json` | Dataset efectivo con datos ficticios |
| `funcional/datos/conversaciones.jsonl` | Plan y respuesta persistidos por el orquestador |
| `funcional/estado_anterior.json` | Interrupción inicial causada por el juez |
| `ciclo/ciclo_reserva.json` | Conversación de propuesta y confirmación |
| `ciclo/verificaciones_estado.json` | Resultado determinista de cuatro condiciones |

La carpeta completa es
`tests/seguridad/deepteam-results/campana_20260909/` y está excluida de Git por
contener conversaciones y evidencias crudas.

## Evidencia local que complementa al juez

La frase “se complementa el juicio del modelo con evidencia local” significa que
no se confía únicamente en la puntuación textual. `ciclo_reserva.py` leyó el
estado y comprobó directamente que:

- la propuesta no escribe antes de la confirmación;
- una confirmación enviada desde otra sesión se rechaza;
- el código correcto crea exactamente una reserva;
- repetir el mismo código no duplica la reserva.

Estas comprobaciones no son DeepEval ni LLM-as-a-Judge. Son aserciones sobre el
estado real del sistema. Un juez podría considerar correcta una frase como
“reserva creada” aunque ninguna herramienta hubiese escrito los datos; esta
verificación evita aceptar ese tipo de falso positivo.

## Limitaciones técnicas identificadas

- El campo `ruteo_correcto` refleja solo el último agente y no evalúa por sí
  mismo todo un plan de dos pasos.
- El contexto RAG del evaluador se recupera con la pregunta original; puede no
  coincidir exactamente con la consulta reformulada por el agente.
- El LLM juez puede penalizar mensajes seguros por su tono o interpretar mal la
  cronología entre una herramienta y el cierre del servidor.
- Un único error de salida estructurada impide calcular una puntuación para ese
  juicio, pero no prueba que el agente haya fallado.
- Diecisiete turnos permiten detectar regresiones concretas; no constituyen una
  garantía estadística de calidad global.

## Reproducción

Para ejecutar solo el flujo original de DeepEval:

```powershell
python -m tests.eval.deepeval_evaluar --modelo gpt-5.6-terra --juez claude-sonnet-5
```

Para ejecutar la versión controlada, aislada y con presupuesto compartido:

```powershell
python -m tests.seguridad.campana funcional --env RUTA_AL_ENV --destino tests/seguridad/deepteam-results/NUEVA_CAMPANA
python -m tests.seguridad.campana ciclo --env RUTA_AL_ENV --destino tests/seguridad/deepteam-results/NUEVA_CAMPANA
```

La ruta del `.env` debe permanecer fuera de Git. La campaña fija los modelos
empleados y registra el consumo, mientras que el comando original ofrece filtros
por guion o agente y genera su propio informe.

