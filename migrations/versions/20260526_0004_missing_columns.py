"""add missing columns to visitors and portal_sessions

Revision ID: 20260526_0004
Revises: 0003
Create Date: 2026-05-26 08:00:00

Adds columns that exist in the SQLAlchemy models but were absent from
the DB after running migrations 0001→0003:

  visitors:
    - is_blocked        (BOOLEAN, NOT NULL, default False)
    - block_reason      (VARCHAR 255, nullable)
    - visit_count       (INTEGER, NOT NULL, default 0)
    - last_seen         (DATETIME, nullable)
    - terms_accepted_at (DATETIME, nullable)
    - terms_version     (VARCHAR 20, nullable)
    - marketing_optin   (BOOLEAN, NOT NULL, default False)

  portal_sessions:
    - client_ip         (VARCHAR 45, nullable)
    - device_type       (VARCHAR 50, nullable)
    - os_hint           (VARCHAR 50, nullable)
    - expired_at        (DATETIME, nullable)
    - duration_minutes  (INTEGER, NOT NULL, default 0)
    - bytes_up          (BIGINT, NOT NULL, default 0)
    - bytes_down        (BIGINT, NOT NULL, default 0)
"""
from alembic import op
import sqlalchemy as sa

revision = '20260526_0004'
down_revision = '0003'
branch_labels = None
depends_on = None


def upgrade():
    # ── visitors ────────────────────────────────────────────────────────────
    with op.batch_alter_table('visitors') as batch_op:
        batch_op.add_column(
            sa.Column('is_blocked', sa.Boolean(), nullable=False,
                      server_default=sa.text('0'))
        )
        batch_op.add_column(
            sa.Column('block_reason', sa.String(length=255), nullable=True)
        )
        batch_op.add_column(
            sa.Column('visit_count', sa.Integer(), nullable=False,
                      server_default=sa.text('0'))
        )
        batch_op.add_column(
            sa.Column('last_seen', sa.DateTime(), nullable=True)
        )
        batch_op.add_column(
            sa.Column('terms_accepted_at', sa.DateTime(), nullable=True)
        )
        batch_op.add_column(
            sa.Column('terms_version', sa.String(length=20), nullable=True)
        )
        batch_op.add_column(
            sa.Column('marketing_optin', sa.Boolean(), nullable=False,
                      server_default=sa.text('0'))
        )

    # ── portal_sessions ──────────────────────────────────────────────────────
    with op.batch_alter_table('portal_sessions') as batch_op:
        batch_op.add_column(
            sa.Column('client_ip', sa.String(length=45), nullable=True)
        )
        batch_op.add_column(
            sa.Column('device_type', sa.String(length=50), nullable=True)
        )
        batch_op.add_column(
            sa.Column('os_hint', sa.String(length=50), nullable=True)
        )
        batch_op.add_column(
            sa.Column('expired_at', sa.DateTime(), nullable=True)
        )
        batch_op.add_column(
            sa.Column('duration_minutes', sa.Integer(), nullable=False,
                      server_default=sa.text('0'))
        )
        batch_op.add_column(
            sa.Column('bytes_up', sa.BigInteger(), nullable=False,
                      server_default=sa.text('0'))
        )
        batch_op.add_column(
            sa.Column('bytes_down', sa.BigInteger(), nullable=False,
                      server_default=sa.text('0'))
        )


def downgrade():
    with op.batch_alter_table('portal_sessions') as batch_op:
        batch_op.drop_column('bytes_down')
        batch_op.drop_column('bytes_up')
        batch_op.drop_column('duration_minutes')
        batch_op.drop_column('expired_at')
        batch_op.drop_column('os_hint')
        batch_op.drop_column('device_type')
        batch_op.drop_column('client_ip')

    with op.batch_alter_table('visitors') as batch_op:
        batch_op.drop_column('marketing_optin')
        batch_op.drop_column('terms_version')
        batch_op.drop_column('terms_accepted_at')
        batch_op.drop_column('last_seen')
        batch_op.drop_column('visit_count')
        batch_op.drop_column('block_reason')
        batch_op.drop_column('is_blocked')
