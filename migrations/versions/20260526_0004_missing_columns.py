"""add missing columns to visitors and portal_sessions

Revision ID: 20260526_0004
Revises: 0003
Create Date: 2026-05-26 08:00:00

Acrescenta colunas que existem nos modelos mas nao foram criadas pelas
migrations 0001->0003.

A versao original usava `ALTER TABLE ... ADD COLUMN IF NOT EXISTS`, que e
sintaxe **so do MariaDB**. No MySQL isso e erro de sintaxe (1064), a
migration falha e a cadeia inteira para aqui — ou seja, instalacao nova
sobre MySQL, que e justamente o banco do docker-compose do projeto, nunca
chegava ao fim. Instalacao sobre MariaDB passava, e foi por isso que o
problema demorou a aparecer.

Agora as colunas existentes sao consultadas pelo inspector e cada uma e
criada so se faltar. Funciona igual em MySQL, MariaDB e SQLite, e continua
seguro de re-executar.
"""
from alembic import op
import sqlalchemy as sa

revision = '20260526_0004'
down_revision = '0003'
branch_labels = None
depends_on = None


#: (tabela, nome, fabrica_do_tipo, kwargs) — a coluna e construida na hora
#: porque um mesmo objeto Column nao pode ser reaproveitado entre chamadas.
COLUNAS = (
    ('visitors', 'is_blocked',        lambda: sa.Boolean(),      {'nullable': False, 'server_default': sa.text('0')}),
    ('visitors', 'block_reason',      lambda: sa.String(255),    {'nullable': True}),
    ('visitors', 'visit_count',       lambda: sa.Integer(),      {'nullable': False, 'server_default': sa.text('0')}),
    ('visitors', 'last_seen',         lambda: sa.DateTime(),     {'nullable': True}),
    ('visitors', 'terms_accepted_at', lambda: sa.DateTime(),     {'nullable': True}),
    ('visitors', 'terms_version',     lambda: sa.String(20),     {'nullable': True}),
    ('visitors', 'marketing_optin',   lambda: sa.Boolean(),      {'nullable': False, 'server_default': sa.text('0')}),

    ('portal_sessions', 'client_ip',        lambda: sa.String(45),  {'nullable': True}),
    ('portal_sessions', 'device_type',      lambda: sa.String(50),  {'nullable': True}),
    ('portal_sessions', 'os_hint',          lambda: sa.String(50),  {'nullable': True}),
    ('portal_sessions', 'expired_at',       lambda: sa.DateTime(),  {'nullable': True}),
    ('portal_sessions', 'duration_minutes', lambda: sa.Integer(),   {'nullable': False, 'server_default': sa.text('0')}),
    ('portal_sessions', 'bytes_up',         lambda: sa.BigInteger(),{'nullable': False, 'server_default': sa.text('0')}),
    ('portal_sessions', 'bytes_down',       lambda: sa.BigInteger(),{'nullable': False, 'server_default': sa.text('0')}),
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
