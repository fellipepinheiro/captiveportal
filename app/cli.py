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
            try:
                for slug, resultado in sync_all().items():
                    click.echo(f"[{slug}] {resultado}")
            finally:
                # Encerra a transacao a cada ciclo. Sem isso a conexao fica
                # aberta durante todo o sleep, segurando metadata lock em
                # portal_sessions — e qualquer ALTER TABLE de migration fica
                # esperando indefinidamente pelo container de sincronizacao.
                db.session.remove()
            if not interval:
                break
            time.sleep(interval)

    @app.cli.command("cleanup-sessions")
    @click.option("--pending-ttl", default=30, show_default=True,
                  help="Minutos até remover sessões que nunca foram autorizadas.")
    @click.option("--expired-ttl", default=365, show_default=True,
                  help="Dias até purgar sessões encerradas. O Marco Civil (Art. 15) "
                       "exige guardar registros de conexão por 1 ano.")
    @with_appcontext
    def cleanup_sessions(pending_ttl, expired_ttl):
        """Remove sessões abandonadas e purga registros antigos de conexão."""
        from datetime import datetime, timezone, timedelta
        from app.models.portal_session import PortalSession

        cutoff_pending = datetime.now(timezone.utc) - timedelta(minutes=pending_ttl)
        cutoff_expired = datetime.now(timezone.utc) - timedelta(days=expired_ttl)

        # Abandonadas = abriram o portal e nunca concluiram a identificacao.
        # O criterio e authorized_at IS NULL, nao authorized == False: uma
        # sessao encerrada tambem fica com authorized False, e apagar essas
        # destruiria o historico de conexoes (o extrato do visitante e o
        # registro que o Marco Civil obriga a guardar).
        n_pending = PortalSession.query.filter(
            PortalSession.authorized_at.is_(None),
            PortalSession.created_at < cutoff_pending
        ).delete(synchronize_session=False)

        n_expired = PortalSession.query.filter(
            PortalSession.expired_at.isnot(None),
            PortalSession.expired_at < cutoff_expired
        ).delete(synchronize_session=False)

        db.session.commit()
        click.echo(f"Limpeza concluída: {n_pending} abandonadas removidas, "
                   f"{n_expired} registros antigos purgados.")
