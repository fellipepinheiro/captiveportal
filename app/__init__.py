from flask import Flask
from .config import Config
from .extensions import db
from .routes.portal import bp as portal_bp


def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    db.init_app(app)
    app.register_blueprint(portal_bp)

    @app.get('/health')
    def health():
        return {'status': 'ok'}

    return app
