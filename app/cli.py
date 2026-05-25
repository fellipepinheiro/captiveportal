import click
from flask.cli import with_appcontext
from app.extensions import db
from app.models.admin_user import AdminUser


def register_commands(app):
    @app.cli.command("create-admin")
    @click.argument("email")
    @click.password_option()
    @with_appcontext
    def create_admin(email, password):
        """Cria um usuario administrador."""
        existing = AdminUser.query.filter_by(email=email).first()
        if existing:
            click.echo(f"Usuario {email} ja existe.")
            return
        user = AdminUser(email=email)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        click.echo(f"Admin {email} criado com sucesso!")
