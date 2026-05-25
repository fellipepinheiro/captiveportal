from datetime import datetime, timezone
from app.extensions import db


class PortalSession(db.Model):
    __tablename__ = "portal_sessions"

    id = db.Column(db.Integer, primary_key=True)
    visitor_id = db.Column(db.Integer, db.ForeignKey("visitors.id"), nullable=True, index=True)
    ap_mac = db.Column(db.String(17), nullable=True)
    client_mac = db.Column(db.String(17), nullable=False, index=True)
    ssid = db.Column(db.String(100), nullable=True)
    redirect_url = db.Column(db.Text, nullable=True)
    query_token = db.Column(db.String(100), nullable=True)
    client_id = db.Column(db.String(64), nullable=True)
    authorized = db.Column(db.Boolean, default=False, nullable=False)
    authorized_at = db.Column(db.DateTime, nullable=True)
    expires_at = db.Column(db.DateTime, nullable=True)
    ip_address = db.Column(db.String(45), nullable=True)
    user_agent = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    # Colunas adicionadas na migration 0003
    site_id = db.Column(db.String(64), nullable=True)
    correlation_id = db.Column(db.String(36), nullable=True, index=True)
    consent_version = db.Column(db.String(20), nullable=True)

    visitor = db.relationship("Visitor", back_populates="sessions")

    def mark_authorized(self, client_id: str, expires_at: datetime):
        self.authorized = True
        self.authorized_at = datetime.now(timezone.utc)
        self.client_id = client_id
        self.expires_at = expires_at
