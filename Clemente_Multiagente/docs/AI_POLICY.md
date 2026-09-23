> Estado de integracion al 2026-09-18: consultar [PR_GUARDRAILS.md](PR_GUARDRAILS.md). Las cifras de 126 pruebas y referencias a Twilio futuro en este documento son antecedentes historicos.

# AI Policy — transparencia sobre el uso de IA en el desarrollo de Clemente

| Campo | Valor |
|---|---|
| Versión | 1.1 |
| Última revisión | 2026-09-11 |
| Responsable del documento | Grupo 02 |
| Estado | Borrador completo, pendiente de aprobación formal por todos los integrantes |
| Próxima revisión | Antes de la presentación final del 2026-10-13 o al cambiar de modelo/proveedor |

**Integrantes que deben revisar y aprobar esta versión** (Grupo 02, según `README.md` sección 2):

| Integrante | Frente | Aprobó esta versión |
|---|---|---|
| Jesús Barboza | Comunicación y canal WhatsApp | ☐ pendiente |
| Christian | Orquestador, agentes, RAG | ☐ pendiente |
| Jean | Orquestador, agentes, RAG | ☐ pendiente |
| Miguel Rojas | Gestor de reservas | ☐ pendiente |
| Adrián Bastidas | Observabilidad | ☐ pendiente |

Ningún integrante ha firmado esta versión todavía — por eso el estado declarado arriba es "borrador
completo, pendiente de aprobación formal", no "aprobado". Marcar cada casilla cuando esa persona
haya leído y esté de acuerdo con el contenido, no antes.

**Criterio de actualización:** esta política se revisa (no solo se relee) cuando ocurra cualquiera
de estos eventos: (1) el equipo incorpora una tercera herramienta de IA de desarrollo; (2) cambia
el modelo o proveedor configurado en `AGENT_MODEL` o `JUEZ_MODEL`; (3) se agrega un canal, backend
o integración nueva que envíe datos a un tercero (p. ej. WhatsApp/Twilio real); (4) una evaluación
o auditoría encuentra que una afirmación de este documento ya no es cierta. Fuera de esos eventos,
revisar de todas formas antes de la presentación final del 2026-10-13.

> Exigido por el docente (Boris Alzamora) en la Sesión 25 (00:00–28:01, 2026-09-09): declarar
> explícitamente qué herramientas de IA se usaron, en qué tareas, qué revisó y decidió el equipo,
> cómo se verificó el resultado, y qué limitaciones siguen abiertas. Ver el análisis completo en
> `../ANALISIS_INDICACIONES_PROYECTO_SESION25.md`, sección 3.5.
>
> **Regla que sigue este documento:** no inventar un porcentaje exacto de código generado por IA
> si no existe un registro que lo mida. Es mejor describir actividades y responsabilidad real.

## 1. Qué herramientas de IA se usaron

- **Claude (Anthropic)**, vía Claude Code, como asistente principal de desarrollo durante buena
  parte del proyecto: generación y refactorización de código, redacción de pruebas, documentación
  técnica (README, análisis de sesiones) y revisión de decisiones de arquitectura.
- **OpenAI Codex**, como segundo asistente de desarrollo: revisió e implementó la integración de
  Guardrails AI, PII, toxicidad, `HumanInTheLoopMiddleware`, estados gráficos, panel HITL, pruebas
  automatizadas y sincronización del README con el código. Sus cambios se verificaron con diff,
  recopilación de pruebas y ejecución local.

- No se usó n8n ni ninguna plataforma de automatización low-code para lógica de negocio, RAG o
  agentes — decisión explícita del equipo, alineada con lo que pidió el docente (sección 3.4 del
  análisis de la Sesión 25: *"n8n no está invitado a esta clase"*).

## 2. En qué tareas se usó IA

Esta política distingue dos usos: **IA para desarrollar Clemente** (Claude Code y OpenAI Codex)
y **IA dentro de Clemente en operación** (modelo conversacional, juez y clasificadores).

| Tarea | Uso de IA | Quién decidió y validó |
|---|---|---|
| Arquitectura (router → orquestador, agentes, MCP) | Discusión y generación de alternativas de diseño | El equipo, contrastado en vivo con el docente (asesoría del 2026-09-07, `ASESORIA_01_BORIS_ACUERDOS.md`) |
| Código de agentes, orquestador, tools, RAG | Generación y refactorización asistida | Los responsables inspeccionaron los cambios mediante diff, pruebas y revisión de los archivos críticos (`base.py`, `grafo.py`, `autorizacion.py`, `indice.py`, `mcp_trello.py`) |
| Pruebas automatizadas (126 casos) | Generación asistida de casos de prueba | Ejecutadas y verificadas por el equipo; no se aceptó ningún caso sin que pasara localmente (ver sección 4) |
| Documentación (README, análisis, evaluaciones) | Redacción y estructuración asistida | Revisada por el equipo contra el código real antes de publicarse; ver la nota de re-verificación del 2026-09-11 en `ANALISIS_INDICACIONES_PROYECTO_SESION25.md` |
| Evaluación (DeepEval/GEval, LangSmith, DeepTeam) | Diseño de métricas y guiones de prueba | El equipo definió los criterios de "buena respuesta" en `tests/eval/metricas.py`; los resultados se corrieron contra el sistema real, no se simularon |

### 2.1 IA utilizada durante la operación

| Componente | Uso | Datos que puede recibir |
|---|---|---|
| Modelo configurado con `AGENT_MODEL` | planificación y respuestas de los agentes | mensaje e historial acotado; PII filtrada según la política técnica |
| Modelo juez configurado para DeepEval | evaluación fuera del flujo del cliente | dataset y respuestas de evaluación |
| `DetectJailbreak` y `ToxicLanguage` | clasificación local en el servicio aislado | texto de entrada o salida validado |

El proveedor y modelo operativo pueden cambiar por configuración. Todo cambio de proveedor exige
revisar transferencia de datos, privacidad, costo, calidad y esta política.

## 3. Qué decidió y revisó el equipo (no delegado a la IA)

- El alcance del entregable (qué queda dentro y qué queda fuera — pedidos/delivery excluidos).
- Las reglas de negocio (turnos válidos, límite de 10 personas, plazos de incidencia por tipo).
- Qué herramientas puede usar cada agente y cuáles deliberadamente **no** existen (el límite de
  permisos es una decisión de producto, no un accidente de implementación).
- La decisión de modelo por defecto (`gpt-5.6-terra`), tomada **midiendo** con el banco de modelos
  propio (`tests/eval/banco_modelos.py`), no aceptando una recomendación sin verificar.
- La corrección de los tres defectos reales que encontró la primera evaluación de la arquitectura
  nueva (doble ticket, escalamiento prematuro, frase repetida en el cierre) — documentados en el
  README, sección 11, como hallazgos propios del equipo tras leer los resultados de la evaluación.

## 4. Cómo se verificó cada resultado generado con asistencia de IA

- **126 casos de prueba automatizados** (113 funciones, con parametrización), verificados por
  ejecución real el 2026-09-11: `126 passed, 0 failed`. No llaman a ningún modelo ni a Trello.
- **Evaluación funcional** con DeepEval/GEval sobre el dataset de 13 guiones / 17 turnos, con juez
  independiente (`claude-sonnet-5` evaluando `gpt-5.6-terra`, evitando que un modelo se
  autoevalúe) — resultados en `docs/EVALUACION_FUNCIONAL_LLM_JUDGE.md`.
- **Red teaming** con DeepTeam, 24 escenarios contra el agente de Reservas — resultados en
  `docs/EVALUACION_TECNICA_SEGURIDAD_MULTIAGENTE.md`.
- **Integración con Trello por MCP**, validada con una tarjeta real (creación, consulta,
  comentario) — evidencia en `docs/VALIDACION_INTEGRACION_TRELLO.md`.
- Ningún hallazgo de estos documentos se aceptó por la palabra del asistente de IA: cada uno se
  contrastó contra una ejecución real (traza, prueba o corrida de evaluación) antes de publicarse.

## 5. Limitaciones que siguen abiertas

- Falta la aprobación formal y registrada de todos los integrantes; no se declara como aprobada
  hasta que esa revisión ocurra.
- No existe un registro que mida qué proporción exacta del código fue escrita por una IA frente a
  un integrante del equipo sin asistencia; por eso esta política describe actividades y
  responsabilidad, no un porcentaje.
- El dominio del código por parte de **todos** los integrantes (no solo quien lo generó) no es
  algo que un documento pueda demostrar — se demuestra en la defensa cruzada (ver
  `CUESTIONARIO_DEFENSA_SESION25.md`, recomendación de la sección 5.3 del análisis de la Sesión 25).
- Esta política debe revisarse si el equipo incorpora una tercera herramienta de IA antes de la
  presentación final del 13 de octubre de 2026.

## 6. Responsabilidad

El equipo (Grupo 02) asume la responsabilidad completa del código, las decisiones de arquitectura,
alcance y reglas de negocio presentadas, con independencia de qué herramienta de IA participó en
generar un borrador inicial. Cualquier aporte generado por IA fue inspeccionado en el repositorio
y aceptado solo cuando pasó las pruebas o la evaluación correspondiente descritas en la sección 4.
