"""stores (multi-loja / UDM Pro por loja) + email do visitante opcional

Revision ID: 20260801_0005
Revises: 20260527_0005
Create Date: 2026-08-01
"""
import os
from datetime import datetime, timezone

from alembic import op
import sqlalchemy as sa

revision = '20260801_0005'
down_revision = '20260527_0005'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'stores',
        sa.Column('id', sa.Integer, primary_key=True),
        sa.Column('name', sa.String(120), nullable=False),
        sa.Column('slug', sa.String(80), unique=True, nullable=False),
        sa.Column('unifi_base_url', sa.String(255), nullable=True),
        sa.Column('unifi_api_key', sa.String(255), nullable=True),
        sa.Column('unifi_site_id', sa.String(80), nullable=True, server_default='default'),
        sa.Column('unifi_verify_ssl', sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column('session_minutes', sa.Integer, nullable=True),
        sa.Column('is_active', sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index('ix_stores_slug', 'stores', ['slug'])
    op.create_index('ix_stores_is_active', 'stores', ['is_active'])

    # batch_alter_table: no-op wrapper no MySQL, mas necessário no SQLite
    # (que não suporta ALTER TABLE ... ADD CONSTRAINT diretamente).
    with op.batch_alter_table('portal_sessions') as batch_op:
        batch_op.add_column(sa.Column('store_id', sa.Integer, nullable=True))
        batch_op.create_index('ix_portal_sessions_store_id', ['store_id'])
        batch_op.create_foreign_key(
            'fk_portal_sessions_store_id', 'stores', ['store_id'], ['id'],
        )

    # Semeia a loja 'default' com as credenciais UniFi já em uso hoje (.env),
    # para que instalações existentes continuem funcionando sem reconfiguração.
    now = datetime.now(timezone.utc)
    stores_table = sa.table(
        'stores',
        sa.column('name', sa.String),
        sa.column('slug', sa.String),
        sa.column('unifi_base_url', sa.String),
        sa.column('unifi_api_key', sa.String),
        sa.column('unifi_site_id', sa.String),
        sa.column('unifi_verify_ssl', sa.Boolean),
        sa.column('is_active', sa.Boolean),
        sa.column('created_at', sa.DateTime),
        sa.column('updated_at', sa.DateTime),
    )
    op.bulk_insert(stores_table, [{
        'name':             'Loja Padrão',
        'slug':             'default',
        'unifi_base_url':   os.environ.get('UNIFI_BASE_URL', 'https://192.168.1.1'),
        'unifi_api_key':    os.environ.get('UNIFI_API_KEY', ''),
        'unifi_site_id':    os.environ.get('UNIFI_SITE_ID', 'default'),
        'unifi_verify_ssl': os.environ.get('UNIFI_VERIFY_SSL', 'false').lower() == 'true',
        'is_active':        True,
        'created_at':       now,
        'updated_at':       now,
    }])

    # Login passa a ser por CPF+celular; e-mail vira campo opcional no cadastro.
    with op.batch_alter_table('visitors') as batch_op:
        batch_op.alter_column(
            'email', existing_type=sa.String(150), nullable=True,
        )

    # CPF vira chave de identificação — normaliza registros antigos que possam
    # ter sido gravados com máscara para o formato só-dígitos da coluna.
    op.execute(
        "UPDATE visitors SET cpf = REPLACE(REPLACE(cpf, '.', ''), '-', '') "
        "WHERE cpf LIKE '%.%' OR cpf LIKE '%-%'"
    )


def downgrade():
    with op.batch_alter_table('visitors') as batch_op:
        batch_op.alter_column(
            'email', existing_type=sa.String(150), nullable=False,
        )

    with op.batch_alter_table('portal_sessions') as batch_op:
        batch_op.drop_constraint('fk_portal_sessions_store_id', type_='foreignkey')
        batch_op.drop_index('ix_portal_sessions_store_id')
        batch_op.drop_column('store_id')

    op.drop_index('ix_stores_is_active', table_name='stores')
    op.drop_index('ix_stores_slug', table_name='stores')
    op.drop_table('stores')
