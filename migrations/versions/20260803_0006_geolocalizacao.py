"""geolocalizacao: coordenadas na sessao e endereco/coordenadas da loja

Revision ID: 20260803_0006
Revises: 20260801_0005
Create Date: 2026-08-03
"""
from alembic import op
import sqlalchemy as sa

revision = '20260803_0006'
down_revision = '20260801_0005'
branch_labels = None
depends_on = None


def upgrade():
    # A posicao pertence a sessao, nao ao visitante: a mesma pessoa acessa
    # de lugares diferentes a cada visita, e sobrescrever no cadastro
    # apagaria justamente o historico que interessa para analise de origem.
    with op.batch_alter_table('portal_sessions') as batch_op:
        batch_op.add_column(sa.Column('latitude', sa.Numeric(10, 7), nullable=True))
        batch_op.add_column(sa.Column('longitude', sa.Numeric(10, 7), nullable=True))
        # Raio de incerteza em metros que o navegador reporta. Guardado para
        # permitir descartar leituras ruins (wifi/torre ao inves de GPS).
        batch_op.add_column(sa.Column('location_accuracy', sa.Integer, nullable=True))
        batch_op.add_column(sa.Column('location_at', sa.DateTime(timezone=True), nullable=True))

    with op.batch_alter_table('stores') as batch_op:
        batch_op.add_column(sa.Column('address', sa.String(255), nullable=True))
        batch_op.add_column(sa.Column('latitude', sa.Numeric(10, 7), nullable=True))
        batch_op.add_column(sa.Column('longitude', sa.Numeric(10, 7), nullable=True))


def downgrade():
    with op.batch_alter_table('stores') as batch_op:
        batch_op.drop_column('longitude')
        batch_op.drop_column('latitude')
        batch_op.drop_column('address')

    with op.batch_alter_table('portal_sessions') as batch_op:
        batch_op.drop_column('location_at')
        batch_op.drop_column('location_accuracy')
        batch_op.drop_column('longitude')
        batch_op.drop_column('latitude')
