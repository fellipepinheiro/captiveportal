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

    @app.cli.command("guests")
    @click.option("--store", "slug", default=None,
                  help="Slug da loja. Sem isso, percorre todas as lojas ativas.")
    @click.option("--revoke", "alvo", default=None, metavar="MAC",
                  help="Derruba o acesso apenas deste MAC.")
    @click.option("--all", "todos", is_flag=True,
                  help="Derruba o acesso de todos os visitantes autorizados.")
    @with_appcontext
    def guests(slug, alvo, todos):
        """Lista ou derruba os visitantes com acesso liberado no controlador.

        Serve para voltar a ver a tela de login num aparelho de teste: o
        UniFi nao manda ao portal quem ja tem autorizacao valida, e ela dura
        horas. Esquecer a rede nao adianta — o celular costuma manter o
        mesmo MAC privado e reencontra a propria autorizacao.
        """
        from app.models import Store
        from app.services.unifi_api import get_unifi_for_store, UnifiAPIError

        lojas = ([Store.query.filter_by(slug=slug).first()] if slug
                 else Store.query.filter_by(is_active=True).all())
        if not any(lojas):
            click.echo(f"Loja '{slug}' nao encontrada." if slug else "Nenhuma loja ativa.")
            return

        total = 0
        for store in filter(None, lojas):
            try:
                unifi = get_unifi_for_store(store)
            except Exception as exc:
                click.echo(f"[{store.slug}] falha ao montar o cliente UniFi: {exc}")
                continue

            if unifi.mock_involuntario:
                click.echo(f"[{store.slug}] sem endereco de controlador — pulando.")
                continue

            site = store.unifi_site_id or "default"
            try:
                clientes = unifi.list_clients(site)
            except UnifiAPIError as exc:
                click.echo(f"[{store.slug}] falha ao listar clientes: {exc}")
                continue

            # O tipo GUEST sozinho nao basta: o dispositivo mantem esse tipo
            # depois de revogado. O que indica acesso liberado e authorized.
            autorizados = [c for c in clientes
                           if (c.get("access") or {}).get("authorized") is True]
            if alvo:
                autorizados = [c for c in autorizados
                               if (c.get("macAddress") or "").lower() == alvo.lower()]

            total += len(autorizados)
            if not autorizados:
                click.echo(f"[{store.slug}] nenhum visitante autorizado"
                           + (f" com o MAC {alvo}." if alvo else "."))
                continue

            for c in autorizados:
                mac = c.get("macAddress")
                nome = c.get("name") or ""
                if not (todos or alvo):
                    click.echo(f"[{store.slug}] {mac}  {nome}")
                    continue
                try:
                    unifi.revoke_guest(site, c["id"])
                    click.echo(f"[{store.slug}] {mac}  {nome} -> derrubado")
                except UnifiAPIError as exc:
                    click.echo(f"[{store.slug}] {mac}  {nome} -> FALHOU: {exc}")

        if total and not (todos or alvo):
            click.echo(f"\n{total} autorizado(s). Use --all para derrubar todos, "
                       f"ou --revoke <mac> para um so.")

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
    @click.option("--interval", type=int, default=0,
                  help="Repete a cada N segundos. 0 (padrao) executa uma vez e sai.")
    @with_appcontext
    def cleanup_sessions(pending_ttl, expired_ttl, interval):
        """Remove sessões abandonadas e purga registros antigos de conexão."""
        from datetime import datetime, timezone, timedelta
        from app.models.portal_session import PortalSession

        while True:
            try:
                cutoff_pending = datetime.now(timezone.utc) - timedelta(minutes=pending_ttl)
                cutoff_expired = datetime.now(timezone.utc) - timedelta(days=expired_ttl)

                # Abandonadas = abriram o portal e nunca concluiram a identificacao.
                # O criterio e authorized_at IS NULL, nao authorized == False: uma
                # sessao encerrada tambem fica com authorized False, e apagar essas
                # destruiria o historico de conexoes (o extrato do visitante e o
                # registro que o Marco Civil obriga a guardar).
                #
                # O corte por created_at protege quem ainda esta preenchendo o
                # formulario: a sessao e o que liga o navegador ao MAC do
                # aparelho, e apagar a de alguem no meio do cadastro derruba
                # a pessoa com "sessao expirada".
                n_pending = PortalSession.query.filter(
                    PortalSession.authorized_at.is_(None),
                    PortalSession.created_at < cutoff_pending
                ).delete(synchronize_session=False)

                n_expired = PortalSession.query.filter(
                    PortalSession.expired_at.isnot(None),
                    PortalSession.expired_at < cutoff_expired
                ).delete(synchronize_session=False)

                db.session.commit()
                if n_pending or n_expired or not interval:
                    click.echo(f"Limpeza concluída: {n_pending} abandonadas removidas, "
                               f"{n_expired} registros antigos purgados.")
            finally:
                # Fecha a transacao a cada ciclo: mante-la aberta durante o
                # sleep segura metadata lock em portal_sessions e trava
                # qualquer ALTER TABLE de migration. Mesmo motivo do
                # sync-sessions acima.
                db.session.remove()

            if not interval:
                break
            time.sleep(interval)
