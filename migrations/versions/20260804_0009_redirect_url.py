"""URL de destino apos o acesso, por loja

Revision ID: 20260804_0009
Revises: 20260804_0008
Create Date: 2026-08-04
"""
from alembic import op
import sqlalchemy as sa

revision = '20260804_0009'
down_revision = '20260804_0008'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('stores') as batch_op:
        # Vazio mantem o comportamento padrao: devolver o visitante para a
        # pagina que ele tentava abrir quando foi interceptado pelo portal.
        batch_op.add_column(sa.Column('redirect_url', sa.String(512), nullable=True))


def downgrade():
    with op.batch_alter_table('stores') as batch_op:
        batch_op.drop_column('redirect_url')
