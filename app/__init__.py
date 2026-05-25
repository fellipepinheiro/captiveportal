import os
from flask import Flask
from .config import Config
from .extensions import db
from .routes.portal import bp as portal_bp
from .routes.admin import bp as admin_bp


def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    # Garante que o diretório de uploads existe
    uploads_dir = os.path.join(app.root_path, 'static', 'uploads')
    os.makedirs(uploads_dir, exist_ok=True)

    db.init_app(app)
    app.register_blueprint(portal_bp)
    app.register_blueprint(admin_bp)

    @app.get('/health')
    def health():
        return {'status': 'ok'}

    @app.context_processor
    def inject_logo():
        """Injeta a URL da logo customizada em todos os templates."""
        logo_path = os.path.join(app.root_path, 'static', 'uploads', 'logo.png')
        has_logo = os.path.exists(logo_path)
        return {'custom_logo_url': '/static/uploads/logo.png' if has_logo else None}

    return app
