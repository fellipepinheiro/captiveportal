"""Adiciona colunas de device/stats em visitors e portal_sessions

Revision ID: 0002v
Revises: 0002
Create Date: 2026-05-25
"""
from alembic import op
import sqlalchemy as sa

revision = '0002v'
down_revision = '0002'
branch_labels = None
depends_on = None


def upgrade():
    # ── visitors ──────────────────────────────────────────────────────────────
    with op.batch_alter_table('visitors') as batch_op:
        try:
            batch_op.add_column(sa.Column('visit_count', sa.Integer(), nullable=True, server_default='0'))
        except Exception:
            pass
        try:
            batch_op.add_column(sa.Column('last_seen', sa.DateTime(timezone=True), nullable=True))
        except Exception:
            pass
        try:
            batch_op.add_column(sa.Column('is_blocked', sa.Boolean(), nullable=True, server_default='0'))
        except Exception:
            pass
        try:
            batch_op.add_column(sa.Column('block_reason', sa.String(200), nullable=True))
        except Exception:
            pass

    # ── portal_sessions ───────────────────────────────────────────────────────
    with op.batch_alter_table('portal_sessions') as batch_op:
        try:
            batch_op.add_column(sa.Column('client_ip', sa.String(45), nullable=True))
        except Exception:
            pass
        try:
            batch_op.add_column(sa.Column('user_agent', sa.String(300), nullable=True))
        except Exception:
            pass
        try:
            batch_op.add_column(sa.Column('device_type', sa.String(30), nullable=True))
        except Exception:
            pass
        try:
            batch_op.add_column(sa.Column('os_hint', sa.String(50), nullable=True))
        except Exception:
            pass
        try:
            batch_op.add_column(sa.Column('duration_minutes', sa.Integer(), nullable=True, server_default='0'))
        except Exception:
            pass
        try:
            batch_op.add_column(sa.Column('bytes_up', sa.BigInteger(), nullable=True, server_default='0'))
        except Exception:
            pass
        try:
            batch_op.add_column(sa.Column('bytes_down', sa.BigInteger(), nullable=True, server_default='0'))
        except Exception:
            pass
        try:
            batch_op.add_column(sa.Column('expired_at', sa.DateTime(timezone=True), nullable=True))
        except Exception:
            pass


def downgrade():
    with op.batch_alter_table('visitors') as batch_op:
        for col in ('block_reason', 'is_blocked', 'last_seen', 'visit_count'):
            try:
                batch_op.drop_column(col)
            except Exception:
                pass

    with op.batch_alter_table('portal_sessions') as batch_op:
        for col in ('expired_at', 'bytes_down', 'bytes_up', 'duration_minutes',
                    'os_hint', 'device_type', 'user_agent', 'client_ip'):
            try:
                batch_op.drop_column(col)
            except Exception:
                pass
