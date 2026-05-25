from datetime import datetime, timezone
from app.extensions import db


class AuditLog(db.Model):
    __tablename__ = "audit_logs"

    id = db.Column(db.Integer, primary_key=True)
    event_type = db.Column(db.String(80), nullable=False, index=True)
    status = db.Column(db.String(20), nullable=False, index=True)
    payload = db.Column(db.Text, nullable=True)
    error_message = db.Column(db.Text, nullable=True)
    created_at = db.Column(
        db.DateTime, default=lambda: datetime.now(timezone.utc),
        nullable=False, index=True
    )
    # Colunas adicionadas na migration 0003
    correlation_id = db.Column(db.String(36), nullable=True, index=True)
    visitor_id = db.Column(
        db.Integer, db.ForeignKey("visitors.id", ondelete="SET NULL"), nullable=True, index=True
    )
    session_id = db.Column(
        db.Integer, db.ForeignKey("portal_sessions.id", ondelete="SET NULL"), nullable=True
    )
    actor = db.Column(db.String(100), nullable=True)
    ip_address = db.Column(db.String(45), nullable=True)
