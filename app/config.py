from decouple import config as env


class BaseConfig:
    SECRET_KEY = env("SECRET_KEY", default="dev-secret-change-me")
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    WTF_CSRF_ENABLED = True
    RATELIMIT_STORAGE_URI = env("REDIS_URL", default="memory://")

    UNIFI_BASE_URL = env("UNIFI_BASE_URL", default="https://192.168.1.1")
    UNIFI_API_KEY = env("UNIFI_API_KEY", default="")
    UNIFI_SITE_ID = env("UNIFI_SITE_ID", default="default")
    UNIFI_SESSION_MINUTES = env("UNIFI_SESSION_MINUTES", default=480, cast=int)
    UNIFI_VERIFY_SSL = env("UNIFI_VERIFY_SSL", default=False, cast=bool)

    FERNET_KEY = env("FERNET_KEY", default="")
    TERMS_VERSION = env("TERMS_VERSION", default="1.0")
    PRIVACY_POLICY_URL = env("PRIVACY_POLICY_URL", default="/politica-de-privacidade")


class DevelopmentConfig(BaseConfig):
    DEBUG = True
    SQLALCHEMY_DATABASE_URI = env("DATABASE_URL", default="sqlite:///dev.db")
    WTF_CSRF_ENABLED = False


class ProductionConfig(BaseConfig):
    DEBUG = False
    SQLALCHEMY_DATABASE_URI = env("DATABASE_URL")
    SESSION_COOKIE_SECURE = True
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"


class TestingConfig(BaseConfig):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    WTF_CSRF_ENABLED = False


config_by_name = {
    "development": DevelopmentConfig,
    "production": ProductionConfig,
    "testing": TestingConfig,
}
