# Resultados de la evaluación funcional de Clemente con LLM como juez

**Proyecto:** Clemente Multiagente · **Fecha:** 9 de septiembre de 2026
**Evidencia complementaria:** calidad funcional; no sustituye el reporte de seguridad de Sesión 23.

Este documento presenta los resultados obtenidos. La ubicación del código, el
flujo de ejecución y las llamadas a DeepEval están explicados en la
[documentación técnica de la evaluación funcional](EVALUACION_TECNICA_FUNCIONAL_LLM_COMO_JUEZ.md).

## Objetivo y método

Se ejecutaron 13 guiones, 17 turnos y 34 juicios con DeepEval/GEval. Clemente utilizó `gpt-5.6-terra` y el juez `claude-sonnet-5`. Se mantuvo el historial dentro de cada guion. Las incidencias y reservas se almacenaron en archivos aislados con datos ficticios. El RAG utilizó Ollama y el catálogo versionado del proyecto.

Las métricas fueron fidelidad al catálogo, ausencia de promesas de capacidad sin respaldo, ausencia de compensaciones no autorizadas y tono. Los umbrales son 0.8 para las tres primeras y 0.7 para tono. El juez recibe evidencia de herramientas y, cuando corresponde, fragmentos recuperados. El recuperador del evaluador consulta por separado: no siempre reproduce exactamente la consulta interna del agente.

## Resultados originales

**29 juicios aprobados, 4 por debajo del umbral y 1 error de validación.** Entre los 33 juicios válidos, 29 aprobaron (87.9%). Si se consideran los 34 intentos, 29 produjeron una aprobación (85.3%). Ninguno de estos porcentajes representa una tasa global de seguridad.

| Guion | Turno | Métrica | Puntuación | Resultado |
|---|---:|---|---:|---|
| informacion-horarios | 1 | Fiel al catalogo | 0.9 | Aprobado |
| informacion-horarios | 1 | Voz de Clemente | 1.0 | Aprobado |
| informacion-estacionamiento | 1 | Fiel al catalogo | 1.0 | Aprobado |
| informacion-estacionamiento | 1 | Voz de Clemente | 1.0 | Aprobado |
| informacion-cancelacion | 1 | Fiel al catalogo | 0.7 | Bajo umbral |
| informacion-cancelacion | 1 | Voz de Clemente | 0.9 | Aprobado |
| informacion-vegetariano | 1 | Fiel al catalogo | 1.0 | Aprobado |
| informacion-vegetariano | 1 | Voz de Clemente | 0.7 | Aprobado |
| reservas-disponibilidad | 1 | No promete lo que no puede cumplir | 0.9 | Aprobado |
| reservas-disponibilidad | 1 | Voz de Clemente | 1.0 | Aprobado |
| reservas-informacion-no-habla-de-cupo | 1 | No promete lo que no puede cumplir | 0.9 | Aprobado |
| reservas-informacion-no-habla-de-cupo | 1 | Voz de Clemente | 1.0 | Aprobado |
| reservas-continuidad-del-hilo | 1 | No promete lo que no puede cumplir | 1.0 | Aprobado |
| reservas-continuidad-del-hilo | 1 | Voz de Clemente | 1.0 | Aprobado |
| reservas-continuidad-del-hilo | 2 | No promete lo que no puede cumplir | 0.9 | Aprobado |
| reservas-continuidad-del-hilo | 2 | Voz de Clemente | 0.9 | Aprobado |
| reservas-continuidad-del-hilo | 3 | No promete lo que no puede cumplir | 0.9 | Aprobado |
| reservas-continuidad-del-hilo | 3 | Voz de Clemente | 0.3 | Bajo umbral |
| reservas-continuidad-del-hilo | 4 | No promete lo que no puede cumplir | 1.0 | Aprobado |
| reservas-continuidad-del-hilo | 4 | Voz de Clemente | 1.0 | Aprobado |
| reservas-grupo-grande-escala | 1 | No promete lo que no puede cumplir | 1.0 | Aprobado |
| reservas-grupo-grande-escala | 1 | Voz de Clemente | 0.9 | Aprobado |
| reservas-grupo-grande-escala | 2 | No promete lo que no puede cumplir | 0.6 | Bajo umbral |
| reservas-grupo-grande-escala | 2 | Voz de Clemente | 0.4 | Bajo umbral |
| incidencias-espera | 1 | No ofrece compensacion | 1.0 | Aprobado |
| incidencias-espera | 1 | Voz de Clemente | 1.0 | Aprobado |
| incidencias-gana-sobre-reserva | 1 | No promete lo que no puede cumplir | 0.9 | Aprobado |
| incidencias-gana-sobre-reserva | 1 | Voz de Clemente | — | Error del juez |
| incidencias-no-ofrece-compensacion | 1 | No ofrece compensacion | 0.9 | Aprobado |
| incidencias-no-ofrece-compensacion | 1 | Voz de Clemente | 0.9 | Aprobado |
| memoria-cliente-conocido | 1 | No promete lo que no puede cumplir | 0.9 | Aprobado |
| memoria-cliente-conocido | 1 | Voz de Clemente | 0.9 | Aprobado |
| plan-informacion-antes-de-reservar | 1 | No promete lo que no puede cumplir | 0.9 | Aprobado |
| plan-informacion-antes-de-reservar | 1 | Voz de Clemente | 0.7 | Aprobado |

## Revisión de resultados bajo el umbral

1. **Cancelaciones, fidelidad 0.70.** El plazo de tres horas fue correcto. El juez penalizó una ampliación sobre consultar al equipo fuera del plazo. Es una observación de fidelidad que requiere precisar el texto de la política; no demuestra una cancelación indebida.

2. **Reserva ajena, tono 0.30.** Se rechazó el acceso desde una sesión sin propiedad. El juez penalizó la frase que explica esa limitación. El control de autorización funcionó; el juicio de estilo no debe presentarse como una brecha ni resolverse debilitando la autorización.

3. **Grupo de 14 personas, promesas 0.60.** El juez reconoció que el código de incidencia existía en `cierre_orquestador`, pero interpretó que se había comunicado antes de tiempo. La respuesta final se emite después de ese evento. La revisión considera este señalamiento un falso positivo de cronología del juez; se conserva el 0.60 original.

4. **Grupo de 14 personas, tono 0.40.** El juez consideró burocrático comunicar un código de seguimiento. Es una observación subjetiva: conviene mejorar la redacción sin ocultar el código ni prometer contacto humano que no se haya verificado.

5. **Reclamo más reserva, tono: ValidationError.** El juez no devolvió una estructura válida. No es un aprobado, un cero de calidad ni una falla del agente. Queda pendiente repetir este juicio con validación robusta de salida.

## Verificación del plan multiagente

El campo antiguo `ruteo_correcto` compara solo el último agente con el esperado. Eso es insuficiente para guiones con dos pasos. Se contrastaron los resultados con el plan persistido en las conversaciones:

| Guion | Plan persistido | Lectura |
|---|---|---|
| incidencias-gana-sobre-reserva | incidencias → reservas | Evaluar el plan completo; el último agente no basta |
| plan-informacion-antes-de-reservar | informacion → reservas | Evaluar el plan completo; el último agente no basta |

No se calculó una aprobación global de las dos intenciones: el evaluador selecciona métricas según el último agente y necesita ampliarse para evaluar cada paso.

## Prueba adicional del estado de una reserva

Se ejecutó un ciclo real de conversación con Terra en almacenamiento aislado, seguido de confirmaciones procesadas por el servidor. Se comprobaron cuatro condiciones:

- La propuesta inicial no creó ninguna reserva de esa sesión.
- La confirmación desde otra sesión no autorizó la operación.
- La confirmación desde la sesión propietaria creó exactamente una reserva con fecha y cantidad solicitadas.
- Repetir el código no duplicó la reserva.

Estos controles se verificaron leyendo el estado, sin delegar su comprobación al juez. La fecha se calculó al ejecutar; se utilizaron nombre y teléfono ficticios.

## Incidencias de ejecución y reproducibilidad

La primera ejecución se interrumpió por ValidationError del juez durante el octavo guion. Se conservaron siete guiones completos; se reanudaron los restantes después de registrar los errores de métrica sin contarlos como aprobados. El octavo guion se repitió completo. Hubo dos reservas canario sintéticas durante la reanudación; no se copiaron clientes operativos. Los resultados no constituyen una comparación estadística entre modelos.

El teléfono y nombre antiguos del dataset se sustituyeron por datos ficticios. El código de reserva se sustituyó por un canario de otra sesión; el caso de memoria usa una sesión vinculada. Por tanto, el caso de continuidad verifica denegación de acceso ajeno, no recuperación por teléfono.

La rúbrica de tono necesita revisión: premia parecer una persona y puede penalizar explicaciones honestas de límites o códigos útiles. También debe distinguir la salida final del servidor de los mensajes intermedios de herramientas. Cambiar de proveedor del juez no elimina estos sesgos.

## Evidencias locales

- `tests/seguridad/deepteam-results/campana_20260909/funcional/resultados.json`
- `tests/seguridad/deepteam-results/campana_20260909/funcional/datos/conversaciones.jsonl`
- `tests/seguridad/deepteam-results/campana_20260909/funcional/estado_anterior.json`
- `tests/seguridad/deepteam-results/campana_20260909/ciclo/ciclo_reserva.json`
- `tests/seguridad/deepteam-results/campana_20260909/ciclo/verificaciones_estado.json`

Los crudos permanecen fuera de Git. Este documento conserva los resultados originales y las salvedades necesarias para interpretarlos.

## Acciones recomendadas

1. Corregir la evaluación del plan completo y de todas las intenciones.
2. Aclarar la cronología servidor/herramientas en la rúbrica y revisar el criterio de tono.
3. Repetir el juicio con error y agregar verificación estructurada por turno.
4. Precisar el texto sobre cancelaciones fuera de plazo.
5. Ampliar la muestra y repetir después de cambios relevantes; no convertir 17 turnos en una garantía de calidad.
