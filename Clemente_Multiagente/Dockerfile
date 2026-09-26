# Imagen de produccion de Clemente. Ver docs/DESPLIEGUE_AZURE.md para el
# despliegue completo en Azure Container Apps (recursos, variables de entorno,
# CI/CD).
#
# Multi-stage: build con build-essential (red de seguridad si chromadb no trae
# wheel manylinux para la combinacion exacta de imagen/arquitectura), runtime
# liviano, usuario no-root.

FROM python:3.13-slim-bookworm AS builder

RUN apt-get update && apt-get install -y --no-install-recommends build-essential gcc \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build
COPY requirements.txt .
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

FROM python:3.13-slim-bookworm

RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --uid 1000 clemente

COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

WORKDIR /app
COPY --chown=clemente:clemente . .
RUN mkdir -p /mnt/datos && chown clemente:clemente /mnt/datos

USER clemente

# Los archivos que Clemente escribe (quien es duena de cada reserva, revisiones pendientes del staff, reclamos
# de respaldo) van a /mnt/datos. Para que sobrevivan a un reinicio o a un despliegue, la Container App tiene
# que montar ahi un volumen persistente (Azure Files); sin volumen se guardan igual, pero se pierden.
ENV CLEMENTE_DATOS_DIR=/mnt/datos \
    CLEMENTE_PORT=8000 \
    FLASK_DEBUG=0 \
    PYTHONUNBUFFERED=1 \
    ANONYMIZED_TELEMETRY=False

EXPOSE 8000

# Se arranca igual que en local: python run.py. run.py ya lee CLEMENTE_PORT y
# FLASK_DEBUG del entorno, asi que no hace falta tocar codigo -- FLASK_DEBUG=0
# arriba asegura que el debugger interactivo de Werkzeug quede desactivado.
CMD ["python", "run.py"]
