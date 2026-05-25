import click
from flask.cli import with_appcontext
from app.extensions import db
from app.models.admin_user import AdminUser


def register_commands(app):
    @app.cli.command("create-admin")
    @click.argument("username")
    @click.password_option()
    @with_appcontext
    def create_admin(username, password):
        """Cria um usuario administrador."""
        existing = AdminUser.query.filter_by(username=username).first()
        if existing:
            click.echo(f"Usuario '{username}' ja existe.")
            return
        user = AdminUser(username=username)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        click.echo(f"Admin '{username}' criado com sucesso!")
