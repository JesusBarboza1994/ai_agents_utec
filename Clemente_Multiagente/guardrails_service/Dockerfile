# Imagen del servicio de Guardrails AI (jailbreak y toxicidad) para Azure Container Apps.
# Se construye con la carpeta guardrails_service como contexto:
#   docker build -t guardrails:local Clemente_Multiagente/guardrails_service
# Ver docs/guia_azure/GUIA_GUARDRAILS_AZURE.md para el despliegue completo.
#
# Los modelos de transformers (unos 1,5 GB) se descargan al construir la imagen y quedan dentro de ella:
# asi el servicio arranca sin depender de descargar nada en cada reinicio.

FROM python:3.13-slim-bookworm

RUN useradd --create-home --uid 1000 guardrails \
    && mkdir -p /opt/hf \
    && chown guardrails:guardrails /opt/hf

ENV PIP_NO_CACHE_DIR=1 \
    PYTHONUNBUFFERED=1 \
    HF_HOME=/opt/hf \
    GUARDRAILS_PORT=8200

# torch va primero y desde el indice de CPU: el de PyPI trae la version con CUDA (varios GB mas) y en
# Container Apps no hay GPU.
RUN pip install --upgrade pip \
    && pip install torch --index-url https://download.pytorch.org/whl/cpu

WORKDIR /srv
COPY requirements.txt .
RUN pip install -r requirements.txt gunicorn

COPY --chown=guardrails:guardrails . .

USER guardrails

# Importar app.py carga los modelos (precargar) y los deja en /opt/hf. Si falla aqui, falla la construccion
# y no un despliegue a medias. El token solo existe para que el modulo importe; no se usa.
RUN CLEMENTE_GUARDRAILS_TOKEN=solo-para-construir python -c "import app"

EXPOSE 8200

# Un solo worker: cada worker carga los modelos en memoria. Los hilos atienden peticiones en paralelo.
CMD ["sh", "-c", "exec gunicorn --bind 0.0.0.0:${GUARDRAILS_PORT} --workers 1 --threads 4 --timeout 120 app:app"]
