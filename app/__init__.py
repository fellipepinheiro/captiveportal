from flask import Flask
from werkzeug.middleware.proxy_fix import ProxyFix
from app.extensions import db, migrate, csrf, limiter, login_manager


def create_app(config_name=None):
    app = Flask(__name__, template_folder='templates')

    # Carrega configuracoes
    from app.config import get_config
    app.config.from_object(get_config(config_name))

    # ProxyFix: extrai X-Real-IP / X-Forwarded-For enviados pelo nginx-proxy.
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)

    # Inicializa extensoes
    db.init_app(app)
    migrate.init_app(app, db)
    csrf.init_app(app)
    limiter.init_app(app)
    login_manager.init_app(app)

    # Headers de seguranca HTTP
    from app.security import register_security_headers
    register_security_headers(app)

    # Registra blueprints
    from app.routes.portal import bp as portal_bp
    from app.routes.admin import bp as admin_bp
    from app.routes.health import bp as health_bp
    app.register_blueprint(portal_bp)
    app.register_blueprint(admin_bp, url_prefix='/admin')
    app.register_blueprint(health_bp)

    # Filtro Jinja2: converte datetime UTC -> America/Sao_Paulo
    import zoneinfo
    from datetime import timezone

    _TZ_BR = zoneinfo.ZoneInfo("America/Sao_Paulo")

    @app.template_filter("localtime")
    def localtime_filter(dt, fmt="%d/%m/%Y %H:%M"):
        """Converte um datetime UTC (naive ou aware) para America/Sao_Paulo."""
        if dt is None:
            return "—"
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(_TZ_BR).strftime(fmt)

    # Context processor
    @app.context_processor
    def inject_portal_vars():
        try:
            from app.models.site_config import SiteConfig
            return dict(
                portal_title=SiteConfig.get('portal_title') or 'Wi-Fi Visitantes',
                portal_welcome=SiteConfig.get('portal_welcome') or 'Identifique-se para acessar a internet.',
                portal_bg_from=SiteConfig.get('portal_bg_from') or '#0f172a',
                portal_bg_via=SiteConfig.get('portal_bg_via') or '#1e1b4b',
                portal_bg_to=SiteConfig.get('portal_bg_to') or '#0f172a',
                portal_accent=SiteConfig.get('portal_accent') or '#2dd4bf',
                portal_btn_color=SiteConfig.get('portal_btn_color') or '#0d9488',
                portal_btn_hover=SiteConfig.get('portal_btn_hover') or '#0f766e',
                custom_logo_url=SiteConfig.get('custom_logo_url') or '',
                logo_title=SiteConfig.get('logo_title') or '',
                ssid='',
                redirect_url='',
            )
        except Exception:
            return dict(
                portal_title='Wi-Fi Visitantes',
                portal_welcome='Identifique-se para acessar a internet.',
                portal_bg_from='#0f172a',
                portal_bg_via='#1e1b4b',
                portal_bg_to='#0f172a',
                portal_accent='#2dd4bf',
                portal_btn_color='#0d9488',
                portal_btn_hover='#0f766e',
                custom_logo_url='',
                logo_title='',
                ssid='',
                redirect_url='',
            )

    # Registra CLI commands
    from app.cli import register_commands
    register_commands(app)

    return app
