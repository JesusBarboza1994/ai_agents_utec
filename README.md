# Agente_Reservas — Clemente Reservations

Implementación en Python de los tipos de **agente reflexivo (IBM)** que
mejor se ajustan al `agent_card_profile_reserva_v2.html` (Product Profile
Card de "Clemente Reservations"). Sigue la misma convención que
`/Examples`: cada script es autocontenido (LangChain 1.x `create_agent` +
Ollama `llama3.2`), con su propio mini-entorno simulado de restaurante, y
puede ejecutarse de forma independiente.

## Cumplimiento de la rúbrica de evaluación

| Criterio | Cómo se cumple |
|---|---|
| System Prompt asociado a cada tipo de agente | `02` y `03` usan `system_prompt=` explícito. `01` usa `dynamic_prompt` (equivalente funcional: genera el system prompt en cada paso inyectando el modelo interno), el mismo mecanismo que usa `02_model_based_reflex_agent.py` en `/Examples` para este tipo de agente. |
| ≥1 tool con docstring que dé contexto del problema | Cada archivo tiene tools cuyo docstring narra en prosa el riesgo de negocio que mitigan (ej. `verificar_disponibilidad` y `confirmar_reserva` explican por qué existe el guardrail de verificación en tiempo real / confirmación explícita; `escalar_a_staff` enumera los casos de riesgo del Criticality Dimension). |
| Short-term memory conforme a ejemplos de sesiones anteriores | Cada archivo incluye un bloque `EJEMPLOS_SESIONES_ANTERIORES` (few-shot) que enseña el patrón esperado, y los 3 agentes arrastran el historial de mensajes entre turnos (`continuar_conversacion`), demostrado con una conversación multi-turno en `__main__` donde el agente no vuelve a pedir datos ya dados antes en la misma sesión. |
| Actualización del Profile Card en base al uso de memoria | Pendiente de forma intencional: queda registrado como anotación de la rúbrica, no como tarea de esta entrega. |

## TL;DR — arquitectura elegida

**No hay un único tipo "correcto": el profile card describe un agente que
necesita memoria, persigue una meta y compara opciones — eso son tres
capacidades distintas.** Se proponen **3 agentes reflexivos
complementarios**, cada uno mapeado 1:1 a secciones concretas del profile
card, más un motivo explícito para **descartar** los otros 2 tipos de IBM:

| # | Archivo | Tipo IBM | Sección del profile card que resuelve |
|---|---|---|---|
| 1 | `01_model_based_reflex_agent.py` | **Model-Based Reflex** | Environment Definition → Knowledge, Long/Short Term Memory · Communication Layer ("continúa la conversación ya iniciada") |
| 2 | `02_goal_based_agent.py` | **Goal-Based** | Autonomy Dimension ("guía la reserva… escala casos especiales") · Criticality → guardrail de confirmación explícita y escalamiento tras fallos repetidos |
| 3 | `03_utility_based_agent.py` | **Utility-Based** | Objectives Definition ("ofrecer franjas disponibles") · Autonomy Dimension ("ofrece recomendaciones de horarios") |
| ✗ | — | Simple Reflex | **Descartado**: el profile card exige memoria explícita; un reflejo simple no tiene estado |
| ✗ | — | Learning | **Descartado por ahora**: no hay, en el profile card actual, un critico/loop de feedback definido; se propone como evolución v2 |

## 1. Por qué NO alcanza con un solo tipo de agente

El profile card no describe un agente de un solo comportamiento: describe
**capas independientes** (Communication, Context, Environment, Autonomy,
Criticality) y cada una empuja hacia una capacidad de agente distinta:

- **Environment Definition** exige *Long Term Memory* (nombre, teléfono,
  preferencias, alergias, zona favorita, historial) y *Short Term Memory*
  (fecha, hora, personas, ocasión, notas, opción elegida) → esto es,
  literalmente, la definición de IBM de un **modelo interno del mundo**.
- **Autonomy Dimension** dice explícitamente "Evaluates and recommends" y
  "Guides and escalates": el agente no solo reacciona, **persigue
  activamente completar una reserva** y sabe cuándo rendirse y escalar →
  esto es la definición de IBM de un **agente basado en objetivos**.
- El propio Autonomy Dimension añade "offers recommendations for available
  time slots" y los Objectives Definition piden "offer available time
  slots": cuando hay **varias** opciones válidas, alguien tiene que decidir
  cuál recomendar primero, sopesando horario vs. zona vs. uso eficiente de
  la mesa → esto es la definición de IBM de un **agente basado en
  utilidad**.

Un solo archivo que intentara cubrir las tres cosas a la vez perdería
exactamente la separación de responsabilidades que hace que cada patrón
sea fácil de razonar, testear y explicar en la justificación del proyecto.
Por eso se proponen **3 agentes especializados y complementarios**, no una
elección excluyente.

## 2. Los 3 agentes propuestos

### 2.1 `01_model_based_reflex_agent.py` — núcleo del sistema

Mantiene un **estado extendido** (`ClementeState`) con tres piezas de
modelo interno, actualizadas por tools que devuelven `Command`:

- `perfil_cliente` → Long Term Memory del profile card (persiste **entre**
  conversaciones, simulado con un diccionario indexado por teléfono).
- `borrador_reserva` → Short Term Memory del profile card (persiste
  **dentro** de la conversación actual).
- `disponibilidad_consultada` → lo que el agente ya percibió del entorno,
  necesario porque el entorno es **parcialmente observable**: la ocupación
  real del restaurante puede cambiar entre un mensaje y el siguiente, tal
  como exige el guardrail de "real-time availability verification before
  confirming any reservation".

Un `dynamic_prompt` inyecta ese modelo interno en cada turno, para que el
agente nunca vuelva a preguntar una alergia ya conocida ni pierda el
borrador de la reserva a mitad de conversación — la propiedad central que
distingue a un agente basado en modelo de uno reflejo simple.

### 2.2 `02_goal_based_agent.py` — flujo de la reserva

Sin estado persistente propio (esa responsabilidad ya la cubre el agente
1): su valor es el **razonamiento dirigido a una meta explícita** —
"reserva pendiente confirmada, respetando políticas, o escalar". Implementa
el ciclo intento → replanificación → reintento → escalamiento:

1. `buscar_alternativas_disponibles` — si la hora exacta pedida no está
   libre, busca las combinaciones más cercanas en vez de responder "no
   hay" sin más (replanificación hacia la meta).
2. `confirmar_reserva` — exige confirmación explícita previa del cliente
   antes de registrar nada (guardrail de "explicit customer confirmation
   before creating... a reservation").
3. `escalar_a_staff` — cuando la meta no se puede alcanzar por vía normal,
   modela el guardrail "after several failed attempts, escalates to a
   human with the accumulated conversation text".

### 2.3 `03_utility_based_agent.py` — motor de recomendación

Se apoya en una función de utilidad explícita, con pesos configurables,
sobre tres señales tomadas directamente del profile card:

- **score_horario** — cercanía a la hora que pidió el cliente.
- **score_zona** — coincidencia con la `zona_favorita` (Long Term Memory).
- **score_ajuste_capacidad** — evita asignar una mesa de 8 a 2 personas
  (uso ineficiente del local, un riesgo operativo real de un restaurante).

El `system_prompt` obliga a evaluar al menos 3 combinaciones antes de
recomendar y a **explicar el trade-off** (por qué no se recomendó la
opción más obvia), igual que exige IBM para un agente basado en utilidad.

## 3. Por qué se descartan los otros 2 tipos de IBM

- **Simple Reflex Agent** (`01_simple_reflex_agent.py` en `/Examples`) —
  por definición **no tiene memoria**: reacciona solo a la percepción
  actual. Esto choca directamente con la Environment Definition del
  profile card, que exige Long Term Memory y Short Term Memory como
  componentes de primera clase. Un reflejo simple tampoco podría cumplir
  la Communication Layer ("continues the conversation already started"),
  que presupone recordar turnos anteriores. Se descarta como arquitectura
  base, aunque el *patrón* de reglas condición-acción sigue vivo dentro de
  los guardrails de los otros 3 agentes (ej. "si no hay confirmación
  explícita → no registrar").

- **Learning Agent** (`05_learning_agent.py` en `/Examples`) — IBM lo
  define por tener un **crítico** que evalúa si una acción fue buena o
  mala y un elemento de aprendizaje que ajusta el comportamiento futuro
  con esa señal. El profile card **no define** todavía esa señal de
  refuerzo (por ejemplo: ¿la reserva terminó en no-show?, ¿el cliente
  canceló?, ¿el staff corrigió la recomendación del agente?). Forzar un
  agente de aprendizaje sin esa señal explícita sería inventar una
  capacidad no pedida. Es, sin embargo, la **evolución natural v2** más
  clara del sistema: el mismo patrón de `05_learning_agent.py` (store JSON
  persistente + tool de feedback) podría reutilizarse para que
  `evaluar_opcion_reserva` (agente 3) ajuste su `score_zona` o
  `score_horario` según el histórico real de no-shows/cancelaciones por
  zona u horario — pero eso requiere primero instrumentar esa señal de
  feedback en el sistema de reservas real, algo fuera del alcance actual
  del profile card.

## 4. Cómo se relacionan los 3 agentes en producción

En una implementación real, los tres no compiten — **se orquestan**: el
agente basado en modelo (1) es la capa de conversación que sostiene la
memoria a lo largo de todo el intercambio; dentro de ese flujo, delega en
el razonamiento del agente basado en objetivos (2) para saber cómo avanzar
hacia una reserva confirmada; y cuando ese razonamiento encuentra más de
una alternativa viable, delega en el agente basado en utilidad (3) para
decidir cuál ofrecer primero. Aquí se mantienen como 3 scripts
independientes (mismo criterio pedagógico que `/Examples`) para que cada
patrón se pueda leer, ejecutar y evaluar por separado.

## Cómo ejecutar

```bash
ollama pull llama3.2
pip install -r requirements.txt

python 01_model_based_reflex_agent.py   # conversación multi-turno con memoria
python 02_goal_based_agent.py           # entrada interactiva: pedido de reserva
python 03_utility_based_agent.py        # entrada interactiva: consulta de recomendación
```
# ai_agents_utec
