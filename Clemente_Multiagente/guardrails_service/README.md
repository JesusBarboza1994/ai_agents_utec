# Servicio Guardrails AI

Este entorno separado ejecuta `DetectJailbreak` y `ToxicLanguage`, validadores del framework
Guardrails AI. Las amenazas y expresiones discriminatorias graves en español tienen además
una regla determinista porque el clasificador no cubre ese idioma de forma suficiente. El
validador de jailbreak fue presentado en la
sesión 24. Se aísla porque sus dependencias no son compatibles con DeepEval y
OpenTelemetry del proceso principal.

Se fija `transformers<5`: el validador 0.1.6 declara solo un mínimo, pero sus
modelos todavía no cargan con Transformers 5.x.

```powershell
python -m venv D:\APRENDIZAJE\PROGRAMA_IMPLEMENTACION_AGENTES_IA\.grvenv
D:\APRENDIZAJE\PROGRAMA_IMPLEMENTACION_AGENTES_IA\.grvenv\Scripts\python.exe -m pip install -r requirements.txt
$env:CLEMENTE_GUARDRAILS_TOKEN="un-token-largo"
D:\APRENDIZAJE\PROGRAMA_IMPLEMENTACION_AGENTES_IA\.grvenv\Scripts\python.exe app.py
```

Los pesos se guardan en `.guardrails_models` en la raíz del workspace para no
superar el límite de longitud de rutas de Windows.

En el `.env` de Clemente:

```ini
CLEMENTE_GUARDRAILS_URL=http://127.0.0.1:8200
CLEMENTE_GUARDRAILS_TOKEN=un-token-largo
```

Al arrancar, el servicio carga los modelos antes de recibir mensajes (unos 15 segundos); así el primer mensaje
no paga esa carga. `GET /health` responde `modelos_cargados: true` cuando ya está listo, y sirve de sonda de
"listo" en Azure. Se apaga con `CLEMENTE_GUARDRAILS_PRECARGAR=0`.

El detector funciona como defensa adicional. Las autorizaciones, límites de
tools, confirmación explícita e HITL siguen siendo obligatorios.
