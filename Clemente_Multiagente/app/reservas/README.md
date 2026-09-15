# Gestor de Reservas — léeme

Responsable: Miguel. Esta carpeta es el módulo de reservas de Clemente. Este
documento explica, en lenguaje simple, qué hay acá adentro y cómo el resto
del sistema lo usa — para que cualquiera del equipo lo entienda sin tener
que leer todo el código.

## ¿Qué problema resuelve esta carpeta?

Alguien tiene que saber qué mesas hay, cuáles están libres a qué hora, y
guardar/cambiar/cancelar reservas sin que dos clientes se peleen por la
misma mesa si escriben al mismo tiempo (uno por WhatsApp, otro por el
webchat). Eso es todo lo que hace esta carpeta. No decide qué responder al
cliente, no habla con el LLM, no valida permisos — eso lo hacen los agentes
(`app/agentes/`), que están fuera de esta carpeta.

## Los archivos

- **`servicio_json.py`** — la implementación original: guarda las reservas
  en un archivo `.json`. Simple, pero si llegan dos escrituras casi al mismo
  tiempo, puede pasar que las dos "vean" la mesa libre y ambas la reserven.
  Para desarrollar y probar rápido está bien; para la demo real, no.

- **`servicio_sqlite.py`** *(nuevo)* — la misma funcionalidad, pero guardada
  en una base SQLite en vez de un JSON. La diferencia importante: cada vez
  que se crea, modifica o cancela una reserva, se abre una transacción que
  "cierra la puerta" antes de mirar qué mesas hay libres. Si dos pedidos
  llegan al mismo tiempo, el segundo espera a que el primero termine, en vez
  de que los dos crean que la mesa está libre. Así no se duplican reservas.

- **`seed.py`** *(nuevo)* — genera la base SQLite desde cero, leyendo
  `datos/mesas.json` (que sigue siendo la única fuente de verdad sobre qué
  mesas existen, sus zonas y capacidades). Cada persona del equipo corre este
  script en su máquina para tener su propia base de pruebas — nadie depende
  de la base de otro. El archivo `.db` que genera **no se sube a git**.

  ```bash
  python -m app.reservas.seed                 # solo las mesas
  python -m app.reservas.seed --con-ejemplos  # + 2 reservas de muestra, útil para probar el chat
  ```

- **`__init__.py`** — el interruptor. Tiene una sola función,
  `obtener_servicio()`, que mira la variable de entorno
  `CLEMENTE_BACKEND_RESERVAS` (en tu `.env`) y decide si usar la versión JSON
  o la versión SQLite. **Nadie más en el proyecto debe importar
  `ServicioReservasJSON` o `ServicioReservasSQLite` directamente** — siempre
  se pide el servicio a través de esta función, así el resto del sistema
  nunca se entera de cuál de las dos está corriendo por debajo.

## Cómo lo usa el resto del sistema (ya integrado)

Los agentes (carpeta `app/agentes/`, de Christian y Jean) hacen esto:

```python
from ...reservas import obtener_servicio as servicio_reservas
...
servicio_reservas().crear_reserva(nombre=..., telefono=..., fecha=..., ...)
```

Es decir: piden el servicio, y usan sus métodos
(`consultar_disponibilidad`, `crear_reserva`, `modificar_reserva`,
`cancelar_reserva`, `obtener_reserva`, `buscar_reservas_de`) sin saber ni
importar nada de `servicio_json.py` o `servicio_sqlite.py`. Ya revisé el
código real de las tools (`app/agentes/tools/reservas_tools.py`) y llaman
exactamente esos métodos, con los mismos parámetros — no hay que cambiar
nada ahí para que funcione con SQLite.

Encima de este módulo, ellos agregaron `app/agentes/autorizacion.py`: una
capa de permisos y confirmación (el cliente tiene que escribir
`CONFIRMO <código>` antes de que se ejecute cualquier cambio, y solo puede
tocar reservas que están "vinculadas" a su sesión). Esa capa tiene su propia
base SQLite chiquita (`datos/autorizaciones.sqlite3`, solo permisos y
propuestas pendientes) — **no reemplaza ni toca la base de reservas**, solo
decide *cuándo* llamar a `crear_reserva` / `modificar_reserva` /
`cancelar_reserva` de este módulo.

## Cómo activar el backend nuevo

En tu `.env` (nunca en el código):

```
CLEMENTE_BACKEND_RESERVAS=sqlite
```

Con eso, la próxima vez que arranque la app, `obtener_servicio()` devuelve
`ServicioReservasSQLite` en vez de la versión JSON. Si el archivo `.db`
todavía no existe en esa máquina, hay que generarlo primero con `seed.py`
(ver arriba) — si no, tira un error claro pidiendo que lo corras.

Por defecto sigue en `json`, para no romper a nadie que no haya corrido
`seed.py` todavía. El cambio a `sqlite` es opcional hasta que el equipo
decida hacerlo el default (ver `ACUERDOS_EQUIPO.md`, sección 7.1).

## Cómo se prueba

`tests/test_reservas.py` tiene 7 pruebas de reglas de negocio (turnos
válidos, no se puede reservar una mesa ocupada, se asigna la mesa más
ajustada primero, etc.). El fixture en `tests/conftest.py` las corre **dos
veces**, una contra JSON y otra contra SQLite — 14 pruebas en total. Si
alguien rompe una regla de negocio en cualquiera de los dos backends, un
test falla.

```bash
pytest -q tests/test_reservas.py
```

## Para dónde va esto (pendiente, ver ACUERDOS_EQUIPO.md sección 7)

- Falta decidir si `sqlite` pasa a ser el backend por defecto para la demo
  final (hoy sigue en `json` por defecto).
- El registro de incidencias (hoy con Christian y Jean, provisional) podría
  unificarse con este mismo patrón de persistencia si el equipo lo decide.
- Para la demo con Twilio, la base vive en la máquina donde corre Flask
  (la de Jesús, por el webhook público). Cada quien tiene la suya para
  desarrollar.
