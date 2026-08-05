"""Adiciona colunas de device/stats em visitors e portal_sessions

Revision ID: 0002v
Revises: 0002
Create Date: 2026-05-25

A versao original usava `ALTER TABLE ... ADD COLUMN IF NOT EXISTS`, que e
sintaxe **so do MariaDB**. No MySQL vira erro de sintaxe (1064) e a cadeia
de migrations para aqui — instalacao nova sobre MySQL, o banco do
docker-compose do projeto, nao chegava nem perto do fim. Sobre MariaDB
passava, e foi por isso que demorou a aparecer.

As colunas existentes agora sao consultadas pelo inspector e cada uma e
criada so se faltar: mesmo efeito, portatil entre MySQL, MariaDB e SQLite,
e continua seguro de re-executar.
"""
from alembic import op
import sqlalchemy as sa

revision = '0002v'
down_revision = '0002'
branch_labels = None
depends_on = None


#: (tabela, nome, fabrica_do_tipo, kwargs) — a coluna e construida na hora
#: porque um mesmo objeto Column nao pode ser reaproveitado entre chamadas.
COLUNAS = (
    ('visitors', 'visit_count',  lambda: sa.Integer(),  {'nullable': True, 'server_default': sa.text('0')}),
    ('visitors', 'last_seen',    lambda: sa.DateTime(), {'nullable': True}),
    ('visitors', 'is_blocked',   lambda: sa.Boolean(),  {'nullable': True, 'server_default': sa.text('0')}),
    ('visitors', 'block_reason', lambda: sa.String(200), {'nullable': True}),

    ('portal_sessions', 'client_ip',        lambda: sa.String(45),   {'nullable': True}),
    ('portal_sessions', 'user_agent',       lambda: sa.String(300),  {'nullable': True}),
    ('portal_sessions', 'device_type',      lambda: sa.String(30),   {'nullable': True}),
    ('portal_sessions', 'os_hint',          lambda: sa.String(50),   {'nullable': True}),
    ('portal_sessions', 'duration_minutes', lambda: sa.Integer(),    {'nullable': True, 'server_default': sa.text('0')}),
    ('portal_sessions', 'bytes_up',         lambda: sa.BigInteger(), {'nullable': True, 'server_default': sa.text('0')}),
    ('portal_sessions', 'bytes_down',       lambda: sa.BigInteger(), {'nullable': True, 'server_default': sa.text('0')}),
    ('portal_sessions', 'expired_at',       lambda: sa.DateTime(),   {'nullable': True}),
)


def _existentes(tabela: str) -> set:
    inspector = sa.inspect(op.get_bind())
    return {c['name'] for c in inspector.get_columns(tabela)}


def upgrade():
    cache = {}
    for tabela, nome, tipo, kwargs in COLUNAS:
        if tabela not in cache:
            cache[tabela] = _existentes(tabela)
        if nome in cache[tabela]:
            continue
        op.add_column(tabela, sa.Column(nome, tipo(), **kwargs))


def downgrade():
    for tabela in ('portal_sessions', 'visitors'):
        existentes = _existentes(tabela)
        alvos = [nome for t, nome, _, _ in COLUNAS if t == tabela and nome in existentes]
        if not alvos:
            continue
        with op.batch_alter_table(tabela) as batch_op:
            for nome in reversed(alvos):
                batch_op.drop_column(nome)
