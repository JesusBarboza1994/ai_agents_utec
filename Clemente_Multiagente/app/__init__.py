"""
Fabrica de la aplicacion Flask (patron *application factory*).

Todo el proyecto cuelga de aqui: `create_app()` arma la app, enciende la
observabilidad y registra los blueprints (los modulos HTTP) de cada
responsable. Nadie instancia Flask en otro archivo.

Por que una fabrica y no un `app = Flask(__name__)` global: permite crear la
app con configuracion distinta en las pruebas (sin trazas, con datos de
prueba) sin duplicar codigo.
"""

from flask import Flask
from flask_cors import CORS

from .config import Config


def create_app(config: Config | None = None) -> Flask:
    config = config or Config.desde_entorno()

    app = Flask(
        __name__,
        template_folder="web/templates",
        static_folder="web/static",
    )
    app.config["CLEMENTE"] = config
    CORS(app)

    # Observabilidad primero: asi cualquier cosa que ocurra despues ya queda trazada.
    from .observabilidad.trazas import configurar_observabilidad
    configurar_observabilidad(app, config)

    # Un blueprint por responsable. Cada quien agrega rutas SOLO en el suyo.
    from .comunicacion.rutas import bp as bp_comunicacion
    from .observabilidad.rutas import bp as bp_observabilidad
    app.register_blueprint(bp_comunicacion)
    app.register_blueprint(bp_observabilidad)

    return app
