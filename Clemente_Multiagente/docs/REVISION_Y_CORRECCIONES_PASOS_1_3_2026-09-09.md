# Revisión y correcciones — pasos 1 a 3

> **Registro histórico.** Este documento describe la fase inicial realizada antes de las
> campañas con DeepEval, DeepTeam y Trello del mismo día. El estado vigente y los resultados
> posteriores están en el README y en los demás documentos de `docs/`.

Fecha: 9 de septiembre de 2026. Alcance autorizado: establecer la versión,
reproducir los riesgos críticos y corregirlos con pruebas locales. No se corrió
DeepTeam, no hubo llamadas de pago, no se modificó el tablero de Trello.

## 1. Versión y punto de partida

- Carpeta de trabajo: `Proyecto_Final/Entregable_Final/clemente/`.
- Copia del grupo: `repo_grupo/`, rama local `feat/agentes`, HEAD `a4d3e52`.
  Estaba limpia respecto de su índice al inicio y al final. No se hizo fetch:
  esto describe la copia local, no certifica el estado remoto ni el PR.
- Antes de editar ya diferían `README.md`, `app/llm.py`, `tests/test_llm.py`,
  `tests/eval/banco_modelos.py`, `tests/eval/juez.py` y
  `tests/seguridad/red_team_reservas.py`. Se conservaron esas diferencias.
- Se eligió `clemente/` porque contiene las correcciones locales recientes.
  No se sobrescribió la copia del grupo ni se hicieron commits, push o merge.
- Base comprobada: **62 pruebas aprobadas**. La primera invocación desde la raíz
  del curso recogió por error pruebas ajenas y copias duplicadas; se corrigió el
  directorio y se limitó la colección a `clemente/tests`.
- No se encontraron instrucciones `AGENTS.md` en la búsqueda de las rutas del
  proyecto. Las carpetas `.pytest_cache` existentes devolvieron acceso denegado;
  no fue necesario leerlas ni cambiar permisos.

## 2. Reproducción antes de corregir

Se añadieron seis regresiones con reservas y clientes ficticios. Las seis
fallaron contra la implementación original:

| Caso | Comportamiento original comprobado | Corrección |
|---|---|---|
| Crear sin confirmación validada | La tool escribía inmediatamente | La tool prepara; el servidor exige confirmación posterior |
| Leer reserva ajena por código | Devolvía nombre, fecha y datos de reserva | Propiedad persistida por sesión |
| Leer reservas ajenas por teléfono | Devolvía códigos e historial | Filtro de propiedad; el teléfono no autentica |
| Cancelar reserva ajena | Cambiaba el estado | Propiedad y confirmación de un solo uso |
| Modificar reserva ajena | Cambiaba comensales | Propiedad, confirmación y comparación con el estado presentado |
| Error del orquestador | Prometía respuesta humana sin crear caso | Mensaje de incertidumbre sin promesa ni escalamiento ficticio |

El registro ficticio `error-prueba` generado durante la reproducción inicial se
retiró de la bitácora de conversaciones. Después se amplió el aislamiento de
fixtures para que registros, perfiles, permisos, reservas e incidencias usen
archivos temporales por prueba. No se borraron reservas o perfiles del equipo.

## 3. Cambios implementados

### Acceso y confirmación

`app/agentes/autorizacion.py` mantiene en SQLite el vínculo reserva–sesión y
las propuestas pendientes. No modifica el contrato ni sustituye el servicio
de reservas en JSON de Miguel.

Las herramientas de crear, modificar y cancelar preparan un resumen concreto.
El servidor lo devuelve sin reescritura del modelo. Para ejecutarlo, el cliente
envía `CONFIRMO <código>` en otro mensaje. Se valida sesión, código, vencimiento
y estado de la reserva; el permiso se consume antes de intentar la escritura.
Un mensaje ambiguo, un código ajeno, una instrucción añadida al código o una
repetición no ejecutan la operación. Un nuevo pedido o reset invalida el permiso.

Las confirmaciones se serializan dentro del proceso. La prueba de dos solicitudes
simultáneas con el mismo código demuestra una única reserva. Esto no convierte
las escrituras JSON en transacciones ni resuelve todos los escenarios multiproceso.

La herramienta de modificación también verifica el límite de 10 personas.
La ficha del cliente usa únicamente reservas vinculadas a su sesión; no confía
en que un identificador comience con `whatsapp-`. Incidencias aplica los mismos
permisos al consultar reservas y restringe consultas de tickets a su sesión.

### Identidad del canal

Flask firma una cookie con un identificador opaco generado en el servidor.
El JSON del chat no puede elegir otra sesión ni declarar un canal confiable.
Las consultas de trazas y conversaciones y el reset se restringen a la sesión
de la cookie. Se retiró el CORS global abierto; el webchat funciona en su origen.

El webhook genérico de desarrollo requiere un secreto de adaptador y por defecto
queda deshabilitado. Esto NO implementa ni reemplaza la validación de firma de
Twilio. El canal real sigue siendo trabajo de integración pendiente.

### Escalamiento y evidencia del juez

El cierre redacta el estado del escalamiento con el código realmente registrado,
elimina el supuesto código inventado por el modelo y no promete llamadas o avisos
que no puede comprobar. Un fallo de registro no se presenta como escalamiento
exitoso. Se verifica el resultado al agregar datos a un ticket existente.

Se encontró además que `comentar_ticket` en modo local decía haber registrado la
nota sin guardarla. Ahora la persiste y el cliente MCP distingue una anotación
exitosa de una respuesta de error. Hay prueba por el protocolo en memoria.

La evaluación recibía las tools del agente pero omitía el evento `escalado` que
ocurre después, en el cierre. Eso podía marcar como inventado un código agregado
correctamente por el servidor. `_tools_del_turno` ahora incluye ese evento y las
operaciones confirmadas por servidor, claramente identificados como tales.
Una regresión comprueba que el mismo código aparece en la respuesta, el ticket
guardado y la evidencia que recibirá el juez.

**No se certifica que el hallazgo histórico I-13A8DF fuera una alucinación.** La
evidencia del evaluador era incompleta. Los resultados históricos no se editaron;
deben volver a medirse cuando se autorice la evaluación con modelos.

## 4. Verificación final

**94 pruebas aprobadas en 9.69 segundos**, sin modelos reales ni Trello.
Los casos cubren rechazo y éxito: lectura propia y ajena, creación, modificación,
cancelación, vencimiento, repetición, concurrencia de la misma confirmación,
invalidación por nuevo pedido/reset, cambios posteriores al resumen, fuga por
Incidencias o memoria, suplantación HTTP y fallos de escalamiento.

Una prueba recorre la API Flask y el grafo con un agente simulado: el primer turno
prepara y no escribe; el segundo confirma, escribe y registra el propietario sin
ejecutar nuevamente al agente. La elección de herramientas por el modelo real
todavía no se ha vuelto a evaluar.

Comando utilizado desde `clemente/` en PowerShell:

```powershell
$env:PYTHON_DOTENV_DISABLED='1'
$env:LANGSMITH_TRACING='false'
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD='1'
& '.venv/Scripts/python.exe' -m pytest tests -q -p no:cacheprovider --basetemp=.test_tmp_final
```

Las fixtures también bloquean la carga del `.env`, quitan credenciales de los
proveedores y aíslan los archivos. La prueba existente de caída de MCP usa un
puerto local sin servicio; las demás pruebas MCP se ejecutan en memoria.

## 5. Compatibilidad y pendientes explícitos

- **Reservas anteriores / otro dispositivo:** no se adjudican por teléfono o
  código. Necesitan verificación y recuperación por el personal. No se implementó
  un mecanismo automático de identidad o recuperación; no se migraron permisos
  de datos antiguos por inferencia.
- **Cookie:** definir `CLEMENTE_SECRET_KEY` estable y privada en el entorno para
  conservar su validez entre reinicios. Sin esa variable se genera una clave
  efímera; perder la cookie implica perder acceso automático desde el navegador.
- **Integración:** clientes de `/api/chat` deben conservar cookies y usar el ID
  devuelto. El webhook de desarrollo necesita `CLEMENTE_WEBHOOK_TOKEN`. Las
  consultas globales de conversaciones ya no están abiertas por HTTP.
- **Equipo:** se tocaron también archivos de comunicación, configuración,
  fábrica Flask y observabilidad porque eran caminos de acceso al mismo dato.
  El cambio requiere revisión de los frentes de Jesús y Adrián al integrarlo.
  No se enviaron mensajes al equipo.
- **Persistencia:** reservas JSON, reglas de calendario/ocupación, historial RAM,
  concurrencia multiproceso y atomicidad entre reserva y permiso siguen pendientes.
  Un fallo entre ambas escrituras requiere reconciliación; el servidor no
  reintenta ciegamente una operación cuyo resultado sea incierto.
- **Seguridad completa:** no se auditó todo el servidor MCP HTTP ni dependencias,
  límites de gasto o despliegue. Estos cambios protegen las operaciones expuestas
  por el chat; no garantizan que todo texto libre del modelo carezca de alucinaciones.
- **Evaluación:** adaptar los guiones que asumían confirmación inmediata o acceso
  por teléfono/código, correr el modelo real y después DeepTeam pertenece a los
  pasos siguientes. Los porcentajes anteriores no certifican esta versión.
- **Repositorio del grupo:** pendiente integrar estos cambios junto con las seis
  diferencias locales preexistentes; evitar copiar una carpeta encima de la otra.

El README contiene una nota de precedencia y `.env.example` las dos variables
nuevas. La limpieza integral de documentación histórica queda para el cierre del
proyecto; esta revisión no presenta los pasos 4 a 8 como completados.


## Integración posterior en el repositorio del grupo

Las correcciones de este informe se integraron en `Clemente_Multiagente/`,
en la rama local `feat/agentes`, partiendo de `a4d3e52` sin cambios locales.
También se incorporaron las correcciones previas de resolución del modelo, juez,
banco de modelos y script de seguridad. Las secciones anteriores conservan
el registro de la revisión inicial; la carpeta definitiva ahora es esta.
No se copiaron credenciales, perfiles de clientes ni resultados generados.

Validación desde `repo_grupo/Clemente_Multiagente`: **94 pruebas aprobadas en
8.74 segundos**. Se utilizó el intérprete Python 3.13 del entorno virtual de
`../../clemente/.venv`, importando el código de la carpeta definitiva (verificado
por la ruta de `app.__file__`). También se comprobó que Flask sirve el webchat
actualizado con la sesión devuelta por el servidor. `git diff --check` pasó.

Los cambios quedaron en el árbol de trabajo de `feat/agentes`, sin commit ni
push. El informe ahora está incluido en `Clemente_Multiagente/docs/` y enlazado
desde su README. El archivo de clientes ya versionado en el repositorio no se
alteró ni se sustituyó por el de la copia local.
