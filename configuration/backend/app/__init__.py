from flask import Flask
from .config import Config
from .extensions.extensions import cors, mqtt
from .scheduler import start_scheduler

from .routes.venti_routes import venti_bp
from .routes.influx_routes import influx_bp
from .routes.system_routes import system_bp

def register_routes(app):
    app.register_blueprint(venti_bp)
    app.register_blueprint(influx_bp)
    app.register_blueprint(system_bp)


def create_app():
    app = Flask(__name__)
    app.secret_key = Config.SECRET_KEY

    # MQTT
    app.config['MQTT_BROKER_URL'] = Config.MQTT_BROKER_URL
    app.config['MQTT_BROKER_PORT'] = Config.MQTT_BROKER_PORT
    app.config['MQTT_KEEPALIVE'] = Config.MQTT_KEEPALIVE

    cors.init_app(app)
    mqtt.init_app(app)

    start_scheduler()

    # Register routes
    register_routes(app)


    return app