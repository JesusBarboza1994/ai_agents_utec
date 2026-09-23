# Indice de documentacion del codigo

Generado por `docs/verificar_documentacion.py`. Incluye codigo propio; excluye datos, caches y dependencias.

Archivos Python analizados: **105**. Elementos con descripcion: **783/783**.

Esta cobertura comprueba presencia de docstrings y sintaxis; no equivale a una prueba funcional ni garantiza por si sola la exactitud de cada descripcion.

Para entender el recorrido, entradas, salidas y limites, consultar [GUIA_CODIGO.md](GUIA_CODIGO.md).

## app/__init__.py

| Elemento | Descripcion |
|---|---|
| [modulo](../app/__init__.py#L1) | Fabrica de la aplicacion Flask (patron *application factory*). |
| [create_app](../app/__init__.py#L18) | Crea la aplicacion Flask con la configuracion recibida o la del entorno. |

## app/agentes/__init__.py

| Elemento | Descripcion |
|---|---|
| [modulo](../app/agentes/__init__.py#L1) | Los agentes especializados de Clemente -- responsables: Christian, Jean. |

## app/agentes/autorizacion.py

| Elemento | Descripcion |
|---|---|
| [modulo](../app/agentes/autorizacion.py#L1) | Autorizacion local: propiedad por sesion y confirmaciones fuera del LLM. |
| [_db](../app/agentes/autorizacion.py#L29) | Abre SQLite, crea las tablas de propiedad y propuestas si faltan y cede la conexion. |
| [vincular](../app/agentes/autorizacion.py#L45) | Persiste la propiedad de reserva_id para sesion. |
| [es_propietario](../app/agentes/autorizacion.py#L56) | Devuelve si SQLite vincula exactamente reserva_id con sesion; no usa el telefono. |
| [reservas_propias](../app/agentes/autorizacion.py#L62) | Devuelve las reservas vinculadas a sesion que todavia existen en servicio. |
| [_dia_y_fecha](../app/agentes/autorizacion.py#L71) | Devuelve el dia y la fecha (sabado 2026-10-10); el dia lo calcula el servidor, para que el cliente vea si coincide con lo que quiso. |
| [descartar](../app/agentes/autorizacion.py#L79) | Elimina la propuesta pendiente de sesion sin borrar la propiedad de sus reservas. |
| [proponer](../app/agentes/autorizacion.py#L86) | Prepara crear, modificar o cancelar sin escribir una reserva en el servicio. |
| [confirmar](../app/agentes/autorizacion.py#L151) | Solo un mensaje completo confirma; el LLM no interpreta ni ejecuta el permiso. |

## app/agentes/base.py

| Elemento | Descripcion |
|---|---|
| [modulo](../app/agentes/base.py#L1) | Andamiaje comun de los tres agentes. |
| [id_de_hilo](../app/agentes/base.py#L41) | Id del hilo del checkpoint: un hash de la sesion, para que el telefono no viaje a LangSmith. |
| [construir_agente](../app/agentes/base.py#L50) | Construye el agente LangChain con modelo, prompt y herramientas recibidos. |
| [_parece_llamada_de_tool](../app/agentes/base.py#L81) | Detecta la falla mas comun de los modelos locales chicos (llama3.2): en vez |
| [_armar_entrada](../app/agentes/base.py#L100) | Antepone al mensaje los datos del sistema que el modelo no debe adivinar. |
| [_olvidar_hilo](../app/agentes/base.py#L113) | Borra el checkpoint del hilo cuando el turno termino sin pausa para revision humana. |
| [ejecutar](../app/agentes/base.py#L130) | Invoca al agente y devuelve solo su texto de respuesta. |
| [reanudar_revision](../app/agentes/base.py#L204) | Reanuda el checkpoint del agente con Command(resume) y la decision recibida. |

## app/agentes/contexto.py

| Elemento | Descripcion |
|---|---|
| [modulo](../app/agentes/contexto.py#L1) | Contexto de la conversacion en curso: lo que el sistema ya sabe y el modelo no |
| [ContextoConversacion](../app/agentes/contexto.py#L23) | Viaja del orquestador a las tools y vuelve con lo que ellas anotaron. |
| [telefono_de](../app/agentes/contexto.py#L34) | El telefono del cliente cuando el canal lo trae en el identificador de sesion. |

## app/agentes/fecha.py

| Elemento | Descripcion |
|---|---|
| [modulo](../app/agentes/fecha.py#L1) | Reloj del restaurante: fecha, hora y dia de la semana en America/Lima. |
| [_zona_lima](../app/agentes/fecha.py#L17) | ZoneInfo de America/Lima; sin base de zonas (Windows, imagen slim) cae a UTC-5 fijo. |
| [_reloj](../app/agentes/fecha.py#L34) | Instante actual con zona horaria de Lima; las pruebas lo reemplazan por uno fijo. |
| [ahora](../app/agentes/fecha.py#L39) | Fecha y hora actuales en America/Lima, siempre con tzinfo. |
| [hoy](../app/agentes/fecha.py#L44) | Fecha de hoy en Lima, no la del servidor. |
| [nombre_dia](../app/agentes/fecha.py#L49) | Nombre en espanol del dia de la semana de `fecha`. |
| [dia_declarado](../app/agentes/fecha.py#L54) | Dia de la semana mencionado en `texto` ("el Sábado"), sin tilde, o None si no hay ninguno. |
| [contradiccion_dia](../app/agentes/fecha.py#L63) | Mensaje para el agente si el dia declarado no cae en `fecha_iso`; None si coincide. |
| [es_pasada](../app/agentes/fecha.py#L85) | True si `fecha_iso` es anterior a hoy en Lima. Una fecha invalida lanza ValueError. |
| [describir_ahora](../app/agentes/fecha.py#L90) | Fecha, dia y hora de este instante, como se le muestra al modelo en cada turno. |
| [proximos_dias](../app/agentes/fecha.py#L96) | Los proximos `cantidad` dias a partir de manana, como pares (nombre, fecha). |

## app/agentes/incidencias.py

| Elemento | Descripcion |
|---|---|
| [modulo](../app/agentes/incidencias.py#L1) | Agente de Incidencias y Experiencia. |
| [obtener_agente](../app/agentes/incidencias.py#L31) | Construye una vez el agente de incidencias con su prompt y herramientas y lo reutiliza. |
| [responder](../app/agentes/incidencias.py#L39) | Ejecuta el agente de incidencias con texto, sesion, historial y contexto de negocio. |
| [reiniciar](../app/agentes/incidencias.py#L53) | Fuerza reconstruir el agente. Lo usan los tests y el banco de modelos: |

## app/agentes/memoria.py

| Elemento | Descripcion |
|---|---|
| [modulo](../app/agentes/memoria.py#L1) | Memoria de largo plazo del cliente -- responsables: Christian, Jean. |
| [_leer](../app/agentes/memoria.py#L28) | Carga los perfiles del JSON; devuelve un diccionario vacio si falta o no puede leerse. |
| [_escribir](../app/agentes/memoria.py#L40) | Guarda todos los perfiles en JSON UTF-8, creando la carpeta si falta. |
| [_clave](../app/agentes/memoria.py#L51) | Un cliente se identifica por telefono; si no hay, por la sesion del webchat. |
| [recordar](../app/agentes/memoria.py#L56) | Guarda o actualiza lo que sabemos del cliente. Se llama desde las tools. |
| [perfil_de](../app/agentes/memoria.py#L80) | Busca el perfil por la clave derivada de sesion_id y telefono; devuelve None si falta. |
| [ficha_del_cliente](../app/agentes/memoria.py#L86) | Resume hasta tres reservas no canceladas vinculadas por el servidor a sesion_id. |

## app/agentes/prompts.py

| Elemento | Descripcion |
|---|---|
| [modulo](../app/agentes/prompts.py#L1) | Prompts de sistema del orquestador y de los dos agentes especializados. |

## app/agentes/rag/__init__.py

| Elemento | Descripcion |
|---|---|
| [modulo](../app/agentes/rag/__init__.py#L1) | RAG del Agente de Conocimiento -- responsables: Christian, Jean. |

## app/agentes/rag/indice.py

| Elemento | Descripcion |
|---|---|
| [modulo](../app/agentes/rag/indice.py#L1) | Indice vectorial (RAG) del catalogo validado del restaurante -- Sesion 13. |
| [_extraer_texto](../app/agentes/rag/indice.py#L46) | Lee texto de TXT, Markdown, DOCX o PDF segun la extension de ruta. |
| [_cargar_documentos](../app/agentes/rag/indice.py#L71) | Devuelve los documentos fragmentados y sus identificadores para el indice RAG. |
| [construir_o_cargar_indice](../app/agentes/rag/indice.py#L131) | Devuelve la coleccion Chroma, construyendola la primera vez. |
| [_id_seguro](../app/agentes/rag/indice.py#L158) | Azure Search solo acepta letras/digitos/_/-/= en la key -- se codifica el id legible. |
| [_cliente_azure_search](../app/agentes/rag/indice.py#L163) | SearchClient con AZURE_SEARCH_ENDPOINT/API_KEY/INDEX; sin endpoint o clave lanza KeyError. |
| [_empujar_a_azure_search](../app/agentes/rag/indice.py#L175) | Vectoriza los chunks y los sube con mergeOrUpload; devuelve cuantos acepto Azure. |
| [indexar_en_azure_search](../app/agentes/rag/indice.py#L198) | Reconstruye (o completa) el indice de Azure AI Search. Idempotente: usa |
| [_borrar_obsoletos_azure_search](../app/agentes/rag/indice.py#L217) | Borra del indice los chunks cuyo id ya no existe en el catalogo; devuelve cuantos borro. |
| [_asegurar_azure_search_indexado](../app/agentes/rag/indice.py#L236) | Primera consulta del proceso: si el indice esta vacio, lo puebla -- misma |
| [_buscar_azure_search](../app/agentes/rag/indice.py#L252) | Busqueda vectorial en Azure AI Search; los errores del SDK se propagan al llamador. |
| [buscar](../app/agentes/rag/indice.py#L275) | Busqueda semantica sobre el catalogo validado del restaurante. |

## app/agentes/reservas.py

| Elemento | Descripcion |
|---|---|
| [modulo](../app/agentes/reservas.py#L1) | Agente de Reservas y Capacidad. |
| [obtener_agente](../app/agentes/reservas.py#L44) | Construye y reutiliza el agente de reservas con checkpoint SQLite y middleware HITL. |
| [responder](../app/agentes/reservas.py#L81) | Ejecuta el agente de reservas con texto, sesion, historial y contexto. |
| [resolver_revision](../app/agentes/reservas.py#L97) | Reanuda el agente de reservas pausado en sesion_id con la decision del personal. |
| [reiniciar](../app/agentes/reservas.py#L105) | Fuerza reconstruir el agente. Lo usan los tests y el banco de modelos: |

## app/agentes/tools/__init__.py

| Elemento | Descripcion |
|---|---|
| [modulo](../app/agentes/tools/__init__.py#L1) | Tools de los tres agentes -- responsables: Christian, Jean. |
| [limpiar_texto](../app/agentes/tools/__init__.py#L29) | Deja `valor` en una sola linea, sin caracteres de control ni invisibles, y con un largo maximo. |
| [con_traza](../app/agentes/tools/__init__.py#L39) | Registra cada llamada a una tool: cuanto tardo, si fallo y en que sesion. |
| [con_traza.envoltura](../app/agentes/tools/__init__.py#L55) | Ejecuta la herramienta original y registra nombre, resultado y duracion por sesion. |

## app/agentes/tools/catalogo_tools.py

| Elemento | Descripcion |
|---|---|
| [modulo](../app/agentes/tools/catalogo_tools.py#L1) | Tools del Agente de Conocimiento (FAQs y politicas). |
| [_consultar](../app/agentes/tools/catalogo_tools.py#L22) | Llama `buscar()` y devuelve los fragmentos, o None si el indice fallo. |
| [buscar_en_catalogo](../app/agentes/tools/catalogo_tools.py#L38) | Busca en el catalogo validado del restaurante: horarios, ubicacion, carta, |
| [consultar_politica](../app/agentes/tools/catalogo_tools.py#L56) | Consulta una politica concreta (cancelacion, anticipacion, no-show, alergias, |

## app/agentes/tools/fecha_tools.py

| Elemento | Descripcion |
|---|---|
| [modulo](../app/agentes/tools/fecha_tools.py#L1) | Tool de fecha y hora, compartida por los tres agentes. |
| [get_current_datetime](../app/agentes/tools/fecha_tools.py#L19) | Devuelve la fecha, el dia de la semana y la hora actuales del restaurante |

## app/agentes/tools/incidencias_tools.py

| Elemento | Descripcion |
|---|---|
| [modulo](../app/agentes/tools/incidencias_tools.py#L1) | Tools del Agente de Incidencias y Experiencia. |
| [_parecida](../app/agentes/tools/incidencias_tools.py#L24) | True si dos descripciones son casi iguales (mismo reclamo repetido con otras palabras sueltas). |
| [registrar_incidencia](../app/agentes/tools/incidencias_tools.py#L31) | Registra el reclamo del cliente con estado, responsable y plazo. Llamar una vez que |
| [consultar_incidencia](../app/agentes/tools/incidencias_tools.py#L73) | Consulta el estado de un reclamo de la misma sesion del runtime. |
| [verificar_reserva_del_reclamo](../app/agentes/tools/incidencias_tools.py#L90) | Comprueba si el cliente tenia reserva, para no discutir con el sobre lo que dice |

## app/agentes/tools/reservas_tools.py

| Elemento | Descripcion |
|---|---|
| [modulo](../app/agentes/tools/reservas_tools.py#L1) | Tools del Agente de Reservas y Capacidad. |
| [_rechazo_de_fecha](../app/agentes/tools/reservas_tools.py#L26) | Texto de rechazo si el dia de la semana no cae en la fecha o la fecha ya paso; None si esta bien. |
| [consultar_disponibilidad](../app/agentes/tools/reservas_tools.py#L52) | Consulta que mesas hay libres. Usar SIEMPRE antes de afirmar que hay o no hay lugar. |
| [crear_reserva](../app/agentes/tools/reservas_tools.py#L86) | Prepara un resumen de reserva; NO escribe la reserva. |
| [buscar_mis_reservas](../app/agentes/tools/reservas_tools.py#L117) | Lista reservas propias de la sesion cuyo telefono coincide con el recibido. |
| [consultar_reserva_por_codigo](../app/agentes/tools/reservas_tools.py#L134) | Consulta una reserva propia por codigo, normalizado a mayusculas. |
| [modificar_reserva](../app/agentes/tools/reservas_tools.py#L155) | Prepara un cambio de una reserva propia, sin ejecutarlo. |
| [cancelar_reserva](../app/agentes/tools/reservas_tools.py#L180) | Prepara cancelar una reserva propia. No cancela hasta recibir CONFIRMO y su codigo. |
| [escalar_a_staff](../app/agentes/tools/reservas_tools.py#L189) | Deja el caso armado para una persona del restaurante. Usar con grupos grandes, |
| [solicitar_excepcion_grupo](../app/agentes/tools/reservas_tools.py#L224) | Solicita al staff revisar un grupo de más de 10 personas. |

## app/communication/__init__.py

| Elemento | Descripcion |
|---|---|
| [modulo](../app/communication/__init__.py#L1) | Gestion de comunicacion: WhatsApp (Twilio), sesiones y webchat -- responsable: Jesus. |

## app/communication/controllers/__init__.py

| Elemento | Descripcion |
|---|---|
| [modulo](../app/communication/controllers/__init__.py#L1) | HTTP controllers: request in, response out. No business logic here. |

## app/communication/controllers/chat_controller.py

| Elemento | Descripcion |
|---|---|
| [modulo](../app/communication/controllers/chat_controller.py#L1) | Webchat controller (`GET /`, `POST /api/chat`, `POST /api/sesiones/<id>/reset`). |
| [_estado_ui](../app/communication/controllers/chat_controller.py#L18) | Traduce la respuesta a tipo y etiqueta del estado visual. |
| [browser_session_id](../app/communication/controllers/chat_controller.py#L35) | Opaque identity signed by Flask; never comes from the client's JSON. |
| [chat_demo](../app/communication/controllers/chat_controller.py#L42) | Inicializa la identidad firmada del navegador y renderiza el chat con panel HITL. |
| [chat](../app/communication/controllers/chat_controller.py#L48) | Normaliza JSON, rechaza identidad ajena y devuelve respuesta protegida con estado visual. |
| [reset](../app/communication/controllers/chat_controller.py#L78) | Comprueba propiedad de la cookie antes de limpiar el hilo y propuestas pendientes. |

## app/communication/controllers/staff_controller.py

| Elemento | Descripcion |
|---|---|
| [modulo](../app/communication/controllers/staff_controller.py#L1) | Endpoints de revision humana con credencial exclusiva del personal. |
| [_staff_autorizado](../app/communication/controllers/staff_controller.py#L5) | Comprueba el Bearer token del personal con comparacion constante. |
| [listar_revisiones](../app/communication/controllers/staff_controller.py#L14) | Cola interna de decisiones; requiere un token distinto al webhook. |
| [resolver_revision_staff](../app/communication/controllers/staff_controller.py#L22) | Resuelve una revision HITL mediante POST autenticado del personal. |

## app/communication/controllers/whatsapp_controller.py

| Elemento | Descripcion |
|---|---|
| [modulo](../app/communication/controllers/whatsapp_controller.py#L1) | Twilio WhatsApp webhook controller (`POST /api/webhook/whatsapp`). |
| [handle_webhook](../app/communication/controllers/whatsapp_controller.py#L14) | Verifica la firma de Twilio antes de aceptar la identidad del remitente. |
| [_process_in_background](../app/communication/controllers/whatsapp_controller.py#L44) | Off the request thread on purpose: storing the message, generating the |
| [_process_in_background._run](../app/communication/controllers/whatsapp_controller.py#L57) | Procesa el turno protegido y envia la respuesta desde un contexto Flask independiente; registra errores sin contenido sensible. |

## app/communication/routes/__init__.py

| Elemento | Descripcion |
|---|---|
| [modulo](../app/communication/routes/__init__.py#L1) | URL wiring for the communication blueprint. No business logic here: every |

## app/communication/services/__init__.py

| Elemento | Descripcion |
|---|---|
| [modulo](../app/communication/services/__init__.py#L1) | Business logic for the communication channels, decoupled from Flask. |

## app/communication/services/chat_service.py

| Elemento | Descripcion |
|---|---|
| [modulo](../app/communication/services/chat_service.py#L1) | Flujo compartido de seguridad, orquestacion e historial para todos los canales. |
| [handle_incoming_message](../app/communication/services/chat_service.py#L8) | Atiende el turno normalizado y aplica los controles del canal en orden. |
| [reset_session](../app/communication/services/chat_service.py#L68) | Elimina historial y estado conversacional propio sin borrar reservas. |

## app/communication/services/llm_bridge.py

| Elemento | Descripcion |
|---|---|
| [modulo](../app/communication/services/llm_bridge.py#L1) | Bridge from a chat's message window to the LLM conversation. |
| [generate_reply](../app/communication/services/llm_bridge.py#L11) | Mocked reply, so the WhatsApp round trip can be tested before the real model is wired. |

## app/communication/services/message_service.py

| Elemento | Descripcion |
|---|---|
| [modulo](../app/communication/services/message_service.py#L1) | Channel-agnostic conversation flow. |
| [IncomingMessage](../app/communication/services/message_service.py#L32) | Canonical shape every channel adapter must produce. |
| [_get_or_create_chat](../app/communication/services/message_service.py#L45) | Resuelve cliente y chat sin guardar el contenido del mensaje entrante. |
| [handle_incoming_message](../app/communication/services/message_service.py#L57) | Stores the message against its customer/chat. Returns the chat_id, for |
| [digenerate_and_store_reply](../app/communication/services/message_service.py#L79) | Utilidad historica de pruebas: lee mensajes y ejecuta el puente simulado. |
| [process_incoming_message](../app/communication/services/message_service.py#L92) | Aplica el flujo compartido antes de persistir texto redactado y devolverlo. |

## app/communication/services/outbound_whatsapp_service.py

| Elemento | Descripcion |
|---|---|
| [modulo](../app/communication/services/outbound_whatsapp_service.py#L1) | Sends outbound WhatsApp messages to customers via the Twilio REST API. |
| [WhatsAppSendError](../app/communication/services/outbound_whatsapp_service.py#L17) | Twilio rejected or failed to deliver an outbound message. |
| [send_whatsapp_message](../app/communication/services/outbound_whatsapp_service.py#L21) | Sends `body` to `to_chat_key` via Twilio. Returns the outbound message SID. |

## app/communication/services/sesiones.py

| Elemento | Descripcion |
|---|---|
| [modulo](../app/communication/services/sesiones.py#L1) | Memoria de conversacion por sesion -- responsable: Jesus. |
| [Sesion](../app/communication/services/sesiones.py#L21) | Datos e historial acotado de un hilo de chat, conservados en memoria del proceso. |
| [Sesion.agregar](../app/communication/services/sesiones.py#L30) | Agrega rol y contenido al historial y conserva los ultimos MAXIMO_TURNOS mensajes. |
| [obtener_sesion](../app/communication/services/sesiones.py#L40) | Devuelve la sesion en memoria o crea una con sesion_id y canal si no existe. |
| [limpiar_sesion](../app/communication/services/sesiones.py#L47) | Retira la sesion del registro en memoria; no falla si no existe ni borra reservas. |
| [sesiones_activas](../app/communication/services/sesiones.py#L52) | Devuelve los identificadores de sesiones actualmente presentes en memoria. |

## app/communication/services/whatsapp_service.py

| Elemento | Descripcion |
|---|---|
| [modulo](../app/communication/services/whatsapp_service.py#L1) | Twilio WhatsApp adapter: request validation and payload translation. |
| [is_valid_request](../app/communication/services/whatsapp_service.py#L27) | Twilio's request validation: HMAC-SHA1 over the URL plus the sorted POST params. |
| [is_valid_account](../app/communication/services/whatsapp_service.py#L43) | Extra check beyond the signature: the message must come from our own |
| [parse_whatsapp_address](../app/communication/services/whatsapp_service.py#L54) | Strips the `whatsapp:` prefix and, for real numbers, the leading `+`. |
| [is_business_scoped_user_id](../app/communication/services/whatsapp_service.py#L60) | Reconoce identificadores de negocio de WhatsApp que sustituyen al telefono real. |
| [format_whatsapp_address](../app/communication/services/whatsapp_service.py#L65) | Rebuilds a Twilio address: business-scoped ids go without '+', numbers keep E.164. |
| [resolve_chat_key](../app/communication/services/whatsapp_service.py#L72) | Identifier used for both the chat and the customer record: `From` without |
| [resolve_phone](../app/communication/services/whatsapp_service.py#L83) | The real phone number, when the chat_key isn't a masked business-scoped id. |
| [media_content_type](../app/communication/services/whatsapp_service.py#L91) | MIME type of the first attachment, when the message carries media. |
| [parse_inbound](../app/communication/services/whatsapp_service.py#L96) | Translates Twilio's raw form payload into Clemente's channel-agnostic contract. |

## app/config.py

| Elemento | Descripcion |
|---|---|
| [modulo](../app/config.py#L1) | Configuracion unica del proyecto, leida del entorno (.env). |
| [Config](../app/config.py#L23) | Configuracion inmutable de Flask, modelos, seguridad, servicios y observabilidad. |
| [Config.falta_credencial](../app/config.py#L58) | Nombre de la variable de entorno que falta para poder llamar al modelo. |
| [Config.desde_entorno](../app/config.py#L77) | Construye Config a partir de variables de entorno y los valores predeterminados. |

## app/contratos.py

| Elemento | Descripcion |
|---|---|
| [modulo](../app/contratos.py#L1) | CONTRATOS: las costuras entre los cuatro frentes de trabajo del Grupo 02. |
| [MensajeEntrante](../app/contratos.py#L38) | Lo que llega de cualquier canal, ya normalizado por Comunicacion. |
| [RespuestaClemente](../app/contratos.py#L49) | Lo que el orquestador devuelve al canal. |
| [OpcionDisponibilidad](../app/contratos.py#L65) | Mesa disponible para una fecha y hora, con zona, identificador y capacidad. |
| [Reserva](../app/contratos.py#L75) | Registro de reserva con contacto, mesa, turno, estado y fecha de creacion. |
| [ServicioReservas](../app/contratos.py#L92) | Interfaz que implementa el Gestor de Reservas (Miguel). |
| [ServicioReservas.consultar_disponibilidad](../app/contratos.py#L101) | Devuelve mesas libres para fecha, hora y personas, filtradas opcionalmente por zona. |
| [ServicioReservas.crear_reserva](../app/contratos.py#L110) | Persiste una reserva y devuelve su registro; la falta de mesa produce ValueError. |
| [ServicioReservas.obtener_reserva](../app/contratos.py#L119) | Devuelve la reserva identificada o None si no existe; no comprueba propiedad aqui. |
| [ServicioReservas.buscar_reservas_de](../app/contratos.py#L123) | Devuelve los registros del telefono indicado; el llamador debe comprobar autorizacion. |
| [ServicioReservas.modificar_reserva](../app/contratos.py#L127) | Actualiza los campos recibidos de una reserva vigente, conservando los omitidos. |
| [ServicioReservas.cancelar_reserva](../app/contratos.py#L136) | Marca la reserva como cancelada y devuelve el registro, o None si no existe. |
| [Incidencia](../app/contratos.py#L146) | Caso de atencion vinculado a una sesion, con tipo, estado, responsable y plazo. |
| [ServicioIncidencias](../app/contratos.py#L161) | Contrato de creacion, consulta, anotacion y cierre de incidencias. |
| [ServicioIncidencias.crear_incidencia](../app/contratos.py#L166) | Registra un caso de la sesion y devuelve su codigo, estado inicial y plazo. |
| [ServicioIncidencias.listar_incidencias](../app/contratos.py#L173) | Devuelve los casos, filtrados por estado cuando se proporciona ese argumento. |
| [ServicioIncidencias.anotar](../app/contratos.py#L177) | Agrega un dato a una incidencia ya abierta, sin cambiarle el estado. |
| [ServicioIncidencias.cerrar_incidencia](../app/contratos.py#L188) | Cierra el caso con una nota opcional; devuelve el registro o None si no existe. |
| [Fragmento](../app/contratos.py#L198) | Un chunk recuperado del indice vectorial, con su fuente para citarla. |
| [Traza](../app/contratos.py#L211) | Un evento observable del sistema. Adrian decide a donde se envia. |

## app/db/__init__.py

| Elemento | Descripcion |
|---|---|
| [modulo](../app/db/__init__.py#L1) | Shared Postgres access: connection pool, migrations and per-table repositories. |

## app/db/connection.py

| Elemento | Descripcion |
|---|---|
| [modulo](../app/db/connection.py#L1) | Postgres connection pool. |
| [_pool_for](../app/db/connection.py#L28) | Obtiene o crea el pool de Postgres para la URL y aplica migraciones al inicializarlo. |
| [connection](../app/db/connection.py#L43) | Presta una conexion del pool; confirma al salir, revierte ante error y siempre devuelve la conexion. |

## app/db/migrate.py

| Elemento | Descripcion |
|---|---|
| [modulo](../app/db/migrate.py#L1) | Applies pending SQL migrations from `migrations/`, in filename order. |
| [apply_pending](../app/db/migrate.py#L22) | Runs every migration not yet recorded. Returns the filenames it applied. |

## app/db/repositories/__init__.py

| Elemento | Descripcion |
|---|---|
| [modulo](../app/db/repositories/__init__.py#L1) | One repository per table/aggregate: only place that writes raw SQL. |

## app/db/repositories/chats_repository.py

| Elemento | Descripcion |
|---|---|
| [modulo](../app/db/repositories/chats_repository.py#L1) | Repository for `chats`: the main table -- one thread per chat_key, linked to its customer. |
| [get_or_create_chat](../app/db/repositories/chats_repository.py#L9) | Existing chat id for `chat_key`, or a new row on first contact. |
| [touch](../app/db/repositories/chats_repository.py#L30) | Bumps `last_message_at` -- called whenever a new message lands on the chat. |

## app/db/repositories/customers_repository.py

| Elemento | Descripcion |
|---|---|
| [modulo](../app/db/repositories/customers_repository.py#L1) | Repository for `customers`: one row per person we've talked to on any channel. |
| [get_or_create_customer](../app/db/repositories/customers_repository.py#L9) | Existing customer id for `chat_key`, or a new row on first contact. |

## app/db/repositories/messages_repository.py

| Elemento | Descripcion |
|---|---|
| [modulo](../app/db/repositories/messages_repository.py#L1) | Repository for `messages`: every turn of a chat. |
| [append_message](../app/db/repositories/messages_repository.py#L16) | Inserta un mensaje en Postgres; el llamador debe entregar contenido redactado. |
| [get_recent_messages](../app/db/repositories/messages_repository.py#L29) | The chat's messages from the last `session_days`, oldest first. |

## app/incidencias/__init__.py

| Elemento | Descripcion |
|---|---|
| [modulo](../app/incidencias/__init__.py#L1) | Registro de incidencias -- lo consume el Agente de Incidencias (customer care). |
| [backend_activo](../app/incidencias/__init__.py#L29) | Cual de los tres backends esta activo: "mcp", "trello" o "json". |
| [obtener_servicio](../app/incidencias/__init__.py#L52) | Selecciona JSON, Trello o MCP con backend_activo y reutiliza la instancia del proceso. |
| [abiertas_de](../app/incidencias/__init__.py#L76) | Casos abiertos de esta conversacion creados en las ultimas `horas`. |
| [reiniciar_servicio](../app/incidencias/__init__.py#L104) | Descarta la instancia en memoria para reconstruirla con la configuracion vigente. |

## app/incidencias/mcp_trello.py

| Elemento | Descripcion |
|---|---|
| [modulo](../app/incidencias/mcp_trello.py#L1) | Servidor MCP de tickets de Clemente -- Sesion 16 (APIs y MCP). |
| [_backend](../app/incidencias/mcp_trello.py#L68) | El servicio que realmente habla con Trello. |
| [_como_dict](../app/incidencias/mcp_trello.py#L87) | Convierte la dataclass Incidencia en un diccionario para la respuesta estructurada MCP. |
| [crear_ticket](../app/incidencias/mcp_trello.py#L100) | Registra una incidencia con el backend del servidor y devuelve sus datos estructurados. |
| [consultar_ticket](../app/incidencias/mcp_trello.py#L123) | Consulta el estado actual de un ticket ya abierto, para responderle a un cliente |
| [listar_tickets](../app/incidencias/mcp_trello.py#L139) | Lista los tickets del restaurante, opcionalmente filtrados por estado. Sirve para |
| [comentar_ticket](../app/incidencias/mcp_trello.py#L150) | Deja una nota en un ticket existente, visible para el equipo del restaurante en la |

## app/incidencias/servicio_json.py

| Elemento | Descripcion |
|---|---|
| [modulo](../app/incidencias/servicio_json.py#L1) | Registro de incidencias sobre archivo JSON. |
| [ServicioIncidenciasJSON](../app/incidencias/servicio_json.py#L23) | Implementa el registro de incidencias en un archivo JSON local. |
| [ServicioIncidenciasJSON.__init__](../app/incidencias/servicio_json.py#L25) | Selecciona el archivo recibido o ARCHIVO; no crea registros hasta una escritura. |
| [ServicioIncidenciasJSON._leer](../app/incidencias/servicio_json.py#L29) | Carga la lista de incidencias o devuelve lista vacia si falta el archivo. |
| [ServicioIncidenciasJSON._escribir](../app/incidencias/servicio_json.py#L37) | Sobrescribe la lista de incidencias en JSON UTF-8, creando la carpeta si falta. |
| [ServicioIncidenciasJSON.crear_incidencia](../app/incidencias/servicio_json.py#L44) | Crea un codigo I-XXXXXX, persiste el caso abierto y devuelve la Incidencia. |
| [ServicioIncidenciasJSON.listar_incidencias](../app/incidencias/servicio_json.py#L64) | Carga los casos locales y devuelve dataclasses, filtrando por estado si se indica. |
| [ServicioIncidenciasJSON.anotar](../app/incidencias/servicio_json.py#L71) | Agrega un dato a una incidencia abierta, sin tocarle el estado. |
| [ServicioIncidenciasJSON.cerrar_incidencia](../app/incidencias/servicio_json.py#L87) | Solo para el panel del staff: ningun agente tiene tool para esto. |

## app/incidencias/servicio_mcp.py

| Elemento | Descripcion |
|---|---|
| [modulo](../app/incidencias/servicio_mcp.py#L1) | Los tickets de incidencia, hablados por MCP -- Sesion 16. |
| [_ejecutar](../app/incidencias/servicio_mcp.py#L47) | Corre una corutina desde codigo sincrono, haya o no un bucle de eventos. |
| [destino_mcp](../app/incidencias/servicio_mcp.py#L65) | A donde se conecta el cliente: una URL, o el servidor en memoria. |
| [ServicioIncidenciasMCP](../app/incidencias/servicio_mcp.py#L75) | Implementa `ServicioIncidencias` (app/contratos.py) contra el servidor MCP. |
| [ServicioIncidenciasMCP.__init__](../app/incidencias/servicio_mcp.py#L83) | Configura el destino MCP y el servicio JSON de respaldo; no abre la conexion aun. |
| [ServicioIncidenciasMCP._llamar_async](../app/incidencias/servicio_mcp.py#L92) | Abre un cliente MCP, llama a herramienta con argumentos y devuelve sus datos. |
| [ServicioIncidenciasMCP.llamar](../app/incidencias/servicio_mcp.py#L108) | Ejecuta la llamada MCP asincrona desde la interfaz sincrona y devuelve sus datos. |
| [ServicioIncidenciasMCP.herramientas](../app/incidencias/servicio_mcp.py#L112) | El catalogo que publica el servidor. Es la auditoria del limite de |
| [ServicioIncidenciasMCP.herramientas.pedir](../app/incidencias/servicio_mcp.py#L117) | Consulta las herramientas publicadas y devuelve nombre y primera linea de descripcion. |
| [ServicioIncidenciasMCP.crear_incidencia](../app/incidencias/servicio_mcp.py#L131) | Llama crear_ticket por MCP y devuelve Incidencia; ante error registra el caso en JSON. |
| [ServicioIncidenciasMCP.listar_incidencias](../app/incidencias/servicio_mcp.py#L148) | Consulta listar_tickets por MCP; ante error devuelve los casos del respaldo JSON. |
| [ServicioIncidenciasMCP.anotar](../app/incidencias/servicio_mcp.py#L156) | Pasa por `comentar_ticket`, que es la cuarta herramienta del servidor. |
| [ServicioIncidenciasMCP.cerrar_incidencia](../app/incidencias/servicio_mcp.py#L165) | NO pasa por MCP, y es la decision de diseno de todo este modulo. |

## app/incidencias/servicio_trello.py

| Elemento | Descripcion |
|---|---|
| [modulo](../app/incidencias/servicio_trello.py#L1) | Registro de incidencias sobre Trello -- el sistema donde el staff realmente trabaja. |
| [credenciales](../app/incidencias/servicio_trello.py#L63) | Clave y token de Trello. Nunca se imprimen ni se registran en una traza. |
| [hay_credenciales](../app/incidencias/servicio_trello.py#L68) | Devuelve si clave y token de Trello estan definidos, sin comprobar su validez remota. |
| [ServicioIncidenciasTrello](../app/incidencias/servicio_trello.py#L74) | Implementa `ServicioIncidencias` (app/contratos.py) contra un tablero de Trello. |
| [ServicioIncidenciasTrello.__init__](../app/incidencias/servicio_trello.py#L82) | Configura el nombre del tablero, respaldo JSON y caches de listas y etiquetas. |
| [ServicioIncidenciasTrello._pedir](../app/incidencias/servicio_trello.py#L94) | Hace una peticion a la API de Trello con credenciales y timeout. |
| [ServicioIncidenciasTrello._cargar_tablero](../app/incidencias/servicio_trello.py#L115) | Resuelve una sola vez el id del tablero, sus listas y sus etiquetas. |
| [ServicioIncidenciasTrello.verificar](../app/incidencias/servicio_trello.py#L143) | Comprueba que el tablero esta como el codigo espera. La usa el comando |
| [ServicioIncidenciasTrello.crear_incidencia](../app/incidencias/servicio_trello.py#L168) | Persiste primero el caso en JSON e intenta crear su tarjeta en la lista Pendiente. |
| [ServicioIncidenciasTrello.listar_incidencias](../app/incidencias/servicio_trello.py#L223) | El estado lo manda Trello: es donde una persona mueve la tarjeta. |
| [ServicioIncidenciasTrello._tarjeta_de](../app/incidencias/servicio_trello.py#L252) | Busca la tarjeta cuyo titulo comienza con incidencia_id; devuelve None si no existe. |
| [ServicioIncidenciasTrello.anotar](../app/incidencias/servicio_trello.py#L263) | Comentario en la tarjeta: es donde el staff lo va a leer. |
| [ServicioIncidenciasTrello.cerrar_incidencia](../app/incidencias/servicio_trello.py#L276) | Cierre desde el panel del staff. Ningun agente tiene tool para esto. |

## app/llm.py

| Elemento | Descripcion |
|---|---|
| [modulo](../app/llm.py#L1) | Resolucion del backend de LLM y de embeddings, en un solo lugar. |
| [precio_de](../app/llm.py#L109) | Precio (entrada, salida) por millon de tokens, o None si no lo conocemos. |
| [costo](../app/llm.py#L119) | Costo en dolares de una corrida, o None si el modelo no tiene precio conocido. |
| [modelo_activo](../app/llm.py#L128) | ID del modelo que se usaria ahora mismo. Lo usan el banco y los informes. |
| [proveedor_de](../app/llm.py#L145) | De que casa es un ID de modelo. Sin adivinar: prefijos conocidos. |
| [resolver_modelo](../app/llm.py#L165) | Devuelve el chat model ya instanciado segun AGENT_MODEL. |
| [resolver_embeddings](../app/llm.py#L265) | Modelo de embeddings del RAG, segun EMBEDDINGS_BACKEND. |
| [nombre_embeddings](../app/llm.py#L302) | Etiqueta del modelo de embeddings activo, para versionar la coleccion de Chroma. |
| [extraer_texto](../app/llm.py#L312) | Texto plano de un AIMessage, ignorando bloques de razonamiento extendido. |

## app/observabilidad/__init__.py

| Elemento | Descripcion |
|---|---|
| [modulo](../app/observabilidad/__init__.py#L1) | Observabilidad -- responsable: Adrian. |

## app/observabilidad/rutas.py

| Elemento | Descripcion |
|---|---|
| [modulo](../app/observabilidad/rutas.py#L1) | Endpoints de observabilidad. Los consume el panel interno y la demo final. |
| [salud](../app/observabilidad/rutas.py#L20) | Devuelve configuracion activa y presencia de credencial, sin llamar a modelos o servicios. |
| [trazas](../app/observabilidad/rutas.py#L37) | Devuelve trazas de la sesion del navegador hasta el limite solicitado. |
| [ver_metricas](../app/observabilidad/rutas.py#L49) | Devuelve las metricas agregadas de las trazas conservadas en el proceso. |
| [conversaciones](../app/observabilidad/rutas.py#L55) | Turnos con su texto, tal como quedaron en disco. Sobreviven al reinicio. |

## app/observabilidad/trazas.py

| Elemento | Descripcion |
|---|---|
| [modulo](../app/observabilidad/trazas.py#L1) | Observabilidad de Clemente -- responsable: Adrian. |
| [configurar_observabilidad](../app/observabilidad/trazas.py#L40) | Se llama una vez desde `create_app()`. |
| [registrar](../app/observabilidad/trazas.py#L70) | Registra un evento de negocio. Es la unica forma de escribir una traza. |
| [cronometro](../app/observabilidad/trazas.py#L90) | Mide cuanto tarda un bloque y lo deja registrado, pase lo que pase dentro. |
| [registrar_conversacion](../app/observabilidad/trazas.py#L109) | Escribe un turno completo (lo que dijo el cliente y lo que respondio Clemente) |
| [leer_conversaciones](../app/observabilidad/trazas.py#L157) | Ultimos turnos registrados, del mas antiguo al mas reciente. |
| [ultimas_trazas](../app/observabilidad/trazas.py#L176) | Devuelve las ultimas trazas en memoria, filtradas opcionalmente por sesion_id. |
| [metricas](../app/observabilidad/trazas.py#L184) | Metricas del informe final (Modulo 8). El desglose por herramienta y los |

## app/orquestador/__init__.py

| Elemento | Descripcion |
|---|---|
| [modulo](../app/orquestador/__init__.py#L1) | Orquestador multiagente -- responsables: Christian, Jean. |

## app/orquestador/grafo.py

| Elemento | Descripcion |
|---|---|
| [modulo](../app/orquestador/grafo.py#L1) | Orquestador de Clemente: grafo LangGraph con topologia *Supervisor*. |
| [_cargar_revisiones](../app/orquestador/grafo.py#L104) | Carga una sola vez las revisiones HITL persistidas al registro en memoria. |
| [_guardar_revisiones](../app/orquestador/grafo.py#L121) | Persiste las revisiones mediante archivo temporal y reemplazo del JSON. |
| [EstadoConversacion](../app/orquestador/grafo.py#L136) | Estado compartido que viaja por el grafo. |
| [PlanDeResolucion](../app/orquestador/grafo.py#L165) | Salida forzada del planificador: a quien llamar y en que orden. |
| [_sesion_de](../app/orquestador/grafo.py#L236) | Sesion del estado, con nombre propio cuando el grafo se lanza desde Studio. |
| [_mensaje_de](../app/orquestador/grafo.py#L241) | Texto del turno, o cadena vacia. |
| [_resumen_del_hilo](../app/orquestador/grafo.py#L252) | Resume los ultimos TURNOS_PARA_ENRUTAR mensajes para el planificador. |
| [_pendientes_de](../app/orquestador/grafo.py#L275) | Temas que el tope dejo fuera: pasos validos que no entraron al plan, o lo que el planificador marco PENDIENTE. |
| [_aviso_pendientes](../app/orquestador/grafo.py#L286) | Frase para el cliente con lo que quedo fuera del turno; nunca afirma haberlo resuelto. |
| [_limpiar_plan](../app/orquestador/grafo.py#L293) | Deja el plan en algo ejecutable: sin repetidos, sin desconocidos y con tope. |
| [_nodo_planificador](../app/orquestador/grafo.py#L310) | Calcula el plan ordenado de resolucion del turno y devuelve la actualizacion del estado. |
| [_nodo_trabajo](../app/orquestador/grafo.py#L367) | Devuelve el nodo ejecutor para un nombre del registro NODOS. |
| [_nodo_trabajo.nodo](../app/orquestador/grafo.py#L376) | Ejecuta el componente capturado por nombre y devuelve el progreso del turno. |
| [_siguiente](../app/orquestador/grafo.py#L406) | Selecciona la transicion condicional usando plan y paso, sin llamar al modelo. |
| [_sintetizar](../app/orquestador/grafo.py#L420) | Un solo mensaje a partir de varios. |
| [_escalamiento_previo](../app/orquestador/grafo.py#L451) | Codigo del ticket de escalamiento que esta conversacion ya abrio, aunque el proceso se haya reiniciado. |
| [_escalar](../app/orquestador/grafo.py#L459) | Abre el ticket del hilo, o le agrega el dato nuevo si ya habia uno. |
| [_nodo_cierre](../app/orquestador/grafo.py#L497) | Construye la respuesta final del recorrido del grafo y gestiona escalamiento. |
| [_construir_grafo](../app/orquestador/grafo.py#L567) | Construye y compila el StateGraph que ejecuta la orquestacion. |
| [obtener_grafo](../app/orquestador/grafo.py#L608) | Devuelve el grafo compilado del proceso, construyendolo solo en la primera llamada. |
| [reiniciar_grafo](../app/orquestador/grafo.py#L616) | Fuerza reconstruir el grafo y los agentes: lo usan los tests y el banco de modelos. |
| [_respuesta_de_limite](../app/orquestador/grafo.py#L634) | Respuesta fija de seguridad para un mensaje limitado; no llama al modelo y deja traza. |
| [responder](../app/orquestador/grafo.py#L643) | Punto de entrada del orquestador: lo unico que llama la capa de comunicacion. |
| [_responder_turno](../app/orquestador/grafo.py#L660) | Atiende un turno ya admitido por los limites de `responder`. |
| [olvidar_sesion](../app/orquestador/grafo.py#L760) | Al reiniciar un hilo, el planificador deja de arrastrar el agente anterior. |
| [revisiones_pendientes](../app/orquestador/grafo.py#L775) | Vista serializable para el panel/API del staff; no expone objetos internos. |
| [resolver_revision](../app/orquestador/grafo.py#L784) | Aprueba o rechaza la ejecución pausada y termina el turno en el cierre único. |
| [_ejecutar_resolucion](../app/orquestador/grafo.py#L806) | Reanuda el agente con la decisión del personal y arma la respuesta de cierre. |
| [diagrama_mermaid](../app/orquestador/grafo.py#L845) | El grafo tal como LangGraph lo compilo, en texto Mermaid. |
| [exportar_diagrama](../app/orquestador/grafo.py#L855) | Exporta el diagrama del grafo (para el informe y la presentacion final). |

## app/orquestador/informacion.py

| Elemento | Descripcion |
|---|---|
| [modulo](../app/orquestador/informacion.py#L1) | El orquestador respondiendo por si mismo: la funcion de *proxy*. |
| [obtener_agente](../app/orquestador/informacion.py#L34) | Construye y reutiliza el agente LangChain del componente de informacion del orquestador. |
| [responder](../app/orquestador/informacion.py#L45) | Responde una consulta general con el agente de lectura del orquestador. |
| [reiniciar](../app/orquestador/informacion.py#L62) | Fuerza reconstruir el agente: lo usan los tests y el banco de modelos. |

## app/orquestador/limites.py

| Elemento | Descripcion |
|---|---|
| [modulo](../app/orquestador/limites.py#L1) | Limites por conversacion: tamano del mensaje, frecuencia y un turno a la vez. |
| [maximo_caracteres](../app/orquestador/limites.py#L33) | Largo maximo de un mensaje (CLEMENTE_MAX_CARACTERES_MENSAJE, 2000). |
| [maximo_por_minuto](../app/orquestador/limites.py#L38) | Mensajes por conversacion y minuto antes de limitar (CLEMENTE_MAX_MENSAJES_MINUTO, 12). |
| [demasiado_largo](../app/orquestador/limites.py#L43) | True si el mensaje supera el largo maximo. |
| [excede_frecuencia](../app/orquestador/limites.py#L48) | Cuenta este mensaje y dice si la conversacion supero el maximo del ultimo minuto. |
| [un_turno_a_la_vez](../app/orquestador/limites.py#L65) | Serializa los turnos de una misma conversacion; cede True si obtuvo el turno, False si vencio la espera. |
| [reiniciar](../app/orquestador/limites.py#L85) | Vacia los contadores y turnos en memoria; lo usan las pruebas. |

## app/reservas/__init__.py

| Elemento | Descripcion |
|---|---|
| [modulo](../app/reservas/__init__.py#L1) | Gestor de Reservas -- responsable: Miguel. |
| [obtener_servicio](../app/reservas/__init__.py#L16) | Singleton del servicio de reservas segun el backend configurado. |
| [reiniciar_servicio](../app/reservas/__init__.py#L32) | Usado por las pruebas para forzar una instancia limpia. |

## app/reservas/seed.py

| Elemento | Descripcion |
|---|---|
| [modulo](../app/reservas/seed.py#L1) | Sube el catalogo de mesas (`datos/mesas.json`) a Postgres. |
| [generar](../app/reservas/seed.py#L26) | Aplica migraciones pendientes y sube el catalogo de mesas. Devuelve cuantas subio. |

## app/reservas/servicio_json.py

| Elemento | Descripcion |
|---|---|
| [modulo](../app/reservas/servicio_json.py#L1) | Implementacion de referencia del Gestor de Reservas, sobre archivos JSON. |
| [ServicioReservasJSON](../app/reservas/servicio_json.py#L31) | Implementa disponibilidad y reservas sobre el mapa de mesas y un archivo JSON. |
| [ServicioReservasJSON.__init__](../app/reservas/servicio_json.py#L37) | Selecciona el archivo de reservas y carga las mesas desde ARCHIVO_MESAS. |
| [ServicioReservasJSON._leer](../app/reservas/servicio_json.py#L46) | Carga las reservas del JSON o devuelve lista vacia si el archivo no existe. |
| [ServicioReservasJSON._escribir](../app/reservas/servicio_json.py#L54) | Sobrescribe el JSON de reservas en UTF-8, creando la carpeta si es necesario. |
| [ServicioReservasJSON.consultar_disponibilidad](../app/reservas/servicio_json.py#L63) | Mesas libres para ese turno. `excluir_reserva_id` libera la mesa de una |
| [ServicioReservasJSON.obtener_reserva](../app/reservas/servicio_json.py#L101) | Busca una reserva por id y devuelve su dataclass, o None si no existe. |
| [ServicioReservasJSON.buscar_reservas_de](../app/reservas/servicio_json.py#L108) | Devuelve las reservas del telefono exacto, incluidas las canceladas. |
| [ServicioReservasJSON.crear_reserva](../app/reservas/servicio_json.py#L116) | Asigna la mesa libre de menor capacidad suficiente y persiste una reserva confirmada. |
| [ServicioReservasJSON.modificar_reserva](../app/reservas/servicio_json.py#L142) | Modifica una reserva no cancelada y vuelve a comprobar disponibilidad. |
| [ServicioReservasJSON.cancelar_reserva](../app/reservas/servicio_json.py#L174) | Persiste estado cancelada para el id recibido y devuelve el registro. |

## app/reservas/servicio_postgres.py

| Elemento | Descripcion |
|---|---|
| [modulo](../app/reservas/servicio_postgres.py#L1) | Implementacion del Gestor de Reservas sobre PostgreSQL (ver ACUERDOS_EQUIPO.md 7.1). |
| [ServicioReservasPostgres](../app/reservas/servicio_postgres.py#L32) | Implementa el contrato de reservas en Postgres con bloqueo transaccional de mesas y consultas parametrizadas. |
| [ServicioReservasPostgres.consultar_disponibilidad](../app/reservas/servicio_postgres.py#L34) | Devuelve mesas libres del turno y capacidad solicitados; un horario no valido devuelve lista vacia. |
| [ServicioReservasPostgres.obtener_reserva](../app/reservas/servicio_postgres.py#L48) | Consulta una reserva por identificador; devuelve None si no existe. La propiedad se valida en la capa de autorizacion. |
| [ServicioReservasPostgres.buscar_reservas_de](../app/reservas/servicio_postgres.py#L59) | Consulta reservas del telefono indicado; la capa de herramientas limita el acceso a la sesion propietaria. |
| [ServicioReservasPostgres.crear_reserva](../app/reservas/servicio_postgres.py#L76) | Bloquea mesas candidatas, asigna la menor disponible e inserta una reserva; sin disponibilidad lanza ValueError. |
| [ServicioReservasPostgres.modificar_reserva](../app/reservas/servicio_postgres.py#L104) | Bloquea la reserva activa y mesas candidatas, verifica disponibilidad y actualiza fecha, turno y capacidad. |
| [ServicioReservasPostgres.cancelar_reserva](../app/reservas/servicio_postgres.py#L145) | Bloquea y marca una reserva cancelada; devuelve None si no existe. |
| [ServicioReservasPostgres._opciones_libres](../app/reservas/servicio_postgres.py#L163) | Filtra mesas por ocupacion, capacidad y zona; lock=True bloquea filas durante las escrituras. |
| [ServicioReservasPostgres._construir](../app/reservas/servicio_postgres.py#L198) | Convierte una fila SQL en el contrato Reserva sin consultar servicios externos. |

## app/seguridad/__init__.py

| Elemento | Descripcion |
|---|---|
| [modulo](../app/seguridad/__init__.py#L1) | Controles transversales de seguridad que rodean a agentes y canales. |

## app/seguridad/errores.py

| Elemento | Descripcion |
|---|---|
| [modulo](../app/seguridad/errores.py#L1) | Errores hacia afuera: solo el tipo, nunca el mensaje. |
| [registrar_error](../app/seguridad/errores.py#L19) | Anota el error en la traza solo con su tipo y deja el detalle completo, redactado, en el log. |

## app/seguridad/guardrails_ai.py

| Elemento | Descripcion |
|---|---|
| [modulo](../app/seguridad/guardrails_ai.py#L1) | Adaptador al servicio aislado de Guardrails AI. |
| [ResultadoEntrada](../app/seguridad/guardrails_ai.py#L17) | Resultado del cliente de validacion: permiso, texto, motivo y disponibilidad. |
| [falla_cerrada](../app/seguridad/guardrails_ai.py#L28) | True si un fallo del validador de ENTRADA debe bloquear el mensaje (por defecto si). |
| [validar_entrada](../app/seguridad/guardrails_ai.py#L36) | Solicita al servicio Guardrails AI la validacion de entrada y registra su resultado. |
| [validar_salida](../app/seguridad/guardrails_ai.py#L77) | Solicita validacion de toxicidad de salida y devuelve la decision al canal. |

## app/seguridad/pii.py

| Elemento | Descripcion |
|---|---|
| [modulo](../app/seguridad/pii.py#L1) | Política local de PII: protege secretos sin romper las reservas. |
| [pii_prohibida](../app/seguridad/pii.py#L19) | Devuelve el primer tipo de tarjeta o secreto detectado por regex, o None. |
| [redactar_pii](../app/seguridad/pii.py#L30) | Sustituye patrones de PII por marcadores en texto y estructuras anidadas. |
| [middleware_pii](../app/seguridad/pii.py#L53) | PIIMiddleware protege correo y tarjetas en input, output y tools. |

## app/seguridad/trazado.py

| Elemento | Descripcion |
|---|---|
| [modulo](../app/seguridad/trazado.py#L1) | Redaccion de lo que viaja a LangSmith. |
| [ocultar](../app/seguridad/trazado.py#L24) | Funcion que LangSmith aplica a inputs y outputs de cada ejecucion antes de enviarlos. |
| [trazado_activo](../app/seguridad/trazado.py#L32) | True si LangSmith esta encendido y con clave (Observabilidad apaga el trazado si no hay clave). |
| [contexto_de_trazado](../app/seguridad/trazado.py#L38) | Context manager que redacta lo que se trace dentro de el; no hace nada con LangSmith apagado. |

## docs/verificar_documentacion.py

| Elemento | Descripcion |
|---|---|
| [modulo](verificar_documentacion.py#L1) | Audita docstrings del proyecto sin importar la app ni llamar servicios externos. |
| [archivos_python](verificar_documentacion.py#L21) | Enumera codigo propio de entrada, app, servicio, pruebas y utilidades documentales. |
| [definiciones](verificar_documentacion.py#L36) | Devuelve nombres cualificados y nodos de clases y funciones en orden del codigo. |
| [auditar](verificar_documentacion.py#L52) | Lee y compila cada fuente y devuelve su inventario y los problemas detectados. |
| [escribir_indice](verificar_documentacion.py#L81) | Genera Markdown con cobertura y enlaces relativos a cada definicion del codigo. |
| [main](verificar_documentacion.py#L110) | Ejecuta la auditoria de CLI y retorna 1 si falta documentacion o falla la sintaxis. |

## guardrails_service/app.py

| Elemento | Descripcion |
|---|---|
| [modulo](../guardrails_service/app.py#L1) | Servicio aislado de seguridad con Guardrails AI, basado en la sesión 24. |
| [obtener_guards](../guardrails_service/app.py#L35) | Inicializa y reutiliza los guards de jailbreak (0.81) y toxicidad (0.8). |
| [autorizado](../guardrails_service/app.py#L51) | Valida el Bearer token de CLEMENTE_GUARDRAILS_TOKEN con comparacion constante. |
| [health](../guardrails_service/app.py#L62) | Devuelve el estado del proceso HTTP sin inicializar ni ejecutar los validadores. |
| [validate_input](../guardrails_service/app.py#L68) | Valida POST /validate/input y devuelve valid, validated_output, reason y validator. |
| [validate_output](../guardrails_service/app.py#L100) | Valida POST /validate/output con el patron local y el guard de toxicidad. |

## mcp_server.py

| Elemento | Descripcion |
|---|---|
| [modulo](../mcp_server.py#L1) | Punto de entrada del servidor MCP de tickets, para las herramientas de linea de comandos. |

## run.py

| Elemento | Descripcion |
|---|---|
| [modulo](../run.py#L1) | Punto de entrada de Clemente. |

## studio.py

| Elemento | Descripcion |
|---|---|
| [modulo](../studio.py#L1) | Punto de entrada de Clemente para LangGraph Studio. |

## tests/conftest.py

| Elemento | Descripcion |
|---|---|
| [modulo](../tests/conftest.py#L1) | Configuracion comun de las pruebas: datos aislados, sin tocar los del equipo. |
| [aislar_estado](../tests/conftest.py#L19) | Aisla archivos y registros globales por prueba y elimina credenciales del entorno. |
| [servicio_reservas](../tests/conftest.py#L54) | Corre el contrato de ServicioReservas contra las dos implementaciones. |
| [servicio_incidencias](../tests/conftest.py#L89) | Proporciona un gestor JSON de incidencias con archivo temporal exclusivo de la prueba. |

## tests/eval/banco_modelos.py

| Elemento | Descripcion |
|---|---|
| [modulo](../tests/eval/banco_modelos.py#L1) | Banco de modelos: cuanto cuesta y cuanto tarda Clemente con cada LLM. |
| [_tiene_vineta](../tests/eval/banco_modelos.py#L61) | Detecta si texto comienza con una vineta Markdown o la contiene tras un salto de linea. |
| [backend_de](../tests/eval/banco_modelos.py#L66) | De que proveedor es un ID de modelo. Sin adivinar: prefijos conocidos. |
| [activar](../tests/eval/banco_modelos.py#L78) | Deja el proceso configurado para correr con este modelo. |
| [credencial_de](../tests/eval/banco_modelos.py#L99) | Comprueba presencia de la variable de credencial del backend, sin validar contra la API. |
| [correr_modelo](../tests/eval/banco_modelos.py#L108) | Ejecuta todo el dataset con un modelo y devuelve sus numeros. |
| [tabla](../tests/eval/banco_modelos.py#L200) | Renderiza resultados como tabla Markdown de calidad minima, tokens, costo y latencia. |
| [informe](../tests/eval/banco_modelos.py#L216) | Genera el informe Markdown con dataset, tabla comparativa, tarifas y limites de interpretacion. |
| [main](../tests/eval/banco_modelos.py#L281) | Procesa modelos y guiones de la CLI, muestra costos y ejecuta la comparacion autorizada. |

## tests/eval/deepeval_evaluar.py

| Elemento | Descripcion |
|---|---|
| [modulo](../tests/eval/deepeval_evaluar.py#L1) | Evaluacion de Clemente con DeepEval -- Sesion 22. |
| [_contexto_recuperado](../tests/eval/deepeval_evaluar.py#L49) | Fragmentos que el RAG devuelve para esa pregunta. |
| [_tools_del_turno](../tests/eval/deepeval_evaluar.py#L63) | Herramientas que el agente llamo en este turno, sacadas de nuestras trazas. |
| [_caso_de_prueba](../tests/eval/deepeval_evaluar.py#L118) | Construye LLMTestCase con entrada, respuesta, referencia y herramientas observadas. |
| [evaluar](../tests/eval/deepeval_evaluar.py#L137) | Ejecuta guiones contra el orquestador y mide las metricas asignadas a cada ruta. |
| [escribir_informe](../tests/eval/deepeval_evaluar.py#L239) | Informe legible para el anexo. El JSON queda para reprocesar. |
| [_fijar_modelo](../tests/eval/deepeval_evaluar.py#L296) | Deja el proceso corriendo con este modelo, cambiando de casa si hace falta. |
| [main](../tests/eval/deepeval_evaluar.py#L311) | Selecciona modelo, juez y guiones de la CLI y guarda la evaluacion DeepEval. |

## tests/eval/deepeval_rag.py

| Elemento | Descripcion |
|---|---|
| [modulo](../tests/eval/deepeval_rag.py#L1) | Evaluacion del recuperador del RAG con ContextualPrecisionMetric -- Sesion 22. |
| [casos_de_catalogo](../tests/eval/deepeval_rag.py#L43) | Los turnos de Conocimiento que tienen respuesta de referencia escrita. |
| [evaluar](../tests/eval/deepeval_rag.py#L54) | Recupera k fragmentos por pregunta y mide precision contextual con el juez. |
| [main](../tests/eval/deepeval_rag.py#L114) | Procesa k y juez, confirma el inicio salvo --si y persiste el informe de precision RAG. |

## tests/eval/evaluar.py

| Elemento | Descripcion |
|---|---|
| [modulo](../tests/eval/evaluar.py#L1) | Evaluacion de Clemente contra el modelo real -- seccion 7.4 de la guia de Jean. |
| [_normalizar](../tests/eval/evaluar.py#L50) | Minusculas y sin tildes: comparar 'politica' con 'política' no debe fallar. |
| [_verificar_texto](../tests/eval/evaluar.py#L56) | Devuelve la lista de incumplimientos de un turno (vacia si esta todo bien). |
| [evaluar](../tests/eval/evaluar.py#L79) | Ejecuta guiones con historial y compara ruta, texto y escalamiento con lo esperado. |
| [_fijar_modelo](../tests/eval/evaluar.py#L154) | Deja el proceso corriendo con este modelo, cambiando de casa si hace falta. |
| [main](../tests/eval/evaluar.py#L169) | Selecciona modelo y guion, muestra costo aproximado y guarda la evaluacion funcional. |

## tests/eval/juez.py

| Elemento | Descripcion |
|---|---|
| [modulo](../tests/eval/juez.py#L1) | Juez de las evaluaciones -- el modelo que califica, no el que atiende clientes. |
| [_modelo_del_juez](../tests/eval/juez.py#L57) | Resuelve el modelo del juez desde su variable de entorno o el valor predeterminado. |
| [advertir_si_se_juzga_a_si_mismo](../tests/eval/juez.py#L62) | Devuelve la advertencia si juez y evaluado coinciden, o cadena vacia. |
| [construir_juez](../tests/eval/juez.py#L83) | Devuelve el juez para DeepEval y DeepTeam. |
| [construir_juez.JuezClemente](../tests/eval/juez.py#L98) | Adaptador de nuestro modelo de `app/llm.py` a la interfaz de DeepEval. |
| [construir_juez.JuezClemente.__init__](../tests/eval/juez.py#L101) | Resuelve el nombre del juez y construye su modelo con temperatura cero. |
| [construir_juez.JuezClemente.load_model](../tests/eval/juez.py#L113) | Devuelve el modelo LangChain que implementa la interfaz de juez DeepEval. |
| [construir_juez.JuezClemente.generate](../tests/eval/juez.py#L117) | DeepEval pasa `schema` (una clase Pydantic) cuando necesita la |
| [construir_juez.JuezClemente.a_generate](../tests/eval/juez.py#L132) | Genera el juicio asincrono como texto o salida del schema recibido. |
| [construir_juez.JuezClemente._formato](../tests/eval/juez.py#L145) | Agrega el contrato JSON del schema si CLEMENTE_JUEZ_EXIGIR_ESQUEMA es 1. |
| [construir_juez.JuezClemente._registrar_error](../tests/eval/juez.py#L158) | Anota tipo de error y detalles de validacion en el diario configurado, si existe. |
| [construir_juez.JuezClemente.get_model_name](../tests/eval/juez.py#L169) | Devuelve el identificador del juez para los informes de evaluacion. |
| [nombre_del_juez](../tests/eval/juez.py#L176) | Para dejarlo escrito en el informe: quien califico. |

## tests/eval/langsmith_experimento.py

| Elemento | Descripcion |
|---|---|
| [modulo](../tests/eval/langsmith_experimento.py#L1) | El dataset de Clemente como experimento de LangSmith -- Sesion 22. |
| [subir_dataset](../tests/eval/langsmith_experimento.py#L55) | Sincroniza `casos.json` con el dataset de LangSmith. |
| [clemente](../tests/eval/langsmith_experimento.py#L119) | Replica un guion completo contra el sistema real y devuelve lo que hizo. |
| [precision_de_ruteo](../tests/eval/langsmith_experimento.py#L154) | Determinista. La metrica principal del orquestador. |
| [plan_completo](../tests/eval/langsmith_experimento.py#L176) | Determinista. Solo mira los turnos que traen DOS pedidos en un mismo mensaje. |
| [sin_texto_prohibido](../tests/eval/langsmith_experimento.py#L199) | Determinista. Verifica los `no_debe_contener` del guion -- las palabras que |
| [sin_texto_prohibido.normalizar](../tests/eval/langsmith_experimento.py#L206) | Convierte texto a minusculas y elimina marcas diacriticas para la comparacion. |
| [escala_cuando_debe](../tests/eval/langsmith_experimento.py#L224) | Determinista. Un grupo de mas de 10 personas no se cierra por chat. |
| [respeta_sus_limites](../tests/eval/langsmith_experimento.py#L238) | Juez con LLM. Reutiliza las mismas metricas GEval de `metricas.py`, para que |
| [_fijar_modelo](../tests/eval/langsmith_experimento.py#L273) | Deja el proceso corriendo con este modelo, cambiando de casa si hace falta. |
| [main](../tests/eval/langsmith_experimento.py#L288) | Procesa la CLI, publica el dataset y opcionalmente ejecuta el experimento en LangSmith. |

## tests/eval/metricas.py

| Elemento | Descripcion |
|---|---|
| [modulo](../tests/eval/metricas.py#L1) | Metricas de calidad de Clemente -- Sesion 22 (Evaluacion Comparativa). |
| [_rubrica](../tests/eval/metricas.py#L38) | Escala explicita para GEval, de 0 a 10. |
| [metrica_no_promete_de_mas](../tests/eval/metricas.py#L60) | El limite del Agente de Reservas: nunca comprometer capacidad sin haberla |
| [metrica_no_ofrece_compensacion](../tests/eval/metricas.py#L108) | El limite del Agente de Incidencias: registra el reclamo, no lo resuelve. |
| [metrica_fiel_al_catalogo](../tests/eval/metricas.py#L147) | El limite del Agente de Conocimiento: responder solo desde el catalogo |
| [metrica_tono_clemente](../tests/eval/metricas.py#L189) | Metrica de matiz, no de limite: aqui `criteria=` en texto libre funciona |
| [metrica_precision_contextual](../tests/eval/metricas.py#L223) | Calidad del recuperador del RAG (`ContextualPrecisionMetric`). |
| [construir_metricas](../tests/eval/metricas.py#L251) | Todas las metricas de juicio, indexadas por nombre. Un solo juez para todas. |

## tests/evals/dataset_casos.py

| Elemento | Descripcion |
|---|---|
| [modulo](../tests/evals/dataset_casos.py#L1) | Dataset de casos de prueba para evaluar al agente Clemente. |

## tests/evals/deepeval/evaluador_deepeval.py

| Elemento | Descripcion |
|---|---|
| [modulo](../tests/evals/deepeval/evaluador_deepeval.py#L1) | Evaluador DeepEval para el agente Clemente |
| [construir_metricas](../tests/evals/deepeval/evaluador_deepeval.py#L80) | Métricas predefinidas de DeepEval, transversales a las 3 categorías (igual que |
| [invocar_agente_real](../tests/evals/deepeval/evaluador_deepeval.py#L101) | Corre un mensaje contra el orquestador real y devuelve (respuesta, tools). |
| [generar_reporte](../tests/evals/deepeval/evaluador_deepeval.py#L129) | Escribe resultados de DeepEval en un reporte para revisar la evaluacion ejecutada. |
| [main](../tests/evals/deepeval/evaluador_deepeval.py#L200) | Ejecuta la evaluacion indicada por este script; puede consumir APIs y publicar resultados externos. |

## tests/evals/langsmith/evaluador_langsmith.py

| Elemento | Descripcion |
|---|---|
| [modulo](../tests/evals/langsmith/evaluador_langsmith.py#L1) | Evaluador LangSmith para el agente Clemente |
| [crear_o_recuperar_dataset](../tests/evals/langsmith/evaluador_langsmith.py#L63) | Reemplaza el dataset existente de LangSmith por los casos actuales y devuelve su identificador. |
| [ejecutar_agente](../tests/evals/langsmith/evaluador_langsmith.py#L89) | Corre el mensaje contra el orquestador real. Cada caso usa una sesion |
| [JuicioLLM](../tests/evals/langsmith/evaluador_langsmith.py#L111) | Define la puntuacion y justificacion estructuradas esperadas del modelo juez. |
| [crear_evaluador_llm](../tests/evals/langsmith/evaluador_langsmith.py#L167) | Construye un evaluador de un criterio con categorias aplicables y juez estructurado. |
| [crear_evaluador_llm.evaluador](../tests/evals/langsmith/evaluador_langsmith.py#L169) | Omite categorias no aplicables y solicita al juez una puntuacion y justificacion para el criterio. |
| [enrutamiento_correcto](../tests/evals/langsmith/evaluador_langsmith.py#L209) | Puntua si las herramientas registradas coinciden con alguna esperada para la categoria. |
| [construir_evaluadores](../tests/evals/langsmith/evaluador_langsmith.py#L223) | Reune jueces de criterios de negocio y el evaluador determinista de herramientas. |
| [main](../tests/evals/langsmith/evaluador_langsmith.py#L237) | Ejecuta la evaluacion indicada por este script; puede consumir APIs y publicar resultados externos. |

## tests/evals/modelo_juez.py

| Elemento | Descripcion |
|---|---|
| [modulo](../tests/evals/modelo_juez.py#L1) | Juez gpt-5.6-luna compartido por los dos evaluadores copiados de la tarea grupal |
| [chat_gpt_luna](../tests/evals/modelo_juez.py#L31) | LLM de LangChain apuntando al deployment de Azure gpt-5.6-luna, el mismo |
| [JuezGptLuna](../tests/evals/modelo_juez.py#L54) | Envoltorio de gpt-5.6-luna (Azure) para usarlo como juez en DeepEval. |
| [JuezGptLuna.load_model](../tests/evals/modelo_juez.py#L57) | Devuelve el modelo de chat configurado para el juez de DeepEval. |
| [JuezGptLuna.generate](../tests/evals/modelo_juez.py#L61) | Invoca el juez sincronicamente y devuelve su texto. |
| [JuezGptLuna.a_generate](../tests/evals/modelo_juez.py#L65) | Invoca el juez asincronicamente y devuelve su texto. |
| [JuezGptLuna.get_model_name](../tests/evals/modelo_juez.py#L70) | Devuelve el nombre del modelo juez para identificar los reportes. |

## tests/seguridad/campana.py

| Elemento | Descripcion |
|---|---|
| [modulo](../tests/seguridad/campana.py#L1) | Campana autorizada: etapas independientes, evidencias y presupuesto comunes. |
| [main](../tests/seguridad/campana.py#L13) | Configura modelos, entorno aislado y presupuesto y ejecuta la etapa solicitada. |
| [funcional](../tests/seguridad/campana.py#L101) | Evalua guiones con datos sinteticos y guarda cada informe al terminar. |
| [trello](../tests/seguridad/campana.py#L133) | Delega la etapa de integracion a validacion_trello.ejecutar, que crea evidencia externa. |

## tests/seguridad/ciclo_reserva.py

| Elemento | Descripcion |
|---|---|
| [modulo](../tests/seguridad/ciclo_reserva.py#L1) | Verificacion del estado real tras propuesta, confirmacion y repeticion. |
| [ejecutar](../tests/seguridad/ciclo_reserva.py#L8) | Ejercita el ciclo de reserva con datos sinteticos y persiste evidencia de cada turno. |
| [ejecutar.turno](../tests/seguridad/ciclo_reserva.py#L24) | Ejecuta un turno para sid, guarda respuesta y reservas propias y actualiza el historial. |

## tests/seguridad/entorno.py

| Elemento | Descripcion |
|---|---|
| [modulo](../tests/seguridad/entorno.py#L1) | Estado y evidencia locales para una corrida de red teaming en proceso propio. |
| [guardar_json](../tests/seguridad/entorno.py#L10) | Crea la carpeta y persiste datos como JSON UTF-8 mediante temporal y reemplazo. |
| [registrar_turno](../tests/seguridad/entorno.py#L18) | Agrega una fila JSONL al diario y vacia el buffer; la carpeta debe existir. |
| [entorno_aislado](../tests/seguridad/entorno.py#L26) | No ejecutar dentro del servidor: los parches son globales al proceso. |

## tests/seguridad/presupuesto.py

| Elemento | Descripcion |
|---|---|
| [modulo](../tests/seguridad/presupuesto.py#L1) | Control conservador de llamadas HTTP de evaluacion, compartido entre etapas. |
| [PresupuestoAgotado](../tests/seguridad/presupuesto.py#L21) | Error que detiene la evaluacion antes de una llamada que excederia el limite reservado. |
| [Presupuesto](../tests/seguridad/presupuesto.py#L26) | Control persistente de gasto estimado por proveedor para la campana de evaluacion. |
| [Presupuesto.__init__](../tests/seguridad/presupuesto.py#L31) | Carga el libro de cargos existente o inicia uno con limite por proveedor y bloqueo local. |
| [Presupuesto.preparar](../tests/seguridad/presupuesto.py#L40) | Valida la peticion, limita salida y reserva costo antes de enviarla al proveedor. |
| [Presupuesto.cerrar](../tests/seguridad/presupuesto.py#L78) | Actualiza el cargo con HTTP y uso reportado y persiste el libro. |
| [Presupuesto.activo](../tests/seguridad/presupuesto.py#L104) | Intercepta temporalmente send de httpx y httpx2, sincrono y asincrono. |
| [Presupuesto.activo.envolver_sync](../tests/seguridad/presupuesto.py#L110) | Construye el wrapper sincrono que aplica la reserva y contabilizacion a send. |
| [Presupuesto.activo.envolver_sync.enviar](../tests/seguridad/presupuesto.py#L112) | Reserva costo, envia con el transporte original y contabiliza el uso si hay cargo. |
| [Presupuesto.activo.envolver_async](../tests/seguridad/presupuesto.py#L123) | Construye el wrapper asincrono que aplica la reserva y contabilizacion a send. |
| [Presupuesto.activo.envolver_async.enviar](../tests/seguridad/presupuesto.py#L125) | Reserva costo, envia con el transporte original y contabiliza el uso si hay cargo. |
| [Presupuesto.activo.drenar](../tests/seguridad/presupuesto.py#L152) | Espera las tareas pendientes sin propagar sus excepciones y cierra el executor del loop. |

## tests/seguridad/red_team_reservas.py

| Elemento | Descripcion |
|---|---|
| [modulo](../tests/seguridad/red_team_reservas.py#L1) | Red teaming de Clemente, Sesion 23, con datos sinteticos por corrida. |
| [construir_callback](../tests/seguridad/red_team_reservas.py#L83) | Envuelve a Clemente en la firma que DeepTeam espera. |
| [construir_callback._responder_sincrono](../tests/seguridad/red_team_reservas.py#L108) | Llama al objetivo elegido con una sesion nueva y devuelve su texto. |
| [construir_callback.callback](../tests/seguridad/red_team_reservas.py#L126) | Adapta un ataque de un turno al objetivo y devuelve RTTurn del asistente. |
| [construir_callback.callback.anotar](../tests/seguridad/red_team_reservas.py#L136) | Anexa evidencia del ataque con identificador y sesion cuando se configura un diario. |
| [construir_escenarios](../tests/seguridad/red_team_reservas.py#L156) | Devuelve (vulnerabilidades, ataques). En modo humo, lo minimo para validar el montaje. |
| [ejecutar](../tests/seguridad/red_team_reservas.py#L192) | DeepTeam 1.0.9: matriz completa, sin subida a Confident ni resumen Unicode. |
| [ejecutar.simular_y_guardar](../tests/seguridad/red_team_reservas.py#L213) | Ejecuta el simulador y persiste ataques antes de evaluarlos para conservar evidencia parcial. |
| [escribir_informe](../tests/seguridad/red_team_reservas.py#L245) | Informe de riesgo con el mapeo a OWASP. Es lo que va al Modulo 8. |
| [main](../tests/seguridad/red_team_reservas.py#L302) | Procesa la CLI de red team, configura aislamiento y guarda manifiesto y resultados. |

## tests/seguridad/rejuzgar.py

| Elemento | Descripcion |
|---|---|
| [modulo](../tests/seguridad/rejuzgar.py#L1) | Repite solo juicios invalidos de una evaluacion, sobre respuestas congeladas. |
| [ejecutar](../tests/seguridad/rejuzgar.py#L9) | Reevalua solo juicios con error de la corrida previa y guarda resultados incrementalmente. |

## tests/seguridad/validacion_trello.py

| Elemento | Descripcion |
|---|---|
| [modulo](../tests/seguridad/validacion_trello.py#L1) | Una incidencia ficticia real: agente -> MCP -> Trello, con lectura de vuelta. |
| [ejecutar](../tests/seguridad/validacion_trello.py#L11) | Comprueba tablero y catalogo MCP y registra un reclamo sintetico mediante el orquestador. |

## tests/test_api.py

| Elemento | Descripcion |
|---|---|
| [modulo](../tests/test_api.py#L1) | Pruebas de la capa HTTP, sin llamar al modelo. |
| [cliente](../tests/test_api.py#L17) | Crea un cliente Flask con orquestador simulado para probar contratos HTTP sin API LLM. |
| [cliente.orquestador_falso](../tests/test_api.py#L19) | Devuelve una respuesta simulada para comprobar rutas, sesion e historial del chat. |
| [test_salud_reporta_proveedor_y_modelo](../tests/test_api.py#L36) | Verifica que salud reporta proveedor y modelo. |
| [test_salud_avisa_cuando_falta_la_clave](../tests/test_api.py#L45) | Con el razonamiento sobre API, arrancar sin clave tiene que ser visible. |
| [test_chat_devuelve_agente_y_sesion](../tests/test_api.py#L55) | Verifica que chat devuelve agente y sesion. |
| [test_webchat_incluye_estados_de_seguridad_y_panel_hitl](../tests/test_api.py#L66) | Verifica que webchat incluye estados de seguridad y panel hitl. |
| [test_estado_ui_distingue_autorizacion_y_revision_humana](../tests/test_api.py#L75) | Verifica que estado ui distingue autorizacion y revision humana. |
| [test_guardrails_ai_bloquea_sin_invocar_orquestador](../tests/test_api.py#L90) | Verifica que guardrails ai bloquea sin invocar orquestador. |
| [test_guardrails_caido_no_llega_al_agente](../tests/test_api.py#L109) | Con Guardrails AI configurado pero caido, el mensaje se rechaza antes del orquestador. |
| [test_guardrails_caido_no_llega_al_agente.cae](../tests/test_api.py#L118) | Simula que el servicio de Guardrails AI no responde. |
| [test_chat_sin_mensaje_es_error](../tests/test_api.py#L131) | Verifica que chat sin mensaje es error. |
| [test_webhook_normaliza_el_canal](../tests/test_api.py#L136) | Un formulario firmado de Twilio llega al trabajador con identidad normalizada. |
| [test_el_historial_se_acumula_en_la_sesion](../tests/test_api.py#L158) | Verifica que el historial se acumula en la sesion. |
| [test_otro_navegador_no_puede_suplantar_leer_o_resetear](../tests/test_api.py#L167) | Verifica que otro navegador no puede suplantar leer o resetear. |
| [test_webhook_sin_autenticacion_no_acepta_identidad](../tests/test_api.py#L177) | Una firma ausente o incorrecta no inicia trabajo ni acepta identidad externa. |
| [test_revision_humana_exige_token_propio](../tests/test_api.py#L194) | Verifica que revision humana exige token propio. |
| [test_staff_solo_puede_aprobar_o_rechazar](../tests/test_api.py#L210) | Verifica que staff solo puede aprobar o rechazar. |
| [test_las_conversaciones_solo_devuelven_el_hilo_propio](../tests/test_api.py#L224) | Verifica que las conversaciones solo devuelven el hilo propio. |
| [test_langsmith_no_se_activa_sin_clave](../tests/test_api.py#L234) | Con el trazado pedido pero sin clave, se apaga y avisa: no falla en cada llamada. |
| [test_la_conversacion_queda_registrada_en_disco](../tests/test_api.py#L245) | El texto de cada turno sobrevive al reinicio del servidor y a LangSmith caido. |
| [test_twilio_signature_uses_configured_public_url](../tests/test_api.py#L264) | Azure puede recibir HTTP interno mientras la firma corresponde a la URL HTTPS publica. |

## tests/test_endurecimiento.py

| Elemento | Descripcion |
|---|---|
| [modulo](../tests/test_endurecimiento.py#L1) | Endurecimiento de seguridad de la capa de agentes: errores, trazas y limites; sin LLM ni base de datos. |
| [runtime](../tests/test_endurecimiento.py#L17) | Runtime simulado con sesion identificada y contexto vacio. |
| [test_el_error_del_catalogo_no_llega_al_modelo](../tests/test_endurecimiento.py#L24) | Verifica que la tool devuelve un aviso generico y el detalle real queda solo en el log. |
| [test_el_error_del_catalogo_no_llega_al_modelo.cae](../tests/test_endurecimiento.py#L28) | Simula un fallo de Azure AI Search cuyo mensaje trae una URL interna. |
| [test_una_tool_que_falla_deja_solo_el_tipo_en_la_traza](../tests/test_endurecimiento.py#L45) | Verifica que con_traza no copia el mensaje de la excepcion a la traza que se lee desde /api/trazas. |
| [test_una_tool_que_falla_deja_solo_el_tipo_en_la_traza.rota](../tests/test_endurecimiento.py#L50) | Tool de prueba que falla con un mensaje que trae un host interno. |
| [test_ocultar_redacta_lo_que_viaja_a_langsmith](../tests/test_endurecimiento.py#L63) | Verifica que el filtro de inputs y outputs tapa telefonos, correos y tarjetas anidados. |
| [test_sin_langsmith_no_se_instala_ningun_cliente](../tests/test_endurecimiento.py#L71) | Verifica que con el trazado apagado no se crea cliente ni se cambia nada. |
| [test_langsmith_recibe_los_datos_redactados](../tests/test_endurecimiento.py#L80) | Verifica de punta a punta que lo enviado a LangSmith, incluso en llamadas anidadas, sale redactado. |
| [test_langsmith_recibe_los_datos_redactados.falso](../tests/test_endurecimiento.py#L87) | Captura lo que el cliente de LangSmith intentaria enviar por HTTP. |
| [test_el_id_de_hilo_no_lleva_el_telefono_y_es_estable](../tests/test_endurecimiento.py#L114) | Verifica que el thread_id del checkpoint (que LangSmith recibe como metadata) no expone el telefono. |

## tests/test_eval_robustez.py

| Elemento | Descripcion |
|---|---|
| [modulo](../tests/test_eval_robustez.py#L1) | Pruebas del tratamiento de errores del juez y agotamiento de presupuesto, con dobles locales. |
| [preparar](../tests/test_eval_robustez.py#L8) | Sustituye el asistente y la metrica para simular un error del juez en la evaluacion. |
| [preparar.Metrica](../tests/test_eval_robustez.py#L15) | Metrica simulada que lanza el error configurado para comprobar su tratamiento. |
| [preparar.Metrica.measure](../tests/test_eval_robustez.py#L17) | Lanza el error configurado en lugar de producir un juicio valido. |
| [test_error_del_juez_no_se_cuenta_como_juicio_valido](../tests/test_eval_robustez.py#L25) | Verifica que error del juez no se cuenta como juicio valido. |
| [test_agotamiento_no_se_oculta_como_error_del_juez](../tests/test_eval_robustez.py#L35) | Verifica que agotamiento no se oculta como error del juez. |

## tests/test_fecha.py

| Elemento | Descripcion |
|---|---|
| [modulo](../tests/test_fecha.py#L1) | Reloj de Lima, tool de fecha y validacion dia/fecha; sin LLM ni base de datos. |
| [reloj_fijo](../tests/test_fecha.py#L22) | Fija el instante del reloj de Lima para que las fechas de las pruebas no dependan del dia real. |
| [servicio](../tests/test_fecha.py#L28) | Servicio de reservas JSON temporal conectado a las tools. |
| [runtime](../tests/test_fecha.py#L35) | Runtime simulado con sesion identificada y contexto vacio. |
| [test_hoy_es_la_fecha_de_lima_y_no_la_del_servidor](../tests/test_fecha.py#L40) | Verifica que a las 21:00 de Lima hoy sigue siendo lunes aunque en UTC ya sea martes. |
| [test_dia_declarado_ignora_tildes_y_mayusculas](../tests/test_fecha.py#L46) | Verifica que se reconoce el dia escrito de cualquier forma y None si no hay ninguno. |
| [test_contradiccion_dia_fecha](../tests/test_fecha.py#L54) | Verifica que 'viernes' con el 10 de octubre (sabado) devuelve la contradiccion y no elige. |
| [test_proximos_dias_empieza_manana](../tests/test_fecha.py#L63) | Verifica que la lista de proximos dias arranca en manana segun Lima. |
| [test_tool_de_fecha_responde_con_la_hora_de_lima](../tests/test_fecha.py#L68) | Verifica que get_current_datetime resuelve hoy y manana con el reloj de Lima. |
| [test_consultar_disponibilidad_rechaza_contradiccion_sin_consultar](../tests/test_fecha.py#L75) | Verifica que un dia y fecha que no coinciden no llegan al servicio y quedan marcados. |
| [test_consultar_disponibilidad_rechaza_contradiccion_sin_consultar.no_debe_llamarse](../tests/test_fecha.py#L77) | Falla la prueba si la tool consulta el servicio pese a la contradiccion. |
| [test_crear_reserva_con_contradiccion_no_deja_propuesta](../tests/test_fecha.py#L87) | Verifica que la contradiccion dia/fecha no prepara el resumen CONFIRMO ni escribe. |
| [test_modificar_reserva_con_contradiccion_no_prepara_cambio](../tests/test_fecha.py#L98) | Verifica que modificar tambien compara el dia con la nueva fecha. |
| [test_hoy_de_lima_no_se_rechaza_como_fecha_pasada](../tests/test_fecha.py#L108) | Verifica que reservar para hoy a las 21:00 de Lima funciona aunque UTC ya sea manana. |
| [test_ayer_de_lima_si_es_fecha_pasada](../tests/test_fecha.py#L117) | Verifica que una fecha anterior a hoy en Lima se rechaza en la tool y no consulta disponibilidad. |
| [test_autorizacion_usa_el_reloj_de_lima_y_no_la_fecha_del_proceso](../tests/test_fecha.py#L126) | Verifica que la validacion del servidor no toma date.today(): con Lima en el 15/09 el 18/09 no es pasado. |
| [test_la_fecha_viaja_en_cada_turno_y_no_en_el_system_prompt](../tests/test_fecha.py#L136) | Verifica que la fecha de Lima se antepone a cada mensaje y el prompt del agente no la congela. |
| [test_la_fecha_viaja_en_cada_turno_y_no_en_el_system_prompt.AgenteFalso](../tests/test_fecha.py#L146) | Agente que guarda lo que recibe y responde con un texto fijo. |
| [test_la_fecha_viaja_en_cada_turno_y_no_en_el_system_prompt.AgenteFalso.invoke](../tests/test_fecha.py#L148) | Guarda los mensajes del turno y devuelve una respuesta simulada. |
| [test_los_tres_agentes_tienen_la_tool_de_fecha](../tests/test_fecha.py#L160) | Verifica que reservas, incidencias e informacion pueden consultar la fecha. |

## tests/test_guardrails.py

| Elemento | Descripcion |
|---|---|
| [modulo](../tests/test_guardrails.py#L1) | Guardrail contra la falla de tool-calling de los modelos locales chicos. |
| [test_detecta_tool_escrita_como_texto](../tests/test_guardrails.py#L13) | Verifica que detecta tool escrita como texto. |
| [test_detecta_tool_dentro_de_un_bloque_de_codigo](../tests/test_guardrails.py#L20) | Verifica que detecta tool dentro de un bloque de codigo. |
| [test_una_respuesta_normal_no_es_falso_positivo](../tests/test_guardrails.py#L25) | Verifica que una respuesta normal no es falso positivo. |
| [test_un_json_que_no_es_una_tool_no_es_falso_positivo](../tests/test_guardrails.py#L32) | Verifica que un json que no es una tool no es falso positivo. |
| [_RuntimeFalso](../tests/test_guardrails.py#L37) | Imita lo unico que las tools usan del ToolRuntime que inyecta create_agent. |
| [_RuntimeFalso.__init__](../tests/test_guardrails.py#L40) | Expone el contexto recibido mediante el atributo context que leen las tools. |
| [test_la_sesion_llega_a_la_tool_por_el_contexto](../tests/test_guardrails.py#L45) | El sesion_id no se le pide al modelo: viaja en el contexto de ejecucion. |
| [test_escalar_levanta_la_mano_pero_no_abre_el_ticket](../tests/test_guardrails.py#L69) | Acuerdo 3 de la asesoria del 2026-09-07: ningun agente escala por su cuenta. |
| [test_excepcion_aprobada_levanta_la_mano_para_el_orquestador](../tests/test_guardrails.py#L96) | La tool protegida solo llega a ejecutarse después del approve del middleware. |
| [test_middleware_interrumpe_y_solo_approve_ejecuta_la_tool](../tests/test_guardrails.py#L114) | Prueba el ciclo real de LangChain, incluido Command(resume=...). |
| [test_middleware_interrumpe_y_solo_approve_ejecuta_la_tool.ModeloFalso](../tests/test_guardrails.py#L127) | Modelo LangChain simulado que produce la llamada y respuesta previstas sin usar API. |
| [test_middleware_interrumpe_y_solo_approve_ejecuta_la_tool.ModeloFalso._llm_type](../tests/test_guardrails.py#L132) | Identificador del modelo simulado requerido por BaseChatModel. |
| [test_middleware_interrumpe_y_solo_approve_ejecuta_la_tool.ModeloFalso.bind_tools](../tests/test_guardrails.py#L136) | Devuelve el modelo simulado sin enlazar herramientas remotas. |
| [test_middleware_interrumpe_y_solo_approve_ejecuta_la_tool.ModeloFalso._generate](../tests/test_guardrails.py#L140) | Produce la secuencia de mensajes simulados para verificar middleware y herramientas. |
| [test_el_cierre_del_orquestador_es_quien_abre_el_ticket](../tests/test_guardrails.py#L179) | La otra mitad del Acuerdo 3: el nodo de cierre convierte la senal en ticket. |
| [test_el_telefono_sale_del_identificador_de_whatsapp](../tests/test_guardrails.py#L210) | Con WhatsApp el telefono ya lo sabe el sistema: no hay que pedirselo al cliente. |
| [test_un_telefono_en_el_id_no_autoriza_la_ficha](../tests/test_guardrails.py#L218) | Una identidad declarada no permite recuperar datos personales antiguos. |
| [test_un_turno_sin_texto_se_contesta_en_vez_de_caerse](../tests/test_guardrails.py#L232) | Regresion del 2026-09-07: al hacer opcionales los campos del estado para |

## tests/test_guardrails_ai.py

| Elemento | Descripcion |
|---|---|
| [modulo](../tests/test_guardrails_ai.py#L1) | Pruebas del cliente Guardrails AI y sus metricas con HTTP simulado, sin iniciar validadores. |
| [config](../tests/test_guardrails_ai.py#L8) | Construye configuracion local del cliente Guardrails AI para peticiones HTTP simuladas. |
| [RespuestaHTTP](../tests/test_guardrails_ai.py#L15) | Doble de respuesta requests con contenido JSON controlado por la prueba. |
| [RespuestaHTTP.__init__](../tests/test_guardrails_ai.py#L17) | Conserva los datos que devolvera la respuesta HTTP simulada. |
| [RespuestaHTTP.raise_for_status](../tests/test_guardrails_ai.py#L21) | Simula una respuesta HTTP exitosa sin realizar validacion de red. |
| [RespuestaHTTP.json](../tests/test_guardrails_ai.py#L25) | Devuelve los datos JSON configurados en el doble HTTP. |
| [test_guardrails_ai_bloquea_antes_del_orquestador](../tests/test_guardrails_ai.py#L30) | Verifica que guardrails ai bloquea antes del orquestador. |
| [test_usa_validated_output_y_no_el_original](../tests/test_guardrails_ai.py#L45) | Verifica que usa validated output y no el original. |
| [_cae](../tests/test_guardrails_ai.py#L57) | Hace que la llamada HTTP al servicio de Guardrails AI falle con el error recibido. |
| [_cae.falla](../tests/test_guardrails_ai.py#L59) | Lanza el error simulado en lugar de consultar al servicio. |
| [test_caida_del_servicio_bloquea_la_entrada_por_defecto](../tests/test_guardrails_ai.py#L65) | Con el servicio configurado, una caida, un timeout o un HTTP 500 bloquean el mensaje. |
| [test_respuesta_sin_veredicto_no_se_toma_como_aprobada](../tests/test_guardrails_ai.py#L77) | Verifica que un 200 sin el campo `valid` no deja pasar el mensaje. |
| [test_el_equipo_puede_volver_a_fail_open_con_la_variable](../tests/test_guardrails_ai.py#L83) | Verifica que CLEMENTE_GUARDRAILS_FALLA_CERRADA=0 restaura la politica anterior de continuar. |
| [test_la_salida_sigue_fail_open_porque_la_operacion_ya_se_ejecuto](../tests/test_guardrails_ai.py#L93) | Verifica que una caida en la validacion de salida no tapa una respuesta ya generada. |
| [test_la_traza_del_fallo_no_guarda_el_texto_del_error](../tests/test_guardrails_ai.py#L101) | Verifica que la traza guarda el tipo de la excepcion y no su mensaje (puede traer URLs). |
| [test_url_vacia_deja_el_servicio_externo_desactivado_sin_llamada](../tests/test_guardrails_ai.py#L113) | Verifica que url vacia deja el servicio externo desactivado sin llamada. |
| [test_metricas_cuentan_bloqueos_y_errores](../tests/test_guardrails_ai.py#L122) | Verifica que metricas cuentan bloqueos y errores. |
| [test_salida_toxica_se_bloquea](../tests/test_guardrails_ai.py#L142) | Verifica que salida toxica se bloquea. |

## tests/test_incidencias.py

| Elemento | Descripcion |
|---|---|
| [modulo](../tests/test_incidencias.py#L1) | Pruebas del registro de incidencias. |
| [test_incidencia_nace_abierta_con_plazo](../tests/test_incidencias.py#L9) | Verifica que incidencia nace abierta con plazo. |
| [test_tipo_desconocido_cae_en_otro](../tests/test_incidencias.py#L19) | Verifica que tipo desconocido cae en otro. |
| [test_listar_filtra_por_estado](../tests/test_incidencias.py#L26) | Verifica que listar filtra por estado. |

## tests/test_llm.py

| Elemento | Descripcion |
|---|---|
| [modulo](../tests/test_llm.py#L1) | Pruebas de la resolucion de modelo y del registro del turno. |
| [credenciales_falsas](../tests/test_llm.py#L31) | Configura credenciales ficticias para construir modelos sin usar cuentas reales. |
| [id_real](../tests/test_llm.py#L37) | El modelo con el que quedo configurado el cliente, no el que dice el nombre. |
| [test_terra_es_el_modelo_predeterminado](../tests/test_llm.py#L42) | README, Config y el constructor deben coincidir incluso sin `.env`. |
| [test_el_proveedor_sale_del_id_del_modelo](../tests/test_llm.py#L66) | Verifica que el proveedor sale del id del modelo. |
| [test_un_modelo_inventado_falla_en_vez_de_adivinar](../tests/test_llm.py#L71) | Adivinar la casa equivocada seria mandar la peticion a la API equivocada. |
| [test_pedir_un_modelo_concreto_ignora_el_env](../tests/test_llm.py#L81) | LA prueba de la regresion. Con el `.env` apuntando a OpenAI, pedir un modelo |
| [test_el_modelo_del_enrutador_no_pisa_al_modelo_pedido](../tests/test_llm.py#L96) | Un modelo explicito es una orden, no una preferencia que el rol pueda ganar. |
| [_reasoning_effort_de](../tests/test_llm.py#L106) | Obtiene reasoning_effort del modelo construido para comprobar su configuracion. |
| [test_los_modelos_gpt56_permiten_herramientas](../tests/test_llm.py#L111) | Regresion del 2026-09-08: los cuatro modelos de OpenAI fallaban 0/17 en el |
| [test_gpt6_astra_no_recibe_reasoning_effort_none](../tests/test_llm.py#L139) | Segunda vuelta de la misma regresion, con un giro: mandarle 'none' a |
| [test_modelo_activo_respeta_el_backend](../tests/test_llm.py#L159) | Con las dos variables definidas en el `.env` -- que es lo normal -- hay que |
| [test_el_juez_es_el_modelo_que_dice_ser](../tests/test_llm.py#L174) | El informe declara quien califico. Si el juez declarado y el real no |
| [test_el_registro_del_turno_guarda_el_plan_completo](../tests/test_llm.py#L196) | Un turno atendido por dos agentes tiene que poder distinguirse de uno |
| [test_un_turno_de_un_solo_paso_igual_deja_su_plan](../tests/test_llm.py#L219) | Lista de uno, no lista vacia: que no haya que adivinar si nadie lo anoto. |
| [test_las_metricas_cuentan_cada_paso_y_los_turnos_encadenados](../tests/test_llm.py#L238) | `pasos_por_agente` se llamaba `ruteos_por_agente` y buscaba un evento |

## tests/test_mcp.py

| Elemento | Descripcion |
|---|---|
| [modulo](../tests/test_mcp.py#L1) | Pruebas del servidor MCP de tickets -- Sesion 16. |
| [servicio_mcp](../tests/test_mcp.py#L22) | Cliente MCP contra el servidor en memoria, con almacenamiento temporal. |
| [test_el_servidor_no_publica_ninguna_herramienta_de_cierre](../tests/test_mcp.py#L35) | El corazon del diseno: el agente no tiene prohibido cerrar un ticket, es que |
| [test_toda_herramienta_publicada_se_describe_para_el_modelo](../tests/test_mcp.py#L53) | El docstring es el contrato que lee el modelo: una tool sin descripcion |
| [test_un_ticket_creado_por_mcp_vuelve_con_su_plazo](../tests/test_mcp.py#L64) | Verifica que un ticket creado por mcp vuelve con su plazo. |
| [test_lo_creado_por_mcp_se_puede_volver_a_leer_por_mcp](../tests/test_mcp.py#L78) | Verifica que lo creado por mcp se puede volver a leer por mcp. |
| [test_consultar_un_ticket_que_no_existe_no_revienta](../tests/test_mcp.py#L92) | Un codigo mal tipeado por el cliente es lo normal, no una excepcion. |
| [test_comentar_por_mcp_persiste_la_nota_y_no_finge_exito](../tests/test_mcp.py#L98) | Verifica que comentar por mcp persiste la nota y no finge exito. |
| [test_si_el_servidor_no_responde_el_reclamo_no_se_pierde](../tests/test_mcp.py#L110) | Un servicio externo caido no puede costarle al cliente su reclamo. El |
| [test_el_backend_mcp_cumple_el_mismo_contrato_que_los_otros_dos](../tests/test_mcp.py#L130) | Los tres backends son intercambiables: si alguno pierde un metodo, el |

## tests/test_message_service.py

| Elemento | Descripcion |
|---|---|
| [modulo](../tests/test_message_service.py#L1) | Tests for the channel-agnostic conversation flow: no network, no Postgres. |
| [_patch_repositories](../tests/test_message_service.py#L8) | Sustituye repositorios y puente LLM por dobles que capturan llamadas sin red ni base real. |
| [test_handle_incoming_message_stores_the_message_and_returns_the_chat_id](../tests/test_message_service.py#L36) | Verifies handle incoming message stores the message and returns the chat id. |
| [test_handle_incoming_message_skips_without_a_chat_key](../tests/test_message_service.py#L55) | Verifies handle incoming message skips without a chat key. |
| [test_handle_incoming_message_traces_unsupported_content_without_touching_the_db](../tests/test_message_service.py#L67) | Verifies handle incoming message traces unsupported content without touching the db. |
| [test_handle_incoming_message_skips_silently_without_text_or_reason](../tests/test_message_service.py#L86) | Verifies handle incoming message skips silently without text or reason. |
| [test_generate_and_store_reply_stores_the_reply_and_returns_it](../tests/test_message_service.py#L99) | Verifies generate and store reply stores the reply and returns it. |
| [test_whatsapp_blocks_secrets_before_orchestrator_and_redacts_storage](../tests/test_message_service.py#L111) | El canal real bloquea tarjetas antes del agente y persiste solo texto redactado. |
| [test_whatsapp_input_rejection_skips_agent_and_output_rejection_is_stored](../tests/test_message_service.py#L130) | Entrada rechazada evita el LLM; salida rechazada se sustituye antes de almacenar. |
| [test_whatsapp_preserves_authenticated_identity_and_shared_history](../tests/test_message_service.py#L151) | El orquestador recibe la sesion estable y el historial redactado del canal real. |
| [test_whatsapp_preserves_authenticated_identity_and_shared_history.responder](../tests/test_message_service.py#L162) | Captura identidad e historial y devuelve una respuesta sin usar un modelo. |
| [test_whatsapp_real_postgres_never_stores_raw_card](../tests/test_message_service.py#L178) | Con Postgres aislado disponible, persiste entrada bloqueada y salida sin tarjeta cruda. |

## tests/test_orquestador.py

| Elemento | Descripcion |
|---|---|
| [modulo](../tests/test_orquestador.py#L1) | Pruebas del orquestador: el plan, el encadenamiento y el punto unico de salida. |
| [test_el_plan_no_repite_agente_ni_pasa_del_tope](../tests/test_orquestador.py#L20) | El esquema de salida garantiza que los valores son validos, no que sean |
| [test_que_sigue_despues_de_cada_paso](../tests/test_orquestador.py#L44) | Verifica que que sigue despues de cada paso. |
| [test_un_plan_de_dos_pasos_recorre_los_dos_agentes](../tests/test_orquestador.py#L53) | El caso que antes se perdia: "espere 40 minutos y ahora quiero mesa el sabado". |
| [test_un_plan_de_dos_pasos_recorre_los_dos_agentes.agente_falso](../tests/test_orquestador.py#L62) | Fabrica un componente simulado que registra el orden de llamada y devuelve su nombre. |
| [test_un_plan_de_dos_pasos_recorre_los_dos_agentes.agente_falso.responder](../tests/test_orquestador.py#L64) | Anota la llamada al componente simulado y devuelve texto identificable en el cierre. |
| [test_una_sola_respuesta_no_paga_una_llamada_de_sintesis](../tests/test_orquestador.py#L94) | Optimizacion deliberada, y la mas importante del nodo de cierre: reescribir |
| [test_una_sola_respuesta_no_paga_una_llamada_de_sintesis.explotar](../tests/test_orquestador.py#L100) | Falla deliberadamente si se llama o para simular una sintesis fallida, segun la prueba. |
| [test_si_falla_la_sintesis_no_se_pierde_ninguna_respuesta](../tests/test_orquestador.py#L110) | Dos textos pegados se leen feo; perder uno de los dos es peor. |
| [test_si_falla_la_sintesis_no_se_pierde_ninguna_respuesta.explotar](../tests/test_orquestador.py#L112) | Falla deliberadamente si se llama o para simular una sintesis fallida, segun la prueba. |
| [test_sin_escalamiento_el_cierre_no_inventa_ticket](../tests/test_orquestador.py#L130) | Solo se abre ticket si un agente levanto la mano. No por las dudas. |
| [test_un_hilo_escala_una_sola_vez](../tests/test_orquestador.py#L149) | Regresion del experimento del 2026-09-08. |
| [test_un_hilo_escala_una_sola_vez.turno](../tests/test_orquestador.py#L168) | Cierra un turno con contexto nuevo y la misma sesion para comprobar deduplicacion del caso. |
| [test_el_cierre_no_repite_un_codigo_que_el_agente_ya_dijo](../tests/test_orquestador.py#L192) | Antes se pegaba siempre una frase completa encima de la del agente, que decia |
| [test_aprobar_revision_reanuda_y_crea_ticket_en_el_cierre](../tests/test_orquestador.py#L205) | Verifica que aprobar revision reanuda y crea ticket en el cierre. |
| [test_aprobar_revision_reanuda_y_crea_ticket_en_el_cierre.reanudar](../tests/test_orquestador.py#L219) | Simula la reanudacion autorizada y coloca el escalamiento en el contexto compartido. |
| [test_rechazar_revision_no_crea_ticket](../tests/test_orquestador.py#L237) | Verifica que rechazar revision no crea ticket. |

## tests/test_outbound_whatsapp.py

| Elemento | Descripcion |
|---|---|
| [modulo](../tests/test_outbound_whatsapp.py#L1) | Tests for the outbound WhatsApp service: no real network call. |
| [_FakeResponse](../tests/test_outbound_whatsapp.py#L8) | Simula una respuesta HTTP de Twilio para probar envio y manejo de errores. |
| [_FakeResponse.__init__](../tests/test_outbound_whatsapp.py#L10) | Inicializa el doble HTTP con codigo y cuerpo de respuesta. |
| [_FakeResponse.json](../tests/test_outbound_whatsapp.py#L16) | Devuelve el cuerpo JSON simulado. |
| [test_send_whatsapp_message_addresses_a_real_number](../tests/test_outbound_whatsapp.py#L21) | Verifies send whatsapp message addresses a real number. |
| [test_send_whatsapp_message_addresses_a_real_number.fake_post](../tests/test_outbound_whatsapp.py#L25) | Captura la peticion de envio a Twilio sin realizar trafico externo. |
| [test_send_whatsapp_message_addresses_a_business_scoped_id](../tests/test_outbound_whatsapp.py#L40) | Verifies send whatsapp message addresses a business scoped id. |
| [test_send_whatsapp_message_raises_without_credentials](../tests/test_outbound_whatsapp.py#L53) | Verifies send whatsapp message raises without credentials. |
| [test_send_whatsapp_message_raises_on_twilio_error](../tests/test_outbound_whatsapp.py#L59) | Verifies send whatsapp message raises on twilio error. |

## tests/test_pii.py

| Elemento | Descripcion |
|---|---|
| [modulo](../tests/test_pii.py#L1) | Pruebas de bloqueo y redaccion local de PII en texto, estructuras y trazas. |
| [test_bloquea_tarjetas_y_secretos](../tests/test_pii.py#L6) | Verifica que bloquea tarjetas y secretos. |
| [test_redacta_pii_de_trazas_y_respuestas](../tests/test_pii.py#L12) | Verifica que redacta pii de trazas y respuestas. |
| [test_telefono_se_permite_para_operar_la_reserva](../tests/test_pii.py#L21) | Verifica que telefono se permite para operar la reserva. |
| [test_registrar_nunca_guarda_pii_cruda](../tests/test_pii.py#L26) | Verifica que registrar nunca guarda pii cruda. |

## tests/test_presupuesto_eval.py

| Elemento | Descripcion |
|---|---|
| [modulo](../tests/test_presupuesto_eval.py#L1) | Pruebas del presupuesto persistente y de la intercepcion HTTP con peticiones simuladas. |
| [test_limite_impide_salida_y_persiste_entre_etapas](../tests/test_presupuesto_eval.py#L12) | Verifica que limite impide salida y persiste entre etapas. |
| [test_token_cap_y_uso_reportado](../tests/test_presupuesto_eval.py#L24) | Comprueba el limite de 2048 tokens y el cargo por uso reportado en ambos transportes. |
| [test_token_cap_y_uso_reportado.respuesta](../tests/test_presupuesto_eval.py#L27) | Construye una respuesta HTTP simulada con uso de tokens para comprobar cargos. |
| [test_token_cap_y_uso_reportado.llamada](../tests/test_presupuesto_eval.py#L35) | Envia una peticion asincrona al transporte simulado bajo el presupuesto activo. |
| [test_error_conserva_reserva](../tests/test_presupuesto_eval.py#L47) | Verifica que error conserva reserva. |
| [test_intercepta_sdk_instalado_httpx2](../tests/test_presupuesto_eval.py#L57) | Verifica que intercepta sdk instalado httpx2. |

## tests/test_rag_azure_y_checkpoint.py

| Elemento | Descripcion |
|---|---|
| [modulo](../tests/test_rag_azure_y_checkpoint.py#L1) | RAG de Azure con un indice falso (ids estables, borrado de obsoletos) y checkpoint sin historial repetido; sin red. |
| [AzureFalso](../tests/test_rag_azure_y_checkpoint.py#L11) | Indice de Azure AI Search simulado: guarda documentos por id y admite buscar, subir y borrar. |
| [AzureFalso.__init__](../tests/test_rag_azure_y_checkpoint.py#L14) | Empieza con un indice vacio. |
| [AzureFalso.merge_or_upload_documents](../tests/test_rag_azure_y_checkpoint.py#L19) | Sube o actualiza documentos por id, como mergeOrUpload; puede simular rechazos. |
| [AzureFalso.search](../tests/test_rag_azure_y_checkpoint.py#L25) | Devuelve los ids del indice paginados, como una busqueda vacia con select=id. |
| [AzureFalso.delete_documents](../tests/test_rag_azure_y_checkpoint.py#L29) | Borra por id. |
| [AzureFalso.get_document_count](../tests/test_rag_azure_y_checkpoint.py#L34) | Cantidad de documentos del indice. |
| [catalogo](../tests/test_rag_azure_y_checkpoint.py#L40) | Catalogo temporal con dos archivos, conectado a un Azure falso y a embeddings falsos. |
| [test_reindexar_tras_agregar_una_seccion_no_duplica](../tests/test_rag_azure_y_checkpoint.py#L53) | Verifica que agregar una seccion al principio deja 4 chunks y no 7: los ids no dependen de la posicion global. |
| [test_editar_una_seccion_actualiza_en_lugar_de_duplicar](../tests/test_rag_azure_y_checkpoint.py#L66) | Verifica que cambiar el texto de una seccion reemplaza su version vieja. |
| [test_una_seccion_retirada_se_borra_del_indice](../tests/test_rag_azure_y_checkpoint.py#L77) | Verifica que lo que ya no esta en el catalogo deja de poder recuperarse. |
| [test_un_catalogo_vacio_no_vacia_el_indice](../tests/test_rag_azure_y_checkpoint.py#L86) | Verifica que un error de carpeta (sin documentos) no borra el indice existente. |
| [test_una_carga_incompleta_no_borra_nada](../tests/test_rag_azure_y_checkpoint.py#L96) | Verifica que si Azure rechaza documentos no se borra lo anterior. |
| [test_dos_archivos_con_el_mismo_nombre_no_se_pisan](../tests/test_rag_azure_y_checkpoint.py#L106) | Verifica que un mismo nombre de archivo y seccion en dos carpetas genera ids distintos. |
| [_agente_con_checkpoint](../tests/test_rag_azure_y_checkpoint.py#L118) | Agente real de LangChain con un modelo falso que anota cuantos mensajes recibe y un checkpoint en memoria. |
| [_agente_con_checkpoint.Modelo](../tests/test_rag_azure_y_checkpoint.py#L125) | Modelo falso que registra el tamano de lo que recibe. |
| [_agente_con_checkpoint.Modelo.bind_tools](../tests/test_rag_azure_y_checkpoint.py#L127) | Ignora las tools: esta prueba no las usa. |
| [_agente_con_checkpoint.Modelo._generate](../tests/test_rag_azure_y_checkpoint.py#L131) | Anota cuantos mensajes llegaron y responde con un texto fijo. |
| [test_el_agente_no_ve_el_historial_repetido_turno_a_turno](../tests/test_rag_azure_y_checkpoint.py#L140) | Verifica que con checkpoint el modelo recibe solo el historial reenviado mas el mensaje nuevo, sin acumular copias. |
| [test_borrar_el_hilo_no_falla_si_no_hay_checkpoint_o_no_se_puede_borrar](../tests/test_rag_azure_y_checkpoint.py#L152) | Verifica que un agente sin checkpointer, o con uno que no sabe borrar, no interrumpe la respuesta. |
| [test_borrar_el_hilo_no_falla_si_no_hay_checkpoint_o_no_se_puede_borrar.SinBorrado](../tests/test_rag_azure_y_checkpoint.py#L156) | Checkpointer que no sabe borrar hilos. |

## tests/test_redteam_montaje.py

| Elemento | Descripcion |
|---|---|
| [modulo](../tests/test_redteam_montaje.py#L1) | Regresiones del montaje: datos aislados y errores no contados como aprobados. |
| [test_aislamiento_incluso_tras_error](../tests/test_redteam_montaje.py#L12) | Verifica que aislamiento incluso tras error. |
| [test_error_del_objetivo_deja_evidencia_y_no_respuesta](../tests/test_redteam_montaje.py#L36) | Verifica que error del objetivo deja evidencia y no respuesta. |
| [test_error_del_objetivo_deja_evidencia_y_no_respuesta.fallo](../tests/test_redteam_montaje.py#L40) | Simula un fallo del objetivo o motor para comprobar conservacion de evidencias y errores. |
| [test_rechaza_historial_en_vez_de_ignorar_turnos](../tests/test_redteam_montaje.py#L54) | Verifica que rechaza historial en vez de ignorar turnos. |
| [test_fallo_de_deepteam_conserva_casos_parciales](../tests/test_redteam_montaje.py#L61) | Verifica que fallo de deepteam conserva casos parciales. |
| [test_fallo_de_deepteam_conserva_casos_parciales.Motor](../tests/test_redteam_montaje.py#L66) | Doble DeepTeam que conserva un ataque parcial y falla como si se agotara el saldo. |
| [test_fallo_de_deepteam_conserva_casos_parciales.Motor.__init__](../tests/test_redteam_montaje.py#L70) | Comprueba que el motor simulado se configure sin concurrencia adicional. |
| [test_fallo_de_deepteam_conserva_casos_parciales.Motor.red_team](../tests/test_redteam_montaje.py#L73) | Verifica opciones del montaje y lanza el agotamiento simulado tras conservar un caso. |
| [test_main_guarda_estado_error_antes_de_propagar](../tests/test_redteam_montaje.py#L86) | Verifica que main guarda estado error antes de propagar. |
| [test_main_guarda_estado_error_antes_de_propagar.fallo](../tests/test_redteam_montaje.py#L91) | Simula un fallo del objetivo o motor para comprobar conservacion de evidencias y errores. |

## tests/test_reservas.py

| Elemento | Descripcion |
|---|---|
| [modulo](../tests/test_reservas.py#L1) | Pruebas del Gestor de Reservas. |
| [test_hay_disponibilidad_en_turno_valido](../tests/test_reservas.py#L11) | Verifica que hay disponibilidad en turno valido. |
| [test_no_hay_disponibilidad_fuera_de_turno](../tests/test_reservas.py#L18) | Verifica que no hay disponibilidad fuera de turno. |
| [test_asigna_la_mesa_mas_ajustada](../tests/test_reservas.py#L23) | Verifica que asigna la mesa mas ajustada. |
| [test_una_mesa_no_se_reserva_dos_veces](../tests/test_reservas.py#L31) | Verifica que una mesa no se reserva dos veces. |
| [test_cancelar_libera_la_mesa](../tests/test_reservas.py#L39) | Verifica que cancelar libera la mesa. |
| [test_modificar_hora_conserva_la_reserva](../tests/test_reservas.py#L52) | Verifica que modificar hora conserva la reserva. |
| [test_sin_mesa_para_el_grupo_lanza_error](../tests/test_reservas.py#L63) | Verifica que sin mesa para el grupo lanza error. |

## tests/test_seguridad_limites.py

| Elemento | Descripcion |
|---|---|
| [modulo](../tests/test_seguridad_limites.py#L1) | Limites, revision humana atomica, tickets y entradas hostiles; sin LLM. Prueba las capas que no dependen del modelo. |
| [reloj_fijo](../tests/test_seguridad_limites.py#L23) | Fija el reloj de Lima para las fechas de estas pruebas. |
| [servicio](../tests/test_seguridad_limites.py#L29) | Servicio de reservas JSON temporal conectado a las tools. |
| [runtime](../tests/test_seguridad_limites.py#L36) | Runtime simulado con sesion identificada y contexto vacio. |
| [entrante](../tests/test_seguridad_limites.py#L41) | Mensaje entrante de WhatsApp con los datos minimos. |
| [respuesta_falsa](../tests/test_seguridad_limites.py#L46) | Respuesta ficticia de un turno ya admitido. |
| [test_mensaje_demasiado_largo_no_llega_al_modelo](../tests/test_seguridad_limites.py#L53) | Verifica que un mensaje de mas de 2000 caracteres se rechaza antes de planificar. |
| [test_una_rafaga_se_limita_y_otra_conversacion_no](../tests/test_seguridad_limites.py#L60) | Verifica que la conversacion que supera el maximo por minuto se limita sin afectar a las demas. |
| [test_la_ventana_de_frecuencia_se_libera_con_el_tiempo](../tests/test_seguridad_limites.py#L70) | Verifica que pasado el minuto la conversacion vuelve a poder escribir. |
| [test_los_turnos_de_una_conversacion_se_serializan](../tests/test_seguridad_limites.py#L78) | Verifica que dos mensajes simultaneos de la misma conversacion no se ejecutan a la vez. |
| [test_los_turnos_de_una_conversacion_se_serializan.turno](../tests/test_seguridad_limites.py#L82) | Turno lento que detecta si otro turno de la misma conversacion corre a la vez. |
| [test_otras_conversaciones_no_esperan](../tests/test_seguridad_limites.py#L98) | Verifica que el candado es por conversacion: dos clientes distintos corren en paralelo. |
| [test_otras_conversaciones_no_esperan.turno](../tests/test_seguridad_limites.py#L102) | Turno lento que registra cuantos turnos corren a la vez. |
| [test_si_el_turno_anterior_no_termina_se_responde_ocupado](../tests/test_seguridad_limites.py#L117) | Verifica que un mensaje que espera demasiado recibe un aviso y no se procesa en paralelo. |
| [test_si_el_turno_anterior_no_termina_se_responde_ocupado.turno](../tests/test_seguridad_limites.py#L122) | Turno que no termina hasta que la prueba lo suelta. |
| [_encolar](../tests/test_seguridad_limites.py#L139) | Deja una revision pendiente y sustituye la reanudacion del agente por `resolver`. |
| [test_dos_aprobaciones_simultaneas_reanudan_una_sola_vez](../tests/test_seguridad_limites.py#L148) | Verifica que dos peticiones a la vez sobre la misma revision solo reanudan al agente una vez. |
| [test_dos_aprobaciones_simultaneas_reanudan_una_sola_vez.resolver](../tests/test_seguridad_limites.py#L152) | Reanudacion lenta que cuenta cuantas veces se ejecuta. |
| [test_dos_aprobaciones_simultaneas_reanudan_una_sola_vez.pedir](../tests/test_seguridad_limites.py#L160) | Una peticion del personal; anota si tuvo exito o si la revision ya no existia. |
| [test_no_se_puede_cambiar_una_decision_ya_tomada](../tests/test_seguridad_limites.py#L174) | Verifica que un reject despues de un approve (y al reves) no reanuda nada. |
| [test_si_la_reanudacion_falla_la_revision_vuelve_a_la_cola](../tests/test_seguridad_limites.py#L184) | Verifica que un error del agente no pierde la revision: el personal puede reintentar. |
| [test_si_la_reanudacion_falla_la_revision_vuelve_a_la_cola.falla](../tests/test_seguridad_limites.py#L186) | Simula un fallo del agente al reanudar. |
| [_propuesta](../tests/test_seguridad_limites.py#L201) | Prepara una reserva y devuelve el codigo real de la propuesta. |
| [test_cinco_codigos_equivocados_cancelan_la_propuesta](../tests/test_seguridad_limites.py#L207) | Verifica que tras el tope de intentos fallidos el codigo correcto ya no sirve. |
| [test_el_codigo_correcto_dentro_del_tope_si_confirma](../tests/test_seguridad_limites.py#L220) | Verifica que unos pocos errores no impiden confirmar con el codigo real. |
| [test_textos_hostiles_no_confirman_nada](../tests/test_seguridad_limites.py#L234) | Verifica que variantes, mezclas y trucos de formato no ejecutan ni confirman la propuesta. |
| [test_el_mismo_reclamo_no_abre_dos_casos](../tests/test_seguridad_limites.py#L244) | Verifica que repetir un reclamo devuelve el caso existente en vez de abrir otro. |
| [test_una_conversacion_no_puede_abrir_casos_sin_limite](../tests/test_seguridad_limites.py#L252) | Verifica que tras tres casos abiertos en una hora no se abren mas. |
| [test_el_limite_de_casos_es_por_conversacion](../tests/test_seguridad_limites.py#L261) | Verifica que el tope de una conversacion no bloquea a otra. |
| [test_reclamo_sobre_reserva_ajena_no_crea_caso](../tests/test_seguridad_limites.py#L269) | Verifica que citar una reserva que no es de esta conversacion se rechaza sin abrir caso. |
| [test_la_descripcion_de_un_caso_se_acota_y_queda_en_una_linea](../tests/test_seguridad_limites.py#L276) | Verifica que una descripcion enorme o con saltos de linea se guarda acotada y en una sola linea. |
| [test_el_escalamiento_no_se_duplica_tras_un_reinicio](../tests/test_seguridad_limites.py#L284) | Verifica que si se pierde el estado en memoria el ticket ya abierto se reutiliza, no se duplica. |
| [test_si_el_registro_de_incidencias_falla_no_se_bloquea_el_reclamo](../tests/test_seguridad_limites.py#L295) | Verifica que un fallo al buscar casos previos deja registrar el reclamo en vez de perderlo. |
| [test_si_el_registro_de_incidencias_falla_no_se_bloquea_el_reclamo.Roto](../tests/test_seguridad_limites.py#L299) | Backend que falla al listar. |
| [test_si_el_registro_de_incidencias_falla_no_se_bloquea_el_reclamo.Roto.listar_incidencias](../tests/test_seguridad_limites.py#L301) | Simula que Trello no responde. |
| [test_los_temas_fuera_del_plan_se_avisan](../tests/test_seguridad_limites.py#L311) | Verifica que lo que el tope de pasos deja sin atender se reporta y no se descarta en silencio. |
| [test_el_resumen_del_servidor_muestra_el_dia_de_la_semana](../tests/test_seguridad_limites.py#L325) | Verifica que el resumen que confirma el cliente incluye el dia real de la fecha, aunque el modelo omita dia_semana. |
| [test_la_excepcion_de_grupo_valida_la_fecha](../tests/test_seguridad_limites.py#L331) | Verifica que un grupo grande con fecha pasada o dia contradictorio no abre caso. |
| [test_limpiar_texto_quita_control_saltos_e_invisibles](../tests/test_seguridad_limites.py#L345) | Verifica que el limpiador deja una linea, sin caracteres de control ni invisibles, con largo maximo. |
| [test_una_nota_con_instrucciones_solo_aparece_en_el_resumen_del_servidor](../tests/test_seguridad_limites.py#L353) | Verifica que una nota hostil no otorga permisos ni escribe: queda como texto en un resumen que aun exige CONFIRMO. |
| [test_reserva_ajena_e_inexistente_dan_la_misma_respuesta](../tests/test_seguridad_limites.py#L363) | Verifica que no hay forma de distinguir si un codigo existe: ajeno, inexistente y mal formado responden igual. |
| [test_los_datos_internos_no_se_piden_por_argumentos_de_la_tool](../tests/test_seguridad_limites.py#L373) | Verifica que la conversacion, el canal y la autorizacion no son parametros que el modelo pueda rellenar. |

## tests/test_seguridad_reservas.py

| Elemento | Descripcion |
|---|---|
| [modulo](../tests/test_seguridad_reservas.py#L1) | Regresiones de autorizacion con datos ficticios; no invocan ningun LLM. |
| [entorno](../tests/test_seguridad_reservas.py#L14) | Conecta herramientas y orquestador a servicios temporales y aisla la memoria del cliente. |
| [runtime](../tests/test_seguridad_reservas.py#L26) | Crea un runtime simulado con sesion identificada y contexto de negocio vacio. |
| [reserva](../tests/test_seguridad_reservas.py#L31) | Crea una reserva sintetica en el servicio temporal para pruebas de autorizacion. |
| [test_crear_no_escribe_sin_confirmacion_del_servidor](../tests/test_seguridad_reservas.py#L36) | Verifica que crear no escribe sin confirmacion del servidor. |
| [test_conocer_codigo_no_permite_leer_reserva_ajena](../tests/test_seguridad_reservas.py#L43) | Verifica que conocer codigo no permite leer reserva ajena. |
| [test_conocer_telefono_no_permite_leer_reservas_ajenas](../tests/test_seguridad_reservas.py#L51) | Verifica que conocer telefono no permite leer reservas ajenas. |
| [test_cancelar_reserva_ajena_no_escribe](../tests/test_seguridad_reservas.py#L59) | Verifica que cancelar reserva ajena no escribe. |
| [test_modificar_reserva_ajena_no_escribe](../tests/test_seguridad_reservas.py#L67) | Verifica que modificar reserva ajena no escribe. |
| [test_error_no_promete_contacto_sin_ticket](../tests/test_seguridad_reservas.py#L75) | Verifica que error no promete contacto sin ticket. |
| [test_error_no_promete_contacto_sin_ticket.Caido](../tests/test_seguridad_reservas.py#L77) | Doble de dependencia que falla para comprobar que no se anuncien operaciones inexistentes. |
| [test_error_no_promete_contacto_sin_ticket.Caido.invoke](../tests/test_seguridad_reservas.py#L79) | Devuelve el turno simulado o lanza el fallo previsto por el doble de esta prueba. |
| [propuesta_crear](../tests/test_seguridad_reservas.py#L90) | Prepara una reserva sin escribirla y devuelve runtime y comando CONFIRMO generado. |
| [test_confirmacion_ejecuta_sin_llm_y_solo_una_vez](../tests/test_seguridad_reservas.py#L98) | Verifica que confirmacion ejecuta sin llm y solo una vez. |
| [test_token_ajeno_no_confirma_y_no_consume_el_del_dueno](../tests/test_seguridad_reservas.py#L113) | Verifica que token ajeno no confirma y no consume el del dueno. |
| [test_ambiguo_o_inyeccion_no_ejecuta](../tests/test_seguridad_reservas.py#L123) | Verifica que ambiguo o inyeccion no ejecuta. |
| [test_token_vencido_no_ejecuta](../tests/test_seguridad_reservas.py#L131) | Verifica que token vencido no ejecuta. |
| [test_modificar_y_cancelar_propias_exigen_confirmacion](../tests/test_seguridad_reservas.py#L141) | Verifica que modificar y cancelar propias exigen confirmacion. |
| [test_no_confirma_snapshot_que_cambio](../tests/test_seguridad_reservas.py#L157) | Verifica que no confirma snapshot que cambio. |
| [test_modificar_mas_de_diez_no_se_propone](../tests/test_seguridad_reservas.py#L170) | Verifica que modificar mas de diez no se propone. |
| [test_cierre_muestra_propuesta_aunque_modelo_afirme_confirmada](../tests/test_seguridad_reservas.py#L180) | Verifica que cierre muestra propuesta aunque modelo afirme confirmada. |
| [test_incidencias_no_es_un_camino_alterno_para_leer_reservas](../tests/test_seguridad_reservas.py#L189) | Verifica que incidencias no es un camino alterno para leer reservas. |
| [test_ficha_no_inyecta_reservas_ajenas_y_persiste_la_propiedad](../tests/test_seguridad_reservas.py#L198) | Verifica que ficha no inyecta reservas ajenas y persiste la propiedad. |
| [test_ticket_real_reemplaza_codigo_inventado_y_no_promete_notificar](../tests/test_seguridad_reservas.py#L211) | Verifica que ticket real reemplaza codigo inventado y no promete notificar. |
| [test_fallo_al_crear_ticket_no_finge_escalamiento](../tests/test_seguridad_reservas.py#L223) | Verifica que fallo al crear ticket no finge escalamiento. |
| [test_fallo_al_crear_ticket_no_finge_escalamiento.Caido](../tests/test_seguridad_reservas.py#L225) | Doble de dependencia que falla para comprobar que no se anuncien operaciones inexistentes. |
| [test_fallo_al_crear_ticket_no_finge_escalamiento.Caido.crear_incidencia](../tests/test_seguridad_reservas.py#L227) | Lanza un error de escritura simulado para comprobar el cierre ante fallo del ticket. |
| [test_el_juez_recibe_el_codigo_creado_por_el_cierre](../tests/test_seguridad_reservas.py#L240) | Verifica que el juez recibe el codigo creado por el cierre. |
| [test_cambio_de_pedido_invalida_confirmacion_anterior](../tests/test_seguridad_reservas.py#L255) | Verifica que cambio de pedido invalida confirmacion anterior. |
| [test_cambio_de_pedido_invalida_confirmacion_anterior.Conversacion](../tests/test_seguridad_reservas.py#L259) | Doble del grafo que devuelve informacion para simular un cambio de pedido. |
| [test_cambio_de_pedido_invalida_confirmacion_anterior.Conversacion.invoke](../tests/test_seguridad_reservas.py#L261) | Devuelve el turno simulado o lanza el fallo previsto por el doble de esta prueba. |
| [test_reset_invalida_permiso_sin_perder_propiedad](../tests/test_seguridad_reservas.py#L270) | Verifica que reset invalida permiso sin perder propiedad. |
| [test_confirmaciones_simultaneas_no_duplican_la_reserva](../tests/test_seguridad_reservas.py#L281) | Verifica que confirmaciones simultaneas no duplican la reserva. |
| [test_confirmaciones_simultaneas_no_duplican_la_reserva.confirmar_en_hilo](../tests/test_seguridad_reservas.py#L288) | Cada escritor Postgres usa su propio contexto Flask; JSON no lo necesita. |
| [test_caso_ajeno_no_se_consulta_desde_incidencias](../tests/test_seguridad_reservas.py#L300) | Verifica que caso ajeno no se consulta desde incidencias. |
| [test_chat_real_prepara_y_confirma_sin_modelo_en_el_segundo_turno](../tests/test_seguridad_reservas.py#L308) | Verifica que chat real prepara y confirma sin modelo en el segundo turno. |
| [test_chat_real_prepara_y_confirma_sin_modelo_en_el_segundo_turno.nodo_reservas](../tests/test_seguridad_reservas.py#L314) | Prepara una propuesta mediante la herramienta real y registra la sesion recibida. |
| [test_whatsapp_prepara_y_confirma_con_propiedad_del_canal](../tests/test_seguridad_reservas.py#L331) | WhatsApp usa el flujo protegido y exige confirmacion en otro turno para escribir. |
| [test_whatsapp_prepara_y_confirma_con_propiedad_del_canal.nodo_reservas](../tests/test_seguridad_reservas.py#L341) | Prepara una reserva real con contexto del canal sin invocar un modelo. |

## tests/test_whatsapp.py

| Elemento | Descripcion |
|---|---|
| [modulo](../tests/test_whatsapp.py#L1) | Tests for the WhatsApp service: no network, no Postgres. |
| [_signature](../tests/test_whatsapp.py#L19) | Calcula una firma Twilio de prueba para comprobar autenticacion del webhook. |
| [test_is_valid_request_accepts_the_correct_signature](../tests/test_whatsapp.py#L25) | Verifies is valid request accepts the correct signature. |
| [test_is_valid_request_rejects_wrong_signature_or_token](../tests/test_whatsapp.py#L33) | Verifies is valid request rejects wrong signature or token. |
| [test_resolve_chat_key_strips_the_whatsapp_prefix_and_plus](../tests/test_whatsapp.py#L43) | Verifies resolve chat key strips the whatsapp prefix and plus. |
| [test_resolve_chat_key_keeps_a_business_scoped_id_as_is](../tests/test_whatsapp.py#L48) | Verifies resolve chat key keeps a business scoped id as is. |
| [test_resolve_chat_key_is_none_without_from](../tests/test_whatsapp.py#L54) | Verifies resolve chat key is none without from. |
| [test_resolve_phone_returns_none_for_a_business_scoped_id](../tests/test_whatsapp.py#L59) | Verifies resolve phone returns none for a business scoped id. |
| [test_resolve_phone_returns_the_number_when_its_real](../tests/test_whatsapp.py#L64) | Verifies resolve phone returns the number when its real. |
| [test_is_business_scoped_user_id](../tests/test_whatsapp.py#L69) | Verifies is business scoped user id. |
| [test_format_whatsapp_address_keeps_e164_plus_for_real_numbers](../tests/test_whatsapp.py#L75) | Verifies format whatsapp address keeps e164 plus for real numbers. |
| [test_format_whatsapp_address_drops_plus_for_business_scoped_ids](../tests/test_whatsapp.py#L80) | Verifies format whatsapp address drops plus for business scoped ids. |
| [test_media_content_type_reads_the_first_attachment](../tests/test_whatsapp.py#L85) | Verifies media content type reads the first attachment. |
| [test_media_content_type_is_none_for_a_text_only_message](../tests/test_whatsapp.py#L90) | Verifies media content type is none for a text only message. |
| [test_is_valid_account_skips_the_check_when_unconfigured](../tests/test_whatsapp.py#L95) | Verifies is valid account skips the check when unconfigured. |
| [test_is_valid_account_matches_the_configured_account](../tests/test_whatsapp.py#L100) | Verifies is valid account matches the configured account. |
| [test_parse_inbound_builds_the_canonical_message](../tests/test_whatsapp.py#L106) | Verifies parse inbound builds the canonical message. |
| [test_parse_inbound_flags_media_without_body_as_unsupported](../tests/test_whatsapp.py#L123) | Verifies parse inbound flags media without body as unsupported. |
