"""admin_user profile fields: full_name, phone, email, avatar_path

Revision ID: 20260527_0005
Revises: 20260526_0004_missing_columns
Create Date: 2026-05-27
"""
from alembic import op
import sqlalchemy as sa

revision = '20260527_0005'
down_revision = '20260526_0004_missing_columns'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('admin_users') as batch_op:
        batch_op.add_column(sa.Column('full_name',   sa.String(120), nullable=True))
        batch_op.add_column(sa.Column('phone',       sa.String(30),  nullable=True))
        batch_op.add_column(sa.Column('email',       sa.String(120), nullable=True))
        batch_op.add_column(sa.Column('avatar_path', sa.String(256), nullable=True))


def downgrade():
    with op.batch_alter_table('admin_users') as batch_op:
        batch_op.drop_column('avatar_path')
        batch_op.drop_column('email')
        batch_op.drop_column('phone')
        batch_op.drop_column('full_name')
