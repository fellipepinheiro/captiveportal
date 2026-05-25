from datetime import datetime
from app.extensions import db


class PortalSession(db.Model):
    __tablename__ = 'portal_sessions'

    id = db.Column(db.Integer, primary_key=True)
    visitor_id = db.Column(db.Integer, db.ForeignKey('visitors.id'), nullable=True, index=True)

    # Identificação de rede — manter puro para comunicar com UniFi
    ap_mac = db.Column(db.String(17), nullable=True)
    client_mac = db.Column(db.String(17), nullable=False, index=True)
    ssid = db.Column(db.String(100), nullable=True)
    redirect_url = db.Column(db.Text, nullable=True)
    query_token = db.Column(db.String(100), nullable=True)

    # UniFi
    site_id = db.Column(db.String(64), nullable=True)         # site_id do UniFi
    client_id = db.Column(db.String(64), nullable=True)

    # Autorização
    authorized = db.Column(db.Boolean, nullable=False, default=False)
    authorized_at = db.Column(db.DateTime, nullable=True)
    expires_at = db.Column(db.DateTime, nullable=True)

    # LGPD — versão dos termos aceitos nesta sessão
    consent_version = db.Column(db.String(20), nullable=True)

    # Rastreabilidade — liga todos os audit_logs desta sessão
    correlation_id = db.Column(db.String(36), nullable=True, index=True)

    # Contexto do cliente
    ip_address = db.Column(db.String(45), nullable=True)
    user_agent = db.Column(db.Text, nullable=True)

    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(
        db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    visitor = db.relationship('Visitor', back_populates='sessions')

    @property
    def client_mac_masked(self):
        """MAC mascarado para logs: A4:5E:60:xx:xx:91"""
        if not self.client_mac:
            return None
        parts = self.client_mac.upper().split(':')
        if len(parts) == 6:
            return f'{parts[0]}:{parts[1]}:{parts[2]}:xx:xx:{parts[5]}'
        return 'xx:xx:xx:xx:xx:xx'

    def __repr__(self):
        return (
            f'<PortalSession id={self.id} mac={self.client_mac_masked} '
            f'authorized={self.authorized} corr={self.correlation_id}>'
        )
