"""admin_users e site_config

Revision ID: 0002
Revises: 0001
Create Date: 2026-05-25
"""
from alembic import op
import sqlalchemy as sa

revision = '0002'
down_revision = '0001'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'admin_users',
        sa.Column('id', sa.Integer, primary_key=True),
        sa.Column('username', sa.String(80), unique=True, nullable=False),
        sa.Column('password_hash', sa.String(256), nullable=False),
        sa.Column('is_active', sa.Boolean, default=True, nullable=False),
        sa.Column('created_at', sa.DateTime, nullable=False),
        sa.Column('last_login', sa.DateTime, nullable=True),
    )
    op.create_index('ix_admin_users_username', 'admin_users', ['username'])

    op.create_table(
        'site_config',
        sa.Column('id', sa.Integer, primary_key=True),
        sa.Column('key', sa.String(80), unique=True, nullable=False),
        sa.Column('value', sa.Text, nullable=True),
        sa.Column('updated_at', sa.DateTime, nullable=True),
    )
    op.create_index('ix_site_config_key', 'site_config', ['key'])


def downgrade():
    op.drop_table('site_config')
    op.drop_table('admin_users')
