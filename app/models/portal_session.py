from datetime import datetime
from app.extensions import db


class PortalSession(db.Model):
    __tablename__ = 'portal_sessions'

    id = db.Column(db.Integer, primary_key=True)
    visitor_id = db.Column(db.Integer, db.ForeignKey('visitors.id'), nullable=True, index=True)
    ap_mac = db.Column(db.String(17), nullable=True)
    client_mac = db.Column(db.String(17), nullable=False, index=True)
    ssid = db.Column(db.String(100), nullable=True)
    redirect_url = db.Column(db.Text, nullable=True)
    query_token = db.Column(db.String(100), nullable=True)
    client_id = db.Column(db.String(64), nullable=True)
    authorized = db.Column(db.Boolean, nullable=False, default=False)
    authorized_at = db.Column(db.DateTime, nullable=True)
    expires_at = db.Column(db.DateTime, nullable=True)
    ip_address = db.Column(db.String(45), nullable=True)
    user_agent = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(
        db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    visitor = db.relationship('Visitor', back_populates='sessions')
