# Cierre de un caso desde Trello hacia WhatsApp y el webchat

Cuando el personal mueve una tarjeta a la lista **Resuelto** en Trello, el cliente recibe, en WhatsApp o en su webchat: *"Tu caso G-XXXXXX fue resuelto por el equipo del restaurante. Si necesitas algo más, escríbenos por aquí."*

La misma entrega se usa cuando el personal **aprueba o rechaza** una solicitud de grupo desde el panel: el cliente se entera sin tener que escribir de nuevo.

Siglas: HMAC-SHA1 (*Hash-based Message Authentication Code* con SHA-1, firma que prueba que la llamada viene de Trello).

## Cómo funciona

1. Trello llama a `POST /api/webhook/trello` cada vez que algo cambia en el tablero.
2. Clemente comprueba la firma de la cabecera `X-Trello-Webhook` (HMAC-SHA1 del cuerpo más la URL registrada, con `TRELLO_SECRET`). Sin secreto o con una firma inválida responde 401.
3. Solo cuenta una tarjeta que **pasa de otra lista a Resuelto**. El caso se identifica por el código del título (`I-XXXXXX` o `G-XXXXXX`).
4. Se busca el caso en el registro local (`incidencias.json`) para saber qué conversación lo originó, y se envía el mensaje con el mismo servicio de aviso que usa la decisión del personal (`aviso_staff_service`). El texto pasa por la validación y la redacción de salida del chat.
5. Cada caso se avisa **una sola vez**: mover la tarjeta de ida y vuelta, o un reintento de Trello, no repiten el mensaje. El registro está en `avisos_cierre.json`, en la carpeta de datos.

## Qué pasa en cada caso

| Situación | Resultado |
|---|---|
| Tarjeta a Resuelto de un caso de WhatsApp | Se envía el mensaje |
| Caso del webchat | El aviso queda en la bandeja de su navegador y el chat lo muestra solo, en unos segundos (`enviado`, canal `webchat`). No usa Twilio ni la ventana de 24 horas |
| Otra lista, tarjeta nueva, otra acción o título sin código | Se ignora |
| Código que no existe | Se ignora |
| Twilio rechaza el envío | Responde 200 con el motivo; el caso no queda como avisado y un nuevo movimiento lo reintenta |

## Cómo llega al webchat

El webchat no tiene Twilio, así que el servidor deja el mensaje en una bandeja (`app/communication/services/bandeja_webchat.py`, archivo `bandeja_webchat.json` en la carpeta de datos) y la página del chat la consulta cada 4 segundos con `GET /api/chat/avisos`.

- **Cada navegador ve solo lo suyo:** la sesión sale de la cookie firmada, no de un dato que mande el cliente.
- **Entrega con acuse:** el chat avisa hasta qué número ya mostró (`visto`) y el servidor borra hasta ahí. Si una respuesta se pierde, el aviso se repite y el chat lo descarta por su número.
- **Si la página está cerrada:** el aviso espera en la bandeja y aparece cuando el cliente vuelva a abrirla con la misma sesión del navegador. Si cierra el navegador entero, la cookie de sesión se pierde y ese aviso ya no tiene a quién llegar.
- **Si el panel del personal está en la misma página que el chat:** el mensaje llega por la respuesta del panel y por la bandeja, pero se dibuja una sola vez.
- **Además**, la decisión queda siempre en el hilo de la conversación, para que el agente sepa que el personal ya decidió.

## Variables

| Variable | Para qué |
|---|---|
| `TRELLO_SECRET` | Secreto del Power-Up de Trello (`trello.com/power-ups/admin`, pestaña *API Key*). Firma cada llamada. |
| `TRELLO_WEBHOOK_URL` | URL pública exacta con la que se registra el webhook. La firma se calcula con ella. |

En Azure, `TRELLO_SECRET` va como **secreto** de la Container App y la variable lo referencia, igual que `TRELLO_TOKEN`.

## Probarlo en local

1. En el `.env`: `TRELLO_SECRET=<cualquier texto>` y `TRELLO_WEBHOOK_URL=http://127.0.0.1:5000/api/webhook/trello`. Para que el mensaje llegue de verdad, también las credenciales de Twilio (`TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_WHATSAPP_FROM`).
2. Levantar la app y dejar un caso de WhatsApp abierto (un reclamo o una solicitud de grupo) desde tu teléfono.
3. `python scripts/simular_cierre_trello.py <código del caso>` envía una llamada firmada como la de Trello.

Sin credenciales de Twilio la respuesta es `no_enviado` con el motivo; la firma, el reconocimiento del caso y el resto del camino se prueban igual.

## Llevarlo a producción

1. Agregar `TRELLO_SECRET` como secreto en Azure y `TRELLO_WEBHOOK_URL=https://<app>/api/webhook/trello` como variable; desplegar.
2. Comprobar que la URL responde: `curl -I https://<app>/api/webhook/trello` debe dar 200.
3. Registrar el webhook (modifica el tablero real): `python scripts/registrar_webhook_trello.py registrar https://<app>/api/webhook/trello`. Con `listar` se ve el estado y con `borrar <id>` se quita.
4. Mover una tarjeta de prueba a Resuelto y comprobar el WhatsApp.

## Límites

- **Ventana de 24 horas de WhatsApp (solo WhatsApp, no el webchat):** el mensaje es libre, así que solo llega si el cliente escribió en las últimas 24 horas. Pasado ese plazo, WhatsApp exigiría una plantilla aprobada, que esta versión no usa. Es una regla de WhatsApp Business, no se comprobó en la cuenta del proyecto.
- **La firma no se probó contra un Trello real**, solo con llamadas firmadas con el algoritmo documentado por Trello. Hasta el paso 4 de producción no hay certeza.
- La app escala a cero: el primer aviso tras un rato sin tráfico pasa por un arranque en frío. Trello reintenta, y el registro de avisos evita duplicados.
