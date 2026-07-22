# `04_unified_agent.py` — Agente Unificado (Utility-Based completo)

Este README explica **por qué se crea un cuarto agente** además de los tres
que ya existen (`01_model_based_reflex_agent.py`, `02_goal_based_agent.py`,
`03_utility_based_agent.py`) y en qué se diferencia concretamente. El README
principal (`README.md`) sigue siendo válido para justificar la elección de
los tres tipos de agente frente al profile card; este documento es
complementario y solo cubre el `04`.

## TL;DR

- Los archivos `01/02/03` son **didácticos**: cada uno aísla **una sola
  capa** (memoria / meta / utilidad) y le quita el resto para que ese patrón
  de IBM se lea limpio. **No están apilados.**
- El `04` **no agrega un tipo de agente nuevo**: sigue siendo **utility-based**.
  Lo que hace es **construir de verdad el agente acumulativo** que `01/02/03`
  solo mostraban por partes, para que sirva como **producto** de punta a punta.
- Fórmula: `04` = score de utilidad del `03` **+** loop de meta del `02` **+**
  memoria del `01` **+** una regla reactiva de orientación temprana.

## 1. El punto de partida: la taxonomía IBM es acumulativa

Los tipos de agente de IBM/Russell-Norvig no son cajas separadas: cada uno
**contiene** al anterior. Un utility-based *es* un goal-based (tiene meta) que
*además* es model-based (tiene estado) que *además* reacciona:

```
reactivo (reglas)  ⊂  model-based (memoria)  ⊂  goal-based (meta)  ⊂  utility-based (optimiza)
```

Un agente se clasifica por su **capacidad más alta**. Por eso el `04`, que
alcanza la capa de utilidad, **es un agente utility-based** que incluye por
debajo el razonamiento hacia la meta, el modelo interno de memoria y las
reglas reactivas.

> El único tipo que queda **fuera** de esta cadena es el **Learning agent**:
> el aprendizaje es una dimensión *transversal*, no un peldaño más arriba. El
> `04` **no** es learning (no ajusta sus pesos con feedback). Ese sería el
> siguiente paso (v2), como ya anota el `README.md`.

## 2. Por qué NO bastaba con quedarnos con el `03`

En teoría, como un utility-based contiene a los demás, "bastaría con el `03`".
**Pero el `03` tal como está escrito no es un utility-based completo: es una
maqueta que ilustra solo la capa de utilidad y le amputaron todo lo de abajo.**

El `03` solo tiene 2 tools (`listar_opciones_reserva` y
`evaluar_opcion_reserva`). Como agente, eso significa que **literalmente**:

- ❌ **No puede hacer una reserva.** No tiene tool de confirmación/registro:
  sabe puntuar opciones, pero no cerrar el flujo.
- ❌ **No recuerda al cliente.** No tiene long-term memory: la `zona_favorita`
  se le pasa como parámetro cada vez; un cliente recurrente tendría que
  repetir su zona en cada conversación.
- ❌ **No tiene borrador (short-term).** No arrastra fecha/personas/zona en un
  estado propio.
- ❌ **No escala** a staff.
- ❌ **No distingue** "verificar disponibilidad exacta" (objetivo) de
  "recomendar entre varias" (utilidad).
- ❌ **No inyecta un modelo interno**: su `system_prompt` es estático.

Es decir: el `03` demuestra el **concepto** de utilidad, pero como agente
está **incompleto**. No sirve como producto.

## 3. Qué tiene el `04` que el `03` no

| Capacidad | `03` | `04` |
|---|---|---|
| Puntuar/rankear opciones (utility) | ✅ | ✅ |
| Cargar perfil de **long-term memory** (zona favorita recordada) | ❌ | ✅ `consultar_perfil_cliente` |
| Utilidad con **fallback** para cliente nuevo | ❌ (zona siempre por parámetro) | ✅ lee zona del estado, o neutro |
| **Estado interno / borrador** (short-term) | ❌ | ✅ `ClementeState` + `actualizar_borrador_reserva` |
| **`dynamic_prompt`** que inyecta el modelo interno cada turno | ❌ | ✅ |
| **Verificar disponibilidad exacta** (objetivo, separado de recomendar) | ❌ | ✅ `verificar_disponibilidad` |
| **Confirmar/registrar** la reserva (cerrar el flujo) | ❌ | ✅ `confirmar_reserva` (+ guardrail de confirmación explícita y revalidación) |
| **Escalar a staff** con contexto acumulado | ❌ | ✅ `escalar_a_staff` |
| **Orientación reactiva** (franjas del día sin pax) | ❌ | ✅ `resumen_disponibilidad_dia` |

El salto grande del `03` al `04` **no** fue una sola cosa: fue darle **memoria
persistente**, la capacidad de **cerrar la reserva** y el **escalamiento** —
todo lo que el `03` tenía amputado por ser una demo de una sola capa.

## 4. Disponibilidad objetiva vs. recomendación (decisión de diseño)

Una distinción central que el `04` implementa y el `03` no:

- **Verificar disponibilidad es OBJETIVO** (¿hay mesa sí/no?): idéntico para
  cualquier cliente, no requiere ranking → `verificar_disponibilidad`.
- **Recomendar entre VARIAS alternativas** es donde entra la utilidad → solo
  se dispara cuando no hay la combinación exacta → `buscar_alternativas`,
  que devuelve **varias** opciones **rankeadas por utilidad**.

### Utilidad con fallback (cliente nuevo vs. conocido)

El score combina 3 señales y **se adapta solo**:

- cliente **conocido** → hora pedida + `zona_favorita` (long-term) + capacidad
- cliente **nuevo** → hora pedida + capacidad (zona en valor neutro)

Así la recomendación funciona con o sin historial, y mejora cuando el cliente
ya tiene perfil guardado.

## 5. La capa reactiva de orientación temprana

Se añadió una **regla reactiva** (condición → acción) para mejorar la UX:

> **Si** el cliente da una fecha pero aún faltan datos (personas/hora) →
> **acción:** mostrar las franjas abiertas de ese día **y** pedir lo que falta,
> en el mismo mensaje.

Implementada con `resumen_disponibilidad_dia(fecha)` + la "regla 0" del prompt.

**Cuidado clave:** la disponibilidad exacta *depende de los pax* (una franja
con mesas de 2 libres no sirve para 8). Por eso esta tool muestra **franjas
abiertas** (orientación), **no** mesas concretas, y siempre va acompañada de
la pregunta por el tamaño del grupo — nunca promete una mesa sin conocer los
pax.

```
Cliente:  "Quiero una reserva para mañana."
Clemente: "¡Genial! Mañana tenemos turnos de almuerzo (12:30–14:00) y cena
           (19:30–21:30). ¿Para cuántas personas y a qué hora, así te
           confirmo mesa exacta?"
```

Tener esta regla reactiva **no baja** la clasificación del agente: un
utility-based normalmente incluye reglas reactivas como atajos/guardrails.

## 6. Guardrails reflexivos encima del flujo deliberativo

- Confirmación **explícita** del cliente antes de `confirmar_reserva` (que
  además revalida disponibilidad por si el mundo cambió).
- `escalar_a_staff` de inmediato ante alergias, casos especiales, o cuando la
  meta no se alcanza tras varios intentos.

Es la arquitectura sensata: **deliberación** para decidir qué ofrecer,
**reglas reflexivas** rígidas para los límites que nunca se cruzan.

## 7. Relación con los otros archivos

| Archivos | Valor |
|---|---|
| `01` / `02` / `03` | **Pedagógico**: explican los tipos de IBM capa por capa, cada uno aislado. |
| `04` | **De producto**: acumula las tres capas en un solo agente que maneja el flujo real de punta a punta. |

No se eliminan `01/02/03`: siguen siendo la mejor forma de *explicar* cada
tipo por separado. El `04` es la forma de *usarlos juntos*.

## Cómo ejecutar

```bash
ollama pull llama3.2
pip install -r requirements.txt

python 04_unified_agent.py   # conversación multi-turno: memoria + meta + recomendación rankeada
```

La demo del `__main__` simula al cliente conocido `+51999111222` (zona
favorita: terraza) pidiendo las 20:00 en terraza —dejada ocupada a
propósito— para que se dispare la recomendación de alternativas rankeadas
ponderando su zona favorita.
