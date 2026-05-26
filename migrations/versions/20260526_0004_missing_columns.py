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
    # ── visitors ────────────────────────────────────────────────────────
    op.execute("ALTER TABLE visitors ADD COLUMN IF NOT EXISTS is_blocked TINYINT(1) NOT NULL DEFAULT 0")
    op.execute("ALTER TABLE visitors ADD COLUMN IF NOT EXISTS block_reason VARCHAR(255) NULL")
    op.execute("ALTER TABLE visitors ADD COLUMN IF NOT EXISTS visit_count INT NOT NULL DEFAULT 0")
    op.execute("ALTER TABLE visitors ADD COLUMN IF NOT EXISTS last_seen DATETIME NULL")
    op.execute("ALTER TABLE visitors ADD COLUMN IF NOT EXISTS terms_accepted_at DATETIME NULL")
    op.execute("ALTER TABLE visitors ADD COLUMN IF NOT EXISTS terms_version VARCHAR(20) NULL")
    op.execute("ALTER TABLE visitors ADD COLUMN IF NOT EXISTS marketing_optin TINYINT(1) NOT NULL DEFAULT 0")

    # ── portal_sessions ──────────────────────────────────────────────────
    op.execute("ALTER TABLE portal_sessions ADD COLUMN IF NOT EXISTS client_ip VARCHAR(45) NULL")
    op.execute("ALTER TABLE portal_sessions ADD COLUMN IF NOT EXISTS device_type VARCHAR(50) NULL")
    op.execute("ALTER TABLE portal_sessions ADD COLUMN IF NOT EXISTS os_hint VARCHAR(50) NULL")
    op.execute("ALTER TABLE portal_sessions ADD COLUMN IF NOT EXISTS expired_at DATETIME NULL")
    op.execute("ALTER TABLE portal_sessions ADD COLUMN IF NOT EXISTS duration_minutes INT NOT NULL DEFAULT 0")
    op.execute("ALTER TABLE portal_sessions ADD COLUMN IF NOT EXISTS bytes_up BIGINT NOT NULL DEFAULT 0")
    op.execute("ALTER TABLE portal_sessions ADD COLUMN IF NOT EXISTS bytes_down BIGINT NOT NULL DEFAULT 0")


def downgrade():
    with op.batch_alter_table('portal_sessions') as batch_op:
        for col in ('bytes_down', 'bytes_up', 'duration_minutes', 'expired_at',
                    'os_hint', 'device_type', 'client_ip'):
            try:
                batch_op.drop_column(col)
            except Exception:
                pass

    with op.batch_alter_table('visitors') as batch_op:
        for col in ('marketing_optin', 'terms_version', 'terms_accepted_at',
                    'last_seen', 'visit_count', 'block_reason', 'is_blocked'):
            try:
                batch_op.drop_column(col)
            except Exception:
                pass
