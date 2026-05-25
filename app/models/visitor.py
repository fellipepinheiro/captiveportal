from datetime import datetime
from app.extensions import db


class Visitor(db.Model):
    __tablename__ = 'visitors'

    id = db.Column(db.Integer, primary_key=True)
    full_name = db.Column(db.String(150), nullable=False)
    cpf = db.Column(db.String(11), unique=True, nullable=False, index=True)
    email = db.Column(db.String(150), nullable=False, index=True)
    mobile = db.Column(db.String(20), nullable=False, index=True)
    is_active = db.Column(db.Boolean, nullable=False, default=True)

    # Consentimento LGPD
    consent_at = db.Column(db.DateTime, nullable=True)
    consent_version = db.Column(db.String(20), nullable=True)        # ex: "v1.0"
    consent_ip = db.Column(db.String(45), nullable=True)             # IP do aceite
    consent_channel = db.Column(db.String(50), nullable=True)        # ex: "portal_wifi"
    marketing_opt_in = db.Column(db.Boolean, nullable=False, default=False)

    # Ciclo de vida dos dados (LGPD Art. 18)
    data_deleted_at = db.Column(db.DateTime, nullable=True)          # exclusão solicitada
    anonymized_at = db.Column(db.DateTime, nullable=True)            # anonimização executada
    data_request_at = db.Column(db.DateTime, nullable=True)          # última solicitação do titular

    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(
        db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    sessions = db.relationship('PortalSession', back_populates='visitor', lazy=True)
    consent_events = db.relationship('ConsentEvent', back_populates='visitor', lazy=True)
    data_requests = db.relationship('DataSubjectRequest', back_populates='visitor', lazy=True)

    # ---------------------------------------------------------------------------
    # Propriedades de mascaramento — use estas em logs, templates e audit payloads
    # NUNCA exponha os campos brutos em contextos de log ou exibição pública
    # ---------------------------------------------------------------------------

    @property
    def cpf_masked(self):
        """Retorna CPF mascarado: ***.***.<últimos3>-**"""
        if not self.cpf:
            return None
        c = self.cpf.zfill(11)
        return f'***.***.{c[6:9]}-**'

    @property
    def email_masked(self):
        """Retorna email mascarado: pr***@dominio.com"""
        if not self.email or '@' not in self.email:
            return None
        user, domain = self.email.split('@', 1)
        visible = user[:2] if len(user) >= 2 else user[:1]
        return f'{visible}***@{domain}'

    @property
    def mobile_masked(self):
        """Retorna celular mascarado: (XX) ***-XXXX"""
        if not self.mobile:
            return None
        digits = ''.join(filter(str.isdigit, self.mobile))
        if len(digits) >= 10:
            return f'({digits[:2]}) ***-{digits[-4:]}'
        return f'***-{digits[-4:]}' if len(digits) >= 4 else '***'

    @property
    def is_anonymized(self):
        return self.anonymized_at is not None

    def __repr__(self):
        return f'<Visitor id={self.id} email={self.email_masked} cpf={self.cpf_masked}>'
