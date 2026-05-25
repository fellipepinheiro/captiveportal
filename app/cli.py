"""Comandos CLI para gerenciamento do portal.

Uso:
    flask create-admin              # cria admin com usuario/senha do .env
    flask create-admin -u joao -p senha123
    flask list-admins
"""
import click
from flask.cli import with_appcontext
from app.extensions import db
from app.models.admin_user import AdminUser


@click.command('create-admin')
@click.option('--username', '-u', default=None, help='Nome de usuario (padrao: ADMIN_USERNAME do .env)')
@click.option('--password', '-p', default=None, help='Senha (padrao: ADMIN_PASSWORD do .env)')
@with_appcontext
def create_admin_cmd(username, password):
    """Cria ou atualiza o usuario administrador."""
    from flask import current_app
    username = username or current_app.config.get('ADMIN_USERNAME', 'admin')
    password = password or current_app.config.get('ADMIN_PASSWORD', 'admin123')

    if len(password) < 8:
        click.secho('Erro: a senha deve ter no minimo 8 caracteres.', fg='red')
        return

    user = AdminUser.query.filter_by(username=username).first()
    if user:
        user.set_password(password)
        user.is_active = True
        db.session.commit()
        click.secho(f'Senha do usuario "{username}" atualizada com sucesso.', fg='yellow')
    else:
        user = AdminUser(username=username)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        click.secho(f'Usuario admin "{username}" criado com sucesso!', fg='green')


@click.command('list-admins')
@with_appcontext
def list_admins_cmd():
    """Lista todos os usuarios administradores."""
    users = AdminUser.query.order_by(AdminUser.created_at).all()
    if not users:
        click.echo('Nenhum usuario administrador cadastrado.')
        return
    click.echo(f"{'ID':<5} {'Usuario':<25} {'Ativo':<8} {'Ultimo login'}")
    click.echo('-' * 60)
    for u in users:
        last = u.last_login.strftime('%d/%m/%Y %H:%M') if u.last_login else 'nunca'
        status = click.style('sim', fg='green') if u.is_active else click.style('nao', fg='red')
        click.echo(f"{u.id:<5} {u.username:<25} {status:<8} {last}")
