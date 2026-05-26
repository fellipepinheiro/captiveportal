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
    op.execute("ALTER TABLE visitors ADD COLUMN IF NOT EXISTS visit_count INT DEFAULT 0")
    op.execute("ALTER TABLE visitors ADD COLUMN IF NOT EXISTS last_seen DATETIME NULL")
    op.execute("ALTER TABLE visitors ADD COLUMN IF NOT EXISTS is_blocked TINYINT(1) DEFAULT 0")
    op.execute("ALTER TABLE visitors ADD COLUMN IF NOT EXISTS block_reason VARCHAR(200) NULL")

    # ── portal_sessions ───────────────────────────────────────────────────────
    op.execute("ALTER TABLE portal_sessions ADD COLUMN IF NOT EXISTS client_ip VARCHAR(45) NULL")
    op.execute("ALTER TABLE portal_sessions ADD COLUMN IF NOT EXISTS user_agent VARCHAR(300) NULL")
    op.execute("ALTER TABLE portal_sessions ADD COLUMN IF NOT EXISTS device_type VARCHAR(30) NULL")
    op.execute("ALTER TABLE portal_sessions ADD COLUMN IF NOT EXISTS os_hint VARCHAR(50) NULL")
    op.execute("ALTER TABLE portal_sessions ADD COLUMN IF NOT EXISTS duration_minutes INT DEFAULT 0")
    op.execute("ALTER TABLE portal_sessions ADD COLUMN IF NOT EXISTS bytes_up BIGINT DEFAULT 0")
    op.execute("ALTER TABLE portal_sessions ADD COLUMN IF NOT EXISTS bytes_down BIGINT DEFAULT 0")
    op.execute("ALTER TABLE portal_sessions ADD COLUMN IF NOT EXISTS expired_at DATETIME NULL")


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
