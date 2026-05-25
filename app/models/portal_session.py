from datetime import datetime, timezone
from app.extensions import db


class PortalSession(db.Model):
    __tablename__ = "portal_sessions"

    id = db.Column(db.Integer, primary_key=True)
    visitor_id = db.Column(db.Integer, db.ForeignKey("visitors.id"), nullable=True, index=True)
    mac_client = db.Column(db.String(17), nullable=False, index=True)
    mac_ap = db.Column(db.String(17), nullable=True)
    ssid = db.Column(db.String(64), nullable=True)
    redirect_url = db.Column(db.String(512), nullable=True)
    unifi_site_id = db.Column(db.String(64), nullable=True)
    unifi_client_id = db.Column(db.String(64), nullable=True)
    ip_address = db.Column(db.String(45), nullable=True)
    user_agent = db.Column(db.String(512), nullable=True)
    authorized = db.Column(db.Boolean, default=False, nullable=False)
    authorized_at = db.Column(db.DateTime, nullable=True)
    expires_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    visitor = db.relationship("Visitor", back_populates="sessions")

    def mark_authorized(self, unifi_client_id: str, expires_at: datetime):
        self.authorized = True
        self.authorized_at = datetime.now(timezone.utc)
        self.unifi_client_id = unifi_client_id
        self.expires_at = expires_at
