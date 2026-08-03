import os
from decouple import config as env


class BaseConfig:
    # ── Segurança básica ─────────────────────────────────────────────────
    SECRET_KEY = env("SECRET_KEY")                        # obrigatório — sem default inseguro
    WTF_CSRF_ENABLED     = True
    WTF_CSRF_TIME_LIMIT  = 3600                           # token CSRF expira em 1 h
    WTF_CSRF_SSL_STRICT  = False                          # relaxado para proxy reverso

    # ── Session ────────────────────────────────────────────────────
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    # Desativado em base: o portal captive é acessado via HTTP (IP interno)
    # antes do redirect HTTPS. Secure=True bloquearia o cookie nesse cenário.
    SESSION_COOKIE_SECURE   = False
    PERMANENT_SESSION_LIFETIME = 3600                     # sessão expira em 1 h

    # ── SQLAlchemy ────────────────────────────────────────────────
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {
        "pool_pre_ping": True,
        "pool_recycle": 300,
    }

    # ── Rate limiting ──────────────────────────────────────────────
    RATELIMIT_STORAGE_URI   = env("REDIS_URL", default="memory://")
    RATELIMIT_DEFAULT        = "200 per day;50 per hour"
    RATELIMIT_HEADERS_ENABLED = True

    # ── UniFi ─────────────────────────────────────────────────────
    UNIFI_BASE_URL        = env("UNIFI_BASE_URL", default="https://192.168.1.1")
    UNIFI_API_KEY         = env("UNIFI_API_KEY", default="")
    UNIFI_SITE_ID         = env("UNIFI_SITE_ID", default="default")
    UNIFI_SESSION_MINUTES = env("UNIFI_SESSION_MINUTES", default=480, cast=int)
    UNIFI_VERIFY_SSL      = env("UNIFI_VERIFY_SSL", default=False, cast=bool)

    # ── LGPD / Portal ───────────────────────────────────────────────
    FERNET_KEY          = env("FERNET_KEY", default="")
    TERMS_VERSION       = env("TERMS_VERSION", default="1.0")
    PRIVACY_POLICY_URL  = env("PRIVACY_POLICY_URL", default="/politica-de-privacidade")

    # ── Upload ─────────────────────────────────────────────────────
    MAX_CONTENT_LENGTH = env("MAX_CONTENT_LENGTH", default=20 * 1024 * 1024, cast=int)  # 20 MB default


class DevelopmentConfig(BaseConfig):
    DEBUG = True
    SQLALCHEMY_DATABASE_URI = env("DATABASE_URL", default="sqlite:///dev.db")
    WTF_CSRF_ENABLED        = False
    SESSION_COOKIE_SECURE   = False
    SECRET_KEY              = env("SECRET_KEY", default="dev-only-insecure-key-change-me")


class ProductionConfig(BaseConfig):
    DEBUG = False
    SQLALCHEMY_DATABASE_URI = env("DATABASE_URL")
    # SESSION_COOKIE_SECURE permanece False (herdado de BaseConfig):
    # o portal captive é acessado via HTTP puro pelo IP interno (redirect do UniFi).
    # O domínio guests.bntc.com.br usa HTTPS, mas o redirect inicial é HTTP.
    # Manter Secure=True bloquearia o cookie de sessão e quebraria o CSRF.
    SESSION_COOKIE_SAMESITE = "Lax"


class TestingConfig(BaseConfig):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    WTF_CSRF_ENABLED        = False
    SECRET_KEY              = "test-secret-key"


config_by_name = {
    "development": DevelopmentConfig,
    "production":  ProductionConfig,
    "testing":     TestingConfig,
}


def get_config(config_name=None):
    """Retorna a classe de configuração do ambiente atual. Padrão: production."""
    if not config_name:
        config_name = os.getenv("FLASK_ENV", "production")
    return config_by_name.get(config_name, ProductionConfig)
