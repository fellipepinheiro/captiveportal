"""initial

Revision ID: 20260525_0001
Revises:
Create Date: 2026-05-25 11:57:00
"""
from alembic import op
import sqlalchemy as sa

revision = '20260525_0001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'audit_logs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('event_type', sa.String(length=80), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('payload', sa.Text(), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_audit_logs_event_type'), 'audit_logs', ['event_type'], unique=False)
    op.create_index(op.f('ix_audit_logs_status'), 'audit_logs', ['status'], unique=False)

    op.create_table(
        'visitors',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('full_name', sa.String(length=150), nullable=False),
        sa.Column('cpf', sa.String(length=11), nullable=False),
        sa.Column('email', sa.String(length=150), nullable=False),
        sa.Column('mobile', sa.String(length=20), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.Column('consent_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('cpf'),
    )
    op.create_index(op.f('ix_visitors_cpf'), 'visitors', ['cpf'], unique=True)
    op.create_index(op.f('ix_visitors_email'), 'visitors', ['email'], unique=False)
    op.create_index(op.f('ix_visitors_mobile'), 'visitors', ['mobile'], unique=False)

    op.create_table(
        'portal_sessions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('visitor_id', sa.Integer(), nullable=True),
        sa.Column('ap_mac', sa.String(length=17), nullable=True),
        sa.Column('client_mac', sa.String(length=17), nullable=False),
        sa.Column('ssid', sa.String(length=100), nullable=True),
        sa.Column('redirect_url', sa.Text(), nullable=True),
        sa.Column('query_token', sa.String(length=100), nullable=True),
        sa.Column('client_id', sa.String(length=64), nullable=True),
        sa.Column('authorized', sa.Boolean(), nullable=False),
        sa.Column('authorized_at', sa.DateTime(), nullable=True),
        sa.Column('expires_at', sa.DateTime(), nullable=True),
        sa.Column('ip_address', sa.String(length=45), nullable=True),
        sa.Column('user_agent', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['visitor_id'], ['visitors.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_portal_sessions_client_mac'), 'portal_sessions', ['client_mac'], unique=False)
    op.create_index(op.f('ix_portal_sessions_visitor_id'), 'portal_sessions', ['visitor_id'], unique=False)


def downgrade():
    op.drop_index(op.f('ix_portal_sessions_visitor_id'), table_name='portal_sessions')
    op.drop_index(op.f('ix_portal_sessions_client_mac'), table_name='portal_sessions')
    op.drop_table('portal_sessions')
    op.drop_index(op.f('ix_visitors_mobile'), table_name='visitors')
    op.drop_index(op.f('ix_visitors_email'), table_name='visitors')
    op.drop_index(op.f('ix_visitors_cpf'), table_name='visitors')
    op.drop_table('visitors')
    op.drop_index(op.f('ix_audit_logs_status'), table_name='audit_logs')
    op.drop_index(op.f('ix_audit_logs_event_type'), table_name='audit_logs')
    op.drop_table('audit_logs')
