from flask import Flask
from app.extensions import db, migrate, csrf, limiter, login_manager
from app.config import config_by_name


def create_app(config_name: str = "development") -> Flask:
    app = Flask(__name__)
    app.config.from_object(config_by_name[config_name])

    db.init_app(app)
    migrate.init_app(app, db)
    csrf.init_app(app)
    limiter.init_app(app)
    login_manager.init_app(app)

    from app.routes.portal import bp as portal_bp
    from app.routes.admin import bp as admin_bp
    from app.routes.health import bp as health_bp

    app.register_blueprint(portal_bp)
    app.register_blueprint(admin_bp, url_prefix="/admin")
    app.register_blueprint(health_bp)

    return app
