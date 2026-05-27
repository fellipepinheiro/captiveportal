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

    @app.cli.command("cleanup-sessions")
    @click.option("--pending-ttl", default=30, show_default=True,
                  help="Minutos até expirar sessões nunca autorizadas.")
    @click.option("--expired-ttl", default=90, show_default=True,
                  help="Dias até purgar sessões já expiradas.")
    @with_appcontext
    def cleanup_sessions(pending_ttl, expired_ttl):
        """Remove sessões pendentes antigas e purga sessões expiradas há muito tempo."""
        from datetime import datetime, timezone, timedelta
        from app.models.portal_session import PortalSession

        cutoff_pending = datetime.now(timezone.utc) - timedelta(minutes=pending_ttl)
        cutoff_expired = datetime.now(timezone.utc) - timedelta(days=expired_ttl)

        n_pending = PortalSession.query.filter(
            PortalSession.authorized == False,
            PortalSession.created_at < cutoff_pending
        ).delete(synchronize_session=False)

        n_expired = PortalSession.query.filter(
            PortalSession.expired_at.isnot(None),
            PortalSession.expired_at < cutoff_expired
        ).delete(synchronize_session=False)

        db.session.commit()
        click.echo(f"Limpeza concluída: {n_pending} pendentes removidas, {n_expired} expiradas purgadas.")
