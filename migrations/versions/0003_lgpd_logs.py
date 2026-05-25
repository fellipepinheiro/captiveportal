"""LGPD e logs — consent_events, data_subject_requests e novos campos

Revision ID: 0003
Revises: 0002
Create Date: 2026-05-25

Alterações:
  - visitors: consent_version, consent_ip, consent_channel, marketing_opt_in,
              data_deleted_at, anonymized_at, data_request_at
  - portal_sessions: site_id, correlation_id, consent_version
  - audit_logs: correlation_id, visitor_id, session_id, actor, ip_address
  - CREATE TABLE consent_events
  - CREATE TABLE data_subject_requests
"""
from alembic import op
import sqlalchemy as sa

revision = '0003'
down_revision = '0002'
branch_labels = None
depends_on = None


def upgrade():
    # ------------------------------------------------------------------
    # visitors — novos campos LGPD
    # ------------------------------------------------------------------
    op.add_column('visitors', sa.Column('consent_version', sa.String(20), nullable=True))
    op.add_column('visitors', sa.Column('consent_ip', sa.String(45), nullable=True))
    op.add_column('visitors', sa.Column('consent_channel', sa.String(50), nullable=True))
    op.add_column('visitors', sa.Column('marketing_opt_in',
                                        sa.Boolean, nullable=False,
                                        server_default=sa.false()))
    op.add_column('visitors', sa.Column('data_deleted_at', sa.DateTime, nullable=True))
    op.add_column('visitors', sa.Column('anonymized_at', sa.DateTime, nullable=True))
    op.add_column('visitors', sa.Column('data_request_at', sa.DateTime, nullable=True))

    # ------------------------------------------------------------------
    # portal_sessions — site_id UniFi, correlation_id e consent_version
    # ------------------------------------------------------------------
    op.add_column('portal_sessions', sa.Column('site_id', sa.String(64), nullable=True))
    op.add_column('portal_sessions', sa.Column('correlation_id', sa.String(36), nullable=True))
    op.add_column('portal_sessions', sa.Column('consent_version', sa.String(20), nullable=True))
    op.create_index('ix_portal_sessions_correlation_id',
                    'portal_sessions', ['correlation_id'])

    # ------------------------------------------------------------------
    # audit_logs — rastreabilidade completa
    # ------------------------------------------------------------------
    op.add_column('audit_logs', sa.Column('correlation_id', sa.String(36), nullable=True))
    op.add_column('audit_logs', sa.Column('visitor_id',
                                          sa.Integer,
                                          sa.ForeignKey('visitors.id', ondelete='SET NULL'),
                                          nullable=True))
    op.add_column('audit_logs', sa.Column('session_id',
                                          sa.Integer,
                                          sa.ForeignKey('portal_sessions.id', ondelete='SET NULL'),
                                          nullable=True))
    op.add_column('audit_logs', sa.Column('actor', sa.String(100), nullable=True))
    op.add_column('audit_logs', sa.Column('ip_address', sa.String(45), nullable=True))
    op.create_index('ix_audit_logs_correlation_id', 'audit_logs', ['correlation_id'])
    op.create_index('ix_audit_logs_visitor_id', 'audit_logs', ['visitor_id'])
    op.create_index('ix_audit_logs_created_at', 'audit_logs', ['created_at'])

    # ------------------------------------------------------------------
    # consent_events — histórico de consentimento (append-only)
    # ------------------------------------------------------------------
    op.create_table(
        'consent_events',
        sa.Column('id', sa.Integer, primary_key=True),
        sa.Column('visitor_id', sa.Integer,
                  sa.ForeignKey('visitors.id', ondelete='CASCADE'),
                  nullable=False),
        sa.Column('event_type', sa.String(30), nullable=False),
        sa.Column('terms_version', sa.String(20), nullable=False),
        sa.Column('ip_address', sa.String(45), nullable=True),
        sa.Column('user_agent', sa.Text, nullable=True),
        sa.Column('channel', sa.String(50), nullable=True),
        sa.Column('marketing_opt_in', sa.Boolean, nullable=True),
        sa.Column('created_at', sa.DateTime, nullable=False),
    )
    op.create_index('ix_consent_events_visitor_id', 'consent_events', ['visitor_id'])
    op.create_index('ix_consent_events_created_at', 'consent_events', ['created_at'])

    # ------------------------------------------------------------------
    # data_subject_requests — solicitações dos titulares (LGPD Art. 18)
    # ------------------------------------------------------------------
    op.create_table(
        'data_subject_requests',
        sa.Column('id', sa.Integer, primary_key=True),
        sa.Column('visitor_id', sa.Integer,
                  sa.ForeignKey('visitors.id', ondelete='SET NULL'),
                  nullable=True),
        sa.Column('request_type', sa.String(30), nullable=False),
        sa.Column('status', sa.String(20), nullable=False, server_default='PENDING'),
        sa.Column('notes', sa.Text, nullable=True),
        sa.Column('rejection_reason', sa.Text, nullable=True),
        sa.Column('channel', sa.String(50), nullable=True),
        sa.Column('requester_email', sa.String(150), nullable=True),
        sa.Column('requester_ip', sa.String(45), nullable=True),
        sa.Column('requested_at', sa.DateTime, nullable=False),
        sa.Column('resolved_at', sa.DateTime, nullable=True),
        sa.Column('resolved_by', sa.String(100), nullable=True),
    )
    op.create_index('ix_data_subject_requests_visitor_id',
                    'data_subject_requests', ['visitor_id'])
    op.create_index('ix_data_subject_requests_status',
                    'data_subject_requests', ['status'])
    op.create_index('ix_data_subject_requests_requested_at',
                    'data_subject_requests', ['requested_at'])


def downgrade():
    # data_subject_requests
    op.drop_index('ix_data_subject_requests_requested_at',
                  table_name='data_subject_requests')
    op.drop_index('ix_data_subject_requests_status',
                  table_name='data_subject_requests')
    op.drop_index('ix_data_subject_requests_visitor_id',
                  table_name='data_subject_requests')
    op.drop_table('data_subject_requests')

    # consent_events
    op.drop_index('ix_consent_events_created_at', table_name='consent_events')
    op.drop_index('ix_consent_events_visitor_id', table_name='consent_events')
    op.drop_table('consent_events')

    # audit_logs
    op.drop_index('ix_audit_logs_created_at', table_name='audit_logs')
    op.drop_index('ix_audit_logs_visitor_id', table_name='audit_logs')
    op.drop_index('ix_audit_logs_correlation_id', table_name='audit_logs')
    op.drop_column('audit_logs', 'ip_address')
    op.drop_column('audit_logs', 'actor')
    op.drop_column('audit_logs', 'session_id')
    op.drop_column('audit_logs', 'visitor_id')
    op.drop_column('audit_logs', 'correlation_id')

    # portal_sessions
    op.drop_index('ix_portal_sessions_correlation_id', table_name='portal_sessions')
    op.drop_column('portal_sessions', 'consent_version')
    op.drop_column('portal_sessions', 'correlation_id')
    op.drop_column('portal_sessions', 'site_id')

    # visitors
    op.drop_column('visitors', 'data_request_at')
    op.drop_column('visitors', 'anonymized_at')
    op.drop_column('visitors', 'data_deleted_at')
    op.drop_column('visitors', 'marketing_opt_in')
    op.drop_column('visitors', 'consent_channel')
    op.drop_column('visitors', 'consent_ip')
    op.drop_column('visitors', 'consent_version')
