from datetime import datetime, timezone
from app.extensions import db


class ConsentEvent(db.Model):
    """Historico de consentimento append-only (tabela consent_events — migration 0003)."""
    __tablename__ = "consent_events"

    id = db.Column(db.Integer, primary_key=True)
    visitor_id = db.Column(
        db.Integer, db.ForeignKey("visitors.id", ondelete="CASCADE"),
        nullable=False, index=True
    )
    event_type = db.Column(db.String(30), nullable=False)  # GRANT, REVOKE, UPDATE
    terms_version = db.Column(db.String(20), nullable=False)
    ip_address = db.Column(db.String(45), nullable=True)
    user_agent = db.Column(db.Text, nullable=True)
    channel = db.Column(db.String(50), nullable=True)
    marketing_opt_in = db.Column(db.Boolean, nullable=True)
    created_at = db.Column(
        db.DateTime, default=lambda: datetime.now(timezone.utc),
        nullable=False, index=True
    )

    visitor = db.relationship("Visitor", back_populates="consent_events")
