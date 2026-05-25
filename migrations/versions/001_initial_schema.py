"""initial schema

Revision ID: 001_initial
Revises:
Create Date: 2026-05-25
"""
from alembic import op
import sqlalchemy as sa

revision = "001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "visitors",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("email", sa.String(180), nullable=False, index=True),
        sa.Column("phone", sa.String(20), nullable=False, index=True),
        sa.Column("cpf_hash", sa.String(64), unique=True, nullable=False),
        sa.Column("active", sa.Boolean, default=True, nullable=False),
        sa.Column("created_at", sa.DateTime, nullable=True),
        sa.Column("updated_at", sa.DateTime, nullable=True),
    )

    op.create_table(
        "portal_sessions",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("visitor_id", sa.Integer, sa.ForeignKey("visitors.id"), nullable=True, index=True),
        sa.Column("mac_client", sa.String(17), nullable=False, index=True),
        sa.Column("mac_ap", sa.String(17), nullable=True),
        sa.Column("ssid", sa.String(64), nullable=True),
        sa.Column("redirect_url", sa.String(512), nullable=True),
        sa.Column("unifi_site_id", sa.String(64), nullable=True),
        sa.Column("unifi_client_id", sa.String(64), nullable=True),
        sa.Column("ip_address", sa.String(45), nullable=True),
        sa.Column("user_agent", sa.String(512), nullable=True),
        sa.Column("authorized", sa.Boolean, default=False, nullable=False),
        sa.Column("authorized_at", sa.DateTime, nullable=True),
        sa.Column("expires_at", sa.DateTime, nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=True),
    )

    op.create_table(
        "consent_records",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("visitor_id", sa.Integer, sa.ForeignKey("visitors.id"), nullable=False),
        sa.Column("terms_version", sa.String(20), nullable=False),
        sa.Column("marketing_optin", sa.Boolean, default=False, nullable=False),
        sa.Column("ip_address", sa.String(45), nullable=True),
        sa.Column("user_agent", sa.String(512), nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=True),
    )

    op.create_table(
        "admin_users",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("email", sa.String(180), unique=True, nullable=False),
        sa.Column("password_hash", sa.String(128), nullable=False),
        sa.Column("active", sa.Boolean, default=True),
    )


def downgrade() -> None:
    op.drop_table("admin_users")
    op.drop_table("consent_records")
    op.drop_table("portal_sessions")
    op.drop_table("visitors")
