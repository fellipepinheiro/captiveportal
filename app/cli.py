import time

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

    @app.cli.command("sync-sessions")
    @click.option("--interval", type=int, default=0,
                  help="Repete a cada N segundos. 0 (padrao) executa uma vez e sai.")
    @with_appcontext
    def sync_sessions(interval):
        """Encerra as sessoes de quem ja saiu do wifi.

        A API do UniFi nao avisa quando um cliente desconecta, entao o
        estado precisa ser conferido no controlador de tempos em tempos.
        """
        from app.services.session_sync import sync_all

        while True:
            for slug, resultado in sync_all().items():
                click.echo(f"[{slug}] {resultado}")
            if not interval:
                break
            time.sleep(interval)
