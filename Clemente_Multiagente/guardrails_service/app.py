"""Servicio aislado de seguridad con Guardrails AI, basado en la sesión 24."""

import os
import secrets
from pathlib import Path

# En el workspace del curso usamos una ruta corta para evitar MAX_PATH en Windows.
# En otro clon, la caché queda junto al servicio salvo que se configure la variable.
service_dir = Path(__file__).resolve().parent
workspace = next(
    (parent for parent in service_dir.parents if parent.name == "PROGRAMA_IMPLEMENTACION_AGENTES_IA"),
    service_dir,
)
os.environ.setdefault(
    "HF_HOME", os.getenv("CLEMENTE_GUARDRAILS_CACHE", str(workspace / ".guardrails_models")),
)
os.environ.setdefault("OTEL_SDK_DISABLED", "true")
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")

from flask import Flask, jsonify, request
from guardrails import Guard
from guardrails_ai.detect_jailbreak import DetectJailbreak
from guardrails_ai.toxic_language import ToxicLanguage
from patrones import motivo_de_bloqueo, motivo_de_bloqueo_en_salida

app = Flask(__name__)
_guards = None


def obtener_guards():
    """Inicializa y reutiliza los guards de jailbreak (0.81) y toxicidad (0.8).

    Devuelve ambos validadores; on_fail=noop permite al endpoint decidir
    el bloqueo con validation_passed. La inicializacion puede cargar modelos."""
    global _guards
    if _guards is None:
        _guards = (
            Guard(name="clemente-jailbreak").use(
                DetectJailbreak(threshold=0.81, on_fail="noop")),
            Guard(name="clemente-toxicidad").use(
                ToxicLanguage(threshold=0.8, validation_method="full", on_fail="noop")),
        )
    return _guards


def autorizado() -> bool:
    """Valida el Bearer token de CLEMENTE_GUARDRAILS_TOKEN con comparacion constante.

    Si no se configura token devuelve False."""
    token = os.getenv("CLEMENTE_GUARDRAILS_TOKEN", "")
    return bool(token) and secrets.compare_digest(
        request.headers.get("Authorization", ""), f"Bearer {token}",
    )


@app.get("/health")
def health():
    """Devuelve el estado del proceso HTTP sin inicializar ni ejecutar los validadores."""
    return jsonify(status="ok", validator="DetectJailbreak")


@app.post("/validate/input")
def validate_input():
    """Valida POST /validate/input y devuelve valid, validated_output, reason y validator.

    Exige token (401) y texto no vacio (400). Primero aplica las reglas locales
    (amenazas, discriminacion e inyecciones de instrucciones, en patrones.py);
    luego ejecuta jailbreak y toxicidad. Un rechazo no devuelve texto validado;
    errores de los validadores se propagan."""
    if not autorizado():
        return jsonify(error="No autorizado"), 401
    text = str((request.get_json(silent=True) or {}).get("text") or "").strip()
    if not text:
        return jsonify(error="text es obligatorio"), 400
    bloqueo = motivo_de_bloqueo(text)
    if bloqueo:
        return jsonify(valid=False, validated_output=None, reason=bloqueo[1], validator=bloqueo[0])
    jailbreak, toxicidad = obtener_guards()
    resultados = (("DetectJailbreak", jailbreak.validate(text)),
                  ("ToxicLanguage", toxicidad.validate(text)))
    fallido = next(((nombre, salida) for nombre, salida in resultados
                    if not salida.validation_passed), None)
    valid = fallido is None
    validator = "DetectJailbreak+ToxicLanguage" if valid else fallido[0]
    validated = text if valid else None
    return jsonify(
        valid=valid,
        validated_output=validated,
        reason="" if valid else f"{validator} rechazó el contenido",
        validator=validator,
    )


@app.post("/validate/output")
def validate_output():
    """Valida POST /validate/output con el patron local y el guard de toxicidad.

    Exige token (401) y texto (400); devuelve el contrato de validacion y
    texto solo si pasa. No ejecuta el detector de jailbreak en las salidas."""
    if not autorizado():
        return jsonify(error="No autorizado"), 401
    text = str((request.get_json(silent=True) or {}).get("text") or "").strip()
    if not text:
        return jsonify(error="text es obligatorio"), 400
    bloqueo = motivo_de_bloqueo_en_salida(text)
    if bloqueo:
        return jsonify(valid=False, validated_output=None, reason=bloqueo[1], validator=bloqueo[0])
    toxicidad = obtener_guards()[1].validate(text)
    valid = bool(toxicidad.validation_passed)
    return jsonify(valid=valid, validated_output=text if valid else None,
                   reason="" if valid else "ToxicLanguage rechazó la salida",
                   validator="ToxicLanguage")


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=int(os.getenv("GUARDRAILS_PORT", "8200")))
