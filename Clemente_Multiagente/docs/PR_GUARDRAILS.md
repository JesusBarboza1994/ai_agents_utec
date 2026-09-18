# PR: Integrar guardrails y revision humana con los canales de Clemente

## Problema y resultado

La reorganizacion de canales del PR #7 elimino la antigua ruta donde estaban nuestros controles pendientes. El chat nuevo invocaba directamente al orquestador y WhatsApp usaba un puente simulado. Esta rama integra los controles del equipo en la estructura controllers/services y conecta ambos canales al flujo protegido.

Base: `origin/main`, commit `a46679f`, obtenido el 2026-09-18. Incluye PR #7, Azure OpenAI y PR #8 (reservas Postgres). Rama: `fix/guardrails-canales`. El trabajo original en `repo_grupo` permanece intacto; la integracion esta en el worktree hermano `repo_guardrails`.

## Cambios y ubicacion

| Archivo | Que hace |
|---|---|
| `app/communication/services/chat_service.py` | Aplica bloqueo local de tarjetas/secretos, Guardrails AI de entrada, orquestador, validacion de salida y redaccion antes del historial. Lo usan chat y WhatsApp. |
| `app/communication/services/message_service.py` | Sustituye el puente simulado en el flujo activo; recupera la ventana de Postgres, redacta texto historico y guarda entrada/salida redactadas. Conserva identidad estable del canal. |
| `app/communication/controllers/whatsapp_controller.py` | Exige firma Twilio y mantiene ack y trabajador asincronos. Envia la respuesta del flujo protegido. Registra tipo de error sin copiar contenido sensible de excepciones. |
| `app/communication/controllers/chat_controller.py` | Conserva identidad de cookie y devuelve estados de seguridad, autorizacion, escalamiento y revision humana para la UI. |
| `app/communication/controllers/staff_controller.py`, `app/communication/routes/__init__.py` | Restablece cola y approve/reject con token exclusivo del personal. |
| `app/seguridad/`, `guardrails_service/` | Recupera PII y el cliente/servicio aislado de DetectJailbreak y ToxicLanguage del trabajo del equipo. |
| `app/agentes/reservas.py`, `app/agentes/base.py`, `app/orquestador/grafo.py` | Integra HITL con checkpoint SQLite, reanudacion y cola persistente. |
| `app/agentes/autorizacion.py`, `app/agentes/tools/` | Mantiene propiedad por sesion y confirmacion exacta de un uso antes de escribir reservas. |
| `app/db/connection.py` | Usa pool seguro para hilos e inicializacion protegida para los trabajadores asincronos. |
| `app/config.py`, `.env.example`, `requirements.txt` | Combina configuracion Guardrails/HITL con Twilio, Postgres y Azure. |
| `Dockerfile`, `pyproject.toml` | Alinea la imagen con Python 3.13 utilizado por el proyecto y la validacion. |
| `.github/workflows/test-guardrails.yml` | Ejecuta auditoria documental y pytest con Postgres de pruebas aislado en cada PR. |
| `docs/GUIA_CODIGO.md`, `docs/INDICE_CODIGO.md`, `docs/verificar_documentacion.py` | Documenta funciones/nodos y verifica presencia de descripciones y sintaxis sin consumir APIs. |

## Validacion

- Suite con Python 3.13 y Postgres 16 en un contenedor temporal exclusivo: **193 aprobadas, 0 fallidas, 0 omitidas**. Incluye almacenamiento real redactado, confirmacion de WhatsApp, aislamiento de propiedad, firma de Twilio, rechazo de entrada/salida y HITL.
- Auditoria: **96 archivos Python, 633/633 elementos documentados, 0 problemas**.
- Seis warnings de dependencias: serializacion Pydantic del contexto y deprecaciones de DeepEval/DeepTeam. No representan fallos de pruebas.
- Las llamadas LLM, Twilio y Guardrails AI se simulan en estas regresiones; la persistencia Postgres del caso dedicado es real. No se afirma validacion de entrega real de WhatsApp ni conectividad con proveedores externos.
- Build Docker de produccion aprobado con Python 3.13. Suite repetida en Linux con dependencias recien resueltas de produccion y desarrollo: **193 aprobadas, 0 omitidas**; `pip check` sin incompatibilidades. CI instala ambos requirements conjuntamente.

## Configuracion y limites

Configurar `TWILIO_AUTH_TOKEN`, `TWILIO_ACCOUNT_SID`, `TWILIO_WHATSAPP_FROM` y `CLEMENTE_DATABASE_URL` para WhatsApp. La URL usada para comprobar la firma debe coincidir con la URL publica registrada en Twilio; si Azure recibe HTTP interno, configurar `TWILIO_WEBHOOK_URL` con la URL publica exacta (sin query string). Ese valor viene del entorno y no de cabeceras del cliente. No se acepta un bypass de firma.

Para validacion externa, levantar `guardrails_service` y configurar `CLEMENTE_GUARDRAILS_URL` y `CLEMENTE_GUARDRAILS_TOKEN`. La politica existente sigue permitiendo continuar cuando ese servicio esta deshabilitado o no disponible; el bloqueo PII local y la autorizacion siguen activos. Esto no garantiza deteccion externa de jailbreak/toxicidad durante una caida.

El personal configura `CLEMENTE_HITL_TOKEN` y aprueba/rechaza desde el panel. Aprobar tramita la excepcion; no confirma una mesa automaticamente. Resolver una revision devuelve una respuesta al personal, sin envio automatico adicional por WhatsApp. La entrega asincrona no implementa reintentos ni deduplicacion de MessageSid. Los datos operativos de cliente y reservas permanecen en sus tablas; lo redactado es el contenido de conversaciones, no todas las columnas del negocio. El cambio protege nuevos mensajes y redacta el historial al leer; no borra retrospectivamente mensajes crudos almacenados antes.

## Publicacion preparada

Titulo sugerido: **Integrar guardrails y revision humana con chat y WhatsApp**.

Publicar desde el worktree `repo_guardrails`:

```powershell
git push -u origin fix/guardrails-canales
```

Abrir el PR hacia `main` con esta descripcion y esperar `Validar PR` y `Pruebas de guardrails y canales`. Los requisitos de revision y merge dependen de las reglas del repositorio. La rama esta preparada localmente; no se ha hecho push, abierto PR, merge ni despliegue.
