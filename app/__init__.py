import os
from flask import Flask
from .config import Config
from .extensions import db
from .routes.portal import bp as portal_bp
from .routes.admin import bp as admin_bp


def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    # Garante diretorio de uploads
    uploads_dir = os.path.join(app.root_path, 'static', 'uploads')
    os.makedirs(uploads_dir, exist_ok=True)

    db.init_app(app)
    app.register_blueprint(portal_bp)
    app.register_blueprint(admin_bp)

    @app.get('/health')
    def health():
        return {'status': 'ok'}

    @app.context_processor
    def inject_portal_config():
        """Injeta logo e configuracoes de aparencia em todos os templates."""
        from .models.site_config import SiteConfig
        logo_path = os.path.join(app.root_path, 'static', 'uploads', 'logo.png')
        has_logo = os.path.exists(logo_path)
        try:
            portal_title = SiteConfig.get('portal_title', 'Portal Wi-Fi UniFi')
            portal_welcome = SiteConfig.get('portal_welcome', 'Preencha seus dados para liberar o acesso à internet.')
            portal_btn_color = SiteConfig.get('portal_btn_color', '#0f766e')
            portal_bg_from = SiteConfig.get('portal_bg_from', '#020617')
            portal_bg_via = SiteConfig.get('portal_bg_via', '#0f172a')
            portal_bg_to = SiteConfig.get('portal_bg_to', '#1e293b')
            portal_accent = SiteConfig.get('portal_accent', '#2dd4bf')
        except Exception:
            portal_title = 'Portal Wi-Fi UniFi'
            portal_welcome = 'Preencha seus dados para liberar o acesso à internet.'
            portal_btn_color = '#0f766e'
            portal_bg_from = '#020617'
            portal_bg_via = '#0f172a'
            portal_bg_to = '#1e293b'
            portal_accent = '#2dd4bf'
        return {
            'custom_logo_url': '/static/uploads/logo.png' if has_logo else None,
            'portal_title': portal_title,
            'portal_welcome': portal_welcome,
            'portal_btn_color': portal_btn_color,
            'portal_bg_from': portal_bg_from,
            'portal_bg_via': portal_bg_via,
            'portal_bg_to': portal_bg_to,
            'portal_accent': portal_accent,
        }

    return app
