from flask import Flask
from werkzeug.middleware.proxy_fix import ProxyFix
from app.extensions import db, migrate, csrf, limiter, login_manager


def create_app(config_name=None):
    app = Flask(__name__, template_folder='templates')

    # Carrega configuracoes
    from app.config import get_config
    app.config.from_object(get_config(config_name))

    # ProxyFix: extrai X-Real-IP / X-Forwarded-For enviados pelo nginx.
    #
    # So faz sentido atras de um proxy de confianca. Com o portal publicado
    # direto (o override local faz isso na porta 80), qualquer um pode mandar
    # X-Forwarded-For e escolher que IP aparece no registro — inclusive nos
    # logs de conexao que o Marco Civil manda guardar. TRUST_PROXY_HOPS=0
    # desliga; o padrao 1 mantem o comportamento de producao, onde o nginx
    # sobrescreve o header.
    import os
    saltos = int(os.getenv("TRUST_PROXY_HOPS", "1"))
    if saltos > 0:
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=saltos, x_proto=saltos,
                                x_host=saltos, x_prefix=saltos)

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

    # Filtros de exibicao: CPF e telefone sao gravados so com digitos
    from app.services.validator import format_cpf, format_phone
    app.jinja_env.filters['cpf'] = format_cpf
    app.jinja_env.filters['telefone'] = format_phone

    # Datas sao gravadas em UTC — converte para o fuso local ao exibir.
    # 'localtime' e mantido como alias (mesma assinatura) porque varios
    # templates ja o usam; a diferenca e que o fuso agora vem de TIMEZONE
    # em vez de ficar fixo em America/Sao_Paulo.
    from app.services.datetime_fmt import fmt_datetime, fmt_short, fmt_date
    app.jinja_env.filters['datahora'] = fmt_datetime
    app.jinja_env.filters['datahora_curta'] = fmt_short
    app.jinja_env.filters['data'] = fmt_date
    app.jinja_env.filters['localtime'] = fmt_datetime

    # Context processor: injeta variaveis do portal em todos os templates
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
