from datetime import datetime
from app.extensions import db


class AuditLog(db.Model):
    """
    Registro append-only de eventos de negócio e segurança.

    Regras:
    - NUNCA salvar CPF, e-mail, celular ou senha em texto puro no payload.
    - Usar correlation_id para ligar front, backend, UniFi e auditoria.
    - O campo actor segue o formato: "system", "admin:<id>" ou "visitor:<id>".
    - Eventos padronizados:
        CONSENT_ACCEPTED   CONSENT_REVOKED    GUEST_REGISTERED
        GUEST_AUTHORIZED   GUEST_DENIED       GUEST_BLOCKED
        UNIFI_API_ERROR    DATA_EXPORTED      DATA_DELETED
        DATA_ANONYMIZED    ADMIN_LOGIN        ADMIN_LOGOUT
        ADMIN_ACTION       SESSION_EXPIRED    RETENTION_JOB
    """
    __tablename__ = 'audit_logs'

    id = db.Column(db.Integer, primary_key=True)

    # Rastreabilidade
    correlation_id = db.Column(db.String(36), nullable=True, index=True)   # UUID da sessão portal
    visitor_id = db.Column(
        db.Integer, db.ForeignKey('visitors.id', ondelete='SET NULL'),
        nullable=True, index=True
    )
    session_id = db.Column(
        db.Integer, db.ForeignKey('portal_sessions.id', ondelete='SET NULL'),
        nullable=True, index=True
    )
    actor = db.Column(db.String(100), nullable=True)   # "system" | "admin:3" | "visitor:42"
    ip_address = db.Column(db.String(45), nullable=True)

    # Evento
    event_type = db.Column(db.String(80), nullable=False, index=True)
    status = db.Column(db.String(20), nullable=False, index=True)           # success | error | warning

    # Payload técnico — APENAS IDs internos, resultados e metadados sem PII
    payload = db.Column(db.Text, nullable=True)
    error_message = db.Column(db.Text, nullable=True)

    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, index=True)

    visitor = db.relationship('Visitor', foreign_keys=[visitor_id], lazy=True)

    def __repr__(self):
        return (
            f'<AuditLog id={self.id} event={self.event_type} '
            f'status={self.status} corr={self.correlation_id}>'
        )
