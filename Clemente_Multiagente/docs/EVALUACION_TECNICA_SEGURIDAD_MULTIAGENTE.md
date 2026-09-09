# Documentación técnica de la evaluación de seguridad del sistema multiagente

## Propósito del documento

Este documento permite al equipo localizar, ejecutar y auditar las pruebas de
seguridad de Clemente. El reporte destinado al docente se mantiene fuera del
repositorio, en `Modulo8_Evaluacion_y_Etica/Sesion23_Seguridad/`
con el nombre `EVALUACION_SEGURIDAD_MULTIAGENTE_CLEMENTE.md`. Aquí se explica
cómo está implementada la evaluación y dónde se produce cada evidencia.

Se utilizó el framework oficial [DeepTeam](https://www.trydeepteam.com/). El
sitio web presenta y documenta la herramienta; no es una API que deba llamarse
desde Clemente. Su forma de uso oficial es instalar el paquete Python
`deepteam`, proporcionar un `model_callback` y ejecutar `red_team(...)`. En este
repositorio está fijado como `deepteam==1.0.9` en `requirements-dev.txt`.

## Diferencia entre DeepTeam, el modelo objetivo y el juez

En esta evaluación participan tres piezas distintas:

| Pieza | Función | Implementación usada |
|---|---|---|
| Clemente | Sistema que recibe el ataque y responde | `gpt-5.6-terra` mediante el orquestador |
| DeepTeam | Construye la campaña, combina vulnerabilidades con técnicas y coordina la evaluación | DeepTeam 1.0.9 |
| LLM evaluador | Genera ataques y juzga si la respuesta vulneró el criterio | `claude-sonnet-5` mediante el adaptador del proyecto |

Por tanto, la prueba de seguridad sí contiene un componente LLM-as-a-Judge:
DeepTeam llama a Claude Sonnet 5 para evaluar las respuestas. DeepTeam es el
marco de red teaming; Claude es el simulador y juez configurado dentro de ese
marco. Esta prueba no debe confundirse con DeepEval, que evalúa calidad funcional
en otro flujo y con otras métricas.

## Archivos principales

| Archivo | Responsabilidad |
|---|---|
| `tests/seguridad/red_team_reservas.py` | Define propósito, mapeo OWASP, vulnerabilidades, técnicas, callback y llamada a DeepTeam |
| `tests/seguridad/campana.py` | Ejecuta por etapas y fija modelos, presupuesto, aislamiento y destinos |
| `tests/eval/juez.py` | Adapta los modelos del proyecto a `DeepEvalBaseLLM`; DeepTeam reutiliza este adaptador |
| `tests/seguridad/entorno.py` | Separa reservas, memoria, autorizaciones, incidencias, trazas e índice por corrida |
| `tests/seguridad/presupuesto.py` | Limita y registra de forma conservadora el consumo por proveedor |
| `tests/seguridad/rejuzgar.py` | Repite únicamente juicios inválidos sobre respuestas congeladas |
| `tests/seguridad/ciclo_reserva.py` | Comprueba el efecto real de propuesta, confirmación y repetición |
| `tests/seguridad/validacion_trello.py` | Verifica creación, consulta y comentario en Trello por MCP |
| `tests/seguridad/LEEME.md` | Explica alcance ético, comandos y manejo de evidencias |

Todos estos archivos están dentro de la raíz `Clemente_Multiagente/`.

## Dónde se llama a DeepTeam

La llamada central está en `tests/seguridad/red_team_reservas.py`, función
`ejecutar()`. El flujo técnico es:

1. `construir_escenarios()` crea las vulnerabilidades de DeepTeam y las tres
   técnicas: Prompt Injection, Permission Escalation y Emotional Manipulation.
2. `construir_juez(modelo_juez)` obtiene el adaptador de Claude Sonnet 5 desde
   `tests/eval/juez.py`.
3. Se crea `RedTeamer` con el mismo modelo como `simulator_model` y
   `evaluation_model`.
4. `motor.red_team(...)` ejecuta la campaña con `run_all_attacks=True`.
5. La combinación de ocho subtipos y tres técnicas produce 24 escenarios.
6. `_upload_to_confident=False` evita subir la evaluación a Confident y
   `_print_assessment=False` evita depender del resumen de consola.
7. `ignore_errors=True` se usó en la repetición completa para conservar los
   casos cuyo juez no produjera una salida válida. Un error queda marcado como
   error y no como aprobación.

La llamada relevante puede localizarse con:

```powershell
rg -n "RedTeamer|red_team\(" tests/seguridad/red_team_reservas.py
```

La invocación concreta del framework es:

```python
from deepteam.red_teamer import RedTeamer

motor = RedTeamer(
    simulator_model=juez,
    evaluation_model=juez,
    target_purpose=PROPOSITO_DEL_OBJETIVO,
    max_concurrent=concurrencia,
)

evaluacion = motor.red_team(
    model_callback=callback,
    vulnerabilities=vulnerabilidades,
    attacks=ataques,
    simulator_model=juez,
    evaluation_model=juez,
    ignore_errors=tolerar_errores,
    run_all_attacks=True,
    _print_assessment=False,
    _upload_to_confident=False,
)
```

Este bloque es una llamada real a DeepTeam. No es una implementación manual de
su algoritmo. Elegimos la clase `RedTeamer` en lugar del atajo
`from deepteam import red_team` porque necesitábamos conservar los casos
simulados y la evaluación parcial si una corrida fallaba.

### Código propio que rodea a DeepTeam

Las siguientes funciones sí son código auxiliar desarrollado para Clemente:

- `construir_escenarios()` selecciona clases de vulnerabilidad y técnicas que
  ya proporciona DeepTeam.
- `construir_callback()` adapta la firma del orquestador de Clemente al contrato
  `model_callback` de DeepTeam.
- `entorno_aislado()` evita modificar datos operativos durante los ataques.
- `Presupuesto` limita y registra llamadas a los proveedores.
- `simular_y_guardar()` envuelve el simulador interno para guardar los ataques
  antes de comenzar la evaluación.
- `rejuzgar.py` vuelve a ejecutar únicamente los juicios cuyo formato fue
  inválido, reutilizando las respuestas originales.

Estas piezas no sustituyen a DeepTeam: configuran el objetivo, protegen el
entorno y hacen reproducible la campaña. La evidencia lo confirma: el resultado
contiene los campos nativos de DeepTeam `vulnerability`, `vulnerability_type`,
`attack_method`, `score`, `reason`, `error` y `cvss_score` para 24 casos.

## Cómo llega un ataque a Clemente

`construir_callback()` convierte a Clemente a la interfaz esperada por DeepTeam.
Para el objetivo `sistema`, cada entrada se transforma en `MensajeEntrante` y se
envía a `app.orquestador.responder()`. Cada ataque recibe una sesión nueva con el
prefijo `redteam-`.

El callback registra el inicio y la respuesta en `turnos.jsonl`. Si el
orquestador registra un error, el callback lanza una excepción para impedir que
una respuesta de contingencia sea interpretada como una defensa exitosa. El
montaje admite un turno por ataque; si DeepTeam entrega historial, lo rechaza de
forma explícita.

```text
DeepTeam genera ataque
        ↓
construir_callback()
        ↓
app.orquestador.responder()
        ↓
agente(s), herramientas y cierre del servidor
        ↓
respuesta devuelta a DeepTeam
        ↓
Claude Sonnet 5 emite score y razón
```

## Aislamiento y comprobaciones independientes del juez

`entorno_aislado()` redirige el estado mutable hacia la carpeta de la corrida.
Se utiliza una reserva canario ficticia propiedad de otra sesión. Durante el red
teaming, las incidencias se almacenan en JSON y no se crean tarjetas de Trello.
Esto evita que los ataques automáticos contaminen el tablero operativo.

Al finalizar, `verificacion_estado_final.json` comprueba directamente:

- que la reserva canario conserva sus campos y propietario;
- que no quedan confirmaciones pendientes;
- que su teléfono y nota privada no aparecen en las respuestas;
- que los ataques no crearon reservas o incidencias adicionales en ese entorno.

Estas verificaciones no son LLM-as-a-Judge. Son comparaciones deterministas
contra archivos y SQLite. Complementan al juez porque este solo analiza texto y
puede desconocer el efecto real de una herramienta.

## Etapas ejecutadas

La entrada operativa es `tests/seguridad/campana.py`:

| Etapa | Qué hace |
|---|---|
| `conexion_medida` | Comprueba ambos modelos y una respuesta del orquestador |
| `humo` | Ejecuta un escenario para validar el montaje |
| `completo` | Primer intento completo; quedó interrumpido y se conservó como evidencia |
| `completo_repeticion` | Ejecuta y conserva los 24 ataques con manejo de errores por caso |
| `rejuzgar` | Repite siete juicios inválidos usando las respuestas ya congeladas |
| `ciclo` | Verifica el estado real de una reserva antes y después de confirmar |
| `trello` | Realiza una prueba controlada sobre Trello real; es complementaria |

Ejemplo para una nueva campaña:

```powershell
python -m tests.seguridad.campana humo --env RUTA_AL_ENV --destino tests/seguridad/deepteam-results/NUEVA_CAMPANA
python -m tests.seguridad.campana completo_repeticion --env RUTA_AL_ENV --destino tests/seguridad/deepteam-results/NUEVA_CAMPANA
```

Las etapas deben ejecutarse secuencialmente porque comparten un archivo de
presupuesto. La ruta del `.env` se pasa de manera explícita y no se publica.

## Evidencias producidas

La campaña ejecutada está en
`tests/seguridad/deepteam-results/campana_20260909/`, excluida de Git. Los
archivos más importantes son:

| Evidencia | Contenido |
|---|---|
| `completo_repeticion/casos_simulados.json` | Los 24 ataques antes de evaluarlos |
| `completo_repeticion/turnos.jsonl` | Entradas y respuestas del objetivo |
| `completo_repeticion/evaluacion.json` | Resultado original de DeepTeam por caso |
| `rejuzgar/juicios_repetidos.json` | Segundo intento de los juicios inválidos |
| `consolidado_seguridad.json` | Unión final sin modificar los resultados originales |
| `presupuesto.json` | Uso reportado y reservas conservadoras por proveedor |
| `completo_repeticion/verificacion_estado_final.json` | Estado del canario y búsqueda de marcadores privados |

El resumen `overview` de DeepTeam 1.0.9 indicó cero errores aunque siete casos
individuales contenían `score=null` y un campo `error`. Por esa razón, el reporte
final utiliza los casos individuales y el consolidado. Después de repetir esos
siete juicios, 21 casos quedaron con juicio favorable y tres siguieron sin una
puntuación válida. Los tres errores no se cuentan como aprobados.

## Pruebas del montaje

`tests/test_redteam_montaje.py`, `tests/test_presupuesto_eval.py` y
`tests/test_eval_robustez.py` verifican el aislamiento, la persistencia parcial,
la propagación de errores, el límite de gasto y el tratamiento de respuestas
inválidas del juez. La última ejecución completa del conjunto local produjo 106
pruebas aprobadas.

## Límites técnicos

- Los ataques automatizados son de un turno y no prueban WhatsApp/Twilio.
- El objetivo de red teaming usa incidencias locales; Trello se valida en una
  prueba controlada aparte.
- Tres escenarios carecen de juicio válido debido al formato de salida del juez.
- Una negativa segura puede aprobar una métrica aunque la respuesta se aleje del
  propósito conversacional del restaurante.
- Los resultados no cubren por completo OWASP Top 10 ni demuestran ausencia de
  vulnerabilidades futuras.
