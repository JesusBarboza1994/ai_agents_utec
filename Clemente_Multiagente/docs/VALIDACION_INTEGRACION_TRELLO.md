# Validación de integración de Clemente con Trello

**Fecha:** 9 de septiembre de 2026  
**Carácter:** evidencia complementaria a la evaluación funcional y de seguridad

## Objetivo

Comprobar que un reclamo ficticio atendido por Clemente llega al tablero real
mediante MCP, se puede consultar y admite un comentario verificable en Trello.
La existencia de una incidencia en JSON no acredita entrega remota: el servicio
dispone de un respaldo local que puede funcionar aunque Trello falle.

## Procedimiento autorizado

1. Verificar credenciales, tablero, listas y catálogo de herramientas MCP.
2. Enviar al orquestador, con `gpt-5.6-terra`, un reclamo ficticio identificado
   como `[PRUEBA]`, sin datos de clientes reales.
3. Comprobar que se genera exactamente una incidencia en la sesión de prueba.
4. Leer la tarjeta correspondiente directamente desde Trello para verificar su
   existencia, nombre, contenido y lista.
5. Consultar el código mediante `consultar_ticket` de MCP.
6. Agregar un comentario `[PRUEBA]` mediante `comentar_ticket` y leer las acciones
   de la tarjeta para confirmar su persistencia remota.

La revisión del resultado se realiza contra la API y el estado almacenado, sin
usar un LLM como juez de la existencia de la tarjeta. Solo se utiliza un modelo
para el turno del agente que origina la incidencia.

## Transporte y permisos

La configuración disponible utiliza el servidor MCP en memoria dentro del
proceso; detrás del protocolo está la API real de Trello. No equivale a validar
un servidor MCP HTTP desplegado, su autenticación o una frontera entre procesos.

El catálogo debe publicar creación, consulta, listado y comentario. La ausencia
de herramientas para cerrar, mover, borrar o compensar limita lo que este
cliente puede invocar, pero no demuestra que la credencial de Trello tenga
permisos mínimos ni protege por sí sola un endpoint MCP expuesto públicamente.

## Resultado de ejecución

La lectura inicial del tablero **Incidencias Clemente** fue exitosa. Se
encontraron las listas Pendiente, En atención, Esperando cliente y Resuelto;
las etiquetas espera, otro, producto, reserva y servicio; y las herramientas
`crear_ticket`, `consultar_ticket`, `listar_tickets` y `comentar_ticket`.
No se encontraron listas ni etiquetas requeridas faltantes.

**Resultado: creación, consulta y comentario verificados en Trello real.**

| Comprobación | Evidencia | Resultado |
|---|---|---|
| Agente que atendió | `incidencias`, con `gpt-5.6-terra` | Correcto |
| Incidencia única de la sesión | `I-3A57A1` | Una incidencia |
| Tarjeta remota | [Abrir tarjeta de prueba](https://trello.com/c/SYLSWUfX) | Existe y contiene `[PRUEBA]` |
| Tipo y estado consultados por MCP | `producto`, `abierta` | Coinciden con la incidencia |
| Comentario por MCP | `Nota agregada al ticket I-3A57A1.` | Confirmación recibida |
| Lectura del comentario desde Trello | Texto encontrado entre las acciones de la tarjeta | Persistencia remota comprobada |
| Herramientas de cierre, movimiento, borrado y compensación | Ausentes del catálogo publicado | No expuestas en esta interfaz |

Respuesta de Clemente durante la prueba:

> Lamento lo ocurrido, plato frío y 40 minutos de espera no está bien. Registré
> la prueba con el código I-3A57A1; el restaurante responderá en un plazo de hasta
> 8 horas.

El plazo de ocho horas corresponde al tipo `producto` configurado y la tarjeta
incluye vencimiento. **No se verificó que una persona responda dentro de ese
plazo.** Conviene formularlo como plazo de atención establecido, evitando que
esta prueba de integración se interprete como garantía de atención humana.
Tampoco se comprobó asignación a un miembro concreto ni recepción de notificaciones.

## Alcance de las conclusiones

Una tarjeta y un comentario persistidos comprueban la ruta de integración
ensayada. No prueban que una persona haya recibido o leído una notificación,
atendido el reclamo ni cerrado el caso. No se ejecutan cierres, movimientos ni
borrados como parte de esta prueba.

La tarjeta de prueba queda identificada para distinguirla de trabajo operativo.
No se incluyen claves ni tokens en este documento ni en sus evidencias publicables.

## Evidencia local

`tests/seguridad/deepteam-results/campana_20260909/trello/`

Se conservaron `preflight.json`, `tablero.json`, `herramientas.json`,
`respuesta.json`, `tarjeta.json`, `consulta_mcp.json`, `comentario.json` y
`estado.json`, cuyo estado final es `completo`.
Los crudos permanecen excluidos de Git.
