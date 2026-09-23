> Estado de integracion al 2026-09-18: consultar [PR_GUARDRAILS.md](PR_GUARDRAILS.md). Las cifras de 126 pruebas y referencias a Twilio futuro en este documento son antecedentes historicos.

# Ética y principios operativos de Clemente (Sesión 24, Módulo 8)

> **Alineado con:** `Modulo8_Evaluacion_y_Etica/Sesion24_Ethics/Sesion24_Etica_ANALISIS_COMPLETO.md`
> (análisis de la transcripción y el material del docente, 2026-09-09) y con la tarea grupal que
> pide ese material en su sección 11.2: documentar **3 a 5 principios operativos**, usando su
> plantilla, más la actualización de la Agentic Profile Card.
>
> **Aclaración necesaria antes de leer esto:** los guardrails técnicos que Clemente ya tiene
> implementados (Guardrails AI, PII, autorización por sesión, HITL) **no son, por sí solos, este
> documento**. El propio material del curso lo dice explícitamente (§9.6 del análisis): *"Un
> filtro de sesgo textual no mide equidad en decisiones. Un detector de PII no verifica todas las
> condiciones de tratamiento de datos... El laboratorio aporta controles técnicos parciales dentro
> de una gobernanza más amplia."* Aquí se usan esos guardrails como **evidencia** de algunos
> principios, y se declara honestamente qué queda sin cubrir.

## 1. Las cuatro dimensiones, aplicadas a Clemente

| Dimensión | Pregunta | Estado en Clemente |
|---|---|---|
| Calidad | ¿El agente realiza la tarea? | Medido: 17/17 ruteo, 2/2 plan completo, evaluación GEval (`docs/EVALUACION_FUNCIONAL_LLM_JUDGE.md`) |
| Seguridad | ¿Resiste manipulación y limita acciones indebidas? | Guardrails AI, autorización por sesión, confirmación explícita, red team DeepTeam (24 escenarios, CVSS 0.0) |
| **Ética** | ¿La finalidad y sus efectos son justificables? | **Este documento** — parcialmente cubierto, con brechas declaradas abajo |
| Cumplimiento | ¿Satisface las obligaciones aplicables? | Parcial: PII redactado y autorización por sesión apoyan el art. 26; existe una clasificación interna argumentada como riesgo aceptable, pendiente de validación formal si el sistema pasa a producción |

Estas cuatro dimensiones no son intercambiables: que Clemente pase sus pruebas de seguridad no
demuestra que su diseño sea éticamente justificable, y viceversa.

## 2. Mapeo rápido a NIST AI RMF (Govern / Map / Measure / Manage)

| Función | Trabajo concreto en Clemente | Entregable / evidencia |
|---|---|---|
| **Govern** | Responsables por frente (`README.md`, sección 2); reglas de archivos compartidos en `ACUERDOS_EQUIPO.md` | Tabla de responsables + `app/contratos.py` como costura única |
| **Map** | Alcance cerrado (información, reservas, incidencias — pedidos y delivery fuera); afectados: cliente del restaurante, *staff* que atiende incidencias y aprueba HITL | `README.md`, sección "Alcance cerrado del entregable" |
| **Measure** | Evaluación funcional (DeepEval/GEval), precisión del RAG, red teaming | `docs/EVALUACION_FUNCIONAL_LLM_JUDGE.md`, `docs/EVALUACION_TECNICA_SEGURIDAD_MULTIAGENTE.md` |
| **Manage** | Guardrails deterministas + Guardrails AI como defensa en profundidad; HITL para excepciones de capacidad | README, sección "Seguridad con Guardrails AI, PII y toxicidad" |

## 3. Clasificación bajo el D.S. N.º 115-2025-PCM (argumentada, no un dictamen legal)

Clemente es un asistente conversacional de un restaurante privado que **no** hace: vigilancia
masiva, decisiones automatizadas sobre crédito, empleo, salud o justicia, ni usa datos biométricos
para identificar personas. Bajo esa descripción funcional, no encaja en los supuestos de riesgo
alto o uso prohibido de los arts. 22–24 del reglamento. Sí le aplican, como a cualquier sistema:

- **Art. 26** (remisión al régimen de protección de datos, Ley N.º 29733 / D.S. N.º 016-2024-JUS):
  cubierto parcialmente — Clemente redacta PII en respuestas y trazas (`app/seguridad/pii.py`),
  pero no existe una política escrita de retención ni de atención de solicitudes de
  corrección/borrado de datos personales del cliente.
- **Art. 25** (transparencia algorítmica): formula obligaciones expresas para sistemas de riesgo
  alto. Clemente se clasifica internamente como riesgo aceptable, por lo que este documento no
  presenta el artículo como obligación directa e inequívoca. El etiquetado sigue siendo una buena
  práctica coherente con el art. 31.2 para el sector privado y con el principio de transparencia;
  hoy no está cubierto — ver Principio 4.
- **Art. 12** (necesidades de grupos vulnerables): no evaluado; Clemente no filtra ni identifica
  usuarios menores de edad, y el catálogo/reservas no distingue esa condición.

Esta clasificación es un argumento de trabajo del equipo, no una certificación legal. Debe
revisarse si el alcance del sistema cambia (por ejemplo, si se agregan pagos o perfiles de
crédito).

## 4. Principios operativos de Clemente

Se documentan 4, siguiendo la plantilla exacta del material de la Sesión 24 (§11.2).

---

### Principio 1: Minimización y protección de datos personales

**Por qué es relevante para este proyecto:** Clemente maneja nombre, teléfono y, en algunos casos,
detalles de un reclamo — datos que identifican a una persona real y que viajan por WhatsApp/Trello,
un canal y un servicio de terceros.

**Personas o grupos afectados:** clientes del restaurante que reservan o reclaman; indirectamente,
el *staff* que ve esos datos en Trello.

**Situación que podría vulnerarlo:** una traza, un log o una respuesta del modelo expone un
teléfono, correo o número de tarjeta completo; o un cliente recupera la reserva de otra persona
solo por conocer su teléfono.

**Compromiso concreto:** el teléfono y el nombre se usan solo dentro del flujo de reserva/reclamo
que los necesita; no se muestran completos en respuestas ni trazas; no se anticipa uso ajeno a
información, reservas o incidencias del restaurante.

**Control técnico y/o organizativo:** `app/seguridad/pii.py` (redacción de correo, DNI, IP, MAC,
teléfono y tarjetas en entrada, salida y trazas) + `app/agentes/autorizacion.py` (autorización por
sesión: conocer un teléfono o código no basta para leer, modificar o cancelar una reserva ajena).

**Flujo de datos que debe gobernarse:**

```text
Cliente -> webchat/WhatsApp -> filtros de entrada -> proveedor del LLM -> tools
                                      |                    |
                                      v                    v
                         historial y memoria       reservas / Trello
                                      |
                                      v
                              trazas y métricas
```

`PIIMiddleware` redacta correo y tarjeta antes de circular por el agente; el teléfono puede llegar
al modelo cuando es necesario para completar una reserva. Guardrails AI se ejecuta localmente en
un proceso aislado. La conexión futura con WhatsApp/Twilio y el backend Trello incorporan terceros
y exigen documentar finalidad, datos enviados, retención y condiciones del proveedor antes de usar
datos reales.

**Base o autorización para tratar los datos.** Ley N.º 29733 (Perú), sin necesidad de
consentimiento expreso adicional cuando el dato es necesario para una relación que el propio
titular inició: el nombre y el teléfono se recogen porque el cliente los entrega **para completar
la reserva o el reclamo que él mismo solicita** (ejecución de la solicitud del titular), no para
ningún fin distinto. Esto cubre nombre y teléfono dentro del flujo de reserva/incidencia. **No**
cubre: reutilizar esos datos para otro fin (marketing, por ejemplo, que Clemente no hace hoy), ni
justifica recoger datos que el flujo no necesita. No existe hoy un aviso de privacidad visible en
el webchat que informe esto al cliente antes de que escriba su teléfono — es la misma brecha de
transparencia del Principio 4, aplicada a datos personales, y debe cerrarse junto con esa.

**Responsable del banco de datos.** Los tres bancos de datos con PII del proyecto
(`app/agentes/datos/clientes.json` — memoria de largo plazo; `app/reservas/datos/reservas.json`;
`app/observabilidad/datos/conversaciones.jsonl`) hoy los mantiene cada responsable de frente
(Christian/Jean, Miguel, Adrián respectivamente, según `README.md` sección 2). Para efectos de
este documento, el equipo designa a **Christian y Jean como responsables de coordinación del
tratamiento de datos personales** del proyecto (son quienes mantienen el banco con más PII,
`clientes.json`, y el código de redacción en `app/seguridad/pii.py`) — sin que eso exima a Miguel
o Adrián de aplicar los mismos controles en su propio banco. Esta designación es interna, para el
entregable académico; si Clemente pasara a operar con clientes reales, correspondería evaluar el
registro formal ante la Autoridad Nacional de Protección de Datos Personales.

**Responsable con autoridad para actuar:** Christian y Jean (orquestador, agentes y RAG, según
`README.md` sección 2) para el código; el equipo completo para la política de datos.

**Prueba y criterio de aceptación:** `tests/test_pii.py` (4 pruebas) y `tests/test_seguridad_reservas.py`
(pruebas `test_conocer_codigo_no_permite_leer_reserva_ajena`,
`test_conocer_telefono_no_permite_leer_reservas_ajenas`) — las 126 pruebas locales pasan
(verificado el 2026-09-11).

**Evidencia disponible / pendiente:** disponible el control técnico y sus pruebas. **Pendiente:**
una política escrita de retención (cuánto tiempo se conserva `clientes.json` y
`conversaciones.jsonl`); un procedimiento para que un cliente pida corrección o borrado de sus
datos — el reglamento de protección de datos (Ley N.º 29733) lo exige y hoy no existe ese
procedimiento en Clemente; y un aviso de privacidad visible en el webchat antes de pedir teléfono
o nombre (ver "Base o autorización para tratar los datos" arriba).

**Respuesta ante incumplimiento:** si se detecta una fuga de PII en trazas o respuesta, se trata
como *bug* de seguridad de prioridad alta: se corrige el guardrail y se revisa el historial de
trazas afectado.

**Límite y fecha de revisión:** revisar antes de conectar WhatsApp real (aumenta el volumen y la
persistencia de datos de contacto reales) — objetivo: antes del 13 de octubre de 2026.

---

### Principio 2: Supervisión humana efectiva antes de comprometer capacidad del restaurante

**Por qué es relevante para este proyecto:** Clemente puede aceptar (o parecer aceptar) reservas
de grupos grandes, lo que compromete un recurso físico real (mesas) que el sistema no puede
verificar por sí solo más allá de un umbral.

**Personas o grupos afectados:** el cliente que pide una mesa para más de 10 personas; el
restaurante, que podría quedar comprometido con una capacidad que no tiene.

**Situación que podría vulnerarlo:** el agente confirma una reserva de grupo grande sin que nadie
del *staff* la revise, o el cliente cree que su pedido "ya quedó gestionado" cuando solo se escaló.

**Compromiso concreto:** ninguna excepción de capacidad (grupos de más de 10 personas) se ejecuta
sin que una persona del *staff* la apruebe explícitamente.

**Control técnico y/o organizativo:** `HumanInTheLoopMiddleware` + `interrupt()` +
checkpointer SQLite en `app/orquestador/grafo.py` y `app/agentes/reservas.py`; cola de revisión en
`GET /api/staff/revisiones` y `POST /api/staff/revisiones/<sesion_id>/resolver`, protegida con
`CLEMENTE_HITL_TOKEN`. Este es el guardrail que sí satisface, con evidencia real, la condición de
"autoridad para intervenir" que pide el material del curso (§5.3): la aprobación es sobre una
acción concreta, antes de ejecutarla.

**Responsable con autoridad para actuar:** el *staff* del restaurante (vía el panel HITL);
Christian y Jean mantienen el mecanismo técnico.

**Prueba y criterio de aceptación:**
`tests/test_guardrails.py::test_middleware_interrumpe_y_solo_approve_ejecuta_la_tool`,
`tests/test_orquestador.py::test_aprobar_revision_reanuda_y_crea_ticket_en_el_cierre`,
`tests/test_orquestador.py::test_rechazar_revision_no_crea_ticket`, las pruebas de autenticación
del API de *staff* y el guion `reservas-grupo-grande-escala` de `tests/eval/casos.json`.

**Evidencia disponible / pendiente:** disponible el mecanismo y sus pruebas automatizadas.
**Pendiente:** una métrica de "tiempo de revisión" y "decisiones corregidas" real (el material del
curso, §5.3, advierte que un porcentaje de aprobación muy alto no prueba calidad si nadie mide el
tiempo de reacción del *staff*) — hoy no se registra cuánto tarda una aprobación real.

**Métricas a incorporar antes de la presentación:** tiempo medio y percentil 95 hasta decisión,
solicitudes aprobadas/rechazadas/vencidas, solicitudes sin atender y decisiones que evitaron una
operación incorrecta. Responsable: Christian y Jean para instrumentación; una persona designada
del *staff* para ejecutar la prueba operativa. Fecha objetivo: 2026-10-13.

**Respuesta ante incumplimiento:** si una excepción de capacidad se ejecuta sin aprobación
registrada, se trata como defecto de seguridad, no como caso de producto — se revisa el
middleware antes de seguir aceptando ese tipo de solicitud.

**Límite y fecha de revisión:** el panel de *staff* ya está implementado en el webchat. Antes del
2026-10-13 debe ejecutarse una prueba operativa cronometrada con una persona distinta del
desarrollador para medir tiempos de revisión reales.

---

### Principio 3: No prometer ni afirmar lo que el sistema no puede cumplir

**Por qué es relevante para este proyecto:** un cliente que cree tener mesa confirmada, o que
cree que alguien ya lo llamó, cuando eso no ocurrió, sufre un daño real y previsible: presentarse
al restaurante sin que exista su reserva.

**Personas o grupos afectados:** el cliente directamente; el restaurante, por la mala experiencia
resultante.

**Situación que podría vulnerarlo:** el agente redacta una respuesta que suena a confirmación
("tu mesa está lista") cuando en realidad la operación solo se **preparó** y falta el mensaje
`CONFIRMO <código>`; o el cierre anuncia un ticket o escalamiento que no ocurrió realmente.

**Compromiso concreto:** ninguna creación, modificación o cancelación se ejecuta directamente
desde una respuesta del modelo; toda promesa de contacto humano corresponde a un escalamiento que
sí ocurrió.

**Control técnico y/o organizativo:** flujo de preparación + confirmación explícita en
`app/agentes/autorizacion.py` (permiso de un uso, ligado a sesión, vigente 10 minutos); guardrail
de "cierre con evidencia del orquestador" en `app/orquestador/grafo.py` (no se anuncia una
reserva, ticket o escalamiento que no aparece en el resultado real de las *tools*); la métrica
`GEval` "No promete lo que no puede cumplir" en `tests/eval/metricas.py`.

**Responsable con autoridad para actuar:** Christian y Jean (agentes y orquestador).

**Prueba y criterio de aceptación:** `tests/test_seguridad_reservas.py::test_cierre_muestra_propuesta_aunque_modelo_afirme_confirmada`
y `test_ticket_real_reemplaza_codigo_inventado_y_no_promete_notificar`; métrica GEval en la
evaluación funcional (`docs/EVALUACION_FUNCIONAL_LLM_JUDGE.md`).

**Evidencia disponible / pendiente:** disponible y medido — es de los principios mejor cubiertos
del proyecto, con prueba determinista y evaluación con juez de LLM.

**Respuesta ante incumplimiento:** cualquier caso donde la evaluación funcional marque este
criterio por debajo del umbral se trata como regresión, igual que un caso de la sección 11 del
README (los "hallazgos que sí eran del agente" de la segunda corrida).

**Límite y fecha de revisión:** repetir la evaluación funcional cada vez que cambie el modelo por
defecto o el *prompt* de los agentes.

---

### Principio 4: Transparencia sobre el uso de IA frente al cliente

**Por qué es relevante para este proyecto:** aunque el art. 25 del D.S. N.º 115-2025-PCM dirige
su obligación expresa a sistemas de riesgo alto, su mecanismo de etiquetado y el deber general de
promover transparencia del art. 31.2 son referencias apropiadas para Clemente. El material del
curso (§5.2) también plantea como primera pregunta "¿se informa que se usa IA?".

**Personas o grupos afectados:** todo cliente que escribe al canal de Clemente, sin excepción.

**Situación que podría vulnerarlo:** un cliente conversa con Clemente creyendo que habla con una
persona del restaurante, y actúa de forma distinta a como lo haría sabiendo que es un asistente
automatizado (por ejemplo, confiando una promesa que "una persona" no haría, o no exigiendo la
misma verificación que le pediría a un humano).

**Compromiso concreto:** *(pendiente de implementar — ver más abajo)*.

**Control técnico y/o organizativo:** **no existe todavía.** Se verificó directamente el código el
2026-09-11: `app/agentes/prompts.py` no contiene ninguna instrucción para que el agente se
identifique como IA, y `app/web/templates/chat.html` (el webchat de demostración) tampoco muestra
un aviso al respecto. **Esta es una brecha real, no una omisión de este documento.**

**Responsable con autoridad para actuar:** Christian y Jean (prompt del sistema) y Jesús (canal de
comunicación/webhook de WhatsApp), antes de la conexión real con Twilio.

**Prueba y criterio de aceptación (propuesta, no implementada):** agregar una línea fija al inicio
de la primera respuesta de cada sesión nueva (p. ej. *"Soy Clemente, el asistente virtual del
restaurante..."*) y una prueba de contrato que verifique que el primer turno de cada sesión la
contiene.

**Evidencia disponible / pendiente:** **pendiente en su totalidad.** Se declara así en vez de
presentarlo como resuelto — es exactamente el tipo de honestidad que pide la sección 3.6 del
análisis de la Sesión 25 ("el profesor aceptó que el equipo declare hasta dónde llega la solución
y qué no resuelve").

**Respuesta ante incumplimiento:** mientras no se implemente, no se debe afirmar en la
presentación final que Clemente informa claramente al cliente que interactúa con IA.

**Límite y fecha de revisión:** implementar antes de la asesoría del 17 de septiembre de 2026, es
de bajo costo (una línea de *prompt* + un aviso en el webchat) y cierra una brecha que un revisor
externo detecta con facilidad.

## 5. Lo que este documento NO resuelve (declarado a propósito)

- **Equidad y no discriminación:** no existe todavía una evaluación ejecutada. Antes del
  2026-10-13, Christian y Jean prepararán pares equivalentes que varíen registro formal/coloquial,
  errores ortográficos y nombres sin cambiar la intención. Se compararán tasa de tarea completada,
  bloqueos y escalamientos. Criterio inicial: ninguna diferencia absoluta mayor a 10 puntos
  porcentuales entre variantes; si la muestra no permite una conclusión estadística, se declarará
  como exploratoria y no como prueba de ausencia de sesgo.
- **Impacto laboral:** no aplica de forma directa al alcance actual (Clemente no reemplaza personal
  del restaurante, atiende un canal adicional), pero si se retira la atención telefónica humana en
  favor de Clemente, este análisis debería repetirse.
- **Explicabilidad más allá de la traza técnica:** las trazas (LangSmith, `trazas.py`) registran
  qué *tool* se llamó y qué devolvió, pero no hay un mecanismo pensado para que un cliente pida
  "por qué me respondiste esto" y reciba una explicación en esos términos.

## 6. Checklist de la Sesión 24, aplicado a Clemente

- [x] Puedo explicar por qué el propósito del agente es justificable (información, reservas,
      incidencias de un restaurante — alcance cerrado y declarado).
- [x] Identifiqué afectados que no son usuarios directos (el *staff* que aprueba HITL y atiende
      Trello).
- [x] Distingo beneficios demostrados (evaluación funcional, pruebas) de beneficios prometidos.
- [ ] Definí métricas de equidad acordes al daño y contexto — **pendiente**.
- [x] Las explicaciones se apoyan en fuentes y decisiones registradas (RAG citado con
      `consultar_politica`, no de memoria).
- [x] Existe autoridad humana efectiva donde el impacto lo requiere (HITL, grupos >10).
- [x] Revisé datos, memoria, consultas a proveedores y logs (PII redactado en las tres capas).
- [ ] Clasifiqué el uso real bajo el D.S. N.º 115-2025-PCM con el detalle de retención y derechos
      de los titulares de datos — **parcial**, ver sección 3.
- [x] Mis principios operativos tienen controles y responsables verificables (sección 4).
- [x] Separé resultados medidos, propuestas y trabajo pendiente en todo este documento.

## 7. Fuentes normativas oficiales consultadas

- Decreto Supremo N.º 115-2025-PCM, Reglamento de la Ley N.º 31814, texto oficial de *El
  Peruano*: https://busquedas.elperuano.pe/dispositivo/NL/2436426-1
- Decreto Supremo N.º 016-2024-JUS, Reglamento de la Ley N.º 29733, publicación oficial:
  https://www3.congreso.gob.pe/Docs/DGP/DIDP/files/ds_016-2024-jus.pdf
- Autoridad Nacional de Protección de Datos Personales, entrada en vigencia del nuevo reglamento:
  https://www.gob.pe/institucion/anpd/campa%C3%B1as/128319-nuevo-reglamento-de-proteccion-de-datos-personales

La clasificación y el mapeo son un análisis académico del Grupo 02. No sustituyen una opinión
de la SGTD, la ANPDP ni una revisión legal si Clemente pasa a operar con clientes reales.
