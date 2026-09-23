# Validación de persistencia y performance — Gestor de Reservas (Postgres)

Este documento es la evidencia de mis tres actividades asignadas:
(1) exponer endpoints y probarlos a mano, validando persistencia y performance;
(2) configurar la cadena de conexión Postgres compartida
(3) validar los inputs de una reserva.

## Qué quería comprobar

Quería ver, contra la base Postgres real del equipo (no un mock ni el SQLite
local), que:

1. el backend `postgres` de `ServicioReservas` guarda bien las reservas,
2. el candado `SELECT ... FOR UPDATE` evita el doble-booking con peticiones
   simultáneas de verdad,
3. la idempotencia aguanta reintentos concurrentes,
4. las validaciones de `app/reservas/validaciones.py` también corren por la
   ruta HTTP y no solo cuando pasa el LLM,
5. la latencia es razonable para lo que vamos a usar.

No borré ninguna de las filas que creé durante las pruebas. Quedan en la tabla
`reservas` de la base compartida como evidencia y se reconocen por nombre y
teléfono (tabla al final).

## Cómo lo hice

1. Configuré mi `.env` local con `CLEMENTE_BACKEND_RESERVAS=postgres`,
   `CLEMENTE_DATABASE_URL=<cadena de conexion bd> CLEMENTE_DEBUG_ROUTES=1`.
2. Verifiqué la conexión cruda con psycopg2 y que el esquema ya estuviera
   migrado (`chats/customers/mesas/messages/reservas/schema_migrations`).
3. Corrí `tests/test_reservas*.py` y `tests/test_seguridad_reservas.py` contra
   la base real.
4. Levanté `python run.py` (`threaded=True`, puerto 5000) con las rutas de
   depuración activas.
5. Probé el ciclo de vida de una reserva por HTTP: crear, consultar, modificar
   y cancelar, sin pasar por el LLM ni por el `CONFIRMO`.
6. Corrí `scripts/benchmark_reservas.py` contra el servidor real con tres
   escenarios: anti-doble-booking (15 peticiones simultáneas), idempotencia
   (15 peticiones idénticas) y escritura individual (5 reservas una tras otra).
7. Miré el estado final de la tabla `reservas` directo por SQL, sin pasar por la
   app, para tener una prueba independiente.

Todo lo revisé contra la base y las respuestas HTTP reales; no usé un LLM para
juzgar si algo se había guardado o no.

## Límites de lo que probé

- El servidor es el de desarrollo de Werkzeug, no un WSGI de producción. Esto no
  dice nada de cómo se comporta detrás de Twilio ni dentro del contenedor de
  Azure.
- Todo corrió desde mi máquina en Perú contra `pooled.db.prisma.io`. La latencia
  de red que aparece depende de esa ruta; en Azure puede ser distinta.
- Los 15 clientes peleando por la misma mesa y el mismo turno son un caso
  adversarial a propósito, para forzar el candado. No es tráfico típico.

## Resultados — pruebas automatizadas

| Suite | Resultado |
|---|---|
| `tests/test_reservas.py` (contrato de `ServicioReservas`, json + postgres) | 9 passed |
| `tests/test_reservas_validaciones.py` | todos passed |
| `tests/test_reservas_rutas.py` (endpoints de depuración, ahora con `PATCH`) | todos passed (3 tests nuevos de modificar) |
| `tests/test_seguridad_reservas.py` | passed (el resto se salta por falta de `ANTHROPIC_API_KEY`/`OPENAI_API_KEY` locales, no aplica a persistencia) |
| Suite completa sin evals ni red-team pesados | 163 passed, 40 skipped, 16 failed |

Los 16 fallos son los mismos que salen sin mis cambios (verifiqué con
`git stash`): vienen de `deepteam` y `httpx2`, que no están instalados en mi
venv, y no tienen relación con reservas.

## Resultados — ciclo de vida por HTTP

| Paso | Endpoint | Resultado |
|---|---|---|
| Crear | `POST /api/reservas` | `201`, `R-B19CD6`, mesa `M01` asignada |
| Consultar | `GET /api/reservas/<id>` | `200`, datos correctos |
| Modificar | `PATCH /api/reservas/<id>` con `{"hora": "21:00"}` | `200`, `R-4A9C1D` pasa de 20:00 a 21:00, `estado: modificada`; un `GET` posterior confirma que quedó guardado |
| Modificar con hora inválida | `PATCH` con `{"hora": "17:30"}` | `400`, mensaje con los turnos disponibles |
| Modificar reserva inexistente | `PATCH /api/reservas/R-NOEXISTE` | `404` |
| Cancelar | `POST /api/reservas/R-DB40FF/cancelar` | `200`, `estado: cancelada`. Es un UPDATE, no un DELETE: la fila sigue en la tabla |

## Resultados — concurrencia real (`scripts/benchmark_reservas.py`)

**A. Anti-doble-booking** (15 clientes distintos piden la misma mesa y turno con
8 personas, que solo cabe en `S01`):

| Métrica | Valor |
|---|---|
| Creadas (`201`) | 1 |
| Rechazadas (`400`, sin mesa) | 14 |
| Errores (`5xx`) | 0 |
| Latencia min / p50 / max | 861 ms / 2472 ms / 4015 ms |

Ganó exactamente una reserva. No hubo doble-booking ni errores 500.

**B. Idempotencia** (15 peticiones idénticas en paralelo):

| Métrica | Valor |
|---|---|
| Respuestas `201` | 15 de 15 |
| IDs distintos devueltos | 1 (`R-33A744`) |
| Latencia min / p50 / max | 1851 ms / 3761 ms / 5365 ms |

Un reintento de webhook no duplica la reserva: las 15 peticiones devuelven el
mismo id.

**C. Escritura individual** (5 reservas una por una, sin nadie más
compitiendo por el candado; esto es lo más parecido a un cliente real de
WhatsApp):

| Métrica | Valor |
|---|---|
| Creadas (`201`) | 5 de 5 |
| Latencia min / p50 / max | 814 ms / 824 ms / 1269 ms |

Corrí el benchmark completo varias veces y los resultados de A y B fueron
consistentes entre corridas (las de la sesión del 20/09 salieron `TODO OK`
las dos veces). Las cifras de arriba son de la primera de esas corridas.

## Análisis de performance

### Lo que había medido mal el 19/09

En la primera vuelta vi latencias mínimas de unos 2.8 s incluso para la
petición que gana sin esperar a nadie, y sospeché del pool de conexiones
(`SimpleConnectionPool(1, 5)` en `app/db/connection.py`). Lo revisé el 20/09 y
la sospecha era incorrecta. Hice dos comprobaciones:

**1. El pool no era el cuello de botella.** Hice el tamaño del pool
configurable con la variable `CLEMENTE_DB_POOL_MAX` (por defecto sigue en 5) y
corrí el benchmark con 5 y con 20 conexiones:

| Pool | A p50 | B p50 | C p50 |
|---|---|---|---|
| 5 (actual) | 2540 ms | 3472 ms | 854 ms |
| 20 | 3606 ms | 3345 ms | 960 ms |

Con cuatro veces más conexiones no mejoró nada; las diferencias son ruido. No
toqué el valor por defecto.

**2. El sobrecosto de ~2 s venía del cliente, no del servidor ni de la base.**
Incluso una petición rechazada por validación tardaba unos 2 s, lo que no tiene
sentido si el tiempo fuera de Postgres. La causa: en Windows, `requests`
resuelve `localhost` primero por IPv6 (`::1`), espera unos 2 s y luego cae a
IPv4. Al apuntar el benchmark a `127.0.0.1` los números bajaron así:

| Escenario | Con `localhost` | Con `127.0.0.1` |
|---|---|---|
| A, latencia mínima | 2781 ms | 726 ms |
| B, latencia mínima | 2983 ms | 823 ms |
| C, p50 | 2884 ms | 743 ms |

Por eso cambié la URL por defecto del script a `http://127.0.0.1:5000` y lo dejé
anotado en su docstring. Las cifras de la sección anterior ya son con
`127.0.0.1`. Los números que puse en la primera versión de este documento
(mínimos de ~2.8 s) estaban inflados por esto y los descarto.

### Cómo lo leo ahora

- Una escritura sola tarda unos **730 a 950 ms** de punta a punta. Se explica
  por los *round trips* a una base en la nube: medí aparte ~629 ms para
  `connect()` (TLS + auth), ~281 ms para el primer `SELECT 1` y ~111 ms para
  el segundo en la misma conexión, y cada reserva hace varias idas y vueltas
  (candidatas con `FOR UPDATE`, `INSERT`, chequeo de idempotencia).
- Bajo concurrencia (A y B) la latencia sube hasta 4 a 5 s porque las
  peticiones se ponen en fila detrás del candado, no por falta de conexiones.
  Eso es justamente lo que queremos que pase.
- Para tráfico normal de WhatsApp, un cliente pidiendo una reserva no compite
  con otros 14, así que la referencia es el escenario C (menos de un segundo).

## Hallazgos menores: cierre

Los tres hallazgos que había dejado pendientes quedan cerrados:

1. **Parseo de `--n` en `scripts/benchmark_reservas.py`.** Corregido con un
   parser explícito (`_parsear_args`) que consume el valor de `--n` y no lo
   confunde con la URL base. Verificado corriendo `--n 15` explícito.
2. **Endpoint HTTP para `modificar_reserva`.** Agregué `PATCH
   /api/reservas/<id>` en `app/reservas/rutas.py`, con 3 tests
   (`200`, `400` con hora inválida, `404` inexistente) y verificado además
   contra Postgres real (ver ciclo de vida arriba).
3. **Pool de conexiones y latencia de una escritura individual.** Medí las dos
   cosas (escenario C y comparación de pool 5 vs 20). El pool no es problema y
   la latencia individual es de unos 730 a 950 ms.

Cambios de código de este cierre: `app/reservas/rutas.py` (PATCH),
`tests/test_reservas_rutas.py`, `scripts/benchmark_reservas.py` (parseo de
`--n`, escenario C, `127.0.0.1` por defecto, fecha al azar por corrida para
que las corridas repetidas no agoten las mesas) y `app/db/connection.py` (pool
configurable por `CLEMENTE_DB_POOL_MAX`).

## Evidencia — tabla `reservas` (consultada por SQL directo, sin pasar por la app)

Al cierre del 20/09 la tabla tenía **46 filas: 24 confirmadas, 21 canceladas y
1 modificada**. Las pego completas (sin la columna de hash interno) para que se
pueda cruzar con la base:

| id | nombre | teléfono | fecha | hora | pers. | mesa | estado | creada |
|---|---|---|---|---|---|---|---|---|
| `R-B19CD6` | [PRUEBA] Ciclo de vida | 999888777 | 2026-09-30 | 20:00 | 2 | M01 | confirmada | 2026-09-19T14:32:36 |
| `R-DB40FF` | [PRUEBA] tmp | 111111111 | 2026-09-30 | 21:00 | 2 | M01 | **cancelada** | 2026-09-19T14:32:37 |
| `R-16F9D8` | Cliente 2 | 900000002 | 2026-09-24 | 13:00 | 8 | S01 | confirmada | 2026-09-19T14:33:24 |
| `R-BAC0B7` | Cliente Reintento | 994278348 | 2026-09-24 | 14:00 | 2 | M01 | confirmada | 2026-09-19T14:33:30 |
| `R-97FFB2` | Cliente 8 | 900000008 | 2026-09-25 | 13:00 | 8 | S01 | confirmada | 2026-09-20T11:12:21 |
| `R-E727B4` | Cliente Reintento | 949456892 | 2026-09-25 | 14:00 | 2 | M01 | confirmada | 2026-09-20T11:12:27 |
| `R-D3DB9F` | Cliente Reintento | 912651565 | 2026-09-25 | 14:00 | 2 | M02 | confirmada | 2026-09-20T11:13:05 |
| `R-9514E8` | Cliente Reintento | 967392745 | 2026-09-25 | 14:00 | 2 | M04 | confirmada | 2026-09-20T11:13:58 |
| `R-A45B6D` | [PRUEBA] Individual 0 | 806491573 | 2026-09-25 | 19:00 | 2 | M01 | confirmada | 2026-09-20T11:14:06 |
| `R-AF3A17` | [PRUEBA] Individual 1 | 824356828 | 2026-09-25 | 19:00 | 2 | M02 | confirmada | 2026-09-20T11:14:09 |
| `R-28BE45` | [PRUEBA] Individual 2 | 826535356 | 2026-09-25 | 19:00 | 2 | M04 | confirmada | 2026-09-20T11:14:12 |
| `R-2AF0DC` | [PRUEBA] Individual 3 | 851201538 | 2026-09-25 | 19:00 | 2 | M03 | confirmada | 2026-09-20T11:14:15 |
| `R-26216E` | [PRUEBA] Individual 4 | 892448080 | 2026-09-25 | 19:00 | 2 | M05 | confirmada | 2026-09-20T11:14:18 |
| `R-8F5ED3` | Cliente Reintento | 950189219 | 2026-09-25 | 14:00 | 2 | M03 | confirmada | 2026-09-20T11:14:23 |
| `R-6138BE` | [PRUEBA] Individual 0 | 881326863 | 2026-09-25 | 19:00 | 2 | S01 | confirmada | 2026-09-20T11:14:27 |
| `R-1ECD15` | Cliente Reintento | 917088593 | 2026-09-25 | 14:00 | 2 | S01 | confirmada | 2026-09-20T11:15:21 |
| `R-BE0E60` | Cliente Reintento | 909116623 | 2026-09-25 | 14:00 | 2 | M05 | confirmada | 2026-09-20T11:15:08 |
| `R-6E4F93` | Cliente 1 | 900000001 | 2026-10-02 | 13:00 | 8 | S01 | confirmada | 2026-09-20T11:15:53 |
| `R-33A744` | Cliente Reintento | 970384708 | 2026-10-02 | 14:00 | 2 | M01 | confirmada | 2026-09-20T11:15:57 |
| `R-9A85F4` | [PRUEBA] Individual 0 | 880440885 | 2026-10-02 | 19:00 | 2 | M01 | **cancelada** | 2026-09-20T11:16:03 |
| `R-7B7F77` | [PRUEBA] Individual 1 | 832541903 | 2026-10-02 | 19:00 | 2 | M02 | **cancelada** | 2026-09-20T11:16:04 |
| `R-EE6D56` | [PRUEBA] Individual 2 | 833657012 | 2026-10-02 | 19:00 | 2 | M04 | **cancelada** | 2026-09-20T11:16:05 |
| `R-270142` | [PRUEBA] Individual 3 | 848827911 | 2026-10-02 | 19:00 | 2 | M03 | **cancelada** | 2026-09-20T11:16:06 |
| `R-AD117E` | [PRUEBA] Individual 4 | 807040870 | 2026-10-02 | 19:00 | 2 | M05 | **cancelada** | 2026-09-20T11:16:06 |
| `R-2B8425` | Cliente 0 | 900000000 | 2026-10-18 | 13:00 | 8 | S01 | confirmada | 2026-09-20T11:16:12 |
| `R-8F2849` | Cliente Reintento | 920913349 | 2026-10-18 | 14:00 | 2 | M01 | confirmada | 2026-09-20T11:16:16 |
| `R-8C0FDF` | [PRUEBA] Individual 0 | 831629531 | 2026-10-18 | 19:00 | 2 | M01 | **cancelada** | 2026-09-20T11:16:23 |
| `R-37BBF5` | [PRUEBA] Individual 1 | 817355667 | 2026-10-18 | 19:00 | 2 | M02 | **cancelada** | 2026-09-20T11:16:24 |
| `R-8E705F` | [PRUEBA] Individual 2 | 889178819 | 2026-10-18 | 19:00 | 2 | M04 | **cancelada** | 2026-09-20T11:16:25 |
| `R-6F1511` | [PRUEBA] Individual 3 | 883741558 | 2026-10-18 | 19:00 | 2 | M03 | **cancelada** | 2026-09-20T11:16:26 |
| `R-548090` | [PRUEBA] Individual 4 | 866483897 | 2026-10-18 | 19:00 | 2 | M05 | **cancelada** | 2026-09-20T11:16:27 |
| `R-D26E66` | Cliente 0 | 900000000 | 2026-12-07 | 13:00 | 8 | S01 | confirmada | 2026-09-20T11:16:54 |
| `R-7ADCEE` | Cliente Reintento | 991289668 | 2026-12-07 | 14:00 | 2 | M01 | confirmada | 2026-09-20T11:16:58 |
| `R-AD5213` | [PRUEBA] Individual 0 | 869901404 | 2026-12-07 | 19:00 | 2 | M01 | **cancelada** | 2026-09-20T11:17:03 |
| `R-679E1B` | [PRUEBA] Individual 1 | 860709961 | 2026-12-07 | 19:00 | 2 | M02 | **cancelada** | 2026-09-20T11:17:04 |
| `R-890B54` | [PRUEBA] Individual 2 | 813954527 | 2026-12-07 | 19:00 | 2 | M04 | **cancelada** | 2026-09-20T11:17:05 |
| `R-A38EF8` | [PRUEBA] Individual 3 | 875950063 | 2026-12-07 | 19:00 | 2 | M03 | **cancelada** | 2026-09-20T11:17:05 |
| `R-97D9D8` | [PRUEBA] Individual 4 | 881687601 | 2026-12-07 | 19:00 | 2 | M05 | **cancelada** | 2026-09-20T11:17:06 |
| `R-4A9C1D` | [PRUEBA] Modificar | 999000111 | 2026-11-10 | 21:00 | 2 | M01 | **modificada** | 2026-09-20T11:17:10 |
| `R-361BA8` | Cliente 0 | 900000000 | 2026-11-05 | 13:00 | 8 | S01 | confirmada | 2026-09-20T11:17:27 |
| `R-0F4AAB` | Cliente Reintento | 961200665 | 2026-11-05 | 14:00 | 2 | M01 | confirmada | 2026-09-20T11:17:32 |
| `R-3ACBEC` | [PRUEBA] Individual 0 | 870219419 | 2026-11-05 | 19:00 | 2 | M01 | **cancelada** | 2026-09-20T11:17:37 |
| `R-DCF1EE` | [PRUEBA] Individual 1 | 871213293 | 2026-11-05 | 19:00 | 2 | M02 | **cancelada** | 2026-09-20T11:17:38 |
| `R-B45EF6` | [PRUEBA] Individual 2 | 806743545 | 2026-11-05 | 19:00 | 2 | M04 | **cancelada** | 2026-09-20T11:17:40 |
| `R-0E34D7` | [PRUEBA] Individual 3 | 803888372 | 2026-11-05 | 19:00 | 2 | M03 | **cancelada** | 2026-09-20T11:17:41 |
| `R-CC55F2` | [PRUEBA] Individual 4 | 802360268 | 2026-11-05 | 19:00 | 2 | M05 | **cancelada** | 2026-09-20T11:17:42 |

Cómo leer la tabla:

- `R-B19CD6` y `R-DB40FF` son el ciclo de vida a mano del 19/09 (esta última
  quedó `cancelada` por el endpoint, no borrada). `R-4A9C1D` es la del `PATCH`
  (pasó de 20:00 a 21:00, estado `modificada`).
- `Cliente N` (con 8 personas, mesa `S01`) son las ganadoras del escenario A.
  Hay una por corrida del benchmark, porque en cada corrida gana una sola.
- `Cliente Reintento` es el escenario B: una sola fila por corrida aunque se
  hayan mandado 15 peticiones, que es justo la idempotencia.
- `[PRUEBA] Individual N` es el escenario C. Las de la fecha 2026-09-25
  quedaron `confirmadas` porque las corrí antes de que el script cancelara sus
  reservas al terminar; desde ahí todas quedan `canceladas` para liberar mesas.
- Todas son datos de prueba (nombres `[PRUEBA]` o `Cliente N`, teléfonos
  inventados, fechas dentro de los próximos 90 días); ninguna es un cliente
  real. No borré ninguna a propósito, y cualquiera del equipo puede verificarlas
  con la cadena del `.env` (DBeaver, `psql` o un script corto).

## Alcance de las conclusiones

Estas pruebas comprueban persistencia, candado de concurrencia e idempotencia
contra la base real, y dan una medición de latencia tanto bajo concurrencia como
de una escritura individual. Lo que sigue sin comprobar es el comportamiento
bajo el WSGI de producción y el contenedor de Azure, porque todo corrió con el
servidor de desarrollo desde mi máquina. Eso queda para el momento del
despliegue y no bloquea la entrega de la parte de reservas.
