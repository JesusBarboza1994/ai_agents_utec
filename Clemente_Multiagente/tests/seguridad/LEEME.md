# Seguridad: red teaming de Clemente

## Alcance y uso autorizado

Ejecutar solo contra este proyecto propio y con claves autorizadas por el equipo.
No dirigir ataques a sistemas de terceros. Ejecutar en un proceso independiente,
no desde el servidor Flask: el aislamiento modifica configuracion global del proceso.

El montaje usa datos sinteticos y archivos separados por corrida. Incidencias usa
JSON local, sin publicar tickets en Trello. Se desactiva la subida a Confident y
el trazado remoto. Los prompts y respuestas necesarios para simular, responder y
juzgar si se envian a los proveedores LLM configurados; los embeddings pueden
usar un proveedor externo segun la configuracion.

`deepteam-results/` contiene todas las evidencias disponibles, incluidos ataques
exitosos, fallidos e incompletos. Esta ignorada por Git. No publicar los crudos;
preparar un resumen revisado para la entrega.

## Ejecucion

```powershell
pip install -r requirements-dev.txt
python -m tests.seguridad.red_team_reservas --plan
python -m tests.seguridad.red_team_reservas --humo
python -m tests.seguridad.red_team_reservas --objetivo sistema
```

`--plan` no llama a modelos. Humo planifica un escenario y completo planifica 24
(8 tipos por 3 tecnicas, con `run_all_attacks=True`). Cada escenario puede generar
varias llamadas; no hay tope monetario automatico. Revisar saldo antes de iniciar.
`--juez` y `--modelo` permiten seleccionar modelos habilitados para las cuentas.

El objetivo predeterminado `sistema` pasa por el orquestador, sin HTTP/Twilio.
`reservas` permite diagnosticar el especialista, sin el cierre del servidor.
Ninguno acredita el funcionamiento del canal WhatsApp ni los permisos Trello.

## Evidencia y limitaciones

Por corrida: `corrida.json` registra configuracion y estado; `turnos.jsonl`
registra el avance del callback. `evaluacion.json` e `informe_riesgo.md` contienen
la evaluacion cuando esta disponible. `casos_simulados.json` conserva los casos
que DeepTeam haya expuesto incluso si falla posteriormente.

Un error no equivale a un ataque rechazado. El montaje propaga errores y rechaza
historiales de varios turnos, que requieren otra prueba. El proceso puede
interrumpirse antes de producir resultados completos: revisar siempre el estado.

El mapeo usa OWASP 2026 y conserva referencias 2025. Es una asociacion contextual,
no cobertura de las diez categorias. Las notas históricas de preparación se
mantienen fuera del repositorio en
`Modulo8_Evaluacion_y_Etica/Sesion23_Seguridad/NOTAS_PREPARACION_DEEPTEAM_2026-09-09.md`.
La campaña real del 2026-09-09 ejecutó 24 escenarios. Tras revisar siete juicios
inválidos, quedaron 21 favorables y tres sin puntuación válida. El entregable
para el docente está fuera del repositorio, en
`Modulo8_Evaluacion_y_Etica/Sesion23_Seguridad/EVALUACION_SEGURIDAD_MULTIAGENTE_CLEMENTE.md`.
No usar únicamente el `overview` de DeepTeam: en esta versión omitió errores
presentes en los casos individuales.

Para reproducir las etapas con el presupuesto compartido:

```powershell
python -m tests.seguridad.campana conexion_medida --env RUTA_AL_ENV --destino tests/seguridad/deepteam-results/NUEVA_CAMPANA
python -m tests.seguridad.campana funcional --env RUTA_AL_ENV --destino tests/seguridad/deepteam-results/NUEVA_CAMPANA
python -m tests.seguridad.campana humo --env RUTA_AL_ENV --destino tests/seguridad/deepteam-results/NUEVA_CAMPANA
python -m tests.seguridad.campana completo_repeticion --env RUTA_AL_ENV --destino tests/seguridad/deepteam-results/NUEVA_CAMPANA
```

Ejecutar secuencialmente: el presupuesto compartido no admite varios procesos
simultáneos. Este ejecutor fija Terra y Sonnet 5 y un límite conservador de US$4
por proveedor; el comando `red_team_reservas` por sí solo no aplica ese control.
La etapa `trello` crea una tarjeta real y un comentario de prueba. No se ejecuta
como parte de los ataques aislados.
