from datetime import datetime
from app.extensions import db


class ConsentEvent(db.Model):
    """
    Histórico completo de eventos de consentimento do visitante.

    Um novo registro é criado a cada aceite ou revogação de termos,
    inclusive quando a versão dos termos é atualizada e o visitante
    precisa consentir novamente.

    Tipos de evento:
        ACCEPTED  — visitante aceitou os termos
        REVOKED   — visitante revogou o consentimento
        UPDATED   — visitante aceitou nova versão dos termos
    """
    __tablename__ = 'consent_events'

    id = db.Column(db.Integer, primary_key=True)
    visitor_id = db.Column(
        db.Integer, db.ForeignKey('visitors.id', ondelete='CASCADE'),
        nullable=False, index=True
    )
    event_type = db.Column(db.String(30), nullable=False)      # ACCEPTED | REVOKED | UPDATED
    terms_version = db.Column(db.String(20), nullable=False)   # ex: "v1.0", "v2.0"
    ip_address = db.Column(db.String(45), nullable=True)
    user_agent = db.Column(db.Text, nullable=True)
    channel = db.Column(db.String(50), nullable=True)          # ex: "portal_wifi", "admin"
    marketing_opt_in = db.Column(db.Boolean, nullable=True)    # valor registrado no momento do aceite
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, index=True)

    visitor = db.relationship('Visitor', back_populates='consent_events')

    def __repr__(self):
        return (
            f'<ConsentEvent id={self.id} visitor_id={self.visitor_id} '
            f'type={self.event_type} version={self.terms_version}>'
        )
