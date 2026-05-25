import os
from flask import Flask, session as flask_session
from .config import Config
from .extensions import db
from .routes.portal import bp as portal_bp
from .routes.admin import bp as admin_bp


def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    uploads_dir = os.path.join(app.root_path, 'static', 'uploads')
    os.makedirs(uploads_dir, exist_ok=True)

    db.init_app(app)
    app.register_blueprint(portal_bp)
    app.register_blueprint(admin_bp)

    with app.app_context():
        _seed_admin(app)

    @app.get('/health')
    def health():
        return {'status': 'ok'}

    @app.context_processor
    def inject_globals():
        from .models import SiteConfig
        logo_path = os.path.join(app.root_path, 'static', 'uploads', 'logo.png')
        has_logo = os.path.exists(logo_path)
        return {
            'custom_logo_url': '/static/uploads/logo.png' if has_logo else None,
            'portal_title': SiteConfig.get('portal_title', 'Portal Wi-Fi UniFi'),
            'portal_welcome': SiteConfig.get('portal_welcome', 'Preencha seus dados para liberar o acesso à internet.'),
            'portal_btn_color': SiteConfig.get('portal_btn_color', '#0f766e'),
        }

    return app


def _seed_admin(app):
    """Cria o usuario admin padrao se nao existir."""
    try:
        from .models import AdminUser
        if not AdminUser.query.filter_by(username=app.config['ADMIN_USERNAME']).first():
            user = AdminUser(username=app.config['ADMIN_USERNAME'])
            user.set_password(app.config['ADMIN_PASSWORD'])
            db.session.add(user)
            db.session.commit()
    except Exception:
        db.session.rollback()
