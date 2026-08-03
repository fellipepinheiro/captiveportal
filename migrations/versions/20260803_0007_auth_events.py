"""idioma na sessao e indice para consultar tentativas de acesso

Revision ID: 20260803_0007
Revises: 20260803_0006
Create Date: 2026-08-03
"""
from alembic import op
import sqlalchemy as sa

revision = '20260803_0007'
down_revision = '20260803_0006'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('portal_sessions') as batch_op:
        # Accept-Language do navegador — perfil de audiencia
        batch_op.add_column(sa.Column('language', sa.String(20), nullable=True))

    # As telas de autenticacao e auditoria filtram por tipo de evento dentro
    # de um periodo; sem este indice a consulta varre a tabela inteira, que
    # cresce a cada acesso ao portal.
    op.create_index(
        'ix_audit_logs_event_created', 'audit_logs', ['event_type', 'created_at']
    )


def downgrade():
    op.drop_index('ix_audit_logs_event_created', table_name='audit_logs')
    with op.batch_alter_table('portal_sessions') as batch_op:
        batch_op.drop_column('language')
