"""
Fabrica de la aplicacion Flask (patron *application factory*).

Todo el proyecto cuelga de aqui: `create_app()` arma la app, enciende la
observabilidad y registra los blueprints (los modulos HTTP) de cada
responsable. Nadie instancia Flask en otro archivo.

Por que una fabrica y no un `app = Flask(__name__)` global: permite crear la
app con configuracion distinta en las pruebas (sin trazas, con datos de
prueba) sin duplicar codigo.
"""

import os

from flask import Flask

from .config import Config


def create_app(config: Config | None = None) -> Flask:
    """Crea la aplicacion Flask con la configuracion recibida o la del entorno.

    Configura cookies, limite de peticion, observabilidad y blueprints; devuelve
    la aplicacion sin iniciar el servidor ni comprobar servicios externos."""
    config = config or Config.desde_entorno()

    app = Flask(
        __name__,
        template_folder="web/templates",
        static_folder="web/static",
    )
    app.config["CLEMENTE"] = config
    app.config.update(SECRET_KEY=config.secret_key, SESSION_COOKIE_HTTPONLY=True,
                      SESSION_COOKIE_SAMESITE="Lax", MAX_CONTENT_LENGTH=16 * 1024)

    # Observabilidad primero: asi cualquier cosa que ocurra despues ya queda trazada.
    from .observabilidad.trazas import configurar_observabilidad
    configurar_observabilidad(app, config)

    from .arranque import verificar_arranque
    verificar_arranque(config)

    # Un blueprint por responsable. Cada quien agrega rutas SOLO en el suyo.
    from .communication.routes import bp as bp_comunicacion
    from .observabilidad.rutas import bp as bp_observabilidad
    app.register_blueprint(bp_comunicacion)
    app.register_blueprint(bp_observabilidad)

    # Rutas de depuracion de reservas (crear/consultar/cancelar SIN pasar
    # por el LLM ni por la confirmacion de autorizacion.py): solo para
    # probar persistencia y rendimiento a mano. Apagado por defecto -- no
    # tiene autenticacion, nunca debe prenderse con trafico real.
    if os.getenv("CLEMENTE_DEBUG_ROUTES") == "1":
        from .reservas.rutas import bp as bp_reservas_debug
        app.register_blueprint(bp_reservas_debug)

    return app
